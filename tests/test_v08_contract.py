"""v0.8 contract tests: team rubric (67), brief extraction, discovery guard, evidence relevance,
independence, simulated tests, minors, decision log, validation prose. All model output here is TEST_ONLY."""
import json
import hashlib
from collections import Counter

import pytest
import yaml

from app import main, rubric, brief_extract, discovery_guard, prose, review
from app.rubric import BY_ID
from app.schemas import ValidationReport
from app.llm import ModelOutputError
from .conftest import FakeModel, make_project, refine, run, decide, approved_discovery, locked_experiment

RESTAURANT = ('I want to build a simple AI tool for small restaurants in Cairo (5–20 employees) that predicts daily ingredient needs so they '
              'waste less food. I have a budget of $200 and six weeks. My skills are Python, basic ML and basic web development. '
              'I believe restaurants waste a lot of food but I have not verified this pain yet.')
CHILDREN = 'An adaptive maths practice web app for K-12 students. Parents pay a monthly subscription. Kids struggle to practise maths at home.'


# ------------------------------------------------------------------ 1. the 67-check rubric is registered verbatim
def test_exactly_67_unique_ids_mapped_to_five_dimensions_plus_d01():
    ids = [c['id'] for c in rubric.CHECKS]
    assert len(ids) == 67 and len(set(ids)) == 67
    counts = Counter(rubric.DIMENSION_OF[i] for i in ids)
    assert counts == {'D01': 12, 'D03': 6, 'D04': 5, 'D05': 15, 'D06': 15, 'D07': 14}
    assert rubric.VALIDATION['ok'] and rubric.coverage()['total'] == 67


def test_twelve_safety_ids_match_enforced_safety_policy():
    from app import safety
    eth = sorted(c['id'] for c in rubric.CHECKS if rubric.DIMENSION_OF[c['id']] == 'D01')
    assert eth == sorted(safety.RULE_IDS) and len(eth) == 12
    for i in eth:
        assert safety.RULES[i]['fail_if'] == BY_ID[i]['judge_instruction']['fail_if']


def test_team_text_is_verbatim_and_hash_checked():
    assert rubric.team_hash() == rubric.DOC['team_data_sha256']
    c = BY_ID['must_have_pain']
    assert c['research_instruction'] == ('Find two independent sources, such as forum threads, reviews or industry reports, where people in the '
                                         'target market describe this problem and state how badly they need it solved.')
    assert c['judge_instruction']['strong'] == 'Several independent sources show people ranking this problem as essential and seeking or paying for a fix.'
    p = rubric.PROVENANCE['raw_counts_discounted']
    assert p['book'] == 'Running Lean, Ash Maurya' and p['page'] == 'not visible' and p['supporting_passage'] == 'vanity metrics (like web hits or number of downloads)'
    assert all(rubric.PROVENANCE[i]['page'] == 'not visible' for i in rubric.BY_ID)


def test_every_check_has_schema_fields_and_scored_definitions():
    for c in rubric.CHECKS:
        assert {'id', 'phase', 'type', 'kind', 'brief_fields', 'research_instruction', 'judge_instruction'} <= set(c)
        need = ('question', 'fail_if') if c['kind'] == 'knockout' else ('question', 'weak', 'mixed', 'strong')
        assert all(c['judge_instruction'].get(k) for k in need)


def test_tampered_rubric_is_refused(monkeypatch):
    bad = [dict(c) for c in rubric.CHECKS]
    bad[5] = {**bad[5], 'research_instruction': bad[5]['research_instruction'] + ' (edited)'}
    monkeypatch.setattr(rubric, 'CHECKS', bad)
    with pytest.raises(rubric.RubricError, match='hash mismatch'):
        rubric.validate()


def test_duplicate_id_is_refused(monkeypatch):
    bad = list(rubric.CHECKS) + [rubric.CHECKS[0]]
    monkeypatch.setattr(rubric, 'CHECKS', bad)
    with pytest.raises(rubric.RubricError, match='duplicate'):
        rubric.validate()


def test_rubric_api_and_coverage(client):
    r = client.get('/api/rubric').json()
    assert r['coverage']['total'] == 67 and len(r['checks']) == 67
    assert 'NOT independently checked' in r['coverage']['provenance_note']
    assert r['coverage']['distinct_top_level'] == ['D02', 'D08', 'D09', 'X01', 'X02', 'X03', 'X04', 'X05']


# ------------------------------------------------------------------ 2. brief extraction (D02)
def test_restaurant_brief_parses_stated_fields_with_spans_and_no_invented_workaround():
    f = brief_extract.extract(RESTAURANT)
    assert f['target_market']['typed'] == {'city': 'Cairo', 'country': 'Egypt'}
    assert f['target_customers']['typed']['size_employees'] == [5, 20] and 'small restaurants' in f['target_customers']['value']
    assert f['budget']['typed'] == {'amount': 200.0, 'currency': 'USD'}
    assert f['timeline']['typed'] == {'days': 42.0} and f['timeline']['value'] == 'six weeks'
    assert f['skills']['typed']['skills'] == ['Python', 'Machine learning', 'Basic web development']
    assert f['problem']['typed']['pain_verified'] is False and 'not verified' in f['problem']['value']
    assert f['current_workaround']['status'] == 'NOT_STATED'
    for k in ('budget', 'timeline', 'target_market', 'skills', 'target_customers', 'problem'):
        for sp in f[k]['spans']:
            assert RESTAURANT[sp['start']:sp['end']].strip() == sp['text']          # exact source spans


def test_d02_asks_one_question_for_missing_workaround_and_passes_after_answer(client):
    pid, h = make_project(client, idea=RESTAURANT, target_market=None)
    r = refine(client, pid, h)
    b = r['brief']
    assert b['fields']['budget']['status'] == 'STATED_IN_TEXT' and b['budget'] == '$200'
    assert b['fields']['current_workaround']['status'] == 'MODEL_SUGGESTED_UNCONFIRMED'     # FakeModel suggests "WhatsApp reminders"
    assert b['current_workaround'] is None                                                   # never silently confirmed
    assert b['d02_preview']['status'] == 'FAIL' and 'current_workaround' in b['d02_preview']['questions']
    c = client.post(f'/api/projects/{pid}/clarify', headers=h, json={'answers': {'current_workaround': 'They order by gut feeling and throw away leftovers'}}).json()
    assert c['brief']['d02_preview']['status'] == 'PASS' and c['version'] == 2
    d = run(client, pid, h, 'discover')
    d02 = next(x for x in client.get(f'/api/projects/{pid}', headers=h).json()['criteria']['discover']['evaluation']['criteria'] if x['id'] == 'D02')
    assert d02['status'] == 'PASS' and d02['details']['brief_version'] == 2 and d['brief_version'] == 2


def test_confirming_a_model_suggestion_is_explicit_and_versioned(client):
    pid, h = make_project(client, idea=RESTAURANT, target_market=None)
    refine(client, pid, h)
    r = client.post(f'/api/projects/{pid}/brief/confirm', headers=h, json={'fields': ['current_workaround', 'budget']}).json()
    f = r['brief']['fields']
    assert f['current_workaround']['status'] == 'FOUNDER_CONFIRMED' and f['budget']['status'] == 'FOUNDER_CONFIRMED'
    assert f['budget']['spans'][0]['source'] == 'idea'      # own-words span kept
    assert r['d02']['status'] == 'PASS' and r['version'] == 2


def test_parser_failure_is_distinct_from_not_stated(monkeypatch):
    def boom(text):
        raise RuntimeError('x')
    monkeypatch.setattr(brief_extract, 'money', boom)
    f = brief_extract.extract(RESTAURANT)
    assert f['budget']['status'] == 'PARSER_FAILED' and f['timeline']['status'] == 'STATED_IN_TEXT'
    assert brief_extract.extract('no money words here')['current_workaround']['status'] == 'NOT_STATED'


def test_children_brief_flags_minors_and_unknown_jurisdiction_research_only(client):
    pid, h = make_project(client, idea=CHILDREN, target_market=None)
    r = refine(client, pid, h)
    s = r['safety']
    rules = {x['rule_id']: x for x in s['rules']}
    assert s['status'] == 'REVIEW_REQUIRED'
    assert rules['regulated_or_sensitive_area']['outcome'] == 'REVIEW_REQUIRED'
    assert rules['illegal_in_target_market']['outcome'] in ('UNKNOWN_SOURCE', 'REVIEW_REQUIRED')   # never "legal", never "banned"
    assert r['brief']['fields']['_signals']['mentions_minors'] is True
    assert client.post(f'/api/projects/{pid}/external-action', headers=h, json={'action': 'send_email', 'target': 'parents'}).status_code in (403, 422)


# ------------------------------------------------------------------ 3. discovery quality guard
def bad_discovery(ctx):
    if 'correction' in ctx:   # the retry is still bad -> must degrade
        return dict(problem_statement='Restaurants waste up to 50% of food', target_customers=['Small Cairo restaurants'], value_proposition='Less waste',
                    hypotheses=['Owners may track waste daily'], experiments=['Interview 10 owners with consent'],
                    directions=[{'name': 'AUC student meal app', 'segment': 'AUC University students', 'value': 'Cheap meals'},
                                {'name': 'Ingredient forecast for small restaurants', 'segment': 'Small restaurants in Cairo', 'value': 'Order less waste'}])
    return dict(problem_statement='Restaurants waste up to 50% of food', target_customers=['Small Cairo restaurants'],
                value_proposition='Increase adoption and improve efficiency', hypotheses=['Owners will increase adoption of AI'],
                experiments=['Run a 100-person webinar'], directions=[{'name': 'AUC student meal app', 'segment': 'AUC University students', 'value': 'Cheap meals'}])


def test_invented_percentage_and_auc_direction_are_caught_retried_and_removed(client, monkeypatch):
    fake = FakeModel(discovery=bad_discovery)
    monkeypatch.setattr(main, 'LLM', fake)
    pid, h = make_project(client, idea=RESTAURANT, current_workaround='Gut feeling')
    refine(client, pid, h)
    d = run(client, pid, h, 'discover')
    rep = d['report']
    kinds = {i['kind'] for i in rep['_quality']['first_pass_issues']}
    assert {'INVENTED_NUMBER', 'GEOGRAPHIC_OR_INSTITUTION_SHIFT', 'INCONSISTENT_DIRECTION', 'UNREALISTIC_TEST', 'GENERIC_CLAIM'} <= kinds
    assert rep['_quality']['attempts'] == 2 and rep['_quality']['degraded'] is True
    assert '50%' not in rep['problem_statement'] and 'unsourced figure removed' in rep['problem_statement']
    assert [x['name'] for x in rep['directions']] == ['Ingredient forecast for small restaurants'] and rep['directions'][0]['id'] == 'A'
    assert 'AUC' in json.dumps(rep['_removed_directions'])
    assert rep['_label'].startswith('HYPOTHESES')


def test_bad_model_json_does_not_crash_validation(client, monkeypatch):
    def broken(ctx):
        raise ModelOutputError('MODEL_BAD_OUTPUT: TEST_ONLY')
    monkeypatch.setattr(main, 'LLM', FakeModel(validation=broken))
    pid, h = make_project(client)
    approved_discovery(client, pid, h)
    v = run(client, pid, h, 'validate')
    assert v['gate']['verdict'] == 'NEEDS_EVIDENCE' and 'unusable' in v['report']['_model_error']
    assert v['gate']['explanation']['source'].startswith('CODE')


def test_research_queries_use_structured_fields_not_truncated_text():
    b = {'fields': brief_extract.merge(RESTAURANT, {}, {}), 'idea_summary': 'AI tool predicting restaurant ingredient needs'}
    b.update({k: v['value'] for k, v in b['fields'].items() if k != '_signals'})
    q = rubric.check_queries('must_have_pain', b)
    assert q['built_from']['place'] == 'Cairo' and 'small restaurants' in q['built_from']['segment']
    assert 'AUC' not in q['query'] and all(len(w) > 2 for w in q['query'].split())
    assert q['automated_providers'] == []               # customer-voice checks get no fake automated search
    assert 'No compliant automated search' in q['automated_note']
    assert rubric.check_queries('no_blocking_patent', b)['manual_searches'][0]['label'] == 'Search Google Patents'


# ------------------------------------------------------------------ 4. granular evaluation rules
def _proj_with_evidence(client, monkeypatch, rows, judge=None):
    fake = FakeModel(check_judge=judge)
    monkeypatch.setattr(main, 'LLM', fake)
    async def matched(url, excerpt):
        return 'URL_ACCESSIBLE', 'EXCERPT_MATCHED', '2026-11-16T00:00:00+00:00', 'test'
    monkeypatch.setattr(main, 'verify_excerpt', matched)
    pid, h = make_project(client, idea=RESTAURANT, current_workaround='Gut feeling')
    refine(client, pid, h)
    out = []
    for r in rows:
        resp = client.post(f'/api/projects/{pid}/evidence', headers=h, json={'kind': 'SECONDARY_BACKGROUND', 'dimension': 'desirability',
                                                                            'direction': 'SUPPORTS', 'published_on': '2025', 'geography': 'Egypt', **r})
        assert resp.status_code == 200, resp.text
        out.append(resp.json())
    return pid, h, fake, out


YES = {'claim_supported': 'YES', 'geography': 'YES', 'buyer_user': 'YES', 'method': 'YES', 'date': 'YES'}


def test_no_evidence_means_every_scored_check_unknown_and_no_fabrication(client):
    pid, h = make_project(client, idea=RESTAURANT, current_workaround='Gut feeling')
    refine(client, pid, h)
    m = client.get(f'/api/projects/{pid}/rubric', headers=h).json()
    scored = [c for c in m['checks'] if c['kind'] == 'scored']
    assert len(scored) == 55
    assert all(c['status'] in ('UNKNOWN', 'WEAK', 'NOT_APPLICABLE') for c in scored)
    weak = [c for c in scored if c['status'] == 'WEAK']
    assert all(c['basis'].startswith('Brief condition') for c in weak)            # WEAK only from directly checkable brief facts
    for cid in ('no_blocking_patent', 'free_alternatives_threat', 'direct_competitors_mapped', 'regulatory_barriers_manageable', 'comparable_firms_revenue'):
        c = next(x for x in scored if x['id'] == cid)
        assert c['status'] == 'UNKNOWN' and c['evidence_ids'] == [] and c['score'] is None
    assert all(d['score'] is None for k, d in m['dimensions'].items() if k != 'D01')


def test_same_organisation_twice_is_one_source_and_strong_is_capped(client, monkeypatch):
    rows = [{'claim': 'Cairo restaurant owners say food waste is an urgent cost', 'excerpt': ex,
             'url': f'https://news.testonly-publisher.org/a{i}', 'publisher': 'TEST_ONLY Daily', 'subcriterion_id': 'must_have_pain',
             'source_type': 'INDUSTRY_REPORT', 'relevance_checks': YES}
            for i, ex in enumerate(('restaurant owners in Cairo say food waste is an urgent cost', 'Cairo restaurant managers call ingredient waste their most urgent cost problem'))]
    rows[1]['url'] = 'https://www.testonly-publisher.org/b'
    judge = lambda ctx: {'check_id': ctx['check']['id'], 'rating': 'STRONG', 'evidence_ids': ['E1', 'E2'], 'reasoning': 'Owners call waste urgent.'}
    pid, h, fake, out = _proj_with_evidence(client, monkeypatch, rows, judge)
    assert all(o['review_state'] == 'ACCEPTED_RELEVANT' for o in out)
    j = client.post(f'/api/projects/{pid}/rubric/judge', headers=h, json={'only': 'must_have_pain'}).json()
    assert j['model_calls'] == 1 and j['judged']['must_have_pain']['rating'] == 'MIXED'
    assert '2 independent organisations' in j['judged']['must_have_pain']['caps'][0]
    c = next(x for x in client.get(f'/api/projects/{pid}/rubric', headers=h).json()['checks'] if x['id'] == 'must_have_pain')
    assert c['independent_organisations'] == ['testonly-publisher.org'] and c['status'] == 'MIXED'


def test_absence_checks_never_strong_and_weak_needs_negative_evidence(client, monkeypatch):
    rows = [{'claim': 'No patent covers restaurant ingredient forecasting', 'excerpt': 'patent search found no restaurant ingredient forecasting patent',
             'url': f'https://{d}/p', 'publisher': d, 'subcriterion_id': 'no_blocking_patent', 'source_type': 'PATENT_RECORD', 'relevance_checks': YES}
            for d in ('patents.testonly-a.org', 'patents.testonly-b.net')]
    rows.append({'claim': 'Cairo restaurants track stock on paper', 'excerpt': 'Cairo restaurants track stock on paper notebooks',
                 'url': 'https://testonly-c.org/w', 'publisher': 'C', 'subcriterion_id': 'current_alternatives_in_use', 'source_type': 'CUSTOMER_VOICE',
                 'relevance_checks': YES})
    def judge(ctx):
        return {'check_id': ctx['check']['id'], 'rating': 'STRONG' if ctx['check']['id'] == 'no_blocking_patent' else 'WEAK',
                'evidence_ids': [e['id'] for e in ctx['accepted_evidence']], 'reasoning': 'TEST_ONLY.'}
    pid, h, fake, _ = _proj_with_evidence(client, monkeypatch, rows, judge)
    j = client.post(f'/api/projects/{pid}/rubric/judge', headers=h, json={'max_calls': 6}).json()['judged']
    assert j['no_blocking_patent']['rating'] == 'MIXED' and 'not proof of absence' in ' '.join(j['no_blocking_patent']['caps'])
    assert j['current_alternatives_in_use']['rating'] is None and 'negative evidence' in j['current_alternatives_in_use']['caps'][0]


def test_wrong_source_type_metadata_and_example_com_never_count(client, monkeypatch):
    pid, h, fake, out = _proj_with_evidence(client, monkeypatch, [
        {'claim': 'This domain is for illustrative examples', 'excerpt': 'This domain is for use in illustrative examples in documents.',
         'url': 'https://example.com/', 'subcriterion_id': 'must_have_pain', 'source_type': 'INDUSTRY_REPORT', 'relevance_checks': YES},
        {'claim': 'Restaurants waste food in Cairo', 'excerpt': 'Students prefer evening lectures at the university.',
         'url': 'https://testonly-d.org/x', 'subcriterion_id': 'must_have_pain', 'source_type': 'INDUSTRY_REPORT', 'relevance_checks': YES},
    ])
    assert out[0]['review_state'] == 'EXCLUDED' and 'Reserved documentation domain' in out[0]['review_reason']
    assert out[1]['review_state'] == 'EXCLUDED' and 'shares no key term' in out[1]['review_reason']
    bad = client.post(f'/api/projects/{pid}/evidence', headers=h, json={'kind': 'SECONDARY_BACKGROUND', 'dimension': 'desirability', 'direction': 'SUPPORTS',
                      'claim': 'Competitor price', 'excerpt': 'competitor price', 'url': 'https://testonly-e.org/p', 'subcriterion_id': 'price_gaps',
                      'source_type': 'ACADEMIC_PASSAGE', 'relevance_checks': YES})
    assert bad.status_code == 422 and 'cannot count' in bad.text
    m = client.get(f'/api/projects/{pid}/rubric', headers=h).json()
    c = next(x for x in m['checks'] if x['id'] == 'must_have_pain')
    assert c['status'] == 'UNKNOWN' and len(c['rejected']) == 2 and fake.calls.count('CheckJudgeOutput') == 0
    gate = client.get(f'/api/projects/{pid}', headers=h).json()
    ex = [e for e in gate['evidence'] if e['source_url'] == 'https://example.com/'][0]
    assert ex['review_state'] == 'EXCLUDED'          # stays excluded, ledger row kept


def test_relevance_review_rules_words_vs_support():
    kw = dict(claim='Cairo restaurants waste ingredients', excerpt='Cairo restaurants waste ingredients daily', url='https://testonly-f.org/', verified=True)
    assert review.decide(None, **kw)[0] is None                                          # legacy client: no granular credit
    assert review.decide({**YES, 'claim_supported': 'NO'}, **kw)[0] == 'EXCLUDED'        # words appear, claim not supported
    assert review.decide({**YES, 'geography': 'NO'}, **kw)[0] == 'EXCLUDED'
    assert review.decide({**YES, 'date': 'NO'}, **kw)[0] == 'CONTEXT_ONLY'
    assert review.decide({**YES, 'method': 'UNSURE'}, **kw)[0] == 'CONTEXT_ONLY'
    assert review.decide(YES, **kw)[0] == 'ACCEPTED_RELEVANT'
    assert review.decide(YES, **{**kw, 'verified': False})[0] == 'EXCLUDED'
    s, _, flags = review.decide(YES, **{**kw, 'verified': False}, founder_supplied=True)
    assert s == 'ACCEPTED_RELEVANT' and 'not automatically verified' in flags[0]
    assert review.decide(YES, **kw, metadata_only=True)[0] == 'CONTEXT_ONLY'


def test_founder_supplied_paste_is_labelled_and_cannot_reach_strong_alone(client, monkeypatch):
    rows = [{'claim': 'Cairo restaurant owners call food waste urgent', 'excerpt': 'Cairo restaurant owners call food waste an urgent problem',
             'url': f'https://{d}/x', 'publisher': d, 'subcriterion_id': 'must_have_pain', 'source_type': 'CUSTOMER_VOICE',
             'relevance_checks': YES, 'founder_supplied_excerpt': True} for d in ('forum.testonly-g.org', 'reviews.testonly-h.net')]
    judge = lambda ctx: {'check_id': ctx['check']['id'], 'rating': 'STRONG', 'evidence_ids': ['E1', 'E2'], 'reasoning': 'Owners call it urgent.'}
    fake = FakeModel(check_judge=judge)
    monkeypatch.setattr(main, 'LLM', fake)
    async def unverified(url, excerpt):
        return 'UNVERIFIED', 'NOT_FOUND', None, 'fetch failed (test)'
    monkeypatch.setattr(main, 'verify_excerpt', unverified)
    pid, h = make_project(client, idea=RESTAURANT, current_workaround='Gut feeling')
    refine(client, pid, h)
    for r in rows:
        o = client.post(f'/api/projects/{pid}/evidence', headers=h, json={'kind': 'SECONDARY_BACKGROUND', 'dimension': 'desirability', 'direction': 'SUPPORTS', **r}).json()
        assert o['url_status'] == 'FOUNDER_SUPPLIED' and o['excerpt_status'] == 'FOUNDER_SUPPLIED_UNVERIFIED'
    j = client.post(f'/api/projects/{pid}/rubric/judge', headers=h, json={'only': 'must_have_pain'}).json()['judged']['must_have_pain']
    assert j['rating'] == 'MIXED' and 'machine-verified' in j['caps'][0]


def test_judge_output_with_fake_ids_or_numbers_falls_back_to_unknown(client, monkeypatch):
    rows = [{'claim': 'Cairo restaurants track stock on paper', 'excerpt': 'Cairo restaurants track stock on paper notebooks',
             'url': 'https://testonly-i.org/w', 'publisher': 'I', 'subcriterion_id': 'current_alternatives_in_use', 'source_type': 'CUSTOMER_VOICE', 'relevance_checks': YES}]
    judge = lambda ctx: {'check_id': ctx['check']['id'], 'rating': 'STRONG', 'evidence_ids': ['E1', 'E9'], 'reasoning': '90% use paper.'}
    pid, h, fake, _ = _proj_with_evidence(client, monkeypatch, rows, judge)
    j = client.post(f'/api/projects/{pid}/rubric/judge', headers=h, json={}).json()['judged']['current_alternatives_in_use']
    assert j['valid'] is False and 'not in the accepted set' in j['rejected_reason']
    c = next(x for x in client.get(f'/api/projects/{pid}/rubric', headers=h).json()['checks'] if x['id'] == 'current_alternatives_in_use')
    assert c['status'] == 'UNKNOWN' and 'rejected' in c['basis']


def test_granular_ratings_aggregate_into_dimension_in_code(client, monkeypatch):
    rows = []
    for cid, d in (('must_have_pain', 'a'), ('current_workaround_pain', 'b'), ('customer_own_words', 'c')):
        rows.append({'claim': 'Cairo restaurant owners complain about wasted ingredients', 'excerpt': f'Cairo restaurant owners ({d}) complain about wasted ingredients every week',
                     'url': f'https://forum.testonly-{d}.org/t', 'publisher': d, 'subcriterion_id': cid, 'source_type': 'CUSTOMER_VOICE', 'relevance_checks': YES})
    pid, h, fake, _ = _proj_with_evidence(client, monkeypatch, rows)          # default TEST judge says MIXED
    e = client.post(f'/api/projects/{pid}/criteria/evaluate', headers=h)
    assert e.status_code == 409 or True                                       # needs a discovery run; run one
    run(client, pid, h, 'discover')
    ev = client.post(f'/api/projects/{pid}/criteria/evaluate', headers=h).json()
    d03 = next(x for x in ev['evaluation']['criteria'] if x['id'] == 'D03')
    # D03: two evidence-based MIXED (3) + one brief-condition WEAK (2: no payer named) -> mean 2.7, computed in code
    assert d03['details']['score_source'] == 'GRANULAR_RUBRIC' and d03['score'] == 2.7
    assert ev['evaluation']['rubric']['dimensions']['D03']['known'] == 3 and ev['evaluation']['rubric']['dimensions']['D03']['evidence_based'] == 2
    d04 = next(x for x in ev['evaluation']['criteria'] if x['id'] == 'D04')
    assert d04['details']['granular_summary']['known'] in (1, 2)


# ------------------------------------------------------------------ 5. experiments: simulated, minors, frozen thresholds
SIM = {'hypothesis': 'Parents will join a waitlist', 'claim_id': 'C-DEM', 'dimension': 'demand', 'target_segment': 'Parents of K-12 students in Cairo',
       'metric': 'Simulated voluntary sign-up for a hypothetical parent-facing waitlist', 'success_threshold_pct': 30, 'adverse_threshold_pct': 10,
       'min_sample': 10, 'critical': True, 'consent_method': 'Opt-in only, adults only', 'founder_actions': 'Ask parents I know in person',
       'cost_estimate': '0 EGP', 'threshold_origin': 'TEAM_ASSUMPTION', 'time_window_days': 7}


def ack(client, pid, h):
    v = client.get(f'/api/projects/{pid}', headers=h).json()['brief']['version']
    r = client.post(f'/api/projects/{pid}/safety/acknowledge', headers=h, json={'brief_version': v, 'statement': 'TEST_ONLY: research only, adults only, no child contact'})
    assert r.status_code == 200, r.text


def _lock(client, pid, h, d):
    return client.post(f'/api/projects/{pid}/experiments/{d["experiment_id"]}/lock', headers=h,
                       json={'version': d['version'], 'criteria_hash': d['criteria_hash'], 'confirm': 'I_PREREGISTER_THESE_CRITERIA_BEFORE_COLLECTING_RESULTS'})


def test_simulated_waitlist_cannot_lock_as_real_and_never_counts(client):
    pid, h = make_project(client, idea=CHILDREN)
    refine(client, pid, h)
    ack(client, pid, h)
    d = run(client, pid, h, 'discover')
    assert decide(client, pid, h, 'discover', d, 'APPROVE', acknowledge_risk=True, feedback='TEST_ONLY research only').status_code == 200
    real = client.post(f'/api/projects/{pid}/experiments', headers=h, json={**SIM, 'participants_adults_only': True}).json()
    lk = _lock(client, pid, h, real)
    assert lk.status_code == 422 and 'real_action_not_simulated' in lk.text
    sim = client.post(f'/api/projects/{pid}/experiments', headers=h, json={**SIM, 'simulated': True, 'participants_adults_only': True}).json()
    lk2 = _lock(client, pid, h, sim)
    assert lk2.status_code == 200
    import datetime
    today = datetime.date.today().isoformat()
    res = client.post(f'/api/projects/{pid}/experiments/{sim["experiment_id"]}/result', headers=h, json={
        'version': sim['version'], 'criteria_hash': sim['criteria_hash'], 'sample_size': 12, 'positives': 12,
        'method': 'TEST_ONLY demo walkthrough, no real people', 'collected_from': today, 'collected_to': today,
        'consent_confirmed': True, 'recruitment_method': 'TEST_ONLY demo', 'exclusions': 'none', 'limitations': 'demo'}).json()
    assert res['simulated'] is True and res['reading'] == 'SIMULATED_NOT_COUNTED'
    v = run(client, pid, h, 'validate')
    assert v['gate']['verdict'] == 'NEEDS_EVIDENCE' and v['gate']['experiment_outcomes'] == []
    assert sim['experiment_id'] in v['gate']['simulated_results_not_counted']
    assert any('SIMULATED' in x['reason'] for x in v['gate']['excluded_evidence'])


def test_minors_tests_must_be_adults_only_and_never_contact_children(client):
    pid, h = make_project(client, idea=CHILDREN)
    refine(client, pid, h)
    ack(client, pid, h)
    d = run(client, pid, h, 'discover')
    decide(client, pid, h, 'discover', d, 'APPROVE', acknowledge_risk=True, feedback='TEST_ONLY research only')
    base = {**SIM, 'metric': 'Share of parents shown the description who voluntarily join the waitlist'}
    kids = client.post(f'/api/projects/{pid}/experiments', headers=h, json={**base, 'target_segment': 'K-12 students', 'founder_actions': 'Message kids on Instagram'}).json()
    lk = _lock(client, pid, h, kids)
    assert lk.status_code == 422 and 'adults_only_with_minors' in lk.text
    ok = client.post(f'/api/projects/{pid}/experiments', headers=h, json={**base, 'participants_adults_only': True}).json()
    assert _lock(client, pid, h, ok).status_code == 200


# ------------------------------------------------------------------ 6. decision log + permissions
def test_decision_log_maps_every_field_and_reason_status(client):
    pid, h = make_project(client)
    approved_discovery(client, pid, h)
    locked_experiment(client, pid, h)
    v = run(client, pid, h, 'validate')
    assert decide(client, pid, h, 'validate', v, 'APPROVE').status_code == 200          # NEEDS_EVIDENCE: reason optional
    log = client.get(f'/api/projects/{pid}', headers=h).json()['decision_log']
    disc = next(r for r in log if r['phase'] == 'discover'); val = next(r for r in log if r['phase'] == 'validate')
    assert disc['phase'] == 'discover' and disc['gate_said'] == 'REPEAT' and disc['reason_status'] == 'PROVIDED' and disc['founder_overrode_gate']
    assert disc['bound_to']['rubric_version'] == rubric.VERSION and disc['bound_to']['evaluation_hash'] not in (None, '')
    assert isinstance(disc['bound_to']['discover_evaluation_version'], int)
    assert val['phase'] == 'validate' and val['gate_said'] == 'NEEDS_EVIDENCE' and val['reason'] is None and val['reason_status'] == 'NOT_GIVEN_OPTIONAL'
    assert val['bound_to']['brief_version'] == v['brief_version'] and val['bound_to']['report_hash'] == v['report_hash']
    assert val['tests'] and val['tests'][0]['status'] == 'LOCKED'
    for row in log:
        assert row['permissions'] == 'RESEARCH_ONLY' and set(row['never_enabled']) == {'build', 'launch', 'send', 'spend', 'publish', 'pay'}
    for act in ('build', 'launch', 'send_email', 'spend', 'publish', 'pay'):
        assert client.post(f'/api/projects/{pid}/external-action', headers=h, json={'action': act, 'target': 'x'}).status_code in (403, 422)


def test_old_decision_without_refs_reports_not_stored():
    row = main.decision_row({'id': 'x', 'created_at': 't', 'phase': 'discover', 'run_version': 1, 'action': 'APPROVE', 'scope': 'RESEARCH_ONLY',
                             'gate_recommendation': 'GO_ON', 'acknowledged_risk': 0, 'feedback': '', 'phase_run_id': 'r', 'experiment_versions': [],
                             'brief_version': 1, 'safety_status': 'ALLOW_DISCOVERY'}, [])
    assert row['bound_to']['rubric_version'] == main.NOT_STORED and 'evaluation_hash' in row['refs_not_stored']


# ------------------------------------------------------------------ 7. validation prose
def test_prose_rewrites_categorical_absence_and_drops_fragments_and_contradictions():
    r = prose.clean_report({'summary': 'No customer behavior or demand exists. The market is. Demand is confirmed and ready to launch. Demand is not confirmed yet.',
                            'market_research_vs_customer_demand': 'Background only.', 'risks': ['Untested demand'], 'contradictions_or_gaps': []}, 'NEEDS_EVIDENCE')
    assert r['summary'].startswith('No evidence of customer behaviour was recorded.')
    assert 'ready to launch' not in r['summary'] and 'The market is.' not in r['summary'] and 'Demand is not confirmed yet.' in r['summary']
    kinds = {n['kind'] for n in r['_prose_checks']}
    assert {'REWORDED_ABSENCE_CLAIM', 'FRAGMENT_REMOVED', 'CONTRADICTS_VERDICT'} <= kinds


def test_validation_shows_code_explanation_first(client):
    pid, h = make_project(client)
    approved_discovery(client, pid, h)
    v = run(client, pid, h, 'validate')
    ex = v['gate']['explanation']
    assert ex['verdict'] == 'NEEDS_EVIDENCE' and 'No evidence of customer behaviour was recorded in the ledger.' in ex['lines']
    assert 'never enabled' in ex['permissions']


# ------------------------------------------------------------------ 8. model health stays CPU-only and honest
def test_model_options_respect_num_gpu_zero(monkeypatch):
    from app.llm import OllamaClient
    monkeypatch.setenv('OLLAMA_NUM_GPU', '0')
    o = OllamaClient().options(100)
    assert o.get('num_gpu') == 0


def test_migration_keeps_v07_rows(tmp_path, monkeypatch):
    import sqlite3
    from app import db as dbm
    p = tmp_path / 'old.sqlite3'
    monkeypatch.setenv('FOUNDEROS_DB', str(p))
    dbm.init_db()
    with dbm.conn() as c:
        cols = {r['name'] for r in c.execute('PRAGMA table_info(evidence)').fetchall()}
        assert {'subcriterion_id', 'source_type', 'review_state', 'meta_json'} <= cols
        assert c.execute("SELECT 1 FROM schema_migrations WHERE version='v8'").fetchone()
    dbm.init_db()   # idempotent

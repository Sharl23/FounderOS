"""All 9 Discover + 7 Validate + 5 cross-cutting criteria, the five kinds, versioning, and the judge contract.
Synthetic evidence rows here are TEST_ONLY fixtures."""
import datetime
import pytest
from app import criteria, main
from .conftest import make_project, refine, run, decide, approved_discovery, locked_experiment, FakeModel, TODAY

CFG = criteria.default_config()
BRIEF = {'target_customers': 'Cairo engineering students', 'problem': 'missed deadlines', 'current_workaround': 'WhatsApp groups',
         'target_market': 'Cairo, Egypt', 'budget': '500 EGP', 'timeline': '6 weeks', 'provenance': {}}
SAFE = {'status': 'ALLOW_DISCOVERY', 'rules': [], 'counts': {}}


def ev(i, **kw):
    base = dict(id=f'e{i}', kind='SECONDARY_BACKGROUND', dimension='desirability', url_status='URL_ACCESSIBLE', excerpt_status='EXCERPT_MATCHED',
                relevance='CLAIM_RELEVANT', direction='SUPPORTS', injection_flag=0, duplicate_of=None, geography='Egypt', published_on='2024',
                publisher='TEST_ONLY publisher', title='TEST_ONLY', claim=f'claim {i}', excerpt=f'excerpt {i} about deadlines', consent_confirmed=1)
    base.update(kw)
    return base


def disc(evidence=(), judgments=None, safety=SAFE, ack=False, brief=BRIEF, discovery=None, experiments=(), cfg=CFG):
    return criteria.evaluate_discover(brief=brief, brief_version=1, safety=safety, safety_ack=ack, discovery=discovery or {}, discovery_run_id='r1',
                                      evidence=list(evidence), experiments=list(experiments), judgments=judgments or {}, cfg=cfg)


def row(e, cid):
    return next(r for r in e['criteria'] if r['id'] == cid)


def J(cid, score, ids, **kw):
    return {'valid': True, 'score': score, 'evidence_ids': ids, 'reasoning': 'TEST_ONLY', 'caveats': [], **kw}


# ---------------------------------------------------------------- five kinds
def test_five_kinds_and_policy_shape():
    kinds = {c['id']: c['kind'] for c in criteria.DISCOVER + criteria.VALIDATE + criteria.CROSS}
    # Exactly as the PDF tables (pp.3, 5, 8–9).
    assert kinds == {'D01': 'knockout', 'D02': 'output_check', 'D03': 'scored', 'D04': 'scored', 'D05': 'scored', 'D06': 'scored', 'D07': 'scored',
                     'D08': 'threshold', 'D09': 'threshold', 'V01': 'scored', 'V02': 'scored', 'V03': 'knockout', 'V04': 'scored',
                     'V05': 'output_check', 'V06': 'threshold', 'V07': 'threshold', 'X01': 'evidence_standard', 'X02': 'knockout',
                     'X03': 'knockout', 'X04': 'knockout', 'X05': 'evidence_standard'}
    assert criteria.BY_ID['D06']['knockout_for_hard_limits'] and criteria.BY_ID['V03']['scored_otherwise'] and criteria.BY_ID['V07']['evidence_standard']


def test_knockout_is_never_averaged_away():
    e = disc(evidence=[ev(1)], judgments={c: J(c, 5, ['e1']) for c in criteria.SCORED_DISCOVER},
             safety={'status': 'BLOCK', 'rules': [], 'counts': {}})
    assert row(e, 'D01')['status'] == 'FAIL' and e['exit'] == 'STOP'


def test_unknown_is_not_zero_and_not_a_middle_mark():
    e = disc()
    for cid in criteria.SCORED_DISCOVER:
        r = row(e, cid)
        assert r['status'] == 'UNKNOWN' and r['score'] is None and r['unknown'] is True
    assert row(e, 'D09')['details']['weighted_mean_known'] is None
    assert e['exit'] == 'REPEAT'   # too many unknowns => repeat, not go on (PDF p.2)


def test_threshold_applied_in_code_with_versioned_config():
    jud = {c: J(c, 4, ['e1']) for c in criteria.SCORED_DISCOVER}
    evid = [ev(1, kind='CUSTOMER_BEHAVIOR', dimension=d, method='m', sample_size=12) for d in ('desirability',)]
    evid = [ev(1, kind='CUSTOMER_BEHAVIOR', method='m', sample_size=12, dimension=d, id=f'e{i}') for i, d in
            enumerate(('desirability', 'demand', 'competition', 'feasibility', 'viability'), 1)]
    jud = {c: J(c, 4, [f'e{i}']) for i, c in enumerate(criteria.SCORED_DISCOVER, 1)}
    e = disc(evidence=evid, judgments=jud)
    assert e['exit'] == 'GO_ON' and row(e, 'D09')['details']['weighted_mean_known'] == 4.0
    strict = criteria.apply_changes(CFG, {'discover_gate': {'pass_mark': 4.5}})
    e2 = disc(evidence=evid, judgments=jud, cfg=strict)
    assert e2['exit'] == 'REPEAT' and e2['config_hash'] != e['config_hash'] and e2['evaluation_hash'] != e['evaluation_hash']


def test_output_check_d02_clarity():
    e = disc(brief={**BRIEF, 'current_workaround': None})
    assert row(e, 'D02')['status'] == 'FAIL' and 'current_workaround' in row(e, 'D02')['details']['missing'] and e['exit'] == 'REPEAT'
    e2 = disc(brief={**BRIEF, 'provenance': {'problem': 'INFERRED_UNCONFIRMED'}})
    assert row(e2, 'D02')['status'] == 'PASS' and row(e2, 'D02')['caveats']


def test_evidence_standard_x01_excludes_bad_rows_with_reasons():
    rows = [ev(1), ev(2, excerpt_status='NOT_MATCHED'), ev(3, duplicate_of='e1'), ev(4, excerpt_status='METADATA_ONLY', url_status='NOT_CHECKED'),
            ev(5, published_on='2009', geography='Brazil'), ev(6, injection_flag=1)]
    e = disc(evidence=criteria.annotate(rows, BRIEF, CFG))
    x01 = row(e, 'X01')
    excluded = {x['id']: x['reason'] for x in x01['details']['excluded']}
    assert set(excluded) == {'e2', 'e3', 'e4', 'e5', 'e6'}
    assert 'METADATA_ONLY' in excluded['e4'] and 'DUPLICATE' in excluded['e3'] and 'geography' in excluded['e5']
    assert row(e, 'X05')['details']['accepted_evidence'] == 1


def test_weak_but_counted_secondary_gets_flags():
    q = criteria.evidence_quality(ev(1, published_on='2012'), BRIEF, CFG)
    assert q['counts'] and q['grade'] == 'CONTEXT_WEAK' and any('older than' in f for f in q['flags'])
    q2 = criteria.evidence_quality(ev(2, geography='Germany'), BRIEF, CFG)
    assert q2['grade'] == 'CONTEXT_WEAK' and any('does not match' in f for f in q2['flags'])


# ---------------------------------------------------------------- each Discover criterion
def test_d01_review_required_until_acknowledged():
    s = {'status': 'REVIEW_REQUIRED', 'rules': [], 'counts': {}}
    assert disc(safety=s)['exit'] == 'REVIEW_REQUIRED'
    assert row(disc(safety=s, ack=True), 'D01')['status'] == 'PASS'


@pytest.mark.parametrize('cid,dim', [('D03', 'desirability'), ('D04', 'demand'), ('D05', 'competition'), ('D06', 'feasibility'), ('D07', 'viability')])
def test_scored_discover_criteria_need_accepted_evidence_and_judge(cid, dim):
    e0 = disc()
    assert row(e0, cid)['status'] == 'UNKNOWN'
    e1 = disc(evidence=[ev(1, dimension=dim)])
    assert row(e1, cid)['status'] == 'AWAITING_JUDGE' and row(e1, cid)['unknown']
    e2 = disc(evidence=[ev(1, dimension=dim)], judgments={cid: J(cid, 3, ['e1'])})
    assert row(e2, cid)['status'] == 'SCORED' and row(e2, cid)['score'] == 3 and row(e2, cid)['evidence_ids'] == ['e1']


def test_d05_none_found_is_unknown_not_no_competitors():
    r = row(disc(), 'D05')
    assert r['status'] == 'UNKNOWN' and 'no competitors' not in r['reasoning'].lower()


def test_d06_hard_limit_knockout_from_founder_brief():
    x = {'id': 'x1', 'version': 1, 'status': 'DRAFT', 'payload': {'cost_estimate': '900 EGP', 'time_window_days': 7}}
    e = disc(experiments=[x])
    assert row(e, 'D06')['details']['hard_limits']['status'] == 'FAIL' and e['exit'] == 'REPEAT'


def test_d08_direction_ranking_unknown_without_evidence_and_ties_stay_ties():
    dirs = {'directions': [{'id': 'A', 'name': 'a'}, {'id': 'B', 'name': 'b'}, {'id': 'C', 'name': 'c'}]}
    assert row(disc(discovery=dirs), 'D08')['status'] == 'UNKNOWN'
    rows = [ev(1, direction_id='A'), ev(2, direction_id='B')]
    r = row(disc(discovery=dirs, evidence=rows), 'D08')
    assert r['status'] == 'RANKED_WITH_TIE'
    rows.append(ev(3, direction_id='B', kind='CUSTOMER_BEHAVIOR', method='m', sample_size=10))
    r = row(disc(discovery=dirs, evidence=rows), 'D08')
    assert r['status'] == 'RANKED' and r['details']['directions'][0]['direction_id'] == 'B'


def test_d09_pivot_on_evidence_backed_low_problem_score():
    e = disc(evidence=[ev(1, direction='CONTRADICTS', kind='CUSTOMER_BEHAVIOR', method='m', sample_size=20)], judgments={'D03': J('D03', 1, ['e1'])})
    assert e['exit'] == 'PIVOT'


def test_d09_agent_output_prohibited_tactic_forces_repeat():
    e = disc(discovery={'_safety_flags': [{'rule_id': 'fake_proof_dependency'}]})
    assert row(e, 'X03')['status'] == 'FAIL' and 'prohibited tactic' in row(e, 'D09')['reasoning']


# ---------------------------------------------------------------- judge contract (adversarial)
def _alias():
    rows = [ev(1, excerpt='45% of students reported missing deadlines'), ev(2)]
    return rows, {'E1': 'e1', 'E2': 'e2'}


def test_judge_rejects_fabricated_evidence_id():
    rows, alias = _alias()
    v = criteria.validate_judgment('D03', {'criterion_id': 'D03', 'proposed_score': 4, 'evidence_ids': ['E9'], 'reasoning': 'x'}, alias, rows, BRIEF)
    assert not v['valid'] and 'not in the accepted ledger' in v['rejected_reason']


def test_judge_rejects_new_urls_and_unsourced_numbers():
    rows, alias = _alias()
    v = criteria.validate_judgment('D03', {'criterion_id': 'D03', 'proposed_score': 3, 'evidence_ids': ['E1'], 'reasoning': 'See https://fake.org'}, alias, rows, BRIEF)
    assert not v['valid'] and 'URL' in v['rejected_reason']
    v = criteria.validate_judgment('D03', {'criterion_id': 'D03', 'proposed_score': 3, 'evidence_ids': ['E1'], 'reasoning': '78% of students struggle'}, alias, rows, BRIEF)
    assert not v['valid'] and 'numbers' in v['rejected_reason']
    v = criteria.validate_judgment('D03', {'criterion_id': 'D03', 'proposed_score': 3, 'evidence_ids': ['E1'], 'reasoning': '45% reported missing deadlines'}, alias, rows, BRIEF)
    assert v['valid'] and v['score'] == 3


def test_judge_cannot_answer_another_criterion_or_score_out_of_scale():
    rows, alias = _alias()
    assert not criteria.validate_judgment('D03', {'criterion_id': 'D04', 'proposed_score': 3, 'evidence_ids': ['E1']}, alias, rows, BRIEF)['valid']
    assert not criteria.validate_judgment('D03', {'criterion_id': 'D03', 'proposed_score': 9, 'evidence_ids': ['E1']}, alias, rows, BRIEF)['valid']
    assert not criteria.validate_judgment('D03', {'criterion_id': 'D03', 'proposed_score': 4, 'evidence_ids': []}, alias, rows, BRIEF)['valid']


def test_score_caps_secondary_and_demand_needs_behaviour():
    rows, alias = _alias()
    v = criteria.validate_judgment('D04', {'criterion_id': 'D04', 'proposed_score': 5, 'evidence_ids': ['E1'], 'reasoning': 'strong'}, alias, rows, BRIEF)
    assert v['valid'] and v['score'] == 3 and 'capped' in v['capped']


def test_score_inconsistent_with_contradicting_evidence_is_discarded():
    rows = [ev(1, direction='CONTRADICTS')]
    v = criteria.validate_judgment('D03', {'criterion_id': 'D03', 'proposed_score': 5, 'evidence_ids': ['E1']}, {'E1': 'e1'}, rows, BRIEF)
    assert not v['valid']


def test_no_judge_calls_without_evidence_and_one_call_per_criterion_cached(client, monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(main, 'LLM', fake)
    pid, h = make_project(client, idea='A study planner for Cairo engineering students who miss deadlines', target_market='Cairo, Egypt',
                          current_workaround='WhatsApp groups')
    refine(client, pid, h)
    run(client, pid, h, 'discover')
    assert not [c for c in fake.calls if c[0] == 'JudgeOutput']
    async def matched(url, excerpt):
        return 'URL_ACCESSIBLE', 'EXCERPT_MATCHED', '2026-11-16T00:00:00+00:00', 'test'
    monkeypatch.setattr(main, 'verify_excerpt', matched)
    for dim in ('desirability', 'demand'):
        assert client.post(f'/api/projects/{pid}/evidence', headers=h, json={'kind': 'SECONDARY_BACKGROUND', 'dimension': dim, 'claim': 'TEST_ONLY students miss deadlines',
                           'url': f'https://testonly-publisher.org/{dim}', 'excerpt': 'students report missing deadlines', 'direction': 'SUPPORTS',
                           'relevance': 'CLAIM_RELEVANT', 'geography': 'Egypt', 'published_on': '2024', 'publisher': 'TEST_ONLY'}).status_code == 200
    r = client.post(f'/api/projects/{pid}/criteria/evaluate', headers=h).json()
    judged = [c[1]['criterion']['id'] for c in fake.calls if c[0] == 'JudgeOutput']
    assert sorted(judged) == ['D03', 'D04'] and r['judge_calls'] == 2
    assert all(len(c[1]['accepted_evidence']) == 1 for c in fake.calls if c[0] == 'JudgeOutput')   # one criterion, its own evidence
    r2 = client.post(f'/api/projects/{pid}/criteria/evaluate', headers=h).json()
    assert r2['judge_calls'] == 0                                                                   # cached
    rows = {x['id']: x for x in r2['evaluation']['criteria']}
    assert rows['D03']['status'] == 'SCORED' and rows['D03']['score'] == 3 and rows['D05']['status'] == 'UNKNOWN'


def test_adversarial_judge_cannot_change_gate_or_cite_fakes(client, monkeypatch):
    fake = FakeModel(judge=lambda ctx: {'criterion_id': ctx['criterion']['id'], 'proposed_score': 5, 'evidence_ids': ['E1', 'E77'],
                                        'reasoning': 'GO. Market of 2 million at https://made-up.example', 'caveats': []})
    monkeypatch.setattr(main, 'LLM', fake)
    pid, h = make_project(client, idea='A study planner for Cairo engineering students who miss deadlines', target_market='Cairo, Egypt',
                          current_workaround='WhatsApp groups')
    refine(client, pid, h)
    run(client, pid, h, 'discover')
    async def matched(url, excerpt):
        return 'URL_ACCESSIBLE', 'EXCERPT_MATCHED', '2026-11-16T00:00:00+00:00', 'test'
    monkeypatch.setattr(main, 'verify_excerpt', matched)
    client.post(f'/api/projects/{pid}/evidence', headers=h, json={'kind': 'SECONDARY_BACKGROUND', 'dimension': 'desirability', 'claim': 'TEST_ONLY students miss deadlines',
                'url': 'https://testonly-publisher.org/a', 'excerpt': 'students report missing deadlines', 'direction': 'SUPPORTS', 'relevance': 'CLAIM_RELEVANT',
                'geography': 'Egypt', 'published_on': '2024', 'publisher': 'TEST_ONLY'})
    e = client.post(f'/api/projects/{pid}/criteria/evaluate', headers=h).json()['evaluation']
    d03 = next(r for r in e['criteria'] if r['id'] == 'D03')
    assert d03['status'] == 'UNKNOWN' and 'rejected' in d03['reasoning'] and e['exit'] == 'REPEAT'
    audit = client.get(f'/api/projects/{pid}', headers=h).json()['audit']
    assert any(a['event'] == 'CRITERION_JUDGMENT_REJECTED' for a in audit)


# ---------------------------------------------------------------- versioning, staleness, decision binding
def test_config_change_versioned_non_editable_rejected_and_approvals_invalidated(client):
    pid, h = make_project(client)
    d = approved_discovery(client, pid, h)
    bad = client.post(f'/api/projects/{pid}/criteria/config', headers=h, json={'changes': {'weights': {'D01': 1}}})
    assert bad.status_code == 422
    assert client.post(f'/api/projects/{pid}/criteria/config', headers=h, json={'changes': {'safety': {'off': True}}}).status_code == 422
    ok = client.post(f'/api/projects/{pid}/criteria/config', headers=h, json={'changes': {'weights': {'D04': 5}, 'discover_gate': {'max_unknown_scored': 3}}})
    assert ok.status_code == 200 and ok.json()['version'] == 1
    s = client.get(f'/api/projects/{pid}', headers=h).json()
    assert next(r for r in s['phase_runs'] if r['phase'] == 'discover')['state'] == 'INVALIDATED'
    assert any(a['event'] == 'CRITERIA_CONFIG_CHANGED' for a in s['audit'])


def test_stale_evaluation_blocks_decision_until_reevaluated(client, monkeypatch):
    pid, h = make_project(client)
    refine(client, pid, h)
    d = run(client, pid, h, 'discover')
    client.post(f'/api/projects/{pid}/evidence', headers=h, json={'kind': 'CUSTOMER_STATEMENT', 'dimension': 'desirability', 'claim': 'TEST_ONLY interviewee said X',
                'method': 'TEST_ONLY interview', 'sample_size': 1, 'collected_from': TODAY, 'consent_confirmed': True})
    r = decide(client, pid, h, 'discover', d, 'APPROVE', acknowledge_risk=True, feedback='x')
    assert r.status_code == 409 and 'Re-evaluate' in r.json()['detail']
    client.post(f'/api/projects/{pid}/criteria/evaluate', headers=h)
    ok = decide(client, pid, h, 'discover', d, 'APPROVE', acknowledge_risk=True, feedback='TEST_ONLY')
    assert ok.status_code == 200
    dec = client.get(f'/api/projects/{pid}', headers=h).json()['decisions'][0]
    assert dec['criteria_version'] == criteria.VERSION and len(dec['criteria_policy_hash']) == 64 and len(dec['evaluation_hash']) == 64
    assert len(dec['config_hash']) == 64 and len(dec['safety_policy_hash']) == 64


def test_wrong_evaluation_hash_rejected(client):
    pid, h = make_project(client)
    refine(client, pid, h)
    d = run(client, pid, h, 'discover')
    r = decide(client, pid, h, 'discover', d, 'APPROVE', acknowledge_risk=True, feedback='x', evaluation_hash='a' * 64)
    assert r.status_code == 409


# ---------------------------------------------------------------- Validate criteria V01–V07
def test_validate_criteria_rows_present_and_honest(client):
    pid, h = make_project(client, budget='500 EGP', timeline='6 weeks')
    approved_discovery(client, pid, h)
    g = run(client, pid, h, 'validate')['gate']
    rows = {r['id']: r for r in g['criteria']['criteria']}
    assert set(rows) >= {'V01', 'V02', 'V03', 'V04', 'V05', 'V06', 'V07', 'X01', 'X02', 'X03', 'X04', 'X05'}
    assert rows['V01']['status'] == 'UNKNOWN' and rows['V02']['status'] == 'UNKNOWN'
    assert rows['V04']['status'] == 'RANKED' and 'should attack' in rows['V04']['reasoning']
    assert rows['V05']['status'] == 'NOT_DESIGNED' and rows['V06']['status'] == 'NOT_SET' and rows['V07']['status'] == 'NO_RESULT'
    assert rows['X04']['status'] == 'PASS' and 'hard-deny' in rows['X04']['reasoning']
    assert g['verdict'] == 'NEEDS_EVIDENCE'


def test_v05_blocks_lock_for_opinion_metric_and_v06_needs_origin(client):
    pid, h = make_project(client, budget='500 EGP')
    approved_discovery(client, pid, h)
    base = {'hypothesis': 'Students will join a consented waitlist', 'target_segment': 'Cairo students', 'success_threshold_pct': 30,
            'adverse_threshold_pct': 10, 'min_sample': 10, 'consent_method': 'Opt-in explained in person', 'founder_actions': 'Ask classmates face to face',
            'cost_estimate': '0', 'time_window_days': 7}
    d = client.post(f'/api/projects/{pid}/experiments', headers=h, json={**base, 'metric': 'Share who say they would you like the idea', 'threshold_origin': 'TEAM_ASSUMPTION'}).json()
    assert d['design_check']['items']['behavioral_metric']['ok'] is False
    lock = client.post(f'/api/projects/{pid}/experiments/{d["experiment_id"]}/lock', headers=h, json={'version': 1, 'criteria_hash': d['criteria_hash'],
                       'confirm': 'I_PREREGISTER_THESE_CRITERIA_BEFORE_COLLECTING_RESULTS'})
    assert lock.status_code == 422 and 'V05' in lock.json()['detail']['message']
    d2 = client.post(f'/api/projects/{pid}/experiments', headers=h, json={**base, 'metric': 'Share who voluntarily join the waitlist'}).json()
    lock2 = client.post(f'/api/projects/{pid}/experiments/{d2["experiment_id"]}/lock', headers=h, json={'version': 1, 'criteria_hash': d2['criteria_hash'],
                        'confirm': 'I_PREREGISTER_THESE_CRITERIA_BEFORE_COLLECTING_RESULTS'})
    assert lock2.status_code == 422 and 'V06' in lock2.json()['detail']['message']
    d3 = client.post(f'/api/projects/{pid}/experiments', headers=h, json={**base, 'metric': 'Share who voluntarily join the waitlist', 'cost_estimate': '5000 EGP',
                     'threshold_origin': 'TEAM_ASSUMPTION'}).json()
    assert d3['design_check']['items']['low_cost_within_budget']['ok'] is False


def test_v07_readings_hit_near_miss_clear_miss_too_little(client):
    pid, h = make_project(client)
    approved_discovery(client, pid, h)
    x = locked_experiment(client, pid, h, min_sample=10, success=30, adverse=10)
    res = client.post(f'/api/projects/{pid}/experiments/{x["experiment_id"]}/result', headers=h, json={'version': 1, 'criteria_hash': x['criteria_hash'],
                      'sample_size': 20, 'positives': 5, 'method': 'TEST_ONLY waitlist form', 'collected_from': TODAY, 'collected_to': TODAY,
                      'consent_confirmed': True}).json()
    assert res['reading'] == 'NEAR_MISS' and res['outcome'] == 'NEAR_MISS'      # 25% within 20% band below 30%
    g = run(client, pid, h, 'validate')['gate']
    assert g['verdict'] == 'NEEDS_EVIDENCE' and 'Near miss' in g['headline']
    assert next(r for r in g['criteria']['criteria'] if r['id'] == 'V07')['status'] == 'NEAR_MISS'
    from app.decision import evaluate_result
    c = {'min_sample': 10, 'success_threshold_pct': 30, 'adverse_threshold_pct': 10, 'near_miss_band': 0.2}
    assert [criteria.READING[evaluate_result(c, n, p)['outcome']] for n, p in [(10, 3), (20, 5), (20, 3), (5, 5)]] == ['HIT', 'NEAR_MISS', 'CLEAR_MISS', 'TOO_LITTLE_DATA']

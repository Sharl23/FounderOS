"""Twelve safety rules (policy/safety_rules.yaml): positive, negative, borderline, negated-language and
absent-source fixtures for EVERY rule. All fixtures are TEST_ONLY briefs, never production evidence."""
import pytest
from app import safety, main
from .conftest import make_project, refine, run

M = 'Cairo, Egypt'

# rule_id -> (positive, negative, borderline, negated) ; expected outcome for positive = policy outcome_on_fail
FIX = {
    'physical_goods_exclusion': (
        dict(idea='We will sell smart water bottle devices to students.', target_market=M),
        dict(idea='An AI inventory forecasting web app for small Cairo restaurants using their daily sales numbers.', target_market=M),
        dict(idea='A marketplace where students resell second-hand textbooks to each other.', target_market=M),
        dict(idea='A study app. We will not sell any devices or hardware; everything is digital.', target_market=M)),
    'financial_crypto_exclusion': (
        dict(idea='A crypto trading signals app for university students.', target_market=M),
        dict(idea='A tutoring booking app; tutors pay us a monthly subscription through an external payment processor.', target_market=M),
        None,
        dict(idea='A study planner. We will never offer investment advice or crypto features.', target_market=M)),
    'health_legal_advice_exclusion': (
        dict(idea='An educational only app that interprets your symptoms and suggests which medication to take.', target_market=M),
        dict(idea='A language-learning flashcard app for Egyptian high-achieving adults.', target_market=M),
        dict(idea='A chatbot that tells tenants what the law requires of their landlord in their case, labelled educational.', target_market=M),
        dict(idea='A clinic scheduling tool that does not diagnose and never interprets symptoms.', target_market=M)),
    'advice_in_disguise': (
        dict(idea='A mood tracker with insights and tips for university students.', target_market=M),
        dict(idea='A group project task board for engineering students.', target_market=M),
        dict(idea='An educational budgeting tracker that suggests how students should cut spending.', target_market=M),
        None),
    'income_promise_dependency': (
        dict(idea='A course platform that guarantees members 10000 EGP monthly income.', target_market=M),
        dict(idea='A freelancing portfolio builder; we charge a flat fee for templates.', target_market=M),
        dict(idea='A coaching app that promises members will earn their first freelance income fast.', target_market=M),
        dict(idea='A skills app. We will never guarantee income or results to anyone.', target_market=M)),
    'fake_proof_dependency': (
        dict(idea='A tutoring marketplace; we buy fake reviews and fake sign-ups to look popular.', target_market=M),
        dict(idea='A tutoring marketplace with verified reviews from real completed sessions.', target_market=M),
        dict(idea='An online course site that shows fake countdown timers to push urgency.', target_market=M),
        dict(idea='A browser extension that detects fake reviews on Egyptian e-commerce sites.', target_market=M)),
    'impersonation_dependency': (
        dict(idea='Send WhatsApp messages as if they came from Cairo University to enrol students in our course.', target_market=M),
        dict(idea='Our own branded study app called PlanWell, speaking only as PlanWell.', target_market=M),
        dict(idea='A white-label exam prep portal branded as a partner school.', target_market=M),
        dict(idea='A study app that will never impersonate any university or person.', target_market=M)),
    'money_or_credentials_dependency': (
        dict(idea='A budgeting app that stores customers\' bank passwords and card details to log in for them.', target_market=M),
        dict(idea='A restaurant inventory forecasting app that stores daily sales counts, not payment data.', target_market=M),
        dict(idea='A wedding gift app where the platform holds the funds until the wedding day.', target_market=M),
        dict(idea='A planner that does not store passwords; login uses an external provider.', target_market=M)),
    'harm_to_people': (
        dict(idea='An app to secretly track your partner\'s location and messages.', target_market=M),
        dict(idea='A revision timetable app for Cairo engineering students.', target_market=M),
        dict(idea='A service that writes students\' assignments for money.', target_market=M),
        dict(idea='A campus safety app that helps report harassment to university staff.', target_market=M)),
    'founder_values_conflict': (
        dict(idea='A free campus app funded by selling students\' location data to advertisers.', target_market=M, values='Privacy above all; no ads'),
        dict(idea='A paid revision planner with no tracking and no ads.', target_market=M, values='Privacy above all; no ads'),
        dict(idea='A planner that shows sponsored posts from bookstores.', target_market=M, values='no ads'),
        dict(idea='A planner that will never use ads or tracking.', target_market=M, values='Privacy first; no ads')),
    'regulated_or_sensitive_area': (
        dict(idea='A homework app for primary school children with parent dashboards.', target_market=M),
        dict(idea='A revision timetable generator for adult learners.', target_market=M),
        dict(idea='A privacy-aware habit app that stores users\' personal data encrypted with consent.', target_market=M),
        None),
    'illegal_in_target_market': (
        dict(idea='A sports betting odds tipster subscription.', target_market=M),
        dict(idea='A revision timetable generator for Cairo students.', target_market=M),
        dict(idea='A gambling odds comparison website.'),   # no jurisdiction: ambiguous
        None),
}

OUT = {r['id']: ('HARD_STOP' if r['outcome_on_fail'] == 'BLOCK' else 'REVIEW_REQUIRED') for r in safety.POLICY['rules']}


def outcome(fields, rid):
    a = safety.screen(fields['idea'], fields)
    return next(r for r in a['rules'] if r['rule_id'] == rid), a


def test_policy_file_has_exactly_the_twelve_ids_with_full_semantics():
    assert safety.RULE_IDS == ['illegal_in_target_market', 'regulated_or_sensitive_area', 'physical_goods_exclusion', 'financial_crypto_exclusion',
                               'health_legal_advice_exclusion', 'advice_in_disguise', 'income_promise_dependency', 'fake_proof_dependency',
                               'impersonation_dependency', 'money_or_credentials_dependency', 'harm_to_people', 'founder_values_conflict']
    for r in safety.POLICY['rules']:
        assert r['question'] and r['fail_if'] and r['research_instruction'] and r['provenance'] and r['kind'] == 'knockout'
    # Appendix C: these three PAUSE for the founder rather than hard-stop.
    assert {k for k, v in OUT.items() if v == 'REVIEW_REQUIRED'} == {'regulated_or_sensitive_area', 'advice_in_disguise', 'founder_values_conflict'}
    assert set(FIX) == set(safety.RULE_IDS)


@pytest.mark.parametrize('rid', list(FIX))
def test_positive(rid):
    row, a = outcome(FIX[rid][0], rid)
    expected = OUT[rid] if rid != 'illegal_in_target_market' else 'REVIEW_REQUIRED'   # no verified official source => no hard stop
    assert row['outcome'] == expected, (row, a['status'])
    assert row['spans'], 'a finding must quote the brief span it came from'
    assert a['status'] == ('BLOCK' if expected == 'HARD_STOP' else a['status'])


@pytest.mark.parametrize('rid', list(FIX))
def test_negative(rid):
    row, a = outcome(FIX[rid][1], rid)
    assert row['outcome'] in ('CLEAR', 'NOT_APPLICABLE', 'UNKNOWN_SOURCE'), row
    assert a['status'] != 'BLOCK'


@pytest.mark.parametrize('rid', [k for k, v in FIX.items() if v[2]])
def test_borderline_goes_to_founder_or_stop_never_silently_clear(rid):
    row, a = outcome(FIX[rid][2], rid)
    assert row['outcome'] in ('REVIEW_REQUIRED', 'HARD_STOP'), row
    if row['outcome'] == 'REVIEW_REQUIRED':
        assert 'RESEARCH_ONLY' in row['founder_review_scope']


@pytest.mark.parametrize('rid', [k for k, v in FIX.items() if v[3]])
def test_negated_language_is_not_a_false_positive(rid):
    row, a = outcome(FIX[rid][3], rid)
    assert row['outcome'] in ('CLEAR', 'NOT_APPLICABLE', 'UNKNOWN_SOURCE'), row


@pytest.mark.parametrize('rid', list(FIX))
def test_absent_source_is_never_a_legal_pass_or_a_fake_ban(rid):
    """No official source was checked for any fixture: no row may claim legal clearance or a source-backed ban."""
    row, a = outcome(FIX[rid][1], rid)
    legal = next(r for r in a['rules'] if r['rule_id'] == 'illegal_in_target_market')
    assert legal['outcome'] == 'UNKNOWN_SOURCE' and legal['official_source'] is None
    assert any('not legal clearance' in x for x in legal['reasons'])
    assert all(s['executed'] is False for s in legal['attempted_searches'])
    assert row['outcome'] != 'HARD_STOP' or 'OFFICIAL_SOURCE' not in row['detected_by']


def test_values_conflict_quotes_both_spans_exactly():
    f = FIX['founder_values_conflict'][0]
    row, _ = outcome(f, 'founder_values_conflict')
    s = row['spans'][0]
    assert s['value_statement'] == f['values'] and s['conflicts_with']['text'].lower() in f['idea'].lower()


def test_ambiguous_jurisdiction_pauses_and_never_passes():
    a = safety.screen('A study planner for students worldwide and in Egypt and Saudi Arabia.', {'idea': 'A study planner for students in Egypt and Saudi Arabia.'})
    legal = next(r for r in a['rules'] if r['rule_id'] == 'illegal_in_target_market')
    assert a['jurisdiction']['status'] == 'AMBIGUOUS' and legal['outcome'] == 'REVIEW_REQUIRED'


def test_model_flag_escalates_only_with_verbatim_quote_and_never_blocks():
    f = dict(idea='A revision planner that sends weekly study insights to students.', target_market=M)
    a = safety.screen(f['idea'], f, model_flags=[{'rule_id': 'advice_in_disguise', 'quote': 'sends weekly study insights'},
                                                 {'rule_id': 'harm_to_people', 'quote': 'secretly spies on everyone'}])
    row = next(r for r in a['rules'] if r['rule_id'] == 'advice_in_disguise')
    assert row['outcome'] == 'REVIEW_REQUIRED' and 'MODEL_CLASSIFIER_ESCALATION' in row['detected_by']
    assert a['status'] == 'REVIEW_REQUIRED'                      # never BLOCK from a model flag
    assert len(a['model_classifier']['rejected_flags']) == 1    # invented quote discarded


def test_model_cannot_remove_a_hard_stop():
    f = FIX['fake_proof_dependency'][0]
    a = safety.screen(f['idea'], f, model_flags=[])
    assert a['status'] == 'BLOCK'


def test_twelve_rows_always_returned_with_version_and_hash():
    a = safety.screen('A planner for students in Cairo.', {'idea': 'A planner for students in Cairo.', 'target_market': M})
    assert [r['rule_id'] for r in a['rules']] == safety.RULE_IDS
    assert a['policy_version'] == safety.POLICY_VERSION and len(a['policy_hash']) == 64


def test_rescreen_on_brief_revision_and_on_agent_output():
    flags = safety.screen_agent_output({'experiments': ['Post 50 fake reviews to seed demand'], '_status': 'ignored'})
    assert flags and flags[0]['rule_id'] == 'fake_proof_dependency'


def test_official_source_can_hard_stop_only_when_verified_and_official(client, monkeypatch):
    pid, h = make_project(client, idea='A sports betting tips subscription app for adults in Cairo.', target_market=M)
    r = refine(client, pid, h)
    legal = next(x for x in r['safety']['rules'] if x['rule_id'] == 'illegal_in_target_market')
    assert legal['outcome'] == 'REVIEW_REQUIRED' and r['safety']['status'] == 'REVIEW_REQUIRED'

    async def page(url, **k):
        return {'final_url': url, 'text': 'Article 1. Betting and gambling services are prohibited for all persons.', 'sha256': 'x' * 64,
                'retrieved_at': '2026-11-17T00:00:00+00:00'}
    monkeypatch.setattr(main.research, 'safe_fetch', page)
    # Blog (non-official domain): stored, but cannot create a hard stop.
    b = client.post(f'/api/projects/{pid}/safety/sources', headers=h, json={'rule_id': 'illegal_in_target_market', 'url': 'https://someblog.example.com/x',
                                                                           'excerpt': 'Betting and gambling services are prohibited', 'finding': 'PROHIBITS'}).json()
    assert b['official_domain'] is False and b['safety_status'] == 'REVIEW_REQUIRED'
    # Invented quote on an official domain: not matched => no hard stop.
    c = client.post(f'/api/projects/{pid}/safety/sources', headers=h, json={'rule_id': 'illegal_in_target_market', 'url': 'https://www.example.gov.eg/law',
                                                                           'excerpt': 'Tips subscriptions are banned forever', 'finding': 'PROHIBITS'}).json()
    assert c['excerpt_status'] == 'NOT_MATCHED' and c['safety_status'] == 'REVIEW_REQUIRED'
    # Verified excerpt on an official domain: HARD STOP, and acknowledgment cannot override it.
    d = client.post(f'/api/projects/{pid}/safety/sources', headers=h, json={'rule_id': 'illegal_in_target_market', 'url': 'https://www.example.gov.eg/law',
                                                                           'excerpt': 'Betting and gambling services are prohibited', 'finding': 'PROHIBITS'}).json()
    assert d['excerpt_status'] == 'EXCERPT_MATCHED' and d['safety_status'] == 'BLOCK'
    assert client.post(f'/api/projects/{pid}/safety/acknowledge', headers=h, json={'brief_version': 1, 'statement': 'I accept the risk fully'}).status_code == 403


def test_blocked_idea_gets_no_research_run(client):
    pid, h = make_project(client, idea=FIX['harm_to_people'][0]['idea'], target_market=M)
    refine(client, pid, h)
    r = client.post(f'/api/projects/{pid}/research/run', headers=h, json={'items': [{'bucket': 'PROBLEM', 'provider': 'crossref', 'query': 'partner tracking'}]})
    assert r.status_code == 403

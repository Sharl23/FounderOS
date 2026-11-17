"""Contract acceptance tests G(1)-G(7): evidence ladder, no double counting, pre-registration, PIVOT/STOP."""
import datetime
from app import main
from app.decision import evaluate_result, evaluate_validation
from .conftest import make_project, run, decide, approved_discovery, locked_experiment, TODAY

SRC = {'kind': 'SECONDARY_BACKGROUND', 'dimension': 'desirability', 'direction': 'SUPPORTS', 'relevance': 'CLAIM_RELEVANT'}


def add(client, pid, h, **kw):
    r = client.post(f'/api/projects/{pid}/evidence', headers=h, json={**SRC, **kw} if kw.get('kind', 'SECONDARY_BACKGROUND') == 'SECONDARY_BACKGROUND' else kw)
    assert r.status_code == 200, r.text
    return r.json()


def test_three_sector_growth_articles_do_not_validate(client, project, fetch_ok):
    """G1 + 'two excerpt matches do not prove demand'."""
    pid, h = project
    approved_discovery(client, pid, h)
    ids = []
    for i, dim in enumerate(('desirability', 'competition', 'viability')):
        ids.append(add(client, pid, h, dimension=dim, claim=f'Egypt edtech sector grew strongly in report {i}',
                       url=f'https://example.org/report{i}', excerpt=f'The sector grew by a large margin in year {i}')['id'])
    v = run(client, pid, h, 'validate')
    g = v['gate']
    assert g['verdict'] == 'NEEDS_EVIDENCE'
    assert g['matrix']['demand']['status'] == 'UNKNOWN' and g['matrix']['demand']['supporting_ids'] == []
    assert g['matrix']['desirability']['status'] == 'SUPPORTED' and 'secondary background only' in g['matrix']['desirability']['note']
    assert g['strongest_source']['kind'] == 'SECONDARY_BACKGROUND' and 'not that they are true' in g['strongest_source']['limitations']
    assert g['risk_register'][0]['assumption_status'] in ('UNTESTED', 'BACKGROUND_ONLY')
    assert 'validated' not in g['headline'].lower()


def test_twenty_enthusiastic_statements_are_not_demand(client, project):
    """G2."""
    pid, h = project
    approved_discovery(client, pid, h)
    for i in range(20):
        add(client, pid, h, kind='CUSTOMER_STATEMENT', dimension='demand', direction='SUPPORTS', claim_id='C-DEM',
            claim=f'Student {i} said they would definitely pay', method=f'Chat with classmate {i}', sample_size=1, positives=1,
            collected_from=TODAY, consent_confirmed=True)
    g = run(client, pid, h, 'validate')['gate']
    assert g['verdict'] == 'NEEDS_EVIDENCE'
    assert g['matrix']['demand']['status'] == 'UNKNOWN'
    assert any('stated interest is not demand' in c for c in g['caveats'])
    reg = next(r for r in g['risk_register'] if r['claim_id'] == 'C-DEM')
    assert reg['assumption_status'] == 'STATED_ONLY' and len(reg['evidence_ids']) == 20


def test_unverified_mismatched_and_duplicate_sources_do_not_count(client, project, monkeypatch):
    """G5 + 'bogus/unreachable/mismatched stay UNVERIFIED'."""
    pid, h = project
    approved_discovery(client, pid, h)
    results = iter([('UNVERIFIED', 'NOT_CHECKED', None, 'unreachable'),
                    ('URL_ACCESSIBLE', 'NOT_MATCHED', '2026-11-16T00:00:00+00:00', 'mismatch'),
                    ('URL_ACCESSIBLE', 'EXCERPT_MATCHED', '2026-11-16T00:00:00+00:00', 'ok'),
                    ('URL_ACCESSIBLE', 'EXCERPT_MATCHED', '2026-11-16T00:00:00+00:00', 'ok')])

    async def fake(url, excerpt):
        return next(results)
    monkeypatch.setattr(main, 'verify_excerpt', fake)
    a = add(client, pid, h, claim='Unreachable claim number one', url='https://example.org/a', excerpt='Some text from the page A')
    b = add(client, pid, h, claim='Mismatched claim number two', url='https://example.org/b', excerpt='Quote that is not there')
    c = add(client, pid, h, claim='Matched claim number three', url='https://example.org/c', excerpt='A real matching passage here')
    d = add(client, pid, h, claim='Matched claim number three again', url='https://example.org/c/', excerpt='A real  matching passage here')
    assert a['url_status'] == 'UNVERIFIED' and b['excerpt_status'] == 'NOT_MATCHED'
    assert d['duplicate_of'] == c['id']
    g = run(client, pid, h, 'validate')['gate']
    excluded = {x['id']: x['reason'] for x in g['excluded_evidence']}
    assert a['id'] in excluded and b['id'] in excluded and d['id'] in excluded and c['id'] not in excluded
    assert 'DUPLICATE' in excluded[d['id']]
    assert g['matrix']['desirability']['supporting_ids'] == [c['id']]
    assert g['verdict'] == 'NEEDS_EVIDENCE'


def test_negative_locked_experiment_gives_stop_with_refuting_ids(client, project):
    """G3 (STOP branch)."""
    pid, h = project
    approved_discovery(client, pid, h)
    x = locked_experiment(client, pid, h, critical=True, pivot=None, min_sample=10, success=30, adverse=10)
    sid = x['experiment_id']
    r = client.post(f'/api/projects/{pid}/experiments/{sid}/result', headers=h, json={
        'version': 1, 'criteria_hash': x['criteria_hash'], 'sample_size': 20, 'positives': 1, 'method': 'In-person ask of 20 classmates',
        'collected_from': TODAY, 'collected_to': TODAY, 'consent_confirmed': True, 'negative_signals': 'Most said they use the free calendar app'})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res['outcome'] == 'FAIL' and res['adverse'] is True and 'Founder-reported' in res['caveats'][0]
    g = run(client, pid, h, 'validate')['gate']
    assert g['verdict'] == 'STOP_DO_NOT_LAUNCH' and g['verdict_kind'] == 'BUSINESS_ADVISORY'
    assert g['matrix']['demand']['status'] == 'REFUTED' and g['matrix']['demand']['contradicting_ids'] == [res['evidence_id']]
    assert g['experiment_outcomes'][0]['criteria']['success_threshold_pct'] == 30
    assert any('n=20' in c for c in g['caveats'])
    # Founder may choose a different course, but only with acknowledgment + reasons, and still research-only.
    v = client.get(f'/api/projects/{pid}', headers=h).json()['passport']
    assert decide(client, pid, h, 'validate', {'run_id': v['run_id'], 'report_hash': v['report_hash'], 'brief_version': v['brief_version']}, 'APPROVE').status_code == 422
    ok = decide(client, pid, h, 'validate', {'run_id': v['run_id'], 'report_hash': v['report_hash'], 'brief_version': v['brief_version']},
                'APPROVE', acknowledge_risk=True, feedback='I will re-test with a different channel first')
    assert ok.status_code == 200 and ok.json()['scope'] == 'RESEARCH_ONLY'


def test_negative_locked_experiment_with_alternative_gives_pivot(client, project):
    pid, h = project
    approved_discovery(client, pid, h)
    x = locked_experiment(client, pid, h, pivot='Target private tutors instead of students')
    r = client.post(f'/api/projects/{pid}/experiments/{x["experiment_id"]}/result', headers=h, json={
        'version': 1, 'criteria_hash': x['criteria_hash'], 'sample_size': 12, 'positives': 1, 'method': 'Classroom ask',
        'collected_from': TODAY, 'collected_to': TODAY, 'consent_confirmed': True})
    assert r.status_code == 200
    g = run(client, pid, h, 'validate')['gate']
    assert g['verdict'] == 'PIVOT' and 'UNTESTED' in g['headline']


def test_planned_experiment_is_not_evidence_and_criteria_are_frozen(client, project):
    """G6 + 'targets frozen before outcome evaluation'."""
    pid, h = project
    approved_discovery(client, pid, h)
    draft = client.post(f'/api/projects/{pid}/experiments', headers=h, json={
        'hypothesis': 'Students will join a consented waitlist', 'target_segment': 'Cairo students',
        'metric': 'Share who leave an email', 'success_threshold_pct': 30, 'adverse_threshold_pct': 10, 'min_sample': 10,
        'consent_method': 'Opt-in explained in person', 'founder_actions': 'Ask classmates face to face'}).json()
    sid = draft['experiment_id']
    # a DRAFT cannot take results
    r = client.post(f'/api/projects/{pid}/experiments/{sid}/result', headers=h, json={
        'version': 1, 'criteria_hash': draft['criteria_hash'], 'sample_size': 10, 'positives': 9, 'method': 'ask people in class', 'collected_from': TODAY,
        'collected_to': TODAY, 'consent_confirmed': True})
    assert r.status_code == 409 and 'planned experiment is not evidence' in r.json()['detail']
    g = run(client, pid, h, 'validate')['gate']
    assert g['verdict'] == 'NEEDS_EVIDENCE' and g['matrix']['demand']['status'] == 'UNKNOWN'
    assert g['next_experiment']['kind'] == 'PROPOSED_EXPERIMENT_NEEDS_FOUNDER_APPROVAL'
    p = client.get(f'/api/projects/{pid}', headers=h).json()['passport']
    assert decide(client, pid, h, 'validate', p, 'REVISE', feedback='lock it first').status_code == 200
    lock = client.post(f'/api/projects/{pid}/experiments/{sid}/lock', headers=h, json={
        'version': 1, 'criteria_hash': draft['criteria_hash'], 'confirm': 'I_PREREGISTER_THESE_CRITERIA_BEFORE_COLLECTING_RESULTS'}).json()
    assert lock['status'] == 'LOCKED'
    # locked criteria cannot be rewritten in place: SQLite trigger
    import sqlite3, os, pytest
    db = sqlite3.connect(os.environ['FOUNDEROS_DB'])
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('UPDATE experiments SET payload_json="{}" WHERE series_id=?', (sid,))
    db.close()
    # result submission with the wrong hash is rejected
    assert client.post(f'/api/projects/{pid}/experiments/{sid}/result', headers=h, json={
        'version': 1, 'criteria_hash': '1' * 64, 'sample_size': 10, 'positives': 9, 'method': 'ask people', 'collected_from': TODAY,
        'collected_to': TODAY, 'consent_confirmed': True}).status_code == 409
    res = client.post(f'/api/projects/{pid}/experiments/{sid}/result', headers=h, json={
        'version': 1, 'criteria_hash': draft['criteria_hash'], 'sample_size': 10, 'positives': 2, 'method': 'ask people', 'collected_from': TODAY,
        'collected_to': TODAY, 'consent_confirmed': True}).json()
    assert res['outcome'] == 'FAIL'
    # Changing thresholds after the result = new version; old result stops counting; audit event exists.
    rev = client.post(f'/api/projects/{pid}/experiments/{sid}/revise', headers=h, json={
        'hypothesis': 'Students will join a consented waitlist', 'target_segment': 'Cairo students',
        'metric': 'Share who leave an email', 'success_threshold_pct': 15, 'adverse_threshold_pct': 5, 'min_sample': 10,
        'consent_method': 'Opt-in explained in person', 'founder_actions': 'Ask classmates face to face'})
    assert rev.status_code == 201 and rev.json()['version'] == 2
    state = client.get(f'/api/projects/{pid}', headers=h).json()
    assert any(e['event'] == 'EXPERIMENT_CRITERIA_CHANGED' and e['details']['had_result'] for e in state['audit'])
    g2 = run(client, pid, h, 'validate')['gate']
    assert g2['verdict'] == 'NEEDS_EVIDENCE'
    assert any('superseded' in x['reason'] for x in g2['excluded_evidence'])


def test_positive_small_sample_continues_testing_with_caveats(client, project):
    """G7."""
    pid, h = project
    approved_discovery(client, pid, h)
    x = locked_experiment(client, pid, h, min_sample=10)
    res = client.post(f'/api/projects/{pid}/experiments/{x["experiment_id"]}/result', headers=h, json={
        'version': 1, 'criteria_hash': x['criteria_hash'], 'sample_size': 11, 'positives': 5, 'method': 'Asked 11 friends from my own class',
        'collected_from': TODAY, 'collected_to': TODAY, 'consent_confirmed': True}).json()
    assert res['outcome'] == 'PASS' and 'NOT validated' in res['explanation']
    g = run(client, pid, h, 'validate')['gate']
    assert g['verdict'] == 'CONTINUE_TESTING'
    assert 'NOT validation' in g['headline'] and g['permissions']['launch'] is False
    assert any('n=11 is small' in c for c in g['caveats'])
    assert g['unresolved_critical_assumptions']  # viability, feasibility etc. still open


def test_inconclusive_below_min_sample():
    crit = {'min_sample': 10, 'success_threshold_pct': 30, 'adverse_threshold_pct': 10}
    assert evaluate_result(crit, 3, 3)['outcome'] == 'INCONCLUSIVE'
    assert evaluate_result(crit, 10, 3)['outcome'] == 'PASS'
    assert evaluate_result(crit, 10, 1)['adverse'] is True


def test_offline_no_sources_gives_honest_unknowns(client, project, no_fetch):
    """G4: nothing invented."""
    pid, h = project
    approved_discovery(client, pid, h)
    e = add(client, pid, h, claim='Some market statistic from a report', url='https://example.org/stat', excerpt='A passage I copied')
    assert e['url_status'] == 'UNVERIFIED'
    g = run(client, pid, h, 'validate')['gate']
    assert g['verdict'] == 'NEEDS_EVIDENCE'
    assert g['strongest_source']['id'] is None
    assert all(m['status'] == 'UNKNOWN' for m in g['matrix'].values())
    assert g['next_experiment']['founder_actions']
    assert 'http' not in str(g['risk_register'])  # no invented URLs anywhere in the register


def test_customer_evidence_requires_consent_and_sane_dates(client, project):
    pid, h = project
    base = {'kind': 'CUSTOMER_BEHAVIOR', 'dimension': 'demand', 'direction': 'SUPPORTS', 'claim': 'Students joined the waitlist',
            'method': 'Form shared in class', 'sample_size': 10, 'positives': 4, 'collected_from': TODAY}
    assert client.post(f'/api/projects/{pid}/evidence', headers=h, json={**base, 'consent_confirmed': False}).status_code == 422
    assert client.post(f'/api/projects/{pid}/evidence', headers=h, json={**base, 'consent_confirmed': True, 'positives': 11}).status_code == 422
    future = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
    assert client.post(f'/api/projects/{pid}/evidence', headers=h, json={**base, 'consent_confirmed': True, 'collected_from': future}).status_code == 422
    ok = client.post(f'/api/projects/{pid}/evidence', headers=h, json={**base, 'consent_confirmed': True}).json()
    assert ok['independence'] == 'FOUNDER_REPORTED_NOT_INDEPENDENTLY_VERIFIED'


def test_skeptic_flags_overclaims_but_verdict_is_backend(client, monkeypatch, tmp_path):
    from .conftest import FakeModel
    from fastapi.testclient import TestClient
    monkeypatch.setenv('FOUNDEROS_DB', str(tmp_path / 'p.sqlite3'))
    monkeypatch.setattr(main, 'LLM', FakeModel(praise=True))
    with TestClient(main.app) as c:
        pid, h = make_project(c)
        approved_discovery(c, pid, h)
        v = run(c, pid, h, 'validate')
        assert v['gate']['verdict'] == 'NEEDS_EVIDENCE'  # model praise changes nothing
        issues = ' '.join(f['issue'] for f in v['report']['_skeptic_flags'])
        assert 'OVER-CLAIM' in issues and 'UNSOURCED NUMBER' in issues


def test_pure_function_safety_block_overrides_everything():
    g = evaluate_validation(brief={}, brief_version=1, safety={'status': 'BLOCK', 'policy_version': 'x'}, discovery=None,
                            discovery_version=None, evidence=[], experiments=[])
    assert g['verdict'] == 'BLOCK_DO_NOT_LAUNCH' and g['verdict_kind'] == 'SAFETY_BLOCK' and g['permissions']['continue_research'] is False

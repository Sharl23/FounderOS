"""v0.4 intents kept under the v7 contract: catalog counts, token required, no invented scores."""
from app import criteria
from .conftest import make_project, refine

CFG = criteria.default_config()


def test_catalog_matches_uploaded_criteria_document(client):
    data = client.get('/api/criteria').json()
    assert len(data['discover']) == 9 and len(data['validate']) == 7 and len(data['cross_cutting']) == 5
    arch = data['architecture_only']
    assert [len(arch[k]['criteria']) for k in ('build', 'commercial_setup', 'launch', 'operate_learn')] == [2, 5, 6, 4]
    for c in data['discover'] + data['validate'] + data['cross_cutting']:
        # The PDF's eight parts (p.9): name/gate, kind, question, scale (scored), evidence, weight/pass mark, origin, who may change it.
        assert c['name'] and c['kind'] in criteria.KINDS and c['question'] and c['evidence_required'] and c['origin'] and c['who_may_change']
        assert c.get('weight') is not None or c.get('pass_mark') or c.get('thresholds') or c.get('checklist') or c.get('readings')
        assert c['pdf_page'] in range(1, 12)
    assert data['version'] == criteria.VERSION and len(data['policy_hash']) == 64


def test_criteria_requires_project_token(client):
    pid, headers = make_project(client)
    assert client.get(f'/api/projects/{pid}/criteria').status_code == 401
    assert client.get(f'/api/projects/{pid}/criteria', headers={'X-Project-Token': 'wrong'}).status_code == 404
    d = client.get(f'/api/projects/{pid}/criteria', headers=headers).json()
    assert d['discover'] is None and d['criteria_version'] == criteria.VERSION


def test_research_plan_legacy_never_claims_evidence(client):
    pid, headers = make_project(client, target_market='Egypt', target_customers='Students in Cairo')
    refine(client, pid, headers)
    d = client.get(f'/api/projects/{pid}/research-plan', headers=headers).json()
    assert d['classification'] == 'SUGGESTED_QUERIES_NOT_RESEARCH' and len(d['queries']) == 3
    assert client.get(f'/api/projects/{pid}', headers=headers).json()['evidence'] == []


def _row(**kw):
    base = dict(id='x', kind='SECONDARY_BACKGROUND', dimension='desirability', url_status='URL_ACCESSIBLE', excerpt_status='EXCERPT_MATCHED',
                relevance='CLAIM_RELEVANT', direction='SUPPORTS', injection_flag=0, duplicate_of=None, geography='Egypt', published_on='2024',
                publisher='CAPMAS', title='t')
    base.update(kw)
    return base


def test_unverified_evidence_is_not_qualified():
    q = criteria.evidence_quality(_row(excerpt_status='NOT_CHECKED'), {'target_market': 'Egypt'}, CFG)
    assert q['counts'] is False and 'UNVERIFIED' in q['exclusion']


def test_matched_secondary_never_scores_without_judge():
    rows = [_row(id='y')]
    e = criteria.evaluate_discover(brief={'target_market': 'Egypt', 'target_customers': 'a', 'problem': 'b', 'current_workaround': 'c'},
                                   brief_version=1, safety={'status': 'ALLOW_DISCOVERY'}, safety_ack=False, discovery={}, discovery_run_id='r',
                                   evidence=rows, experiments=[], judgments={}, cfg=CFG)
    d03 = next(r for r in e['criteria'] if r['id'] == 'D03')
    assert d03['status'] == 'AWAITING_JUDGE' and d03['score'] is None and d03['unknown'] is True and d03['evidence_ids'] == ['y']

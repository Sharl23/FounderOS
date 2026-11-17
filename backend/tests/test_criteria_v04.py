"""Criteria coverage, access control, and no invented scores."""
from app import criteria
from .conftest import make_project, refine


def test_catalog_matches_uploaded_criteria_document(client):
    response=client.get('/api/criteria')
    assert response.status_code==200
    data=response.json()
    assert len(data['discover'])==9
    assert len(data['validate'])==7
    assert len(data['cross_cutting'])==5
    assert len(data['architecture_only']['build'])==2
    assert len(data['architecture_only']['commercial'])==5
    assert len(data['architecture_only']['launch'])==6
    assert len(data['architecture_only']['operate'])==4
    assert all('origin' in x and 'change_control' in x for x in data['discover'])


def test_criteria_requires_project_token(client):
    pid,headers=make_project(client)
    assert client.get(f'/api/projects/{pid}/criteria').status_code==401
    assert client.get(f'/api/projects/{pid}/criteria', headers={'X-Project-Token':'wrong'}).status_code==404
    result=client.get(f'/api/projects/{pid}/criteria', headers=headers)
    assert result.status_code==200
    d=result.json()
    assert d['qualified_evidence_count']==0
    assert all(x['score'] is None for x in d['criteria'] if x['kind']=='scored')
    assert d['raw_evidence_count']==0


def test_research_plan_never_claims_evidence(client):
    pid,headers=make_project(client, target_market='Egypt',target_customers='Students in Cairo')
    refine(client,pid,headers)
    result=client.get(f'/api/projects/{pid}/research-plan',headers=headers)
    assert result.status_code==200, result.text
    d=result.json()
    assert d['classification']=='SUGGESTED_QUERIES_NOT_RESEARCH'
    assert len(d['queries'])==3
    assert all(len(q['query'])<=70 for q in d['queries'])
    assert 'No results become evidence automatically' in d['notice']
    snapshot=client.get(f'/api/projects/{pid}',headers=headers).json()
    assert snapshot['evidence']==[]


def test_duplicate_or_unverified_evidence_is_not_qualified():
    evidence=[dict(id='x',kind='SECONDARY_BACKGROUND',dimension='desirability',
                   url_status='URL_ACCESSIBLE',excerpt_status='NOT_CHECKED',
                   relevance='CLAIM_RELEVANT', direction='SUPPORTS',injection_flag=0,duplicate_of=None)]
    outcome=criteria.summarize(evidence,'ALLOW_DISCOVERY')
    assert outcome['raw_evidence_count']==1
    assert outcome['qualified_evidence_count']==0
    assert next(x for x in outcome['criteria'] if x['id']=='D03')['status']=='UNKNOWN'


def test_matched_metadata_never_automatically_gets_score():
    evidence=[dict(id='y',kind='SECONDARY_BACKGROUND',dimension='desirability',
                   url_status='URL_ACCESSIBLE',excerpt_status='EXCERPT_MATCHED',
                   relevance='CLAIM_RELEVANT', direction='SUPPORTS',injection_flag=0,duplicate_of=None)]
    outcome=criteria.summarize(evidence,'ALLOW_DISCOVERY')
    row=next(x for x in outcome['criteria'] if x['id']=='D03')
    assert row['status']=='EVIDENCE_TO_REVIEW'
    assert row['score'] is None
    assert row['evidence_ids']==['y']

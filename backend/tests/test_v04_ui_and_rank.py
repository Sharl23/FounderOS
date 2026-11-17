"""Static UI contracts and research ranking: no live external network needed."""
from pathlib import Path
import re
from bs4 import BeautifulSoup
from .conftest import make_project
from app import main
import json

STATIC = Path(__file__).parents[1] / 'app' / 'static'


def test_ui_id_integrity_and_unique_navigation(client):
    page=client.get('/')
    assert page.status_code == 200
    soup=BeautifulSoup(page.text,'html.parser')
    ids=[x['id'] for x in soup.select('[id]')]
    assert len(ids)==len(set(ids)), 'Duplicate HTML IDs can break actions'
    js=(STATIC/'app.js').read_text()
    refs=set(re.findall(r"\$\('([^']+)'\)",js))
    assert refs-set(ids) == {'ack-form','clarify-form'}, refs-set(ids)
    assert len(soup.select('nav#workspace-nav'))==1
    assert not soup.select('#rail-discover,#rail-validate'), 'Duplicate sidebar should be removed'
    for key in ('research-form','research-suggestions','criteria-rows','criteria-version','evidence-src','evidence-cust','roadmap-card'):
        assert key in ids


def test_crossref_title_ranking_is_not_truth_verification(client, monkeypatch):
    data={'message':{'items':[
      {'DOI':'10.1234/preschool','title':['Pre-university student academic stress'], 'publisher':'Sample','published':{'date-parts':[[2025]]},'type':'journal-article'},
      {'DOI':'10.1234/undergrad','title':['University students academic stress time management'], 'publisher':'Sample','published':{'date-parts':[[2024]]},'type':'journal-article'},
    ]}}
    class Response:
        status_code=200
        headers={'content-type':'application/json'}
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def aiter_bytes(self): yield json.dumps(data).encode()
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        def stream(self,*args,**kwargs): return Response()
    monkeypatch.setattr(main.httpx,'AsyncClient',lambda **kwargs:Client())
    d=client.get('/api/research/crossref?q=university%20students%20academic%20stress%20time%20management').json()
    assert d['results'][0]['id']=='10.1234/undergrad'
    assert d['results'][1]['topic_match']=='WEAK'
    assert d['classification']=='UNVERIFIED_CANDIDATES_NOT_EVIDENCE'

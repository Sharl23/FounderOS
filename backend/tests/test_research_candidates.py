"""Candidate search must never enter the evidence ledger or assert demand."""
import json
import httpx
import pytest
from app import main


@pytest.mark.parametrize('q', ['x', 'ab', 'zz'])
def test_too_short_query(client, q):
    response=client.get('/api/research/crossref',params={'q':q})
    assert response.status_code == 422


def test_crossref_candidates_are_not_evidence(client, monkeypatch):
    class DummyResponse:
        status_code=200
        headers={'content-type':'application/json'}
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def aiter_bytes(self):
            yield json.dumps({'message':{'items':[{'DOI':'10.1234/example','title':['Study planning among students'], 'publisher':'Example Publisher', 'published':{'date-parts':[[2025,2]]}, 'type':'journal-article'}]}}).encode()
    class DummyClient:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        def stream(self,*args,**kwargs):
            assert args[1]=='https://api.crossref.org/works'
            assert kwargs['params']['rows']==12
            return DummyResponse()
    monkeypatch.setattr(main.httpx,'AsyncClient',lambda **kwargs:DummyClient())
    r=client.get('/api/research/crossref?q=student%20time%20management')
    assert r.status_code==200, r.text
    data=r.json()
    assert data['classification']=='UNVERIFIED_CANDIDATES_NOT_EVIDENCE'
    assert data['results'][0]['url']=='https://doi.org/10.1234/example'
    assert data['results'][0]['year']==2025
    # Search does not create projects, evidence or authorize actions.
    assert 'evidence' not in data


def test_crossref_unavailable_is_honest(client, monkeypatch):
    class Failing:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        def stream(self,*args,**kwargs): raise httpx.ConnectError('offline')
    monkeypatch.setattr(main.httpx,'AsyncClient',lambda **kwargs:Failing())
    r=client.get('/api/research/crossref?q=student%20research')
    assert r.status_code==503
    assert 'unavailable' in r.text.lower()

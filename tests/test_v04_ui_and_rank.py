"""Static UI contracts (the browser journey itself is scripts/ui_e2e.py) and legacy Crossref ranking."""
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from app import main

STATIC = Path(__file__).parents[1] / 'backend' / 'app' / 'static'


def test_single_sidebar_unique_ids_and_routes(client):
    soup = BeautifulSoup(client.get('/').text, 'html.parser')
    ids = [x['id'] for x in soup.select('[id]')]
    assert len(ids) == len(set(ids))
    assert len(soup.select('nav#workspace-nav')) == 1 and len(soup.select('aside')) == 1
    assert soup.select_one('a.skip')['href'] == '#main' and soup.select_one('main#main')
    for path in ('/projects', '/projects/0123456789abcdef0123456789abcdef/research', '/roadmap', '/help'):
        assert client.get(path).status_code == 200


def test_no_cdn_fonts_or_remote_assets():
    for f in ('index.html', 'style.css'):
        text = (STATIC / f).read_text()
        assert not re.search(r'https?://', text), f'{f} must not load remote assets (offline after setup)'
    assert (STATIC / 'fonts' / 'LICENSE-InstrumentSans-OFL.txt').exists() and (STATIC / 'fonts' / 'LICENSE-Newsreader-OFL.txt').exists()


def test_raw_json_only_inside_advanced_drawers():
    js = (STATIC / 'app.js').read_text()
    for line in js.splitlines():
        if 'JSON.stringify(' in line:
            assert ('<pre>' in line or 'body:' in line or 'body ===' in line or 'localStorage' in line or 'setItem' in line
                    or 'typeof v' in line), line.strip()[:120]


def test_every_button_hits_a_real_endpoint():
    js = (STATIC / 'app.js').read_text()
    endpoints = set(re.findall(r"api\(`?['\"]?(/[a-z/{}$._?=-]+)", js))
    assert endpoints, 'UI must call the backend'
    assert 'setTimeout(() => { live' in js   # only timer is the screen-reader announcement, not fake progress
    assert 'Math.random' not in js


def test_crossref_title_ranking_is_not_truth_verification(client, monkeypatch):
    data = {'message': {'items': [
        {'DOI': '10.1234/preschool', 'title': ['Pre-university student academic stress'], 'publisher': 'Sample', 'published': {'date-parts': [[2025]]}, 'type': 'journal-article'},
        {'DOI': '10.1234/undergrad', 'title': ['University students academic stress time management'], 'publisher': 'Sample', 'published': {'date-parts': [[2024]]}, 'type': 'journal-article'}]}}

    class Response:
        status_code = 200
        headers = {'content-type': 'application/json'}
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def aiter_bytes(self): yield json.dumps(data).encode()

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def stream(self, *args, **kwargs): return Response()
    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda **kwargs: Client())
    d = client.get('/api/research/crossref?q=university%20students%20academic%20stress%20time%20management').json()
    assert d['results'][0]['id'] == '10.1234/undergrad' and d['results'][1]['topic_match'] == 'WEAK'
    assert d['classification'] == 'UNVERIFIED_CANDIDATES_NOT_EVIDENCE'

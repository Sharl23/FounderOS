"""Research Studio back end: Gatherer (providers) -> Verifier (safe fetch + exact passage).

Honest coverage boundaries (shown in the UI):
  * Crossref  — scholarly publication METADATA (title, DOI, publisher, year, sometimes an abstract).
                Not market data, not competitor data, not proof of findings.
  * OpenAlex  — scholarly metadata incl. reconstructed abstracts. Optional key/mailto via env.
  * World Bank Indicators v2 — dated NATIONAL statistics (structured datum). Country-level only:
                never city- or segment-level.
  * Founder URL / DOI landing page — fetched by the SSRF-guarded verifier; passages offered from
                the actually fetched text.
  * General web / competitor search — NOT AVAILABLE: no compliant free search API is configured.
                FounderOS proposes targeted queries for the founder to run in their own browser.
No candidate becomes evidence without a founder review action.
"""
from __future__ import annotations
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, quote_plus

import httpx
from bs4 import BeautifulSoup

from . import safety

UA = 'FounderOS/0.7 (open-source local research assistant; contact: see repository)'
PROVIDERS = {
    'crossref': {'name': 'Crossref', 'covers': 'Scholarly publication metadata (title, DOI, publisher, year; abstract when deposited).',
                 'does_not_cover': 'Market size, competitors, prices, customer behaviour. Metadata is not a study finding.',
                 'access': 'Free public REST API, no key. Polite use; may throttle.'},
    'openalex': {'name': 'OpenAlex', 'covers': 'Scholarly works metadata and reconstructed abstracts.',
                 'does_not_cover': 'Commercial competitors, live prices, customer behaviour.',
                 'access': 'Free public API; optional key/mailto via OPENALEX_API_KEY / OPENALEX_MAILTO. Subject to its current terms and quotas.'},
    'worldbank': {'name': 'World Bank Indicators', 'covers': 'Dated national statistics (population, internet use, GDP per capita, tertiary enrolment, ...).',
                  'does_not_cover': 'City- or segment-level figures, willingness to pay, demand for this product.',
                  'access': 'Free public API v2, no key.'},
    'founder_url': {'name': 'Founder-supplied URL', 'covers': 'Any public HTTPS page you choose (competitor site, regulator page, report).',
                    'does_not_cover': 'Nothing is searched automatically; you pick the page.', 'access': 'SSRF-guarded fetch.'},
    'web_search': {'name': 'General web / competitor search', 'covers': 'NOT AVAILABLE',
                   'does_not_cover': 'No compliant free general-web search API is configured, so competitor and pricing discovery is manual.',
                   'access': 'DISCOVERY_NOT_AVAILABLE'},
}

_backoff: dict[str, float] = {}

ISO3 = {'Egypt': 'EGY', 'Saudi Arabia': 'SAU', 'United Arab Emirates': 'ARE', 'Jordan': 'JOR', 'Morocco': 'MAR', 'Tunisia': 'TUN',
        'Kenya': 'KEN', 'Nigeria': 'NGA', 'United States': 'USA', 'United Kingdom': 'GBR', 'Germany': 'DEU', 'France': 'FRA',
        'India': 'IND', 'Canada': 'CAN', 'Turkey': 'TUR', 'Pakistan': 'PAK', 'Lebanon': 'LBN', 'Qatar': 'QAT', 'Kuwait': 'KWT'}
ISO2 = {'EGY': 'EG', 'SAU': 'SA', 'ARE': 'AE', 'JOR': 'JO', 'MAR': 'MA', 'TUN': 'TN', 'KEN': 'KE', 'NGA': 'NG', 'USA': 'US', 'GBR': 'GB',
        'DEU': 'DE', 'FRA': 'FR', 'IND': 'IN', 'CAN': 'CA', 'TUR': 'TR', 'PAK': 'PK', 'LBN': 'LB', 'QAT': 'QA', 'KWT': 'KW'}
INDICATORS = {
    'SP.POP.TOTL': 'Population, total',
    'SP.URB.TOTL.IN.ZS': 'Urban population (% of total population)',
    'IT.NET.USER.ZS': 'Individuals using the Internet (% of population)',
    'SE.TER.ENRR': 'School enrollment, tertiary (% gross)',
    'NY.GDP.PCAP.CD': 'GDP per capita (current US$)',
    'IT.CEL.SETS.P2': 'Mobile cellular subscriptions (per 100 people)',
}


def now():
    return datetime.now(timezone.utc).isoformat()


class FetchError(Exception):
    def __init__(self, status, message, http=None):
        super().__init__(message)
        self.status, self.message, self.http = status, message, http


# ----------------------------------------------------------------------------- SSRF-guarded fetch
BLOCKED_NAMES = ('localhost', 'host.docker.internal', 'gateway.docker.internal', 'metadata.google.internal', 'metadata', 'kubernetes.default')
PRIVATE_SUFFIXES = ('.local', '.internal', '.localhost', '.home', '.lan', '.corp', '.intranet', '.docker')


def check_public_url(url: str):
    p = urlparse(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Only public HTTPS URLs on port 443 without credentials are allowed')
    host = p.hostname.lower().rstrip('.')
    if host in BLOCKED_NAMES or host.endswith(PRIVATE_SUFFIXES):
        raise ValueError('Private or internal hosts are blocked')
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
        except (socket.gaierror, ValueError, UnicodeError) as exc:
            raise ValueError('Host could not be resolved (offline or unknown host)') from exc
    if not addresses or any(not a.is_global or a.is_multicast for a in addresses):
        raise ValueError('Only public IP addresses are allowed (no private, loopback, link-local or metadata ranges)')
    return host


def _sanitize(html: str) -> tuple[str, dict]:
    soup = BeautifulSoup(html, 'html.parser')
    meta = {}

    def m(*names):
        for n in names:
            tag = soup.find('meta', attrs={'property': n}) or soup.find('meta', attrs={'name': n})
            if tag and tag.get('content'):
                return tag['content'].strip()[:300]
        return None
    meta['title'] = m('og:title', 'citation_title', 'dc.title') or (soup.title.string.strip()[:300] if soup.title and soup.title.string else None)
    meta['publisher'] = m('og:site_name', 'citation_publisher', 'dc.publisher', 'publisher', 'citation_journal_title')
    meta['published_on'] = m('article:published_time', 'citation_publication_date', 'citation_date', 'dc.date', 'date', 'pubdate')
    if not meta['published_on']:
        t = soup.find('time', attrs={'datetime': True})
        meta['published_on'] = t['datetime'][:40] if t else None
    meta['author'] = m('author', 'citation_author', 'dc.creator')
    meta['doi'] = m('citation_doi', 'dc.identifier')
    for tag in soup(['script', 'style', 'noscript', 'iframe', 'svg', 'form', 'template', 'object', 'embed']):
        tag.decompose()
    text = re.sub(r'[ \t\r\f\v]+', ' ', soup.get_text('\n', strip=True))
    text = re.sub(r'\n{2,}', '\n', text)
    return text, meta


async def safe_fetch(url: str, *, max_bytes=800_000, max_redirects=3, timeout=8.0, client_factory=None) -> dict:
    """GET a public HTTPS page. Every redirect hop is re-validated against the SSRF rules."""
    hops = []
    current = url
    factory = client_factory or (lambda: httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False))
    for _ in range(max_redirects + 1):
        try:
            check_public_url(current)
        except ValueError as exc:
            raise FetchError('FETCH_FAILED', f'Blocked: {exc}' + (f' (redirect from {hops[-1]})' if hops else '')) from exc
        try:
            async with factory() as client:
                async with client.stream('GET', current, headers={'User-Agent': UA, 'Accept': 'text/html,text/plain;q=0.9'}) as resp:
                    if 300 <= resp.status_code < 400:
                        loc = resp.headers.get('location')
                        if not loc:
                            raise FetchError('FETCH_FAILED', f'Redirect without location (HTTP {resp.status_code})', resp.status_code)
                        hops.append(current)
                        current = urljoin(current, loc)
                        continue
                    if resp.status_code != 200:
                        raise FetchError('FETCH_FAILED', f'HTTP {resp.status_code}' + (' (access denied or paywall)' if resp.status_code in (401, 402, 403) else ''), resp.status_code)
                    ctype = resp.headers.get('content-type', '').split(';')[0].strip().lower()
                    if ctype not in ('text/html', 'text/plain', 'application/xhtml+xml'):
                        raise FetchError('FETCH_FAILED', f'Content type {ctype or "unknown"} is not inspected (HTML/plain text only)')
                    chunks, n = [], 0
                    async for chunk in resp.aiter_bytes():
                        n += len(chunk)
                        if n > max_bytes:
                            raise FetchError('FETCH_FAILED', f'Page exceeds the {max_bytes // 1000} KB safe download limit')
                        chunks.append(chunk)
                    raw = b''.join(chunks).decode(resp.encoding or 'utf-8', 'replace')
        except httpx.TimeoutException as exc:
            raise FetchError('FETCH_FAILED', 'Timed out') from exc
        except httpx.HTTPError as exc:
            raise FetchError('FETCH_FAILED', f'Network error: {str(exc)[:120]} (offline?)') from exc
        text, meta = _sanitize(raw) if ctype != 'text/plain' else (raw, {})
        paywall = len(text) < 1500 or bool(re.search(r'\b(purchase (this )?article|subscribe to (read|continue)|access through your institution|sign in to read|buy this article)\b', text, re.I))
        return {'requested_url': url, 'final_url': current, 'redirects': hops, 'content_type': ctype, 'text': text[:300_000],
                'meta': meta, 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'retrieved_at': now(), 'chars': len(text),
                'paywall_suspected': paywall}
    raise FetchError('FETCH_FAILED', f'More than {max_redirects} redirects')


def norm(s):
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s%.,-]', ' ', (s or '').casefold())).strip()


def excerpt_in(text: str, excerpt: str) -> bool:
    return bool(excerpt) and len(excerpt.strip()) >= 12 and norm(excerpt) in norm(text)


STOP = {'the', 'and', 'for', 'with', 'among', 'about', 'from', 'that', 'this', 'are', 'was', 'were', 'have', 'has', 'their', 'they',
        'into', 'your', 'you', 'our', 'who', 'what', 'which', 'when', 'will', 'can', 'not', 'but', 'all', 'more', 'than', 'its'}


def terms_of(q):
    return {t for t in re.findall(r'[a-z؀-ۿ]{3,}', (q or '').lower())} - STOP


def passages(text: str, query: str, k: int = 8) -> list[dict]:
    """Candidate excerpts from the ACTUALLY fetched text. Ranking = term overlap (exploratory heuristic only)."""
    terms = terms_of(query)
    parts = re.split(r'(?<=[.!?])\s+|\n', text)
    out = []
    for i, p in enumerate(parts):
        p = p.strip()
        if not 60 <= len(p) <= 420:
            continue
        hit = sorted(terms & terms_of(p))
        inj = safety.looks_like_injection(p)
        out.append({'index': i, 'text': p, 'matched_terms': hit, 'overlap': len(hit), 'has_number': bool(re.search(r'\d', p)),
                    'injection_flag': inj})
    out.sort(key=lambda x: (-x['overlap'], -x['has_number'], x['index']))
    return [p for p in out if p['overlap'] > 0][:k] or out[:min(k, 4)]


# ----------------------------------------------------------------------------- providers
async def _get_json(url, params, provider, headers=None, timeout=8.0, max_bytes=400_000, client_factory=None):
    until = _backoff.get(provider, 0)
    if until > time.time():
        return {'status': 'RATE_LIMITED', 'error': f'{PROVIDERS[provider]["name"]} asked us to slow down; retry in {int(until - time.time())} s.'}
    factory = client_factory or (lambda: httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False))
    try:
        async with factory() as client:
            async with client.stream('GET', url, params=params, headers={'User-Agent': UA, 'Accept': 'application/json', **(headers or {})}) as r:
                if r.status_code == 429:
                    _backoff[provider] = time.time() + 60
                    return {'status': 'RATE_LIMITED', 'error': 'HTTP 429 from provider; backing off 60 s.'}
                if r.status_code in (401, 403):
                    return {'status': 'ACCESS_DENIED', 'error': f'HTTP {r.status_code}: provider requires a key or denied access.'}
                if r.status_code != 200:
                    return {'status': 'PROVIDER_ERROR', 'error': f'HTTP {r.status_code}'}
                if 'json' not in r.headers.get('content-type', ''):
                    return {'status': 'PROVIDER_ERROR', 'error': 'Unexpected content type'}
                buf, n = [], 0
                async for chunk in r.aiter_bytes():
                    n += len(chunk)
                    if n > max_bytes:
                        return {'status': 'PROVIDER_ERROR', 'error': 'Response exceeded safe size limit'}
                    buf.append(chunk)
        return {'status': 'OK', 'data': json.loads(b''.join(buf))}
    except httpx.TimeoutException:
        return {'status': 'OFFLINE', 'error': 'Timed out (offline or provider slow).'}
    except (httpx.HTTPError, OSError) as exc:
        return {'status': 'OFFLINE', 'error': f'Network unavailable: {str(exc)[:100]}'}
    except ValueError:
        return {'status': 'PROVIDER_ERROR', 'error': 'Invalid JSON'}


def _strip_jats(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s or '')).strip()


async def crossref(query: str, rows: int = 8, client_factory=None) -> dict:
    r = await _get_json('https://api.crossref.org/works', {'query': query, 'rows': rows,
                        'select': 'DOI,title,publisher,published,type,abstract,container-title'}, 'crossref', client_factory=client_factory)
    if r['status'] != 'OK':
        return {**r, 'results': []}
    out = []
    for item in (r['data'].get('message') or {}).get('items', [])[:rows]:
        doi = item.get('DOI', '')
        if not isinstance(doi, str) or not re.fullmatch(r'10\.\d{4,9}/[^\s<>]{1,180}', doi, re.I):
            continue
        title = item.get('title') or []
        parts = (item.get('published') or {}).get('date-parts') or [[None]]
        year = parts[0][0] if parts and parts[0] else None
        abstract = _strip_jats(item.get('abstract'))[:900]
        out.append({'provider': 'crossref', 'title': str(title[0])[:300] if title else 'Untitled', 'doi': doi, 'url': 'https://doi.org/' + doi,
                    'publisher': str(item.get('publisher') or '')[:150], 'venue': (item.get('container-title') or [''])[0][:150] if item.get('container-title') else None,
                    'year': year, 'type': str(item.get('type') or '')[:60], 'abstract': abstract or None,
                    'state': 'CANDIDATE_METADATA', 'evidence_status': 'METADATA_ONLY'})
    return {'status': 'OK' if out else 'NO_RESULTS', 'results': out}


def _openalex_abstract(inv):
    if not isinstance(inv, dict):
        return None
    pos = []
    for word, idxs in inv.items():
        for i in idxs:
            pos.append((i, word))
    return ' '.join(w for _, w in sorted(pos))[:900] if pos else None


async def openalex(query: str, rows: int = 8, client_factory=None) -> dict:
    params = {'search': query, 'per-page': rows, 'select': 'id,doi,display_name,publication_year,primary_location,abstract_inverted_index,type'}
    if os.getenv('OPENALEX_MAILTO'):
        params['mailto'] = os.getenv('OPENALEX_MAILTO')
    if os.getenv('OPENALEX_API_KEY'):
        params['api_key'] = os.getenv('OPENALEX_API_KEY')
    r = await _get_json('https://api.openalex.org/works', params, 'openalex', client_factory=client_factory)
    if r['status'] != 'OK':
        return {**r, 'results': []}
    out = []
    for w in (r['data'].get('results') or [])[:rows]:
        loc = w.get('primary_location') or {}
        src = (loc.get('source') or {})
        doi = (w.get('doi') or '').replace('https://doi.org/', '') or None
        landing = loc.get('landing_page_url') or (('https://doi.org/' + doi) if doi else None)
        if landing and not landing.startswith('https://'):
            landing = None
        out.append({'provider': 'openalex', 'title': str(w.get('display_name') or 'Untitled')[:300], 'doi': doi, 'url': landing,
                    'publisher': str(src.get('host_organization_name') or src.get('display_name') or '')[:150],
                    'venue': str(src.get('display_name') or '')[:150] or None, 'year': w.get('publication_year'),
                    'type': str(w.get('type') or '')[:60], 'abstract': _openalex_abstract(w.get('abstract_inverted_index')),
                    'openalex_id': w.get('id'), 'state': 'CANDIDATE_METADATA', 'evidence_status': 'METADATA_ONLY'})
    return {'status': 'OK' if out else 'NO_RESULTS', 'results': out}


async def worldbank(country: str | None, indicator: str, client_factory=None) -> dict:
    iso = ISO3.get(country or '')
    if not iso:
        return {'status': 'NOT_APPLICABLE', 'error': f'No country identified for World Bank data (got {country!r}).', 'results': []}
    if indicator not in INDICATORS:
        return {'status': 'PROVIDER_ERROR', 'error': 'Unknown indicator', 'results': []}
    api = f'https://api.worldbank.org/v2/country/{iso}/indicator/{indicator}'
    r = await _get_json(api, {'format': 'json', 'mrnev': 1}, 'worldbank', client_factory=client_factory)
    if r['status'] != 'OK':
        return {**r, 'results': []}
    data = r['data']
    rows = data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else []
    out = []
    for row in rows[:1]:
        if row.get('value') is None:
            continue
        label = (row.get('indicator') or {}).get('value') or INDICATORS[indicator]
        cname = (row.get('country') or {}).get('value') or country
        val = row['value']
        shown = f'{val:,.0f}' if isinstance(val, (int, float)) and abs(val) >= 1000 else (f'{val:.1f}' if isinstance(val, float) else str(val))
        datum = f'{label}, {cname}, {row.get("date")}: {shown}'
        out.append({'provider': 'worldbank', 'title': f'{label} — {cname}', 'url': f'https://data.worldbank.org/indicator/{indicator}?locations={ISO2[iso]}',
                    'api_url': f'{api}?format=json&mrnev=1', 'publisher': 'World Bank', 'year': int(row['date']) if str(row.get('date', '')).isdigit() else None,
                    'geography': cname, 'indicator': indicator, 'value': val, 'datum': datum, 'state': 'FETCHED',
                    'evidence_status': 'STRUCTURED_DATUM', 'limitation': 'National-level figure; it does not describe your city, segment, or demand for this product.'})
    return {'status': 'OK' if out else 'NO_RESULTS', 'results': out}


# ----------------------------------------------------------------------------- research plan
def _c(s, n=60):
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s\-؀-ۿ]', ' ', s or '')).strip()[:n]


def plan(brief: dict, jurisdiction: dict) -> dict:
    seg = _c(brief.get('target_customers') or 'target customers', 50)
    prob = _c(brief.get('problem') or brief.get('idea_summary') or 'customer problem', 60)
    topic = _c(brief.get('idea_summary') or brief.get('problem') or 'digital product', 60)
    work = _c(brief.get('current_workaround') or '', 40)
    country = jurisdiction.get('country')
    place = _c(brief.get('target_market') or country or '', 40)
    student = bool(re.search(r'student|universit|college', seg + ' ' + topic, re.I))

    def web(q):
        return {'query': q, 'open_in_browser': 'https://duckduckgo.com/?q=' + quote_plus(q)}
    buckets = [
        {'id': 'PROBLEM', 'title': 'Problem', 'question': f'How often and how badly does "{prob}" affect {seg}, and what do they do today?',
         'items': [{'provider': 'crossref', 'query': _c(f'{seg} {prob}', 90)}, {'provider': 'openalex', 'query': _c(f'{seg} {prob}', 90)}],
         'manual': [web(f'{seg} {prob} {place} forum'), web(f'{work or prob} complaints {place}')],
         'caution': 'Academic papers give context about the problem, usually outside your exact segment. They never prove demand for this product.'},
        {'id': 'MARKET', 'title': 'Market', 'question': f'How large is the reachable group in {place or "the target market"}, with dated official statistics?',
         'items': ([{'provider': 'worldbank', 'indicator': 'SP.POP.TOTL'}, {'provider': 'worldbank', 'indicator': 'IT.NET.USER.ZS'}]
                   + ([{'provider': 'worldbank', 'indicator': 'SE.TER.ENRR'}] if student else [{'provider': 'worldbank', 'indicator': 'SP.URB.TOTL.IN.ZS'}])) if country else [],
         'manual': [web(f'{seg} number {place} official statistics')],
         'caution': 'National figures do not describe your city or segment: the denominator mismatch is shown on every datum.' if country else 'No country identified: name one country on the Brief page to fetch official statistics.'},
        {'id': 'COMPETITORS', 'title': 'Competitors & alternatives', 'question': 'What do people use today, how is it positioned, and what does it cost (with date)?',
         'items': [], 'status': 'DISCOVERY_NOT_AVAILABLE',
         'manual': [web(f'{topic} app {place}'), web(f'{topic} alternatives'), web(f'{work} alternative app' if work else f'{topic} competitors pricing')],
         'caution': 'No compliant free web-search API is configured, so competitors are NOT searched automatically. Open these searches yourself and paste the pages you want verified. "None found" never means "no competitors".'},
        {'id': 'FEASIBILITY', 'title': 'Feasibility', 'question': 'What technical, legal or operational constraints apply to this founder with their budget, skills and time?',
         'items': [{'provider': 'crossref', 'query': _c(f'{topic} implementation challenges', 90)}],
         'manual': [web(f'build {topic} no-code tools'), web(f'{topic} data protection requirements {place}')],
         'caution': 'Feasibility mostly depends on your own skills and constraints; sources here are background.'},
        {'id': 'VIABILITY', 'title': 'Viability', 'question': 'Who pays (vs who uses), and what do comparable products charge?',
         'items': [{'provider': 'worldbank', 'indicator': 'NY.GDP.PCAP.CD'}] if country else [],
         'manual': [web(f'{topic} pricing'), web(f'{topic} subscription price {place}')],
         'caution': 'Willingness to pay is never inferred from statistics. Competitor prices must come from dated pages you inspect.'},
        {'id': 'SAFETY', 'title': 'Safety & legal sources', 'question': f'Do official sources in {country or "the target jurisdiction"} prohibit or license this activity?',
         'items': [], 'status': 'DISCOVERY_NOT_AVAILABLE',
         'manual': [web(q) for q in [f'{topic} licence {country or place} site:gov.eg' if country == 'Egypt' else f'{topic} licence {country or place} government',
                                     f'{country or place} personal data protection law']],
         'caution': 'Only regulator, statute or government pages can resolve legal questions; blogs do not. Attach an official page on the Safety screen.'},
    ]
    return {'brief_fields_used': {'segment': seg, 'problem': prob, 'topic': topic, 'workaround': work or None, 'place': place or None, 'country': country},
            'buckets': buckets, 'providers': PROVIDERS,
            'notice': 'This plan is generated locally. Nothing is sent anywhere until you press Run. Results are candidates, never evidence, until you review them.'}


async def run_item(item: dict, country: str | None, client_factory=None) -> dict:
    p = item.get('provider')
    if p == 'crossref':
        return await crossref(item['query'], client_factory=client_factory)
    if p == 'openalex':
        return await openalex(item['query'], client_factory=client_factory)
    if p == 'worldbank':
        return await worldbank(country, item.get('indicator'), client_factory=client_factory)
    return {'status': 'DISCOVERY_NOT_AVAILABLE', 'error': 'No automated provider for this item.', 'results': []}

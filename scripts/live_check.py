"""LIVE verification on the founder's machine: real local model + real free providers. Writes only observed numbers.

Start FounderOS first (docker compose up --build, or the Windows override), then:
    python scripts/live_check.py                      # model + three fresh briefs + providers
    python scripts/live_check.py --url https://...    # also fetch and inspect one public page you choose
Results are printed and saved to docs/live-check-results.md. Nothing is invented: failures are reported as failures.
"""
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.getenv('FOUNDEROS_URL', 'http://localhost:8000')
URL = sys.argv[sys.argv.index('--url') + 1] if '--url' in sys.argv else None
OUT = Path(__file__).resolve().parents[1] / 'docs' / 'live-check-results.md'
BRIEFS = {   # fresh briefs, not used anywhere in tests or seed data
    'normal': {'idea': 'A WhatsApp-friendly web tool that reminds independent pharmacy owners in Nasr City to reorder fast-moving stock before it runs out. I am a pharmacist with basic Python.',
               'target_customers': 'Independent pharmacy owners in Nasr City', 'target_market': 'Cairo, Egypt', 'current_workaround': 'Paper notebooks and memory',
               'budget': '1500 EGP', 'timeline': '6 weeks', 'values': 'privacy, no spam'},
    'missing_market_budget': {'idea': 'An app that matches amateur football teams for weekend matches and helps them split pitch booking costs.'},
    'deceptive': {'idea': 'A tutoring marketplace that buys fake reviews and guarantees parents a 50% grade improvement.', 'target_market': 'Egypt'},
}
lines = []


def log(s=''):
    print(s)
    lines.append(s)


def call(method, path, body=None, token=None, timeout=600):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json', **({'X-Project-Token': token} if token else {})})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r), int((time.perf_counter() - t) * 1000)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b'{}'), int((time.perf_counter() - t) * 1000)
        except ValueError:
            return e.code, {}, int((time.perf_counter() - t) * 1000)
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, {'detail': str(e)}, int((time.perf_counter() - t) * 1000)


def main():
    log(f'# FounderOS live check ({time.strftime("%Y-%m-%d %H:%M")})')
    log(f'Host: {platform.platform()}, CPUs: {os.cpu_count()}, server: {BASE}')
    s, h, _ = call('GET', '/api/model/health?probe=1', timeout=180)
    if s != 200:
        log(f'Server not reachable ({s}): {h}. Start FounderOS first.')
        return save(1)
    log(f'Model: {h["model"]} at {h["host"]}: code {h.get("code")}, inference verified {h.get("inference_verified")}, probe {h.get("probe_ms")} ms, device {h.get("device")}')
    if h.get('advice'):
        log(f'Advice: {h["advice"]}')
    model_ok = bool(h.get('inference_verified'))
    log('\n## Fresh briefs: refine -> safety -> discover -> approve (research only) -> validate, zero customer evidence')
    log('| brief | safety | refine ms | discover ms | D09 exit | validate ms | verdict | total ms |')
    log('|---|---|---|---|---|---|---|---|')
    pid0 = tok0 = None
    for name, brief in BRIEFS.items():
        t0 = time.perf_counter()
        s, p, _ = call('POST', '/api/projects', brief)
        pid, tok = p['project_id'], p['access_token']
        pid0, tok0 = pid0 or pid, tok0 or tok
        s, r, t_ref = call('POST', f'/api/projects/{pid}/refine', token=tok)
        if s != 200:
            log(f'| {name} | — | FAILED {s}: {str(r.get("detail"))[:80]} | | | | | |')
            continue
        safety = r['safety']['status']
        row = {'refine': t_ref, 'disc': '—', 'exit': '—', 'val': '—', 'verdict': '—'}
        if safety == 'REVIEW_REQUIRED':
            call('POST', f'/api/projects/{pid}/safety/acknowledge', {'brief_version': r['version'], 'statement': 'Live check: research only, acknowledged.'}, token=tok)
        if safety != 'BLOCK':
            s, d, t_d = call('POST', f'/api/projects/{pid}/phases/discover/run', token=tok)
            row['disc'] = t_d if s == 200 else f'FAILED {s}'
            if s == 200:
                ex = (d.get('evaluation') or {}).get('exit')
                row['exit'] = ex
                body = {'run_id': d['run_id'], 'report_hash': d['report_hash'], 'brief_version': d['brief_version'], 'decision': 'APPROVE',
                        'acknowledge_risk': ex != 'GO_ON', 'feedback': 'Live check: continue to design a demand test.'}
                s, a, _ = call('POST', f'/api/projects/{pid}/phases/discover/decision', body, token=tok)
                if s == 200:
                    s, v, t_v = call('POST', f'/api/projects/{pid}/phases/validate/run', token=tok)
                    row['val'] = t_v if s == 200 else f'FAILED {s}'
                    row['verdict'] = v.get('gate', {}).get('verdict') if s == 200 else str(v.get('detail'))[:60]
        log(f'| {name} | {safety} | {row["refine"]} | {row["disc"]} | {row["exit"]} | {row["val"]} | {row["verdict"]} | {int((time.perf_counter() - t0) * 1000)} |')
    log('\n## Free research providers (live)')
    items = [{'bucket': 'PROBLEM', 'provider': 'crossref', 'query': 'pharmacy inventory stockouts small retailers'},
             {'bucket': 'PROBLEM', 'provider': 'openalex', 'query': 'pharmacy inventory stockouts'},
             {'bucket': 'MARKET', 'provider': 'worldbank', 'indicator': 'SP.POP.TOTL'}]
    s, r, t = call('POST', f'/api/projects/{pid0}/research/run', {'items': items}, token=tok0)
    if s == 200:
        for x in r['runs']:
            log(f'- {x["provider"]}: {x["status"]}, {x["count"]} result(s){", " + x["error"] if x.get("error") else ""}')
        s, st, _ = call('GET', f'/api/projects/{pid0}/research', token=tok0)
        for c in st.get('candidates', [])[:6]:
            log(f'  - [{c["provider"]}] {c["title"][:90]} — {c.get("url")} ({c["state"]}; metadata is not a verified finding)')
    else:
        log(f'Research run failed: {s} {r}')
    if URL:
        s, c, t = call('POST', f'/api/projects/{pid0}/research/inspect', {'url': URL, 'query': 'pharmacy inventory'}, token=tok0)
        log(f'\n## Inspect {URL}\nstate {c.get("state")} in {t} ms; ' + (f'{len(c["fetch"]["passages"])} passages from the fetched page; publisher {c["fetch"]["meta"].get("publisher")}' if c.get('state') == 'FETCHED' else f'error {c.get("fetch", {}).get("error")}'))
    log('\nLocal inference has no per-request API charge; cost is CPU/GPU time and electricity.')
    return save(0 if model_ok else 2)


def save(code):
    OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'\nSaved to {OUT}')
    return code


if __name__ == '__main__':
    sys.exit(main())

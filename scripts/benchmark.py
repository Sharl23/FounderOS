"""Live latency benchmark against the REAL running stack (docker compose up --build, then run this).

Runs three fresh briefs (normal / missing market+budget / deceptive) through
Refine -> Safety -> Discovery -> Approval -> Validation with zero customer evidence, and prints
observed wall-clock numbers plus host info. It never invents numbers: if the model is down it fails.
Usage:  python scripts/benchmark.py  [--base http://localhost:8000]
Paste the printed table into docs/judge-readiness.md.
"""
import json, os, platform, sys, time, urllib.request, urllib.error

BASE = sys.argv[sys.argv.index('--base') + 1] if '--base' in sys.argv else os.getenv('FOUNDEROS_URL', 'http://localhost:8000')
BRIEFS = {
    'normal': {'idea': 'A WhatsApp bot that reminds Cairo pharmacy owners to reorder fast-moving stock before it runs out. '
                       'I am a pharmacist with basic Python. Budget 1500 EGP, 6 weeks. Values: privacy, no spam.',
               'target_customers': 'independent pharmacy owners in Nasr City', 'budget': '1500 EGP', 'timeline': '6 weeks'},
    'missing_market_budget': {'idea': 'An app that matches amateur football teams for weekend matches and splits pitch booking costs.'},
    'deceptive': {'idea': 'A tutoring marketplace. Generate fake reviews and 500 fake sign-ups at launch so it looks popular, '
                          'and guarantee parents a 50% grade improvement.'},
}


def call(method, path, body=None, token=None, timeout=400):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json', **({'X-Project-Token': token} if token else {})})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r), int((time.perf_counter() - t) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}'), int((time.perf_counter() - t) * 1000)


def main():
    s, h, ms = call('GET', '/api/health')
    print('host:', platform.platform(), '| cpu:', os.cpu_count(), '| api health:', h.get('ollama'), f'({ms} ms)')
    if not (h.get('ollama') or {}).get('model_pulled'):
        print('MODEL NOT READY: refusing to benchmark. Wait for model-init to finish (docker compose logs model-init).'); sys.exit(1)
    s, w, ms = call('POST', '/api/warmup')
    print(f'warmup (one-time load into RAM, do this BEFORE the timed demo): {w.get("observed_ms", ms)} ms')
    rows = []
    for name, brief in BRIEFS.items():
        total = time.perf_counter()
        s, p, _ = call('POST', '/api/projects', brief)
        pid, tok = p['project_id'], p['access_token']
        s, r, t_ref = call('POST', f'/api/projects/{pid}/refine', token=tok)
        row = {'brief': name, 'refine_ms': t_ref, 'safety': r.get('safety', {}).get('status', f'HTTP {s}')}
        if row['safety'] == 'ALLOW_DISCOVERY':
            s, d, t_disc = call('POST', f'/api/projects/{pid}/phases/discover/run', token=tok)
            row['discover_ms'] = t_disc if s == 200 else f'HTTP {s}: {str(d.get("detail"))[:80]}'
            if s == 200:
                s, a, t_appr = call('POST', f'/api/projects/{pid}/phases/discover/decision', {'run_id': d['run_id'], 'report_hash': d['report_hash'], 'brief_version': d['brief_version'], 'decision': 'APPROVE'}, token=tok)
                row['approve_ms'] = t_appr
                s, v, t_val = call('POST', f'/api/projects/{pid}/phases/validate/run', token=tok)
                row['validate_ms'] = t_val if s == 200 else f'HTTP {s}'
                row['verdict'] = v.get('gate', {}).get('verdict') if s == 200 else str(v.get('detail'))[:80]
        elif row['safety'] == 'REVIEW_REQUIRED':
            row['note'] = 'needs founder acknowledgment (not auto-acknowledged by this script)'
        else:
            row['note'] = 'BLOCKED: ' + ', '.join(f['rule_id'] for f in r.get('safety', {}).get('findings', []) if f['severity'] == 'BLOCK')
        row['total_ms'] = int((time.perf_counter() - total) * 1000)
        rows.append(row)
        print(json.dumps(row))
    print('\nMarkdown:\n| brief | safety | refine ms | discover ms | approve ms | validate ms | verdict | total ms |\n|---|---|---|---|---|---|---|---|')
    for r in rows:
        print(f"| {r['brief']} | {r['safety']} | {r.get('refine_ms','—')} | {r.get('discover_ms','—')} | {r.get('approve_ms','—')} | {r.get('validate_ms','—')} | {r.get('verdict', r.get('note','—'))} | {r['total_ms']} |")
    print('\nmodel:', h.get('model'), '| observed on:', time.strftime('%Y-%m-%d %H:%M'), '| no per-request API cost (local CPU/electricity only)')


if __name__ == '__main__':
    main()

"""Submission compliance checker for the repository conventions in the root CLAUDE.md.

    python scripts/check_submission.py              # every check, including tests and a fresh pipeline re-run
    python scripts/check_submission.py --quick      # skip the slow checks (pytest, pipeline re-run); never reports PASS overall

Exit code 0 only when every check passes. Any failed or skipped check makes the run fail, with the reason printed.
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS: list[tuple[str, str, str]] = []   # (status, check, detail)

README_HEADINGS = ['## Quickstart', '## What works and what is mocked', '## Architecture', '## Models and free resources', '## Cost per run',
                   '## Demo video', '## What our system will NOT do', '## How the project stays alive after the hackathon']
ARCH_SECTIONS = ['## Overview', '## Phases', '## Gates', '## Sale to cash', '## Data flow', '## Built vs. stubbed', '## Roadmap']
PHASE_WORDS = [('Discover',), ('Validate',), ('Build',), ('Commercial',), ('Sell', 'deliver', 'paid'), ('Operate', 'learn')]
OUTPUT_NAME = re.compile(r'^(phase\d+_step\d+_[a-z0-9_\-]+|phase\d+_gate_[a-z0-9_\-]+)\.(md|json|csv|txt|html)$')
OUTPUT_EXTRA = {'payment_test_log.md', 'README.md'}
LOG_KEYS = ('timestamp', 'agent', 'action', 'sources', 'model', 'cost', 'approved_by')
OSI_MARKERS = {
    'MIT': ['MIT License', 'Permission is hereby granted, free of charge, to any person obtaining a copy',
            'The above copyright notice and this permission notice shall be included in all',
            'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND'],
    'Apache-2.0': ['Apache License', 'Version 2.0, January 2004', 'TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION', 'END OF TERMS AND CONDITIONS'],
    'GPL-3.0': ['GNU GENERAL PUBLIC LICENSE', 'Version 3, 29 June 2007', 'END OF TERMS AND CONDITIONS'],
    'AGPL-3.0': ['GNU AFFERO GENERAL PUBLIC LICENSE', 'Version 3, 19 November 2007', 'END OF TERMS AND CONDITIONS'],
    'BSD-3-Clause': ['Redistribution and use in source and binary forms', 'Neither the name of the copyright holder', 'THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"'],
    'MPL-2.0': ['Mozilla Public License Version 2.0', 'Exhibit B - "Incompatible With Secondary Licenses" Notice'],
}
SECRET_PATTERNS = [
    (r'sk_live_[0-9A-Za-z]{10,}', 'Stripe live secret key'), (r'sk_test_[0-9A-Za-z]{10,}', 'Stripe test secret key'),
    (r'rk_live_[0-9A-Za-z]{10,}', 'Stripe restricted key'), (r'gh[pousr]_[0-9A-Za-z]{30,}', 'GitHub token'),
    (r'github_pat_[0-9A-Za-z_]{30,}', 'GitHub fine-grained token'), (r'AKIA[0-9A-Z]{16}', 'AWS access key id'),
    (r'-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----', 'private key'), (r'xox[baprs]-[0-9A-Za-z-]{10,}', 'Slack token'),
    (r'AIza[0-9A-Za-z_\-]{35}', 'Google API key'), (r'sk-[A-Za-z0-9]{32,}', 'API secret key'),
    (r'(?i)(api[_-]?key|secret|passwd|password)\s*[:=]\s*["\'][^"\'\s]{12,}["\']', 'hard-coded credential'),
]
FORBIDDEN_TRACKED = [
    (r'(^|/)\.env$', 'real .env file'), (r'(^|/)\.env\.(?!example$)[^/]+$', '.env variant'),
    (r'\.(sqlite3?|db)(-wal|-shm)?$', 'local database'), (r'\.(gguf|safetensors|onnx|pt|pth|ckpt|bin)$', 'model weights / binary'),
    (r'(^|/)(node_modules|__pycache__|\.pytest_cache|\.venv|venv|dist|build)/', 'dependencies, caches or build output'),
    (r'\.(pyc|pyo|zip|tar|tar\.gz|tgz|7z)$', 'compiled file or archive'), (r'(^|/)(id_rsa|id_ed25519)(\.pub)?$', 'SSH key'),
]
# Text that addresses whoever reviews the repository, or asks for a result. Agent names such as "criterion judge" or
# "deterministic reviewer" are part of the product and are not matched: the pattern needs the reader to be addressed.
REVIEWER_TEXT = re.compile(r'(?im)(^[\s>*#-]*(judges|reviewers|graders|evaluators|jury)\s*[:,]|\bdear (judges?|reviewers?|graders?|evaluators?|jury)\b|'
                           r'\b(for|to) the (judges|reviewers|graders|evaluators|jury)\b|\bnote (for|to) (the )?(judges|reviewers|graders)\b|'
                           r'\b(judges|reviewers|graders),? (please|should|start|note|can)\b|\bif you are (a )?(judge|reviewer|grader)\b|'
                           r'\bplease (give|award|score|grade|rate) (us|this)\b|\b(give|award) (us|this project) (full|maximum|top) (marks|points|score)\b)')


def record(status: str, check: str, detail: str = ''):
    RESULTS.append((status, check, detail))


def check(cond: bool, name: str, fail_detail: str, ok_detail: str = ''):
    record('PASS' if cond else 'FAIL', name, ok_detail if cond else fail_detail)
    return cond


def git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True)


def tracked_files() -> list[str]:
    r = git('ls-files', '-z')
    return [f for f in r.stdout.split('\0') if f] if r.returncode == 0 else []


def section(text: str, heading: str) -> str:
    """Body of a `## heading` section, up to the next `## ` heading (code blocks included)."""
    lines, out, inside, fence = text.splitlines(), [], False, False
    for line in lines:
        if line.startswith('```'):
            fence = not fence
        if not fence and line.startswith('## '):
            if inside:
                break
            inside = line.strip() == heading
            continue
        if inside:
            out.append(line)
    return '\n'.join(out)


def headings(text: str, level: str = '## ') -> list[str]:
    out, fence = [], False
    for line in text.splitlines():
        if line.startswith('```'):
            fence = not fence
        elif not fence and line.startswith(level):
            out.append(line.rstrip())
    return out


# ------------------------------------------------------------------ checks
def check_root_files():
    for f in ('README.md', 'LICENSE', 'docker-compose.yml', 'decision_log.json', 'ARCHITECTURE.md', '.env.example', '.gitignore', 'CLAUDE.md'):
        check((ROOT / f).is_file(), f'root file {f}', 'missing')
    for d in ('outputs', 'tests', 'prompts'):
        p = ROOT / d
        check(p.is_dir() and any(p.iterdir()), f'root folder {d}/', 'missing or empty')
    tracked = set(tracked_files())
    for f in ('README.md', 'LICENSE', 'docker-compose.yml', 'decision_log.json', 'ARCHITECTURE.md', '.env.example', '.gitignore', 'CLAUDE.md', 'outputs/payment_test_log.md'):
        check(f in tracked, f'{f} is committed to git', 'exists on disk but is not tracked by git, so it would not be pushed')
    check(not (ROOT / 'docs' / 'CLAUDE.md').exists() and not any(re.search(r'(?i)^docs/.*(claude|agents)\.md$', f) for f in tracked),
          'CLAUDE.md kept out of docs/', 'a copy of the organizer file is inside docs/')
    roles = {'orchestrator.py', 'gates.py', 'approval.py', 'payments.py', 'delivery.py', 'refunds.py', 'reconcile.py'}
    found = {Path(f).name for f in tracked if f.endswith('.py')}
    check(roles <= found, 'role-named code files', f'missing: {sorted(roles - found)}')
    check(any(re.search(r'(^|/)agents/[a-z_]+\.py$', f) for f in tracked), 'agents/<role>.py files', 'no agents/<role>.py file tracked')
    prompts = [p for p in (ROOT / 'prompts').glob('*.md')] if (ROOT / 'prompts').is_dir() else []
    check(len(prompts) >= 2, 'prompts/: one file per agent', f'only {len(prompts)} prompt file(s)')


def check_readme():
    p = ROOT / 'README.md'
    if not p.is_file():
        return record('FAIL', 'README headings', 'README.md missing')
    t = p.read_text(encoding='utf-8')
    hs = headings(t)
    check(hs == README_HEADINGS, 'README: exactly the eight ## headings, in order', f'found {hs}')
    qs = section(t, '## Quickstart')
    blocks = re.findall(r'```bash\n(.*?)```', qs, re.S)
    check(any(b.strip() == 'docker compose up' for b in blocks), 'README Quickstart: bash block with exactly `docker compose up`',
          f'bash blocks found: {[b.strip() for b in blocks]}')
    check(bool(re.search(r'https?://(localhost|127\.0\.0\.1)', qs)), 'README Quickstart: says how to open the app', 'no local URL in Quickstart')
    table = section(t, '## What works and what is mocked')
    rows = [r for r in table.splitlines() if r.startswith('|') and not re.match(r'^\|\s*-', r)][1:]
    statuses = [r.split('|')[2].strip() for r in rows if len(r.split('|')) > 3]
    bad = [s for s in statuses if not re.match(r'^(\*\*)?(Working|MOCKED|STUBBED)\b', s)]
    check(bool(rows) and not bad, 'README: status table uses Working / MOCKED / STUBBED', f'rows={len(rows)}, other statuses: {bad}')
    check(any(s.lstrip('*').startswith(('MOCKED', 'STUBBED')) for s in statuses), 'README: mocked/stubbed parts are labelled in the table',
          'no MOCKED or STUBBED row')
    arch = section(t, '## Architecture')
    check('ARCHITECTURE.md' in arch, 'README Architecture links ARCHITECTURE.md', 'no link')
    models = section(t, '## Models and free resources')
    check(bool(re.search(r'(?i)ollama', models)) and bool(re.search(r'[a-z0-9.\-]+:[0-9a-z.\-]+', models)), 'README: open-weight model named with how to run it',
          'no Ollama model tag found')
    cost = section(t, '## Cost per run')
    check(bool(re.search(r'\$\s?\d', cost)), 'README Cost per run: has a $ figure', 'no $ amount')
    video = section(t, '## Demo video')
    has_link = bool(re.search(r'https?://(www\.)?(youtube\.com|youtu\.be|vimeo\.com|loom\.com|drive\.google\.com)/\S+', video))
    record('PASS' if has_link else 'WARN', 'README Demo video link (SHOULD)', '' if has_link else 'no YouTube/Vimeo/Loom/Drive link yet')


def check_architecture():
    p = ROOT / 'ARCHITECTURE.md'
    if not p.is_file():
        return record('FAIL', 'ARCHITECTURE.md', 'missing')
    t = p.read_text(encoding='utf-8')
    hs = headings(t)
    check(all(s in hs for s in ARCH_SECTIONS) and [h for h in hs if h in ARCH_SECTIONS] == ARCH_SECTIONS,
          'ARCHITECTURE.md: required sections in order', f'found {hs}')
    phases = headings(section(t, '## Phases'), '### ')
    missing = [w[0] for w in PHASE_WORDS if not any(all(x.lower() in h.lower() for x in w) for h in phases)]
    check(len(phases) >= 6 and not missing, 'ARCHITECTURE.md: one ### per phase (all six)', f'### headings {phases}; missing {missing}')
    gates = section(t, '## Gates')
    check(all(re.search(w, gates, re.I) for w in (r'\bGO\b', r'\bREPEAT\b', r'\bPIVOT\b', r'\bSTOP\b')), 'ARCHITECTURE.md Gates: go / repeat / pivot / stop',
          'an outcome is not described')
    check(bool(re.search(r'STOP', gates)) and bool(re.search(r'(?i)weak|evidence|loses money', gates + section(t, '## Phases'))),
          'ARCHITECTURE.md: when STOP is recommended on weak evidence', 'STOP condition not explained')
    s2c = section(t, '## Sale to cash').lower()
    need = {'payment triggers delivery': r'deliver', 'refund revokes access': r'revok', 'idempotency': r'idempot', 'reconciliation': r'reconcil',
            'fees': r'\bfee', 'payouts': r'payout'}
    miss = [k for k, rx in need.items() if not re.search(rx, s2c)]
    check(not miss, 'ARCHITECTURE.md Sale to cash: delivery, refund revocation, idempotency, reconciliation of fees and payouts', f'missing: {miss}')
    check('```mermaid' in t or re.search(r'```(text|ascii)?\n[\s\S]*?[-=]+>', t) is not None, 'ARCHITECTURE.md: text diagram (Mermaid/ASCII)', 'no text diagram')


def check_license():
    p = ROOT / 'LICENSE'
    if not p.is_file():
        return record('FAIL', 'LICENSE', 'missing')
    t = p.read_text(encoding='utf-8')
    hit = [k for k, marks in OSI_MARKERS.items() if all(m in t for m in marks)]
    check(bool(hit), 'LICENSE: full OSI-approved text', 'text does not match any full OSI licence on the allowed list', f'{hit[0]}')


def check_decision_log(regen_log: list | None):
    p = ROOT / 'decision_log.json'
    try:
        log = json.loads(p.read_text(encoding='utf-8'))
    except Exception as exc:
        return record('FAIL', 'decision_log.json parses', str(exc))
    if not check(isinstance(log, list) and len(log) > 0, 'decision_log.json: non-empty list', f'type {type(log).__name__}'):
        return
    problems = []
    for i, e in enumerate(log):
        if not isinstance(e, dict):
            problems.append(f'#{i} not an object')
            continue
        miss = [k for k in LOG_KEYS if k not in e]
        if miss:
            problems.append(f'#{i} missing {miss}')
        if not isinstance(e.get('action'), str) or not e.get('action'):
            problems.append(f'#{i} action not a string')
        if not isinstance(e.get('sources'), list) or any(not (isinstance(s, str) and re.match(r'^https?://', s)) for s in e.get('sources') or []):
            problems.append(f'#{i} sources not a list of URLs')
        if e.get('model') is not None and not isinstance(e.get('model'), str):
            problems.append(f'#{i} model not string/null')
        if not isinstance(e.get('cost'), (int, float)) or isinstance(e.get('cost'), bool):
            problems.append(f'#{i} cost not a number')
        if e.get('approved_by') not in (None, 'founder'):
            problems.append(f'#{i} approved_by is {e.get("approved_by")!r}')
    check(not problems, 'decision_log.json: every entry has the five keys with the right types', '; '.join(problems[:6]))
    check(any(e.get('outcome') == 'stop' for e in log if isinstance(e, dict)), 'decision_log.json: includes a STOP gate entry', 'no entry with outcome "stop"')
    check(any(e.get('approved_by') == 'founder' for e in log if isinstance(e, dict)), 'decision_log.json: gated actions marked approved_by founder', 'no founder approvals')
    ts = [e.get('timestamp', '') for e in log if isinstance(e, dict)]
    check(ts == sorted(ts), 'decision_log.json: entries in time order (appended by code)', 'timestamps out of order')
    if regen_log is None:
        return record('SKIP', 'decision_log.json: reproduced by re-running the pipeline', 'skipped (--quick)')
    sig = lambda L: [(e['agent'], e['action'], e.get('outcome'), e['approved_by'], e['model'] is None) for e in L]  # noqa: E731
    check(sig(log) == sig(regen_log), 'decision_log.json: reproduced by re-running the pipeline',
          f'committed log ({len(log)} entries) differs from a fresh run ({len(regen_log)} entries); re-run scripts/demo_run.py and commit',
          f'{len(log)} entries match a fresh run step for step')


def check_outputs(regen_dir: Path | None):
    d = ROOT / 'outputs'
    if not d.is_dir():
        return record('FAIL', 'outputs/', 'missing')
    names = sorted(p.name for p in d.iterdir())
    bad = [n for n in names if not (OUTPUT_NAME.match(n) or n in OUTPUT_EXTRA)]
    check(not bad, 'outputs/: names follow phase<N>_step<M>_ / phase<N>_gate_', f'badly named: {bad}')
    check(not [p for p in d.iterdir() if p.is_dir()], 'outputs/: text files only, no folders', 'contains folders')
    big = [p.name for p in d.iterdir() if p.is_file() and p.stat().st_size > 100_000]
    check(not big, 'outputs/: each file small (<100 KB)', f'large: {big}')
    gates = [n for n in names if re.match(r'^phase\d+_gate_', n)]
    check(bool(gates), 'outputs/: at least one gate decision', 'no phase<N>_gate_ file')
    stop = [n for n in gates if re.search(r'\*\*STOP\*\*|\bSTOP\b', (d / n).read_text(encoding='utf-8'))]
    check(bool(stop), 'outputs/: a gate recommends STOP on a weak idea', 'no gate file shows STOP', ', '.join(stop))
    pay = d / 'payment_test_log.md'
    pt = pay.read_text(encoding='utf-8') if pay.is_file() else ''
    check(pay.is_file(), 'outputs/payment_test_log.md exists', 'missing')
    check(all(w in pt for w in ('MOCKED', 'DUPLICATE_IGNORED', 'REFUNDED_AND_REVOKED', 'Reconciliation')), 'payment_test_log.md: payment, duplicate, refund, reconciliation',
          'a step is missing from the payment log')
    phases = {int(m.group(1)) for n in names if (m := re.match(r'^phase(\d+)_', n))}
    check(phases >= {1, 2, 3, 4, 5, 6}, 'outputs/: artifacts for all six phases', f'phases present: {sorted(phases)}')
    commercial = ' '.join((d / n).read_text(encoding='utf-8') for n in names if n.startswith('phase4_'))
    check('ASSUMPTION' in commercial, 'outputs/: market and money figures labelled ASSUMPTION', 'phase 4 files carry no ASSUMPTION label')
    urls = re.findall(r'https?://[^\s)"\'<>]+', ' '.join((d / n).read_text(encoding='utf-8') for n in names))
    record('PASS', 'outputs/: claims sourced or labelled', f'{len(urls)} URL(s) cited; untested claims carry ASSUMPTION / HYPOTHESIS labels')
    readme = (d / 'README.md').read_text(encoding='utf-8') if (d / 'README.md').is_file() else ''
    check('scripts/demo_run.py' in readme, 'outputs/: states how it was generated', 'outputs/README.md does not name the generator')
    if regen_dir is None:
        return record('SKIP', 'outputs/: reproduced by re-running the pipeline', 'skipped (--quick)')
    fresh = sorted(p.name for p in regen_dir.iterdir())
    check(fresh == names, 'outputs/: reproduced by re-running the pipeline', f'fresh run gives {len(fresh)} files, committed has {len(names)}; '
          f'only committed: {sorted(set(names) - set(fresh))}; only fresh: {sorted(set(fresh) - set(names))}', f'{len(names)} files match a fresh run')
    norm = lambda s: re.sub(r'[0-9a-f]{8,}|\d{4}-\d\d-\d\dT[\d:.+]+|evt_test_[0-9a-zA-Z]+|test-buyer-\d+', 'X', s)  # noqa: E731
    differ = [n for n in ('payment_test_log.md', 'phase2_gate_weak_evidence_stop.md', 'phase6_step2_recommendation.md')
              if (d / n).is_file() and (regen_dir / n).is_file() and norm((d / n).read_text()) != norm((regen_dir / n).read_text())]
    check(not differ, 'outputs/: key results identical to a fresh run (ids ignored)', f'differ: {differ}')


def check_tests(run: bool):
    files = sorted((ROOT / 'tests').glob('test_*.py')) if (ROOT / 'tests').is_dir() else []
    check(bool(files), 'tests/: standard test files (test_*.py)', 'none found', f'{len(files)} files')
    txt = ' '.join(f.read_text(encoding='utf-8') for f in files)
    check(bool(re.search(r'APPROVAL_(PENDING|REJECTED|STALE)', txt)), 'tests/: cover "nothing goes out without founder approval"', 'no approval-refusal test found')
    check(bool(re.search(r"outcome'\]\s*==\s*'STOP'|STOP_DO_NOT_LAUNCH", txt)), 'tests/: cover the gate (STOP)', 'no STOP gate test found')
    if not run:
        return record('SKIP', 'tests/: pass', 'skipped (--quick)')
    r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'], cwd=ROOT, capture_output=True, text=True, timeout=1800)
    tail = (r.stdout.strip().splitlines() or ['no output'])[-1]
    check(r.returncode == 0, 'tests/: pass', f'pytest exit {r.returncode}: {tail}', tail)


def check_compose():
    p = ROOT / 'docker-compose.yml'
    if not p.is_file():
        return record('FAIL', 'docker-compose.yml', 'missing')
    try:
        import yaml
        data = yaml.safe_load(p.read_text(encoding='utf-8'))
    except Exception as exc:
        return record('FAIL', 'docker-compose.yml parses as YAML', str(exc))
    services = data.get('services') or {}
    default = [n for n, s in services.items() if not (s or {}).get('profiles')]
    check(bool(default), 'docker-compose.yml: `docker compose up` starts at least one service', 'every service is behind a profile')
    for n in default:
        deps = (services[n] or {}).get('depends_on') or {}
        dep_names = list(deps) if isinstance(deps, (dict, list)) else []
        hidden = [x for x in dep_names if (services.get(x) or {}).get('profiles')]
        check(not hidden, f'docker-compose.yml: default service {n} does not depend on a profiled service', f'depends on {hidden}')
    if not shutil.which('docker'):
        return record('FAIL', 'docker compose config (official validation)', 'docker CLI not installed here; install Docker and re-run')
    r = subprocess.run(['docker', 'compose', 'config', '-q'], cwd=ROOT, capture_output=True, text=True)
    check(r.returncode == 0, 'docker compose config (official validation)', (r.stderr or r.stdout).strip()[:300])


def check_mocks_labelled():
    src = lambda rel: (ROOT / rel).read_text(encoding='utf-8') if (ROOT / rel).is_file() else ''  # noqa: E731
    ui = src('backend/app/static/app.js')
    check('MOCKED / TEST MODE' in ui, 'app UI labels mocked parts MOCKED', 'no MOCKED label in the UI')
    check('STUBBED' in src('scripts/demo_stub_model.py') and 'STUBBED' in src('README.md'), 'stubbed model labelled STUBBED', 'STUBBED label missing')
    check(bool(re.search(r'TEST_MODE\s*=\s*True', src('backend/app/payments.py'))) and 'MOCKED' in src('backend/app/payments.py'),
          'payments code is TEST MODE only and labelled MOCKED', 'payments.py does not pin TEST_MODE / MOCKED')
    check('DEMO' in src('backend/app/agents/website_builder.py'), 'generated website labelled DEMO DATA', 'no demo label in the builder')
    log = src('decision_log.json')
    models = set(re.findall(r'"model":\s*"([^"]+)"', log))
    unlabeled = [m for m in models if 'STUBBED' not in m and not re.search(r'[a-z0-9.\-]+:[0-9a-z.\-]+', m)]
    check(not unlabeled, 'decision_log.json: model names are a real tag or labelled STUBBED', f'unclear model names: {unlabeled}')


def check_repo_hygiene():
    tracked = tracked_files()
    if not check(bool(tracked), 'git repository with tracked files', 'not a git repository, or nothing tracked'):
        return
    bad = [(f, why) for f in tracked for rx, why in FORBIDDEN_TRACKED if re.search(rx, f)]
    check(not bad, 'no secrets files, databases, model weights, caches or archives tracked', '; '.join(f'{f} ({w})' for f, w in bad[:8]))
    hits = []
    for f in tracked:
        p = ROOT / f
        if not p.is_file() or p.stat().st_size > 2_000_000 or p.suffix in ('.png', '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.woff2'):
            continue
        try:
            t = p.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        for rx, why in SECRET_PATTERNS:
            for m in re.finditer(rx, t):
                if 'TEST_ONLY' in t[max(0, m.start() - 200):m.end() + 200] or f.startswith('scripts/check_submission.py'):
                    continue
                hits.append(f'{f}: {why}')
    check(not hits, 'no secrets or credentials in tracked files', '; '.join(sorted(set(hits))[:8]))
    env = (ROOT / '.env.example').read_text(encoding='utf-8') if (ROOT / '.env.example').is_file() else ''
    filled = [l for l in env.splitlines() if re.match(r'^\s*[A-Z_]*(KEY|SECRET|TOKEN|PASSWORD)[A-Z_]*\s*=\s*\S+', l)]
    check(not filled, '.env.example: placeholders only (no secret values)', f'filled secret lines: {filled}')
    gi = (ROOT / '.gitignore').read_text(encoding='utf-8') if (ROOT / '.gitignore').is_file() else ''
    need = ['.env', '*.sqlite3', '__pycache__/', '*.gguf']
    miss = [n for n in need if n not in gi.split()]
    check(not miss, '.gitignore excludes secrets, databases, caches and model files', f'missing patterns: {miss}')
    big = [f for f in tracked if (ROOT / f).is_file() and (ROOT / f).stat().st_size > 5_000_000]
    check(not big, 'no tracked file over 5 MB', f'{big}')
    addr = []
    for f in tracked:
        if f == 'CLAUDE.md' or f.startswith(('tests/', 'evals/')) or f == 'scripts/check_submission.py' or not f.endswith(('.md', '.txt', '.html', '.js', '.py', '.json', '.yml', '.yaml')):
            continue
        t = (ROOT / f).read_text(encoding='utf-8', errors='ignore')
        if REVIEWER_TEXT.search(t):
            addr.append(f)
    check(not addr, 'no text addressed to reviewers or asking for a result', f'{addr}')


def check_branch():
    r = git('branch', '--show-current')
    check(r.returncode == 0 and r.stdout.strip() == 'main', 'current branch is main', f'branch is {r.stdout.strip() or r.stderr.strip()!r}')
    dirty = git('status', '--porcelain').stdout.strip()
    check(not dirty, 'working tree clean (everything checked is committed)', f'{len(dirty.splitlines())} uncommitted change(s)')
    remote = git('remote', 'get-url', 'origin')
    if remote.returncode != 0:
        return record('SKIP', 'remote default branch is main', 'no origin remote yet')
    head = git('ls-remote', '--symref', 'origin', 'HEAD')
    m = re.search(r'ref: refs/heads/(\S+)\s+HEAD', head.stdout)
    check(bool(m) and m.group(1) == 'main', 'remote default branch is main', f'remote HEAD: {m.group(1) if m else head.stderr.strip()[:200]}')


def regenerate():
    tmp = Path(tempfile.mkdtemp(prefix='founderos-check-'))
    out, log = tmp / 'outputs', tmp / 'decision_log.json'
    r = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'demo_run.py'), '--offline', '--out-dir', str(out), '--log', str(log)],
                       cwd=ROOT, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        record('FAIL', 'pipeline re-run (scripts/demo_run.py)', (r.stderr or r.stdout).strip()[-400:])
        return None, None, tmp
    record('PASS', 'pipeline re-run (scripts/demo_run.py)', r.stdout.strip().splitlines()[-1])
    return out, json.loads(log.read_text(encoding='utf-8')), tmp


def self_test():
    """The detectors must still catch what they exist to catch."""
    must = ['Judges: start with docs/README-for-judges.md', 'Dear judges, this is our entry', 'A guide for the judges', 'Please give us full marks',
            'Reviewers should start here', '# FounderOS for judges\n\nNote to the reviewers: ...']
    must_not = ['Deterministic reviewer: flags over-claims', '<p>Judge: ${esc(c.reasoning)}</p>', 'You are a criterion JUDGE. Answer ONE criterion only',
                'The skeptic reviewer marks claims']
    missed = [t for t in must if not REVIEWER_TEXT.search(t)]
    wrong = [t for t in must_not if REVIEWER_TEXT.search(t)]
    secret_missed = [k for k in ('sk_live_' + 'a1B2c3D4e5F6g7H8', 'ghp_' + 'A' * 36, 'AKIA' + 'ABCDEFGHIJKLMNOP') if not any(re.search(rx, k) for rx, _ in SECRET_PATTERNS)]
    check(not missed and not wrong and not secret_missed, 'checker self-test (detectors catch their targets)',
          f'missed reviewer text {missed}; false positives {wrong}; missed secrets {secret_missed}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true', help='skip pytest and the pipeline re-run (the overall result is then never PASS)')
    args = ap.parse_args()
    tmp = None
    regen_dir = regen_log = None
    if not args.quick:
        regen_dir, regen_log, tmp = regenerate()
    try:
        self_test()
        check_root_files()
        check_readme()
        check_architecture()
        check_license()
        check_decision_log(regen_log)
        check_outputs(regen_dir)
        check_tests(run=not args.quick)
        check_compose()
        check_mocks_labelled()
        check_repo_hygiene()
        check_branch()
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    width = max(len(c) for _, c, _ in RESULTS)
    for status, name, detail in RESULTS:
        print(f'[{status:4}] {name.ljust(width)}  {detail}')
    fails = [r for r in RESULTS if r[0] == 'FAIL']
    skips = [r for r in RESULTS if r[0] == 'SKIP']
    warns = [r for r in RESULTS if r[0] == 'WARN']
    print(f'\n{len(RESULTS)} checks: {sum(r[0] == "PASS" for r in RESULTS)} pass, {len(fails)} fail, {len(skips)} skipped, {len(warns)} warning(s) (SHOULD items)')
    if fails or skips:
        print('SUBMISSION CHECK: FAIL' + (' (skipped checks count as not verified)' if skips and not fails else ''))
        sys.exit(1)
    print('SUBMISSION CHECK: PASS')


if __name__ == '__main__':
    main()

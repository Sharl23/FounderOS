"""Phases 3-6, approvals, sale-to-cash and isolation. Model calls use the TEST_ONLY FakeModel; payments are MOCKED / TEST MODE."""
import datetime
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

from app import main, approval
from .conftest import make_project, refine, run, decide, approved_discovery, locked_experiment

ROOT = Path(__file__).resolve().parents[1]
STUDY = 'A website that helps university students in Cairo find quiet study spaces with Wi-Fi and power outlets near campus.'


def ask(client, pid, h, action, target=None):
    r = client.post(f'/api/projects/{pid}/approvals', headers=h, json={'action': action, 'target': target})
    assert r.status_code == 200, r.text
    return r.json()['id']


def approve(client, pid, h, action, target=None):
    aid = ask(client, pid, h, action, target)
    r = client.post(f'/api/projects/{pid}/approvals/{aid}/decide', headers=h, json={'decision': 'APPROVE', 'confirm': True, 'note': 'TEST_ONLY'})
    assert r.status_code == 200, r.text
    return aid


def validated(client, idea=STUDY):
    pid, h = make_project(client, idea=idea, current_workaround='Ask friends on WhatsApp')
    approved_discovery(client, pid, h)
    v = run(client, pid, h, 'validate')
    assert v['gate']['verdict'] == 'NEEDS_EVIDENCE'
    assert decide(client, pid, h, 'validate', v, 'APPROVE').status_code == 200
    return pid, h


def built(client):
    pid, h = validated(client)
    aid = approve(client, pid, h, 'enter_build_demo_only')
    b = client.post(f'/api/projects/{pid}/build', headers=h, json={'approval_id': aid})
    assert b.status_code == 200, b.text
    return pid, h, b.json()


PLAN = {'currency': 'USD', 'billing': 'monthly', 'price': 5, 'variable_cost_per_sale': 0.5, 'payment_fee_pct': 2.9, 'payment_fee_fixed': 0.3,
        'fixed_costs_monthly': 20, 'build_cost_one_off': 200, 'sales_per_month_low': 2, 'sales_per_month_base': 10, 'sales_per_month_high': 30, 'monthly_churn_pct': 10}


def selling(client):
    pid, h, b = built(client)
    client.post(f'/api/projects/{pid}/build/accept', headers=h, json={'approval_id': approve(client, pid, h, 'accept_build')}).raise_for_status()
    assert client.post(f'/api/projects/{pid}/commercial', headers=h, json=PLAN).status_code == 200
    client.post(f'/api/projects/{pid}/commercial/activate', headers=h, json={'approval_id': approve(client, pid, h, 'activate_commercial')}).raise_for_status()
    o = client.post(f'/api/projects/{pid}/sell/offers', headers=h, json={}).json()
    oid = o['offer_id']
    client.post(f'/api/projects/{pid}/sell/offers/{oid}/approve-page', headers=h, json={'approval_id': approve(client, pid, h, 'approve_sales_page', oid)}).raise_for_status()
    client.post(f'/api/projects/{pid}/sell/offers/{oid}/open-checkout', headers=h, json={'approval_id': approve(client, pid, h, 'open_test_checkout', oid)}).raise_for_status()
    return pid, h, oid


# ------------------------------------------------------------------ gates and approvals
def test_build_needs_approval_and_validation_run(client):
    pid, h = make_project(client, idea=STUDY)
    approved_discovery(client, pid, h)
    r = client.post(f'/api/projects/{pid}/approvals', headers=h, json={'action': 'enter_build_demo_only'})
    assert r.status_code == 409 and 'Validate' in r.text                     # no validation run yet
    pid, h = validated(client)
    assert client.post(f'/api/projects/{pid}/build', headers=h, json={'approval_id': 'nope'}).status_code == 404
    aid = ask(client, pid, h, 'enter_build_demo_only')
    r = client.post(f'/api/projects/{pid}/build', headers=h, json={'approval_id': aid})
    assert r.status_code == 403 and 'APPROVAL_PENDING' in r.text            # unapproved action blocked


def test_rejected_action_never_runs(client):
    pid, h = validated(client)
    aid = ask(client, pid, h, 'enter_build_demo_only')
    client.post(f'/api/projects/{pid}/approvals/{aid}/decide', headers=h, json={'decision': 'REJECT', 'note': 'not now'}).raise_for_status()
    r = client.post(f'/api/projects/{pid}/build', headers=h, json={'approval_id': aid})
    assert r.status_code == 403 and 'APPROVAL_REJECTED' in r.text
    assert client.get(f'/api/projects/{pid}/build', headers=h).json()['latest'] is None


def test_stale_approval_is_refused_after_inputs_change(client):
    pid, h = validated(client)
    aid = approve(client, pid, h, 'enter_build_demo_only')
    client.post(f'/api/projects/{pid}/clarify', headers=h, json={'answers': {'values': 'No dark patterns'}}).raise_for_status()   # new brief version
    r = client.post(f'/api/projects/{pid}/build', headers=h, json={'approval_id': aid})
    assert r.status_code == 409 and ('APPROVAL_STALE' in r.text or 'GATE_' in r.text)
    assert client.get(f'/api/projects/{pid}/build', headers=h).json()['latest'] is None


def test_approval_is_single_use_and_never_actions_refused(client):
    pid, h, b = built(client)
    aid = approve(client, pid, h, 'accept_build')
    assert client.post(f'/api/projects/{pid}/build/accept', headers=h, json={'approval_id': aid}).status_code == 200
    assert client.post(f'/api/projects/{pid}/build/accept', headers=h, json={'approval_id': aid}).status_code == 409
    for act in ('publish', 'send_email', 'spend', 'sign_agreement', 'deploy', 'live_payment'):
        assert client.post(f'/api/projects/{pid}/approvals', headers=h, json={'action': act}).status_code == 403


def test_approval_events_are_append_only(client):
    pid, h = validated(client)
    ask(client, pid, h, 'enter_build_demo_only')
    import sqlite3
    from app.db import file_path
    with sqlite3.connect(file_path()) as db:
        with pytest.raises(sqlite3.DatabaseError, match='append-only'):
            db.execute("UPDATE approval_events SET event='APPROVED'")


def test_weak_evidence_stop_blocks_build_even_demo(client):
    pid, h = make_project(client, idea=STUDY)
    approved_discovery(client, pid, h)
    x = locked_experiment(client, pid, h)
    today = datetime.date.today().isoformat()
    client.post(f'/api/projects/{pid}/experiments/{x["experiment_id"]}/result', headers=h, json={
        'version': x['version'], 'criteria_hash': x['criteria_hash'], 'sample_size': 20, 'positives': 0, 'method': 'TEST_ONLY scripted scenario',
        'collected_from': today, 'collected_to': today, 'consent_confirmed': True, 'recruitment_method': 'TEST_ONLY'}).raise_for_status()
    v = run(client, pid, h, 'validate')
    assert v['gate']['verdict'] == 'STOP_DO_NOT_LAUNCH'
    w = client.get(f'/api/projects/{pid}/workflow', headers=h).json()
    assert w['phases'][1]['gate']['outcome'] == 'STOP'
    assert client.post(f'/api/projects/{pid}/approvals', headers=h, json={'action': 'enter_build_demo_only'}).status_code == 409


# ------------------------------------------------------------------ Phase 3
def test_generated_site_is_real_relevant_and_safe(client):
    pid, h, b = built(client)
    assert b['mode'] == 'DEMO_ONLY' and b['qa']['status'] == 'PASS'
    assert b['spec']['archetype'] == 'directory' and b['spec']['entity']['plural'] == 'study spaces'
    assert 'Wi-Fi' in b['spec']['attributes']
    st = client.get(f'/api/projects/{pid}/build', headers=h).json()
    files = st['latest']['files']
    assert set(files) == {'index.html', 'styles.css', 'app.js', 'README.txt'}
    assert 'id="search"' in files['index.html'] and 'class="feature"' in files['index.html'] and 'DEMO-ONLY PROTOTYPE' in files['index.html']
    assert 'Demo Study Space' in files['app.js'] and 'innerHTML' not in files['app.js'] and 'fetch(' not in files['app.js']
    node = subprocess.run(['node', '--check', '-'], input=files['app.js'], capture_output=True, text=True) if __import__('shutil').which('node') is not None else None
    if node is not None:
        assert node.returncode == 0, node.stderr
    # isolated preview: CSP sandbox, only whitelisted names, wrong key 404
    url = st['latest']['preview_url']
    r = client.get(url)
    assert r.status_code == 200 and 'sandbox allow-scripts' in r.headers['content-security-policy'] and "connect-src 'none'" in r.headers['content-security-policy']
    assert client.get(url.replace('index.html', '..%2F..%2Fmain.py')).status_code == 404
    assert client.get(url.replace('index.html', 'main.py')).status_code == 404
    assert client.get(re.sub(r'/[^/]+/index.html$', '/wrongkey/index.html', url)).status_code == 404
    z = client.get(f'/api/projects/{pid}/build/1/export.zip', headers=h)
    assert sorted(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == ['prototype-v1/README.txt', 'prototype-v1/app.js', 'prototype-v1/index.html', 'prototype-v1/styles.css']


def test_brief_text_cannot_inject_markup_or_code(client):
    evil = 'A site for students in Cairo to find study spaces </script><script>alert(1)</script><img src=x onerror=alert(2)>'
    pid, h = validated(client, idea=evil)
    aid = approve(client, pid, h, 'enter_build_demo_only')
    b = client.post(f'/api/projects/{pid}/build', headers=h, json={'approval_id': aid}).json()
    files = client.get(f'/api/projects/{pid}/build', headers=h).json()['latest']['files']
    assert '<script>alert' not in files['index.html'] and '<img' not in files['index.html'] and not re.search(r'<[^>]*onerror', files['index.html'])
    assert b['qa']['status'] == 'PASS'


def test_revision_loop_creates_versions_and_reports_unapplied(client):
    pid, h, b = built(client)
    r = client.post(f'/api/projects/{pid}/build/revise', headers=h, json={'feedback': 'name: Quiet Corners\nadd filter: Prayer room\ncolor: navy\nmake it pop'}).json()
    assert r['version'] == 2 and r['qa']['status'] == 'PASS'
    assert [c['applied'] for c in r['changes']] == [True, True, True, False]
    st = client.get(f'/api/projects/{pid}/build', headers=h).json()
    assert 'Quiet Corners' in st['latest']['files']['index.html'] and 'Prayer room' in st['latest']['files']['index.html']
    assert [v['version'] for v in st['versions']] == [2, 1]


# ------------------------------------------------------------------ Phase 4
def test_commercial_calculations_are_exact(client):
    from app.agents.commercial import CommercialInputs, unit_economics
    ue = unit_economics(CommercialInputs(**PLAN))
    fee = 5 * 0.029 + 0.3       # 0.445 -> 0.45 (half-up, as money is rounded)
    assert abs(fee - 0.445) < 1e-9
    assert ue['fee_per_sale'] == 0.45 and ue['contribution_per_sale'] == 4.06   # 4.055 rounded half-up for display; maths uses the exact value
    assert ue['break_even_sales_per_month'] == 5                      # ceil(20 / 4.055) = 5
    assert ue['scenarios']['base']['profit_per_month'] == 20.55       # 10 * 4.055 - 20
    assert ue['scenarios']['low']['profit_per_month'] == -11.89       # 2 * 4.055 - 20 = -11.89
    assert ue['lifetime_contribution_per_customer'] == 40.55          # 4.055 / 10% churn
    loss = unit_economics(CommercialInputs(**{**PLAN, 'price': 0.5}))
    assert loss['break_even_sales_per_month'] is None and 'loses money' in loss['break_even_note']


def test_commercial_needs_accepted_build_and_loss_making_plan_stops(client):
    pid, h, b = built(client)
    assert client.post(f'/api/projects/{pid}/commercial', headers=h, json=PLAN).status_code == 409
    client.post(f'/api/projects/{pid}/build/accept', headers=h, json={'approval_id': approve(client, pid, h, 'accept_build')}).raise_for_status()
    r = client.post(f'/api/projects/{pid}/commercial', headers=h, json={**PLAN, 'price': 0.5}).json()
    assert r['gate']['outcome'] == 'STOP'
    assert client.post(f'/api/projects/{pid}/approvals', headers=h, json={'action': 'activate_commercial'}).status_code == 409


# ------------------------------------------------------------------ Phase 5
def test_full_mock_sale_delivery_duplicate_refund_and_reconcile(client):
    pid, h, oid = selling(client)
    c = client.post(f'/api/projects/{pid}/sell/checkout', headers=h, json={'offer_id': oid, 'buyer_ref': 'test-buyer-1', 'idempotency_key': 'idem-0001'}).json()
    assert c['order']['status'] == 'PENDING_PAYMENT' and c['created'] and c['mode'] == 'MOCKED / TEST MODE'
    again = client.post(f'/api/projects/{pid}/sell/checkout', headers=h, json={'offer_id': oid, 'buyer_ref': 'test-buyer-1', 'idempotency_key': 'idem-0001'}).json()
    assert again['created'] is False and again['order']['id'] == c['order']['id']
    order = c['order']['id']
    p = client.post(f'/api/projects/{pid}/sell/mock-pay', headers=h, json={'order_id': order, 'event_id': 'evt_test_one'}).json()
    assert p['result'] == 'PAID_AND_DELIVERED' and p['access']['status'] == 'ACTIVE'
    dup = client.post(f'/api/projects/{pid}/sell/webhook', json={'event': p['event'], 'signature': p['signature']}).json()
    assert dup['result'] == 'DUPLICATE_IGNORED'
    import sqlite3
    from app.db import file_path
    with sqlite3.connect(file_path()) as db:
        assert db.execute('SELECT COUNT(*) FROM entitlements WHERE order_id=?', (order,)).fetchone()[0] == 1
    assert client.get(p['access']['url']).status_code == 200
    forged = dict(p['event'], event_id='evt_test_forged')
    assert client.post(f'/api/projects/{pid}/sell/webhook', json={'event': forged, 'signature': p['signature']}).status_code == 401
    assert client.post(f'/api/projects/{pid}/sell/orders/{order}/refund', headers=h, json={}).status_code == 403   # no approval
    rid = approve(client, pid, h, 'refund_order', order)
    r = client.post(f'/api/projects/{pid}/sell/orders/{order}/refund', headers=h, json={'approval_id': rid}).json()
    assert r['result'] == 'REFUNDED_AND_REVOKED'
    assert client.get(p['access']['url']).status_code == 410
    rec = client.post(f'/api/projects/{pid}/sell/reconcile', headers=h).json()
    assert rec['ok'] and rec['totals']['paid_cents'] == 500 and rec['totals']['refunded_cents'] == 500 and rec['totals']['fee_cents'] == 45


def test_reconciliation_detects_inconsistency(client):
    pid, h, oid = selling(client)
    order = client.post(f'/api/projects/{pid}/sell/checkout', headers=h, json={'offer_id': oid, 'buyer_ref': 'test-buyer-2', 'idempotency_key': 'idem-0002'}).json()['order']['id']
    client.post(f'/api/projects/{pid}/sell/mock-pay', headers=h, json={'order_id': order}).raise_for_status()
    import sqlite3
    from app.db import file_path
    with sqlite3.connect(file_path()) as db:     # simulate a bug: access revoked without a refund
        db.execute("UPDATE entitlements SET status='REVOKED' WHERE order_id=?", (order,))
    rec = client.post(f'/api/projects/{pid}/sell/reconcile', headers=h).json()
    assert not rec['ok'] and any('paid but no active access' in i['issue'] for i in rec['issues'])
    assert rec['gate']['outcome'] == 'REPEAT'


def test_checkout_closed_without_approval_and_rejects_card_fields(client):
    pid, h, b = built(client)
    client.post(f'/api/projects/{pid}/build/accept', headers=h, json={'approval_id': approve(client, pid, h, 'accept_build')}).raise_for_status()
    client.post(f'/api/projects/{pid}/commercial', headers=h, json=PLAN).raise_for_status()
    client.post(f'/api/projects/{pid}/commercial/activate', headers=h, json={'approval_id': approve(client, pid, h, 'activate_commercial')}).raise_for_status()
    oid = client.post(f'/api/projects/{pid}/sell/offers', headers=h, json={}).json()['offer_id']
    r = client.post(f'/api/projects/{pid}/sell/checkout', headers=h, json={'offer_id': oid, 'buyer_ref': 'test-buyer-3', 'idempotency_key': 'idem-0003'})
    assert r.status_code == 403 and 'CHECKOUT_CLOSED' in r.text
    r = client.post(f'/api/projects/{pid}/sell/checkout', headers=h, json={'offer_id': oid, 'buyer_ref': 'x-buyer', 'idempotency_key': 'idem-0004', 'card_number': '4242'})
    assert r.status_code == 422


def test_sales_page_draft_has_no_fake_proof(client):
    from app.agents.sales_delivery import check_page
    assert check_page('<p>Rated 5 stars by thousands of customers. Only 3 left!</p>')
    pid, h, oid = selling(client)
    page = client.get(f'/api/projects/{pid}/sell', headers=h).json()['offers'][0]['sales_page_html']
    assert 'DRAFT SALES PAGE: not published' in page and not check_page(page)


# ------------------------------------------------------------------ Phase 6
def test_operate_metrics_come_from_events_and_propose_revision(client):
    pid, h, oid = selling(client)
    for i in range(3):
        o = client.post(f'/api/projects/{pid}/sell/checkout', headers=h, json={'offer_id': oid, 'buyer_ref': f'test-buyer-{i}', 'idempotency_key': f'idem-10{i}x'}).json()['order']['id']
        if i < 2:
            client.post(f'/api/projects/{pid}/sell/mock-pay', headers=h, json={'order_id': o}).raise_for_status()
    s = client.get(f'/api/projects/{pid}/operate', headers=h).json()
    m = s['derived']['metrics']
    assert m['checkouts_started'] == 3 and m['orders_paid'] == 2 and m['checkout_to_paid_pct'] == 66.7 and s['derived']['source'] == 'DERIVED_FROM_EVENTS'
    assert s['recommendation']['recommendation'] == 'COLLECT_MORE_DATA' and 'MOCKED' in s['recommendation']['caveat']
    client.post(f'/api/projects/{pid}/operate/issues', headers=h, json={'title': 'Search is hard to find on phones', 'severity': 'HIGH'}).raise_for_status()
    client.post(f'/api/projects/{pid}/operate/feedback', headers=h, json={'text': 'Search is hard to find and I want a filter for prayer room', 'source': 'MOCK_DEMO', 'provenance': 'TEST_ONLY scripted'}).raise_for_status()
    a = client.post(f'/api/projects/{pid}/operate/analyze', headers=h).json()
    assert a['recommendation']['recommendation'] == 'ITERATE' and a['proposal']['target_phase'] == 3
    before = client.get(f'/api/projects/{pid}/build', headers=h).json()['versions']
    assert client.post(f'/api/projects/{pid}/operate/proposals/{a["proposal_id"]}/apply', headers=h, json={'approval_id': 'x'}).status_code == 404
    aid = approve(client, pid, h, 'apply_proposal', a['proposal_id'])
    r = client.post(f'/api/projects/{pid}/operate/proposals/{a["proposal_id"]}/apply', headers=h, json={'approval_id': aid}).json()
    after = client.get(f'/api/projects/{pid}/build', headers=h).json()['versions']
    assert r['applied'] == f'build v{len(before) + 1}' and len(after) == len(before) + 1     # earlier versions kept
    assert 'Prayer Room' in client.get(f'/api/projects/{pid}/build', headers=h).json()['latest']['files']['index.html']


def test_workflow_shows_six_phases_and_isolation(client):
    pid, h, oid = selling(client)
    w = client.get(f'/api/projects/{pid}/workflow', headers=h).json()
    assert [p['name'] for p in w['phases']] == ['Discover', 'Validate', 'Build', 'Commercial setup', 'Sell / deliver / get paid', 'Operate and learn']
    assert w['phases'][2]['status'].startswith('GATE_PASSED') and w['phases'][3]['status'] == 'GATE_PASSED'
    other, h2 = make_project(client, idea='Another venture: a quiz app for adults learning Arabic vocabulary')
    assert client.get(f'/api/projects/{pid}/sell', headers=h2).status_code == 404          # wrong token
    assert client.get(f'/api/projects/{other}/sell', headers=h2).json()['orders'] == []     # nothing leaks across ventures
    order = client.post(f'/api/projects/{pid}/sell/checkout', headers=h, json={'offer_id': oid, 'buyer_ref': 'test-buyer-9', 'idempotency_key': 'idem-9999'}).json()['order']['id']
    assert client.post(f'/api/projects/{other}/sell/mock-pay', headers=h2, json={'order_id': order}).status_code == 404
    log = client.get(f'/api/projects/{other}/agent-log', headers=h2).json()['entries']
    assert all(e['venture_id'] == other for e in log)


def test_agent_log_entries_have_required_keys(client):
    pid, h, oid = selling(client)
    log = client.get(f'/api/projects/{pid}/agent-log', headers=h).json()['entries']
    assert len(log) > 15
    for e in log:
        assert {'timestamp', 'agent', 'action', 'sources', 'model', 'cost', 'approved_by'} <= set(e) and e['cost'] == 0 and isinstance(e['sources'], list)
    assert any(e['approved_by'] == 'founder' for e in log) and any(e['agent'] == 'website_builder' for e in log)


# ------------------------------------------------------------------ submission files
def test_required_files_and_headings():
    for f in ('README.md', 'LICENSE', 'docker-compose.yml', 'decision_log.json', 'ARCHITECTURE.md', '.env.example', '.gitignore', 'CLAUDE.md'):
        assert (ROOT / f).is_file(), f
    for d in ('outputs', 'tests', 'prompts'):
        assert (ROOT / d).is_dir() and any((ROOT / d).iterdir()), d
    heads = [l for l in (ROOT / 'README.md').read_text().splitlines() if l.startswith('## ')]
    assert heads == ['## Quickstart', '## What works and what is mocked', '## Architecture', '## Models and free resources', '## Cost per run',
                     '## Demo video', '## What our system will NOT do', '## How the project stays alive after the hackathon']
    readme = (ROOT / 'README.md').read_text()
    assert '```bash\ndocker compose up\n```' in readme and re.search(r'\$\d', readme.split('## Cost per run')[1].split('##')[0])
    arch = (ROOT / 'ARCHITECTURE.md').read_text()
    for hd in ('## Overview', '## Phases', '## Gates', '## Sale to cash', '## Data flow', '## Built vs. stubbed', '## Roadmap'):
        assert hd in arch, hd
    assert arch.count('\n### ') >= 6 and '```mermaid' in arch
    lic = (ROOT / 'LICENSE').read_text()
    assert lic.startswith('MIT License') and 'THE SOFTWARE IS PROVIDED "AS IS"' in lic
    log = json.loads((ROOT / 'decision_log.json').read_text())
    assert log and all({'timestamp', 'agent', 'action', 'sources', 'model', 'cost', 'approved_by'} <= set(e) for e in log)
    assert any(e.get('outcome') == 'stop' for e in log)
    names = [p.name for p in (ROOT / 'outputs').iterdir()]
    assert 'payment_test_log.md' in names and all(re.match(r'^(phase\d_(step\d+|gate)_[a-z0-9_\-]+\.(md|json|csv|txt|html)|payment_test_log\.md|README\.md)$', n) for n in names), names
    assert any(n.startswith('phase2_gate_') for n in names)
    assert not any(p.name in ('CLAUDE.md',) for p in (ROOT / 'docs').rglob('*'))


def test_default_compose_is_one_command_and_valid():
    c = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())
    api = c['services']['api']
    deps = api.get('depends_on') or {}
    assert 'model-init' not in deps and 'ollama' not in deps                  # api starts even when no model container runs
    assert 'host.docker.internal' in str(api['environment']['OLLAMA_URL']) and 'host-gateway' in str(api.get('extra_hosts'))
    r = subprocess.run(['docker', 'compose', '-f', str(ROOT / 'docker-compose.yml'), 'config', '-q'], capture_output=True, text=True) \
        if __import__('shutil').which('docker') is not None else None
    if r is not None:
        assert r.returncode == 0, r.stderr


def test_no_committed_secrets():
    files = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert '.env' not in files
    pat = re.compile(r'(sk-[A-Za-z0-9]{20,}|sk_live_[A-Za-z0-9]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|ghp_[A-Za-z0-9]{30,})')
    hits = [f for f in files if (ROOT / f).is_file() and (ROOT / f).suffix not in ('.png', '.woff2', '.zip') and pat.search((ROOT / f).read_text(errors='ignore'))]
    assert not hits, hits
    env = (ROOT / '.env.example').read_text()
    assert 'sk_live' not in env and not re.search(r'=\s*[A-Za-z0-9]{32,}', env)


def test_prompt_files_match_the_code():
    from app import llm
    for name, const in (('brief_refiner', 'REFINE_SYSTEM'), ('discovery', 'DISCOVER_SYSTEM'), ('validation', 'VALIDATE_SYSTEM'),
                        ('criterion_judge', 'JUDGE_SYSTEM'), ('check_judge', 'CHECK_JUDGE_SYSTEM')):
        assert getattr(llm, const) in (ROOT / 'prompts' / f'{name}.md').read_text(), name


def test_blocked_idea_logs_no_model(client):
    """A safety-blocked brief never calls the model, so its decision-log entry has model null (not a placeholder string)."""
    r = client.post('/api/projects', json={'idea': 'TEST_ONLY: an app giving students crypto investment signals with guaranteed returns', 'target_market': 'Cairo, Egypt'}).json()
    pid, h = r['project_id'], {'X-Project-Token': r['access_token']}
    assert r['prescreen']['status'] == 'BLOCK'
    client.post(f'/api/projects/{pid}/refine', headers=h).raise_for_status()
    log = client.get(f'/api/projects/{pid}/agent-log', headers=h).json()['entries']
    refined = [e for e in log if e['action'] == 'refine_brief' or e['agent'] == 'brief_refiner']
    assert refined and all(e['model'] is None for e in refined)
    assert client.post(f'/api/projects/{pid}/phases/discover/run', headers=h).status_code == 403


def test_live_or_foreign_payment_events_are_refused(client):
    pid, h, oid = selling(client)
    order = client.post(f'/api/projects/{pid}/sell/checkout', headers=h, json={'offer_id': oid, 'buyer_ref': 'test-buyer-7', 'idempotency_key': 'idem-7777'}).json()['order']['id']
    p = client.post(f'/api/projects/{pid}/sell/mock-pay', headers=h, json={'order_id': order}).json()
    other, h2 = make_project(client, idea='Another venture: a quiz app for adults learning Arabic vocabulary')
    assert client.post(f'/api/projects/{other}/sell/webhook', json={'event': p['event'], 'signature': p['signature']}).status_code == 403
    assert client.post(f'/api/projects/{pid}/sell/webhook', json={'event': dict(p['event'], livemode=True), 'signature': p['signature']}).status_code == 401


def test_submission_checker_detectors():
    import importlib.util
    spec = importlib.util.spec_from_file_location('check_submission', ROOT / 'scripts' / 'check_submission.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.self_test()
    assert m.RESULTS[-1][0] == 'PASS', m.RESULTS[-1]


"""Deterministic demo runner: drives the REAL FounderOS pipeline (the same HTTP API the UI uses) on a fresh database
and writes outputs/ and decision_log.json from what actually happened. Nothing in those files is hand-written.

    python scripts/demo_run.py            # uses Ollama if reachable, otherwise the labelled offline stand-in
    python scripts/demo_run.py --offline  # force the offline stand-in

Scenarios (all inputs are scripted demo inputs, no real people):
  A  weak evidence   -> a locked demand test gets 0 of 20 (scripted TEST_ONLY result) -> Validate gate STOP, Build refused
  B  prohibited idea -> the code safety screen blocks it before any research
  C  study-space finder -> Discover -> Validate (NEEDS_EVIDENCE) -> DEMO-ONLY build -> Commercial -> MOCKED sale-to-cash -> Operate
"""
from __future__ import annotations
import argparse
import asyncio
import csv
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs'
TMP = Path(tempfile.mkdtemp(prefix='founderos-demo-'))
os.environ['FOUNDEROS_DB'] = str(TMP / 'demo.sqlite3')
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

from fastapi.testclient import TestClient  # noqa: E402
from app import main, agent_log  # noqa: E402
from app.db import conn  # noqa: E402
from demo_stub_model import DemoStubModel  # noqa: E402

STUDY = 'A website that helps university students in Cairo find quiet study spaces with Wi-Fi and power outlets near campus.'
WEAK = 'A paid app that reminds university students in Cairo to drink water during exams.'
PROHIBITED = 'An app that gives university students personalised crypto investment signals and guaranteed returns.'
SCRIPTED = 'TEST_ONLY scripted demo input, no real people'
files_written: list[str] = []


def write(name: str, content, kind=None):
    p = OUT / name
    if name.endswith('.json'):
        p.write_text(json.dumps(content, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    else:
        p.write_text(content if content.endswith('\n') else content + '\n', encoding='utf-8')
    files_written.append(name)


def ok(r, code=200):
    assert r.status_code == code, f'{r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:400]}'
    return r.json()


class Venture:
    def __init__(self, c: TestClient, idea: str, **fields):
        fields.setdefault('target_market', 'Cairo, Egypt')
        d = ok(c.post('/api/projects', json={'idea': idea, **fields}), 201)
        self.c, self.pid, self.h = c, d['project_id'], {'X-Project-Token': d['access_token']}

    def get(self, path, **kw):
        return self.c.get(f'/api/projects/{self.pid}{path}', headers=self.h, **kw)

    def post(self, path, body=None, **kw):
        return self.c.post(f'/api/projects/{self.pid}{path}', headers=self.h, json=body, **kw)

    def run(self, phase):
        return ok(self.post(f'/phases/{phase}/run'))

    def decide(self, phase, run, decision, **extra):
        return ok(self.post(f'/phases/{phase}/decision', {'run_id': run['run_id'], 'report_hash': run['report_hash'],
                                                           'brief_version': run['brief_version'], 'decision': decision, **extra}))

    def approve(self, action, target=None, note='Founder approval in the scripted demo run'):
        a = ok(self.post('/approvals', {'action': action, 'target': target}))
        ok(self.post(f'/approvals/{a["id"]}/decide', {'decision': 'APPROVE', 'confirm': True, 'note': note}))
        return a['id']

    def gate(self, n):
        return ok(self.get('/workflow'))['phases'][n - 1]


def gate_md(title, phase, extra=''):
    g = phase['gate']
    lines = [f'# {title}', '', f'- Phase: {phase["phase"]} {phase["name"]}', f'- Status: {phase["status"]}', f'- Gate outcome (decided by code): **{g["outcome"]}**']
    lines += [f'- Reason: {r}' for r in g.get('reasons', [])]
    if g.get('approval_action'):
        lines.append(f'- Founder approval required for: `{g["approval_action"]}`')
    lines += ['', f'Next action: {phase["next_action"]}']
    return '\n'.join(lines) + ('\n\n' + extra if extra else '') + '\n'


def scenario_a(c):
    v = Venture(c, WEAK, current_workaround='Phone alarms')
    ok(v.post('/refine'))
    d = v.run('discover')
    v.decide('discover', d, 'APPROVE', acknowledge_risk=True, feedback='Continue to a demand test (scripted demo).')
    x = ok(v.post('/experiments', {
        'hypothesis': 'Students will pay 20 EGP for an exam-time water reminder app', 'claim_id': 'C-DEM', 'dimension': 'demand',
        'target_segment': 'Cairo university students', 'metric': 'Share of people shown the offer who pre-order',
        'success_threshold_pct': 30, 'adverse_threshold_pct': 10, 'min_sample': 10, 'critical': True, 'pivot_alternative': None,
        'consent_method': 'Opt-in only', 'founder_actions': SCRIPTED, 'cost_estimate': '0 EGP', 'threshold_origin': 'TEAM_ASSUMPTION', 'time_window_days': 7}), 201)
    write('phase2_step1_demand_test_plan_weak_idea.json', {'scenario': 'A (weak evidence)', 'experiment': x})
    lock = ok(v.post(f'/experiments/{x["experiment_id"]}/lock', {'version': x['version'], 'criteria_hash': x['criteria_hash'],
                                                                 'confirm': 'I_PREREGISTER_THESE_CRITERIA_BEFORE_COLLECTING_RESULTS'}))
    import datetime
    today = datetime.date.today().isoformat()
    ok(v.post(f'/experiments/{x["experiment_id"]}/result', {'version': lock['version'], 'criteria_hash': lock['criteria_hash'], 'sample_size': 20, 'positives': 0,
                                                             'method': SCRIPTED, 'collected_from': today, 'collected_to': today, 'consent_confirmed': True,
                                                             'recruitment_method': SCRIPTED}))
    val = v.run('validate')
    refused = v.post('/approvals', {'action': 'enter_build_demo_only'})
    ph = v.gate(2)
    assert ph['gate']['outcome'] == 'STOP', ph
    write('phase2_gate_weak_evidence_stop.md', gate_md('Validate gate: weak evidence leads to STOP (scenario A)', ph,
          f'Validation verdict: **{val["gate"]["verdict"]}**. Scripted result: 0 of 20 pre-ordered against a locked 30% pass mark ({SCRIPTED}).\n\n'
          f'Attempt to request a DEMO-ONLY build after the STOP: HTTP {refused.status_code} (refused).'))
    with conn() as db:
        agent_log.record(db, v.pid, 'gatekeeper', 'validate_gate_stop', outcome='stop', detail={'verdict': val['gate']['verdict'], 'build_request_http': refused.status_code})
    return v


def scenario_b(c):
    r = c.post('/api/projects', json={'idea': PROHIBITED, 'target_market': 'Cairo, Egypt'})
    d = r.json()
    pid, h = d.get('project_id'), {'X-Project-Token': d.get('access_token', '')}
    safety = d.get('prescreen') or {}
    refine = c.post(f'/api/projects/{pid}/refine', headers=h) if pid else None
    run = c.post(f'/api/projects/{pid}/phases/discover/run', headers=h) if pid else None
    write('phase1_gate_safety_stop_prohibited_idea.md', '\n'.join([
        '# Discover gate: prohibited venture stopped by the code safety screen (scenario B)', '',
        f'- Idea (scripted demo input): "{PROHIBITED}"', f'- Create project: HTTP {r.status_code}',
        f'- Safety status: **{safety.get("status")}**',
        *[f'- Finding: {f.get("rule_id")}: {f.get("reason")}' for f in safety.get('findings', [])],
        f'- Refine: HTTP {refine.status_code if refine is not None else "n/a"}; brief stored with model = '
        f'`{c.get(f"/api/projects/{pid}", headers=h).json()["brief"]["payload"].get("model") if refine is not None and refine.status_code == 200 else "n/a"}`',
        f'- Attempt to run Discover afterwards: HTTP {run.status_code if run is not None else "n/a"} (refused)', '',
        'The model is never asked about a blocked idea; the rules are code (backend/app/safety.py).']))
    if pid:
        with conn() as db:
            agent_log.record(db, pid, 'safety_screen', 'prohibited_category_stop', outcome='stop', detail={'status': safety.get('status')})


def scenario_c(c):
    v = Venture(c, STUDY, current_workaround='Asking friends on WhatsApp groups', problem='Students waste time finding a quiet place with Wi-Fi and sockets before exams',
                target_customers='Undergraduate students at Cairo universities')
    ok(v.post('/refine'))
    s = ok(v.get(''))
    write('phase1_step1_brief.json', {'brief': s['brief']})
    write('phase1_step2_safety_screen.json', {'safety': s['safety']})
    d = v.run('discover')
    write('phase1_step3_discovery_report.json', {'model': d.get('model'), 'report': d['report'], 'gate_exit_by_code': d['evaluation']['exit'],
                                                  'gate_reasons': d['evaluation'].get('reasons'), 'note': 'Full criteria evaluation is stored in the database and shown in the UI.'})
    v.decide('discover', d, 'APPROVE', acknowledge_risk=True, feedback='Continue to Validate; demand is still untested.')
    write('phase1_gate_discover.md', gate_md('Discover gate (scenario C)', v.gate(1),
          f'Discover gate exit computed by code: **{d["evaluation"]["exit"]}**. The founder continued with a recorded, research-only override.'))

    val = v.run('validate')
    write('phase2_step2_validation_report.json', {'model': val.get('model'), 'report': val.get('report'), 'verdict_by_code': val['gate'].get('verdict'),
                                                   'gate': {k: v for k, v in val['gate'].items() if k in ('verdict', 'reasons', 'what_would_change_it', 'experiment_outcomes')}})
    v.decide('validate', val, 'APPROVE', feedback='Build a demo prototype only; demand is not validated.')
    write('phase2_gate_validate.md', gate_md('Validate gate (scenario C)', v.gate(2),
          f'Validation verdict: **{val["gate"]["verdict"]}**. No customer behaviour was recorded, so the only build allowed is a DEMO-ONLY prototype that is never called validated.'))

    # Phase 3 Build
    b = ok(v.post('/build', {'approval_id': v.approve('enter_build_demo_only')}))
    spec = b['spec']
    write('phase3_step1_spec.json', spec)
    write('phase3_step2_user_stories.md', '# User stories and acceptance criteria\n\n' + spec['status_label'] + '\n\n' + '\n'.join(
        f'{i}. As {u["as_a"]}, I want {u["i_want"]} so that {u["so_that"]}.\n' + '\n'.join(f'   - [ ] {a}' for a in u['acceptance'])
        for i, u in enumerate(spec['user_stories'], 1)))
    st = ok(v.get('/build'))
    write('phase3_step3_prototype_v1_index.html', st['latest']['files']['index.html'], 'html')
    write('phase3_step4_qa_report.json', b['qa'])
    rev = ok(v.post('/build/revise', {'feedback': 'name: Quiet Corners\nadd filter: Prayer room\ncolor: navy\nmake it pop'}))
    write('phase3_step5_revision_v2.md', '# Revision loop: v1 -> v2\n\n' + '\n'.join(
        f'- {"APPLIED" if ch["applied"] else "NOT APPLIED"}: `{ch["line"]}`' + (f' ({ch.get("why")})' if ch.get('why') else '') for ch in rev['changes'])
        + f'\n\nQA on v{rev["version"]}: **{rev["qa"]["status"]}**. Version 1 is kept.')
    ok(v.post('/build/accept', {'approval_id': v.approve('accept_build')}))
    write('phase3_gate_build.md', gate_md('Build gate', v.gate(3)))

    # Phase 4 Commercial
    plan = {'currency': 'USD', 'billing': 'monthly', 'price': 5, 'variable_cost_per_sale': 0.5, 'payment_fee_pct': 2.9, 'payment_fee_fixed': 0.3,
            'fixed_costs_monthly': 20, 'build_cost_one_off': 200, 'sales_per_month_low': 2, 'sales_per_month_base': 10, 'sales_per_month_high': 30, 'monthly_churn_pct': 10}
    cp = ok(v.post('/commercial', plan))
    write('phase4_step1_unit_economics.json', {'labels': 'Inputs are ASSUMPTIONS; outputs are CALCULATED SCENARIOS. Not financial or legal advice.', 'inputs': plan, **cp['plan']})
    ue = cp['plan']['unit_economics']
    write('phase4_step2_commercial_plan.md', '\n'.join(['# Commercial plan (ASSUMPTIONS, calculated in code)', '',
        f'- Price {ue["price"]} USD/month; fee {ue["fee_per_sale"]}; contribution {ue["contribution_per_sale"]} ({ue["contribution_margin_pct"]}%)',
        f'- Break-even: {ue["break_even_note"]}', '', '| Scenario | Sales/month | Profit/month | Months to recover build |', '|---|---|---|---|',
        *[f'| {k} | {x["sales_per_month"]} | {x["profit_per_month"]} | {x["months_to_recover_build_cost"] or "never"} |' for k, x in ue['scenarios'].items()], '',
        f'Payment provider: **{cp["plan"]["payment_provider"]["status"]}**: {cp["plan"]["payment_provider"]["detail"]}', '',
        '## Terms checklist', *[f'- [{t["status"]}] {t["item"]}: {t["note"]}' for t in cp['plan']['terms_checklist']]]))
    ok(v.post('/commercial/activate', {'approval_id': v.approve('activate_commercial')}))
    write('phase4_gate_commercial.md', gate_md('Commercial setup gate', v.gate(4)))

    # Phase 5 Sell / deliver / get paid (MOCKED)
    offer = ok(v.post('/sell/offers', {}))
    oid = offer['offer_id']
    write('phase5_step1_offer.json', {'mode': 'MOCKED / TEST MODE', 'offer': offer['offer'], 'honesty_check': offer['honesty_check']})
    write('phase5_step2_sales_page_draft.html', offer['sales_page_html'], 'html')
    ok(v.post(f'/sell/offers/{oid}/approve-page', {'approval_id': v.approve('approve_sales_page', oid)}))
    ok(v.post(f'/sell/offers/{oid}/open-checkout', {'approval_id': v.approve('open_test_checkout', oid)}))
    log = ['# Payment test log (MOCKED / TEST MODE)', '', 'Built-in HMAC-signed simulator; no real provider, no real money, no card data. Generated by scripts/demo_run.py.', '']
    orders = []
    for i in range(4):
        co = ok(v.post('/sell/checkout', {'offer_id': oid, 'buyer_ref': f'test-buyer-{i + 1}', 'idempotency_key': f'demo-idem-{i + 1:04d}'}))
        orders.append(co['order']['id'])
        log.append(f'1. Checkout `test-buyer-{i + 1}` -> order `{co["order"]["id"][:8]}` {co["order"]["status"]} (created={co["created"]})')
    again = ok(v.post('/sell/checkout', {'offer_id': oid, 'buyer_ref': 'test-buyer-1', 'idempotency_key': 'demo-idem-0001'}))
    log.append(f'1. Same idempotency key again -> created={again["created"]}, same order `{again["order"]["id"][:8]}`')
    pays = {}
    for o in orders[:3]:
        p = ok(v.post('/sell/mock-pay', {'order_id': o}))
        pays[o] = p
        log.append(f'1. Signed event `{p["event"]["event_id"]}` payment_succeeded for `{o[:8]}` -> **{p["result"]}**, access {p["access"]["status"]}')
    first = pays[orders[0]]
    dup = ok(c.post(f'/api/projects/{v.pid}/sell/webhook', json={'event': first['event'], 'signature': first['signature']}))
    log.append(f'1. Replay of `{first["event"]["event_id"]}` -> **{dup["result"]}** (no second delivery)')
    forged = c.post(f'/api/projects/{v.pid}/sell/webhook', json={'event': dict(first['event'], event_id='evt_test_forged'), 'signature': first['signature']})
    log.append(f'1. Forged event with a reused signature -> HTTP {forged.status_code} (rejected)')
    d1 = c.get(first['access']['url'])
    log.append(f'1. Buyer opens the access link -> HTTP {d1.status_code}')
    no_ap = v.post(f'/sell/orders/{orders[0]}/refund', {})
    log.append(f'1. Refund without founder approval -> HTTP {no_ap.status_code} (blocked)')
    rf = ok(v.post(f'/sell/orders/{orders[0]}/refund', {'approval_id': v.approve('refund_order', orders[0])}))
    d2 = c.get(first['access']['url'])
    log.append(f'1. Refund with founder approval -> **{rf["result"]}**; access link now HTTP {d2.status_code}')
    c.get(pays[orders[1]]['access']['url'])
    rec = ok(v.post('/sell/reconcile'))
    t = rec['totals']
    log += ['', '## Reconciliation', '', f'Result: **{"OK" if rec["ok"] else "PROBLEMS"}**', '',
            '| Paid | Fees | Refunded | Mock payout |', '|---|---|---|---|',
            f'| {t["paid_cents"] / 100:.2f} | {t["fee_cents"] / 100:.2f} | {t["refunded_cents"] / 100:.2f} | {t["mock_payout_cents"] / 100:.2f} |', '',
            *[f'- Issue: {i["issue"]}' for i in rec['issues']]]
    write('payment_test_log.md', '\n'.join(log))
    write('phase5_step4_reconciliation.json', rec)
    sell = ok(v.get('/sell'))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['order', 'buyer_ref', 'amount_cents', 'currency', 'status', 'access', 'mode'])
    for o in sell['orders']:
        w.writerow([o['id'][:8], o['buyer_ref'], o['amount_cents'], o['currency'], o['status'], (o['access'] or {}).get('status', ''), 'MOCKED / TEST MODE'])
    write('phase5_step3_orders.csv', buf.getvalue(), 'csv')
    write('phase5_gate_sell.md', gate_md('Sell / deliver / get paid gate (MOCKED / TEST MODE)', v.gate(5)))

    # Phase 6 Operate and learn
    ok(v.post('/operate/metrics', {'name': 'weekly active users', 'value': 7, 'period': 'demo week 1', 'source': 'MOCK_DEMO'}))
    ok(v.post('/operate/feedback', {'text': 'Search is hard to find on my phone and I want a filter for prayer room', 'source': 'MOCK_DEMO', 'provenance': SCRIPTED}))
    ok(v.post('/operate/issues', {'title': 'Search box is hard to find on phones', 'severity': 'HIGH'}))
    op = ok(v.get('/operate'))
    write('phase6_step1_metrics.json', {'derived': op['derived'], 'manual_metrics': op['manual_metrics'], 'feedback': op['feedback'], 'issues': op['issues']})
    an = ok(v.post('/operate/analyze'))
    r = an['recommendation']
    write('phase6_step2_recommendation.md', '\n'.join([f'# Recommendation: {r["recommendation"]}', '', *[f'- {x}' for x in r['reasons']], '', f'Caveat: {r["caveat"]}',
                                                       '', f'Thresholds: {json.dumps(r["thresholds"])}']))
    write('phase6_step3_proposal.json', an['proposal'])
    write('phase6_gate_operate.md', gate_md('Operate and learn gate', v.gate(6)))
    if an.get('proposal_id'):
        ap = ok(v.post(f'/operate/proposals/{an["proposal_id"]}/apply', {'approval_id': v.approve('apply_proposal', an['proposal_id'])}))
        p3 = v.gate(3)
        write('phase6_step4_applied_proposal.md', f'# Proposal applied after founder approval\n\nApplied as **{ap["applied"]}**. Earlier versions and decisions are kept unchanged.\n\n'
              f'The loop is back in Phase 3: Build is now `{p3["status"]}` ({p3["gate"]["outcome"]}): {" ".join(p3["gate"]["reasons"])} '
              'Phases 4-6 wait until the founder reviews and accepts the new version.')
    return v


async def pick_model(offline: bool):
    if not offline:
        st = await main.LLM.status()
        if st.get('ollama_reachable') and st.get('model_pulled'):
            return main.LLM, f'{main.LLM.model} via local Ollama'
    main.LLM = DemoStubModel()
    return main.LLM, DemoStubModel.model


def main_(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--offline', action='store_true', help='use the labelled offline stand-in even if Ollama is reachable')
    args = ap.parse_args(argv)
    model, model_label = asyncio.run(pick_model(args.offline))
    agent_log.RUN_TAG = 'demo_run'
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    with TestClient(main.app) as c:
        scenario_a(c)
        scenario_b(c)
        scenario_c(c)
    with conn() as db:
        entries = agent_log.entries(db, run_tag='demo_run')
    (ROOT / 'decision_log.json').write_text(json.dumps(entries, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    write('README.md', '\n'.join([
        '# outputs/', '', 'Generated by `python scripts/demo_run.py` from one run of the real pipeline on a fresh database. Do not edit by hand.', '',
        f'- Model used: **{model_label}**',
        '- Scenario A: weak evidence (scripted 0/20 demand-test result) -> Validate gate STOP; Build refused.',
        '- Scenario B: prohibited idea -> code safety screen stop.',
        '- Scenario C: study-space finder through all six phases; Validate said NEEDS_EVIDENCE, so Build made a DEMO-ONLY prototype.',
        '- Phases 5-6 are MOCKED / TEST MODE: simulated payments, test buyers, nothing published, sent, spent or signed.',
        '- IDs and timestamps differ between runs; the steps, gates and amounts do not.', '',
        '## Files', '', *[f'- `{n}`' for n in sorted(files_written)]]))
    print(f'model: {model_label}\nwrote {len(files_written)} files to outputs/ and {len(entries)} entries to decision_log.json')
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == '__main__':
    main_()

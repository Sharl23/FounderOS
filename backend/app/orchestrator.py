"""Workflow orchestrator for the six phases (Discover, Validate, Build, Commercial setup, Sell/deliver/get paid,
Operate and learn), plus the HTTP endpoints for phases 3-6, approvals and the agent log.

State machine: a phase is LOCKED until the previous gate is GO (or DEMO_ONLY for Build). Transitions into
Build, acceptance of a prototype, adoption of a commercial plan, the sales-page draft, the TEST MODE checkout,
refunds and revision proposals all need a founder approval consumed server-side (approval.consume).
Agents run in a fixed order and pass typed outputs on:
  Product Architect (spec + stories) -> Website Builder (files) -> QA (checks) -> founder accept
  -> Commercial (unit economics) -> founder adopt -> Sales & Delivery (offer, draft page) -> founder approve
  -> checkout / mock payment / webhook / delivery / refund / reconcile -> Operations Analyst -> proposal -> founder
"""
from __future__ import annotations
import io
import json
import secrets
import uuid
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, HTMLResponse
from pydantic import BaseModel, Field

from .db import conn, now, qone, qall
from .criteria import stable_hash
from . import approval, gates, payments, refunds, agent_log
from .agents import product_architect, website_builder, qa, revision, commercial, sales_delivery, operations
from .main import authorize, not_stopped, latest_brief, latest_run, jsonstr

router = APIRouter()
PREVIEW_CSP = ("sandbox allow-scripts; default-src 'none'; script-src 'self'; style-src 'self'; img-src data:; "
               "connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'")
TEST_BANNER = 'MOCKED / TEST MODE'


def _log(db, pid, agent, action, **kw):
    agent_log.record(db, pid, agent, action, **kw)


def _gate_log(db, pid, g):
    _log(db, pid, 'gate', f'phase{g["phase"]}_gate', outcome=g['outcome'].lower(), detail={'reasons': g.get('reasons')})


# ----------------------------------------------------------------------------- workflow state
INPUTS = {1: 'Your idea, confirmed brief fields, safety screen', 2: 'Approved Discover run, research sources, locked demand tests',
          3: 'Validate gate result (GO or DEMO-ONLY) and founder approval', 4: 'Accepted prototype version, price and cost assumptions',
          5: 'Adopted commercial plan, approved sales-page draft, TEST MODE checkout', 6: 'Recorded MOCKED orders/events, manual or demo metrics, feedback'}
AGENTS = {1: ['Brief refiner (LLM)', 'Safety agent (rules)', 'Discovery agent (LLM)', 'Gate (D09, code)'],
          2: ['Research agent (providers + verifier)', 'Evidence review (code)', 'Check judges (LLM, validated)', 'Validation agent (LLM) + verdict (code)'],
          3: ['Product Architect (template)', 'Website Builder (template)', 'QA agent (static checks)', 'Revision agent (rules)'],
          4: ['Commercial agent (calculator)'], 5: ['Sales & Delivery agent (template)', 'Mock payment simulator', 'Webhook / delivery / refunds / reconcile (code)'],
          6: ['Operations Analyst (rules)', 'Gate (code)']}


def ops_snapshot(db, pid) -> dict:
    orders = qall(db, 'SELECT * FROM orders WHERE project_id=?', (pid,))
    events = qall(db, 'SELECT * FROM payment_events WHERE project_id=?', (pid,))
    ents = qall(db, 'SELECT * FROM entitlements WHERE project_id=?', (pid,))
    d = operations.derived(orders, events, ents)
    d['metrics']['duplicate_events_ignored'] = qone(db, "SELECT COUNT(*) n FROM agent_actions WHERE project_id=? AND action='process_payment_event' AND outcome='duplicate_ignored'", (pid,))['n']
    manual = qall(db, 'SELECT * FROM op_metrics WHERE project_id=? ORDER BY created_at', (pid,))
    fb = qall(db, 'SELECT * FROM feedback WHERE project_id=? ORDER BY created_at', (pid,))
    for f in fb:
        f['sentiment'] = operations.sentiment(f['text'])
    issues = qall(db, 'SELECT * FROM op_issues WHERE project_id=? ORDER BY created_at', (pid,))
    run = latest_run(db, pid, 'validate')
    exps = []
    for x in qall(db, 'SELECT * FROM experiments WHERE project_id=?', (pid,)):
        x['id'] = x['series_id']
        p = json.loads(x['payload_json'])
        o = next((o for o in ((run or {}).get('gate') or {}).get('experiment_outcomes') or [] if o['experiment_id'] == x['id']), None)
        exps.append({'id': x['id'], 'version': x['version'], 'hypothesis': p.get('hypothesis'), 'critical': p.get('critical'), 'simulated': p.get('simulated'),
                     'reading': {'PASS': 'HIT', 'FAIL': 'CLEAR_MISS', 'NEAR_MISS': 'NEAR_MISS', 'INCONCLUSIVE': 'TOO_LITTLE_DATA'}.get((o or {}).get('outcome')),
                     'rate_pct': (o or {}).get('rate_pct'), 'threshold_pct': p.get('success_threshold_pct')})
    rec = operations.recommend(d, manual, fb, issues, exps)
    return {'derived': d, 'manual_metrics': manual, 'feedback': fb, 'issues': issues, 'experiments': exps, 'recommendation': rec,
            'proposals': [dict(p, change=json.loads(p['change_json']), basis=json.loads(p['basis_json'])) for p in qall(db, 'SELECT * FROM proposals WHERE project_id=? ORDER BY created_at DESC', (pid,))]}


def workflow(db, pid) -> dict:
    ops = ops_snapshot(db, pid)
    gs = gates.all_gates(db, pid, ops['recommendation'] if gates.gate5_sell(db, pid)['outcome'] == 'GO' else None)
    phases = []
    prev_ok = True
    for i, g in enumerate(gs, 1):
        open_ = prev_ok
        status = 'LOCKED' if not open_ else ('GATE_PASSED' if g['outcome'] == 'GO' else 'DEMO_ONLY_ALLOWED' if g['outcome'] == 'DEMO_ONLY'
                                             else 'STOPPED' if g['outcome'] == 'STOP' else 'PIVOT' if g['outcome'] == 'PIVOT' else 'IN_PROGRESS')
        if i == 3 and g['outcome'] == 'GO':
            status = 'GATE_PASSED (' + ('DEMO-ONLY' if g.get('mode') == 'DEMO_ONLY' else 'MVP') + ')'
        pending = [a for a in approval.history(db, pid) if a['status'] == 'PENDING']
        phases.append({'phase': i, 'id': gates.PHASES[i - 1], 'name': gates.PHASE_NAMES[i - 1], 'status': status, 'gate': g, 'inputs': INPUTS[i],
                       'agents': AGENTS[i], 'next_action': _next(i, g, open_)})
        prev_ok = open_ and g['outcome'] in ('GO', 'DEMO_ONLY') and (i != 2 or entered_phase(db, pid, 3))
        if i == 2 and g['outcome'] in ('GO', 'DEMO_ONLY') and not entered_phase(db, pid, 3):
            prev_ok = False
    return {'phases': phases, 'pending_approvals': [a for a in approval.history(db, pid) if a['status'] == 'PENDING'],
            'mode_notice': 'Phases 3-6 run in MOCKED / TEST MODE: demo data, simulated payments, nothing published, sent, spent or signed.'}


def entered_phase(db, pid, phase):
    return bool(gates.entered(db, pid, phase))


def _next(i, g, open_):
    if not open_:
        return 'Locked until the previous gate passes.'
    o = g['outcome']
    if i == 2 and o == 'DEMO_ONLY':
        return 'Request approval for a DEMO-ONLY prototype (Build Studio).'
    if g.get('approval_action'):
        return f'Founder approval needed: {approval.ACTIONS[g["approval_action"]][3]}'
    return {'GO': 'Gate passed: continue to the next phase.', 'STOP': 'Stop: the gate recommends not continuing.', 'PIVOT': 'Pivot: revise the idea in Discover.',
            'BLOCKED': ' '.join(g['reasons'])}.get(o, ' '.join(g['reasons']))


@router.get('/api/projects/{pid}/workflow')
async def get_workflow(pid: str, project=Depends(authorize)):
    with conn() as db:
        return workflow(db, pid)


# ----------------------------------------------------------------------------- approvals
class ApprovalRequest(BaseModel):
    action: str = Field(max_length=40)
    target: str | None = Field(default=None, max_length=80)


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern='^(APPROVE|REJECT)$')
    note: str | None = Field(default=None, max_length=600)
    confirm: bool = False


def current_payload(db, pid, action, target):
    if action in ('enter_build', 'enter_build_demo_only'):
        g = gates.gate2_validate(db, pid)
        if g.get('approval_action') != action:
            raise HTTPException(409, {'code': 'GATE_NOT_OPEN', 'message': f'Validate gate is {g["outcome"]}: ' + ' '.join(g['reasons'])})
        return g['payload']
    if action == 'accept_build':
        g = gates.gate3_build(db, pid)
        if not g.get('payload') or g['payload']['qa_status'] != 'PASS':
            raise HTTPException(409, {'code': 'GATE_NOT_OPEN', 'message': ' '.join(g['reasons'])})
        return g['payload']
    if action == 'activate_commercial':
        g = gates.gate4_commercial(db, pid)
        if g['outcome'] in ('BLOCKED', 'STOP') or not g.get('payload'):
            raise HTTPException(409, {'code': 'GATE_NOT_OPEN', 'message': ' '.join(g['reasons'])})
        return g['payload']
    if action in ('approve_sales_page', 'open_test_checkout'):
        o = qone(db, 'SELECT * FROM offers WHERE id=? AND project_id=?', (target, pid))
        if not o:
            raise HTTPException(404, 'Offer not found for this venture')
        if gates.gate4_commercial(db, pid)['outcome'] != 'GO':
            raise HTTPException(409, {'code': 'GATE_NOT_OPEN', 'message': 'Adopt the commercial plan first.'})
        if action == 'open_test_checkout' and o['status'] != 'APPROVED_DRAFT':
            raise HTTPException(409, {'code': 'GATE_NOT_OPEN', 'message': 'Approve the sales-page draft first.'})
        return {'offer_id': o['id'], 'offer_hash': o['offer_hash'], 'mode': TEST_BANNER}
    if action == 'refund_order':
        o = qone(db, 'SELECT * FROM orders WHERE id=? AND project_id=?', (target, pid))
        if not o:
            raise HTTPException(404, 'Order not found for this venture')
        return refunds.refund_payload(o)
    if action == 'apply_proposal':
        p = qone(db, 'SELECT * FROM proposals WHERE id=? AND project_id=?', (target, pid))
        if not p:
            raise HTTPException(404, 'Proposal not found for this venture')
        return {'proposal_id': p['id'], 'change_hash': stable_hash(p['change_json']), 'status': p['status']}
    raise HTTPException(422, f'Unknown action {action}')


@router.post('/api/projects/{pid}/approvals')
async def request_approval(pid: str, req: ApprovalRequest, project=Depends(authorize)):
    not_stopped(project)
    with conn() as db:
        if req.action in approval.NEVER:
            _log(db, pid, 'approval', f'refused_{req.action}', outcome='refused')
            raise HTTPException(403, f'{req.action} is never performed by FounderOS, with or without approval.')
        payload = current_payload(db, pid, req.action, req.target)
        a = approval.request(db, pid, req.action, payload, req.target)
        _log(db, pid, 'approval', f'request_{req.action}', outcome='pending', detail={'approval_id': a['id']})
    return a


@router.post('/api/projects/{pid}/approvals/{aid}/decide')
async def decide_approval(pid: str, aid: str, req: ApprovalDecision, project=Depends(authorize)):
    if req.decision == 'APPROVE' and not req.confirm:
        raise HTTPException(422, 'Tick the confirmation to approve.')
    with conn() as db:
        a = approval.decide(db, pid, aid, req.decision, req.note)
        _log(db, pid, 'founder', f'{req.decision.lower()}_{a["action"]}', approved_by='founder' if req.decision == 'APPROVE' else None,
             outcome=a['status'].lower(), detail={'approval_id': aid})
    return a


@router.get('/api/projects/{pid}/approvals')
async def list_approvals(pid: str, project=Depends(authorize)):
    with conn() as db:
        return {'approvals': approval.history(db, pid),
                'events': qall(db, 'SELECT * FROM approval_events WHERE project_id=? ORDER BY id DESC LIMIT 200', (pid,))}


# ----------------------------------------------------------------------------- Phase 3: Build Studio
class BuildStart(BaseModel):
    approval_id: str


class BuildRevise(BaseModel):
    feedback: str = Field(min_length=3, max_length=2000)


def _spec_inputs(db, pid, project):
    brief = latest_brief(db, pid)
    disc = latest_run(db, pid, 'discover')
    val = latest_run(db, pid, 'validate')
    b = dict(brief['payload'], original_idea_text=project['original_idea'])
    return b, disc and disc['report'], val and val['gate'].get('verdict')


def _store_build(db, pid, spec, mode, parent, feedback, changes, approval_id):
    v = (qone(db, 'SELECT MAX(version) v FROM builds WHERE project_id=?', (pid,))['v'] or 0) + 1
    files = website_builder.build(spec, seed=int(stable_hash([pid, v])[:8], 16))
    check = qa.check(spec, files)
    db.execute('INSERT INTO builds(id,project_id,version,mode,parent_version,spec_json,files_json,qa_json,feedback,changes_json,spec_hash,files_hash,preview_key,approval_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (uuid.uuid4().hex, pid, v, mode, parent, jsonstr(spec), jsonstr(files), jsonstr(check), feedback, jsonstr(changes), stable_hash(spec),
                stable_hash(files), secrets.token_urlsafe(18), approval_id, now()))
    _log(db, pid, 'product_architect', 'write_spec_and_user_stories', outcome=f'{spec["archetype"]}, {len(spec["user_stories"])} stories', detail={'build_version': v})
    _log(db, pid, 'website_builder', 'generate_website_files', outcome=f'v{v}: ' + ', '.join(files), detail={'mode': mode})
    _log(db, pid, 'qa', 'check_generated_site', outcome=check['status'].lower(), detail={'failed': [i['id'] for i in check['items'] if not i['ok']]})
    return v, check


@router.post('/api/projects/{pid}/build')
async def start_build(pid: str, req: BuildStart, project=Depends(authorize)):
    not_stopped(project)
    with conn() as db:
        g = gates.gate2_validate(db, pid)
        _gate_log(db, pid, g)
        if g['outcome'] not in ('GO', 'DEMO_ONLY'):
            raise HTTPException(409, {'code': 'GATE_' + g['outcome'], 'message': ' '.join(g['reasons'])})
        a = approval.consume(db, pid, req.approval_id, g['approval_action'], g['payload'])
        mode = 'MVP' if g['outcome'] == 'GO' else 'DEMO_ONLY'
        db.execute('INSERT INTO phase_transitions(id,project_id,phase,outcome,gate_json,approval_id,created_at) VALUES(?,?,?,?,?,?,?)',
                   (uuid.uuid4().hex, pid, 3, mode, jsonstr(g), a['id'], now()))
        _log(db, pid, 'orchestrator', 'enter_phase3_build', approved_by='founder', outcome=mode.lower())
        b, disc, verdict = _spec_inputs(db, pid, project)
        spec = product_architect.spec(b, disc, verdict, mode)
        v, check = _store_build(db, pid, spec, mode, None, None, [], a['id'])
    return {'version': v, 'mode': mode, 'qa': check, 'spec': spec}


def _build_allowed(db, pid):
    t = gates.entered(db, pid, 3)
    if not t:
        raise HTTPException(403, {'code': 'APPROVAL_REQUIRED', 'message': 'Build has not been entered with a founder approval.'})
    g = gates.gate2_validate(db, pid)
    if g['outcome'] not in ('GO', 'DEMO_ONLY') or g['payload'] != json.loads(t['gate_json']).get('payload'):
        raise HTTPException(409, {'code': 'APPROVAL_STALE', 'message': 'The validation inputs changed since Build was approved. Request a new Build approval.'})
    return t


@router.post('/api/projects/{pid}/build/revise')
async def revise_build(pid: str, req: BuildRevise, project=Depends(authorize)):
    not_stopped(project)
    with conn() as db:
        t = _build_allowed(db, pid)
        cur = gates.latest_build(db, pid)
        if not cur:
            raise HTTPException(409, 'Generate the first prototype first.')
        overrides, changes = revision.parse(req.feedback, cur['spec'])
        b, disc, verdict = _spec_inputs(db, pid, project)
        spec = product_architect.spec(b, disc, verdict, cur['mode'], overrides)
        _log(db, pid, 'revision', 'parse_founder_feedback', outcome=f'{sum(c["applied"] for c in changes)} applied, {sum(not c["applied"] for c in changes)} not applied')
        v, check = _store_build(db, pid, spec, cur['mode'], cur['version'], req.feedback, changes, t['approval_id'])
    return {'version': v, 'qa': check, 'changes': changes}


@router.get('/api/projects/{pid}/build')
async def get_build(pid: str, project=Depends(authorize)):
    with conn() as db:
        rows = qall(db, 'SELECT version, mode, parent_version, feedback, changes_json, qa_json, files_hash, created_at FROM builds WHERE project_id=? ORDER BY version DESC', (pid,))
        latest = gates.latest_build(db, pid)
        g2, g3 = gates.gate2_validate(db, pid), gates.gate3_build(db, pid)
    for r in rows:
        r['changes'] = json.loads(r.pop('changes_json') or '[]')
        r['qa_status'] = json.loads(r.pop('qa_json'))['status']
    if latest:
        latest['preview_url'] = f'/preview/{pid}/{latest["version"]}/{latest["preview_key"]}/index.html'
        latest['file_sizes'] = {k: len(v.encode()) for k, v in latest['files'].items()}
    return {'validate_gate': g2, 'build_gate': g3, 'latest': latest, 'versions': rows}


@router.get('/api/projects/{pid}/build/{version}/export.zip')
async def export_build(pid: str, version: int, project=Depends(authorize)):
    with conn() as db:
        b = qone(db, 'SELECT * FROM builds WHERE project_id=? AND version=?', (pid, version))
        if not b:
            raise HTTPException(404, 'No such build version')
        _log(db, pid, 'website_builder', 'export_zip', outcome=f'v{version}')
    files = json.loads(b['files_json'])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in website_builder.FILES:
            z.writestr(f'prototype-v{version}/{name}', files[name])
    return Response(buf.getvalue(), media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="prototype-v{version}.zip"'})


MEDIA = {'index.html': 'text/html; charset=utf-8', 'styles.css': 'text/css; charset=utf-8', 'app.js': 'text/javascript; charset=utf-8', 'README.txt': 'text/plain; charset=utf-8'}


@router.get('/preview/{pid}/{version}/{key}/{name}')
async def preview(pid: str, version: int, key: str, name: str):
    """Isolated static preview. Only the four generated file names are served (no paths); CSP sandbox gives an opaque origin,
    no network, no forms, no access to FounderOS. Nothing is executed on the server."""
    if name not in MEDIA:
        raise HTTPException(404, 'Not a prototype file')
    with conn() as db:
        b = qone(db, 'SELECT files_json, preview_key FROM builds WHERE project_id=? AND version=?', (pid, version))
    if not b or not secrets.compare_digest(b['preview_key'], key):
        raise HTTPException(404, 'Preview not found')
    return Response(json.loads(b['files_json'])[name], media_type=MEDIA[name],
                    headers={'Content-Security-Policy': PREVIEW_CSP, 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                             'Cache-Control': 'no-store',
                             # the sandboxed iframe has an opaque origin, so its own CSS/JS requests are cross-origin by definition
                             'Cross-Origin-Resource-Policy': 'cross-origin'})


# ----------------------------------------------------------------------------- Phase 4: Commercial setup
@router.post('/api/projects/{pid}/commercial')
async def save_commercial(pid: str, req: commercial.CommercialInputs, project=Depends(authorize)):
    not_stopped(project)
    with conn() as db:
        g3 = gates.gate3_build(db, pid)
        if g3['outcome'] != 'GO':
            raise HTTPException(409, {'code': 'GATE_' + g3['outcome'], 'message': 'Accept a prototype version first: ' + ' '.join(g3['reasons'])})
        b = latest_brief(db, pid)
        res = commercial.plan(req, b['payload'])
        v = (qone(db, 'SELECT MAX(version) v FROM commercial_plans WHERE project_id=?', (pid,))['v'] or 0) + 1
        h = stable_hash([req.model_dump(), res])
        db.execute('INSERT INTO commercial_plans(id,project_id,version,inputs_json,results_json,plan_hash,created_at) VALUES(?,?,?,?,?,?,?)',
                   (uuid.uuid4().hex, pid, v, jsonstr(req.model_dump()), jsonstr(res), h, now()))
        _log(db, pid, 'commercial', 'calculate_unit_economics', outcome=f'contribution {res["unit_economics"]["contribution_per_sale"]} per sale, break-even {res["unit_economics"]["break_even_sales_per_month"]}/month')
        g4 = gates.gate4_commercial(db, pid)
        _gate_log(db, pid, g4)
    return {'version': v, 'plan': res, 'gate': g4}


@router.get('/api/projects/{pid}/commercial')
async def get_commercial(pid: str, project=Depends(authorize)):
    with conn() as db:
        return {'latest': gates.latest_plan(db, pid), 'gate': gates.gate4_commercial(db, pid), 'build_gate': gates.gate3_build(db, pid)}


class Activate(BaseModel):
    approval_id: str


def _apply_approval(db, pid, approval_id, action, target=None):
    payload = current_payload(db, pid, action, target)
    a = approval.consume(db, pid, approval_id, action, payload, target)
    _log(db, pid, 'orchestrator', f'execute_{action}', approved_by='founder', outcome='done')
    return a


@router.post('/api/projects/{pid}/build/accept')
async def accept_build(pid: str, req: Activate, project=Depends(authorize)):
    with conn() as db:
        _apply_approval(db, pid, req.approval_id, 'accept_build')
        g = gates.gate3_build(db, pid)
        _gate_log(db, pid, g)
    return {'gate': g}


@router.post('/api/projects/{pid}/commercial/activate')
async def activate_commercial(pid: str, req: Activate, project=Depends(authorize)):
    with conn() as db:
        _apply_approval(db, pid, req.approval_id, 'activate_commercial')
        g = gates.gate4_commercial(db, pid)
        _gate_log(db, pid, g)
    return {'gate': g}


# ----------------------------------------------------------------------------- Phase 5: Sell / deliver / get paid
class OfferCreate(BaseModel):
    package_index: int = Field(default=0, ge=0, le=3)


@router.post('/api/projects/{pid}/sell/offers')
async def create_offer(pid: str, req: OfferCreate, project=Depends(authorize)):
    not_stopped(project)
    with conn() as db:
        g4 = gates.gate4_commercial(db, pid)
        if g4['outcome'] != 'GO':
            raise HTTPException(409, {'code': 'GATE_' + g4['outcome'], 'message': 'Adopt a commercial plan first.'})
        p = gates.latest_plan(db, pid)
        b = gates.latest_build(db, pid)
        o = sales_delivery.offer(b and b['spec'], p['results'], req.package_index)
        page = sales_delivery.sales_page(o, b and b['spec'])
        bad = sales_delivery.check_page(page)
        if bad:
            raise HTTPException(422, f'Sales-page draft failed the honesty check: {bad}')
        v = (qone(db, 'SELECT MAX(version) v FROM offers WHERE project_id=?', (pid,))['v'] or 0) + 1
        oid = uuid.uuid4().hex
        db.execute('INSERT INTO offers(id,project_id,version,commercial_version,build_version,package_json,sales_page_html,offer_hash,status,checkout_open,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,0,?,?)',
                   (oid, pid, v, p['version'], b and b['version'], jsonstr(o), page, stable_hash([o, page]), 'DRAFT', now(), now()))
        _log(db, pid, 'sales_delivery', 'draft_offer_and_sales_page', outcome=f'offer v{v} DRAFT ({o["price"]} {o["currency"]})')
    return {'offer_id': oid, 'version': v, 'offer': o, 'sales_page_html': page, 'status': 'DRAFT', 'honesty_check': 'PASS'}


class OfferApproval(BaseModel):
    approval_id: str


@router.post('/api/projects/{pid}/sell/offers/{oid}/approve-page')
async def approve_page(pid: str, oid: str, req: OfferApproval, project=Depends(authorize)):
    with conn() as db:
        _apply_approval(db, pid, req.approval_id, 'approve_sales_page', oid)
        db.execute("UPDATE offers SET status='APPROVED_DRAFT', updated_at=? WHERE id=?", (now(), oid))
    return {'status': 'APPROVED_DRAFT', 'published': False, 'note': 'Approved as a draft. FounderOS has no publishing code; nothing was posted anywhere.'}


@router.post('/api/projects/{pid}/sell/offers/{oid}/open-checkout')
async def open_checkout(pid: str, oid: str, req: OfferApproval, project=Depends(authorize)):
    with conn() as db:
        _apply_approval(db, pid, req.approval_id, 'open_test_checkout', oid)
        db.execute('UPDATE offers SET checkout_open=1, updated_at=? WHERE id=?', (now(), oid))
    return {'checkout_open': True, 'mode': TEST_BANNER}


class CheckoutReq(BaseModel):
    offer_id: str
    buyer_ref: str = Field(min_length=3, max_length=40, pattern=r'^[A-Za-z0-9_\-]+$')
    idempotency_key: str = Field(min_length=8, max_length=80)

    model_config = {'extra': 'allow'}


def _fees(db, pid):
    p = gates.latest_plan(db, pid)
    return {'pct': p['inputs']['payment_fee_pct'], 'fixed': p['inputs']['payment_fee_fixed']}


@router.post('/api/projects/{pid}/sell/checkout')
async def checkout(pid: str, req: CheckoutReq, project=Depends(authorize)):
    payments.no_payment_data(req.model_dump())
    with conn() as db:
        offer = qone(db, 'SELECT * FROM offers WHERE id=? AND project_id=?', (req.offer_id, pid))
        if not offer:
            raise HTTPException(404, 'Offer not found for this venture')
        order, created = payments.checkout(db, pid, offer, req.buyer_ref, req.idempotency_key)
        _log(db, pid, 'sales_delivery', 'create_test_checkout_order', outcome='created' if created else 'idempotent_replay', detail={'order_id': order['id']})
    return {'order': order, 'created': created, 'mode': TEST_BANNER}


class MockPay(BaseModel):
    order_id: str
    event_id: str | None = Field(default=None, max_length=60, pattern=r'^evt_test_[A-Za-z0-9]+$')


@router.post('/api/projects/{pid}/sell/mock-pay')
async def mock_pay(pid: str, req: MockPay, project=Depends(authorize)):
    """The built-in TEST MODE simulator plays the payment provider: it signs a payment_succeeded event and delivers it to the webhook."""
    with conn() as db:
        o = qone(db, 'SELECT * FROM orders WHERE id=? AND project_id=?', (req.order_id, pid))
        if not o:
            raise HTTPException(404, 'Order not found for this venture')
        ev = payments.make_event(db, pid, 'payment_succeeded', o, req.event_id)
        res = payments.handle_event(db, pid, ev['event'], ev['signature'], _fees(db, pid))
        _log(db, pid, 'payments', 'process_payment_event', outcome=res['result'].lower(), detail={'event_id': ev['event']['event_id']})
        ent = qone(db, 'SELECT token, status FROM entitlements WHERE order_id=?', (o['id'],))
    return {'event': ev['event'], 'signature': ev['signature'], **res, 'access': ent and {'status': ent['status'], 'url': f'/deliver/{ent["token"]}'}, 'mode': TEST_BANNER}


class WebhookIn(BaseModel):
    event: dict
    signature: str


@router.post('/api/projects/{pid}/sell/webhook')
async def webhook(pid: str, req: WebhookIn):
    """Webhook endpoint (signature-authenticated, like a provider callback). Replaying an event is a no-op."""
    with conn() as db:
        res = payments.handle_event(db, pid, req.event, req.signature, _fees(db, pid))
        _log(db, pid, 'payments', 'process_payment_event', outcome=res['result'].lower(), detail={'event_id': req.event.get('event_id')})
    return res


class RefundReq(BaseModel):
    approval_id: str | None = None


@router.post('/api/projects/{pid}/sell/orders/{oid}/refund')
async def refund(pid: str, oid: str, req: RefundReq, project=Depends(authorize)):
    with conn() as db:
        res = refunds.refund(db, pid, oid, req.approval_id, _fees(db, pid))
        _log(db, pid, 'payments', 'refund_and_revoke', approved_by='founder', outcome=res['result'].lower(), detail={'order_id': oid})
    return {**res, 'mode': TEST_BANNER}


@router.get('/deliver/{token}')
async def deliver(token: str):
    """Digital delivery: an access link that works only while the entitlement is ACTIVE (paid, not refunded)."""
    with conn() as db:
        ent = payments.access(db, token)
        o = qone(db, 'SELECT * FROM orders WHERE id=?', (ent['order_id'],))
        offer = qone(db, 'SELECT * FROM offers WHERE id=?', (o['offer_id'],))
        b = qone(db, 'SELECT version, preview_key FROM builds WHERE project_id=? AND version=?', (o['project_id'], offer['build_version'])) if offer['build_version'] else None
        _log(db, o['project_id'], 'delivery', 'serve_access_link', outcome='delivered', detail={'order_id': o['id']})
    link = f'/preview/{o["project_id"]}/{b["version"]}/{b["preview_key"]}/index.html' if b else None
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Your access (MOCKED / TEST MODE)</title></head><body style="font-family:system-ui;max-width:640px;margin:40px auto">
<p><strong>MOCKED / TEST MODE purchase.</strong> No real money moved.</p><h1>Access granted</h1>
<p>Order <code>{o['id'][:8]}</code> for buyer <code>{o['buyer_ref']}</code>.</p>{f'<p><a href="{link}">Open the prototype</a></p>' if link else ''}
<p>This link stops working if the payment is refunded.</p></body></html>""", headers={'Cache-Control': 'no-store'})


@router.get('/api/projects/{pid}/sell')
async def sell_state(pid: str, project=Depends(authorize)):
    with conn() as db:
        offers = qall(db, 'SELECT * FROM offers WHERE project_id=? ORDER BY version DESC', (pid,))
        for o in offers:
            o['offer'] = json.loads(o.pop('package_json'))
        orders = qall(db, 'SELECT * FROM orders WHERE project_id=? ORDER BY created_at DESC', (pid,))
        ents = {e['order_id']: e for e in qall(db, 'SELECT * FROM entitlements WHERE project_id=?', (pid,))}
        for o in orders:
            e = ents.get(o['id'])
            o['access'] = e and {'status': e['status'], 'url': f'/deliver/{e["token"]}', 'deliveries': e['deliveries']}
        events = qall(db, 'SELECT * FROM payment_events WHERE project_id=? ORDER BY received_at DESC', (pid,))
        return {'mode': TEST_BANNER, 'offers': offers, 'orders': orders, 'events': events, 'reconciliation': payments.reconcile(db, pid),
                'gate': gates.gate5_sell(db, pid), 'commercial_gate': gates.gate4_commercial(db, pid)}


@router.post('/api/projects/{pid}/sell/reconcile')
async def run_reconcile(pid: str, project=Depends(authorize)):
    with conn() as db:
        r = payments.reconcile(db, pid)
        db.execute('INSERT INTO reconciliations(id,project_id,result_json,ok,created_at) VALUES(?,?,?,?,?)', (uuid.uuid4().hex, pid, jsonstr(r), int(r['ok']), now()))
        _log(db, pid, 'reconcile', 'reconcile_orders_payments_fees_payouts', outcome='ok' if r['ok'] else f'{len(r["issues"])} issue(s)')
        g = gates.gate5_sell(db, pid)
        _gate_log(db, pid, g)
    return {**r, 'gate': g}


# ----------------------------------------------------------------------------- Phase 6: Operate and learn
class MetricIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    value: float
    period: str = Field(min_length=2, max_length=40)
    source: str = Field(pattern='^(MANUAL|MOCK_DEMO)$')
    note: str | None = Field(default=None, max_length=300)


class FeedbackIn(BaseModel):
    text: str = Field(min_length=3, max_length=1000)
    source: str = Field(pattern='^(FOUNDER_INTERVIEW|SUPPORT_MESSAGE|MOCK_DEMO)$')
    provenance: str = Field(min_length=3, max_length=300)
    order_id: str | None = None


class IssueIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    severity: str = Field(pattern='^(LOW|MEDIUM|HIGH)$')


@router.post('/api/projects/{pid}/operate/metrics')
async def add_metric(pid: str, req: MetricIn, project=Depends(authorize)):
    with conn() as db:
        db.execute('INSERT INTO op_metrics(id,project_id,name,value,period,source,note,created_at) VALUES(?,?,?,?,?,?,?,?)',
                   (uuid.uuid4().hex, pid, req.name, req.value, req.period, req.source, req.note, now()))
        _log(db, pid, 'operations', 'record_metric', outcome=req.source.lower())
    return {'ok': True}


@router.post('/api/projects/{pid}/operate/feedback')
async def add_feedback(pid: str, req: FeedbackIn, project=Depends(authorize)):
    with conn() as db:
        if req.order_id and not qone(db, 'SELECT 1 FROM orders WHERE id=? AND project_id=?', (req.order_id, pid)):
            raise HTTPException(404, 'Order not found for this venture')
        db.execute('INSERT INTO feedback(id,project_id,text,source,provenance,order_id,created_at) VALUES(?,?,?,?,?,?,?)',
                   (uuid.uuid4().hex, pid, req.text, req.source, req.provenance, req.order_id, now()))
        _log(db, pid, 'operations', 'ingest_feedback', outcome=operations.sentiment(req.text).lower(), detail={'source': req.source})
    return {'ok': True, 'sentiment': operations.sentiment(req.text)}


@router.post('/api/projects/{pid}/operate/issues')
async def add_issue(pid: str, req: IssueIn, project=Depends(authorize)):
    with conn() as db:
        iid = uuid.uuid4().hex
        db.execute("INSERT INTO op_issues(id,project_id,title,severity,status,created_at,updated_at) VALUES(?,?,?,?,'OPEN',?,?)", (iid, pid, req.title, req.severity, now(), now()))
    return {'id': iid}


@router.post('/api/projects/{pid}/operate/issues/{iid}/close')
async def close_issue(pid: str, iid: str, project=Depends(authorize)):
    with conn() as db:
        db.execute("UPDATE op_issues SET status='CLOSED', updated_at=? WHERE id=? AND project_id=?", (now(), iid, pid))
    return {'ok': True}


@router.get('/api/projects/{pid}/operate')
async def operate_state(pid: str, project=Depends(authorize)):
    with conn() as db:
        s = ops_snapshot(db, pid)
        s['gate'] = gates.gate6_operate(db, pid, s['recommendation'])
    return s


@router.post('/api/projects/{pid}/operate/analyze')
async def analyze(pid: str, project=Depends(authorize)):
    """Operations Analyst: metrics from recorded events -> recommendation -> (if warranted) a revision proposal awaiting founder approval."""
    with conn() as db:
        s = ops_snapshot(db, pid)
        g = gates.gate6_operate(db, pid, s['recommendation'])
        _log(db, pid, 'operations', 'analyze_recorded_events', outcome=s['recommendation']['recommendation'].lower(),
             detail={'paid': s['derived']['metrics']['orders_paid']})
        _gate_log(db, pid, g)
        prop = operations.proposal_from(s['recommendation'], s['feedback'])
        pid_ = None
        if prop:
            pid_ = uuid.uuid4().hex
            db.execute('INSERT INTO proposals(id,project_id,target_phase,rationale,change_json,basis_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                       (pid_, pid, prop['target_phase'], prop['rationale'], jsonstr(prop['change']), jsonstr({'metrics': s['derived']['metrics'], 'recommendation': s['recommendation']}),
                        'PROPOSED', now(), now()))
            _log(db, pid, 'operations', f'propose_phase{prop["target_phase"]}_revision', outcome='proposed')
    return {'recommendation': s['recommendation'], 'gate': g, 'proposal_id': pid_, 'proposal': prop}


class ApplyProposal(BaseModel):
    approval_id: str


@router.post('/api/projects/{pid}/operate/proposals/{prop_id}/apply')
async def apply_proposal(pid: str, prop_id: str, req: ApplyProposal, project=Depends(authorize)):
    """Applies a proposal as a NEW version (brief version or prototype version). Earlier versions and decisions are kept."""
    not_stopped(project)
    with conn() as db:
        p = qone(db, 'SELECT * FROM proposals WHERE id=? AND project_id=?', (prop_id, pid))
        if not p or p['status'] != 'PROPOSED':
            raise HTTPException(409, 'Proposal is not open')
        _apply_approval(db, pid, req.approval_id, 'apply_proposal', prop_id)
        change = json.loads(p['change_json'])
        if p['target_phase'] == 3:
            cur = gates.latest_build(db, pid)
            overrides, changes = revision.parse('\n'.join(change['feedback_commands']), cur['spec'])
            b, disc, verdict = _spec_inputs(db, pid, project)
            spec = product_architect.spec(b, disc, verdict, cur['mode'], overrides)
            v, _ = _store_build(db, pid, spec, cur['mode'], cur['version'], 'Operate & Learn proposal ' + prop_id[:8], changes, req.approval_id)
            ref = f'build v{v}'
        else:
            brief = latest_brief(db, pid)
            payload = dict(brief['payload'])
            prev = (payload.get('constraints') or '').strip()
            payload['founder_answers'] = dict(payload.get('founder_answers') or {}, constraints=(prev + ' | ' if prev else '') + change['constraints'])
            from . import brief_extract
            from .main import apply_fields, invalidate_runs, store_safety
            fields = brief_extract.merge(project['original_idea'], json.loads(project['intake_json']), payload['founder_answers'],
                                         model=payload.get('model_suggestions') or {}, previous=payload.get('fields'))
            apply_fields(payload, fields)
            v = brief['version'] + 1
            db.execute('INSERT INTO briefs(project_id,version,payload_json,created_at) VALUES(?,?,?,?)', (pid, v, jsonstr(payload), now()))
            invalidate_runs(db, pid, f'Operate & Learn proposal {prop_id[:8]} created brief v{v}')
            store_safety(db, pid, v, project, payload, keep_ack=False)
            ref = f'brief v{v}'
        db.execute("UPDATE proposals SET status='APPLIED', applied_ref=?, updated_at=? WHERE id=?", (ref, now(), prop_id))
        _log(db, pid, 'orchestrator', f'apply_phase{p["target_phase"]}_proposal', approved_by='founder', outcome=ref)
    return {'applied': ref}


# ----------------------------------------------------------------------------- agent log
@router.get('/api/projects/{pid}/agent-log')
async def get_agent_log(pid: str, project=Depends(authorize)):
    with conn() as db:
        return {'entries': agent_log.entries(db, pid)}

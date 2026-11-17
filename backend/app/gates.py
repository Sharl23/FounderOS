"""Phase gates for the six venture phases. Deterministic code only; the model never decides a gate.

Outcomes: GO (founder may approve the transition), DEMO_ONLY (Build only: a labelled demo prototype may be
approved although validation has not passed), REPEAT, PIVOT, STOP, BLOCKED (a precondition is missing).
Each gate returns the exact payload a founder approval is bound to; if that payload changes, the approval is stale.
"""
from __future__ import annotations
import json

from .db import qone, qall, unpack_run
from .decision import discovery_gate, evaluate_validation  # noqa: F401  (Discover/Validate gate logic, unchanged)

PHASES = ['discover', 'validate', 'build', 'commercial_setup', 'sell_deliver_get_paid', 'operate_learn']
PHASE_NAMES = ['Discover', 'Validate', 'Build', 'Commercial setup', 'Sell / deliver / get paid', 'Operate and learn']
ACTIVE_PHASES = ('discover', 'validate')   # phases whose runs go through /phases/{phase}/run (model agents)

STOP_VERDICTS = {'STOP_DO_NOT_LAUNCH': 'STOP', 'BLOCK_DO_NOT_LAUNCH': 'STOP', 'PIVOT': 'PIVOT'}
D09_TO_OUTCOME = {'GO_ON': 'GO', 'REPEAT': 'REPEAT', 'PIVOT': 'PIVOT', 'STOP': 'STOP', 'REVIEW_REQUIRED': 'REPEAT'}


def _latest_run(db, pid, phase):
    return unpack_run(qone(db, 'SELECT * FROM phase_runs WHERE project_id=? AND phase=? ORDER BY version DESC LIMIT 1', (pid, phase)))


def _brief_version(db, pid):
    r = qone(db, 'SELECT MAX(version) v FROM briefs WHERE project_id=?', (pid,))
    return r['v'] if r else None


def gate1_discover(db, pid) -> dict:
    run = _latest_run(db, pid, 'discover')
    bv = _brief_version(db, pid)
    ev = qone(db, 'SELECT payload_json FROM criteria_evaluations WHERE project_id=? AND phase=? ORDER BY version DESC LIMIT 1', (pid, 'discover'))
    exit_ = json.loads(ev['payload_json'])['exit'] if ev else None
    if not run:
        return {'phase': 1, 'outcome': 'BLOCKED', 'reasons': ['Run Discover first.'], 'd09_exit': None}
    if run['state'] == 'STOPPED':
        return {'phase': 1, 'outcome': 'STOP', 'reasons': ['The founder stopped this venture.'], 'd09_exit': exit_}
    if run['brief_version'] != bv or run['state'] == 'INVALIDATED':
        return {'phase': 1, 'outcome': 'REPEAT', 'reasons': ['The brief changed after the last Discover run. Run Discover again.'], 'd09_exit': exit_}
    if run['state'] != 'APPROVED':
        return {'phase': 1, 'outcome': D09_TO_OUTCOME.get(exit_, 'REPEAT') if exit_ else 'REPEAT',
                'reasons': [f'Discover gate (D09) says {exit_ or "not evaluated"}; the founder has not approved moving on.'], 'd09_exit': exit_}
    return {'phase': 1, 'outcome': 'GO', 'reasons': [f'Founder approved Discover (gate said {exit_ or "n/a"}) for research only.'], 'd09_exit': exit_}


def gate2_validate(db, pid) -> dict:
    """Validate -> Build. Production build only on CONTINUE_TESTING with every critical locked test HIT; DEMO_ONLY otherwise."""
    g1 = gate1_discover(db, pid)
    run = _latest_run(db, pid, 'validate')
    base = {'phase': 2, 'approval_action': None, 'payload': None}
    if g1['outcome'] != 'GO':
        return base | {'outcome': 'BLOCKED', 'reasons': ['Discover has not been approved on the current brief.']}
    if not run or run['state'] in ('INVALIDATED',):
        return base | {'outcome': 'BLOCKED', 'reasons': ['Run Validate on the current brief and evidence.']}
    verdict = run['gate'].get('verdict')
    payload = {'brief_version': _brief_version(db, pid), 'validate_run_id': run['id'], 'validate_run_version': run['version'], 'verdict': verdict}
    if verdict in STOP_VERDICTS:
        return base | {'outcome': STOP_VERDICTS[verdict], 'verdict': verdict, 'payload': payload,
                       'reasons': [f'Validation verdict {verdict}: the evidence argues against building. Build is blocked, including demos.']}
    if run['state'] != 'APPROVED':
        return base | {'outcome': 'REPEAT', 'verdict': verdict, 'payload': payload, 'reasons': [f'Validation verdict {verdict}; the founder has not approved this validation run.']}
    crit = [x for x in qall(db, 'SELECT * FROM experiments WHERE project_id=?', (pid,)) if json.loads(x['payload_json']).get('critical') and x['status'] == 'LOCKED'
            and not json.loads(x['payload_json']).get('simulated')]
    hits = [o for o in (run['gate'].get('experiment_outcomes') or []) if o.get('outcome') == 'PASS']
    if verdict == 'CONTINUE_TESTING' and crit and len(hits) >= len(crit):
        return base | {'outcome': 'GO', 'verdict': verdict, 'payload': payload, 'approval_action': 'enter_build',
                       'reasons': ['Every critical locked demand test was a hit; the founder may approve an MVP build.']}
    return base | {'outcome': 'DEMO_ONLY', 'verdict': verdict, 'payload': payload, 'approval_action': 'enter_build_demo_only',
                   'reasons': [f'Validation verdict {verdict}: not enough real customer evidence for an MVP. A DEMO-ONLY prototype may be approved; it is not validated, launch-ready or commercially approved.']}


def latest_build(db, pid):
    b = qone(db, 'SELECT * FROM builds WHERE project_id=? ORDER BY version DESC LIMIT 1', (pid,))
    if b:
        for k in ('spec_json', 'files_json', 'qa_json', 'changes_json'):
            b[k[:-5]] = json.loads(b.pop(k) or 'null')
    return b


def entered(db, pid, phase) -> dict | None:
    return qone(db, 'SELECT * FROM phase_transitions WHERE project_id=? AND phase=? ORDER BY created_at DESC LIMIT 1', (pid, phase))


def gate3_build(db, pid) -> dict:
    b = latest_build(db, pid)
    t = entered(db, pid, 3)
    if not t:
        return {'phase': 3, 'outcome': 'BLOCKED', 'reasons': ['Build has not been entered (needs the Validate gate and a founder approval).']}
    if not b:
        return {'phase': 3, 'outcome': 'REPEAT', 'reasons': ['Generate the first prototype.']}
    payload = {'build_version': b['version'], 'files_hash': b['files_hash'], 'qa_status': b['qa']['status'], 'mode': b['mode']}
    if b['qa']['status'] != 'PASS':
        return {'phase': 3, 'outcome': 'REPEAT', 'payload': payload, 'reasons': ['QA failed on the latest version; revise it.']}
    acc = qone(db, "SELECT * FROM approvals WHERE project_id=? AND action='accept_build' AND status='CONSUMED' ORDER BY consumed_at DESC LIMIT 1", (pid,))
    if acc and json.loads(acc['payload_json']) == payload:
        return {'phase': 3, 'outcome': 'GO', 'payload': payload, 'mode': b['mode'], 'reasons': [f'Founder accepted prototype v{b["version"]} ({b["mode"]}).']}
    return {'phase': 3, 'outcome': 'REPEAT', 'payload': payload, 'approval_action': 'accept_build', 'mode': b['mode'],
            'reasons': [f'QA passed on v{b["version"]}. The founder must accept this version before Commercial setup.']}


def latest_plan(db, pid):
    p = qone(db, 'SELECT * FROM commercial_plans WHERE project_id=? ORDER BY version DESC LIMIT 1', (pid,))
    if p:
        p['inputs'] = json.loads(p.pop('inputs_json'))
        p['results'] = json.loads(p.pop('results_json'))
    return p


def gate4_commercial(db, pid) -> dict:
    if gate3_build(db, pid)['outcome'] != 'GO':
        return {'phase': 4, 'outcome': 'BLOCKED', 'reasons': ['Accept a prototype version in Build first.']}
    p = latest_plan(db, pid)
    if not p:
        return {'phase': 4, 'outcome': 'REPEAT', 'reasons': ['Enter the pricing and cost assumptions.']}
    payload = {'plan_version': p['version'], 'plan_hash': p['plan_hash']}
    ue = p['results']['unit_economics']
    if ue['contribution_per_sale'] <= 0:
        return {'phase': 4, 'outcome': 'STOP', 'payload': payload,
                'reasons': ['Every sale loses money after fees and variable costs at this price. Change the price or costs.']}
    acc = qone(db, "SELECT * FROM approvals WHERE project_id=? AND action='activate_commercial' AND status='CONSUMED' ORDER BY consumed_at DESC LIMIT 1", (pid,))
    if acc and json.loads(acc['payload_json']) == payload:
        return {'phase': 4, 'outcome': 'GO', 'payload': payload, 'reasons': [f'Founder adopted plan v{p["version"]} for TEST MODE selling.']}
    return {'phase': 4, 'outcome': 'REPEAT', 'payload': payload, 'approval_action': 'activate_commercial',
            'reasons': [f'Plan v{p["version"]} is calculated. The founder must adopt it (TEST MODE only) before selling.']}


def gate5_sell(db, pid) -> dict:
    if gate4_commercial(db, pid)['outcome'] != 'GO':
        return {'phase': 5, 'outcome': 'BLOCKED', 'reasons': ['Adopt a commercial plan first.']}
    o = qone(db, 'SELECT * FROM offers WHERE project_id=? ORDER BY version DESC LIMIT 1', (pid,))
    if not o:
        return {'phase': 5, 'outcome': 'REPEAT', 'reasons': ['Create an offer and sales-page draft.']}
    if o['status'] != 'APPROVED_DRAFT' or not o['checkout_open']:
        return {'phase': 5, 'outcome': 'REPEAT', 'reasons': ['The founder must approve the sales-page draft and open the TEST MODE checkout.']}
    from .payments import reconcile
    rec = reconcile(db, pid)
    paid = [r for r in rec['orders'] if r['paid_cents']]
    if not paid:
        return {'phase': 5, 'outcome': 'REPEAT', 'reasons': ['No MOCKED order has been paid yet.']}
    if not rec['ok']:
        return {'phase': 5, 'outcome': 'REPEAT', 'reasons': ['Reconciliation found problems: ' + '; '.join(i['issue'] for i in rec['issues'][:3])]}
    return {'phase': 5, 'outcome': 'GO', 'reasons': [f'{len(paid)} MOCKED order(s) paid, delivered and reconciled in TEST MODE.']}


def gate6_operate(db, pid, rec: dict | None) -> dict:
    if gate5_sell(db, pid)['outcome'] != 'GO':
        return {'phase': 6, 'outcome': 'BLOCKED', 'reasons': ['Complete a reconciled MOCKED sale first.']}
    if not rec:
        return {'phase': 6, 'outcome': 'REPEAT', 'reasons': ['Run the Operations analysis.']}
    m = {'CONTINUE': 'GO', 'ITERATE': 'REPEAT', 'COLLECT_MORE_DATA': 'REPEAT', 'PIVOT': 'PIVOT', 'STOP': 'STOP'}
    return {'phase': 6, 'outcome': m[rec['recommendation']], 'reasons': rec['reasons'], 'recommendation': rec['recommendation']}


def all_gates(db, pid, ops_rec=None) -> list[dict]:
    return [gate1_discover(db, pid), gate2_validate(db, pid), gate3_build(db, pid), gate4_commercial(db, pid), gate5_sell(db, pid), gate6_operate(db, pid, ops_rec)]

"""Founder approvals, enforced in backend code (not by hiding buttons).

Flow: the server REQUESTS an approval for an action. It computes the payload from the current venture
state (never from the client), so the founder approves exactly what will run. The founder decides
APPROVE or REJECT with the project's capability token. The executing endpoint then calls `consume()`, which:
  * refuses PENDING, REJECTED, EXPIRED or already-CONSUMED approvals;
  * recomputes the payload and refuses if its hash changed (stale approval = materially different action);
  * marks the approval CONSUMED (single use).
Every state change is appended to approval_events (append-only, enforced by SQLite triggers).
The AI agents have no code path to request-and-decide: decide() needs the founder's token at the HTTP layer,
and no agent module imports it.
"""
from __future__ import annotations
import datetime as dt
import json
import uuid

from fastapi import HTTPException

from .db import now, qone
from .criteria import stable_hash

# action -> (risk, scope, ttl hours, human description)
ACTIONS = {
    'enter_build_demo_only':   ('MEDIUM', 'DEMO_ONLY_PROTOTYPE', 24, 'Generate a DEMO-ONLY website prototype although validation has not passed. Not validated, not launch-ready.'),
    'enter_build':             ('HIGH', 'MVP_BUILD', 24, 'Enter the Build phase on passed validation evidence.'),
    'accept_build':            ('MEDIUM', 'ACCEPT_PROTOTYPE_VERSION', 24, 'Accept this prototype version as the product for Commercial setup.'),
    'activate_commercial':     ('HIGH', 'COMMERCIAL_TEST_MODE', 24, 'Adopt this pricing/package plan for TEST MODE selling. No live payments, no agreements signed.'),
    'approve_sales_page':      ('HIGH', 'SALES_PAGE_DRAFT_ONLY', 24, 'Approve the sales-page draft. It is NOT published anywhere; FounderOS has no publishing code.'),
    'open_test_checkout':      ('HIGH', 'MOCKED_TEST_CHECKOUT', 24, 'Open a MOCKED / TEST MODE checkout for this offer. No real money can move.'),
    'refund_order':            ('HIGH', 'MOCKED_REFUND', 2, 'Refund this MOCKED order and revoke the buyer\'s access.'),
    'apply_proposal':          ('MEDIUM', 'REVISION_PROPOSAL', 24, 'Apply this Operate & Learn proposal as a new version (earlier versions and decisions are kept).'),
}
# Externally consequential actions that FounderOS never performs, even with approval.
NEVER = {'publish', 'send_message', 'send_email', 'spend', 'sign_agreement', 'deploy', 'live_payment', 'create_account', 'contact_buyer'}


def _event(db, aid, pid, event, detail=None):
    db.execute('INSERT INTO approval_events(approval_id,project_id,event,detail_json,at) VALUES(?,?,?,?,?)',
               (aid, pid, event, json.dumps(detail or {}, default=str), now()))


def request(db, pid: str, action: str, payload: dict, target: str | None = None) -> dict:
    if action in NEVER:
        raise HTTPException(403, f'{action} is never performed by FounderOS, with or without approval.')
    if action not in ACTIONS:
        raise HTTPException(422, f'Unknown approval action {action!r}')
    risk, scope, ttl, desc = ACTIONS[action]
    # A newer request supersedes older pending ones for the same action+target.
    for old in db.execute("SELECT id FROM approvals WHERE project_id=? AND action=? AND IFNULL(target,'')=IFNULL(?,'') AND status='PENDING'",
                          (pid, action, target)).fetchall():
        db.execute("UPDATE approvals SET status='SUPERSEDED' WHERE id=?", (old['id'],))
        _event(db, old['id'], pid, 'SUPERSEDED')
    aid = uuid.uuid4().hex
    exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=ttl)).isoformat()
    db.execute('INSERT INTO approvals(id,project_id,action,risk,scope,target,payload_json,payload_hash,status,requested_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
               (aid, pid, action, risk, scope, target, json.dumps(payload, default=str, sort_keys=True), stable_hash(payload), 'PENDING', now(), exp))
    _event(db, aid, pid, 'REQUESTED', {'action': action, 'payload_hash': stable_hash(payload)})
    return get(db, pid, aid) | {'description': desc}


def get(db, pid, aid) -> dict:
    a = qone(db, 'SELECT * FROM approvals WHERE id=? AND project_id=?', (aid, pid))
    if not a:
        raise HTTPException(404, 'Approval not found for this venture')
    a['payload'] = json.loads(a.pop('payload_json'))
    a['description'] = ACTIONS.get(a['action'], ('', '', 0, ''))[3]
    if a['status'] == 'PENDING' and a['expires_at'] < now():
        a['status'] = 'EXPIRED'
    return a


def decide(db, pid, aid, decision: str, note: str | None) -> dict:
    a = get(db, pid, aid)
    if a['status'] != 'PENDING':
        raise HTTPException(409, f'This approval is {a["status"]}; it can no longer be decided.')
    status = {'APPROVE': 'APPROVED', 'REJECT': 'REJECTED'}[decision]
    db.execute('UPDATE approvals SET status=?, decided_at=?, decision_note=? WHERE id=?', (status, now(), note, aid))
    _event(db, aid, pid, status, {'note': note})
    return get(db, pid, aid)


def consume(db, pid: str, aid: str | None, action: str, current_payload: dict, target: str | None = None) -> dict:
    """Server-side enforcement. Raises 403/409 unless a fresh, approved, unused approval matches the current payload."""
    if not aid:
        raise HTTPException(403, {'code': 'APPROVAL_REQUIRED', 'message': f'{action} needs a founder approval first.', 'action': action})
    a = get(db, pid, aid)
    if a['action'] != action or (target is not None and (a['target'] or None) != target):
        raise HTTPException(403, {'code': 'APPROVAL_MISMATCH', 'message': 'That approval is for a different action or object.'})
    if a['status'] == 'REJECTED':
        raise HTTPException(403, {'code': 'APPROVAL_REJECTED', 'message': 'The founder rejected this action. It will not run.'})
    if a['status'] == 'EXPIRED' or (a['status'] == 'APPROVED' and a['expires_at'] < now()):
        _event(db, aid, pid, 'REFUSED_EXPIRED')
        raise HTTPException(409, {'code': 'APPROVAL_EXPIRED', 'message': 'The approval expired. Request a new one.'})
    if a['status'] == 'CONSUMED':
        raise HTTPException(409, {'code': 'APPROVAL_USED', 'message': 'This approval was already used. Each approval authorises one execution.'})
    if a['status'] != 'APPROVED':
        raise HTTPException(403, {'code': 'APPROVAL_PENDING', 'message': f'Approval is {a["status"]}; the founder has not approved it.'})
    if stable_hash(current_payload) != a['payload_hash']:
        db.execute("UPDATE approvals SET status='STALE' WHERE id=?", (aid,))
        _event(db, aid, pid, 'REFUSED_STALE', {'approved_hash': a['payload_hash'], 'current_hash': stable_hash(current_payload)})
        raise HTTPException(409, {'code': 'APPROVAL_STALE', 'message': 'The inputs changed after approval, so it no longer authorises this action. Request a new approval.',
                                  'approved': a['payload'], 'current': current_payload})
    db.execute("UPDATE approvals SET status='CONSUMED', consumed_at=? WHERE id=?", (now(), aid))
    _event(db, aid, pid, 'CONSUMED')
    return a


def history(db, pid) -> list[dict]:
    rows = db.execute('SELECT * FROM approvals WHERE project_id=? ORDER BY requested_at DESC', (pid,)).fetchall()
    out = []
    for r in rows:
        a = dict(r)
        a['payload'] = json.loads(a.pop('payload_json'))
        a['description'] = ACTIONS.get(a['action'], ('', '', 0, ''))[3]
        if a['status'] == 'PENDING' and a['expires_at'] < now():
            a['status'] = 'EXPIRED'
        out.append(a)
    return out

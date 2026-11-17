"""Phase 5 sale-to-cash, MOCKED / TEST MODE ONLY.

There is no live payment provider and no code path that moves real money. The "payment provider" is a
built-in simulator that emits HMAC-signed test events into the same webhook handler a real provider would call.

  checkout()      -> order PENDING_PAYMENT (idempotent on the client's idempotency key)
  mock_pay()      -> simulator signs a payment_succeeded event and delivers it to handle_event()
  handle_event()  -> idempotent on event_id: payment_succeeded => order PAID + entitlement granted (delivery);
                     refund_succeeded => order REFUNDED + entitlement REVOKED
  refund()        -> needs a consumed founder approval; simulator emits refund_succeeded
  reconcile()     -> matches orders, payment events, fees, refunds, entitlements and the computed (mock) payout
No card numbers, passwords or bank details are accepted anywhere; such fields are rejected.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import secrets
import uuid

from fastapi import HTTPException

from .db import now, qone, qall

TEST_MODE = True     # constant: there is no live mode in this codebase
FORBIDDEN_FIELDS = ('card', 'cvv', 'cvc', 'pan', 'password', 'iban', 'account_number', 'expiry')


def no_payment_data(payload: dict):
    bad = [k for k in payload if any(f in k.lower() for f in FORBIDDEN_FIELDS)]
    if bad:
        raise HTTPException(422, f'FounderOS never accepts payment or credential fields: {bad}')


def secret(db) -> bytes:
    row = qone(db, "SELECT value FROM kv WHERE key='mock_webhook_secret'")
    if not row:
        v = secrets.token_hex(32)
        db.execute("INSERT INTO kv(key,value) VALUES('mock_webhook_secret',?)", (v,))
        return v.encode()
    return row['value'].encode()


def sign(db, event: dict) -> str:
    return hmac.new(secret(db), json.dumps(event, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def fee_cents(amount_cents: int, pct: float, fixed: float) -> int:
    from decimal import Decimal, ROUND_HALF_UP
    return int((Decimal(amount_cents) * Decimal(repr(pct)) / 100 + Decimal(repr(fixed)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


# ------------------------------------------------------------------------- checkout
def checkout(db, pid: str, offer: dict, buyer_ref: str, idem: str) -> tuple[dict, bool]:
    if not offer['checkout_open']:
        raise HTTPException(403, {'code': 'CHECKOUT_CLOSED', 'message': 'The founder has not approved a TEST MODE checkout for this offer.'})
    existing = qone(db, 'SELECT * FROM orders WHERE project_id=? AND idempotency_key=?', (pid, idem))
    if existing:
        return existing, False
    pk = json.loads(offer['package_json'])
    oid = uuid.uuid4().hex
    amount = int(round(pk['price'] * 100))
    db.execute('INSERT INTO orders(id,project_id,offer_id,buyer_ref,amount_cents,currency,status,idempotency_key,test_mode,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?)',
               (oid, pid, offer['id'], buyer_ref, amount, pk['currency'], 'PENDING_PAYMENT', idem, now(), now()))
    return qone(db, 'SELECT * FROM orders WHERE id=?', (oid,)), True


def make_event(db, pid, etype, order, event_id=None) -> dict:
    ev = {'event_id': event_id or 'evt_test_' + uuid.uuid4().hex[:20], 'type': etype, 'order_id': order['id'], 'project_id': pid,
          'amount_cents': order['amount_cents'], 'currency': order['currency'], 'livemode': False}
    return {'event': ev, 'signature': sign(db, ev)}


# ------------------------------------------------------------------------- webhook (idempotent)
def handle_event(db, pid: str, event: dict, signature: str, fees: dict) -> dict:
    if not hmac.compare_digest(sign(db, event), signature or ''):
        raise HTTPException(401, 'Bad test-webhook signature')
    if event.get('livemode') is not False:
        raise HTTPException(422, 'Live events are refused: FounderOS runs in MOCKED / TEST MODE only.')
    if event.get('project_id') != pid:
        raise HTTPException(403, 'Event belongs to another venture')
    seen = qone(db, 'SELECT * FROM payment_events WHERE project_id=? AND event_id=?', (pid, event['event_id']))
    if seen:
        return {'event_id': event['event_id'], 'result': 'DUPLICATE_IGNORED', 'first_result': seen['result']}
    order = qone(db, 'SELECT * FROM orders WHERE id=? AND project_id=?', (event['order_id'], pid))
    if not order:
        raise HTTPException(404, 'Order not found for this venture')
    fee = 0
    if event['type'] == 'payment_succeeded':
        if event['amount_cents'] != order['amount_cents'] or event['currency'] != order['currency']:
            result = 'REJECTED_AMOUNT_MISMATCH'
        elif order['status'] != 'PENDING_PAYMENT':
            result = f'IGNORED_ORDER_{order["status"]}'
        else:
            fee = fee_cents(order['amount_cents'], fees['pct'], fees['fixed'])
            db.execute("UPDATE orders SET status='PAID', updated_at=? WHERE id=?", (now(), order['id']))
            grant(db, pid, order['id'])
            result = 'PAID_AND_DELIVERED'
    elif event['type'] == 'refund_succeeded':
        if order['status'] != 'PAID':
            result = f'IGNORED_ORDER_{order["status"]}'
        else:
            db.execute("UPDATE orders SET status='REFUNDED', updated_at=? WHERE id=?", (now(), order['id']))
            revoke(db, order['id'])
            result = 'REFUNDED_AND_REVOKED'
    else:
        result = 'IGNORED_UNKNOWN_TYPE'
    db.execute('INSERT INTO payment_events(id,project_id,event_id,type,order_id,amount_cents,fee_cents,result,received_at,test_mode) VALUES(?,?,?,?,?,?,?,?,?,1)',
               (uuid.uuid4().hex, pid, event['event_id'], event['type'], order['id'], event['amount_cents'], fee, result, now()))
    return {'event_id': event['event_id'], 'result': result, 'order_id': order['id']}


# ------------------------------------------------------------------------- delivery
def grant(db, pid, order_id) -> dict:
    ent = qone(db, 'SELECT * FROM entitlements WHERE order_id=?', (order_id,))
    if ent:                       # UNIQUE(order_id): a second grant is impossible
        return ent
    tok = secrets.token_urlsafe(24)
    db.execute("INSERT INTO entitlements(id,project_id,order_id,token,status,granted_at) VALUES(?,?,?,?,'ACTIVE',?)", (uuid.uuid4().hex, pid, order_id, tok, now()))
    return qone(db, 'SELECT * FROM entitlements WHERE order_id=?', (order_id,))


def revoke(db, order_id):
    db.execute("UPDATE entitlements SET status='REVOKED', revoked_at=? WHERE order_id=? AND status='ACTIVE'", (now(), order_id))


def access(db, token: str) -> dict:
    ent = qone(db, 'SELECT * FROM entitlements WHERE token=?', (token,))
    if not ent:
        raise HTTPException(404, 'Unknown access link')
    if ent['status'] != 'ACTIVE':
        raise HTTPException(410, 'Access was revoked (the MOCKED payment was refunded).')
    db.execute('UPDATE entitlements SET deliveries=deliveries+1, last_access_at=? WHERE id=?', (now(), ent['id']))
    return ent


# ------------------------------------------------------------------------- reconciliation
def reconcile(db, pid: str) -> dict:
    orders = qall(db, 'SELECT * FROM orders WHERE project_id=? ORDER BY created_at', (pid,))
    events = qall(db, 'SELECT * FROM payment_events WHERE project_id=?', (pid,))
    ents = {e['order_id']: e for e in qall(db, 'SELECT * FROM entitlements WHERE project_id=?', (pid,))}
    refunds = {r['order_id']: r for r in qall(db, 'SELECT * FROM refunds WHERE project_id=?', (pid,))}
    rows, issues = [], []
    for o in orders:
        pay = [e for e in events if e['order_id'] == o['id'] and e['result'] == 'PAID_AND_DELIVERED']
        ref = [e for e in events if e['order_id'] == o['id'] and e['result'] == 'REFUNDED_AND_REVOKED']
        paid = sum(e['amount_cents'] for e in pay)
        fee = sum(e['fee_cents'] for e in pay)
        refunded = sum(e['amount_cents'] for e in ref)
        ent = ents.get(o['id'])
        exp_status = 'REFUNDED' if ref else 'PAID' if pay else 'PENDING_PAYMENT'
        prob = []
        if o['status'] != exp_status:
            prob.append(f'order status {o["status"]} but events say {exp_status}')
        if len(pay) > 1:
            prob.append('more than one successful payment for one order')
        if pay and paid != o['amount_cents']:
            prob.append(f'paid {paid} != order amount {o["amount_cents"]}')
        if o['status'] == 'PAID' and (not ent or ent['status'] != 'ACTIVE'):
            prob.append('paid but no active access')
        if o['status'] != 'PAID' and ent and ent['status'] == 'ACTIVE':
            prob.append('access active without a valid payment')
        if ref and o['id'] not in refunds:
            prob.append('refund event without an approved refund record')
        if o['id'] in refunds and refunds[o['id']]['amount_cents'] != refunded:
            prob.append('refund record amount differs from refund event')
        rows.append({'order_id': o['id'], 'buyer_ref': o['buyer_ref'], 'status': o['status'], 'amount_cents': o['amount_cents'], 'paid_cents': paid,
                     'fee_cents': fee, 'refunded_cents': refunded, 'net_cents': paid - fee - refunded,
                     'access': ent['status'] if ent else 'NONE', 'deliveries': ent['deliveries'] if ent else 0, 'issues': prob})
        issues += [{'order_id': o['id'], 'issue': p} for p in prob]
    orphan = [e for e in events if e['order_id'] not in {o['id'] for o in orders}]
    issues += [{'order_id': e['order_id'], 'issue': 'payment event for unknown order'} for e in orphan]
    totals = {k: sum(r[k] for r in rows) for k in ('paid_cents', 'fee_cents', 'refunded_cents', 'net_cents')}
    totals['mock_payout_cents'] = totals['net_cents']
    return {'mode': 'MOCKED / TEST MODE', 'orders': rows, 'totals': totals, 'issues': issues, 'ok': not issues,
            'payout_note': 'Mock payout = payments - fees - refunds. No payout is made; there is no bank account.'}

"""Refunds (MOCKED / TEST MODE). A refund needs a consumed founder approval bound to the order and amount;
the simulator then emits refund_succeeded, which the webhook handler processes (order REFUNDED, access REVOKED)."""
from __future__ import annotations
import uuid

from fastapi import HTTPException

from .db import now, qone
from . import approval
from .payments import make_event, handle_event


def refund_payload(order: dict) -> dict:
    return {'order_id': order['id'], 'amount_cents': order['amount_cents'], 'currency': order['currency'], 'status': order['status']}


def refund(db, pid: str, order_id: str, approval_id: str | None, fees: dict) -> dict:
    order = qone(db, 'SELECT * FROM orders WHERE id=? AND project_id=?', (order_id, pid))
    if not order:
        raise HTTPException(404, 'Order not found for this venture')
    if order['status'] != 'PAID':
        raise HTTPException(409, f'Only PAID orders can be refunded (this one is {order["status"]}).')
    approval.consume(db, pid, approval_id, 'refund_order', refund_payload(order), target=order_id)
    ev = make_event(db, pid, 'refund_succeeded', order)
    res = handle_event(db, pid, ev['event'], ev['signature'], fees)
    db.execute('INSERT INTO refunds(id,project_id,order_id,amount_cents,approval_id,event_id,created_at) VALUES(?,?,?,?,?,?,?)',
               (uuid.uuid4().hex, pid, order_id, order['amount_cents'], approval_id, ev['event']['event_id'], now()))
    return {'event': ev['event'], **res}

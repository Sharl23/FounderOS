# payments

- Phase: Phase 5
- Kind: deterministic code agent (no model, no prompt)
- Source: `backend/app/payments.py, webhooks.py, delivery.py, refunds.py, reconcile.py`

## Contract

TEST MODE simulator: idempotent checkout, HMAC-signed events, idempotent webhook, one entitlement per order, approved refund with revocation, reconciliation.

"""Digital delivery: one entitlement per paid order (UNIQUE order_id), revoked on refund. See payments.grant/revoke/access."""
from .payments import grant, revoke, access  # noqa: F401

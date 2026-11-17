"""Webhook entry point for (MOCKED / TEST MODE) payment events. Logic lives in payments.handle_event:
signature check, livemode refusal, venture isolation and idempotency on event_id."""
from .payments import handle_event, make_event  # noqa: F401

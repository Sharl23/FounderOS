# safety_screen

- Phase: Phase 1
- Kind: deterministic code agent (no model, no prompt)
- Source: `backend/app/safety.py`

## Contract

Twelve written rules applied to the founder text before any model call. BLOCK stops the venture; REVIEW_REQUIRED allows research only.

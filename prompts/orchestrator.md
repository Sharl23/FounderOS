# orchestrator

- Phase: All
- Kind: deterministic code agent (no model, no prompt)
- Source: `backend/app/orchestrator.py, gates.py, approval.py`

## Contract

Six-phase state machine: computes each gate in code, requests founder approvals bound to current state, and refuses stale, rejected, expired or reused approvals.

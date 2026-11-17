# Judge readiness — PARTIALLY READY

Superseded by [`README-for-judges.md`](README-for-judges.md) (demo script, claims map, verification status) and [`v7-implementation-matrix.md`](v7-implementation-matrix.md).

Status stays **PARTIALLY READY** until `python scripts/live_check.py` has run on the demo laptop with a real local model (inference verified) and `docker compose up --build` has been observed working there. Paste the generated `docs/live-check-results.md` numbers into the pitch; none are pre-filled.

Rubric map: working prototype (25) → seven-screen journey, `scripts/ui_e2e.py`; architecture (20) → `architecture.md`; supported claims (15) → research studio + evidence standard + traceability; founder control/safety (15) → twelve rules, gates, append-only log; pitch (15) → human; openness (10) → MIT, open-weight model, no paid APIs.

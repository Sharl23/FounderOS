# Build verification — honest handoff (v0.2, 2026-11-17)

## Executed in the authoring environment (Linux sandbox, Python 3.13, no Docker daemon, no internet to model registries)
- `cd backend && python -m pytest -q` → **46 passed** (test-only fake model).
- `python -m compileall backend/app` → OK; `node --check backend/app/static/app.js` → OK.
- `docker compose config -q` → valid (Compose v5.7 CLI; daemon not available, so no build/run).
- `python scripts/ui_smoke.py` (Playwright + headless Chromium against a live uvicorn with the test-only fake model) → **UI SMOKE OK**: create → refine → safety → discovery → approve → secondary evidence → experiment draft → lock → failing result → validation = STOP_DO_NOT_LAUNCH → truthful 422 on approve-without-acknowledgment → approve with reasons → reload persistence → blocked brief path.
- All four `workflows/*.json` parse; approval adapter carries `report_hash` + `brief_version`.
- Paid-key audit: no API keys or paid endpoints referenced anywhere.

## NOT executed here (must be done on the founder's machine)
- `docker compose up --build`, the first Ollama model pull, real Qwen2.5 inference quality and latency (`scripts/benchmark.py`), persistence across container restarts, the optional n8n import.
- Real fetching of public URLs (the sandbox's egress is restricted; the fetcher's SSRF checks were unit-tested, the happy path was not hit against a live site).

Nothing above is claimed beyond what ran. Status: **PARTIALLY READY** (see `docs/judge-readiness.md`).

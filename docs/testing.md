# Verification and test strategy

## Automated tests

Execute from repo root:

```bash
python -m pip install -r backend/requirements-dev.txt
cd backend && PYTHONPATH=. python -m pytest -q
```

Unit/integration tests run against a fresh local SQLite database with a **fake, deterministic LLM used only by the test suite**. They verify (46 tests, `backend/tests/`):
1. `test_flow.py` — full journey with persistence, research-only approval scope, decision-log binding; STOP enforced; revision feedback reaches the next run; edited brief invalidates approvals; tampered hash / cross-project / unauthenticated rejected; external actions 403; later phases 501 (never simulated); offline model → 503, no fake report; append-only decision/audit log enforced by SQLite triggers.
2. `test_evidence_and_verdict.py` — contract acceptance tests G1–G7: sector-growth articles ≠ validation; 20 enthusiastic statements ≠ demand; unverified/mismatched/duplicate sources excluded; negative locked experiment → STOP (with refuting IDs) or PIVOT (with alternative); planned experiment ≠ evidence; criteria frozen (trigger + hash); criteria change → new version + audit, old result retired; small positive sample → CONTINUE_TESTING with caveats; offline + no sources → honest unknowns, no invented URLs; consent/date validation; model praise cannot change the verdict (skeptic flags over-claims).
3. `test_safety.py` — the eight organizer MUST-NEVER attacks each hard-blocked before any model call and un-overridable by acknowledgment; negated mentions are not blocked; REVIEW_REQUIRED needs acknowledgment and resets on new versions; injection through evidence/feedback/experiment text is excluded/rejected; private/localhost/metadata/non-HTTPS/custom-port URLs never fetched; redirects never followed; card numbers rejected in every text field.

Headless browser click-through: `python scripts/ui_smoke.py` (Playwright + Chromium, fake model) exercises every dashboard button against the real API including truthful 422 errors, reload persistence and the BLOCK path.

Automated tests **do not** verify Ollama response quality, first-pull Docker startup, third-party n8n import, external website reliability, or an actual customer demand experiment.

## Recommended smoke test on real computer

1. `docker compose up --build` and wait for `model-init` to download the chosen model.
2. Open `http://localhost:8000/api/health`. It must show `ollama_reachable: true, model_pulled: true` and mode `LIVE_LOCAL_OLLAMA_REQUIRED`. Then `python scripts/benchmark.py` for observed latencies.
3. Create a new project and run Refine. Confirm fields are returned from the real model (not test fixtures).
4. Check basic JSON quality and constraints retention; smaller models can make mistakes.
5. Run discovery; attempt validation before approving and confirm rejection. Approve discovery, then run validation with no evidence and confirm `NEEDS_EVIDENCE`.
6. Try `REVISE`; include feedback and rerun. Confirm report version increments and audit persists after page refresh.
7. Add a **real public URL** and an **exact excerpt**. Confirm remote retrieval status is honest; if inaccessible, remains `UNVERIFIED`.
8. Try external action API and confirm HTTP 403. Make sure no real account messages or payments occur.
9. Optional: import n8n JSON into local n8n editor, activate one workflow, verify backend enforces the same approval guard. These exports were not live-verified in the authoring environment.

## Input-quality evaluation harness (recommended before final submission)

The software does not assert prompt refinement boosts accuracy. Compare ten messy founder briefs against ground-truth, human-written structured briefs; score missing-value invention rate, budget/timeline retention, clarification quality, schema failures and incorrect market claims. Use separate real model calls for direct vs refined downstream inputs. Do not fabricate results.

# FounderOS for judges

**What it is:** a local, open-source decision system that tells a founder whether an idea has earned more of their time, and why, using evidence. **What it is not:** a builder or launcher of the founder's startup. No publishing, sending, spending, signing or payments exist anywhere in the code.

## Functional vs architecture only

| Live and tested | Architecture only (documented, endpoints 501, nothing simulated) |
|---|---|
| Brief refinement with provenance; 12-rule safety screen; discovery agent; research studio (Crossref, OpenAlex, World Bank, founder-chosen pages) with exact-passage verification; 21 criteria with per-criterion judge and code gates; locked demand tests; decision passport; append-only decision log | Build, Commercial setup, Launch, Operate & learn — with their 17 criteria and gates in `docs/architecture.md` |

## Three-minute fresh-brief demo

Before the slot: `docker compose up --build` (or the Windows override in the README), open http://localhost:8000, click the model status and run the real test until it says **Model ready**.

1. **Projects → Start a venture.** Paste the judges' brief; fill segment and location if given. *Create venture*.
2. **Refine and check safety.** Point at the provenance badges: typed fields are “Yours”, model guesses are “Inferred, confirm it”, gaps are “Unknown”.
3. **Safety.** Twelve named checks. The legal check says “Source not checked”: FounderOS never claims legality.
4. **Discover → Run the discovery agent.** Cards, then the gate: with no evidence the code says **Repeat with more evidence** (PDF p.2: unknowns lead to repeat). Approve research with a written reason; the dialog states it allows research only.
5. **Decision → Run validation.** Verdict **Needs evidence**, with the five dimensions all unknown, the next demand test, and no success percentage anywhere.

If the model cannot load, the screen says why (e.g. *ran out of RAM*) and what to do; the founder's input is kept and nothing is faked. Try a forbidden brief (“buy fake reviews”) to see a hard stop with the exact phrase and no override.

## Where to check the claims

| Claim | Evidence |
|---|---|
| 12 safety rules with exact semantics | `backend/policy/safety_rules.yaml`, `backend/app/safety.py`, `docs/criteria-traceability.md`, `backend/tests/test_safety_rules_v7.py` |
| 9 + 7 + 5 criteria, five kinds, versioned | `backend/policy/criteria.yaml`, `backend/app/criteria.py`, `docs/criteria-methodology.md`, `backend/tests/test_criteria_v7.py` |
| Model cannot pick a verdict or invent citations | `criteria.validate_judgment`; tests `test_adversarial_judge_cannot_change_gate_or_cite_fakes`, `test_judge_rejects_*` |
| Real research, no fabricated sources | `backend/app/research.py`; `backend/tests/test_research_v7.py` (404, timeout, paywall, SSRF, redirect to private IP, injection, duplicates, metadata-only DOI) |
| Version-bound, append-only decisions | `decisions` table + SQLite triggers; `test_flow.py`, `test_platform_v7.py::test_direct_api_bypass_attempts` |
| Real browser journey | `scripts/ui_e2e.py`, screenshots in `docs/screenshots/` |

## Verification status (honest)

| Check | Result |
|---|---|
| `pytest` (212 tests, TEST_ONLY fake model and mocked providers) | PASS in the authoring sandbox |
| Real-browser end-to-end (`scripts/ui_e2e.py`, Chromium, 1366×768 and 390 px) | PASS, 44 checks, TEST_ONLY model |
| `docker compose config` (default and Windows override) | PASS |
| Live local model inference, live providers, `docker compose up` | **NOT VERIFIED** in the authoring sandbox (no Docker daemon, no internet). Run `python scripts/live_check.py` on the demo laptop; it writes `docs/live-check-results.md` with observed numbers only. |

Organizer timing note: the slides say a 3-minute live run then 5 + 2 minutes; the one-pager says 10 + 10. Confirm with organizers.

## Cost

No paid service, key or subscription. Local inference has no per-request fee; the cost is the laptop's CPU/GPU time and electricity plus a one-time ~1 GB model download.

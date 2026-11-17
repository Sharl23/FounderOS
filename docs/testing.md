# Testing

| Layer | Command | What it proves | What it does not |
|---|---|---|---|
| Unit/integration (247 tests) | `cd backend && python -m pytest -q` | Safety rules (12 × fixtures), 21 criteria, five kinds, judge contract and adversarial judges, research verifier and failure paths (timeout retry, TLS, truncation, SSRF), gates and bypass attempts, OOM mapping, v0.4 and v0.7 migrations. v0.8 (`test_v08_contract.py`): all 67 rubric ids, hash and mapping; brief extraction with spans; discovery guard; relevance review; independence; absence caps; simulated tests; minors; decision log; validation prose | Real model quality; live providers |
| Real browser (60 checks) | `python scripts/ui_e2e.py` (Playwright + Chromium) | Every screen and button against the live API and SQLite. Includes: refresh, back, deep links, the criteria matrix with judging, the relevance review, restaurant brief spans and D02, the decision log fields, hard stop, model failure, phone width, the keyboard skip link, and no raw JSON | Uses a TEST_ONLY fake model and mocked providers |
| Live check (founder's machine) | `python scripts/live_check.py [--url https://...]` | Real inference, latency of three fresh briefs, live Crossref/OpenAlex/World Bank access | Writes only what it observed |
| Manual API smoke | `python scripts/smoke.py` | Live refine + discover via HTTP | — |

All synthetic data in tests is labelled TEST_ONLY; the shipped app has no fake model, no seeded evidence and no simulated output.

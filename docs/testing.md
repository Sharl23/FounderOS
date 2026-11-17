# Testing

| Layer | Command | What it proves | What it does not |
|---|---|---|---|
| Unit/integration (212 tests) | `cd backend && python -m pytest -q` | Safety rules (12 × fixtures), 21 criteria, five kinds, judge contract and adversarial judges, research verifier and failure paths, gates and bypass attempts, OOM mapping, v0.4 migration | Real model quality; live providers |
| Real browser | `python scripts/ui_e2e.py` (Playwright + Chromium) | Every screen and button against the live API and SQLite; refresh, back, deep links, hard stop, model failure, phone width, keyboard skip link, no raw JSON | Uses a TEST_ONLY fake model and mocked providers |
| Live check (founder's machine) | `python scripts/live_check.py [--url https://...]` | Real inference, latency of three fresh briefs, live Crossref/OpenAlex/World Bank access | Writes only what it observed |
| Manual API smoke | `python scripts/smoke.py` | Live refine + discover via HTTP | — |

All synthetic data in tests is labelled TEST_ONLY; the shipped app has no fake model, no seeded evidence and no simulated output.

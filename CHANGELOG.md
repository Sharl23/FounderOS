# Changelog

## 0.10.0 — 17 Nov 2026 (founder-specific decisions)

- **Next decision.** "Your next decision" was added to the Decision Passport. It gives:
  - the decision and why, with evidence IDs and the claims still unknown;
  - the options considered and rejected, and the trade-off;
  - the founder-fit reasons and the next action;
  - the cost and time (ASSUMPTION), a success criterion, and what would change the decision;
  - the approval needed, and a confidence level that describes evidence coverage, not a probability.
- **Strategy engine.** It now weighs the founder's budget (with a TEAM_ASSUMPTION floor per currency for paid tests), skills (whether they can build a page) and time.
  - Each critical claim has candidate methods: problem walk-through, concierge, self-built page, neutral opt-in, paid ad, switching trial, side-by-side task, two-price test, and a refused real deposit.
  - The pilot window follows the chosen method, never beyond the stated time.
  - Behaviour change: a 6-week founder now gets the stronger 14-day concierge test instead of a 7-day opt-in, and one test assertion was updated to match.
- **Build.** Two new working prototype types: a client and project tracker (the freelancer case) and appointment booking. Both have QA checks, and `scripts/prototype_e2e.py` drives them in a real browser.
- **Commercial.** A recommendation layer covers loss per sale with the minimum viable price, break-even against scenarios, budget fit, churn sensitivity and unsupported price.
- **Operate.** Adds INSUFFICIENT EVIDENCE, the bottleneck, the phase the next iteration loops back to, and a count of each data source.
- **Research.** The plan is ranked by the weakest critical claim, and each bucket states what research cannot prove.
- **Evaluation.** `evals/founder_cases.py` runs six synthetic founders (StudyFlow, freelancer, booking, weak evidence, adverse result, safety stop) and writes `evals/founder_eval_results.md`; `tests/test_founder_eval.py` enforces the same expectations.
- **Fixes:**
  - A safety-blocked venture no longer shows an evidence confidence level.
  - The passport's side panel no longer says "design the next test" under a STOP verdict.
  - The passport no longer crashes on an evidence row without claim text.

## 0.9.0 — 17 Nov 2026 (all six phases, MOCKED / TEST MODE for 3-6)

- **Phase 3 Build:**
  - `agents/product_architect.py` writes the spec, user stories and acceptance criteria from the founder's own words.
  - `agents/website_builder.py` writes a real static site: HTML, CSS, JS and a README.
  - `agents/qa.py` runs static checks; `agents/revision.py` runs the feedback loop and reports what it did not apply.
  - Versions, a sandboxed preview (CSP sandbox, random key, four allowed file names) and a ZIP export.
  - Validate STOP or BLOCK refuses any build. Otherwise the build is DEMO-ONLY unless every critical locked test was a hit.
- **Phase 4 Commercial setup:** `agents/commercial.py` computes Decimal unit economics, break-even, scenarios, pricing hypotheses, business models, packages and a terms checklist. The payment provider is MOCKED.
- **Phase 5 Sell / deliver / get paid (MOCKED / TEST MODE):**
  - offer and draft sales page, with an honesty check;
  - idempotent checkout that rejects card fields;
  - HMAC-signed simulator and an idempotent webhook (duplicates ignored, forged events rejected);
  - one entitlement per order, a refund that needs approval and revokes access, and reconciliation.
- **Phase 6 Operate and learn:** metrics derived from recorded events, MANUAL or MOCK_DEMO metrics, feedback with provenance and issues. A rule-based recommendation leads to a proposal back to Phase 3 or 1, applied as a new version.
- **Approvals:** `approval.py` covers server-side approvals:
  - bound to a state hash;
  - single use, with expiry;
  - stale, rejected and pending approvals refused;
  - append-only event history.

  Actions that are never performed are refused even with an approval.
- **Gates and orchestration:** `gates.py` holds gates 1-6. `orchestrator.py` holds the workflow state machine and API. `agent_log.py` writes one row per agent action, exported as `decision_log.json`.
- **Interface:** sidebar grouped by the six phases, a Six phases overview, and Build Studio, Commercial setup, Sell and get paid, and Operate and learn views. An approval dialog offers approve or reject.
- **Repository layout:**
  - `tests/` moved to the root;
  - `ARCHITECTURE.md`, `prompts/` (generated from code), `outputs/` and `decision_log.json` from `scripts/demo_run.py`;
  - README rewritten to the required headings;
  - reviewer-facing docs removed.
- **Submission checker:** `scripts/check_submission.py` re-runs the pipeline and compares the result with the committed outputs.
- **Fixes from the audit:**
  - A safety-blocked step now logs `model: null` instead of a placeholder string.
  - A payment event sent to a venture without a commercial plan now gets 401, 403 or 409 instead of a server error. The signature is checked before anything else.
  - `.gitignore` now excludes model weights and local databases.
- **Docker:** `docker compose up` now starts only the app against Ollama on the host. The Ollama containers are under the `ollama` profile.

## 0.8.0 — 17 Nov 2026 (final repair after the founder's manual trial)

Repairs every defect seen in the real end-to-end trial on 17 Nov 2026 and registers the team's 67-check Phase-1 rubric. Data from v0.7 is kept (additive migration `v8`; nothing is deleted).

### Team rubric (67 checks)
- `backend/policy/rubric_phase1.yaml`: the team's `checks` and `provenance` copied word for word (parsed from the contract by `scripts/rubric/parse_team_rubric.py`, written by `generate_rubric_yaml.py`). A sha256 of the team data is checked at startup; the app refuses to start if the text was edited, an id is duplicated, a field is missing, or the 12 ethics checks differ from `policy/safety_rules.yaml`.
- `backend/app/rubric.py`: the 12 ethics checks aggregate under D01 (still enforced by the safety screen); 6 / 5 / 15 / 15 / 14 scored checks aggregate under D03–D07. D02, D08, D09 and X01–X05 are unchanged and separate.
- Granular statuses UNKNOWN / AWAITING_JUDGE / WEAK / MIXED / STRONG / NOT_APPLICABLE, decided by code around one local-model judgment per check:
  - WEAK needs a cited challenging source or a directly checkable brief condition; "nothing found" stays UNKNOWN.
  - STRONG needs the required number of independent organisations (counted by publisher or registrable domain, not by URL), at least one machine-verified excerpt, and no accepted challenging source.
  - Absence-type checks (`no_blocking_patent`, `free_alternatives_threat`, `substitution_threat`, `regulatory_barriers_manageable`) are never STRONG.
  - Only accepted source types count. Academic metadata, simulated results and book passages never count.
- Dimension score = mean of mapped ratings (WEAK 2, MIXED 3, STRONG 4). It is computed only when at least 2 checks are rated and at least one rating rests on linked evidence.
- API: `GET /api/rubric`, `GET /api/projects/{id}/rubric` (Research Matrix), `POST /api/projects/{id}/rubric/judge`.
- Research Matrix UI (Research → Criteria matrix). Each check shows:
  - the question and the weak, mixed and strong definitions;
  - the source types it accepts, and sources required versus accepted;
  - accepted and rejected evidence, with reasons;
  - searches tried and the next step;
  - a per-check search: automated only where a compliant provider exists, otherwise manual links;
  - an add-source form;
  - the team provenance, labelled "not independently checked".
- `docs/rubric-traceability.md`: all 67 rows.

### Defects from the trial
1. **Brief extraction / false D02 fail.**
   - New `brief_extract.py` pulls typed fields from the founder's own words, with exact character spans: city and country, employee range, budget and currency, timeline in days, skills, problem sentence, "pain not verified", current workaround. It never invents a workaround.
   - Source precedence: founder answer, then form, then own words, then model suggestion. A model suggestion never counts until confirmed.
   - PARSER_FAILED is shown separately from NOT_STATED, and there is one clear question per missing field.
   - New `POST /brief/confirm`. D02 is re-evaluated on every new brief version.
2. **Discovery quality.**
   - New `discovery_guard.py` catches:
     - numbers not in the brief (e.g. "up to 50%");
     - places or institutions not in the brief (e.g. "AUC");
     - directions that share nothing with the brief's customer or problem;
     - generic goals and tests that are too big for the stated budget.
   - The model is retried once with the specific problems listed. Anything still wrong is removed (never replaced), and everything is labelled HYPOTHESES. The prompt is constrained to the brief.
3. **Research errors.**
   - Precise codes: TIMEOUT, TLS_VERIFY_FAILED, DNS_FAILED, BLOCKED_ADDRESS, HTTP_DENIED, HTTP_NOT_FOUND, UNSUPPORTED_TYPE, TOO_MANY_REDIRECTS, NETWORK. Each comes with advice.
   - One bounded retry for timeouts and network errors only.
   - Oversized pages are read to 800 KB and safely truncated (labelled) instead of failing.
   - TLS verification and SSRF rules are unchanged.
   - A "paste the passage yourself" fallback is labelled *pasted by you, not verified* and can never make a check STRONG on its own.
   - Queries are built from structured key words, never from the first 60 characters of raw text.
4. **Evidence review.**
   - Five explicit relevance questions: claim supported (not just the same words), geography, buyer/user, method, date.
   - Review states: ACCEPTED_RELEVANT, CONTEXT_ONLY, EXCLUDED.
   - Reserved documentation domains (`example.com` and the like) are always excluded, including old ledger rows.
   - An excerpt that shares no key term with the claim is excluded.
   - The claim field has plain examples.
5. **Decision log.**
   - Built server-side as named fields (`decision_log`): gate said, reason, `reason_status` (PROVIDED / NOT_GIVEN_OPTIONAL), scope, and every reference version and hash.
   - References that a record predates are shown as "not stored", never invented.
   - Decisions now also store the rubric version and hash and the Discover evaluation version.
   - The UI renders one card per decision, so columns can no longer shift.
6. **Demand tests.**
   - Wording like "simulated sign-up" or "hypothetical waitlist" fails the V05 design check, so the test cannot be locked as real.
   - An explicit SIMULATED / NOT COUNTED demo stores its result as `SIMULATED_RESULT`, which is excluded everywhere.
   - Ventures involving minors require adults-only tests (parents, guardians, teachers), and any wording that contacts children blocks the lock.
   - Recruitment method, exclusions and limitations are recorded. Results show denominator, numerator, dates, consent, locked thresholds and their origin.
7. **Validation prose.**
   - The code's verdict explanation is shown first (`prose.verdict_explanation`).
   - The model text is cleaned: categorical absence claims are rewritten ("No evidence of customer behaviour was recorded"), fragments are dropped, and sentences contradicting the verdict are removed. All corrections are listed.
   - A malformed model narrative no longer blocks validation.
   - Empty values read "Unknown / not provided".
8. **UI.** Highlighted source spans on the brief, D02 status box, Criteria matrix, granular checks under each dimension, review chips in the ledger, fetch-error advice, SIMULATED styling, decision cards.

### Also fixed
- **Restart crash:** with v0.7 on any Python (reproduced on 3.11, 3.12 = the Docker image, and 3.13), a second start against an existing database failed with "cannot change into wal mode from within a transaction". The migration transaction is now committed first (`db.init_db`).

### Tests
- `pytest`: **247 passed** (31 new in `tests/test_v08_contract.py`; research error tests added). TEST_ONLY fake model, mocked providers.
- `scripts/ui_e2e.py`: **60 checks passed** in headless Chromium (desktop 1366 px and phone 390 px, dark theme, keyboard). TEST_ONLY model.
- Not run here: live Ollama inference, live Crossref/OpenAlex/World Bank, `docker compose up`. See `docs/v08-repair-report.md`.

## 0.7.0
Route-separated UI, 12 safety rules, 21 criteria as code, research studio, model health. See `docs/history/`.

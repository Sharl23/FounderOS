# Changelog

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
- **Restart crash:** on Python 3.13 (the Docker image) a second start against an existing database failed with "cannot change into wal mode from within a transaction". The migration transaction is now committed first (`db.init_db`).

### Tests
- `pytest`: **247 passed** (31 new in `tests/test_v08_contract.py`; research error tests added). TEST_ONLY fake model, mocked providers.
- `scripts/ui_e2e.py`: **60 checks passed** in headless Chromium (desktop 1366 px and phone 390 px, dark theme, keyboard). TEST_ONLY model.
- Not run here: live Ollama inference, live Crossref/OpenAlex/World Bank, `docker compose up`. See `docs/v08-repair-report.md`.

## 0.7.0
Route-separated UI, 12 safety rules, 21 criteria as code, research studio, model health. See `docs/history/`.

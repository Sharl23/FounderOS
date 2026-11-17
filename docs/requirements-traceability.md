# Compliance traceability (reviewed against organizers' provided slides + one-page PDF)

Source of truth: user-supplied photos of slides titled **The problem statement**, **The Six Phases**, **How It Works**, **The Rules**, **Tips & Tricks**, plus *AI Hackathon – Details.pdf* one-pager.

| Exact organizer expectation | Status | Evidence / caveat |
|---|---|---|
| Build an **open-source team of AI agents** | Core implemented, OSS repo; optional n8n excluded | MIT code, independent Discover and Validate model prompts, plus refiner. n8n is optional and non-OSI. |
| Help a founder convert idea toward a **validated, sellable digital product** | Partial live vertical slice | Refine → Discover → Validate → gate working; phases 3–6 are architecture **only**, not falsely claimed as completed. |
| Prototype that shows system in action | Backend/UI code present; runtime model/Docker NOT LIVE VERIFIED | 46 pytest + headless-Chromium click-through passed with a test-only fake model; `docker compose config` valid. |
| Architecture of the **full system** submitted in repo | Designed | `docs/architecture.md`: each phase has contracts, output, tools and gate. |
| Evidence-based decisions, founder stays in control | Implemented | Source ledger + deterministic gates + approval endpoint + audit. |
| Six phases: Discover / Validate / Build / Commercial setup / Launch / Operate & learn | Included in exact order | Full six-phase architecture; only first two executed by MVP. |
| Every phase ends with a gate: approve / target / tests | Implemented for live phases; specified for future phases | `backend/app/gates.py`, `backend/app/main.py`, phase tables in architecture. |
| Founder brings short brief + skills, budget, time, market, values | Implemented | Dashboard form, schema, explicit-field preservation. |
| Open source and **single-command setup** | Configured, needs Docker-run verification | `docker compose up --build`; first model pull automated; authoring environment has no Docker binary. |
| At least one **open-weight** model, no paid services | Configured, model tag verified | Ollama `qwen2.5:1.5b-instruct` (Apache-2.0), API calls local. Runtime LLM output quality not benchmarked. |
| Founder approval before publishing, sending, spending, signing | Enforced by absence + blocked API | No external actions implemented; `/external-action` rejects and audits. |
| Provide sources for market claims or mark as assumptions | Implemented with explicit limitations | Quote verifier, unverified fallback, outputs treated as hypotheses; cannot guarantee LLM truthfulness. |
| Never promise income / guarantee success | Prompts and UI prohibit it | No income guarantee logic. |
| Never fake testimonials / reviews / registrations | Backend hard-block + consent-gated evidence | `safety.py` FAKE_SOCIAL_PROOF rule blocks such briefs before any model call; customer evidence requires consent confirmation and stays FOUNDER_REPORTED. |
| Never impersonate founder/customer/brand | No impersonation tools | All writing draft-only, no outbound identity or messaging tools. |
| Never hold, transfer or refund money | Not implemented | No payments/financial tools. |
| Never store passwords or card details | No password/card data models + admission guard on every text field + CREDENTIAL_STORAGE block rule | Luhn/credential patterns rejected (422) before persistence; briefs asking to store credentials are BLOCKED. |
| Never publish/send/spend without approval | More conservative: no outbound functions exist | API blocks even if phase approved. |
| Label mocks/stubs | Implemented in docs, no runtime fallback | Tests marked fake; 3–6 are design only; optional n8n not verified. |
| Back up market claims | Ledger requires retrieved source excerpt or explicit unverified status | Source-excerpt verification ≠ objective market proof, documented. |
| Test STOP / not launching | Implemented, unit-tested | Failed critical pre-registered experiment → STOP_DO_NOT_LAUNCH or PIVOT; absence of behaviour evidence → NEEDS_EVIDENCE; prohibited brief → BLOCK. Source excerpts alone never move the verdict. |
| Build one part, architect rest (36-hour caveat) | Followed | Connected two-phase MVP; honest scope. |
| Deadline Tue 17 Nov, 11:59 pm | Documented; no submission performed | Requires user's push and MADS upload. |

No extra judging rubric, requirement to produce a demo video, or file format was invented.

## Added in v0.2 (business-evidence contract)

| Requirement | Where |
|---|---|
| Safety screen ALLOW/REVIEW/BLOCK, persisted per brief version, non-overridable BLOCK | `backend/app/safety.py`, `/safety/acknowledge`, `tests/test_safety.py` |
| Four evidence classes, multidimensional verification, dedupe, injection exclusion | `evidence` table, `/evidence`, `decision.exclusion_reason` |
| Pre-registered experiments (frozen criteria, versions, retired results) | `experiments` table + triggers, `/experiments/*`, G6 test |
| Deterministic verdict, 5-dimension matrix, risk register, next experiment, what-would-change-our-mind | `decision.evaluate_validation`, Decision Passport UI |
| Version-bound approvals (run id, report hash, brief version, safety status, experiment versions), append-only decision log | `decisions` table + triggers, `/phases/{phase}/decision` |
| Rubric map + 3-minute demo checklist + PARTIALLY READY status | `docs/judge-readiness.md` |
| Free-dependency / license audit | `docs/api-cost-and-licenses.md` |

# Criteria and safety-rule traceability (v0.7)

Policy files: `backend/policy/criteria.yaml` (version `criteria-2026-11-17.v7.1`) and `backend/policy/safety_rules.yaml` (version `safety-policy-2026-11-17.v7-1`). Both are hashed (SHA-256) and the hashes are stored on every evaluation and founder decision (`decisions.criteria_policy_hash`, `decisions.safety_policy_hash`).
Page numbers refer to *Criteria Types for the Agent Workflow* (@Sharl, 16 Nov 2026, 11 pages), read in full. Test status is from `cd backend && python -m pytest -q` → **247 passed** (v0.8; unit/integration; model mocked as `FakeModel`, TEST_ONLY).

UI locations: Brief `/projects/:id/brief`, Safety `/safety`, Discover `/discovery`, Research `/research`, Demand tests `/experiments`, Decision `/decision`, Log `/audit`, Roadmap `/roadmap`.

## Discover — 9 criteria (PDF p.3; ethics tiers p.4)

| ID | Criterion (PDF wording) | Kind | Implementation (code) | UI | Tests | Honest gaps |
|---|---|---|---|---|---|---|
| D01 | Ethics and legality screen | knockout | `safety.screen` (12 rules) → `criteria.evaluate_discover` D01 row; hard stop ⇒ exit STOP; review unacknowledged ⇒ REVIEW_REQUIRED | Safety; Discover scorecard | `test_safety_rules_v7.py` (all), `test_criteria_v7.py::test_knockout_is_never_averaged_away`, `::test_d01_review_required_until_acknowledged` | Rule detection is English pattern matching + escalate-only model flags |
| D02 | Idea clarity | output_check | customer + pain + current workaround present; inferred fields flagged | Brief (provenance badges, “confirm as written”) | `::test_output_check_d02_clarity` | — |
| D03 | Problem and customer | scored | evidence-gated; judge per criterion; `validate_judgment` | Discover scorecard | `::test_scored_discover_criteria_need_accepted_evidence_and_judge[D03]`, judge adversarial tests | Judge quality on qwen2.5:1.5b NOT LIVE VERIFIED |
| D04 | Demand signals | scored | as D03; score capped at 3 unless behaviour/experiment evidence | Discover scorecard | `[D04]`, `::test_score_caps_secondary_and_demand_needs_behaviour` | as above |
| D05 | Competition and alternatives | scored | as D03; none found ⇒ UNKNOWN | Discover scorecard; AI alternatives shown “Unverified” | `[D05]`, `::test_d05_none_found_is_unknown_not_no_competitors` | No automatic competitor search (see research honesty) |
| D06 | Feasibility and founder fit | scored + knockout for hard limits | `criteria.hard_limits` (budget/timeline vs experiment cost/window) | Discover scorecard | `[D06]`, `::test_d06_hard_limit_knockout_from_founder_brief` | Skills fit is only judged from evidence, not parsed |
| D07 | Viability, first look | scored | as D03 | Discover scorecard | `[D07]` | — |
| D08 | Direction ranking | threshold | ranks discovery directions A–C by behaviour-backed then net accepted support; <2 grounded ⇒ UNKNOWN; ties kept | Discover scorecard; evidence can be tagged to a direction | `::test_d08_direction_ranking_unknown_without_evidence_and_ties_stay_ties` | — |
| D09 | Discover gate rule | threshold | code exits STOP / REVIEW_REQUIRED / PIVOT / REPEAT / GO_ON; thresholds from versioned config; GO = validation research only | Discover gate slip | `::test_threshold_applied_in_code_with_versioned_config`, `::test_unknown_is_not_zero_and_not_a_middle_mark`, `::test_d09_pivot_on_evidence_backed_low_problem_score`, `::test_d09_agent_output_prohibited_tactic_forces_repeat`, `::test_stale_evaluation_blocks_decision_until_reevaluated` | Numeric pass marks are TEAM_ASSUMPTION |

## Validate — 7 criteria (PDF pp.4–5)

| ID | Criterion | Kind | Implementation | UI | Tests | Gaps |
|---|---|---|---|---|---|---|
| V01 | Business model coherence | scored | evidence-gated judge (viability rows) | Decision → Validate criteria | `::test_validate_criteria_rows_present_and_honest` | live judge quality not verified |
| V02 | Strategy and positioning | scored | evidence-gated judge (competition rows) | same | same | same |
| V03 | Financial fit | knockout + scored | `hard_limits` knockout; fit via judge | same | same; `::test_v05_blocks_lock_for_opinion_metric_and_v06_needs_origin` (cost vs budget) | costs parsed only from numbers the founder typed |
| V04 | Risk ranking | scored | criticality × weakness over the assumption register (code); notes whether a locked test targets the top risk | same | `::test_validate_criteria_rows_present_and_honest` | formula is TEAM_ASSUMPTION |
| V05 | Experiment design | output_check | `experiment_design_check`: behavioural metric, can fail, cost within budget, honest consent, founder runs it, no never-rule; **lock refused if any fails** | Demand tests (checklist on each draft) | `::test_v05_blocks_lock_for_opinion_metric_and_v06_needs_origin` | behavioural-metric check is a keyword heuristic |
| V06 | Target setting | threshold | threshold origin (TEAM_ASSUMPTION or CITED_BENCHMARK = accepted ledger row), sample floor, time window; frozen by lock + hash + SQLite trigger | Demand tests | same; `test_evidence_and_verdict.py::test_planned_experiment_is_not_evidence_and_criteria_are_frozen` | — |
| V07 | Result reading | threshold + evidence standard | `decision.evaluate_result`: HIT / NEAR_MISS / CLEAR_MISS / TOO_LITTLE_DATA vs locked criteria; critical clear miss ⇒ STOP or PIVOT (advisory, not generalised) | Demand tests; Decision passport | `::test_v07_readings_hit_near_miss_clear_miss_too_little`, `test_evidence_and_verdict.py` STOP/PIVOT/CONTINUE tests, `test_platform_v7.py::test_result_cannot_race_ahead_of_lock` | results are founder-reported |

## Cross-cutting — 5 criteria, at every live gate (PDF pp.8–9)

| ID | Criterion | Kind | Implementation | Tests |
|---|---|---|---|---|
| X01 | Evidence quality | evidence_standard | `criteria.evidence_quality`: exclusion (unverified, mismatch, duplicate/syndicated, metadata-only, injection, stale **and** off-market, superseded test) and flags (date, publisher, geography, relevance, sample) | `::test_evidence_standard_x01_excludes_bad_rows_with_reasons`, `::test_weak_but_counted_secondary_gets_flags`, research tests |
| X02 | Founder constraints and values | knockout + scored | hard limits + `founder_values_conflict` acknowledgment | `::test_d06_hard_limit...`, `test_safety_rules_v7.py::test_values_conflict_quotes_both_spans_exactly` |
| X03 | Safety rules | knockout | brief screen + re-screen of agent outputs (`safety.screen_agent_output`) + experiment designs + feedback | `::test_rescreen_on_brief_revision_and_on_agent_output`, `test_safety.py` |
| X04 | Approval scope | knockout | all approvals `RESEARCH_ONLY`; `/external-action` always 403; decision dialogs state the scope | `test_flow.py::test_external_actions_hard_denied...`, `test_platform_v7.py::test_direct_api_bypass_attempts` |
| X05 | Confidence and unknowns | evidence_standard | counts of unknown criteria and accepted/excluded evidence; no percentages | `::test_unknown_is_not_zero_and_not_a_middle_mark` |

Five-kind semantics: `test_criteria_v7.py::test_five_kinds_and_policy_shape` asserts the kind of every criterion against the PDF tables. Versioning: `::test_config_change_versioned_non_editable_rejected_and_approvals_invalidated`. Judge contract (PDF p.10 rules 3–6): `::test_judge_rejects_fabricated_evidence_id`, `::test_judge_rejects_new_urls_and_unsourced_numbers`, `::test_judge_cannot_answer_another_criterion_or_score_out_of_scale`, `::test_score_inconsistent_with_contradicting_evidence_is_discarded`, `::test_no_judge_calls_without_evidence_and_one_call_per_criterion_cached`, `::test_adversarial_judge_cannot_change_gate_or_cite_fakes`.

## Phases 3–6 — 17 criteria, ARCHITECTURE ONLY (PDF pp.6–8)

Named with their PDF questions in `criteria.yaml → architecture_only` and on the Roadmap screen; **none is evaluated, and the phase endpoints return 501**.
Build (p.6): B01 Scope fit (output check), B02 Acceptance (threshold: the tests pass).
Commercial setup (pp.6–7): C01 Pricing logic (scored), C02 Offer structure (scored), C03 Policy completeness (output check), C04 Fair dealing (knockout), C05 Compliance flags (output check). Drafts only; no payments.
Launch (p.7): L01 Positioning and message (scored), L02 Channel selection (scored), L03 Content honesty (knockout), L04 Content quality (scored), L05 Launch readiness (output check), L06 Launch targets (threshold). Marketing lives here, not in Commercial.
Operate and learn (p.8): O01 Metric selection (output check), O02 Support quality (scored, knockout for hand-offs), O03 Learning validity (evidence standard), O04 Next-step decision (threshold).

## Twelve safety rules (V7 contract Appendix A/B — binding semantics)

Provenance below is the founder-supplied attribution. It is **design provenance, not legal evidence**; pages are "not visible" in the supplied text and none are invented. Only the two Appendix A rules quote the Criteria PDF (its p.4 three-tier table contains both passages verbatim — verified in the PDF text).

| Rule id | Outcome on fail (code) | Provenance (as supplied) | Code | Tests (positive / negative / borderline / negated / absent-source) |
|---|---|---|---|---|
| illegal_in_target_market | HARD_STOP **only** with a fetched, excerpt-verified, official-domain source classified PROHIBITS/unobtainable licence; otherwise UNKNOWN_SOURCE, or REVIEW_REQUIRED for unknown/ambiguous jurisdiction or legal-risk indicators | Criteria PDF p.4 ("Illegal in the target market…") | `safety.screen`, `/safety/sources` | `test_safety_rules_v7.py` 3 fixtures + `::test_official_source_can_hard_stop_only_when_verified_and_official`, `::test_ambiguous_jurisdiction_pauses_and_never_passes` — PASS |
| regulated_or_sensitive_area | REVIEW_REQUIRED (research-only acknowledgment) | Criteria PDF p.4 ("Legal but sensitive or regulated areas…") | detectors (children, personal/special data, regulated activities) | 3 fixtures + absent-source — PASS |
| physical_goods_exclusion | HARD_STOP; marketplaces of physical items REVIEW | *The Gate at the Edge of the Map*, ch.3 | detectors with "software for a physical business" exception | 4 fixtures + restaurant brief — PASS |
| financial_crypto_exclusion | HARD_STOP | ch.3 | detectors; external payment processor ≠ handling users' money | 3 fixtures — PASS |
| health_legal_advice_exclusion | HARD_STOP (label "educational" ignored) | ch.3 | detectors | 4 fixtures — PASS |
| advice_in_disguise | REVIEW_REQUIRED (escalate in plain language) | ch.3 | detectors | 3 fixtures — PASS |
| income_promise_dependency | HARD_STOP | ch.3 | detectors | 4 fixtures — PASS |
| fake_proof_dependency | HARD_STOP; anti-fraud products not blocked | ch.3 | detectors incl. fake urgency | 4 fixtures — PASS |
| impersonation_dependency | HARD_STOP; authorised/white-label branding REVIEW | ch.3 | detectors | 4 fixtures — PASS |
| money_or_credentials_dependency | HARD_STOP | ch.3 | detectors; FounderOS also rejects card numbers/credentials in all input | 4 fixtures — PASS |
| harm_to_people | HARD_STOP (source labels this wall a proposed assumption) | ch.3 | detectors | 4 fixtures — PASS |
| founder_values_conflict | REVIEW_REQUIRED with both exact quotes | ch.2 | value lexicon vs idea text | 4 fixtures + `::test_values_conflict_quotes_both_spans_exactly` — PASS |

Model involvement: `RefinedBrief.risk_flags` may **escalate** a rule to REVIEW_REQUIRED only with a verbatim brief quote; it can never create or remove a HARD_STOP (`::test_model_flag_escalates_only_with_verbatim_quote_and_never_blocks`, `::test_model_cannot_remove_a_hard_stop`). System guards outside the twelve rules: `SYSTEM_PROMPT_INJECTION`, `SYSTEM_UNAPPROVED_EXTERNAL_ACTION` (X04).

Unavailable regulatory sources: no compliant automated legal-search provider is configured, so every brief's legal check shows the jurisdiction, the proposed search queries (marked "not executed") and `UNKNOWN_SOURCE` until the founder attaches an official page.

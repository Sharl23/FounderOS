# Criteria methodology

Source: *Criteria Types for the Agent Workflow* (@Sharl, 16 Nov 2026, 11 pages). FounderOS implements its design rules as code. Page references below are to that PDF.

## Five kinds (p.2), and who enforces each

| Kind | PDF: "best enforced by" | FounderOS |
|---|---|---|
| Knockout | code and fixed lists, model only classifying | `safety.py` detectors + `criteria.py` (D01, D06 hard limits, V03, X02–X04). Runs first: a hard-stopped brief gets no model call and no research run. |
| Scored | a judging agent, one criterion at a time | `JUDGE_SYSTEM` prompt + `JudgeOutput` schema; one call per criterion that has accepted evidence; output validated by `criteria.validate_judgment`. |
| Evidence standard | code checking the claims record, plus a verifying agent | `criteria.evidence_quality` (X01, X05) + `research.safe_fetch`/`excerpt_in` (the verifier). |
| Threshold | code only | D08, D09, V06, V07 in `criteria.py` / `decision.py`. |
| Output check | code for format, reviewing agent for content | D02, V05 in code; the skeptic pass (`decision.skeptic_review`) and agent-output safety re-screen review content. |

The PDF's three consequences (p.2) are tested: knockouts run first; "a score without evidence is unknown, not a middle mark" (UNKNOWN, never 0 or 3); "too many unknowns should lead to repeat" (D09 → REPEAT); "the model never applies the threshold".

## Seven rules for feeding criteria to agents (p.10)

1. **Own file** — `backend/policy/criteria.yaml`, readable by the founder (Roadmap screen, Criteria settings), the criterion judge agents and code.
2. **Version in every decision** — `decisions.criteria_version`, `criteria_policy_hash`, `config_hash`, `evaluation_hash`, `safety_policy_hash`.
3. **One criterion per call** — `run_judges` loops criteria; each call carries only that criterion's accepted evidence.
4. **Gatherer ≠ judge** — Research Studio gathers (providers, founder URLs); the judge may cite only aliased ledger ids `E1…En`.
5. **Reason + evidence reference with every score** — otherwise rejected → UNKNOWN; invented ids, URLs or numbers ⇒ rejected and logged (`CRITERION_JUDGMENT_REJECTED`).
6. **Arithmetic and pass marks in code** — weighted mean of KNOWN scores only; exits picked in `evaluate_discover`.
7. **Founder sees and adjusts before the run** — Criteria settings panel; `POST /criteria/config` creates a new version and invalidates stale approvals; knockouts and safety rules are not editable (422).

## Numbers that are assumptions

The PDF prescribes that weights and pass marks exist and are fixed before the run (p.9, p.10); it does not give values. Every number in `criteria.yaml` (weights 2–3, pass mark 3.0, pivot mark 2.0, max 2 unknown scores, 5-year source age, 20 % near-miss band, evidence caps) is labelled **TEAM_ASSUMPTION** in the file and in the UI. Suggested experiment targets (30 % of ≥10 people) are labelled the same way unless the founder cites an accepted ledger row as benchmark (V06).

## Evidence caps (code)

A judge score is capped by the strongest cited evidence class: secondary sources and customer statements ≤ 3; D04 Demand > 3 requires customer behaviour or a locked-test result. Secondary articles therefore can never establish demand for this product.

## Decision exits

Discover (D09): STOP (hard stop) · REVIEW_REQUIRED · PIVOT (D03/D04 evidence-backed ≤ pivot mark) · REPEAT (clarity, hard limit, prohibited tactic in agent output, too many unknowns, mean below pass mark) · GO_ON. Every GO and every founder approval is **validation research only**.
Validate (`decision.evaluate_validation`): BLOCK_DO_NOT_LAUNCH · STOP_DO_NOT_LAUNCH · PIVOT · NEEDS_EVIDENCE · CONTINUE_TESTING. Never VALIDATED, never READY_TO_LAUNCH, no success probability.

Business-testing principles behind the validate verdict are in `business-decision-methodology.md`.

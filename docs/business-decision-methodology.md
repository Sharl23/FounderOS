# Business-decision methodology (what the verdict is, and is not)

**Implemented in `backend/app/decision.py` (deterministic) and `backend/app/safety.py` (deterministic).** The local LLM never computes, changes or approves a verdict; it only drafts hypotheses and explains a verdict the backend already fixed.

## Principles we borrow (references, not evidence)

These are published decision frameworks. They tell us **how to test**. They are **not** evidence that any particular founder's idea works, and the links are to the publishers, not to proof.

| Principle used in code | Source |
|---|---|
| Prioritise risky hypotheses; fix hypothesis, experiment, metric and success threshold **before** observing results; prefer observed behaviour over stated opinion; separate desirability / feasibility / viability | Bland & Osterwalder, *Testing Business Ideas* (Strategyzer) — https://www.strategyzer.com/library/testing-business-ideas-book ; https://www.strategyzer.com/library/validate-your-ideas-with-the-test-card ; https://www.strategyzer.com/library/business-testing-is-your-hypothesis-really-validated |
| Narrow beachhead segment, payer vs user, alternatives, quantified value, first customers, pricing, costs, key assumptions as a **checklist** (`canonical_assumptions`) | Aulet, *Disciplined Entrepreneurship* (MIT) — https://entrepreneurship.mit.edu/profile/bill-aulet-2/ ; https://entrepreneurship.mit.edu/news/entrepreneurs-can-conduct-primary-market-research/ |
| Ask about past behaviour and workarounds; discount flattery and hypothetical "I'd buy" (`CUSTOMER_STATEMENT` never counts for demand) | Fitzpatrick, *The Mom Test* — https://www.simonandschuster.net/books/The-Mom-Test/Rob-Fitzpatrick/9798893312560 |
| Build–measure–learn; pivot/persevere decided on observed results, not opinion | Ries, *The Lean Startup* — https://theleanstartup.com/principles?level=1 |
| Market size, local relevance, customer economics, alternatives, pricing and acquisition are **separate** questions; foreign data ≠ Egyptian data (`geography` field; secondary sources are context only) | US SBA, market research & competitive analysis — https://www.sba.gov/counseling/plan-your-business/ |

A prestigious domain (university, government) is not proof of relevance or quality. A paper's title/abstract cannot substantiate claims not present in the accessible text. FounderOS therefore records **what was actually retrieved** and nothing more.

## The five dimensions and what may count

| Dimension | Counts toward SUPPORTED/REFUTED | Never counts |
|---|---|---|
| Desirability / problem | all four classes (behaviour strongest) | — |
| **Demand / traction** | `CUSTOMER_BEHAVIOR`, `PRE_REGISTERED_EXPERIMENT_RESULT` | secondary sources, customer statements |
| Competition | sourced alternatives; absence of rivals = **UNKNOWN**, never "no competitors" | AI-listed alternatives (they are `alternatives_unverified`) |
| Feasibility / safety | safety screen status + founder constraints | legal certification (never claimed) |
| Viability / pricing | behaviour or pre-registered price tests; otherwise **UNTESTED** | AI pricing hypotheses |

## Evidence ladder (`evidence.kind`) and verification axes

`SECONDARY_BACKGROUND` < `CUSTOMER_STATEMENT` < `CUSTOMER_BEHAVIOR` < `PRE_REGISTERED_EXPERIMENT_RESULT`.
Each row stores: `url_status` (URL_ACCESSIBLE / UNVERIFIED), `excerpt_status` (EXCERPT_MATCHED / NOT_MATCHED / NOT_CHECKED), `relevance` (founder-declared), `independence` (INDEPENDENT_SOURCE_FOUNDER_SELECTED / FOUNDER_REPORTED_NOT_INDEPENDENTLY_VERIFIED), method/sample/dates/consent, `dedupe_key` + `duplicate_of`, `injection_flag`, `limitations`.
An excerpt match proves only that the words appear at the URL. Duplicates, unreachable/mismatched sources, irrelevant rows, injection-flagged rows and results of superseded experiment versions are **excluded** (listed in the passport with the reason).

## Deterministic verdict policy (`evaluate_validation`)

1. Safety `BLOCK` → **BLOCK_DO_NOT_LAUNCH** (`SAFETY_BLOCK`, not a business opinion, not overridable).
2. A **critical, locked** experiment whose founder-reported result **FAILS** its own frozen criterion →
   * recorded `pivot_alternative` → **PIVOT** (alternative is untested);
   * at/below the frozen adverse trigger → **STOP_DO_NOT_LAUNCH** (advisory);
   * otherwise → **NEEDS_EVIDENCE** (repeat/redesign).
3. Any locked experiment **PASS**, or any counted `CUSTOMER_BEHAVIOR` supporting demand → **CONTINUE_TESTING** (not validation; not permission to build or launch).
4. Otherwise → **NEEDS_EVIDENCE** (default for every fresh brief, however good the market articles are). This is not "bad idea".

There is no weighted score and no success probability. Thresholds are never universal: they are whatever the founder locks per experiment. Results below `min_sample` are **INCONCLUSIVE**. Small samples always carry a caveat line.

## Pre-registration contract (`experiments` table)

Draft → **Lock** (founder confirms `I_PREREGISTER_THESE_CRITERIA_BEFORE_COLLECTING_RESULTS`; `locked_at` stamped; SQLite trigger forbids editing a locked payload) → **Result** (must cite the exact `criteria_hash` and version; collection dates must be after `locked_at`) → compared with the frozen criteria. Editing after locking creates **a new version**, supersedes the old one, retires its results from the verdict and writes `EXPERIMENT_CRITERIA_CHANGED` to the audit log. A pivot archives locked experiments.

## What the passport shows

Verdict + kind, headline, conditional recommendation, 5-dimension matrix with linked evidence IDs, top-3 reasons for/against, strongest source + limitations (or **SOURCE UNAVAILABLE**), unresolved critical assumptions, contradictions, excluded evidence, experiment outcomes vs frozen criteria, assumption risk register, "what would change our mind", caveats, permissions (`build:false`, `launch:false`, `external_actions:false` always), the exact input versions/hashes, and the founder's version-bound decision.

## Known limitations

English-only pattern safety screen; founder-declared relevance/direction; no automatic source discovery (optional free connectors were not added — see `docs/api-cost-and-licenses.md`); founder-reported customer data is never independently verified by the system.

## Adaptive founder experiment planner (v0.9 enhancement)

`backend/app/founder_strategy.py` proposes a **draft** next experiment using the founder-entered
segment, market, existing workaround, budget, timeline, privacy constraints, and the evidence
classified by `risk_register`. A missing workaround prompts a past-behaviour problem test; an
unsupported demand assumption prompts an observed opt-in test; once demand has supporting behaviour,
the next questions are switching away from alternatives and price commitment. The proposal shows
the precise claim ID and the IDs of counted evidence (or `NONE`), its rationale and limits.
If a test is already locked, the founder must complete it rather than rewriting criteria after results.
Safety blocks and adverse critical verdicts pause new-test suggestions in the Decision Passport.

Recruitment and all external actions are founder-only. Numeric thresholds are **arbitrary draft
assumptions**, not researched conversion benchmarks or proof of demand; the founder must select
and lock them before collecting data. The planner estimates a free, short pilot consistent with
the stated duration and reports when time is unknown. No inference here can override a gate.

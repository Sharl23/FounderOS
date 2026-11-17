# operations

- Phase: Phase 6
- Kind: deterministic code agent (no model, no prompt)
- Source: `backend/app/agents/operations.py`

## Contract

Input: recorded events, labelled manual/mock metrics, feedback with provenance, issues, demand tests. Output: derived metrics, a rule-based recommendation, INSUFFICIENT EVIDENCE below 10 paid orders, the bottleneck and the phase it loops back to, and a proposal back to Phase 1 or 3.

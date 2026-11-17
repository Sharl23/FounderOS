# revision

- Phase: Phase 3
- Kind: deterministic code agent (no model, no prompt)
- Source: `backend/app/agents/revision.py`

## Contract

Input: feedback lines + current spec. Output: spec overrides and a list of changes, each APPLIED or NOT APPLIED. Nothing is guessed.

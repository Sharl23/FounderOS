# qa

- Phase: Phase 3
- Kind: deterministic code agent (no model, no prompt)
- Source: `backend/app/agents/qa.py`

## Contract

Input: spec + files. Output: PASS/FAIL with one item per check (structure, unique and required ids, forbidden HTML/JS, feature evidence, DEMO label).

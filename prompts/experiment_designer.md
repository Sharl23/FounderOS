# experiment_designer

- Phase: Phase 2
- Kind: deterministic code agent (no model, no prompt)
- Source: `backend/app/criteria.py (experiment_design_check), decision.py, main.py experiment endpoints`

## Contract

Checks a demand-test design, locks it with a hash before results, and reads results against the locked pass mark (hit / near miss / clear miss / too little data).

# founder_strategy

- Phase: Phase 2
- Kind: deterministic code agent (no model, no prompt)
- Source: `backend/app/founder_strategy.py, decision.py (next_decision_card)`

## Contract

Input: brief (budget, skills, timeline, segment, market), risk register, experiments. Output: the next test for the weakest critical claim, chosen among candidate methods by evidence strength within the founder's budget, skills and time; rejected options with reasons; the Decision Passport next-decision card. Never invents evidence or changes a verdict.

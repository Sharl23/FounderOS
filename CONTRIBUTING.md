# Working together (hackathon team)

- Keep `main` runnable and make small branches: `feat/refiner`, `feat/evidence`, `fix/approval`, `docs/architecture`.
- Do not edit the same file at the same time; assign ownership before large changes.
- Always run `python -m pytest -q` from the repository root before merging.
- No secrets in Git, `.env`, SQLite volumes, screenshots of real customer data, or project access tokens.
- If you use a coding agent, review its actual code diff and test it. Do not equate generated code with working code.
- Do not falsely claim to have run Ollama, n8n, external web research, a customer interview, or a real paid transaction.
- Preserve every founder approval gate, source provenance status and immutable history.
- Test a STOP recommendation; missing evidence means NEEDS_EVIDENCE, not guaranteed failure.

# website_builder

- Phase: Phase 3
- Kind: deterministic code agent (no model, no prompt)
- Source: `backend/app/agents/website_builder.py`

## Contract

Input: spec. Output: index.html, styles.css, app.js, README.txt. All text is HTML-escaped; demo data is JSON rendered with textContent; no network, storage or eval.

# FounderOS v0.3 — focused UX / bibliographic discovery / criteria status

This release is an **incremental implementation**, not a complete autonomous research or validated product-building agent. It preserves the 0.2 SQLite/HITL/safety/verdict behavior.

## UX implemented

- Six distinct workspace pages: Idea, Safety, Discovery, Research & Evidence, Demand Experiments, Validation & Decision.
- Left navigation + Back/Next controls. The browser keeps the currently selected page for the tab; backend phase gates remain authoritative.
- Discovery uses readable fields and lists; raw model JSON is available in an expandable Technical report.
- Validation has a Decision Passport and audit log on its own page.
- No external actions introduced.

## Research implemented

- `GET /api/research/crossref?q=...` searches **Crossref public bibliographic metadata** with no required subscription or API key.
- The server queries a fixed Crossref host; user input is bounded text, never a URL target. Timeouts, redirect refusal, and a response-byte limit are enforced.
- Up to five DOI / title / publisher / year candidates are displayed, clearly **UNVERIFIED_CANDIDATES_NOT_EVIDENCE**.
- The founder may prefill citation metadata, but must independently review publication contents, enter a specific claim and exact excerpt, and use the existing HTTPS evidence-verification flow.
- No automatic insertion in the evidence ledger; no candidate changes the verdict. Only matching page text in the ledger is recorded as EXCERPT_MATCHED, which is not truth verification.
- Crossref does not serve market reports, competitor websites or interview results comprehensively. This feature alone cannot assess a market or verify willingness to buy.
- Internet is needed for live Crossref searches. The core local application continues working when Crossref is offline.

## Criteria mapping to "Criteria Types for the Agent Workflow" (11-page PDF)

The PDF names **five criterion kinds**: Knockout, Scored, Evidence standard, Threshold, Output check. It also describes **nine Discover**, **seven Validate**, and **five cross-cutting** types, plus architecture-only types for phases 3–6.

**Implemented previously and retained:**

- Knockout: backend rules for explicitly prohibited ideas and prohibited external actions; higher-risk terms trigger research-only acknowledgment.
- Evidence standard: the four evidence classes, duplicate rejection, URL/excerpt status, and founder-reported customer data.
- Threshold: pre-registered demand experiments and deterministic verdicts (STOP, PIVOT, CONTINUE_TESTING, NEEDS_EVIDENCE).
- Output check: typed LLM schema and required fields.
- Founder constraints in the brief, versioned approvals, immutable decision logs.

**Not yet implemented despite PDF recommending them:**

- Criterion-by-criterion scored judgments for five Discover types and Validate business-model/positioning/finance/risk criteria, with sourced criterion scores/weights.
- Direction ranking across 2–3 alternative concepts.
- A generic versioned criteria registry used directly by the backend.
- Independent evidence credibility classification beyond HTTP/excerpt matching and founder-declared relevance.
- Automatic market-wide search, market-size and actual competitor extraction.
- Fully autonomous phases 3–6 (architecture only).

Current backend verdict is conservative and safe, but the current research enrichment and score coverage remain limited.

## Local Windows execution

Because some machines cannot pull the large Ollama Docker image, `compose.windows.yaml` allows **Windows host Ollama**:

1. Install Ollama on Windows and run `ollama pull qwen2.5:1.5b-instruct`.
2. From the repo folder: `docker compose -f docker-compose.yml -f compose.windows.yaml up --build`.
3. Open http://localhost:8000. Keep the same flags on all subsequent Compose commands.
4. If the health API cannot reach Ollama, check the host Ollama listening interface and Windows firewall; do not expose Ollama on public networks.

This override is a **local testing workaround**; the default Compose file remains for the organizer's one-command deployment.

## Verification status in this environment

- Python backend unit tests including candidate-research behavior: 51 passed.
- Python compileall: passed.
- JS syntax check: passed.
- Browser-level test was attempted but the execution environment blocked Chromium accessing local URLs (`net::ERR_BLOCKED_BY_ADMINISTRATOR`). It must be run on Windows before submission.
- **Not live-verified:** Crossref external service, actual Windows Docker + host Ollama for v0.3, n8n import, or model output in this upgraded package.

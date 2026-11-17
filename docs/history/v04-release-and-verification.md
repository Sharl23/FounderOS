# FounderOS v0.4 — audited interface and criteria coverage

Release status: **locally tested Python backend and JavaScript syntax**. This is an incremental release of v0.3, **not** a fully autonomous six-phase system or a finished criteria-scoring framework.

## The actual changes

- Reorganized the UI to **one sidebar**, a compact header and a compact project identity card. The existing six workspaces retain their individual task views. Older "phases 3–6" text is available on the Decision page under roadmap, not duplicated in the sidebar. The overall theme stays dark, but the layout emphasizes the current task.
- The Research workspace has **three locally generated topic prompts** from the normalized brief. A click only fills the search box: **nothing is transmitted to Crossref until the user presses Search**.
- Crossref metadata discovery now considers up to 12 candidate records and shows the best six, ranked using **transparent title-term matching**, with a penalty for "pre-university" articles when searching university students. This is only lexical relevance, **not scientific quality, proof, or population applicability**. Query matches and weak topic matches are labeled; DOI metadata is not evidence.
- Added `backend/app/criteria.py`: a **versioned, separate, read-only registry** with the **nine Discover, seven Validate, and five cross-cutting criterion types** from the 11-page *Criteria Types for the Agent Workflow* PDF. The four additional phases have architecture-only lists (2+5+6+4 types).
- New project-scoped criteria dashboard shows unknowns, basic qualified-evidence coverage and evidence IDs. **It deliberately does not invent scores or change the existing GO/STOP backend verdict.** A matched excerpt can qualify as a record to review but never prove truth.
- New API endpoints: `GET /api/criteria`, `GET /api/projects/{id}/criteria`, `GET /api/projects/{id}/research-plan`. Project-specific endpoints require existing access tokens. Future audit entries for phase runs, founder decisions, and locked experiments include the catalog version.
- Kept existing SQLite immutable decisions, experiment pre-registration, safety rules, no publishing or payment actions, and the Windows host-Ollama Docker override.

## Verified in this environment

| Check | Result |
|---|---|
| Backend test suite (existing + v0.4 additions) | **58 passed** |
| Python compileall | Passed |
| JavaScript syntax via Node `--check` | Passed |
| HTML element/ID references and duplicate rail regression test | Passed |
| Crossref metadata ranking using a controlled mocked HTTP response | Passed |
| Existing safety, founder approval, evidence, experiments and deterministic verdict tests | Passed |
| Browser end-to-end smoke test | **BLOCKED by environment policy** (`net::ERR_BLOCKED_BY_ADMINISTRATOR`) |
| Live Crossref query from this environment | **Not verified**; the user previously confirmed v0.3 Crossref worked on Windows |
| Actual Windows Docker + Ollama v0.4 run | **Not verified**; user must run locally |

Mock model / mocked Crossref are used **only inside tests**; the shipped app has no mocked business evidence or fabricated live AI output.

## Important limitations vs. the PDF

- Registry and coverage dashboard **do not perform** rubric-specific scored AI judging, weighted aggregation, auditable founder-adjusted thresholds or 2–3 direction ranking. Those are future tasks. Existing deterministic Validation verdict remains live, separate and unmodified.
- `SOURCE_MATCHED` means excerpt found in fetched HTML; it is **not proof of scientific rigor or factual truth**.
- Crossref does not cover real-world competitor pricing, national census data, customer interviews or purchase decisions comprehensively. The product **does not automatically verify customer demand**.
- Build, Commercial, Launch, Operate are **architecture only**.
- A normal user should not use manually invented experimental data as real evidence. Use a test-only workspace when testing synthetic flows.
- The application uses a prototype browser capability token rather than production-grade account auth; keep it local.

## Windows upgrade without destroying project history

1. In the old v0.3 PowerShell Docker session, press `Ctrl+C` to release port 8000.
2. Unzip v0.4 in a **separate folder**. Do **not** delete v0.3 or its Docker volumes.
3. Inside `founder-os` directory, run:

   ```powershell
   docker compose -f docker-compose.yml -f compose.windows.yaml up --build
   ```

4. Open `http://localhost:8000` and hard refresh (`Ctrl+Shift+R`).
5. Because this is the same Compose project name and SQLite volume, the existing project may reappear (depending on local volume naming); **do not delete the volume**. If the browser's stored project token no longer matches the active database, create a new project; never paste your token into chat.
6. On the Research & Evidence page inspect the three suggested queries and the **Criteria audit** panel. Search a topic, open one DOI independently and verify its actual sample before entering an exact quote.
7. If you have Playwright installed on Windows, `python scripts/ui_smoke.py` runs a test-only disposable database. It uses a fake model **only in the test harness**; never submit those test data as customer research.

A better local verification path is to run the browser smoke test on your machine and check both desktop and narrow-screen layout before hackathon submission.

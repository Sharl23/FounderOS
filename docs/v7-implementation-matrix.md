# V7 implementation matrix

Legend: **EXISTING** (kept from v0.4) · **IMPLEMENTED** (new/changed in v0.7) · **TESTED** (automated test passes) · **NOT VERIFIED** (needs the founder's machine) · **LIMITATION**.
Baseline: v0.4 as supplied, 58 tests passing (git commit "Baseline: FounderOS v0.4 as supplied"). v0.7: 212 tests passing, 44/44 real-browser checks.

| V7 promise | Status | Where | Limitation / note |
|---|---|---|---|
| Preserve SQLite, approvals, audit, experiment locking, safety, Ollama path | EXISTING + TESTED | `db.py`, `main.py` | Migration is additive (`schema_migrations`), tested on a v0.4 database (`test_v04_database_migrates_...`) |
| Route-separated journey: /projects, brief, safety, discovery, research, experiments, decision (+ audit, roadmap, help) | IMPLEMENTED + TESTED | `static/app.js`, `main.spa` | Browser test with TEST_ONLY model |
| One canonical sidebar, compact top bar, model status, no raw token or JSON in primary view | IMPLEMENTED + TESTED | `index.html`, `style.css` | Raw JSON only in "Advanced" drawers |
| Light default + dark theme, local fonts, responsive 1366/390, keyboard, skip link, reduced motion | IMPLEMENTED + TESTED (overflow, skip link, both themes rendered) | `style.css` | Contrast checked visually, not with an automated audit tool |
| Backend-enforced navigation; disabled CTAs state the reason; dialogs state what approval grants | IMPLEMENTED + TESTED | `app.js`, `main.decide` | — |
| Draft persistence on refresh; input kept on model failure | IMPLEMENTED + TESTED | localStorage drafts; project saved before any model call | — |
| Five criterion kinds as code; criteria in a versioned file with eight parts | IMPLEMENTED + TESTED | `policy/criteria.yaml`, `criteria.py` | Numbers are TEAM_ASSUMPTION |
| 9 Discover / 7 Validate / 5 cross-cutting criteria evaluated | IMPLEMENTED + TESTED | `criteria.evaluate_discover`, `evaluate_validate` | Scored criteria need ledger evidence; judge quality on the live 1.5B model NOT VERIFIED |
| Gatherer → verifier → ledger → per-criterion judge → deterministic gate → founder | IMPLEMENTED + TESTED | `research.py`, `main.run_judges`, `criteria.validate_judgment` | — |
| No 21 model calls on an unresearched idea; cached judgments | IMPLEMENTED + TESTED | `judgeable_rows`, `judgments` table | — |
| Founder adjusts weights/pass marks before a run; new version invalidates stale conclusions; knockouts locked | IMPLEMENTED + TESTED | `POST /criteria/config` | — |
| Policy version/hash + config hash + evaluation hash on every decision | IMPLEMENTED + TESTED | `decisions` columns | Application-level append-only (SQLite triggers), not tamper-proof storage |
| Twelve safety rules, exact semantics, three-way outcome, UNKNOWN_SOURCE | IMPLEMENTED + TESTED | `policy/safety_rules.yaml`, `safety.py` | English patterns + escalate-only model flags; can miss paraphrases |
| Each rule: positive / negative / borderline / negated / absent-source fixtures | TESTED | `test_safety_rules_v7.py` | Borderline/negated omitted where not meaningful (noted in file) |
| Official legal source: hard stop only when fetched, excerpt-verified, official domain | IMPLEMENTED + TESTED | `POST /safety/sources` | "Official domain" is a suffix heuristic |
| Re-screen after every brief revision and on agent outputs | IMPLEMENTED + TESTED | `store_safety`, `screen_agent_output` | — |
| Research plan by bucket (problem, market, competitors, feasibility, viability, safety) with editable queries | IMPLEMENTED + TESTED | `research.plan` | — |
| Crossref, OpenAlex, World Bank adapters; rate-limit backoff; honest statuses | IMPLEMENTED + TESTED (mocked) | `research.py` | Live access NOT VERIFIED here (sandbox had no internet). OpenAlex may require a free key under its current terms; set `OPENALEX_API_KEY` if it returns ACCESS_DENIED |
| Competitor / general web search | LIMITATION (honest) | plan bucket COMPETITORS | `DISCOVERY_NOT_AVAILABLE`: no compliant free search API; queries + manual URL inspection instead |
| Candidate states CANDIDATE_METADATA, FETCHED, EXCERPT_VERIFIED (= EXCERPT_MATCHED), EVIDENCE_ADDED, REJECTED, FETCH_FAILED; METADATA_ONLY | IMPLEMENTED + TESTED | `research_candidates` | "Source reviewed" is the founder's add/reject action |
| SSRF: https only, private/metadata/host.docker.internal blocked, every redirect re-validated, size/time/content-type caps | IMPLEMENTED + TESTED | `research.safe_fetch` | DNS-rebinding window between check and connect remains (documented) |
| Duplicates/syndication, stale + off-market, contradictions, injection in pages | IMPLEMENTED + TESTED | `insert_evidence`, `evidence_quality` | — |
| Model health: reachability ≠ inference; OOM GPU/CPU, not found, unreachable, timeout codes | IMPLEMENTED + TESTED | `llm.health`, `/api/model/health?probe=1` | Live probe NOT VERIFIED here |
| Windows host-Ollama override without pulling the Ollama image | IMPLEMENTED + config-validated | `compose.windows.yaml` | Run on Windows NOT VERIFIED |
| Conservative resource settings (num_ctx 2048, optional num_gpu=0, num_thread) | IMPLEMENTED + TESTED | `llm.options` | — |
| Phases 3–6 with 17 criteria documented; not presented as running | IMPLEMENTED (docs + roadmap screen) | `architecture.md`, `/roadmap` | Optional P1 slices (spec export, pricing drafts) NOT implemented |
| Live fresh-brief latency numbers | NOT VERIFIED | `scripts/live_check.py` | Run on the demo laptop; no numbers are pre-filled |

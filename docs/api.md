# HTTP API overview (v0.7)

Base `http://localhost:8000`. All project endpoints require `X-Project-Token: <access_token>` (capability token returned **once** at creation; prototype security, not production auth). Unauthenticated calls → 401; wrong token → 404.

| Method | Path | Action |
|---|---|---|
| GET | `/api/health` | Model tag + live Ollama readiness (`ollama_reachable`, `model_pulled`) |
| POST | `/api/warmup` | Load the model into RAM once (do before a timed demo); returns observed ms |
| POST | `/api/projects` | Create project; immediate deterministic pre-screen (`prescreen.status`) |
| GET | `/api/projects/{pid}` | Full snapshot: brief, safety, runs, evidence, experiments, decisions, audit, passport, phases |
| POST | `/api/projects/{pid}/refine` | Local LLM → typed brief with provenance; persists safety assessment per brief version; invalidates approvals |
| POST | `/api/projects/{pid}/clarify` | Founder corrections → new brief version, re-screen, invalidates approvals |
| POST | `/api/projects/{pid}/safety/acknowledge` | REVIEW_REQUIRED → research-only clearance for that brief version (403 on BLOCK) |
| POST | `/api/projects/{pid}/phases/discover/run` | Discovery agent (needs safety clearance); pending gate |
| POST | `/api/projects/{pid}/phases/validate/run` | Only after APPROVED discovery on the current brief; backend verdict + agent explanation |
| POST | `/api/projects/{pid}/phases/{phase}/decision` | APPROVE / REVISE / PIVOT / STOP bound to run id, report hash, brief version |
| POST | `/api/projects/{pid}/phases/{build,commercial_setup,launch,operate_learn}/run` | 501 — architecture only |
| POST | `/api/projects/{pid}/evidence` | Secondary source (fetched+checked) or founder-run customer research (consent required) |
| GET | `/api/projects/{pid}/experiments/suggest` | Next best experiment (proposal; founder approves thresholds) |
| POST | `/api/projects/{pid}/experiments` | Draft experiment |
| POST | `/api/projects/{pid}/experiments/{id}/lock` | Pre-register (freeze criteria; stamps `locked_at`) |
| POST | `/api/projects/{pid}/experiments/{id}/revise` | New version; old results retire; audit event |
| POST | `/api/projects/{pid}/experiments/{id}/result` | Founder-reported result vs frozen criteria (needs `criteria_hash`) |
| POST | `/api/projects/{pid}/external-action` | Always 403 (PUBLISH/SEND/SPEND/SIGN/PAY/REFUND/TRANSFER/CONTACT) |

**Decision body** (all fields required):
```json
{"run_id":"<latest run id>","report_hash":"<64-hex from the run>","brief_version":1,"decision":"APPROVE","feedback":"","acknowledge_risk":false}
```
Rejections: 409 stale/duplicate/mismatched run, hash mismatch, brief changed; 403 safety block; 422 missing feedback, missing acknowledgment when approving against STOP/PIVOT/REVISE, or instruction-like feedback. Approval scope is always `RESEARCH_ONLY`.

**Secondary evidence body**:
```json
{"kind":"SECONDARY_BACKGROUND","dimension":"desirability","claim":"…","url":"https://…","excerpt":"exact passage","direction":"SUPPORTS","relevance":"CLAIM_RELEVANT","title":"…","publisher":"…","published_on":"2024","geography":"Egypt"}
```
**Customer research body**:
```json
{"kind":"CUSTOMER_BEHAVIOR","dimension":"demand","claim":"4 of 12 joined the waitlist","direction":"SUPPORTS","method":"form shared in class","sample_size":12,"positives":4,"collected_from":"2026-11-10","consent_confirmed":true}
```
**Experiment draft** → **lock** `{"version":1,"criteria_hash":"…","confirm":"I_PREREGISTER_THESE_CRITERIA_BEFORE_COLLECTING_RESULTS"}` → **result** `{"version":1,"criteria_hash":"…","sample_size":12,"positives":1,"method":"…","collected_from":"…","collected_to":"…","consent_confirmed":true}`.


## Added in v0.7

| Method | Path | Action |
|---|---|---|
| GET | `/api/model/health?probe=1` | Daemon reachable, model installed, and (with probe) a real 1-token inference; codes READY, MODEL_OOM_GPU, MODEL_OOM_CPU, MODEL_NOT_FOUND, OLLAMA_UNREACHABLE, MODEL_TIMEOUT |
| GET | `/api/policy/safety` | The twelve rules (version + hash) |
| GET | `/api/criteria` | Criteria catalog (9/7/5 live + 17 architecture-only), scale, caps, default config |
| GET | `/api/projects/{pid}/summary` | Compact status for the projects list |
| POST | `/api/projects/{pid}/safety/sources` | Attach an official source to a legal rule (fetched, excerpt-verified, official-domain heuristic) |
| POST | `/api/projects/{pid}/criteria/config` | Founder changes weights/pass marks → new config version, approvals invalidated; knockouts not editable (422) |
| POST | `/api/projects/{pid}/criteria/evaluate` | Re-evaluate the Discover gate; judge calls only where accepted evidence exists (cached) |
| GET | `/api/projects/{pid}/criteria` | Latest Discover evaluation and whether it is stale |
| GET | `/api/projects/{pid}/research/plan` | Bucketed research plan from the brief (nothing sent) |
| POST | `/api/projects/{pid}/research/run` | Run selected plan items on Crossref / OpenAlex / World Bank; stores candidates, never evidence |
| GET | `/api/projects/{pid}/research` | Search history and candidates |
| POST | `/api/projects/{pid}/research/inspect` | Fetch a founder-chosen public page (SSRF-guarded) and offer passages from its text |
| POST | `/api/projects/{pid}/research/candidates/{cid}/fetch` | Inspect a candidate's landing page |
| POST | `/api/projects/{pid}/research/candidates/{cid}/reject` | Reject with a reason |
| POST | `/api/projects/{pid}/research/candidates/{cid}/add` | Founder review: add one verified passage (or labelled metadata / World Bank datum) to the ledger |

Discover decisions also accept `evaluation_hash`; a decision is refused (409) when evidence, settings or the brief changed since the last evaluation. Model failures return 503 with `{code, message, advice, note}`. Deep links `/projects/...`, `/roadmap`, `/help` serve the app shell.

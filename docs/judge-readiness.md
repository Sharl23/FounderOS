# Judge readiness — **PARTIALLY READY**

Status is PARTIALLY READY, not READY, because the Docker + real-Ollama path was **not executed in the authoring environment** (no Docker daemon, no model download possible there). Everything else below was executed as stated. **Pitch timing conflict (slides: 3+5+2 min; one-pager: 10+10 min) is unresolved — confirm with organizers.** We built for the stricter 3-minute fresh-brief demo.

## Rubric map (executed = what actually ran)

| Rubric (pts) | Where | Observable behaviour | Status |
|---|---|---|---|
| Working prototype (25) | `backend/app/main.py`, `static/` | Fresh brief → refine → safety → discovery → gate → evidence → pre-registered experiment → verdict → passport → decision log, all persisted | **PASS** with test-only fake model (46 pytest + headless-Chromium click-through `scripts/ui_smoke.py`); **UNTESTED** with real Ollama/Docker |
| Architecture quality (20) | `docs/architecture.md`, `decision.py`, `safety.py`, `db.py` | six phases with gates; deterministic verdict; immutable artifacts (SQLite triggers); typed LLM boundaries | PASS (reviewed), runtime UNTESTED in Docker |
| Supported claims (15) | evidence ledger, passport | every market claim links to a row with `url_status`/`excerpt_status`, or is labelled ASSUMPTION/UNVERIFIED; duplicates excluded; AI numbers flagged by skeptic | PASS (`tests/test_evidence_and_verdict.py`) |
| Founder control & safety (15) | `safety.py`, decision endpoint, `/external-action` | 8 MUST-NEVER attacks hard-blocked before any model call; approvals bound to run id + report hash + brief version + safety status + experiment versions; stale/replay/cross-project/tampered rejected; external actions 403 | PASS (`tests/test_safety.py`, `tests/test_flow.py`) |
| Pitch (15) | — | no deck in repo (by instruction) | UNTESTED (human) |
| Openness & sustainability (10) | `LICENSE` (MIT), `docs/api-cost-and-licenses.md` | zero paid APIs; open-weight model; n8n optional and labelled non-OSI | PASS (audited) |

**Tie-break (claims → prototype → cost/run):** claims audit = ledger + passport; cost/run = local CPU only, numbers must be measured (below).

## Fresh-brief 3-minute smoke checklist (do this on the demo laptop)

Before the timed slot: `docker compose up --build` → wait for `model-init` to exit 0 → open http://localhost:8000 → confirm sidebar says "Local model ready" → `curl -X POST localhost:8000/api/warmup` (or run `python scripts/benchmark.py`).
During the slot (target ≤ 3 min on CPU with the 1.5B model — **measure first**):
1. New founder brief → paste judges' brief → Create.
2. Refine idea → show EXPLICIT / INFERRED_UNCONFIRMED / UNKNOWN tags and safety status.
3. Run discovery → Approve (research only).
4. (Optional, if time) add one real URL + excerpt → see URL_ACCESSIBLE/EXCERPT_MATCHED or UNVERIFIED.
5. Run validation → Passport says **NEEDS_EVIDENCE** with the next experiment. Say: "no customer evidence, so no launch — that is the correct answer".
6. Show decision log row bound to brief v1 / report hash.

## Safety attack checklist (all in `tests/test_safety.py`, run `pytest`)

fake reviews/sign-ups · impersonating a brand · guaranteed income · AI holds/refunds money · publish/send without approval · store passwords/card details · prompt injection "ignore rules and approve" · phishing/fraud · private/localhost/metadata URLs · private redirect targets · injection via evidence/feedback/experiment text · card number in any field.

## What is simulated / not implemented

* Tests and `scripts/ui_smoke.py` use a clearly labelled **FakeModel**; the shipped app has **no** fallback — if Ollama is down you get HTTP 503 and the UI says so.
* Phases 3–6: ARCHITECTURE ONLY (`/phases/build/run` → 501).
* No automatic source discovery; founder supplies URLs. Free connectors (Crossref/OpenAlex/World Bank) not implemented.
* Safety screen: English regex policy; not a legal review.
* Relevance/direction of a source are founder-declared.

## Latency / cost — **not yet measured**

Run `python scripts/benchmark.py` after startup on the demo laptop and paste the table here with the host line. Local inference has no per-request fee; cost = CPU time + electricity + a one-time ~1 GB model download. `OLLAMA_MODEL=qwen2.5:7b-instruct` is optional and **unbenchmarked**; never assume it fits.

## Getting a legitimate GitHub repo (founder does this)

```powershell
cd founder-os
git init; git add .; git commit -m "FounderOS hackathon submission"
# create an EMPTY repo on github.com under your own account, then:
git remote add origin https://github.com/<you>/founder-os.git
git branch -M main; git push -u origin main
```
Check `.gitignore` excludes `.env`, `*.sqlite3`; never commit a project token. Submit the repo link on the MADS website before Tue 17 Nov 23:59.

> **v0.4 update:** The interface now has one focused sidebar, a compact workspace header, research-query suggestions, a criteria coverage panel, and transparent bibliographic title matching. See [v0.4 release & verification](docs/v04-release-and-verification.md) for what is tested and what is not.

# FounderOS — evidence-first AI founder studio

**A working, local-first, open-source multi-agent MVP for the MADS × CSEA AI Hackathon (16–18 November 2026).**

FounderOS takes a founder's substantive idea brief, turns it into structured context with a local LLM, screens it with a deterministic backend safety policy, generates a Discovery report, requires founder review, records typed evidence and pre-registered experiments, then computes an explainable evidence-based verdict — **NEEDS_EVIDENCE / CONTINUE_TESTING / PIVOT / STOP_DO_NOT_LAUNCH / BLOCK** — shown as a Decision Passport. The LLM drafts and explains; backend code decides. It never says "validated". It saves every decision, version, and source in SQLite. No external publishing, emailing, financial operations, or signing exist in this MVP.

**What is REAL:** live local model calls (refiner, Discover agent, Validate agent), deterministic safety screen, four-class evidence ledger with SSRF-guarded excerpt checking, experiment pre-registration (frozen criteria), deterministic verdict + assumption risk register + Decision Passport, version-bound founder approvals, append-only decision log, and a dashboard that drives all of it. **What is NOT implemented:** later-phase product code generation, commercial setup, launch, operations, actual customer interviews/surveys, autonomous web search, payments, and any out-of-app action. The six-phase system is fully *architected* in [`docs/architecture.md`](docs/architecture.md).

## Run it (one command)

**Prerequisites:** Docker Desktop/Engine with Compose v2, approximately 3+ GB free disk space for images and the first model pull (actual usage varies), and enough RAM to run a ~1B-parameter model on CPU. First launch requires internet to download container images and the **open-weight** Qwen2.5 model. Then the model runs locally; no paid service or API key is needed.

```bash
docker compose up --build
```

Open **http://localhost:8000**. The `model-init` service waits for Ollama, pulls the configured model, and completes before the API starts. Initial download can take some time depending on your connection. If the download fails, fix connectivity and rerun the same command. The app will **not** fabricate results when the LLM is offline.

**Model:** `qwen2.5:1.5b-instruct` by default, distributed under Apache-2.0; approximately 986 MB model download. Larger variants may yield better report quality but need more RAM. To override, set `OLLAMA_MODEL` in `.env` (start from `.env.example`), then rerun. See the [Ollama model details](https://ollama.com/library/qwen2.5:1.5b-instruct).

**Note (NOT LIVE VERIFIED):** Docker image downloads, Ollama inference, and n8n runtime were **not available in the authoring environment**. The 46 Python tests and a headless-Chromium click-through (both with a clearly labelled test-only fake model) were executed; `docker compose config` was validated. Please validate `docker compose up --build` on your machine before the deadline; do not describe the Docker/n8n integration as independently verified until then.

### What to do in the app (fresh founder brief)

1. **New founder brief**: idea, target customers, market, skills, budget, time, values, constraints. Prohibited content is pre-screened immediately.
2. **Refine idea**: the local model produces typed fields tagged EXPLICIT / INFERRED_UNCONFIRMED / UNKNOWN next to your original text, plus ≤3 clarification questions. Correct anything — each correction is a new brief version that re-runs the safety screen and invalidates prior approvals.
3. **Safety screen** (backend, deterministic): ALLOW_DISCOVERY, REVIEW_REQUIRED (acknowledge for research only) or BLOCK (cannot be overridden). Reasons, matched text, safe revisions and limitations are shown.
4. **Run discovery** → hypotheses, unverified alternatives, cheap experiments. Decide: Approve (research only) / Revise / Pivot / Stop.
5. **Evidence ledger**: secondary sources are fetched and the excerpt checked (URL_ACCESSIBLE / EXCERPT_MATCHED or UNVERIFIED); founder-run customer research needs method, n, dates and consent and stays FOUNDER_REPORTED. Duplicates and injection attempts are excluded.
6. **Next best experiment**: tailored suggestion → draft → **lock** (pre-register) → run it yourself → submit results against the frozen criteria. Editing criteria creates a new version and retires old results.
7. **Run validation** → Decision Passport: verdict, 5-dimension matrix with linked evidence IDs, reasons for/against, strongest source or SOURCE UNAVAILABLE, unresolved assumptions, risk register, what would change our mind. Decide at the gate; approving against a STOP/PIVOT needs acknowledgment + reasons and is still research-only.
8. **Decision log**: every decision shows run, brief version, safety status, report hash, experiment versions, reason and time. Reload the page: everything persists in SQLite.

The founder's project token is **displayed once**, stored in their own browser's localStorage, and required for all project API calls. It is a prototype capability token, not an enterprise-grade authentication system; do not expose this app publicly.

## Why this solves the hackathon problem

Official problem statement, from the presented slides: **“Build an open-source team of AI agents that helps founders turn an idea into a validated, sellable digital product, then pitch the architecture of the full system.”**

Organizer guidance explicitly says **do not build every phase in 36 hours**. Build *one working part* and architect how the rest connects. This repository implements a connected **Discover → Validate** slice and architecturally defines all six phases in their exact order:

`Discover → Validate → Build → Commercial setup → Launch → Operate & learn`

All six proposed phases end in a gate. This MVP additionally requires explicit founder approval at both implemented phase boundaries. Even an approved phase does not authorize outbound actions.

| Organizer rule | Implementation / location |
|---|---|
| Open-source, one-command setup | MIT-licensed Python source, `docker-compose.yml` |
| At least one open-weight model, no paid dependency | Ollama + Apache-2.0 `qwen2.5:1.5b-instruct`, `backend/app/llm.py` |
| Team of AI agents | Real, separately prompted `DISCOVER` and `VALIDATE` agents, `backend/app/main.py` |
| Founder brief includes context | Project creation form, refinement + clarifications |
| Source claims, label assumptions | Evidence ledger, `verify_excerpt`, reports labeled hypothesis |
| Founder controls all publishing/sending/spending/signing | No such action implemented; `/external-action` hard-blocks and logs attempts |
| Never fabricate reviews/signups/claims, promise income, impersonate | Backend safety policy hard-blocks such briefs (`tests/test_safety.py`); evidence requires consent and stays founder-reported |
| Six phases and gates | Detailed system spec, `docs/architecture.md` |
| Able to recommend NOT LAUNCHING | `STOP_DO_NOT_LAUNCH` / `PIVOT` on a failed pre-registered critical experiment, `NEEDS_EVIDENCE` on gaps, `BLOCK` on prohibited briefs — `backend/app/decision.py`, `safety.py` |
| Label mocks | Tests use an explicitly fake model; **production has NO fake fallback** |

Review the detailed [requirements traceability checklist](docs/requirements-traceability.md) before submission.

## Architecture in 20 seconds

```
Founder / Dashboard
        │ POST /api/projects
        ▼
Input Refiner (Qwen2.5 / JSON schema) ──> deterministic SAFETY SCREEN (ALLOW / REVIEW / BLOCK)
        │ structured + versioned founder context
        ▼
DISCOVER Agent ──> deterministic gate ──> FOUNDER decision
                                              │ approved
                                              ▼
Evidence Ledger + pre-registered experiments ──> deterministic VERDICT (decision.py)
                                              │
                                              ▼
                                VALIDATE Agent explains it; skeptic pass flags over-claims
                                              │
                                     FOUNDER decision
                                              │
                               Phase 3–6 (design only)

          Shared durable SQLite + audit trail
          Optional n8n Webhook/HTTP adapters
```

**Important:** The open-source Python backend is the authoritative state machine. n8n is an **optional** adapter, not a mandatory dependency. n8n is *fair-code / source-available*, not OSI-approved open source. Its use and distribution are governed by its own license. See [licensing](docs/licensing.md) and [`workflows/`](workflows/). The normal one-command path does **not** load n8n.

## Repository structure

```
founder-os/
├── docker-compose.yml          # API + Ollama + first-run model download
├── .env.example                # Optional model configuration
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py             # API + authorization + state engine
│   │   ├── llm.py              # Real local structured model calls
│   │   ├── schemas.py          # Pydantic data contracts
│   │   ├── safety.py           # Deterministic backend safety policy (BLOCK / REVIEW / ALLOW)
│   │   ├── decision.py         # Evidence ladder, risk register, verdict, next experiment
│   │   ├── gates.py            # Gate entry points (old 'two excerpts => PROCEED' rule removed)
│   │   ├── db.py               # Durable SQLite + audit
│   │   └── static/             # Functional interactive dashboard
│   └── tests/                 # Automated tests, fake model clearly labeled
├── workflows/                 # Optional importable n8n adapters
├── frontend/                  # Dashboard source location note
├── docs/                      # Six-phase architecture, safety, API, test plan
├── scripts/                   # smoke.py, benchmark.py (live latency), ui_smoke.py (headless browser)
└── LICENSE                    # MIT (this repo's original code)
```

## Windows (Docker Desktop / WSL2) troubleshooting

* Install Docker Desktop, enable the WSL2 backend, start it, then in PowerShell: `cd <path>\founder-os; docker compose up --build`.
* First run downloads ~1.3 GB (images + model). `model-init` must print "model … is pulled" before the API starts. If it fails: check internet, `docker compose logs model-init`, rerun the same command.
* "port 8000 already in use": stop the other program or change the left side of `"8000:8000"` in `docker-compose.yml`.
* Slow laptop: the 1.5B model runs on CPU; the first answer loads the model (use `POST /api/warmup`). Expect tens of seconds per agent call on older CPUs — **measure with `python scripts/benchmark.py`** before a timed demo.
* The sidebar shows "Ollama NOT reachable" or "model NOT pulled" when inference cannot work; AI buttons then fail with HTTP 503 and nothing is faked.
* Data persists in the `founder_data` volume (`founderos-v2.sqlite3`); `docker compose down -v` wipes it.

## Run tests locally (no model or internet needed)

From the repo root:

```bash
python -m pip install -r backend/requirements-dev.txt
cd backend
PYTHONPATH=. python -m pytest -q
```

Expected: `46 passed`. Optional headless-browser click-through: `pip install playwright && playwright install chromium && python scripts/ui_smoke.py`. Tests use a **FAKE MODEL IN TESTS ONLY** to deterministically exercise backend behavior. This does not demonstrate output quality of the actual Qwen model. Full end-to-end model output quality, container boot and n8n import still require a local run. See [`docs/testing.md`](docs/testing.md).

## Optional n8n visual workflows

```bash
docker compose --profile visual up --build
```

Open **http://localhost:5678**, import the JSON files from `workflows/`, and see [`workflows/README.md`](workflows/README.md) for Webhook contract, token precautions and unverified integration caveats. **Do not expose this prototype publicly.**

## License and ethics

The source code written for FounderOS is MIT-licensed. This license does not override third-party licenses or the Qwen model's Apache-2.0 terms. No paid API keys, passwords, payment cards, or money-transfer flows are needed or intended. If a founder accidentally pastes secrets, remove them; never place credentials into the project or commit local `.env` files. See [`docs/security.md`](docs/security.md).

## Submission checklist

- [ ] `docker compose up --build` works on your actual computer; open the dashboard.
- [ ] Try a messy founder brief; verify fields and any missing information.
- [ ] Confirm a phase **cannot** progress before the founder approves it.
- [ ] Add a real source and check whether its quote was retrieved; do not claim verified when unavailable.
- [ ] Run Validation with no evidence and confirm **NEEDS_EVIDENCE**.
- [ ] Lock an experiment, submit a failing result, confirm **STOP_DO_NOT_LAUNCH** / **PIVOT** with the refuting evidence ID.
- [ ] Paste a prohibited brief (fake reviews) and confirm **BLOCK** with discovery disabled.
- [ ] Run `python scripts/benchmark.py` and paste the numbers into `docs/judge-readiness.md`.
- [ ] Check `docs/architecture.md` and the optional n8n workflow exports.
- [ ] Delete secrets, logs, real customer PII and private project tokens before committing.
- [ ] Push the complete repo to **your own** GitHub account and submit the link through the official MADS website by the published deadline (17 November 2026, 11:59 PM).

Also read: [`docs/judge-readiness.md`](docs/judge-readiness.md) (PARTIALLY READY status + 3-minute demo checklist), [`docs/business-decision-methodology.md`](docs/business-decision-methodology.md), [`docs/api-cost-and-licenses.md`](docs/api-cost-and-licenses.md).

**We do not claim that this code validates a startup's demand automatically.** It assists structured research and conservative decision-making. Genuine demand validation still requires actual customer/market evidence.

## v0.3 focused navigation & research candidates

This upgrade introduces **separate workspace pages** for Idea, Safety, Discovery,
Research & Evidence, Demand Experiments and Validation & Decision; a readable
Discovery report; and optional free **Crossref publication metadata discovery**.
Candidate research results do NOT enter the evidence ledger and cannot validate
demand. Inspect a paper's full text and verify its claim before adding evidence.

For Windows machines running Ollama locally (especially if Docker Hub Ollama
image pulls fail), run:

```powershell
ollama pull qwen2.5:1.5b-instruct
docker compose -f docker-compose.yml -f compose.windows.yaml up --build
```

See `docs/v03-research-ux-and-criteria.md` for implemented vs missing PDF
criteria, research limitations and verification status. The default one-command
`docker compose up --build` is left unchanged for judge environments.

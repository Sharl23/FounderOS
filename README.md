# FounderOS: an evidence-first venture builder

FounderOS is an open-source, local-first team of AI agents. It takes a founder's idea through six phases:

1. Discover
2. Validate
3. Build
4. Commercial setup
5. Sell, deliver and get paid
6. Operate and learn

Each phase ends in a gate that code decides. Moving on needs a founder approval that the server enforces. A small open-weight model, running locally through Ollama, drafts the text.

**Phases 3-6 run in MOCKED / TEST MODE.**

- The website it builds is a DEMO-ONLY prototype that uses demo data.
- Payments go through a built-in signed simulator.
- Nothing is published, sent, spent, signed or deployed.

Version 0.9.0 (17 Nov 2026). Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md). Outputs of a real run: [`outputs/`](outputs/README.md) and [`decision_log.json`](decision_log.json).

## Quickstart

```bash
docker compose up
```

1. Open **http://localhost:8000**.
2. The app looks for Ollama on your machine (the host) at `http://host.docker.internal:11434`. To give it a model, install [Ollama](https://ollama.com) and run `ollama pull qwen2.5:1.5b-instruct`.
3. To check the model works, click the model status in the top bar and run the real one-token test.

Without a model, the interface still opens. Phases 1-2 then say plainly that the model is unavailable, and Phases 3-6 keep working, because they need no model.

- **Ollama in a container instead.** Set `OLLAMA_URL=http://ollama:11434` in `.env`, then run `docker compose --profile ollama up`.
- **Machine settings.** Copy `.env.example` to `.env`. On a GPU with 6 GB or less that runs out of memory, set `OLLAMA_NUM_GPU=0`. If RAM runs out, set `OLLAMA_NUM_CTX=1024`. Troubleshooting is in [`docs/user-guide.md`](docs/user-guide.md).
- **Reproduce `outputs/` and `decision_log.json`.** Run `pip install -r backend/requirements-dev.txt && python scripts/demo_run.py`.
- **Tests.** Run `python -m pytest -q` from the repository root.

## What works and what is mocked

| Area | Status | Notes |
|---|---|---|
| Phase 1 Discover: brief, 12-rule safety screen, discovery agent, Discover gate | Working | Model drafts; code screens and decides |
| Phase 2 Validate: research verification, pre-registered demand tests, verdict, decision log | Working | Customer results are founder-reported |
| Phase 3 Build: spec, user stories, acceptance criteria, HTML/CSS/JS generator, QA, revision loop, versions, sandboxed preview, ZIP export | Working | Template-based generator; DEMO DATA; a DEMO-ONLY build is never called validated |
| Phase 4 Commercial setup: unit economics, break-even, scenarios, pricing hypotheses, business models, terms checklist | Working | Every input is an ASSUMPTION; not financial or legal advice |
| Phase 5 payment provider | MOCKED | Built-in HMAC-signed simulator, TEST MODE only; no live mode exists |
| Phase 5 checkout, idempotent webhook, delivery link, refund and revocation, reconciliation | Working (against the mock) | No card data accepted or stored |
| Phase 5 publishing the sales page, emailing buyers | STUBBED | Not built on purpose: drafts only |
| Phase 6 metrics from recorded events, feedback with provenance, issues, recommendation, proposals back to Phase 1 or 3 | Working | Sales events are MOCKED, so results describe the simulation |
| Phase 6 real analytics or support inbox | STUBBED | Manual or MOCK_DEMO entries only |
| Founder approvals: bound to state, single use, expiring, stale or rejected ones refused, append-only history | Working | Enforced on the server |
| Model used by `scripts/demo_run.py` when Ollama is not running | STUBBED | Labelled offline stand-in; marked in every log entry it touches |

## Architecture

There is one FastAPI service with a vanilla-JS interface, SQLite storage and Ollama on the host.

- **The orchestrator** (`backend/app/orchestrator.py`) runs a six-phase state machine.
- **The agents** each have one role, with typed inputs and outputs, in `backend/app/agents/`:
  - product architect;
  - website builder;
  - QA;
  - revision;
  - commercial;
  - sales and delivery;
  - operations.

  The Phase 1-2 agents (refiner, discovery, validation and criterion judges) use the prompts in `prompts/`.
- **The gates** (`gates.py`) and **approvals** (`approval.py`) are code.
- **Sale to cash** runs through `payments.py`, `webhooks.py`, `delivery.py`, `refunds.py` and `reconcile.py`.

Details, the Mermaid diagram and the data flow are in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Models and free resources

- **Model:** `qwen2.5:1.5b-instruct` (Apache-2.0 open weights, about 1 GB) via [Ollama](https://ollama.com). It runs on a CPU, and a 6 GB GPU is optional.
- **Paid APIs, keys and accounts:** none are required.
- **Research sources:** free public services (Crossref, OpenAlex, World Bank), plus pages the founder brings. They may throttle requests, and failures are shown as failures.
- **Smaller model:** `OLLAMA_MODEL=qwen2.5:0.5b-instruct` is available, but only if you choose it. The authors did not benchmark it.
- **What has been tested:** the automated tests and `outputs/` were produced with the labelled offline stand-in, not with the model. Check the model on your own machine with `python scripts/live_check.py`.

Licences are listed in [`docs/api-cost-and-licenses.md`](docs/api-cost-and-licenses.md).

## Cost per run

About $0.00 per run: the model is local and no API is paid. The only costs are your computer's electricity and the one-time model download of about 1 GB. Token counts per run were not measured.

## Demo video

No demo video has been recorded yet. The link will be added here when one exists (3 minutes at most).

## What our system will NOT do

- Take real payments, store card data, or create merchant, bank or provider accounts.
- Publish pages, post to social media, send emails or messages, contact buyers, sign agreements, deploy, or spend money. The server refuses these actions even with an approval.
- Invent customer evidence, reviews, testimonials, signups or benchmarks. Demo and test data is labelled MOCK_DEMO, TEST_ONLY or DEMO DATA.
- Promise profits or give financial, investment, legal or health advice. Commercial figures are ASSUMPTIONS and CALCULATED SCENARIOS.
- Help build prohibited ventures: physical goods; financial, investment or crypto products; health or legal advice. The code safety screen stops these before any model call.
- Call a DEMO-ONLY prototype validated, launch-ready or production-ready.

## How the project stays alive after the hackathon

- **Maintainers.** The founding team maintains the project. Contributions follow [`CONTRIBUTING.md`](CONTRIBUTING.md) under the MIT licence.
- **Roadmap** (also in [`ARCHITECTURE.md`](ARCHITECTURE.md#roadmap)):
  1. A real payment provider in its own test mode, behind the same approvals.
  2. Model-assisted copy, with QA kept in code.
  3. Real opt-in analytics.
  4. Export and import of a venture.
- **Running costs.** Running it costs nothing beyond a laptop, so the project does not depend on funding to keep working. Any future funding would go to user research with founders, not to API bills.
- **Community.** Issues and pull requests are welcome. Policy files (`backend/policy/*.yaml`) and agent prompts (`prompts/`) are plain text, so non-programmers can propose changes.

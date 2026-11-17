# FounderOS — evidence-first venture decisions

Open-source, local-first team of AI agents for the MADS × CSEA AI Hackathon (Nov 2026). FounderOS helps a founder decide, with evidence, whether an idea deserves more of their time. **It evaluates and guides venture work; it does not build, publish, sell or launch the founder's product.**

The local open-weight model drafts and explains. **Code decides**: twelve written safety rules, 21 criteria from *Criteria Types for the Agent Workflow*, source verification, locked pass marks and every gate exit. The founder approves, revises, pivots or stops at each gate, and every approval means *research only*.

| Business phase | Status |
|---|---|
| 1 Discover (brief → safety → discovery agent → research → Discover gate) | **Live** |
| 2 Validate (demand tests → locked targets → result reading → decision passport) | **Live** |
| 3 Build · 4 Commercial setup · 5 Launch · 6 Operate & learn | **Architecture only** — documented with their 17 criteria, endpoints return 501, nothing simulated |

Judges: start with [`docs/README-for-judges.md`](docs/README-for-judges.md).

## Run it — one command (official path)

Prerequisites: Docker Desktop (Windows: WSL2 backend) or Docker Engine with Compose v2, ~3 GB disk, internet for the first download only.

```powershell
cd founder-os
docker compose up --build
```

Wait until `model-init` prints `model qwen2.5:1.5b-instruct is pulled`, then open **http://localhost:8000**. Click the model status in the top bar and run the one-token test before a timed demo: “installed” is not the same as “working”.

## Windows with Ollama already installed on Windows (optional override)

Use this if you run the Ollama app on Windows instead of the Ollama container. The official command above is unchanged.

```powershell
ollama pull qwen2.5:1.5b-instruct
ollama run qwen2.5:1.5b-instruct "Reply OK"        # must answer before you continue
cd founder-os
docker compose -f docker-compose.yml -f compose.windows.yaml up --build
```

In this mode Compose starts only the `api` container and reaches Ollama at `http://host.docker.internal:11434`; it does not pull the Ollama image.

### If the model will not load (out of memory)

FounderOS maps Ollama errors to plain codes and never switches models or shows simulated text.

| You see | Meaning | Do this |
|---|---|---|
| `MODEL_OOM_GPU` / `cudaMalloc failed: out of memory` | GPU memory too small or busy | Close GPU-heavy apps. In `.env` set `OLLAMA_NUM_GPU=0` (CPU only), restart. On host Ollama you can also set the Windows environment variable `OLLAMA_NUM_GPU=0` or `CUDA_VISIBLE_DEVICES=-1` and restart the Ollama app. |
| `MODEL_OOM_CPU` / `failed to allocate CPU_REPACK buffer` | Not enough free RAM | Close browsers with many tabs, IDEs and games; set `OLLAMA_NUM_CTX=1024` in `.env`; in Docker Desktop → Settings → Resources (or `%UserProfile%\.wslconfig` `memory=6GB`) give the VM more memory, then `wsl --shutdown` and restart Docker. Check free memory in Task Manager → Performance. |
| `OLLAMA_UNREACHABLE` | Ollama not running / wrong URL | Container mode: wait for `ollama` and `model-init`. Host mode: start the Ollama app; `http://localhost:11434` must answer in your browser. |
| `MODEL_NOT_FOUND` | Model not pulled | `ollama pull qwen2.5:1.5b-instruct` |
| `MODEL_TIMEOUT` | First load is slow | Press Retry; raise `OLLAMA_TIMEOUT_S`. |

Do not disable the Windows pagefile or kill unrelated processes. A smaller model (`OLLAMA_MODEL=qwen2.5:0.5b-instruct`) is your explicit choice only and was **not** benchmarked by the authors. Your input is saved before every model call, so a failure never loses it.

## The journey (seven screens, two live phases)

1. **Projects** — start a venture or continue one. Project keys stay in your browser.
2. **Brief** — your words next to structured fields marked *yours / inferred, confirm it / unknown*. Corrections create new versions and retire old approvals.
3. **Safety** — twelve checks (hard stop, needs your review, source not checked, no issue found). Hard stops cannot be overridden; reviews allow research only. Attach official sources for the legal checks.
4. **Discover** — the discovery agent's hypotheses as cards, the criteria scorecard (unknown is never zero) and the Discover gate decided by code.
5. **Research** — a plan built from your brief; Crossref, OpenAlex and World Bank searches; inspection of any public page you choose; exact passages into an immutable ledger; your own customer research (founder-reported).
6. **Demand tests** — suggestion aimed at the riskiest assumption; design check; **lock** before collecting; code reads real results as hit / near miss / clear miss / too little data.
7. **Decision** — verdict (Needs evidence, Continue testing, Pivot, Stop, Blocked), five dimensions with clickable evidence, what would change it, the agent's explanation labelled as AI text, printable. Plus the **decision log** and a **six-phase roadmap**.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -q                         # 212 tests; model and providers mocked (TEST_ONLY)
cd ..
pip install playwright && playwright install chromium
python scripts/ui_e2e.py                    # real browser through every screen (TEST_ONLY model)
python scripts/live_check.py                # LIVE: your model + free providers, writes docs/live-check-results.md
```

## What is honest about this prototype

- No paid API, key or account is required. Research providers are free public services that may throttle or be offline; failures are shown as failures.
- General web and competitor search is **not automated** (no compliant free search API). FounderOS proposes queries for you to run and verifies the pages you bring back.
- A verified excerpt proves the words are on the page, not that they are true; secondary sources never prove demand.
- Customer results are entered by you and stay *founder-reported, not independently verified*.
- The project key is a prototype capability token, not production authentication. Do not expose the app to the internet.

Docs: [architecture](docs/architecture.md) · [criteria methodology](docs/criteria-methodology.md) · [criteria & safety traceability](docs/criteria-traceability.md) · [implementation matrix](docs/v7-implementation-matrix.md) · [API](docs/api.md) · [security](docs/security.md) · [costs & licenses](docs/api-cost-and-licenses.md)

License: MIT (this repository). Third-party components and their licences: `docs/api-cost-and-licenses.md`. n8n (optional, off by default) is fair-code, not OSI open source.

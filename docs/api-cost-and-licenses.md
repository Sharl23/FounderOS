# API cost and licenses (audited 2026-11-17)

## Paid or keyed services required: **none**

Audit method: `grep -ri "api_key\|apikey\|bearer\|openai\|anthropic\|brave\|tavily\|serp\|exa\.\|ollama.com\|cloud" docker-compose.yml .env.example backend/ workflows/ README.md docs/` — the only hits are prohibitions in docs/prompts and the `reject_obvious_secrets` guard that refuses credential-looking input.

| Dependency | Role | Cost | License |
|---|---|---|---|
| Ollama server (`ollama/ollama:0.9.6` image) | local inference at `http://ollama:11434/api/chat` inside Compose | free, local | MIT |
| `qwen2.5:1.5b-instruct` (default) | open-weight model, ~986 MB pull on first run | free | Apache-2.0 |
| `qwen2.5:7b-instruct` (optional via `OLLAMA_MODEL`) | larger model; needs several GB more RAM; **not benchmarked here** | free | Apache-2.0 |
| Python 3.12, FastAPI, Uvicorn, Pydantic, httpx, BeautifulSoup4 | API | free | MIT / BSD / MIT / BSD / MIT |
| SQLite (stdlib) | persistence | free | public domain |
| PyYAML 6.0.2 | policy files | free | MIT |
| Instrument Sans, Newsreader (bundled `.woff2`, from Fontsource) | UI typefaces, served locally (no CDN) | free | SIL Open Font License 1.1 (licence files in `backend/app/static/fonts/`) |
| Crossref REST API | publication metadata | free, no key | public API; metadata largely CC0 |
| OpenAlex API | scholarly metadata | free; optional key/mailto via env | data CC0; check current access terms and quotas |
| World Bank Indicators API v2 | national statistics | free, no key | World Bank data, CC BY 4.0 for most indicators |
| Vanilla JS/CSS dashboard | UI | free | MIT (this repo) |
| Docker Engine / Compose | runtime | free (Docker Desktop is free for small businesses/personal use; check Docker's terms for larger orgs) | Apache-2.0 (engine) |
| **n8n** (`--profile visual`, optional, off by default) | optional visual adapter | free self-hosted | **Sustainable Use License — fair-code, NOT OSI open source, NOT MIT** |
| pytest, Playwright (dev/test only) | tests | free | MIT / Apache-2.0 |

**This repository's own code:** MIT (`LICENSE`). The complete stack is **not** all MIT: the model is Apache-2.0 and n8n (optional) is fair-code.

## External network use at runtime

* First run only: Docker image pulls and the Ollama model pull (internet needed once).
* Evidence ledger: bounded HTTPS GET of **founder-supplied public URLs** only (SSRF-guarded: HTTPS/443, no userinfo, DNS resolved to global IPs only, redirects not followed, 8 s timeout, 600 KB cap, HTML/plain text only). Offline → the row stays `UNVERIFIED`; nothing is invented.
* No search-engine API (Brave/Tavily/SerpAPI/Exa/Google) is used or required. Crossref, OpenAlex and World Bank are implemented as optional free providers (v0.7): the founder presses Run, failures show as OFFLINE / RATE_LIMITED / ACCESS_DENIED, and nothing is invented. Competitor and general-web search is not automated.

## Cost per run (honest note for the tie-break rule)

Local inference has **no per-request charge**. The cost is the laptop's CPU time and electricity, plus the one-time ~1 GB download. Observed latencies are **not** pre-filled here; run `python scripts/live_check.py` after `docker compose up --build` and paste the numbers into `docs/judge-readiness.md`.

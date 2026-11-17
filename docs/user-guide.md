# User guide: running, troubleshooting and the Phase 1-2 screens

Moved here from the README in v0.9 so the README stays short.

## If the model will not load (out of memory)

FounderOS maps Ollama errors to plain codes and never switches models or shows simulated text.

| You see | Meaning | Do this |
|---|---|---|
| `MODEL_OOM_GPU` / `cudaMalloc failed: out of memory` | GPU memory too small or busy | Close GPU-heavy apps. In `.env` set `OLLAMA_NUM_GPU=0` (CPU only), restart. On host Ollama you can also set the Windows environment variable `OLLAMA_NUM_GPU=0` or `CUDA_VISIBLE_DEVICES=-1` and restart the Ollama app. |
| `MODEL_OOM_CPU` / `failed to allocate CPU_REPACK buffer` | Not enough free RAM | Close browsers with many tabs, IDEs and games; set `OLLAMA_NUM_CTX=1024` in `.env`; in Docker Desktop → Settings → Resources (or `%UserProfile%\.wslconfig` `memory=6GB`) give the VM more memory, then `wsl --shutdown` and restart Docker. Check free memory in Task Manager → Performance. |
| `OLLAMA_UNREACHABLE` | Ollama not running / wrong URL | Container mode: wait for `ollama` and `model-init`. Host mode: start the Ollama app; `http://localhost:11434` must answer in your browser. |
| `MODEL_NOT_FOUND` | Model not pulled | `ollama pull qwen2.5:1.5b-instruct` |
| `MODEL_TIMEOUT` | First load is slow | Press Retry; raise `OLLAMA_TIMEOUT_S`. |

Do not disable the Windows pagefile or kill unrelated processes. A smaller model (`OLLAMA_MODEL=qwen2.5:0.5b-instruct`) is your explicit choice only and was **not** benchmarked by the authors. Your input is saved before every model call, so a failure never loses it.

## Phase 1-2 screens

1. **Projects** — start a venture or continue one. Project keys stay in your browser.
2. **Brief** — your words with the phrases used for each field highlighted. Each field is marked *typed by you*, *in your words (please confirm)*, *model suggestion* (never counts until confirmed), *not stated* (with one clear question) or *parser failed*. An idea-clarity (D02) box says exactly what is missing. Corrections create new versions and retire old approvals.
3. **Safety** — twelve checks (hard stop, needs your review, source not checked, no issue found). Hard stops cannot be overridden; reviews allow research only. Attach official sources for the legal checks.
4. **Discover** — the discovery agent's hypotheses as cards, the criteria scorecard (unknown is never zero) and the Discover gate decided by code.
5. **Research** — the **Criteria matrix**: all 67 team checks grouped under the five dimensions. Each check shows its question, weak/mixed/strong definitions, the source types it accepts, sources required versus accepted, rejected evidence with reasons, searches tried and what to do next.
   - **Searches:** a plan built from your brief's structured fields; Crossref, OpenAlex and World Bank searches.
   - **Inspection:** inspection of any public page you choose, with precise fetch errors (timeout, certificate, oversized page). If a page can't be fetched, you can paste the passage yourself; it's labelled as yours and never counted as verified.
   - **Relevance review:** five questions (claim, geography, buyer, method, date) decide whether a source counts.
   - **Ledger:** exact passages go into an immutable ledger, alongside your own customer research (founder-reported).
6. **Demand tests** — a suggestion aimed at the riskiest assumption; design check; **lock** before collecting; code reads real results as hit / near miss / clear miss / too little data.
   - Simulated or hypothetical actions cannot be locked as real. A labelled SIMULATED demo never counts.
   - Ideas involving children are tested with consenting adults only.
   - Results record recruitment, exclusions, consent, dates and limitations.
7. **Decision** — verdict (Needs evidence, Continue testing, Pivot, Stop, Blocked) with the code's own explanation first; five dimensions with clickable evidence; what would change it; the model's commentary, checked against the verdict, with every correction listed. Printable.
   - Plus the **decision log**: one card per decision with the gate it was made against, your reason (or "none given, optional here") and every version and hash it is bound to.
   - Plus a **six-phase roadmap**.

## What is honest about this prototype

- No paid API, key or account is required. Research providers are free public services that may throttle or be offline; failures are shown as failures.
- General web, competitor, pricing, patent and regulator search is **not automated** (no compliant free search API). FounderOS proposes queries and links for you to run and verifies the pages you bring back. Academic indexes return metadata about papers, which never counts as customer or competitor evidence.
- The team rubric's book references are recorded exactly as supplied ("page: not visible") and were not independently checked. They explain why a check exists; they are never evidence about your venture.
- A verified excerpt proves the words are on the page, not that they are true; secondary sources never prove demand.
- Customer results are entered by you and stay *founder-reported, not independently verified*.
- The project key is a prototype capability token, not production authentication. Do not expose the app to the internet.


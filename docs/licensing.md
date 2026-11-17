# Licensing and deployability

## Original FounderOS code
Licensed MIT (see root `LICENSE`). This license grants rights to this repository's original source only.

## Local LLM
Default model `qwen2.5:1.5b-instruct` is offered by Ollama with **Apache License 2.0** weights. See https://ollama.com/library/qwen2.5:1.5b-instruct . Other Qwen variants have differing licenses; check the exact tag before substituting.

## n8n (optional)
**n8n is not OSI-approved open source.** Its own licensing documentation states it is fair-code/source-available under the **Sustainable Use License**. See https://docs.n8n.io/sustainable-use-license/ and https://github.com/n8n-io/n8n-docs/blob/main/docs/n8n-community-license/README.md . Do not describe n8n as OSI-open-source. The default `docker compose up --build` has **no n8n**. Optional visual adapters can be imported in a separate profile (`--profile visual`), subject to n8n's license.

The event's wording does not resolve whether optional fair-code integration is allowed. For lowest compliance risk, evaluate and submit the standalone open-source Python core and treat n8n as an optional local development convenience, not as the implementation's license basis. If an organizer prohibits even including n8n workflow files, remove the optional profile and `workflows/` before submission; the core remains functional.

All Python libraries and container images have their own licenses; preserve third-party notices and review exact versions for your final distribution.

# Optional n8n integration (not in the open-source core)

The actual founder state machine, LLM prompts, gates, durable memory, and approvals are in the MIT-licensed Python backend. **n8n is not an OSI-open-source dependency**; it is distributed under its own Sustainable Use License. It is deliberately excluded from the default setup.

These are importable n8n workflow JSON definitions, **not screenshots**:
- `refinement.json`: Webhook → authenticated POST `/api/projects/{id}/refine` → Respond.
- `discovery.json`: Webhook → authenticated POST `/api/projects/{id}/phases/discover/run` → Respond.
- `validation.json`: Webhook → authenticated POST `/api/projects/{id}/phases/validate/run` → Respond.
- `approval.json`: Webhook → authenticated POST `/api/projects/{id}/phases/{phase}/decision` → Respond. Backend checks the run version and founder decision.

To try the optional visual adapter, run `docker compose --profile visual up --build` and open `http://localhost:5678`. Import each workflow from the editor menu. The HTTP Request targets the `api` container on the Compose network. Activate a workflow and invoke the corresponding `/webhook/founderos-...` endpoint with JSON keys `project_id`, `access_token`, and (for approval) `phase`, `run_id`, `report_hash`, `brief_version`, `decision`, `feedback`, `acknowledge_risk`. The backend rejects any approval whose `report_hash`/`brief_version` do not match the stored artifact, so n8n cannot bypass the gate.

**Security warning:** Passing a live project token through an automation platform may expose it in workflow execution logs. Only run this locally for a personal hackathon demonstration. In production, use a trusted service-to-service authentication scheme and restrict logs. Do NOT expose n8n publicly. No workflow contains real credentials.

These workflow exports follow common n8n Webhook/HTTP/Respond node formats, but **were not imported into an actual n8n runtime in the authoring environment**. Check node versions and execution carefully before claiming integration is verified. The core does not require n8n.

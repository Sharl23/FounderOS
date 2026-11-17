# v0.8 repair report: issue → files → tests → status

Scope: the 17 Nov 2026 manual trial of v0.7 plus the team's 67-check rubric. Every row below was implemented in this repository and tested as stated. "Mocked" means the TEST_ONLY fake model or fixed provider responses; nothing in the shipped app is mocked.

| # | Trial issue | Files | Tests | Status |
|---|---|---|---|---|
| R | 67 team checks registered verbatim, validated at startup, mapped to D01/D03–D07 | `policy/rubric_phase1.yaml`, `app/rubric.py`, `scripts/rubric/*` | `test_exactly_67_unique_ids…`, `test_twelve_safety_ids…`, `test_team_text_is_verbatim…`, `test_tampered_rubric_is_refused`, `test_duplicate_id_is_refused`, `test_rubric_api_and_coverage` | PASS (unit) |
| R | Granular statuses, independence, source types, absence caps, aggregation | `app/rubric.py`, `app/criteria.py` (`_with_granular`), `app/main.py` | `test_no_evidence_means_every_scored_check_unknown…`, `test_same_organisation_twice…`, `test_absence_checks_never_strong…`, `test_wrong_source_type…example_com…`, `test_judge_output_with_fake_ids…`, `test_granular_ratings_aggregate…` | PASS (mocked judge) |
| 1 | Brief fields not captured, false D02 fail | `app/brief_extract.py`, `app/main.py` (`apply_fields`, `/brief/confirm`, `/clarify`), `app/criteria.py` (D02) | `test_restaurant_brief_parses…`, `test_d02_asks_one_question…`, `test_confirming_a_model_suggestion…`, `test_parser_failure_is_distinct…`, `test_children_brief_flags_minors…`; e2e 9b | PASS |
| 2 | Invented %, AUC direction, unrealistic tests | `app/discovery_guard.py`, `app/llm.py` (prompt), `app/main.py` (retry once, degrade) | `test_invented_percentage_and_auc_direction…`, `test_skeptic_flags_overclaims…` | PASS (mocked model output) |
| 3 | Timeouts, TLS failure, >800 KB page, query building | `app/research.py` (`safe_fetch`, `_get_json`, `plan`), `app/rubric.py` (`check_queries`), `app/main.py` (founder paste) | `test_oversized_page_is_truncated…`, `test_tls_failure_is_classified…`, `test_timeout_is_retried_once…`, `test_ssrf_blocks_have_their_own_code`, `test_crossref_timeout_is_recoverable_status`, `test_ssrf_targets_never_fetched`, `test_research_queries_use_structured_fields…`, `test_founder_supplied_paste…` | PASS (mocked HTTP) |
| 4 | Words-appeared vs claim-supported; example.com | `app/review.py`, `app/decision.py` (`exclusion_reason`), UI relevance form | `test_relevance_review_rules_words_vs_support`, `test_wrong_source_type…example_com…`; e2e step 5 | PASS |
| 5 | Decision log columns / reason "—" | `app/main.py` (`decision_row`, `decision_log`), UI decision cards | `test_decision_log_maps_every_field…`, `test_old_decision_without_refs_reports_not_stored`; e2e step 9 | PASS |
| 6 | "Simulated voluntary sign-up" draft; minors | `app/criteria.py` (`experiment_design_check`), `app/main.py` (`SIMULATED_RESULT`), `app/schemas.py`, UI | `test_simulated_waitlist_cannot_lock_as_real…`, `test_minors_tests_must_be_adults_only…`; existing locked-threshold tests | PASS |
| 7 | Fragmented / categorical validation prose | `app/prose.py`, `app/main.py`, `app/llm.py` (prompt) | `test_prose_rewrites_categorical_absence…`, `test_validation_shows_code_explanation_first`, `test_bad_model_json_does_not_crash_validation` | PASS |
| 8 | UI polish | `app/static/app.js`, `style.css` | `scripts/ui_e2e.py` (60 checks, 1366 px + 390 px, dark, keyboard) + screenshots | PASS (TEST_ONLY model) |
| — | Restart crash on existing DB (Python 3.13) | `app/db.py` | `test_migration_keeps_v07_rows` | PASS |
| — | CPU-only stays CPU-only | `app/llm.py` (`OLLAMA_NUM_GPU` passed through, never overridden) | `test_model_options_respect_num_gpu_zero`, `test_platform_v7.py` OOM mapping | PASS (unit). Live probe: **not run here** |

## Run results in the authoring sandbox (17 Nov 2026)

```
$ cd backend && python -m pytest -q
247 passed, 1 warning
$ python scripts/ui_e2e.py
UI E2E PASSED: 0 problem(s)        # 60 "ok" checks, exit 0
```

## Not verified here (state plainly)

- **Live Ollama inference** (`/api/model/health?probe=1`): the sandbox has no Ollama. The founder verified v0.7 on CPU (`num_gpu 0`, ~4.3 s probe). v0.8 does not change the model client except one extra prompt (`CHECK_JUDGE_SYSTEM`). Re-run the probe on the demo laptop.
- **Live providers** (Crossref, OpenAlex, World Bank, real page fetches): no internet in the sandbox. Error handling is tested with mocked HTTP failures. Run `python scripts/live_check.py`.
- **`docker compose up`**: no Docker daemon in the sandbox. The compose files are unchanged from v0.7 apart from the image contents.
- **Real 1.5B behaviour on the per-check judge**: only the validation rules are tested. A small model may often answer INSUFFICIENT or be rejected; that leaves checks UNKNOWN, which is the safe failure.

## Known limitations

- There is no general web or competitor search API. Customer-voice, pricing, patent and regulator checks get manual search links; the founder brings pages back for verification.
- Independence is approximated by publisher name or registrable domain. Two outlets owned by one group still count as two unless the founder sets the organisation.
- `brief_extract` is pattern-based (English, plus a small city and country list). Anything it misses shows as NOT_STATED with a question, never as a guess.
- Brief-condition WEAKs (no payer named, no costs named, no contacts named, no charging method named) follow the team's weak definitions literally. They never produce a dimension score on their own.
- Team book provenance is recorded as supplied ("page: not visible"), not checked.

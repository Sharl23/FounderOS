"""SQLite state store: versioned briefs, safety assessments, phase runs, evidence, pre-registered
experiments, and an append-only decision log + audit trail (enforced by SQLite triggers)."""
from __future__ import annotations
import json
import os
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, original_idea TEXT NOT NULL,
  intake_json TEXT NOT NULL, created_at TEXT NOT NULL, stopped INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS briefs (project_id TEXT NOT NULL, version INTEGER NOT NULL, payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY(project_id,version));
CREATE TABLE IF NOT EXISTS safety_assessments (project_id TEXT NOT NULL, brief_version INTEGER NOT NULL,
  payload_json TEXT NOT NULL, status TEXT NOT NULL, acknowledged_at TEXT, ack_statement TEXT, created_at TEXT NOT NULL,
  PRIMARY KEY(project_id, brief_version));
CREATE TABLE IF NOT EXISTS phase_runs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, phase TEXT NOT NULL,
  version INTEGER NOT NULL, state TEXT NOT NULL, report_json TEXT NOT NULL, gate_json TEXT NOT NULL,
  brief_version INTEGER NOT NULL, safety_status TEXT NOT NULL, report_hash TEXT NOT NULL, input_hash TEXT NOT NULL,
  upstream_run_id TEXT, invalidated_reason TEXT, model TEXT, latency_ms INTEGER, created_at TEXT NOT NULL,
  UNIQUE(project_id,phase,version));
CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL,
  dimension TEXT NOT NULL, claim_id TEXT, claim TEXT NOT NULL, direction TEXT NOT NULL,
  source_url TEXT, title TEXT, publisher TEXT, author TEXT, published_on TEXT, retrieved_at TEXT, excerpt TEXT,
  url_status TEXT NOT NULL, excerpt_status TEXT NOT NULL, relevance TEXT NOT NULL, independence TEXT NOT NULL,
  method TEXT, sample_size INTEGER, positives INTEGER, segment TEXT, geography TEXT, collected_from TEXT, collected_to TEXT,
  consent_confirmed INTEGER NOT NULL DEFAULT 0, experiment_id TEXT, experiment_version INTEGER, outcome TEXT,
  rate_pct REAL, adverse INTEGER, positive_signals TEXT, negative_signals TEXT,
  dedupe_key TEXT NOT NULL, duplicate_of TEXT, injection_flag INTEGER NOT NULL DEFAULT 0,
  limitations TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS experiments (series_id TEXT NOT NULL, version INTEGER NOT NULL, project_id TEXT NOT NULL,
  status TEXT NOT NULL, payload_json TEXT NOT NULL, criteria_hash TEXT NOT NULL, locked_at TEXT,
  result_evidence_id TEXT, created_at TEXT NOT NULL, PRIMARY KEY(series_id, version));
CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, phase TEXT NOT NULL,
  phase_run_id TEXT NOT NULL UNIQUE, run_version INTEGER NOT NULL, action TEXT NOT NULL, scope TEXT NOT NULL,
  feedback TEXT NOT NULL, acknowledged_risk INTEGER NOT NULL, actor TEXT NOT NULL, brief_version INTEGER NOT NULL,
  safety_status TEXT NOT NULL, report_hash TEXT NOT NULL, input_hash TEXT NOT NULL, experiment_versions_json TEXT NOT NULL,
  gate_recommendation TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, event TEXT NOT NULL,
  details_json TEXT NOT NULL, created_at TEXT NOT NULL);

CREATE TRIGGER IF NOT EXISTS decisions_immutable_u BEFORE UPDATE ON decisions BEGIN SELECT RAISE(ABORT,'decision log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS decisions_immutable_d BEFORE DELETE ON decisions BEGIN SELECT RAISE(ABORT,'decision log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_immutable_u BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_immutable_d BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS evidence_immutable_u BEFORE UPDATE ON evidence BEGIN SELECT RAISE(ABORT,'evidence is immutable; add a new record'); END;
CREATE TRIGGER IF NOT EXISTS evidence_immutable_d BEFORE DELETE ON evidence BEGIN SELECT RAISE(ABORT,'evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS briefs_immutable BEFORE UPDATE ON briefs BEGIN SELECT RAISE(ABORT,'brief versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS reports_immutable BEFORE UPDATE OF report_json, gate_json, report_hash, input_hash, brief_version ON phase_runs
  BEGIN SELECT RAISE(ABORT,'phase-run artifacts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS experiment_criteria_locked BEFORE UPDATE OF payload_json, criteria_hash, locked_at ON experiments
  WHEN OLD.locked_at IS NOT NULL BEGIN SELECT RAISE(ABORT,'locked experiment criteria cannot be rewritten; create a new version'); END;
'''


def now():
    return datetime.now(timezone.utc).isoformat()


def file_path():
    return os.getenv('FOUNDEROS_DB', '/data/founderos-v2.sqlite3')


SCHEMA_V7 = '''
CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS criteria_configs (project_id TEXT NOT NULL, version INTEGER NOT NULL, payload_json TEXT NOT NULL,
  config_hash TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(project_id, version));
CREATE TABLE IF NOT EXISTS criteria_evaluations (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, phase TEXT NOT NULL,
  version INTEGER NOT NULL, payload_json TEXT NOT NULL, evaluation_hash TEXT NOT NULL, fingerprint_hash TEXT NOT NULL,
  criteria_version TEXT NOT NULL, criteria_policy_hash TEXT NOT NULL, config_hash TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(project_id, phase, version));
CREATE TABLE IF NOT EXISTS judgments (cache_key TEXT PRIMARY KEY, project_id TEXT NOT NULL, criterion_id TEXT NOT NULL,
  payload_json TEXT NOT NULL, model TEXT, latency_ms INTEGER, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_runs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, bucket TEXT NOT NULL, provider TEXT NOT NULL,
  query TEXT NOT NULL, status TEXT NOT NULL, error TEXT, result_count INTEGER NOT NULL DEFAULT 0, brief_version INTEGER, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_candidates (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, run_id TEXT, bucket TEXT, provider TEXT NOT NULL,
  url TEXT, doi TEXT, title TEXT, publisher TEXT, year INTEGER, state TEXT NOT NULL, payload_json TEXT NOT NULL,
  fetch_json TEXT, evidence_id TEXT, reject_reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS safety_sources (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, brief_version INTEGER NOT NULL, rule_id TEXT NOT NULL,
  url TEXT NOT NULL, final_url TEXT, excerpt TEXT NOT NULL, finding TEXT NOT NULL, jurisdiction TEXT, official_domain INTEGER NOT NULL,
  url_status TEXT NOT NULL, excerpt_status TEXT NOT NULL, retrieved_at TEXT, source_hash TEXT, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS criteria_configs_immutable BEFORE UPDATE ON criteria_configs BEGIN SELECT RAISE(ABORT,'criteria configs are versioned; add a new version'); END;
CREATE TRIGGER IF NOT EXISTS criteria_evaluations_immutable BEFORE UPDATE ON criteria_evaluations BEGIN SELECT RAISE(ABORT,'evaluations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS safety_sources_immutable BEFORE UPDATE ON safety_sources BEGIN SELECT RAISE(ABORT,'safety sources are immutable'); END;
'''

# Additive column migrations from v0.2–v0.4 databases (never destructive).
COLUMNS_V7 = {
    'projects': [('name', 'TEXT')],
    'evidence': [('direction_id', 'TEXT'), ('criterion_id', 'TEXT'), ('source_hash', 'TEXT'), ('candidate_id', 'TEXT'),
                 ('doi', 'TEXT'), ('provider', 'TEXT'), ('final_url', 'TEXT')],
    'decisions': [('criteria_version', 'TEXT'), ('criteria_policy_hash', 'TEXT'), ('config_hash', 'TEXT'),
                  ('evaluation_hash', 'TEXT'), ('safety_policy_hash', 'TEXT')],
}


# v0.8: granular rubric links, source typing, relevance review, simulated results, decision references.
COLUMNS_V8 = {
    'evidence': [('subcriterion_id', 'TEXT'), ('source_type', 'TEXT'), ('review_state', 'TEXT'), ('review_reason', 'TEXT'),
                 ('relevance_checks_json', 'TEXT'), ('organization', 'TEXT'), ('meta_json', 'TEXT')],
    'research_runs': [('subcriterion_id', 'TEXT'), ('error_code', 'TEXT')],
    'decisions': [('rubric_version', 'TEXT'), ('rubric_hash', 'TEXT'), ('discover_evaluation_version', 'INTEGER')],
}


# v0.9: phases 3-6 (build, commercial, sell/deliver/get paid, operate), approvals, agent actions.
SCHEMA_V9 = '''
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_actions(
  id TEXT PRIMARY KEY, project_id TEXT, run_tag TEXT, ts TEXT NOT NULL, agent TEXT NOT NULL, action TEXT NOT NULL,
  sources_json TEXT NOT NULL DEFAULT '[]', model TEXT, cost REAL NOT NULL DEFAULT 0, approved_by TEXT, outcome TEXT, detail_json TEXT);
CREATE INDEX IF NOT EXISTS ix_agent_actions_project ON agent_actions(project_id, ts);
CREATE TABLE IF NOT EXISTS approvals(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, action TEXT NOT NULL, risk TEXT NOT NULL, scope TEXT NOT NULL,
  target TEXT, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL, status TEXT NOT NULL, requested_at TEXT NOT NULL,
  decided_at TEXT, decision_note TEXT, expires_at TEXT NOT NULL, consumed_at TEXT);
CREATE TABLE IF NOT EXISTS approval_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, approval_id TEXT NOT NULL, project_id TEXT NOT NULL, event TEXT NOT NULL, detail_json TEXT, at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS approval_events_no_update BEFORE UPDATE ON approval_events BEGIN SELECT RAISE(ABORT, 'approval events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS approval_events_no_delete BEFORE DELETE ON approval_events BEGIN SELECT RAISE(ABORT, 'approval events are append-only'); END;
CREATE TABLE IF NOT EXISTS phase_transitions(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, phase INTEGER NOT NULL, outcome TEXT NOT NULL, gate_json TEXT NOT NULL,
  approval_id TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS builds(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, version INTEGER NOT NULL, mode TEXT NOT NULL, parent_version INTEGER,
  spec_json TEXT NOT NULL, files_json TEXT NOT NULL, qa_json TEXT NOT NULL, feedback TEXT, changes_json TEXT,
  spec_hash TEXT NOT NULL, files_hash TEXT NOT NULL, preview_key TEXT NOT NULL, approval_id TEXT, created_at TEXT NOT NULL,
  UNIQUE(project_id, version));
CREATE TABLE IF NOT EXISTS commercial_plans(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, version INTEGER NOT NULL, inputs_json TEXT NOT NULL, results_json TEXT NOT NULL,
  plan_hash TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(project_id, version));
CREATE TABLE IF NOT EXISTS offers(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, version INTEGER NOT NULL, commercial_version INTEGER NOT NULL, build_version INTEGER,
  package_json TEXT NOT NULL, sales_page_html TEXT NOT NULL, offer_hash TEXT NOT NULL, status TEXT NOT NULL, checkout_open INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, offer_id TEXT NOT NULL, buyer_ref TEXT NOT NULL, amount_cents INTEGER NOT NULL,
  currency TEXT NOT NULL, status TEXT NOT NULL, idempotency_key TEXT NOT NULL, test_mode INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(project_id, idempotency_key));
CREATE TABLE IF NOT EXISTS payment_events(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, event_id TEXT NOT NULL, type TEXT NOT NULL, order_id TEXT NOT NULL,
  amount_cents INTEGER NOT NULL, fee_cents INTEGER NOT NULL DEFAULT 0, result TEXT NOT NULL, received_at TEXT NOT NULL,
  test_mode INTEGER NOT NULL DEFAULT 1, UNIQUE(project_id, event_id));
CREATE TABLE IF NOT EXISTS entitlements(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, order_id TEXT NOT NULL UNIQUE, token TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
  granted_at TEXT NOT NULL, revoked_at TEXT, deliveries INTEGER NOT NULL DEFAULT 0, last_access_at TEXT);
CREATE TABLE IF NOT EXISTS refunds(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, order_id TEXT NOT NULL UNIQUE, amount_cents INTEGER NOT NULL, approval_id TEXT NOT NULL,
  event_id TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reconciliations(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, result_json TEXT NOT NULL, ok INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS op_metrics(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, value REAL NOT NULL, period TEXT NOT NULL, source TEXT NOT NULL,
  note TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, text TEXT NOT NULL, source TEXT NOT NULL, provenance TEXT NOT NULL,
  order_id TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS op_issues(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposals(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, target_phase INTEGER NOT NULL, rationale TEXT NOT NULL, change_json TEXT NOT NULL,
  basis_json TEXT NOT NULL, status TEXT NOT NULL, applied_ref TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
'''


def migrate(db):
    db.executescript(SCHEMA_V7)
    db.executescript(SCHEMA_V9)
    for table, cols in list(COLUMNS_V7.items()) + list(COLUMNS_V8.items()):
        have = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
        for name, typ in cols:
            if name not in have:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {typ}')
    db.execute('INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?,?)', ('v7', now()))
    db.execute('INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?,?)', ('v8', now()))
    db.execute('INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?,?)', ('v9', now()))


def init_db():
    path = file_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=20) as db:
        db.executescript(SCHEMA)
        migrate(db)
        db.commit()   # close the implicit migration transaction before switching journal mode (restart-safe)
        db.execute('PRAGMA journal_mode=WAL')


@contextmanager
def conn():
    db = sqlite3.connect(file_path(), timeout=20, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=20000')
    # One serialised write transaction per request: checks and writes happen under the same lock,
    # which prevents replayed/duplicate approvals racing each other.
    db.execute('BEGIN IMMEDIATE')
    try:
        yield db
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
        raise
    finally:
        db.close()


def qone(db, sql, args=()):
    row = db.execute(sql, args).fetchone()
    return dict(row) if row else None


def qall(db, sql, args=()):
    return [dict(x) for x in db.execute(sql, args).fetchall()]


def audit(db, pid, event, details=None):
    db.execute('INSERT INTO audit(project_id,event,details_json,created_at) VALUES(?,?,?,?)',
               (pid, event, json.dumps(details or {}, ensure_ascii=False), now()))


def unpack_run(row):
    if row is None:
        return None
    obj = dict(row)
    obj['report'] = json.loads(obj.pop('report_json'))
    obj['gate'] = json.loads(obj.pop('gate_json'))
    return obj


def unpack_brief(row):
    if row is None:
        return None
    obj = dict(row)
    obj['payload'] = json.loads(obj.pop('payload_json'))
    return obj


def unpack_experiment(row):
    if row is None:
        return None
    obj = dict(row)
    obj['payload'] = json.loads(obj.pop('payload_json'))
    obj['id'] = obj['series_id']
    return obj

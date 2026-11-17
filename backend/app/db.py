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


def init_db():
    path = file_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=20) as db:
        db.executescript(SCHEMA)
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

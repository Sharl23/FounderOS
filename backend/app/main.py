"""FounderOS API (v0.8). Phase transitions, safety, criteria and verdicts are backend-enforced.

Agent roles are isolated functions with typed contracts:
  Refiner (LLM, RefinedBrief) -> Safety screen (code + escalate-only model flags)
  -> Discover agent (LLM, DiscoveryReport) -> Research Gatherer (research.py providers)
  -> Evidence Verifier (research.safe_fetch + exact passage check) -> Claim Ledger (evidence table)
  -> Criterion Judge (LLM, JudgeOutput, one criterion per call, accepted evidence only, validated in code)
  -> Deterministic Gate (criteria.py D09 / decision.py verdict) -> Founder action (version-bound, audited).
No LLM can approve a gate or choose an exit.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .db import init_db, conn, now, qone, qall, audit as _db_audit, unpack_run, unpack_brief, unpack_experiment
from . import agent_log
from .schemas import (ProjectCreate, RefinedBrief, DiscoveryReport, ValidationReport, ClarifyRequest, SafetyAck,
                      DecisionRequest, EvidenceAdd, ExperimentDraft, ExperimentLock, ExperimentResult,
                      PublicActionRequest, JudgeOutput, CheckJudgeOutput, BRIEF_FIELDS)
from .gates import evaluate_validation, PHASES, ACTIVE_PHASES
from .decision import stable_hash, norm, criteria_of, evaluate_result, skeptic_review, suggest_experiment, risk_register, exclusion_reason
from . import safety, criteria, research, brief_extract, rubric, discovery_guard, prose, review
from .research import check_public_url, FetchError
from .llm import (OllamaClient, ModelUnavailable, ModelOutputError, ADVICE, REFINE_SYSTEM, DISCOVER_SYSTEM,
                  VALIDATE_SYSTEM, JUDGE_SYSTEM, CHECK_JUDGE_SYSTEM)

LLM = OllamaClient()
STARTED_AT = now()
VERSION = '0.9.0'


@asynccontextmanager
async def lifespan(app: FastAPI):
    rubric.validate()          # refuses to start on a malformed or edited team rubric
    init_db()
    yield


app = FastAPI(title='FounderOS', version=VERSION, lifespan=lifespan,
              description='Evidence-first founder decision system. Draft-only: no publishing, sending, spending, signing or payments.')


# Audit events that are agent actions also go to the agent log (exported as decision_log.json).
AGENT_EVENTS = {
    'BRIEF_REFINED': ('brief_refiner', 'refine_brief'), 'SAFETY_SCREENED': ('safety', 'screen_twelve_rules'), 'SAFETY_PRESCREEN_BLOCK': ('safety', 'prescreen_block'),
    'PHASE_RUN_READY': (None, None), 'CRITERIA_EVALUATED': ('gate', 'phase1_criteria_evaluation'), 'CRITERION_JUDGED': ('criterion_judge', 'judge_criterion'),
    'RUBRIC_CHECK_JUDGED': ('check_judge', 'judge_rubric_check'), 'RESEARCH_QUERY_RUN': ('researcher', 'search_provider'),
    'SOURCE_INSPECTED': ('verifier', 'inspect_source'), 'EVIDENCE_ADDED': ('evidence_review', 'add_to_ledger'),
    'EXPERIMENT_DRAFTED': ('experiment_designer', 'draft_demand_test'), 'EXPERIMENT_PREREGISTERED': ('founder', 'lock_demand_test'),
    'EXPERIMENT_RESULT_RECORDED': ('validation', 'read_locked_result'), 'FOUNDER_DECISION': ('founder', None), 'RISK_ACKNOWLEDGED': ('founder', 'acknowledge_review_required'),
    'EXTERNAL_ACTION_BLOCKED': ('approval', 'refuse_external_action'),
}


def audit(db, pid, event, details=None):
    _db_audit(db, pid, event, details)
    if event not in AGENT_EVENTS:
        return
    d = details or {}
    agent, action = AGENT_EVENTS[event]
    model, outcome, approved = None, None, None
    sources = [u for u in (d.get('final_url'), d.get('url'), d.get('source_url')) if u]
    if event == 'PHASE_RUN_READY':
        agent, action, model = ('discovery' if d.get('phase') == 'discover' else 'validation'), f'run_{d.get("phase")}', d.get('model')
        outcome = str(d.get('gate')).lower()
    elif event == 'FOUNDER_DECISION':
        action, approved, outcome = f'{d.get("decision", "").lower()}_{d.get("phase")}_gate', ('founder' if d.get('decision') == 'APPROVE' else None), f'gate said {d.get("gate")}'
    elif event in ('EXPERIMENT_PREREGISTERED', 'RISK_ACKNOWLEDGED'):
        approved = 'founder'
    elif event == 'BRIEF_REFINED':
        model = d.get('model')
    elif event in ('CRITERION_JUDGED', 'RUBRIC_CHECK_JUDGED'):
        model, outcome = LLM.model, str(d.get('rating') or d.get('score') or d.get('status')).lower()
    elif event == 'CRITERIA_EVALUATED':
        outcome = str(d.get('exit')).lower()
    elif event == 'SAFETY_SCREENED':
        outcome = str(d.get('status')).lower()
    elif event == 'RESEARCH_QUERY_RUN':
        outcome = f'{d.get("provider")}: {d.get("status")}, {d.get("results")} result(s)'
    elif event == 'EXPERIMENT_RESULT_RECORDED':
        outcome = str(d.get('outcome')).lower()
    agent_log.record(db, pid, agent, action, sources=sources, model=model, approved_by=approved, outcome=outcome, detail={'event': event})


def jsonstr(x):
    return json.dumps(x, ensure_ascii=False, default=str)


def model_error(exc):
    code = getattr(exc, 'code', 'MODEL_ERROR')
    return HTTPException(503, {'code': code, 'message': str(exc), 'advice': ADVICE.get(code, '').format(model=LLM.model),
                               'retry': True, 'note': 'Your input is saved. Nothing was simulated.'})


# ----------------------------------------------------------------------------- admission guards
def _luhn(number: str) -> bool:
    digits = [int(ch) for ch in number if ch.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for idx, digit in enumerate(reversed(digits)):
        if idx % 2 == 1:
            digit = digit * 2 - 9 if digit * 2 > 9 else digit * 2
        total += digit
    return total % 10 == 0


def reject_obvious_secrets(text: str):
    """Best-effort admission guard so credentials/cards never reach SQLite or logs. NOT a complete detector."""
    if re.search(r'(?i)(?:password|passwd|api[_ -]?key|secret[_ -]?key|access[_ -]?token|bearer)\s*[:=]\s*[\w\-+/.]{5,}', text):
        raise HTTPException(422, 'Input appears to contain a credential. Remove passwords or tokens; FounderOS never stores them.')
    if re.search(r'(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{25,}|AKIA[0-9A-Z]{16})', text):
        raise HTTPException(422, 'Input appears to contain an API secret. Remove it first.')
    for match in re.finditer(r'(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)', text):
        if _luhn(match.group(0)):
            raise HTTPException(422, 'Input appears to contain a payment card number. Remove it; card details are never stored.')


def check_project(pid: str, token: str | None):
    if not token:
        raise HTTPException(401, 'X-Project-Token header required')
    with conn() as db:
        project = qone(db, 'SELECT * FROM projects WHERE id=?', (pid,))
    if not project or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), project['token_hash']):
        raise HTTPException(404, 'Project not found or token invalid')
    return project


def authorize(pid: str, x_project_token: str | None = Header(default=None)):
    return check_project(pid, x_project_token)


def not_stopped(project):
    if project['stopped']:
        raise HTTPException(409, 'This project has been stopped by the founder. It is read-only.')


# ----------------------------------------------------------------------------- queries
def latest_run(db, pid, phase):
    return unpack_run(qone(db, 'SELECT * FROM phase_runs WHERE project_id=? AND phase=? ORDER BY version DESC LIMIT 1', (pid, phase)))


def latest_brief(db, pid):
    return unpack_brief(qone(db, 'SELECT * FROM briefs WHERE project_id=? ORDER BY version DESC LIMIT 1', (pid,)))


def safety_for(db, pid, brief_version):
    row = qone(db, 'SELECT * FROM safety_assessments WHERE project_id=? AND brief_version=?', (pid, brief_version))
    if not row:
        return None
    row['assessment'] = json.loads(row.pop('payload_json'))
    return row


def experiments_of(db, pid):
    return [unpack_experiment(x) for x in qall(db, 'SELECT * FROM experiments WHERE project_id=? ORDER BY created_at, version', (pid,))]


def evidence_of(db, pid):
    return qall(db, 'SELECT * FROM evidence WHERE project_id=? ORDER BY created_at', (pid,))


def config_of(db, pid):
    row = qone(db, 'SELECT * FROM criteria_configs WHERE project_id=? ORDER BY version DESC LIMIT 1', (pid,))
    if not row:
        return criteria.default_config(), 0
    return json.loads(row['payload_json']), row['version']


def latest_eval(db, pid, phase):
    row = qone(db, 'SELECT * FROM criteria_evaluations WHERE project_id=? AND phase=? ORDER BY version DESC LIMIT 1', (pid, phase))
    if row:
        row['evaluation'] = json.loads(row.pop('payload_json'))
    return row


def judgments_for(db, pid, phase, brief, evidence, experiments, cfg):
    out = {}
    for cid, rows, quality in criteria.judgeable_rows(phase, brief, evidence, experiments, cfg):
        key = criteria.judge_cache_key(cid, rows, quality, LLM.model)
        hit = qone(db, 'SELECT payload_json FROM judgments WHERE cache_key=?', (key,))
        if hit:
            out[cid] = json.loads(hit['payload_json'])
    return out


def missing_fields(brief):
    if brief is None:
        return ['refined brief']
    p = brief['payload']
    return [name for name in ('problem', 'target_customers', 'current_workaround', 'target_market') if not p.get(name)]


def invalidate_runs(db, pid, reason, phases=ACTIVE_PHASES):
    """Any change of inputs retires dependent approvals (state only; artifacts stay immutable)."""
    for phase in phases:
        for run in qall(db, 'SELECT id,state FROM phase_runs WHERE project_id=? AND phase=? AND state IN ("PENDING_APPROVAL","APPROVED")', (pid, phase)):
            db.execute('UPDATE phase_runs SET state=?, invalidated_reason=? WHERE id=?', ('INVALIDATED', reason, run['id']))
            audit(db, pid, 'APPROVAL_INVALIDATED', {'phase': phase, 'run_id': run['id'], 'previous_state': run['state'], 'reason': reason})


def safety_fields(project, payload):
    f = {k: payload.get(k) for k in BRIEF_FIELDS}
    f['idea'] = project['original_idea']
    f['idea_summary'] = payload.get('idea_summary')
    f['founder_answers'] = payload.get('founder_answers') or {}
    return f


def store_safety(db, pid, brief_version, project, payload, keep_ack=False):
    sources = qall(db, 'SELECT * FROM safety_sources WHERE project_id=? ORDER BY created_at', (pid,))
    prev = safety_for(db, pid, brief_version)
    assessment = safety.screen(project['original_idea'], safety_fields(project, payload),
                               model_flags=payload.get('model_risk_flags') or [], official_sources=sources)
    ack_at = prev['acknowledged_at'] if (keep_ack and prev and prev['status'] == assessment['status']) else None
    ack_st = prev['ack_statement'] if ack_at else None
    db.execute('INSERT OR REPLACE INTO safety_assessments(project_id,brief_version,payload_json,status,acknowledged_at,ack_statement,created_at) VALUES(?,?,?,?,?,?,?)',
               (pid, brief_version, jsonstr(assessment), assessment['status'], ack_at, ack_st, now()))
    audit(db, pid, 'SAFETY_SCREENED', {'brief_version': brief_version, 'status': assessment['status'], 'counts': assessment['counts'],
                                       'rules': [f['rule_id'] for f in assessment['findings']], 'policy': assessment['policy_version'],
                                       'policy_hash': assessment['policy_hash']})
    return assessment


# ----------------------------------------------------------------------------- snapshot
DECISION_LABEL = {'APPROVE': 'Approved (research only)', 'REVISE': 'Revision requested', 'PIVOT': 'Pivot requested', 'STOP': 'Stopped'}
NOT_STORED = 'not stored (record predates this field)'


def decision_row(d: dict, runs: list[dict]) -> dict:
    """One explicit, named field per column: the UI renders these keys and never infers positions."""
    run = next((r for r in runs if r['id'] == d['phase_run_id']), None)
    against = d['gate_recommendation'] in ADVISES_AGAINST
    if d['feedback']:
        reason_status = 'PROVIDED'
    elif d['action'] in ('REVISE', 'PIVOT') or (d['action'] == 'APPROVE' and against):
        reason_status = 'MISSING_BUT_REQUIRED'      # cannot happen through the API (422); shown if an old record lacks it
    else:
        reason_status = 'NOT_GIVEN_OPTIONAL'
    refs = {'brief_version': d.get('brief_version'), 'safety_status': d.get('safety_status'), 'safety_policy_hash': d.get('safety_policy_hash'),
            'run_id': d.get('phase_run_id'), 'run_version': d.get('run_version'), 'report_hash': d.get('report_hash'), 'input_hash': d.get('input_hash'),
            'criteria_version': d.get('criteria_version'), 'criteria_policy_hash': d.get('criteria_policy_hash'), 'config_hash': d.get('config_hash'),
            'evaluation_hash': d.get('evaluation_hash'), 'discover_evaluation_version': d.get('discover_evaluation_version'),
            'rubric_version': d.get('rubric_version'), 'rubric_hash': d.get('rubric_hash')}
    if d['phase'] == 'validate':
        refs['discover_evaluation_version'] = refs['discover_evaluation_version'] or 'not applicable (validation decision)'
    missing = [k for k, v in refs.items() if v in (None, '')]
    for k in missing:
        refs[k] = NOT_STORED
    return {'id': d['id'], 'at': d['created_at'], 'phase': d['phase'], 'run_version': d['run_version'],
            'decision': d['action'], 'decision_label': DECISION_LABEL.get(d['action'], d['action']), 'scope': d['scope'],
            'gate_said': d['gate_recommendation'], 'founder_overrode_gate': bool(d['acknowledged_risk']),
            'reason': d['feedback'] or None, 'reason_status': reason_status,
            'bound_to': refs, 'refs_not_stored': missing, 'tests': d['experiment_versions'],
            'run_state_now': run and run['state'], 'permissions': 'RESEARCH_ONLY' if d['scope'] == 'RESEARCH_ONLY' else 'NONE',
            'never_enabled': ['build', 'launch', 'send', 'spend', 'publish', 'pay']}


def public_project(pid):
    with conn() as db:
        project = qone(db, 'SELECT id,name,original_idea,intake_json,created_at,stopped FROM projects WHERE id=?', (pid,))
        project['intake'] = json.loads(project.pop('intake_json'))
        brief = latest_brief(db, pid)
        safety_row = safety_for(db, pid, brief['version']) if brief else None
        runs = [unpack_run(x) for x in qall(db, 'SELECT * FROM phase_runs WHERE project_id=? ORDER BY created_at DESC', (pid,))]
        evidence = evidence_of(db, pid)
        experiments = experiments_of(db, pid)
        decisions = qall(db, 'SELECT * FROM decisions WHERE project_id=? ORDER BY created_at DESC', (pid,))
        history = qall(db, 'SELECT * FROM audit WHERE project_id=? ORDER BY id DESC LIMIT 150', (pid,))
        cfg, cfg_version = config_of(db, pid)
        ev_d, ev_v = latest_eval(db, pid, 'discover'), latest_eval(db, pid, 'validate')
        sources = qall(db, 'SELECT * FROM safety_sources WHERE project_id=? ORDER BY created_at DESC', (pid,))
        rcount = qone(db, 'SELECT COUNT(*) n FROM research_candidates WHERE project_id=?', (pid,))['n']
        live_d = live_discover_fingerprint(db, pid) if ev_d else None
    for h in history:
        h['details'] = json.loads(h.pop('details_json'))
    for d in decisions:
        d['experiment_versions'] = json.loads(d.pop('experiment_versions_json'))
    decision_log = [decision_row(d, runs) for d in decisions]
    disc = next((r for r in runs if r['phase'] == 'discover'), None)
    val = next((r for r in runs if r['phase'] == 'validate'), None)
    passport = None
    if val:
        passport = {'verdict': val['gate'], 'report': val['report'], 'run_id': val['id'], 'version': val['version'],
                    'report_hash': val['report_hash'], 'state': val['state'], 'created_at': val['created_at'],
                    'brief_version': val['brief_version'], 'safety_status': val['safety_status'],
                    'founder_decision': next((d for d in decisions if d['phase_run_id'] == val['id']), None),
                    'invalidated_reason': val.get('invalidated_reason')}
    if ev_d:
        ev_d['stale'] = ev_d['fingerprint_hash'] != live_d
    bp = (brief or {}).get('payload') or {}
    for x in experiments:
        x['design_check'] = criteria.experiment_design_check(x['payload'], bp)
        x['reading'] = None
        if x.get('result_evidence_id'):
            r = next((e for e in evidence if e['id'] == x['result_evidence_id']), None)
            x['reading'] = r and ('SIMULATED_NOT_COUNTED' if r['kind'] == 'SIMULATED_RESULT' else criteria.READING.get(r.get('outcome')))
    return {'project': project, 'brief': brief, 'safety': safety_row, 'safety_sources': sources, 'phase_runs': runs, 'evidence': evidence,
            'experiments': experiments, 'decisions': decisions, 'decision_log': decision_log, 'audit': history, 'passport': passport,
            'criteria': {'version': criteria.VERSION, 'policy_hash': criteria.POLICY_HASH, 'config': cfg, 'config_version': cfg_version,
                         'config_hash': stable_hash(cfg), 'discover': ev_d, 'validate': ev_v},
            'research_candidate_count': rcount,
            'phases': [{'id': p, 'status': 'LIVE'} for p in PHASES],
            'current': {'discover': disc and disc['state'], 'validate': val and val['state'], 'stopped': bool(project['stopped']),
                        'safety': safety_row and safety_row['status']}}


# ----------------------------------------------------------------------------- health
@app.get('/api/health')
async def health():
    status = await LLM.status()
    return {'status': 'ok', 'version': VERSION, 'mode': 'LIVE_LOCAL_OLLAMA_REQUIRED', 'model': LLM.model, 'ollama': status,
            'started_at': STARTED_AT, 'host': platform.platform(), 'cpu_count': os.cpu_count(),
            'warning': 'Model reachable + installed does NOT prove inference works. Use /api/model/health?probe=1.'}


@app.get('/api/model/health')
async def model_health(probe: bool = False):
    return await LLM.health(probe=probe)


@app.post('/api/warmup')
async def warmup():
    started = time.monotonic()
    try:
        await LLM.warmup()
    except ModelUnavailable as exc:
        raise model_error(exc) from exc
    except httpx.HTTPError as exc:
        raise model_error(ModelUnavailable(f'OLLAMA_UNREACHABLE: {str(exc)[:160]}', 'OLLAMA_UNREACHABLE')) from exc
    return {'warmed': True, 'model': LLM.model, 'observed_ms': int((time.monotonic() - started) * 1000)}


@app.get('/api/policy/safety')
async def safety_policy():
    return {'version': safety.POLICY_VERSION, 'hash': safety.POLICY_HASH, 'rules': safety.POLICY['rules'],
            'note': 'Quoted provenance is design provenance from the founder-supplied documents, not legal evidence.'}


@app.get('/api/rubric')
async def rubric_catalog():
    """All 67 team-rubric checks, verbatim, with provenance and FounderOS's labelled implementation overlay."""
    return rubric.catalog()


class RubricJudge(BaseModel):
    only: str | None = Field(default=None, max_length=60, pattern='^([a-z_]{3,60}|D0[3-7])$')
    max_calls: int = Field(default=4, ge=1, le=12)


@app.get('/api/projects/{pid}/rubric')
async def project_rubric(pid: str, project=Depends(authorize)):
    """Research Matrix: every check with its status, evidence, queries tried and next step. Code only, no model call."""
    with conn() as db:
        brief = latest_brief(db, pid)
        if brief is None:
            return {'coverage': rubric.coverage(), 'checks': [], 'dimensions': {}, 'note': 'Refine the brief first.'}
        srow = safety_for(db, pid, brief['version'])
        cfg, _ = config_of(db, pid)
        ev = criteria.annotate(evidence_of(db, pid), brief['payload'], cfg)
        ex = experiments_of(db, pid)
        g = granular_for(db, pid, brief, srow, ev, ex, cfg)
    bp = dict(brief['payload'], original_idea_text=project['original_idea'])
    for c in g['checks']:
        if c['kind'] != 'knockout':
            c['search'] = rubric.check_queries(c['id'], bp)
    return {'coverage': rubric.coverage(), 'brief_version': brief['version'], **g,
            'note': 'Statuses are computed by code from accepted, relevant, linked evidence. UNKNOWN means not yet researched or not enough evidence, never a low score.'}


@app.post('/api/projects/{pid}/rubric/judge')
async def judge_rubric(pid: str, req: RubricJudge, project=Depends(authorize)):
    """Judge checks that have eligible evidence (one local-model call each, highest decision risk first, cached)."""
    not_stopped(project)
    with conn() as db:
        brief = latest_brief(db, pid)
        if brief is None:
            raise HTTPException(409, 'Refine the founder brief first')
        cfg, _ = config_of(db, pid)
        ev = criteria.annotate(evidence_of(db, pid), brief['payload'], cfg)
        ex = experiments_of(db, pid)
    try:
        results, calls = await run_rubric_judges(pid, brief['payload'], ev, ex, cfg, only=req.only, max_calls=req.max_calls)
    except ModelUnavailable as exc:
        raise model_error(exc) from exc
    return {'judged': {k: {'valid': v.get('valid'), 'rating': v.get('rating'), 'caps': v.get('caps'), 'rejected_reason': v.get('rejected_reason')}
                       for k, v in results.items()}, 'model_calls': calls,
            'note': 'Checks without eligible evidence were not sent to the model; they stay UNKNOWN.'}


@app.get('/api/criteria')
async def criteria_catalog():
    return criteria.catalog()


# ----------------------------------------------------------------------------- projects & brief
@app.post('/api/projects', status_code=201)
async def create_project(req: ProjectCreate):
    reject_obvious_secrets(jsonstr(req.model_dump()))
    pid = uuid.uuid4().hex
    token = secrets.token_urlsafe(32)
    name = (req.name or re.sub(r'\s+', ' ', req.idea).strip()[:48]).strip()
    with conn() as db:
        db.execute('INSERT INTO projects(id, token_hash, original_idea, intake_json, created_at, name) VALUES(?,?,?,?,?,?)',
                   (pid, hashlib.sha256(token.encode()).hexdigest(), req.idea, jsonstr(req.model_dump()), now(), name))
        audit(db, pid, 'PROJECT_CREATED', {'input_length': len(req.idea)})
        pre = safety.find_blocks('\n'.join([req.idea] + [str(v or '') for k, v in req.model_dump().items() if v and k != 'values']))
        if pre:
            audit(db, pid, 'SAFETY_PRESCREEN_BLOCK', {'rules': [f['rule_id'] for f in pre]})
    return {'project_id': pid, 'access_token': token, 'name': name,
            'prescreen': {'status': 'BLOCK' if pre else 'NOT_YET_SCREENED', 'findings': pre},
            'notice': 'The project token is stored only in this browser. It is shown once and is never recoverable.'}


@app.get('/api/projects/{pid}')
async def get_project(pid: str, project=Depends(authorize)):
    return public_project(pid)


@app.get('/api/projects/{pid}/summary')
async def project_summary(pid: str, project=Depends(authorize)):
    s = public_project(pid)
    ev = (s['criteria']['discover'] or {}).get('evaluation') or {}
    return {'id': pid, 'name': s['project']['name'], 'created_at': s['project']['created_at'], 'stopped': s['current']['stopped'],
            'brief_version': s['brief'] and s['brief']['version'], 'safety': s['current']['safety'],
            'discover': s['current']['discover'], 'discover_exit': ev.get('exit'), 'validate': s['current']['validate'],
            'verdict': s['passport'] and s['passport']['verdict'].get('verdict'), 'evidence': len(s['evidence'])}


def apply_fields(payload, fields):
    """Write typed fields into the flat payload. Model suggestions are kept but NOT promoted to field values."""
    payload['fields'] = fields
    for key in BRIEF_FIELDS:
        f = fields.get(key) or {}
        payload[key] = f.get('value') if f.get('status') in brief_extract.COUNTS_AS_CAPTURED else None
    payload['model_suggestions'] = {k: (fields.get(k) or {}).get('value') if (fields.get(k) or {}).get('status') == 'MODEL_SUGGESTED_UNCONFIRMED'
                                    else (fields.get(k) or {}).get('model_suggestion') for k in BRIEF_FIELDS}
    payload['model_suggestions'] = {k: v for k, v in payload['model_suggestions'].items() if v}
    payload['provenance'] = brief_extract.legacy_provenance(fields)
    payload['d02_preview'] = brief_extract.d02(fields)
    return payload


def _brief_payload_from(project, intake, answers, result=None, model_flags=None, confirmed=None, previous_fields=None):
    payload = (result or {}).copy()
    payload.setdefault('idea_summary', project['original_idea'][:300])
    payload['questions'] = (payload.get('questions') or [])[:3]
    payload.setdefault('assumptions', [])
    model_vals = {k: (result or {}).get(k) for k in BRIEF_FIELDS}
    fields = brief_extract.merge(project['original_idea'], intake, answers, confirmed=confirmed, model=model_vals, previous=previous_fields)
    apply_fields(payload, fields)
    payload.pop('risk_flags', None)
    payload['model_risk_flags'] = model_flags or []
    payload['founder_answers'] = answers
    payload['original_idea_text'] = project['original_idea']
    return payload


@app.post('/api/projects/{pid}/refine')
async def refine(pid: str, project=Depends(authorize)):
    not_stopped(project)
    intake = json.loads(project['intake_json'])
    with conn() as db:
        current = latest_brief(db, pid)
    answers = current['payload'].get('founder_answers', {}) if current else {}
    full = '\n'.join([project['original_idea']] + [str(v or '') for k, v in intake.items() if k != 'values'] + list(answers.values()))
    pre = safety.find_blocks(full)
    latency, model_flags = None, []
    if pre:
        # Knockouts run first (PDF p.2): a prohibited brief never gets a model call.
        payload = _brief_payload_from(project, intake, answers)
        payload['model'] = 'NOT_CALLED_SAFETY_BLOCK'
    else:
        started = time.monotonic()
        try:
            result = await LLM.generate(REFINE_SYSTEM, {'founder_input': project['original_idea'], 'explicit_form_fields': intake,
                                                       'previous_clarifications': answers}, RefinedBrief, max_tokens=520)
        except (ModelUnavailable, ModelOutputError) as exc:
            raise model_error(exc) from exc
        latency = int((time.monotonic() - started) * 1000)
        raw = result.model_dump()
        model_flags = [f for f in raw.get('risk_flags') or [] if f.get('rule_id') in safety.RULES]
        payload = _brief_payload_from(project, intake, answers, raw, model_flags)
        payload['model'] = LLM.model
        payload['latency_ms'] = latency
    with conn() as db:
        current = latest_brief(db, pid)
        version = (current['version'] + 1) if current else 1
        db.execute('INSERT INTO briefs(project_id,version,payload_json,created_at) VALUES(?,?,?,?)', (pid, version, jsonstr(payload), now()))
        invalidate_runs(db, pid, f'brief changed to v{version}')
        assessment = store_safety(db, pid, version, project, payload)
        audit(db, pid, 'BRIEF_REFINED', {'version': version, 'unknowns': missing_fields({'payload': payload}), 'model': payload['model'],
                                         'latency_ms': latency, 'criteria_version': criteria.VERSION})
    return {'version': version, 'brief': payload, 'safety': assessment, 'missing_fields': missing_fields({'payload': payload}), 'latency_ms': latency}


@app.post('/api/projects/{pid}/clarify')
async def clarify(pid: str, req: ClarifyRequest, project=Depends(authorize)):
    reject_obvious_secrets(jsonstr(req.model_dump()))
    not_stopped(project)
    with conn() as db:
        brief = latest_brief(db, pid)
        if brief is None:
            raise HTTPException(409, 'Refine the founder brief first')
        payload = dict(brief['payload'])
        payload['founder_answers'] = dict(payload.get('founder_answers', {}))
        payload['founder_answers'].update({k: v.strip() for k, v in req.answers.items()})
        intake = json.loads(project['intake_json'])
        model_vals = payload.get('model_suggestions') or {}
        prev_fields = payload.get('fields') or {}
        confirmed = [k for k, f in prev_fields.items() if isinstance(f, dict) and f.get('status') == 'FOUNDER_CONFIRMED']
        fields = brief_extract.merge(project['original_idea'], intake, payload['founder_answers'], confirmed=confirmed, model=model_vals, previous=prev_fields)
        apply_fields(payload, fields)
        version = brief['version'] + 1
        db.execute('INSERT INTO briefs(project_id,version,payload_json,created_at) VALUES(?,?,?,?)', (pid, version, jsonstr(payload), now()))
        invalidate_runs(db, pid, f'brief corrected to v{version} (fields: {", ".join(req.answers)})')
        assessment = store_safety(db, pid, version, project, payload)
        audit(db, pid, 'BRIEF_CLARIFIED', {'fields': list(req.answers), 'version': version})
    return {'version': version, 'brief': payload, 'safety': assessment, 'missing_fields': missing_fields({'payload': payload})}


class ConfirmFields(BaseModel):
    fields: list[str] = Field(min_length=1, max_length=9)


@app.post('/api/projects/{pid}/brief/confirm')
async def confirm_fields(pid: str, req: ConfirmFields, project=Depends(authorize)):
    """Founder confirms values as written. Own-words spans are kept; a model suggestion becomes the founder's answer."""
    not_stopped(project)
    bad = [f for f in req.fields if f not in BRIEF_FIELDS]
    if bad:
        raise HTTPException(422, f'Unknown fields: {bad}')
    with conn() as db:
        brief = latest_brief(db, pid)
        if brief is None:
            raise HTTPException(409, 'Refine the founder brief first')
        payload = dict(brief['payload'])
        prev = payload.get('fields') or {}
        answers = dict(payload.get('founder_answers') or {})
        confirmed = [k for k, f in prev.items() if isinstance(f, dict) and f.get('status') == 'FOUNDER_CONFIRMED']
        for f in req.fields:
            row = prev.get(f) or {}
            if not row.get('value'):
                raise HTTPException(422, f'{f} has no value to confirm; type an answer instead.')
            if row.get('status') == 'MODEL_SUGGESTED_UNCONFIRMED':
                answers[f] = row['value']
            else:
                confirmed.append(f)
        payload['founder_answers'] = answers
        fields = brief_extract.merge(project['original_idea'], json.loads(project['intake_json']), answers, confirmed=confirmed,
                                     model=payload.get('model_suggestions') or {}, previous=prev)
        apply_fields(payload, fields)
        version = brief['version'] + 1
        db.execute('INSERT INTO briefs(project_id,version,payload_json,created_at) VALUES(?,?,?,?)', (pid, version, jsonstr(payload), now()))
        invalidate_runs(db, pid, f'brief fields confirmed in v{version} ({", ".join(req.fields)})')
        assessment = store_safety(db, pid, version, project, payload, keep_ack=False)
        audit(db, pid, 'BRIEF_FIELDS_CONFIRMED', {'fields': req.fields, 'version': version, 'd02': payload['d02_preview']['status']})
    return {'version': version, 'brief': payload, 'safety': assessment, 'd02': payload['d02_preview']}


@app.post('/api/projects/{pid}/safety/acknowledge')
async def acknowledge_risk(pid: str, req: SafetyAck, project=Depends(authorize)):
    not_stopped(project)
    with conn() as db:
        brief = latest_brief(db, pid)
        if not brief or brief['version'] != req.brief_version:
            raise HTTPException(409, 'Acknowledgment must reference the latest brief version')
        row = safety_for(db, pid, req.brief_version)
        if not row:
            raise HTTPException(409, 'No safety assessment for this brief version')
        if row['status'] == 'BLOCK':
            raise HTTPException(403, 'This brief has a HARD STOP. Founder acknowledgment cannot override it; revise the brief.')
        if row['status'] != 'REVIEW_REQUIRED':
            raise HTTPException(409, 'No acknowledgment needed for this status')
        db.execute('UPDATE safety_assessments SET acknowledged_at=?, ack_statement=? WHERE project_id=? AND brief_version=?',
                   (now(), req.statement, pid, req.brief_version))
        audit(db, pid, 'RISK_ACKNOWLEDGED', {'brief_version': req.brief_version, 'scope': 'RESEARCH_ONLY',
                                             'rules': [f['rule_id'] for f in row['assessment']['findings']]})
    return {'acknowledged': True, 'brief_version': req.brief_version, 'scope': 'RESEARCH_ONLY',
            'notice': 'Acknowledgment permits research only. It does not certify legality or permit building, launching or any external action.'}


class SafetySourceIn(BaseModel):
    rule_id: str
    url: str = Field(min_length=12, max_length=2000)
    excerpt: str = Field(min_length=12, max_length=1200)
    finding: str = Field(pattern='^(PROHIBITS|REQUIRES_UNOBTAINABLE_LICENCE|REQUIRES_LICENCE|SETS_RULES|DOES_NOT_ADDRESS)$')


@app.post('/api/projects/{pid}/safety/sources')
async def attach_safety_source(pid: str, req: SafetySourceIn, project=Depends(authorize)):
    """Attach an official source to a legal rule. Verified excerpt + official-style domain are both required before it can count."""
    not_stopped(project)
    if req.rule_id not in ('illegal_in_target_market', 'regulated_or_sensitive_area'):
        raise HTTPException(422, 'Official sources apply to illegal_in_target_market and regulated_or_sensitive_area only.')
    reject_obvious_secrets(req.excerpt)
    try:
        f = await research.safe_fetch(req.url)
        url_status, ex = 'URL_ACCESSIBLE', ('EXCERPT_MATCHED' if research.excerpt_in(f['text'], req.excerpt) else 'NOT_MATCHED')
        host, final, sha, when = urlparse(f['final_url']).hostname, f['final_url'], f['sha256'], f['retrieved_at']
    except FetchError as exc:
        url_status, ex, host, final, sha, when = 'UNVERIFIED', 'NOT_CHECKED', urlparse(req.url).hostname, None, None, None
    official = safety.is_official_domain(host or '')
    with conn() as db:
        brief = latest_brief(db, pid)
        if not brief:
            raise HTTPException(409, 'Refine the brief first')
        sid = uuid.uuid4().hex
        jur = safety.jurisdiction_of(safety_fields(project, brief['payload']))
        db.execute('INSERT INTO safety_sources(id,project_id,brief_version,rule_id,url,final_url,excerpt,finding,jurisdiction,official_domain,url_status,excerpt_status,retrieved_at,source_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (sid, pid, brief['version'], req.rule_id, req.url, final, req.excerpt, req.finding, jur.get('country'), int(official),
                    url_status, ex, when, sha, now()))
        before = safety_for(db, pid, brief['version'])
        assessment = store_safety(db, pid, brief['version'], project, brief['payload'], keep_ack=True)
        if before and before['status'] != assessment['status']:
            invalidate_runs(db, pid, f'safety status changed to {assessment["status"]} after an official source was attached')
        audit(db, pid, 'SAFETY_SOURCE_ATTACHED', {'rule_id': req.rule_id, 'finding': req.finding, 'url_status': url_status,
                                                  'excerpt_status': ex, 'official_domain': official})
    return {'id': sid, 'url_status': url_status, 'excerpt_status': ex, 'official_domain': official, 'safety_status': assessment['status'],
            'notice': 'A source only counts if the page was fetched, the exact excerpt was found, and the domain looks official. This is still not legal advice.'}


def require_safety_clearance(db, pid, brief):
    row = safety_for(db, pid, brief['version'])
    if not row:
        raise HTTPException(409, 'Brief has no safety assessment; refine it first')
    if row['status'] == 'BLOCK':
        raise HTTPException(403, {'message': 'HARD STOP by backend safety policy. Not overridable by founder approval or model output.',
                                  'findings': row['assessment']['findings']})
    if row['status'] == 'REVIEW_REQUIRED' and not row['acknowledged_at']:
        raise HTTPException(409, 'Safety review required: acknowledge the flagged checks (research only) for this brief version first.')
    return row


# ----------------------------------------------------------------------------- criteria config + evaluation
class ConfigChange(BaseModel):
    changes: dict


@app.post('/api/projects/{pid}/criteria/config')
async def change_config(pid: str, req: ConfigChange, project=Depends(authorize)):
    not_stopped(project)
    with conn() as db:
        cfg, v = config_of(db, pid)
        try:
            new = criteria.apply_changes(cfg, req.changes)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, f'{exc}') from exc
        h = stable_hash(new)
        db.execute('INSERT INTO criteria_configs(project_id,version,payload_json,config_hash,created_at) VALUES(?,?,?,?,?)', (pid, v + 1, jsonstr(new), h, now()))
        invalidate_runs(db, pid, f'criteria settings changed to v{v + 1}')
        audit(db, pid, 'CRITERIA_CONFIG_CHANGED', {'from_version': v, 'to_version': v + 1, 'config_hash': h, 'changes': req.changes,
                                                    'criteria_version': criteria.VERSION})
    return {'version': v + 1, 'config': new, 'config_hash': h,
            'notice': 'New settings version. Approvals made under the old settings are invalidated; re-run to apply.'}


def live_discover_fingerprint(db, pid):
    brief = latest_brief(db, pid)
    if not brief:
        return None
    srow = safety_for(db, pid, brief['version'])
    run = latest_run(db, pid, 'discover')
    cfg, _ = config_of(db, pid)
    ev = evidence_of(db, pid)
    ex = experiments_of(db, pid)
    ann = criteria.annotate(ev, brief['payload'], cfg)
    quality = criteria.prepare(brief['payload'], ann, ex, cfg)
    g = granular_for(db, pid, brief, srow, ann, ex, cfg)
    fp = {'phase': 'discover', 'brief_version': brief['version'], 'safety': srow and srow['status'],
          'safety_policy': srow and srow['assessment'].get('policy_hash'), 'criteria_policy': criteria.POLICY_HASH,
          'config': stable_hash(cfg), 'run_id': run and run['id'],
          'evidence': sorted((e['id'], quality[e['id']]['grade']) for e in ev),
          'experiments': sorted((x['id'], x['version'], x['status'], x.get('result_evidence_id')) for x in ex),
          'rubric': criteria.granular_signature(g)}
    return stable_hash(fp)


def research_runs_of(db, pid):
    return qall(db, 'SELECT * FROM research_runs WHERE project_id=? ORDER BY created_at DESC LIMIT 400', (pid,))


def rubric_judgments_for(db, evidence, quality):
    out = {}
    for cid, rows in rubric.judgeable(evidence, quality):
        hit = qone(db, 'SELECT payload_json FROM judgments WHERE cache_key=?', (rubric.cache_key(cid, rows, LLM.model),))
        if hit:
            out[cid] = json.loads(hit['payload_json'])
    return out


def granular_for(db, pid, brief, srow, evidence, experiments, cfg):
    """Evaluate all 67 team-rubric checks (code only; uses cached validated judgments)."""
    quality = criteria.prepare(brief['payload'], evidence, experiments, cfg)
    return rubric.evaluate(brief['payload'], evidence, quality, rubric_judgments_for(db, evidence, quality), research_runs_of(db, pid),
                           srow and srow['assessment'])


async def run_rubric_judges(pid, brief, evidence, experiments, cfg, only=None, max_calls=6):
    """One local-model call per granular check that has eligible evidence, highest decision risk first. Cached; validated in code."""
    quality = criteria.prepare(brief, evidence, experiments, cfg)
    calls, results = 0, {}
    for cid, rows in rubric.judgeable(evidence, quality, only):
        key = rubric.cache_key(cid, rows, LLM.model)
        with conn() as db:
            hit = qone(db, 'SELECT payload_json FROM judgments WHERE cache_key=?', (key,))
        if hit:
            results[cid] = json.loads(hit['payload_json'])
            continue
        if calls >= max_calls:
            continue
        ctx, alias = rubric.judge_input(cid, brief, rows)
        t = time.monotonic()
        try:
            out = await LLM.generate(CHECK_JUDGE_SYSTEM, ctx, CheckJudgeOutput, max_tokens=220)
            calls += 1
            j = rubric.validate_judgment(cid, out.model_dump(), alias, rows)
        except ModelOutputError as exc:
            calls += 1
            j = {'valid': False, 'rejected_reason': f'model output unusable (parse failure falls back to UNKNOWN): {str(exc)[:120]}'}
        j['model'], j['judged_at'], j['rubric_version'] = LLM.model, now(), rubric.VERSION
        with conn() as db:
            db.execute('INSERT OR REPLACE INTO judgments(cache_key,project_id,criterion_id,payload_json,model,latency_ms,created_at) VALUES(?,?,?,?,?,?,?)',
                       (key, pid, cid, jsonstr(j), LLM.model, int((time.monotonic() - t) * 1000), now()))
            audit(db, pid, 'RUBRIC_CHECK_JUDGED' if j.get('valid') else 'RUBRIC_JUDGMENT_REJECTED',
                  {'check': cid, 'rating': j.get('rating'), 'rejected_reason': j.get('rejected_reason'), 'caps': j.get('caps'),
                   'evidence_ids': j.get('evidence_ids'), 'rubric_version': rubric.VERSION})
        results[cid] = j
    return results, calls


async def run_judges(pid, phase, brief, evidence, experiments, cfg):
    """One judge call per scored criterion that has accepted evidence (PDF p.10 rules 3–5). Cached."""
    jobs = criteria.judgeable_rows(phase, brief, evidence, experiments, cfg)
    results, calls = {}, 0
    for cid, rows, quality in jobs:
        key = criteria.judge_cache_key(cid, rows, quality, LLM.model)
        with conn() as db:
            hit = qone(db, 'SELECT payload_json FROM judgments WHERE cache_key=?', (key,))
        if hit:
            results[cid] = json.loads(hit['payload_json'])
            continue
        ctx, alias = criteria.judge_input(cid, brief, rows, quality)
        t = time.monotonic()
        try:
            out = await LLM.generate(JUDGE_SYSTEM, ctx, JudgeOutput, max_tokens=260)
            calls += 1
            j = criteria.validate_judgment(cid, out.model_dump(), alias, rows, brief)
        except ModelOutputError as exc:
            j = {'valid': False, 'rejected_reason': f'model output unusable: {str(exc)[:120]}'}
        j['model'] = LLM.model
        j['judged_at'] = now()
        with conn() as db:
            db.execute('INSERT OR REPLACE INTO judgments(cache_key,project_id,criterion_id,payload_json,model,latency_ms,created_at) VALUES(?,?,?,?,?,?,?)',
                       (key, pid, cid, jsonstr(j), LLM.model, int((time.monotonic() - t) * 1000), now()))
            audit(db, pid, 'CRITERION_JUDGED' if j.get('valid') else 'CRITERION_JUDGMENT_REJECTED',
                  {'criterion': cid, 'score': j.get('score'), 'rejected_reason': j.get('rejected_reason'), 'evidence_ids': j.get('evidence_ids')})
        results[cid] = j
    return results, calls


def _blocked_count(db, pid):
    return qone(db, 'SELECT COUNT(*) n FROM audit WHERE project_id=? AND event="EXTERNAL_ACTION_BLOCKED"', (pid,))['n']


def store_discover_evaluation(db, pid, judgments):
    brief = latest_brief(db, pid)
    srow = safety_for(db, pid, brief['version'])
    run = latest_run(db, pid, 'discover')
    cfg, _ = config_of(db, pid)
    ev = criteria.annotate(evidence_of(db, pid), brief['payload'], cfg)
    ex = experiments_of(db, pid)
    e = criteria.evaluate_discover(brief=brief['payload'], brief_version=brief['version'], safety=srow and srow['assessment'],
                                   safety_ack=bool(srow and srow['acknowledged_at']), discovery=run and run['report'],
                                   discovery_run_id=run and run['id'], evidence=ev, experiments=ex, judgments=judgments, cfg=cfg,
                                   blocked_actions=_blocked_count(db, pid), granular=granular_for(db, pid, brief, srow, ev, ex, cfg))
    last = latest_eval(db, pid, 'discover')
    version = (last['version'] + 1) if last else 1
    db.execute('INSERT INTO criteria_evaluations(id,project_id,phase,version,payload_json,evaluation_hash,fingerprint_hash,criteria_version,criteria_policy_hash,config_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
               (uuid.uuid4().hex, pid, 'discover', version, jsonstr(e), e['evaluation_hash'], e['fingerprint_hash'], criteria.VERSION,
                criteria.POLICY_HASH, e['config_hash'], now()))
    audit(db, pid, 'CRITERIA_EVALUATED', {'phase': 'discover', 'version': version, 'exit': e['exit'], 'unknown_count': e['unknown_count'],
                                          'evaluation_hash': e['evaluation_hash'], 'criteria_version': criteria.VERSION, 'config_hash': e['config_hash']})
    return e, version


@app.post('/api/projects/{pid}/criteria/evaluate')
async def evaluate_criteria(pid: str, project=Depends(authorize)):
    """Re-evaluate the Discover gate after research: runs judges only where accepted evidence exists."""
    not_stopped(project)
    with conn() as db:
        brief = latest_brief(db, pid)
        run = latest_run(db, pid, 'discover')
        if not brief or not run:
            raise HTTPException(409, 'Run the discovery agent first.')
        cfg, _ = config_of(db, pid)
        ev = criteria.annotate(evidence_of(db, pid), brief['payload'], cfg)
        ex = experiments_of(db, pid)
    try:
        judgments, calls = await run_judges(pid, 'discover', brief['payload'], ev, ex, cfg)
        _, rcalls = await run_rubric_judges(pid, brief['payload'], ev, ex, cfg, max_calls=6)
    except ModelUnavailable as exc:
        raise model_error(exc) from exc
    with conn() as db:
        e, version = store_discover_evaluation(db, pid, judgments)
    return {'version': version, 'evaluation': e, 'judge_calls': calls + rcalls, 'rubric_judge_calls': rcalls}


@app.get('/api/projects/{pid}/criteria')
async def project_criteria(pid: str, project=Depends(authorize)):
    with conn() as db:
        ev = latest_eval(db, pid, 'discover')
        live = live_discover_fingerprint(db, pid) if ev else None
        cfg, v = config_of(db, pid)
    return {'criteria_version': criteria.VERSION, 'policy_hash': criteria.POLICY_HASH, 'config': cfg, 'config_version': v,
            'discover': ev and {**ev, 'stale': ev['fingerprint_hash'] != live}}


# ----------------------------------------------------------------------------- phase runs
@app.post('/api/projects/{pid}/phases/{phase}/run')
async def run_phase(pid: str, phase: str, project=Depends(authorize)):
    if phase in PHASES and phase not in ACTIVE_PHASES:
        raise HTTPException(409, f'Phase "{phase}" is run through its own workflow endpoints (/api/projects/{{id}}/workflow); see ARCHITECTURE.md.')
    if phase not in ACTIVE_PHASES:
        raise HTTPException(404, 'Unknown phase')
    not_stopped(project)
    with conn() as db:
        brief = latest_brief(db, pid)
        if brief is None:
            raise HTTPException(409, 'Refine the founder brief first')
        safety_row = require_safety_clearance(db, pid, brief)
        prior = latest_run(db, pid, phase)
        discovery = latest_run(db, pid, 'discover')
        cfg, _ = config_of(db, pid)
        evidence = criteria.annotate(evidence_of(db, pid), brief['payload'], cfg)
        experiments = experiments_of(db, pid)
        previous_decision = qone(db, 'SELECT action,feedback FROM decisions WHERE phase_run_id=?', (prior['id'],)) if prior else None
    if prior and prior['state'] in ('PENDING_APPROVAL', 'APPROVED'):
        raise HTTPException(409, 'The current run is waiting for your decision or already approved. Choose Revise to run it again.')
    if phase == 'validate':
        if discovery is None or discovery['state'] != 'APPROVED':
            raise HTTPException(409, 'Approve the latest discovery (for the current brief) before validation.')
        if discovery['brief_version'] != brief['version']:
            raise HTTPException(409, 'Discovery approval belongs to an older brief version; re-run discovery.')
    ctx = {'founder_brief': {k: brief['payload'].get(k) for k in ('idea_summary',) + BRIEF_FIELDS},
           'provenance': brief['payload'].get('provenance', {})}
    if prior and prior['state'] in ('REVISE_REQUESTED', 'PIVOT_REQUESTED'):
        ctx['previous_report'] = {k: v for k, v in prior['report'].items() if not k.startswith('_')}
        ctx['founder_revision_feedback'] = previous_decision['feedback'] if previous_decision else (prior.get('invalidated_reason') or '')
        ctx['revision_type'] = prior['state']
    started = time.monotonic()
    judge_calls = 0
    if phase == 'discover':
        try:
            result = await LLM.generate(DISCOVER_SYSTEM, ctx, DiscoveryReport, max_tokens=900)
        except (ModelUnavailable, ModelOutputError) as exc:
            raise model_error(exc) from exc
        report = result.model_dump()
        bp = dict(brief['payload'], original_idea_text=project['original_idea'])
        issues = discovery_guard.review(report, bp)
        quality = {'attempts': 1, 'first_pass_issues': issues}
        if discovery_guard.high(issues):
            # Retry ONCE with the specific problems listed; then degrade gracefully (remove, never invent).
            try:
                retry = await LLM.generate(DISCOVER_SYSTEM, {**ctx, 'correction': discovery_guard.correction_message(issues)}, DiscoveryReport, max_tokens=900)
                report2 = retry.model_dump()
                issues2 = discovery_guard.review(report2, bp)
                quality['attempts'] = 2
                if len(discovery_guard.high(issues2)) <= len(discovery_guard.high(issues)):
                    report, issues = report2, issues2
            except (ModelUnavailable, ModelOutputError) as exc:
                quality['retry_error'] = str(exc)[:160]
            if discovery_guard.high(issues):
                report = discovery_guard.degrade(report, issues)
                quality['degraded'] = True
        quality['remaining_issues'] = issues
        report['directions'] = (report.get('directions') or [])[:3]
        for i, d in enumerate(report['directions']):
            d['id'] = 'ABC'[i]
        report['_quality'] = quality
        report['_label'] = 'HYPOTHESES: everything below was written by the local model from your brief. None of it is evidence.'
        report['_status'] = 'AI_HYPOTHESES_ONLY: nothing here is evidence; no customer was contacted.'
        report['_skeptic_flags'] = skeptic_review(report)
        report['_safety_flags'] = safety.screen_agent_output(report)
        gate = {'phase': 'discover', 'note': 'The Discover gate (D09) is the latest criteria evaluation, recomputed in code.', 'approval_scope': 'RESEARCH_ONLY',
                'external_actions_permitted': False}
    else:
        register = risk_register(brief['payload'], discovery['report'], discovery['version'],
                                 [e for e in evidence if not e.get('duplicate_of') and not e.get('injection_flag')])
        verdict = evaluate_validation(brief=brief['payload'], brief_version=brief['version'], safety=safety_row['assessment'],
                                      discovery=discovery['report'], discovery_version=discovery['version'],
                                      evidence=evidence, experiments=experiments)
        try:
            judgments, judge_calls = await run_judges(pid, 'validate', brief['payload'], evidence, experiments, cfg)
        except ModelUnavailable as exc:
            raise model_error(exc) from exc
        with conn() as db:
            blocked = _blocked_count(db, pid)
        vcrit = criteria.evaluate_validate(brief=brief['payload'], brief_version=brief['version'], safety=safety_row['assessment'],
                                           safety_ack=bool(safety_row['acknowledged_at']), discovery=discovery['report'],
                                           evidence=evidence, experiments=experiments, judgments=judgments, cfg=cfg,
                                           register=verdict['risk_register'], blocked_actions=blocked)
        ctx['discovery_report'] = {k: v for k, v in discovery['report'].items() if not k.startswith('_')}
        ctx['evidence_ledger'] = [{'id': e['id'][:8], 'kind': e['kind'], 'dimension': e['dimension'], 'claim': e['claim'],
                                   'direction': e['direction'], 'url_status': e['url_status'], 'excerpt_status': e['excerpt_status'],
                                   'independence': e['independence'], 'sample_size': e['sample_size'], 'outcome': e['outcome'],
                                   'counted': not any(x['id'] == e['id'] for x in verdict['excluded_evidence'])}
                                  for e in evidence if not e['injection_flag']][:20]
        ctx['backend_verdict'] = {'verdict': verdict['verdict'], 'headline': verdict['headline'],
                                  'matrix': {k: v['status'] for k, v in verdict['matrix'].items()},
                                  'unresolved_critical_assumptions': [u['claim_id'] for u in verdict['unresolved_critical_assumptions']]}
        try:
            result = await LLM.generate(VALIDATE_SYSTEM, ctx, ValidationReport, max_tokens=700)
            report = prose.clean_report(result.model_dump(), verdict['verdict'])
        except ModelUnavailable as exc:
            raise model_error(exc) from exc
        except ModelOutputError as exc:
            # The verdict is computed by code; a malformed model narrative must not block it.
            report = {'summary': prose.UNKNOWN, 'market_research_vs_customer_demand': prose.UNKNOWN, 'risks': [], 'contradictions_or_gaps': [],
                      'pricing_hypotheses': [], 'business_model_hypotheses': [], 'competitor_research_limitations': [],
                      '_model_error': f'The model narrative was unusable and was omitted ({str(exc)[:120]}). The code verdict is unaffected.',
                      '_prose_checks': []}
        report['_status'] = 'VALIDATION_ASSISTANCE: AI explanation of a backend-computed verdict. Not customer testing.'
        report['_skeptic_flags'] = skeptic_review(report)
        report['_safety_flags'] = safety.screen_agent_output(report)
        gate = verdict
        gate['criteria'] = {k: vcrit[k] for k in ('criteria', 'unknown_count', 'criteria_version', 'criteria_policy_hash', 'config_hash', 'evaluation_hash')}
        gate['explanation'] = prose.verdict_explanation(verdict)
        gate['simulated_results_not_counted'] = [x['id'] for x in experiments if (x['payload'] or {}).get('simulated')]
    latency = int((time.monotonic() - started) * 1000)
    report_hash = stable_hash(report)
    input_hash = stable_hash({'brief_version': brief['version'], 'safety': safety_row['status'], 'policy': safety_row['assessment'].get('policy_hash'),
                              'criteria_policy': criteria.POLICY_HASH, 'config': stable_hash(cfg),
                              'discovery_run': discovery['id'] if phase == 'validate' else None,
                              'evidence': [e['id'] for e in evidence] if phase == 'validate' else None,
                              'experiments': [(x['id'], x['version'], x['status']) for x in experiments] if phase == 'validate' else None})
    run_id = uuid.uuid4().hex
    with conn() as db:
        last = latest_run(db, pid, phase)
        if last and last['state'] in ('PENDING_APPROVAL', 'APPROVED'):
            raise HTTPException(409, 'Another run was saved concurrently')
        if latest_brief(db, pid)['version'] != brief['version']:
            raise HTTPException(409, 'The brief changed while the agent ran; run it again.')
        if phase == 'validate':
            d = latest_run(db, pid, 'discover')
            if not d or d['id'] != discovery['id'] or d['state'] != 'APPROVED':
                raise HTTPException(409, 'Discovery approval changed while validation ran')
        version = (last['version'] + 1) if last else 1
        db.execute('INSERT INTO phase_runs(id,project_id,phase,version,state,report_json,gate_json,brief_version,safety_status,report_hash,input_hash,upstream_run_id,model,latency_ms,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (run_id, pid, phase, version, 'PENDING_APPROVAL', jsonstr(report), jsonstr(gate), brief['version'], safety_row['status'],
                    report_hash, input_hash, discovery['id'] if phase == 'validate' else None, LLM.model, latency, now()))
        audit(db, pid, 'PHASE_RUN_READY', {'phase': phase, 'run_id': run_id, 'version': version, 'brief_version': brief['version'],
                                           'gate': gate.get('verdict'), 'report_hash': report_hash, 'model': LLM.model, 'latency_ms': latency,
                                           'criteria_version': criteria.VERSION, 'judge_calls': judge_calls,
                                           'agent_output_safety_flags': len(report['_safety_flags'])})
        evaluation = None
        if phase == 'discover':
            evaluation, _ = store_discover_evaluation(db, pid, judgments_for(db, pid, 'discover', brief['payload'], evidence, experiments, cfg))
    return {'run_id': run_id, 'version': version, 'phase': phase, 'state': 'PENDING_APPROVAL', 'report': report, 'gate': gate,
            'evaluation': evaluation, 'report_hash': report_hash, 'brief_version': brief['version'], 'latency_ms': latency, 'model': LLM.model}


ADVISES_AGAINST = ('STOP_DO_NOT_LAUNCH', 'PIVOT', 'REVISE', 'REPEAT')


@app.post('/api/projects/{pid}/phases/{phase}/decision')
async def decide(pid: str, phase: str, req: DecisionRequest, project=Depends(authorize)):
    if phase not in ACTIVE_PHASES:
        raise HTTPException(404, 'Unknown active phase')
    not_stopped(project)
    reject_obvious_secrets(req.feedback)
    if safety.looks_like_injection(req.feedback):
        raise HTTPException(422, 'Feedback contains instruction-like text that tries to change rules. Remove it.')
    with conn() as db:  # BEGIN IMMEDIATE held: checks + writes are atomic, so replays cannot race.
        run = latest_run(db, pid, phase)
        if not run or run['id'] != req.run_id:
            raise HTTPException(409, 'Stale or mismatched run: this is not the latest run for this project and phase.')
        if run['state'] != 'PENDING_APPROVAL':
            raise HTTPException(409, f'This run was already decided or invalidated (state={run["state"]}); duplicates are rejected.')
        if not hmac.compare_digest(run['report_hash'], req.report_hash):
            raise HTTPException(409, 'report_hash does not match the stored report (tampered or outdated page). Reload.')
        brief = latest_brief(db, pid)
        if brief['version'] != req.brief_version or run['brief_version'] != brief['version']:
            raise HTTPException(409, 'The brief changed since this report; run it again.')
        safety_row = safety_for(db, pid, brief['version'])
        if safety_row['status'] == 'BLOCK':
            raise HTTPException(403, 'HARD STOP: no decision can approve a blocked brief.')
        cfg, _ = config_of(db, pid)
        evaluation_hash, eval_version = None, None
        if phase == 'discover':
            ev = latest_eval(db, pid, 'discover')
            if not ev:
                raise HTTPException(409, 'No criteria evaluation exists for this discovery. Re-evaluate first.')
            if ev['fingerprint_hash'] != live_discover_fingerprint(db, pid):
                raise HTTPException(409, 'Evidence, settings or brief changed since the last criteria evaluation. Press "Re-evaluate" first.')
            if req.evaluation_hash and not hmac.compare_digest(ev['evaluation_hash'], req.evaluation_hash):
                raise HTTPException(409, 'The criteria evaluation you saw is not the latest one. Reload.')
            rec = ev['evaluation']['exit']
            evaluation_hash, eval_version = ev['evaluation_hash'], ev['version']
            if rec == 'STOP':
                raise HTTPException(403, 'D01 hard stop: the system must not work on this idea.')
        else:
            rec = run['gate'].get('verdict')
            evaluation_hash = (run['gate'].get('criteria') or {}).get('evaluation_hash')
        if req.decision in ('REVISE', 'PIVOT') and not req.feedback.strip():
            raise HTTPException(422, 'Revise and Pivot need feedback that tells the agent what to change.')
        if req.decision == 'APPROVE' and rec in ADVISES_AGAINST and not req.acknowledge_risk:
            raise HTTPException(422, f'The gate says {rec}. To continue anyway, tick the acknowledgment and give your reason (research only).')
        if req.decision == 'APPROVE' and rec in ADVISES_AGAINST and not req.feedback.strip():
            raise HTTPException(422, 'Write your reason for choosing a different course than the gate.')
        state = {'APPROVE': 'APPROVED', 'REVISE': 'REVISE_REQUESTED', 'PIVOT': 'PIVOT_REQUESTED', 'STOP': 'STOPPED'}[req.decision]
        scope = 'RESEARCH_ONLY' if req.decision == 'APPROVE' else 'NONE'
        db.execute('UPDATE phase_runs SET state=? WHERE id=?', (state, run['id']))
        experiments = experiments_of(db, pid)
        decision_id = uuid.uuid4().hex
        db.execute('INSERT INTO decisions(id,project_id,phase,phase_run_id,run_version,action,scope,feedback,acknowledged_risk,actor,brief_version,safety_status,report_hash,input_hash,experiment_versions_json,gate_recommendation,created_at,criteria_version,criteria_policy_hash,config_hash,evaluation_hash,safety_policy_hash,rubric_version,rubric_hash,discover_evaluation_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (decision_id, pid, phase, run['id'], run['version'], req.decision, scope, req.feedback.strip(), int(req.acknowledge_risk),
                    'FOUNDER(project capability token)', brief['version'], safety_row['status'], run['report_hash'], run['input_hash'],
                    jsonstr([{'id': x['id'], 'version': x['version'], 'status': x['status'], 'criteria_hash': x['criteria_hash'],
                              'simulated': bool((x['payload'] or {}).get('simulated'))} for x in experiments]),
                    str(rec), now(), criteria.VERSION, criteria.POLICY_HASH, stable_hash(cfg), evaluation_hash,
                    safety_row['assessment'].get('policy_hash'), rubric.VERSION, rubric.FILE_HASH, eval_version))
        if req.decision == 'STOP':
            db.execute('UPDATE projects SET stopped=1 WHERE id=?', (pid,))
        if req.decision == 'PIVOT':
            if phase == 'validate':
                up = latest_run(db, pid, 'discover')
                if up and up['state'] == 'APPROVED':
                    db.execute('UPDATE phase_runs SET state=?, invalidated_reason=? WHERE id=?', ('PIVOT_REQUESTED', 'founder pivot from validation: ' + req.feedback[:300], up['id']))
                    audit(db, pid, 'PHASE_PIVOT_BACK_TO_DISCOVER', {'upstream_run': up['id'], 'feedback': req.feedback[:300]})
            for x in experiments:
                if x['status'] == 'LOCKED':
                    db.execute('UPDATE experiments SET status=? WHERE series_id=? AND version=?', ('ARCHIVED_PIVOT', x['id'], x['version']))
                    audit(db, pid, 'EXPERIMENT_ARCHIVED', {'experiment_id': x['id'], 'version': x['version'], 'reason': 'pivot'})
        if phase == 'discover' and req.decision in ('REVISE', 'PIVOT', 'STOP'):
            invalidate_runs(db, pid, f'discovery {req.decision.lower()}', phases=('validate',))
        audit(db, pid, 'FOUNDER_DECISION', {'phase': phase, 'run_id': run['id'], 'run_version': run['version'], 'decision': req.decision,
                                            'scope': scope, 'brief_version': brief['version'], 'report_hash': run['report_hash'],
                                            'risk_override': req.acknowledge_risk, 'gate': rec, 'decision_id': decision_id,
                                            'criteria_version': criteria.VERSION, 'evaluation_hash': evaluation_hash})
    return {'decision_id': decision_id, 'state': state, 'phase': phase, 'scope': scope, 'gate_recommendation': rec,
            'notice': 'Approval permits further research only. It never authorizes building, launching, sending, publishing, signing or spending.'}


# ----------------------------------------------------------------------------- evidence (manual + verified)
async def verify_excerpt(url: str, excerpt: str):
    """SSRF-guarded retrieval with redirect re-validation. Returns (url_status, excerpt_status, retrieved_at, note, fetch)."""
    try:
        f = await research.safe_fetch(url)
    except FetchError as exc:
        return 'UNVERIFIED', 'NOT_CHECKED', None, f'Retrieval failed safely: {exc.message}'
    if research.excerpt_in(f['text'], excerpt):
        return 'URL_ACCESSIBLE', 'EXCERPT_MATCHED', f['retrieved_at'], 'Excerpt found at URL. This proves only that the words appear there, not that the claim is true or that customers want this product.'
    return 'URL_ACCESSIBLE', 'NOT_MATCHED', f['retrieved_at'], 'URL fetched, but the excerpt was NOT found in the page text. Stays unverified.'


def _guard_validate_open(db, pid):
    validate = latest_run(db, pid, 'validate')
    if validate and validate['state'] in ('PENDING_APPROVAL', 'APPROVED'):
        raise HTTPException(409, 'Validation has a pending or approved snapshot. Choose Revise on the Decision page first; new evidence then feeds a new run.')


def insert_evidence(db, pid, *, kind, dimension, claim, direction, relevance, independence, url_status, excerpt_status, limitations,
                    dedupe_key, url=None, title=None, publisher=None, author=None, published_on=None, retrieved_at=None, excerpt=None,
                    method=None, sample_size=None, positives=None, segment=None, geography=None, collected_from=None, collected_to=None,
                    consent=False, positive_signals=None, negative_signals=None, injection=False, criterion_id=None, direction_id=None,
                    source_hash=None, candidate_id=None, doi=None, provider=None, final_url=None, claim_id=None,
                    subcriterion_id=None, source_type=None, review_state=None, review_reason=None, relevance_checks=None,
                    organization=None, meta=None):
    dup = qone(db, 'SELECT id FROM evidence WHERE project_id=? AND dedupe_key=? ORDER BY created_at LIMIT 1', (pid, dedupe_key))
    if not dup and excerpt and kind == 'SECONDARY_BACKGROUND':
        # Syndicated copy: the same passage on a different host is not independent evidence.
        for row in qall(db, 'SELECT id, excerpt FROM evidence WHERE project_id=? AND kind="SECONDARY_BACKGROUND"', (pid,)):
            if row['excerpt'] and len(norm(row['excerpt'])) > 40 and norm(row['excerpt']) == norm(excerpt):
                dup = {'id': row['id']}
                limitations = 'SYNDICATED/DUPLICATE passage of an earlier source: not double-counted. ' + limitations
                break
    if not dup and doi:
        d2 = qone(db, 'SELECT id FROM evidence WHERE project_id=? AND doi=? AND excerpt=?', (pid, doi, excerpt))
        dup = d2
    eid = uuid.uuid4().hex
    db.execute('''INSERT INTO evidence(id,project_id,kind,dimension,claim_id,claim,direction,source_url,title,publisher,author,published_on,retrieved_at,excerpt,
                  url_status,excerpt_status,relevance,independence,method,sample_size,positives,segment,geography,collected_from,collected_to,consent_confirmed,
                  experiment_id,experiment_version,outcome,rate_pct,adverse,positive_signals,negative_signals,dedupe_key,duplicate_of,injection_flag,limitations,created_at,
                  direction_id,criterion_id,source_hash,candidate_id,doi,provider,final_url,
                  subcriterion_id,source_type,review_state,review_reason,relevance_checks_json,organization,meta_json)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
               (eid, pid, kind, dimension, claim_id, claim, direction, url, title, publisher, author, published_on, retrieved_at, excerpt,
                url_status, excerpt_status, relevance, independence, method, sample_size, positives, segment, geography,
                str(collected_from) if collected_from else None, str(collected_to) if collected_to else None, int(consent),
                None, None, None, None, None, positive_signals, negative_signals, dedupe_key, dup['id'] if dup else None, int(injection),
                limitations, now(), direction_id, criterion_id, source_hash, candidate_id, doi, provider, final_url,
                subcriterion_id, source_type, review_state, review_reason, jsonstr(relevance_checks) if relevance_checks else None,
                organization, jsonstr(meta) if meta else None))
    invalidate_runs(db, pid, 'new evidence added', phases=('validate',))
    audit(db, pid, 'EVIDENCE_ADDED', {'id': eid, 'kind': kind, 'dimension': dimension, 'url_status': url_status,
                                      'excerpt_status': excerpt_status, 'duplicate_of': dup['id'] if dup else None, 'injection_flag': injection,
                                      'provider': provider, 'candidate_id': candidate_id, 'subcriterion_id': subcriterion_id,
                                      'source_type': source_type, 'review_state': review_state})
    return eid, dup


LIMITS = {
    'SECONDARY_BACKGROUND': 'Market context only. Excerpt match ≠ claim truth ≠ product demand.',
    'CUSTOMER_STATEMENT': 'Stated interest/opinion. Not demand; not a purchase. Founder-reported.',
    'CUSTOMER_BEHAVIOR': 'Observed voluntary action, founder-reported. Sample selection and incentives unassessed.',
}


def _check_link(subcriterion_id, source_type):
    if subcriterion_id and subcriterion_id not in rubric.BY_ID:
        raise HTTPException(422, f'Unknown rubric check id {subcriterion_id!r}.')
    if subcriterion_id and rubric.BY_ID[subcriterion_id]['kind'] == 'knockout':
        raise HTTPException(422, 'Ethics checks are decided by the written safety rules; attach official sources on the Safety screen.')
    if source_type and (source_type not in rubric.SOURCE_TYPES or source_type == 'BRIEF'):
        raise HTTPException(422, f'Unknown source type {source_type!r}. Allowed: {sorted(k for k in rubric.SOURCE_TYPES if k != "BRIEF")}')
    if subcriterion_id and source_type and source_type not in rubric.OV[subcriterion_id]['accepted_source_types']:
        raise HTTPException(422, {'message': f'This check asks for {", ".join(rubric.OV[subcriterion_id]["accepted_source_types"])}; '
                                             f'a {source_type} source cannot count for it. Link it to another check or leave it unlinked.'})


@app.post('/api/projects/{pid}/evidence')
async def add_evidence(pid: str, req: EvidenceAdd, project=Depends(authorize)):
    reject_obvious_secrets(jsonstr(req.model_dump()))
    not_stopped(project)
    _check_link(req.subcriterion_id, req.source_type)
    with conn() as db:
        _guard_validate_open(db, pid)
    free_text = ' '.join(filter(None, [req.claim, req.excerpt, req.method, req.positive_signals, req.negative_signals, req.title]))
    injection = safety.looks_like_injection(free_text)
    founder_supplied = False
    if req.kind == 'SECONDARY_BACKGROUND':
        url_status, excerpt_status, retrieved_at, note = await verify_excerpt(req.url, req.excerpt)
        if excerpt_status != 'EXCERPT_MATCHED' and req.founder_supplied_excerpt:
            founder_supplied = True
            url_status, excerpt_status = 'FOUNDER_SUPPLIED', 'FOUNDER_SUPPLIED_UNVERIFIED'
            note = 'Founder-supplied excerpt with URL: FounderOS could not verify it at the URL (' + note + ').'
        independence = 'INDEPENDENT_SOURCE_FOUNDER_SELECTED'
        dedupe_key = stable_hash([urlparse(req.url).hostname, urlparse(req.url).path.rstrip('/'), norm(req.excerpt)])
    else:
        url_status, excerpt_status, retrieved_at, note = 'NOT_APPLICABLE', 'NOT_APPLICABLE', None, 'Founder-run research.'
        independence = 'FOUNDER_REPORTED_NOT_INDEPENDENTLY_VERIFIED'
        dedupe_key = stable_hash([req.kind, norm(req.method), req.sample_size, req.positives, str(req.collected_from), norm(req.segment or '')])
    state, reason, rflags = review.decide(req.relevance_checks, claim=req.claim, excerpt=req.excerpt, url=req.url,
                                          verified=excerpt_status == 'EXCERPT_MATCHED', founder_supplied=founder_supplied,
                                          customer_research=req.kind != 'SECONDARY_BACKGROUND')
    limits = LIMITS[req.kind]
    if injection:
        limits = 'EXCLUDED: instruction-like text detected (possible prompt injection). Withheld from agents and gates. ' + limits
    stype = req.source_type or ('FOUNDER_CUSTOMER_RESEARCH' if req.kind != 'SECONDARY_BACKGROUND' else None)
    with conn() as db:
        eid, dup = insert_evidence(db, pid, kind=req.kind, dimension=req.dimension, claim=req.claim, direction=req.direction,
                                   relevance=review.legacy_relevance(state, req.relevance), independence=independence, url_status=url_status,
                                   excerpt_status=excerpt_status, limitations=limits + ' ' + note + (' ' + ' '.join(rflags) if rflags else ''),
                                   dedupe_key=dedupe_key, url=req.url, title=req.title, publisher=req.publisher,
                                   author=req.author, published_on=req.published_on, retrieved_at=retrieved_at, excerpt=req.excerpt,
                                   method=req.method, sample_size=req.sample_size, positives=req.positives, segment=req.segment,
                                   geography=req.geography, collected_from=req.collected_from, collected_to=req.collected_to,
                                   consent=req.consent_confirmed, positive_signals=req.positive_signals, negative_signals=req.negative_signals,
                                   injection=injection, criterion_id=req.criterion_id, direction_id=req.direction_id,
                                   provider='founder_manual', claim_id=req.claim_id, subcriterion_id=req.subcriterion_id, source_type=stype,
                                   review_state=state, review_reason=reason, relevance_checks=req.relevance_checks, organization=req.organization)
    return {'id': eid, 'kind': req.kind, 'url_status': url_status, 'excerpt_status': excerpt_status, 'independence': independence,
            'duplicate_of': dup['id'] if dup else None, 'injection_flag': injection, 'limitations': limits + ' ' + note,
            'review_state': state, 'review_reason': reason, 'review_flags': rflags,
            'notice': 'Nothing here proves demand on its own. Counting rules: docs/criteria-methodology.md'}


# ----------------------------------------------------------------------------- Research Studio
def _cand(row):
    if not row:
        return None
    r = dict(row)
    r['payload'] = json.loads(r.pop('payload_json'))
    f = r.pop('fetch_json')
    r['fetch'] = json.loads(f) if f else None
    if r['fetch']:
        r['fetch'].pop('text', None)
    return r


@app.get('/api/projects/{pid}/research/plan')
async def research_plan_v7(pid: str, project=Depends(authorize)):
    with conn() as db:
        brief = latest_brief(db, pid)
    if not brief:
        raise HTTPException(409, 'Refine the brief first: the research plan is built from it.')
    jur = safety.jurisdiction_of(safety_fields(project, brief['payload']))
    return {'brief_version': brief['version'], 'jurisdiction': jur, **research.plan(brief['payload'], jur)}


class ResearchItem(BaseModel):
    bucket: str = Field(pattern='^(PROBLEM|MARKET|COMPETITORS|FEASIBILITY|VIABILITY|SAFETY)$')
    provider: str = Field(pattern='^(crossref|openalex|worldbank)$')
    query: str | None = Field(default=None, max_length=160)
    indicator: str | None = Field(default=None, max_length=40)
    subcriterion_id: str | None = Field(default=None, max_length=60, pattern='^[a-z_]{3,60}$')


class ResearchRun(BaseModel):
    items: list[ResearchItem] = Field(min_length=1, max_length=12)


@app.post('/api/projects/{pid}/research/run')
async def research_run(pid: str, req: ResearchRun, project=Depends(authorize)):
    """Gatherer: runs the founder-approved plan items, sequentially and rate-limited. Stores candidates, never evidence."""
    not_stopped(project)
    with conn() as db:
        brief = latest_brief(db, pid)
        if not brief:
            raise HTTPException(409, 'Refine the brief first.')
        srow = safety_for(db, pid, brief['version'])
        if srow and srow['status'] == 'BLOCK':
            raise HTTPException(403, 'HARD STOP: no research is run for a blocked idea (knockouts run first).')
    jur = safety.jurisdiction_of(safety_fields(project, brief['payload']))
    summary = []
    for i, it in enumerate(req.items):
        if it.provider in ('crossref', 'openalex'):
            if not it.query or not re.search(r'[A-Za-z؀-ۿ]{3,}', it.query):
                summary.append({'bucket': it.bucket, 'provider': it.provider, 'status': 'INVALID_QUERY', 'count': 0})
                continue
            reject_obvious_secrets(it.query)
        if i:
            await asyncio_sleep(0.35)
        res = await research.run_item(it.model_dump(), jur.get('country'))
        rid = uuid.uuid4().hex
        added = 0
        with conn() as db:
            db.execute('INSERT INTO research_runs(id,project_id,bucket,provider,query,status,error,result_count,brief_version,created_at,subcriterion_id,error_code) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (rid, pid, it.bucket, it.provider, it.query or it.indicator or '', res['status'], res.get('error'), len(res.get('results', [])),
                        brief['version'], now(), it.subcriterion_id, res['status'] if res['status'] not in ('OK', 'NO_RESULTS') else None))
            for c in res.get('results', []):
                key_url, key_doi = c.get('url'), c.get('doi')
                exists = qone(db, 'SELECT id FROM research_candidates WHERE project_id=? AND ((doi IS NOT NULL AND doi=?) OR (url IS NOT NULL AND url=?))',
                              (pid, key_doi, key_url))
                if exists:
                    continue
                c = {**c, 'subcriterion_id': it.subcriterion_id, 'query': it.query}
                db.execute('INSERT INTO research_candidates(id,project_id,run_id,bucket,provider,url,doi,title,publisher,year,state,payload_json,fetch_json,evidence_id,reject_reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,?,?)',
                           (uuid.uuid4().hex, pid, rid, it.bucket, it.provider, key_url, key_doi, c.get('title'), c.get('publisher'), c.get('year'),
                            c['state'], jsonstr(c), now(), now()))
                added += 1
            audit(db, pid, 'RESEARCH_QUERY_RUN', {'bucket': it.bucket, 'provider': it.provider, 'query': (it.query or it.indicator or '')[:120],
                                                  'status': res['status'], 'results': len(res.get('results', [])), 'new_candidates': added})
        summary.append({'bucket': it.bucket, 'provider': it.provider, 'query': it.query or it.indicator, 'status': res['status'],
                        'error': res.get('error'), 'count': len(res.get('results', [])), 'new_candidates': added, 'subcriterion_id': it.subcriterion_id,
                        'recoverable': res['status'] in ('TIMEOUT', 'OFFLINE', 'RATE_LIMITED', 'PROVIDER_ERROR')})
    return {'runs': summary, 'notice': 'Candidates are not evidence. Inspect a source, pick an exact passage, then add it to the ledger.'}


async def asyncio_sleep(s):
    import asyncio
    await asyncio.sleep(s)


@app.get('/api/projects/{pid}/research')
async def research_state(pid: str, project=Depends(authorize)):
    with conn() as db:
        runs = qall(db, 'SELECT * FROM research_runs WHERE project_id=? ORDER BY created_at DESC LIMIT 60', (pid,))
        cands = [_cand(r) for r in qall(db, 'SELECT * FROM research_candidates WHERE project_id=? ORDER BY created_at DESC LIMIT 200', (pid,))]
    return {'runs': runs, 'candidates': cands, 'providers': research.PROVIDERS}


class InspectReq(BaseModel):
    url: str = Field(min_length=12, max_length=2000)
    bucket: str = Field(default='COMPETITORS', pattern='^(PROBLEM|MARKET|COMPETITORS|FEASIBILITY|VIABILITY|SAFETY)$')
    query: str | None = Field(default=None, max_length=160)


async def _fetch_into(pid, cid, url, query):
    try:
        f = await research.safe_fetch(url)
        ps = research.passages(f['text'], query or '')
        fetch = {**{k: f.get(k) for k in ('requested_url', 'final_url', 'redirects', 'content_type', 'meta', 'sha256', 'retrieved_at', 'chars', 'paywall_suspected',
                                           'truncated', 'truncation_note', 'reserved_domain')},
                 'passages': ps, 'text': f['text'], 'ranking_note': 'Passages ranked by query-term overlap: an exploratory heuristic, not relevance or truth.'}
        state, err = 'FETCHED', None
    except FetchError as exc:
        fetch, state, err = {'error': exc.message, 'error_code': exc.code, 'advice': exc.advice, 'http': exc.http, 'attempted_at': now(),
                             'recoverable': exc.code not in ('BLOCKED_ADDRESS',), 'tls_verification': 'ON (never disabled)'}, 'FETCH_FAILED', exc.message
    with conn() as db:
        db.execute('UPDATE research_candidates SET state=?, fetch_json=?, updated_at=? WHERE id=?', (state, jsonstr(fetch), now(), cid))
        audit(db, pid, 'SOURCE_INSPECTED', {'candidate_id': cid, 'state': state, 'error': err, 'error_code': fetch.get('error_code'),
                                            'final_url': fetch.get('final_url'), 'truncated': fetch.get('truncated')})
        return _cand(qone(db, 'SELECT * FROM research_candidates WHERE id=?', (cid,)))


@app.post('/api/projects/{pid}/research/inspect')
async def research_inspect(pid: str, req: InspectReq, project=Depends(authorize)):
    """Verifier entry point for a founder-chosen public page (competitor site, regulator page, report)."""
    not_stopped(project)
    reject_obvious_secrets(req.url)
    if not req.url.startswith('https://'):
        raise HTTPException(422, 'Only https:// links can be inspected.')
    cid = uuid.uuid4().hex
    with conn() as db:
        db.execute('INSERT INTO research_candidates(id,project_id,run_id,bucket,provider,url,doi,title,publisher,year,state,payload_json,fetch_json,evidence_id,reject_reason,created_at,updated_at) VALUES(?,?,NULL,?,?,?,NULL,?,NULL,NULL,?,?,NULL,NULL,NULL,?,?)',
                   (cid, pid, req.bucket, 'founder_url', req.url, req.url[:200], 'CANDIDATE_METADATA', jsonstr({'query': req.query}), now(), now()))
    return await _fetch_into(pid, cid, req.url, req.query)


@app.post('/api/projects/{pid}/research/candidates/{cid}/fetch')
async def candidate_fetch(pid: str, cid: str, project=Depends(authorize)):
    not_stopped(project)
    with conn() as db:
        c = _cand(qone(db, 'SELECT * FROM research_candidates WHERE id=? AND project_id=?', (cid, pid)))
    if not c:
        raise HTTPException(404, 'Candidate not found in this project')
    if not c['url']:
        raise HTTPException(422, 'This candidate has no fetchable link (metadata only).')
    q = c['payload'].get('query') or c['title'] or ''
    return await _fetch_into(pid, cid, c['url'], q)


class RejectReq(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@app.post('/api/projects/{pid}/research/candidates/{cid}/reject')
async def candidate_reject(pid: str, cid: str, req: RejectReq, project=Depends(authorize)):
    not_stopped(project)
    with conn() as db:
        c = qone(db, 'SELECT id, state FROM research_candidates WHERE id=? AND project_id=?', (cid, pid))
        if not c:
            raise HTTPException(404, 'Candidate not found in this project')
        if c['state'] == 'EVIDENCE_ADDED':
            raise HTTPException(409, 'Already in the ledger; evidence is immutable. Add a contradicting record instead.')
        db.execute('UPDATE research_candidates SET state=?, reject_reason=?, updated_at=? WHERE id=?', ('REJECTED', req.reason, now(), cid))
        audit(db, pid, 'SOURCE_REJECTED', {'candidate_id': cid, 'reason': req.reason})
    return {'id': cid, 'state': 'REJECTED'}


class AddFromCandidate(BaseModel):
    excerpt: str | None = Field(default=None, max_length=1200)
    use: str = Field(default='PASSAGE', pattern='^(PASSAGE|ABSTRACT_METADATA|STRUCTURED_DATUM|FOUNDER_PASTE)$')
    subcriterion_id: str | None = Field(default=None, max_length=60, pattern='^[a-z_]{3,60}$')
    source_type: str | None = Field(default=None, max_length=40, pattern='^[A-Z_]{3,40}$')
    organization: str | None = Field(default=None, max_length=200)
    relevance_checks: dict | None = None
    paste_confirm: bool = False
    claim: str = Field(min_length=8, max_length=800)
    dimension: str = Field(pattern='^(desirability|demand|competition|feasibility|viability)$')
    direction: str = Field(default='UNSURE', pattern='^(SUPPORTS|CONTRADICTS|UNSURE)$')
    relevance: str = Field(default='UNSURE', pattern='^(CLAIM_RELEVANT|IRRELEVANT|UNSURE)$')
    criterion_id: str | None = Field(default=None, pattern='^(D0[3-7]|V0[1-3])$')
    direction_id: str | None = Field(default=None, pattern='^[A-C]$')
    geography: str | None = Field(default=None, max_length=120)
    published_on: str | None = Field(default=None, max_length=40)
    publisher: str | None = Field(default=None, max_length=200)


@app.post('/api/projects/{pid}/research/candidates/{cid}/add')
async def candidate_add(pid: str, cid: str, req: AddFromCandidate, project=Depends(authorize)):
    """Founder review action: move ONE verified passage (or labelled metadata/datum) into the claim ledger."""
    not_stopped(project)
    reject_obvious_secrets(jsonstr(req.model_dump()))
    with conn() as db:
        _guard_validate_open(db, pid)
        raw = qone(db, 'SELECT * FROM research_candidates WHERE id=? AND project_id=?', (cid, pid))
        if not raw:
            raise HTTPException(404, 'Candidate not found in this project')
        if raw['state'] in ('REJECTED', 'EVIDENCE_ADDED'):
            raise HTTPException(409, f'Candidate is {raw["state"]}.')
        payload = json.loads(raw['payload_json'])
        fetch = json.loads(raw['fetch_json']) if raw['fetch_json'] else None
        meta = (fetch or {}).get('meta') or {}
        _check_link(req.subcriterion_id, req.source_type)
        founder_supplied = False
        if req.use == 'FOUNDER_PASTE':
            if not raw['url'] and not payload.get('url'):
                raise HTTPException(422, 'A pasted excerpt needs the source URL it came from.')
            if not req.paste_confirm or not req.excerpt or len(req.excerpt.strip()) < 12:
                raise HTTPException(422, 'Paste the exact passage (12+ characters) and confirm you copied it from this URL yourself.')
            if fetch and fetch.get('text') and research.excerpt_in(fetch['text'], req.excerpt):
                url_status, ex_status, excerpt = 'URL_ACCESSIBLE', 'EXCERPT_MATCHED', req.excerpt.strip()
                note = 'Pasted passage was found in the fetched page text, so it is verified.'
            else:
                founder_supplied = True
                url_status, ex_status, excerpt = 'FOUNDER_SUPPLIED', 'FOUNDER_SUPPLIED_UNVERIFIED', req.excerpt.strip()
                note = 'FOUNDER-SUPPLIED excerpt: FounderOS could not fetch or match it at the URL, so it was never automatically verified.'
        elif req.use == 'PASSAGE':
            if raw['state'] != 'FETCHED' or not fetch or not fetch.get('text'):
                raise HTTPException(409, 'Inspect (fetch) the source first; only passages from the fetched page can be verified.')
            if not req.excerpt or not research.excerpt_in(fetch['text'], req.excerpt):
                raise HTTPException(422, 'That excerpt is not in the fetched page text. Pick a passage from the page; FounderOS never stores invented quotes.')
            url_status, ex_status, excerpt = 'URL_ACCESSIBLE', 'EXCERPT_MATCHED', req.excerpt.strip()
            note = 'Exact passage found in the fetched page. Proves the words appear there, not that they are true.'
            if fetch.get('paywall_suspected'):
                note += ' Page looked like a paywall or very short page: read the full source yourself.'
        elif req.use == 'ABSTRACT_METADATA':
            excerpt = payload.get('abstract')
            if not excerpt:
                raise HTTPException(422, 'No abstract in the provider metadata.')
            url_status, ex_status = 'NOT_CHECKED', 'METADATA_ONLY'
            note = 'METADATA_ONLY: provider abstract, not an inspected page. Kept as context; it does not count toward any score.'
        else:
            if raw['provider'] != 'worldbank' or not payload.get('datum'):
                raise HTTPException(422, 'Structured datum is only available for World Bank results.')
            excerpt, url_status, ex_status = payload['datum'], 'URL_ACCESSIBLE', 'STRUCTURED_DATUM'
            note = 'Structured datum returned by the World Bank API. ' + payload.get('limitation', '')
        injection = safety.looks_like_injection(excerpt + ' ' + req.claim)
        if fetch and fetch.get('truncated') and req.use == 'PASSAGE':
            note += ' ' + (fetch.get('truncation_note') or '')
        url_for_review = (fetch or {}).get('final_url') or raw['url'] or payload.get('url')
        state, reason, rflags = review.decide(req.relevance_checks, claim=req.claim, excerpt=excerpt, url=url_for_review,
                                              verified=ex_status in ('EXCERPT_MATCHED', 'STRUCTURED_DATUM'), founder_supplied=founder_supplied,
                                              metadata_only=ex_status == 'METADATA_ONLY')
        stype = req.source_type or ('ACADEMIC_METADATA' if ex_status == 'METADATA_ONLY' else 'OFFICIAL_STATISTIC' if ex_status == 'STRUCTURED_DATUM'
                                    else 'ACADEMIC_PASSAGE' if raw['provider'] in ('crossref', 'openalex') else None)
        if raw['provider'] in ('crossref', 'openalex') and ex_status == 'METADATA_ONLY':
            stype = 'ACADEMIC_METADATA'
        limits = LIMITS['SECONDARY_BACKGROUND'] + ' ' + note + (' ' + ' '.join(rflags) if rflags else '')
        if injection:
            limits = 'EXCLUDED: instruction-like text detected (possible prompt injection). ' + limits
        url = (fetch or {}).get('final_url') or raw['url'] or payload.get('url')
        dedupe = stable_hash([raw['doi'] or urlparse(url or '').hostname, urlparse(url or '').path.rstrip('/'), norm(excerpt)])
        eid, dup = insert_evidence(db, pid, kind='SECONDARY_BACKGROUND', dimension=req.dimension, claim=req.claim, direction=req.direction,
                                   relevance=review.legacy_relevance(state, req.relevance), independence='INDEPENDENT_SOURCE_FOUNDER_SELECTED', url_status=url_status,
                                   excerpt_status=ex_status, limitations=limits, dedupe_key=dedupe, url=raw['url'] or payload.get('url'),
                                   title=raw['title'] or meta.get('title'), publisher=req.publisher or raw['publisher'] or meta.get('publisher'),
                                   author=meta.get('author'), published_on=req.published_on or meta.get('published_on') or (str(raw['year']) if raw['year'] else None),
                                   retrieved_at=(fetch or {}).get('retrieved_at') or (now() if req.use == 'STRUCTURED_DATUM' else None), excerpt=excerpt,
                                   geography=req.geography or payload.get('geography'), injection=injection, criterion_id=req.criterion_id,
                                   direction_id=req.direction_id, source_hash=(fetch or {}).get('sha256'), candidate_id=cid, doi=raw['doi'],
                                   provider=raw['provider'], final_url=(fetch or {}).get('final_url'), subcriterion_id=req.subcriterion_id,
                                   source_type=stype, review_state=state, review_reason=reason, relevance_checks=req.relevance_checks,
                                   organization=req.organization, meta={'truncated': bool((fetch or {}).get('truncated')), 'use': req.use})
        db.execute('UPDATE research_candidates SET state=?, evidence_id=?, updated_at=? WHERE id=?', ('EVIDENCE_ADDED', eid, now(), cid))
    return {'evidence_id': eid, 'excerpt_status': ex_status, 'duplicate_of': dup['id'] if dup else None, 'injection_flag': injection,
            'limitations': limits, 'review_state': state, 'review_reason': reason, 'review_flags': rflags, 'source_type': stype}


# Legacy v0.4 endpoints kept for compatibility (bibliographic discovery only).
@app.get('/api/projects/{pid}/research-plan')
async def research_plan_legacy(pid: str, project=Depends(authorize)):
    with conn() as db:
        brief = latest_brief(db, pid)
    p = brief['payload'] if brief else {}

    def compact(s):
        return re.sub(r'[^\w\s-]', ' ', s)[:70].strip()
    segment = (p.get('target_customers') or 'target customers').strip()
    market = (p.get('target_market') or 'target market').strip()
    problem = (p.get('problem') or 'customer problem').strip()
    topic = (p.get('idea_summary') or 'proposed digital product').strip()
    queries = [{'id': 'problem', 'title': 'Customer problem', 'query': compact(f'{compact(segment)} {compact(problem)}'),
                'purpose': 'Find context about the problem. No source proves demand for this product.'},
               {'id': 'geography', 'title': 'Local market', 'query': compact(f'{compact(segment)} {compact(market)} statistics'),
                'purpose': 'Search for geography-specific statistics, then check population and date.'},
               {'id': 'alternatives', 'title': 'Existing solutions', 'query': compact(f'{compact(topic)} alternatives competitor'),
                'purpose': 'Academic indexes rarely cover commercial competitors; inspect actual product sites separately.'}]
    return {'classification': 'SUGGESTED_QUERIES_NOT_RESEARCH', 'brief_version': brief['version'] if brief else None, 'queries': queries,
            'notice': 'Queries are generated locally. No results become evidence automatically.'}


@app.get('/api/research/crossref')
async def research_crossref(q: str = Query(min_length=4, max_length=160)):
    if not re.search(r'[A-Za-z؀-ۿ]{3,}', q):
        raise HTTPException(422, detail='Use a descriptive research question')
    stop_words = {'the', 'and', 'for', 'with', 'among', 'about', 'from', 'study', 'research', 'of', 'on', 'in', 'to', 'a', 'an', 'at', 'or'}
    query_terms = set(re.findall(r'[a-z]{3,}', q.lower())) - stop_words

    def title_match(title, year):
        terms = set(re.findall(r'[a-z]{3,}', title.lower())) - stop_words
        matches = query_terms & terms
        score = len(matches)
        if 'university' in query_terms and re.search(r'\bpre[ -]?university\b|\bhigh school\b', title, re.I):
            score -= 3
        if year and year < 2016:
            score -= 1
        return max(score, 0), sorted(matches)
    try:
        async with httpx.AsyncClient(timeout=7, follow_redirects=False, trust_env=False) as client:
            async with client.stream('GET', 'https://api.crossref.org/works', params={'query': q, 'rows': 12, 'select': 'DOI,title,publisher,published,type'},
                                     headers={'User-Agent': research.UA, 'Accept': 'application/json'}) as response:
                if response.status_code != 200:
                    raise HTTPException(503, detail='Crossref index temporarily unavailable; manual evidence entry remains available.')
                if 'application/json' not in response.headers.get('content-type', ''):
                    raise HTTPException(503, detail='Crossref returned an unexpected content type')
                blocks, length = [], 0
                async for chunk in response.aiter_bytes():
                    length += len(chunk)
                    if length > 300_000:
                        raise HTTPException(503, detail='Research response exceeded safe limit')
                    blocks.append(chunk)
        items = json.loads(b''.join(blocks)).get('message', {}).get('items', [])
        results = []
        for item in items[:12]:
            doi = item.get('DOI', '')
            if not isinstance(doi, str) or not re.fullmatch(r'10\.\d{4,9}/[^\s<>]{1,180}', doi, re.I):
                continue
            title = item.get('title') or []
            published = item.get('published', {}).get('date-parts', [])
            year = published[0][0] if published and published[0] else None
            readable = str(title[0])[:350] if isinstance(title, list) and title else 'Untitled publication'
            score, matched = title_match(readable, year)
            results.append({'id': doi, 'title': readable, 'publisher': str(item.get('publisher', ''))[:150], 'year': year,
                            'type': str(item.get('type', ''))[:80], 'url': 'https://doi.org/' + doi, 'title_match_score': score,
                            'matched_query_terms': matched, 'topic_match': 'POSSIBLE' if score >= 2 else 'WEAK'})
        results.sort(key=lambda x: (-x['title_match_score'], -(x['year'] or 0)))
        return {'provider': 'Crossref', 'classification': 'UNVERIFIED_CANDIDATES_NOT_EVIDENCE',
                'limitations': 'Sorted by query-term title overlap only. Metadata is not proof.', 'results': results[:6]}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, detail='Research provider unavailable; use manual evidence entry. No sources invented.') from exc


# ----------------------------------------------------------------------------- experiments (pre-registration)
@app.get('/api/projects/{pid}/experiments/suggest')
async def suggest(pid: str, project=Depends(authorize)):
    with conn() as db:
        brief = latest_brief(db, pid)
        if not brief:
            raise HTTPException(409, 'Refine the brief first')
        disc = latest_run(db, pid, 'discover')
        experiments = experiments_of(db, pid)
        live = {x['id']: x for x in experiments if x['status'] == 'LOCKED'}
        counted = [e for e in evidence_of(db, pid) if exclusion_reason(e, live) is None]
        reg = risk_register(brief['payload'], disc and disc['report'], disc and disc['version'], counted)
        gate = latest_run(db, pid, 'validate')
        ss = safety_for(db, pid, brief['version'])
        if ss and ss['status'] == 'BLOCK':
            s = {'kind': 'NO_EXPERIMENT_SAFETY_BLOCK',
                 'instruction': 'This venture is blocked by safety policy. Revise the prohibited brief before testing.'}
        elif (gate and gate['brief_version'] == brief['version'] and gate['state'] != 'INVALIDATED'
              and gate['gate'].get('verdict') in ('STOP_DO_NOT_LAUNCH', 'PIVOT', 'BLOCK_DO_NOT_LAUNCH')):
            s = {'kind': 'REVIEW_CRITICAL_RESULT_BEFORE_MORE_TESTS',
                 'instruction': 'Review the current critical-failure verdict and the founder decision before drafting another test.'}
        else:
            s = suggest_experiment(brief['payload'], disc and disc['report'], reg, experiments)
    if s.get('kind') == 'PROPOSED_EXPERIMENT_NEEDS_FOUNDER_APPROVAL':
        s['suggested_criteria']['threshold_origin'] = 'TEAM_ASSUMPTION'
        s['suggested_criteria'].setdefault('time_window_days', 7)
        s['suggested_criteria']['near_miss_band'] = criteria.default_config()['results']['near_miss_band']
        s.setdefault('risk_ranking_note', 'Targets an evidence gap rather than assuming demand.')
    return s


def _exp_rows(db, pid, series_id):
    rows = [unpack_experiment(x) for x in qall(db, 'SELECT * FROM experiments WHERE project_id=? AND series_id=? ORDER BY version', (pid, series_id))]
    if not rows:
        raise HTTPException(404, 'Experiment not found in this project')
    return rows


def _prep_payload(req: ExperimentDraft, db, pid):
    payload = req.model_dump()
    cfg, _ = config_of(db, pid)
    payload.setdefault('near_miss_band', cfg['results']['near_miss_band'])
    if payload.get('near_miss_band') is None:
        payload['near_miss_band'] = cfg['results']['near_miss_band']
    return payload


@app.post('/api/projects/{pid}/experiments', status_code=201)
async def create_experiment(pid: str, req: ExperimentDraft, project=Depends(authorize)):
    reject_obvious_secrets(jsonstr(req.model_dump()))
    not_stopped(project)
    text = ' '.join([req.hypothesis, req.metric, req.consent_method, req.founder_actions, req.pivot_alternative or ''])
    blocks = safety.find_blocks(text)
    if blocks or safety.looks_like_injection(text):
        raise HTTPException(422, {'message': 'Experiment design breaks a never-rule (fake sign-ups, outreach by the AI, payments, ...).',
                                  'findings': blocks})
    sid = uuid.uuid4().hex
    with conn() as db:
        brief = latest_brief(db, pid)
        payload = _prep_payload(req, db, pid)
        db.execute('INSERT INTO experiments(series_id,version,project_id,status,payload_json,criteria_hash,locked_at,result_evidence_id,created_at) VALUES(?,?,?,?,?,?,NULL,NULL,?)',
                   (sid, 1, pid, 'DRAFT', jsonstr(payload), stable_hash(criteria_of(payload)), now()))
        audit(db, pid, 'EXPERIMENT_DRAFTED', {'experiment_id': sid, 'version': 1})
    check = criteria.experiment_design_check(payload, (brief or {}).get('payload') or {})
    return {'experiment_id': sid, 'version': 1, 'status': 'DRAFT', 'criteria_hash': stable_hash(criteria_of(payload)), 'criteria': criteria_of(payload),
            'design_check': check, 'notice': 'DRAFT. Lock it (pre-register) BEFORE collecting data. A planned experiment is never evidence.'}


@app.post('/api/projects/{pid}/experiments/{sid}/lock')
async def lock_experiment(pid: str, sid: str, req: ExperimentLock, project=Depends(authorize)):
    not_stopped(project)
    with conn() as db:
        rows = _exp_rows(db, pid, sid)
        x = rows[-1]
        if x['version'] != req.version or x['status'] != 'DRAFT':
            raise HTTPException(409, f'Only the latest DRAFT can be locked (latest v{x["version"]} is {x["status"]}).')
        if not hmac.compare_digest(x['criteria_hash'], req.criteria_hash):
            raise HTTPException(409, 'criteria_hash mismatch: reload the draft before locking.')
        brief = latest_brief(db, pid)
        bp = (brief or {}).get('payload') or {}
        v05 = criteria.experiment_design_check(x['payload'], bp)
        if v05['status'] != 'PASS':
            failed = [f'{k}: {v["why"]}' for k, v in v05['items'].items() if not v['ok']]
            raise HTTPException(422, {'message': 'V05 experiment design check failed; fix the draft (edit = new version) before locking.', 'failed': failed})
        cfg, _ = config_of(db, pid)
        ev = criteria.annotate(evidence_of(db, pid), bp, cfg)
        quality = criteria.prepare(bp, ev, experiments_of(db, pid), cfg)
        v06 = criteria.target_setting_check(x['payload'], {e['id'] for e in ev if quality[e['id']]['counts']})
        if v06['status'] != 'PASS':
            raise HTTPException(422, {'message': 'V06 target setting incomplete.', 'failed': v06['problems']})
        locked_at = now()
        db.execute('UPDATE experiments SET status=?, locked_at=? WHERE series_id=? AND version=?', ('LOCKED', locked_at, sid, x['version']))
        audit(db, pid, 'EXPERIMENT_PREREGISTERED', {'experiment_id': sid, 'version': x['version'], 'criteria_hash': x['criteria_hash'],
                                                    'locked_at': locked_at, 'threshold_origin': x['payload'].get('threshold_origin'),
                                                    'criteria_version': criteria.VERSION})
    return {'experiment_id': sid, 'version': x['version'], 'status': 'LOCKED', 'locked_at': locked_at, 'criteria_hash': x['criteria_hash'],
            'notice': 'Criteria are frozen. Submitting results cannot change them; editing creates a new version and retires old results.'}


@app.post('/api/projects/{pid}/experiments/{sid}/revise', status_code=201)
async def revise_experiment(pid: str, sid: str, req: ExperimentDraft, project=Depends(authorize)):
    reject_obvious_secrets(jsonstr(req.model_dump()))
    not_stopped(project)
    text = ' '.join([req.hypothesis, req.metric, req.consent_method, req.founder_actions, req.pivot_alternative or ''])
    if safety.find_blocks(text) or safety.looks_like_injection(text):
        raise HTTPException(422, 'Experiment design breaks a never-rule.')
    with conn() as db:
        rows = _exp_rows(db, pid, sid)
        prev = rows[-1]
        payload = _prep_payload(req, db, pid)
        version = prev['version'] + 1
        db.execute('INSERT INTO experiments(series_id,version,project_id,status,payload_json,criteria_hash,locked_at,result_evidence_id,created_at) VALUES(?,?,?,?,?,?,NULL,NULL,?)',
                   (sid, version, pid, 'DRAFT', jsonstr(payload), stable_hash(criteria_of(payload)), now()))
        if prev['status'] in ('LOCKED', 'DRAFT'):
            db.execute('UPDATE experiments SET status=? WHERE series_id=? AND version=?', ('SUPERSEDED', sid, prev['version']))
        invalidate_runs(db, pid, f'experiment {sid[:8]} criteria changed to v{version}', phases=('validate',))
        audit(db, pid, 'EXPERIMENT_CRITERIA_CHANGED', {'experiment_id': sid, 'from_version': prev['version'], 'to_version': version,
                                                       'had_result': bool(prev['result_evidence_id']), 'old_hash': prev['criteria_hash'],
                                                       'new_hash': stable_hash(criteria_of(payload))})
    return {'experiment_id': sid, 'version': version, 'status': 'DRAFT', 'criteria_hash': stable_hash(criteria_of(payload)),
            'notice': f'Version {prev["version"]} and any result recorded against it no longer count. Lock v{version} before collecting new data.'}


@app.post('/api/projects/{pid}/experiments/{sid}/result')
async def submit_result(pid: str, sid: str, req: ExperimentResult, project=Depends(authorize)):
    reject_obvious_secrets(jsonstr(req.model_dump()))
    not_stopped(project)
    signals = ' '.join(filter(None, [req.method, req.positive_signals, req.negative_signals]))
    if safety.looks_like_injection(signals):
        raise HTTPException(422, 'Result text contains instruction-like content. Remove it.')
    with conn() as db:
        rows = _exp_rows(db, pid, sid)
        x = rows[-1]
        if x['version'] != req.version or x['status'] != 'LOCKED':
            raise HTTPException(409, f'Results are only accepted against the latest LOCKED version (latest v{x["version"]} is {x["status"]}). A planned experiment is not evidence.')
        if not hmac.compare_digest(x['criteria_hash'], req.criteria_hash):
            raise HTTPException(409, 'criteria_hash mismatch: results must reference the exact locked criteria')
        if x['result_evidence_id']:
            raise HTTPException(409, 'A result already exists for this version. Create a new version for a repeat run.')
        if req.collected_from < date.fromisoformat(x['locked_at'][:10]):
            raise HTTPException(422, f'Results collected before the pre-registration date ({x["locked_at"][:10]}) are not accepted as pre-registered.')
        crit = criteria_of(x['payload'])
        outcome = evaluate_result(crit, req.sample_size, req.positives)
        simulated = bool(x['payload'].get('simulated'))
        kind = 'SIMULATED_RESULT' if simulated else 'PRE_REGISTERED_EXPERIMENT_RESULT'
        if simulated:
            outcome['caveats'] = ['SIMULATED / NOT COUNTED: this was a labelled demo, not real customer behaviour. It never counts toward any verdict.'] + outcome['caveats']
        meta = {'recruitment_method': req.recruitment_method, 'exclusions': req.exclusions, 'limitations': req.limitations,
                'denominator': req.sample_size, 'numerator': req.positives, 'consent_confirmed': req.consent_confirmed,
                'collected_from': str(req.collected_from), 'collected_to': str(req.collected_to),
                'locked_success_pct': crit['success_threshold_pct'], 'locked_adverse_pct': crit['adverse_threshold_pct'],
                'threshold_origin': crit.get('threshold_origin'), 'simulated': simulated}
        eid = uuid.uuid4().hex
        db.execute('''INSERT INTO evidence(id,project_id,kind,dimension,claim_id,claim,direction,source_url,title,publisher,author,published_on,retrieved_at,excerpt,
                      url_status,excerpt_status,relevance,independence,method,sample_size,positives,segment,geography,collected_from,collected_to,consent_confirmed,
                      experiment_id,experiment_version,outcome,rate_pct,adverse,positive_signals,negative_signals,dedupe_key,duplicate_of,injection_flag,limitations,created_at,direction_id,
                      meta_json,source_type,review_state)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                   (eid, pid, kind, crit['dimension'] or 'demand', crit['claim_id'], crit['hypothesis'],
                    {'PASS': 'SUPPORTS', 'FAIL': 'CONTRADICTS'}.get(outcome['outcome'], 'UNSURE'), None, None, None, None, None, None, None,
                    'NOT_APPLICABLE', 'NOT_APPLICABLE', 'CLAIM_RELEVANT', 'FOUNDER_REPORTED_NOT_INDEPENDENTLY_VERIFIED', req.method, req.sample_size,
                    req.positives, crit['target_segment'], None, str(req.collected_from), str(req.collected_to), int(req.consent_confirmed),
                    sid, x['version'], outcome['outcome'], outcome['rate_pct'], int(outcome['adverse']), req.positive_signals, req.negative_signals,
                    stable_hash([sid, x['version']]), None, 0, ' '.join(outcome['caveats']) + ' ' + outcome['explanation'], now(), crit.get('direction_id'),
                    jsonstr(meta), 'SIMULATED_RESULT' if simulated else 'FOUNDER_CUSTOMER_RESEARCH', 'EXCLUDED' if simulated else None))
        db.execute('UPDATE experiments SET result_evidence_id=? WHERE series_id=? AND version=?', (eid, sid, x['version']))
        invalidate_runs(db, pid, 'experiment result recorded', phases=('validate',))
        audit(db, pid, 'EXPERIMENT_RESULT_RECORDED', {'experiment_id': sid, 'version': x['version'], 'evidence_id': eid, 'outcome': outcome['outcome'], 'simulated': simulated,
                                                      'reading': criteria.READING.get(outcome['outcome']), 'n': req.sample_size,
                                                      'positives': req.positives, 'criteria_hash': x['criteria_hash']})
    return {'evidence_id': eid, 'experiment_id': sid, 'version': x['version'], 'locked_criteria': crit, 'locked_at': x['locked_at'],
            'reading': 'SIMULATED_NOT_COUNTED' if simulated else criteria.READING.get(outcome['outcome']), **outcome, 'simulated': simulated, 'result_meta': meta,
            'notice': 'Founder-reported. Compared in code against the criteria locked BEFORE collection. One result does not validate the business.'}


# ----------------------------------------------------------------------------- hard-denied outbound actions
@app.post('/api/projects/{pid}/external-action', status_code=403)
async def external_action_denied(pid: str, req: PublicActionRequest, project=Depends(authorize)):
    reject_obvious_secrets(req.description)
    with conn() as db:
        audit(db, pid, 'EXTERNAL_ACTION_BLOCKED', {'kind': req.kind, 'description': req.description[:200]})
    raise HTTPException(403, 'Draft-only prototype: publishing, sending, spending, signing, paying, refunding, transferring and contacting are NOT implemented '
                             'and are hard-denied. Phase approval never grants external-action permission (X04).')


# ----------------------------------------------------------------------------- static SPA
HERE = Path(__file__).resolve().parent
STATIC = HERE / 'static'
if STATIC.exists():
    app.mount('/assets', StaticFiles(directory=STATIC), name='assets')


@app.get('/')
async def home():
    return FileResponse(STATIC / 'index.html')


@app.get('/projects')
@app.get('/projects/{rest:path}')
@app.get('/roadmap')
@app.get('/help')
async def spa(rest: str = ''):
    """Deep links (/projects/:id/brief, ...) serve the same app shell; data access still needs the project token."""
    return FileResponse(STATIC / 'index.html')


# ----------------------------------------------------------------------------- phases 3-6, approvals, agent log
from .orchestrator import router as _workflow_router  # noqa: E402  (imported last: it uses helpers defined above)
app.include_router(_workflow_router)

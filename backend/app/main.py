"""FounderOS API. Phase transitions, safety and verdicts are backend-enforced; no LLM can approve a gate."""
from __future__ import annotations
import hashlib
import hmac
import json
import re
import secrets
import socket
import ipaddress
import uuid
import platform
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db, conn, now, qone, qall, audit, unpack_run, unpack_brief, unpack_experiment
from .schemas import (ProjectCreate, RefinedBrief, DiscoveryReport, ValidationReport, ClarifyRequest, SafetyAck,
                      DecisionRequest, EvidenceAdd, ExperimentDraft, ExperimentLock, ExperimentResult,
                      PublicActionRequest, BRIEF_FIELDS)
from .gates import discovery_gate, evaluate_validation, PHASES, ACTIVE_PHASES
from .decision import stable_hash, norm, criteria_of, evaluate_result, skeptic_review, suggest_experiment, risk_register
from . import safety, criteria
from .llm import OllamaClient, ModelUnavailable, ModelOutputError, REFINE_SYSTEM, DISCOVER_SYSTEM, VALIDATE_SYSTEM

LLM = OllamaClient()
STARTED_AT = now()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title='FounderOS', version='0.4.0', lifespan=lifespan,
              description='Evidence-first founder decision system. Draft-only: no publishing, sending, spending, signing or payments.')


def jsonstr(x):
    return json.dumps(x, ensure_ascii=False, default=str)


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


def missing_fields(brief):
    if brief is None:
        return ['refined brief']
    p = brief['payload']
    return [name for name in ('problem', 'target_customers', 'target_market') if not p.get(name)]


def invalidate_runs(db, pid, reason, phases=ACTIVE_PHASES):
    """Any change of inputs retires dependent approvals (state only; artifacts stay immutable)."""
    for phase in phases:
        for run in qall(db, 'SELECT id,state FROM phase_runs WHERE project_id=? AND phase=? AND state IN ("PENDING_APPROVAL","APPROVED")', (pid, phase)):
            db.execute('UPDATE phase_runs SET state=?, invalidated_reason=? WHERE id=?', ('INVALIDATED', reason, run['id']))
            audit(db, pid, 'APPROVAL_INVALIDATED', {'phase': phase, 'run_id': run['id'], 'previous_state': run['state'], 'reason': reason})


def store_safety(db, pid, brief_version, text, fields):
    assessment = safety.screen(text, fields)
    db.execute('INSERT OR REPLACE INTO safety_assessments(project_id,brief_version,payload_json,status,acknowledged_at,ack_statement,created_at) VALUES(?,?,?,?,NULL,NULL,?)',
               (pid, brief_version, jsonstr(assessment), assessment['status'], now()))
    audit(db, pid, 'SAFETY_SCREENED', {'brief_version': brief_version, 'status': assessment['status'],
                                       'rules': [f['rule_id'] for f in assessment['findings']], 'policy': assessment['policy_version']})
    return assessment


def brief_text(project, payload):
    parts = [project['original_idea']] + [str(payload.get(k) or '') for k in BRIEF_FIELDS]
    parts += list((payload.get('founder_answers') or {}).values())
    return '\n'.join(parts)


def public_project(pid):
    with conn() as db:
        project = qone(db, 'SELECT id,original_idea,intake_json,created_at,stopped FROM projects WHERE id=?', (pid,))
        project['intake'] = json.loads(project.pop('intake_json'))
        brief = latest_brief(db, pid)
        safety_row = safety_for(db, pid, brief['version']) if brief else None
        runs = [unpack_run(x) for x in qall(db, 'SELECT * FROM phase_runs WHERE project_id=? ORDER BY created_at DESC', (pid,))]
        evidence = evidence_of(db, pid)
        experiments = experiments_of(db, pid)
        decisions = qall(db, 'SELECT * FROM decisions WHERE project_id=? ORDER BY created_at DESC', (pid,))
        history = qall(db, 'SELECT * FROM audit WHERE project_id=? ORDER BY id DESC LIMIT 120', (pid,))
    for h in history:
        h['details'] = json.loads(h.pop('details_json'))
    for d in decisions:
        d['experiment_versions'] = json.loads(d.pop('experiment_versions_json'))
    disc = next((r for r in runs if r['phase'] == 'discover'), None)
    val = next((r for r in runs if r['phase'] == 'validate'), None)
    passport = None
    if val:
        passport = {'verdict': val['gate'], 'report': val['report'], 'run_id': val['id'], 'version': val['version'],
                    'report_hash': val['report_hash'], 'state': val['state'], 'created_at': val['created_at'],
                    'brief_version': val['brief_version'], 'safety_status': val['safety_status'],
                    'founder_decision': next((d for d in decisions if d['phase_run_id'] == val['id']), None),
                    'invalidated_reason': val.get('invalidated_reason')}
    return {'project': project, 'brief': brief, 'safety': safety_row, 'phase_runs': runs, 'evidence': evidence,
            'experiments': experiments, 'decisions': decisions, 'audit': history, 'passport': passport,
            'phases': [{'id': p, 'status': 'LIVE' if p in ACTIVE_PHASES else 'ARCHITECTURE_ONLY'} for p in PHASES],
            'current': {'discover': disc and disc['state'], 'validate': val and val['state'], 'stopped': bool(project['stopped']),
                        'safety': safety_row and safety_row['status']}}


# ----------------------------------------------------------------------------- health
@app.get('/api/health')
async def health():
    status = await LLM.status()
    return {'status': 'ok', 'mode': 'LIVE_LOCAL_OLLAMA_REQUIRED', 'model': LLM.model, 'ollama': status,
            'started_at': STARTED_AT, 'host': platform.platform(), 'cpu_count': __import__('os').cpu_count(),
            'warning': 'No simulated AI responses, ever. Market claims without sources are assumptions.'}


@app.post('/api/warmup')
async def warmup():
    """Loads the model into RAM before a timed demo. Takes the first-load cost, returns observed ms."""
    started = time.monotonic()
    try:
        await LLM.warmup()
    except httpx.HTTPError as exc:
        raise HTTPException(503, f'Model warmup failed: {str(exc)[:160]}') from exc
    return {'warmed': True, 'model': LLM.model, 'observed_ms': int((time.monotonic() - started) * 1000)}


# Criteria are deliberately read-only here: changing them must use a future
# reviewed, versioned policy workflow, never a model-generated threshold.
@app.get('/api/criteria')
async def criteria_catalog():
    return {'version': criteria.VERSION, 'discover': criteria.DISCOVER,
            'validate': criteria.VALIDATE, 'cross_cutting': criteria.CROSS,
            'architecture_only': criteria.ARCHITECTURE}


@app.get('/api/projects/{pid}/criteria')
async def project_criteria(pid: str, project=Depends(authorize)):
    with conn() as db:
        brief = latest_brief(db, pid)
        safety_row = safety_for(db, pid, brief['version']) if brief else None
        result = criteria.summarize(evidence_of(db,pid),
                                   safety_row['status'] if safety_row else None,
                                   experiments_of(db,pid), brief)
    return result


@app.get('/api/projects/{pid}/research-plan')
async def research_plan(pid: str, project=Depends(authorize)):
    """Local, deterministic, privacy-preserving research suggestions; no claims made."""
    with conn() as db:
        brief = latest_brief(db,pid)
    p = brief['payload'] if brief else {}
    segment = (p.get('target_customers') or 'target customers').strip()
    market = (p.get('target_market') or 'target market').strip()
    problem = (p.get('problem') or 'customer problem').strip()
    topic = (p.get('idea_summary') or 'proposed digital product').strip()
    # Bound search length, and never send a private founder brief automatically.
    def compact(s): return re.sub(r'[^\w\s-]',' ',s)[:70].strip()
    queries = [
        {'id':'problem', 'title':'Customer problem', 'query':compact(f'{compact(segment)} {compact(problem)}'),
         'purpose':'Find context about the problem. No source proves demand for this product.'},
        {'id':'geography', 'title':'Local market', 'query':compact(f'{compact(segment)} {compact(market)} statistics'),
         'purpose':'Search for geography-specific statistics, then check population and date.'},
        {'id':'alternatives', 'title':'Existing solutions', 'query':compact(f'{compact(topic)} alternatives competitor'),
         'purpose':'Academic indexes rarely cover commercial competitors; inspect actual product sites separately.'},
    ]
    return {'classification':'SUGGESTED_QUERIES_NOT_RESEARCH', 'brief_version': brief['version'] if brief else None,
            'queries': queries, 'notice':'Queries are generated locally; clicking Search explicitly sends that query to Crossref. No results become evidence automatically.'}


# ----------------------------------------------------------------------------- projects & brief
@app.get('/api/research/crossref')
async def research_crossref(q: str = Query(min_length=4, max_length=160)):
    """Bibliographic discovery only. Never enters ledger or changes verdicts.

    Calls a fixed public endpoint, never a founder-provided URL, with strict
    response size, timeout and redirect controls. No paid account required.
    """
    if not re.search(r'[A-Za-z\u0600-\u06ff]{3,}', q):
        raise HTTPException(422, detail='Use a descriptive research question')
    # Relevance here means lexical title matching only; it is NOT evidence quality.
    stop_words = {'the','and','for','with','among','about','from','study','research','of','on','in','to','a','an','at','or'}
    query_terms = set(re.findall(r'[a-z]{3,}', q.lower())) - stop_words
    def title_match(title: str, year: int | None):
        terms = set(re.findall(r'[a-z]{3,}', title.lower())) - stop_words
        matches = query_terms & terms
        score = len(matches)
        # Reject misleading matches, e.g. 'pre-university' when looking for adults.
        if 'university' in query_terms and re.search(r'\bpre[ -]?university\b|\bhigh school\b', title, re.I):
            score -= 3
        if year and year < 2016: score -= 1
        return max(score, 0), sorted(matches)
    try:
        async with httpx.AsyncClient(timeout=7, follow_redirects=False, trust_env=False) as client:
            async with client.stream('GET', 'https://api.crossref.org/works', params={'query':q, 'rows':12, 'select':'DOI,title,publisher,published,type'},
                                     headers={'User-Agent':'FounderOS/0.3 (academic candidate discovery; local open-source demo)', 'Accept':'application/json'}) as response:
                if response.status_code != 200:
                    raise HTTPException(503, detail='Crossref index temporarily unavailable; manual evidence entry remains available.')
                if 'application/json' not in response.headers.get('content-type',''):
                    raise HTTPException(503, detail='Crossref returned an unexpected content type')
                blocks=[]; length=0
                async for chunk in response.aiter_bytes():
                    length+=len(chunk)
                    if length>300_000: raise HTTPException(503, detail='Research response exceeded safe limit')
                    blocks.append(chunk)
        items=json.loads(b''.join(blocks)).get('message',{}).get('items',[])
        results=[]
        for item in items[:12]:
            doi=item.get('DOI','')
            if not isinstance(doi,str) or not re.fullmatch(r'10\.\d{4,9}/[^\s<>]{1,180}',doi,re.I): continue
            title=item.get('title') or []
            published=item.get('published',{}).get('date-parts',[])
            year=published[0][0] if published and published[0] else None
            readable_title = str(title[0])[:350] if isinstance(title,list) and title else 'Untitled publication'
            relevance_score, matched_terms = title_match(readable_title, year)
            results.append({'id':doi,'title':readable_title,
                            'publisher':str(item.get('publisher',''))[:150],'year':year,'type':str(item.get('type',''))[:80],
                            'url':'https://doi.org/'+doi,
                            'title_match_score':relevance_score, 'matched_query_terms':matched_terms,
                            'topic_match':'POSSIBLE' if relevance_score >= 2 else 'WEAK'})
        results.sort(key=lambda x: (-x['title_match_score'], -(x['year'] or 0)))
        results = results[:6]
        return {'provider':'Crossref','classification':'UNVERIFIED_CANDIDATES_NOT_EVIDENCE',
                'limitations':'Results sorted by simple query-term title overlap (not content relevance or truth). Metadata is not proof. Read original publications and verify populations/geography/methods. No candidate is counted as evidence automatically.',
                'results':results}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, detail='Research provider unavailable; use manual evidence entry. No sources invented.') from exc


@app.post('/api/projects', status_code=201)
async def create_project(req: ProjectCreate):
    reject_obvious_secrets(jsonstr(req.model_dump()))
    pid = uuid.uuid4().hex
    token = secrets.token_urlsafe(32)
    with conn() as db:
        db.execute('INSERT INTO projects(id, token_hash, original_idea, intake_json, created_at) VALUES(?,?,?,?,?)',
                   (pid, hashlib.sha256(token.encode()).hexdigest(), req.idea, jsonstr(req.model_dump()), now()))
        audit(db, pid, 'PROJECT_CREATED', {'input_length': len(req.idea)})
        # Pre-screen the raw text immediately so prohibited ideas are visibly blocked before any model call.
        pre = safety.find_blocks('\n'.join([req.idea] + [str(v or '') for v in req.model_dump().values() if v]))
        if pre:
            audit(db, pid, 'SAFETY_PRESCREEN_BLOCK', {'rules': [f['rule_id'] for f in pre]})
    return {'project_id': pid, 'access_token': token, 'prescreen': {'status': 'BLOCK' if pre else 'NOT_YET_SCREENED', 'findings': pre},
            'notice': 'Save this project token locally. It is shown once and never recoverable; never publish it.'}


@app.get('/api/projects/{pid}')
async def get_project(pid: str, project=Depends(authorize)):
    return public_project(pid)


@app.post('/api/projects/{pid}/refine')
async def refine(pid: str, project=Depends(authorize)):
    if project['stopped']:
        raise HTTPException(409, 'This project has been stopped')
    intake = json.loads(project['intake_json'])
    with conn() as db:
        current = latest_brief(db, pid)
    answers = current['payload'].get('founder_answers', {}) if current else {}
    full_text = '\n'.join([project['original_idea']] + [str(v or '') for v in intake.values()] + list(answers.values()))
    pre = safety.find_blocks(full_text)
    if pre:
        # Save a BLOCK assessment without calling the model: prohibited briefs never get an AI pass.
        with conn() as db:
            version = (current['version'] + 1) if current else 1
            payload = {'idea_summary': project['original_idea'][:300], 'provenance': {}, 'assumptions': [], 'questions': [],
                       'founder_answers': answers, 'original_idea_text': project['original_idea'], 'model': 'NOT_CALLED_SAFETY_BLOCK'}
            for k in BRIEF_FIELDS:
                payload[k] = intake.get(k) or answers.get(k)
                payload['provenance'][k] = 'EXPLICIT' if payload[k] else 'UNKNOWN'
            db.execute('INSERT INTO briefs(project_id,version,payload_json,created_at) VALUES(?,?,?,?)', (pid, version, jsonstr(payload), now()))
            invalidate_runs(db, pid, f'brief changed to v{version}')
            assessment = store_safety(db, pid, version, full_text, payload)
            audit(db, pid, 'BRIEF_REFINED', {'version': version, 'model': 'NOT_CALLED_SAFETY_BLOCK'})
        return {'version': version, 'brief': payload, 'safety': assessment, 'missing_fields': missing_fields({'payload': payload})}
    started = time.monotonic()
    try:
        result = await LLM.generate(REFINE_SYSTEM, {'founder_input': project['original_idea'], 'explicit_form_fields': intake,
                                                   'previous_clarifications': answers}, RefinedBrief, max_tokens=500)
    except (ModelUnavailable, ModelOutputError) as exc:
        raise HTTPException(503, str(exc)) from exc
    latency = int((time.monotonic() - started) * 1000)
    payload = result.model_dump()
    payload['questions'] = payload['questions'][:3]
    payload['provenance'] = {}
    for key in BRIEF_FIELDS:
        if intake.get(key):
            payload[key] = intake[key]  # a submitted form field is source-of-truth; the LLM never changes it
            payload['provenance'][key] = 'EXPLICIT'
        elif answers.get(key):
            payload[key] = answers[key]
            payload['provenance'][key] = 'EXPLICIT'
        elif payload.get(key):
            payload['provenance'][key] = 'INFERRED_UNCONFIRMED'
        else:
            payload[key] = None
            payload['provenance'][key] = 'UNKNOWN'
    payload['founder_answers'] = answers
    payload['original_idea_text'] = project['original_idea']
    payload['model'] = LLM.model
    payload['latency_ms'] = latency
    with conn() as db:
        current = latest_brief(db, pid)
        version = (current['version'] + 1) if current else 1
        db.execute('INSERT INTO briefs(project_id,version,payload_json,created_at) VALUES(?,?,?,?)', (pid, version, jsonstr(payload), now()))
        invalidate_runs(db, pid, f'brief changed to v{version}')
        assessment = store_safety(db, pid, version, brief_text(project, payload), payload)
        audit(db, pid, 'BRIEF_REFINED', {'version': version, 'unknowns': missing_fields({'payload': payload}), 'model': LLM.model, 'latency_ms': latency, 'criteria_catalog_version': criteria.VERSION})
    return {'version': version, 'brief': payload, 'safety': assessment, 'missing_fields': missing_fields({'payload': payload}), 'latency_ms': latency}


@app.post('/api/projects/{pid}/clarify')
async def clarify(pid: str, req: ClarifyRequest, project=Depends(authorize)):
    reject_obvious_secrets(jsonstr(req.model_dump()))
    if project['stopped']:
        raise HTTPException(409, 'This project has been stopped')
    with conn() as db:
        brief = latest_brief(db, pid)
        if brief is None:
            raise HTTPException(409, 'Refine the founder brief first')
        payload = dict(brief['payload'])
        payload['founder_answers'] = dict(payload.get('founder_answers', {}))
        payload['founder_answers'].update(req.answers)
        payload['provenance'] = dict(payload.get('provenance', {}))
        for k, v in req.answers.items():
            payload[k] = v.strip()
            payload['provenance'][k] = 'EXPLICIT'
        version = brief['version'] + 1
        db.execute('INSERT INTO briefs(project_id,version,payload_json,created_at) VALUES(?,?,?,?)', (pid, version, jsonstr(payload), now()))
        invalidate_runs(db, pid, f'brief corrected to v{version} (fields: {", ".join(req.answers)})')
        assessment = store_safety(db, pid, version, brief_text(project, payload), payload)
        audit(db, pid, 'BRIEF_CLARIFIED', {'fields': list(req.answers), 'version': version})
    return {'version': version, 'brief': payload, 'safety': assessment, 'missing_fields': missing_fields({'payload': payload})}


@app.post('/api/projects/{pid}/safety/acknowledge')
async def acknowledge_risk(pid: str, req: SafetyAck, project=Depends(authorize)):
    if project['stopped']:
        raise HTTPException(409, 'This project has been stopped')
    with conn() as db:
        brief = latest_brief(db, pid)
        if not brief or brief['version'] != req.brief_version:
            raise HTTPException(409, 'Acknowledgment must reference the latest brief version')
        row = safety_for(db, pid, req.brief_version)
        if not row:
            raise HTTPException(409, 'No safety assessment for this brief version')
        if row['status'] == 'BLOCK':
            raise HTTPException(403, 'This brief is BLOCKED by backend safety policy. Founder acknowledgment cannot override a block; revise the brief.')
        if row['status'] != 'REVIEW_REQUIRED':
            raise HTTPException(409, 'No acknowledgment needed for this status')
        db.execute('UPDATE safety_assessments SET acknowledged_at=?, ack_statement=? WHERE project_id=? AND brief_version=?',
                   (now(), req.statement, pid, req.brief_version))
        audit(db, pid, 'RISK_ACKNOWLEDGED', {'brief_version': req.brief_version, 'scope': 'RESEARCH_ONLY'})
    return {'acknowledged': True, 'brief_version': req.brief_version, 'scope': 'RESEARCH_ONLY',
            'notice': 'Acknowledgment permits research only. It does not certify legality or permit building, launching or any external action.'}


def require_safety_clearance(db, pid, brief):
    row = safety_for(db, pid, brief['version'])
    if not row:
        raise HTTPException(409, 'Brief has no safety assessment; refine it first')
    if row['status'] == 'BLOCK':
        raise HTTPException(403, {'message': 'BLOCKED by backend safety policy. Not overridable by founder approval or model output.',
                                  'findings': row['assessment']['findings']})
    if row['status'] == 'REVIEW_REQUIRED' and not row['acknowledged_at']:
        raise HTTPException(409, 'Safety review required: acknowledge the flagged risks (research-only) for this brief version before discovery.')
    return row


# ----------------------------------------------------------------------------- phase runs
@app.post('/api/projects/{pid}/phases/{phase}/run')
async def run_phase(pid: str, phase: str, project=Depends(authorize)):
    if phase in PHASES and phase not in ACTIVE_PHASES:
        raise HTTPException(501, f'Phase "{phase}" is ARCHITECTURE ONLY in this MVP; it is not executed and nothing is simulated.')
    if phase not in ACTIVE_PHASES:
        raise HTTPException(404, 'Unknown phase')
    if project['stopped']:
        raise HTTPException(409, 'This project has been stopped')
    with conn() as db:
        brief = latest_brief(db, pid)
        if brief is None:
            raise HTTPException(409, 'Refine the founder brief first')
        safety_row = require_safety_clearance(db, pid, brief)
        prior = latest_run(db, pid, phase)
        discovery = latest_run(db, pid, 'discover')
        evidence = evidence_of(db, pid)
        experiments = experiments_of(db, pid)
        previous_decision = qone(db, 'SELECT action,feedback FROM decisions WHERE phase_run_id=?', (prior['id'],)) if prior else None
    if prior and prior['state'] in ('PENDING_APPROVAL', 'APPROVED'):
        raise HTTPException(409, 'Existing phase run needs review or is already approved; request revision first')
    if phase == 'validate':
        if discovery is None or discovery['state'] != 'APPROVED':
            raise HTTPException(409, 'Founder must approve the latest discovery (matching the current brief) before validation')
        if discovery['brief_version'] != brief['version']:
            raise HTTPException(409, 'Discovery approval belongs to an older brief version; re-run discovery')
    ctx = {'founder_brief': {k: brief['payload'].get(k) for k in ('idea_summary',) + BRIEF_FIELDS},
           'provenance': brief['payload'].get('provenance', {})}
    if prior and prior['state'] in ('REVISE_REQUESTED', 'PIVOT_REQUESTED'):
        ctx['previous_report'] = prior['report']
        ctx['founder_revision_feedback'] = previous_decision['feedback'] if previous_decision else (prior.get('invalidated_reason') or '')
        ctx['revision_type'] = prior['state']
    started = time.monotonic()
    if phase == 'discover':
        try:
            result = await LLM.generate(DISCOVER_SYSTEM, ctx, DiscoveryReport, max_tokens=700)
        except (ModelUnavailable, ModelOutputError) as exc:
            raise HTTPException(503, str(exc)) from exc
        report = result.model_dump()
        report['_status'] = 'AI_HYPOTHESES_ONLY: nothing here is evidence; no customer was contacted.'
        report['_skeptic_flags'] = skeptic_review(report)
        gate = discovery_gate(report, missing_fields(brief))
    else:
        # The verdict is computed by code BEFORE the model is asked to explain it; the model cannot change it.
        verdict = evaluate_validation(brief=brief['payload'], brief_version=brief['version'], safety=safety_row['assessment'],
                                      discovery=discovery['report'], discovery_version=discovery['version'],
                                      evidence=evidence, experiments=experiments)
        ctx['discovery_report'] = {k: v for k, v in discovery['report'].items() if not k.startswith('_')}
        ctx['evidence_ledger'] = [{'id': e['id'], 'kind': e['kind'], 'dimension': e['dimension'], 'claim': e['claim'],
                                   'direction': e['direction'], 'url_status': e['url_status'], 'excerpt_status': e['excerpt_status'],
                                   'independence': e['independence'], 'sample_size': e['sample_size'], 'outcome': e['outcome'],
                                   'counted': not any(x['id'] == e['id'] for x in verdict['excluded_evidence'])}
                                  for e in evidence if not e['injection_flag']]
        ctx['backend_verdict'] = {'verdict': verdict['verdict'], 'headline': verdict['headline'],
                                  'matrix': {k: v['status'] for k, v in verdict['matrix'].items()},
                                  'unresolved_critical_assumptions': verdict['unresolved_critical_assumptions']}
        try:
            result = await LLM.generate(VALIDATE_SYSTEM, ctx, ValidationReport, max_tokens=700)
        except (ModelUnavailable, ModelOutputError) as exc:
            raise HTTPException(503, str(exc)) from exc
        report = result.model_dump()
        report['_status'] = 'VALIDATION_ASSISTANCE: AI explanation of a backend-computed verdict. Not customer testing.'
        report['_skeptic_flags'] = skeptic_review(report)
        gate = verdict
    latency = int((time.monotonic() - started) * 1000)
    report_hash = stable_hash(report)
    input_hash = stable_hash({'brief_version': brief['version'], 'safety': safety_row['status'], 'policy': safety_row['assessment']['policy_version'],
                              'discovery_run': discovery['id'] if phase == 'validate' else None,
                              'evidence': [e['id'] for e in evidence] if phase == 'validate' else None,
                              'experiments': [(x['id'], x['version'], x['status']) for x in experiments] if phase == 'validate' else None})
    run_id = uuid.uuid4().hex
    with conn() as db:
        last = latest_run(db, pid, phase)
        if last and last['state'] in ('PENDING_APPROVAL', 'APPROVED'):
            raise HTTPException(409, 'Another run was saved concurrently')
        if latest_brief(db, pid)['version'] != brief['version']:
            raise HTTPException(409, 'Brief changed while the agent ran; re-run')
        if phase == 'validate':
            d = latest_run(db, pid, 'discover')
            if not d or d['id'] != discovery['id'] or d['state'] != 'APPROVED':
                raise HTTPException(409, 'Discovery approval changed while validation ran')
        version = (last['version'] + 1) if last else 1
        db.execute('INSERT INTO phase_runs(id,project_id,phase,version,state,report_json,gate_json,brief_version,safety_status,report_hash,input_hash,upstream_run_id,model,latency_ms,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (run_id, pid, phase, version, 'PENDING_APPROVAL', jsonstr(report), jsonstr(gate), brief['version'], safety_row['status'],
                    report_hash, input_hash, discovery['id'] if phase == 'validate' else None, LLM.model, latency, now()))
        audit(db, pid, 'PHASE_RUN_READY', {'phase': phase, 'run_id': run_id, 'version': version, 'brief_version': brief['version'],
                                           'gate': gate.get('verdict') or gate.get('recommendation'), 'report_hash': report_hash,
                                           'model': LLM.model, 'latency_ms': latency, 'criteria_catalog_version': criteria.VERSION})
    return {'run_id': run_id, 'version': version, 'phase': phase, 'state': 'PENDING_APPROVAL', 'report': report, 'gate': gate,
            'report_hash': report_hash, 'brief_version': brief['version'], 'latency_ms': latency, 'model': LLM.model}


@app.post('/api/projects/{pid}/phases/{phase}/decision')
async def decide(pid: str, phase: str, req: DecisionRequest, project=Depends(authorize)):
    if phase not in ACTIVE_PHASES:
        raise HTTPException(404, 'Unknown active phase')
    if project['stopped']:
        raise HTTPException(409, 'Project is stopped')
    reject_obvious_secrets(req.feedback)
    if safety.looks_like_injection(req.feedback):
        raise HTTPException(422, 'Feedback contains instruction-like text that tries to change rules. Remove it.')
    with conn() as db:  # BEGIN IMMEDIATE already held: checks + writes are atomic, so replays cannot race.
        run = latest_run(db, pid, phase)
        if not run or run['id'] != req.run_id:
            raise HTTPException(409, 'Stale or mismatched run_id: this is not the latest run for this project/phase')
        if run['state'] != 'PENDING_APPROVAL':
            raise HTTPException(409, f'Run already decided or invalidated (state={run["state"]}); duplicate decisions are rejected')
        if not hmac.compare_digest(run['report_hash'], req.report_hash):
            raise HTTPException(409, 'report_hash does not match the stored artifact (tampered or outdated client)')
        brief = latest_brief(db, pid)
        if brief['version'] != req.brief_version or run['brief_version'] != brief['version']:
            raise HTTPException(409, 'Brief version changed since this report; re-run the phase')
        safety_row = safety_for(db, pid, brief['version'])
        if safety_row['status'] == 'BLOCK':
            raise HTTPException(403, 'Safety BLOCK: no decision can approve a blocked brief')
        if req.decision in ('REVISE', 'PIVOT') and not req.feedback.strip():
            raise HTTPException(422, 'Revision/pivot requires actionable founder feedback')
        rec = run['gate'].get('verdict') or run['gate'].get('recommendation')
        if req.decision == 'APPROVE' and rec in ('STOP_DO_NOT_LAUNCH', 'PIVOT', 'REVISE') and not req.acknowledge_risk:
            raise HTTPException(422, 'The gate advises against proceeding. Explicit acknowledgment is required to record a different course (research only).')
        if req.decision == 'APPROVE' and rec in ('STOP_DO_NOT_LAUNCH', 'PIVOT') and not req.feedback.strip():
            raise HTTPException(422, 'Record your reasons for choosing a different course than the recommendation')
        state = {'APPROVE': 'APPROVED', 'REVISE': 'REVISE_REQUESTED', 'PIVOT': 'PIVOT_REQUESTED', 'STOP': 'STOPPED'}[req.decision]
        scope = 'RESEARCH_ONLY' if req.decision == 'APPROVE' else 'NONE'
        db.execute('UPDATE phase_runs SET state=? WHERE id=?', (state, run['id']))
        experiments = experiments_of(db, pid)
        decision_id = uuid.uuid4().hex
        db.execute('INSERT INTO decisions(id,project_id,phase,phase_run_id,run_version,action,scope,feedback,acknowledged_risk,actor,brief_version,safety_status,report_hash,input_hash,experiment_versions_json,gate_recommendation,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (decision_id, pid, phase, run['id'], run['version'], req.decision, scope, req.feedback, int(req.acknowledge_risk),
                    'FOUNDER(project-token)', brief['version'], safety_row['status'], run['report_hash'], run['input_hash'],
                    jsonstr([{'id': x['id'], 'version': x['version'], 'status': x['status'], 'criteria_hash': x['criteria_hash']} for x in experiments]),
                    str(rec), now()))
        if req.decision == 'STOP':
            db.execute('UPDATE projects SET stopped=1 WHERE id=?', (pid,))
        if req.decision == 'PIVOT':
            # Pivot really resets downstream: discovery approval dies and locked experiments are archived.
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
                                            'risk_override': req.acknowledge_risk, 'gate': rec, 'decision_id': decision_id, 'criteria_catalog_version': criteria.VERSION})
    return {'decision_id': decision_id, 'state': state, 'phase': phase, 'scope': scope, 'gate_recommendation': rec,
            'notice': 'Approval permits further research only. It never authorizes building, launching, sending, publishing, signing, or spending.'}


# ----------------------------------------------------------------------------- evidence
PRIVATE_SUFFIXES = ('.local', '.internal', '.localhost', '.home', '.lan', '.corp')


def check_public_url(url):
    p = urlparse(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Only public HTTPS URLs on port 443 without credentials are allowed')
    host = p.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(PRIVATE_SUFFIXES) or host == 'metadata.google.internal':
        raise ValueError('Private hosts are blocked')
    try:
        literal = ipaddress.ip_address(host)
        addresses = [literal]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
        except (socket.gaierror, ValueError) as exc:
            raise ValueError('Host could not be resolved') from exc
    if not addresses or any(not a.is_global or a.is_multicast for a in addresses):
        raise ValueError('Only public IP addresses are allowed (no private, loopback, link-local or metadata ranges)')
    return host, addresses


async def verify_excerpt(url: str, excerpt: str):
    """Bounded, SSRF-guarded retrieval. Returns (url_status, excerpt_status, retrieved_at, note)."""
    try:
        check_public_url(url)
        async with httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False) as client:
            async with client.stream('GET', url, headers={'User-Agent': 'FounderOS-Research/0.2 (+local hackathon prototype)'}) as resp:
                if 300 <= resp.status_code < 400:
                    return 'UNVERIFIED', 'NOT_CHECKED', now(), f'Source redirected (HTTP {resp.status_code}); redirects are not followed for safety. Supply the final URL.'
                if resp.status_code != 200:
                    return 'UNVERIFIED', 'NOT_CHECKED', now(), f'Source unavailable (HTTP {resp.status_code}).'
                kind = resp.headers.get('content-type', '').split(';')[0].strip()
                if kind not in ('text/html', 'text/plain', 'application/xhtml+xml'):
                    return 'URL_ACCESSIBLE', 'NOT_CHECKED', now(), f'Content type {kind or "unknown"} is not checked (HTML/plain text only). Stays unverified.'
                chunks, n = [], 0
                async for chunk in resp.aiter_bytes():
                    n += len(chunk)
                    if n > 600_000:
                        return 'URL_ACCESSIBLE', 'NOT_CHECKED', now(), 'Source exceeds the 600 KB safe download limit.'
                    chunks.append(chunk)
                content = b''.join(chunks).decode('utf-8', 'replace')
        body = BeautifulSoup(content, 'html.parser').get_text(' ', strip=True) if kind != 'text/plain' else content
        if norm(excerpt) in norm(body):
            return 'URL_ACCESSIBLE', 'EXCERPT_MATCHED', now(), 'Excerpt found at URL. This proves only that the words appear there, not that the claim is true or that customers want this product.'
        return 'URL_ACCESSIBLE', 'NOT_MATCHED', now(), 'URL fetched, but the excerpt was NOT found in the page text. Stays unverified.'
    except (ValueError, httpx.HTTPError, UnicodeError) as exc:
        return 'UNVERIFIED', 'NOT_CHECKED', None, f'Retrieval not performed or failed safely: {str(exc)[:160]}'


@app.post('/api/projects/{pid}/evidence')
async def add_evidence(pid: str, req: EvidenceAdd, project=Depends(authorize)):
    reject_obvious_secrets(jsonstr(req.model_dump()))
    if project['stopped']:
        raise HTTPException(409, 'Project stopped')
    with conn() as db:
        validate = latest_run(db, pid, 'validate')
        if validate and validate['state'] in ('PENDING_APPROVAL', 'APPROVED'):
            raise HTTPException(409, 'Validation has a pending/approved snapshot. Request revision first; new evidence then feeds a new run.')
    free_text = ' '.join(filter(None, [req.claim, req.excerpt, req.method, req.positive_signals, req.negative_signals, req.title]))
    injection = safety.looks_like_injection(free_text)
    if req.kind == 'SECONDARY_BACKGROUND':
        url_status, excerpt_status, retrieved_at, note = await verify_excerpt(req.url, req.excerpt)
        independence = 'INDEPENDENT_SOURCE_FOUNDER_SELECTED'
        dedupe_key = stable_hash([urlparse(req.url).hostname, urlparse(req.url).path.rstrip('/'), norm(req.excerpt)])
    else:
        url_status, excerpt_status, retrieved_at, note = 'NOT_APPLICABLE', 'NOT_APPLICABLE', None, 'Founder-run research.'
        independence = 'FOUNDER_REPORTED_NOT_INDEPENDENTLY_VERIFIED'
        dedupe_key = stable_hash([req.kind, norm(req.method), req.sample_size, req.positives, str(req.collected_from), norm(req.segment or '')])
    limits = {
        'SECONDARY_BACKGROUND': 'Market context only. Excerpt match ≠ claim truth ≠ product demand.',
        'CUSTOMER_STATEMENT': 'Stated interest/opinion. Not demand; not a purchase. Founder-reported.',
        'CUSTOMER_BEHAVIOR': 'Observed voluntary action, founder-reported. Sample selection and incentives unassessed.',
    }[req.kind]
    if injection:
        limits = 'EXCLUDED: instruction-like text detected (possible prompt injection). Withheld from agents and gates. ' + limits
    eid = uuid.uuid4().hex
    with conn() as db:
        dup = qone(db, 'SELECT id FROM evidence WHERE project_id=? AND dedupe_key=? ORDER BY created_at LIMIT 1', (pid, dedupe_key))
        db.execute('''INSERT INTO evidence(id,project_id,kind,dimension,claim_id,claim,direction,source_url,title,publisher,author,published_on,retrieved_at,excerpt,
                      url_status,excerpt_status,relevance,independence,method,sample_size,positives,segment,geography,collected_from,collected_to,consent_confirmed,
                      experiment_id,experiment_version,outcome,rate_pct,adverse,positive_signals,negative_signals,dedupe_key,duplicate_of,injection_flag,limitations,created_at)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                   (eid, pid, req.kind, req.dimension, req.claim_id, req.claim, req.direction, req.url, req.title, req.publisher, req.author, req.published_on,
                    retrieved_at, req.excerpt, url_status, excerpt_status, req.relevance, independence, req.method, req.sample_size, req.positives, req.segment,
                    req.geography, str(req.collected_from) if req.collected_from else None, str(req.collected_to) if req.collected_to else None,
                    int(req.consent_confirmed), None, None, None, None, None, req.positive_signals, req.negative_signals, dedupe_key,
                    dup['id'] if dup else None, int(injection), limits + ' ' + note, now()))
        invalidate_runs(db, pid, 'new evidence added', phases=('validate',))
        audit(db, pid, 'EVIDENCE_ADDED', {'id': eid, 'kind': req.kind, 'dimension': req.dimension, 'url_status': url_status,
                                          'excerpt_status': excerpt_status, 'duplicate_of': dup['id'] if dup else None, 'injection_flag': injection})
    return {'id': eid, 'kind': req.kind, 'url_status': url_status, 'excerpt_status': excerpt_status, 'independence': independence,
            'duplicate_of': dup['id'] if dup else None, 'injection_flag': injection, 'limitations': limits + ' ' + note,
            'notice': 'Nothing here proves demand on its own. Counting rules: docs/business-decision-methodology.md'}


# ----------------------------------------------------------------------------- experiments (pre-registration)
@app.get('/api/projects/{pid}/experiments/suggest')
async def suggest(pid: str, project=Depends(authorize)):
    with conn() as db:
        brief = latest_brief(db, pid)
        if not brief:
            raise HTTPException(409, 'Refine the brief first')
        disc = latest_run(db, pid, 'discover')
        counted = [e for e in evidence_of(db, pid) if not e['duplicate_of'] and not e['injection_flag']]
        reg = risk_register(brief['payload'], disc and disc['report'], disc and disc['version'], counted)
        return suggest_experiment(brief['payload'], disc and disc['report'], reg, experiments_of(db, pid))


def _exp_rows(db, pid, series_id):
    rows = [unpack_experiment(x) for x in qall(db, 'SELECT * FROM experiments WHERE project_id=? AND series_id=? ORDER BY version', (pid, series_id))]
    if not rows:
        raise HTTPException(404, 'Experiment not found in this project')
    return rows


@app.post('/api/projects/{pid}/experiments', status_code=201)
async def create_experiment(pid: str, req: ExperimentDraft, project=Depends(authorize)):
    reject_obvious_secrets(jsonstr(req.model_dump()))
    if project['stopped']:
        raise HTTPException(409, 'Project stopped')
    text = ' '.join([req.hypothesis, req.metric, req.consent_method, req.founder_actions, req.pivot_alternative or ''])
    blocks = safety.find_blocks(text)
    if blocks or safety.looks_like_injection(text):
        raise HTTPException(422, {'message': 'Experiment design violates safety rules (no fake sign-ups, outreach by the AI, payments, etc.)',
                                  'findings': blocks})
    payload = req.model_dump()
    sid = uuid.uuid4().hex
    with conn() as db:
        db.execute('INSERT INTO experiments(series_id,version,project_id,status,payload_json,criteria_hash,locked_at,result_evidence_id,created_at) VALUES(?,?,?,?,?,?,NULL,NULL,?)',
                   (sid, 1, pid, 'DRAFT', jsonstr(payload), stable_hash(criteria_of(payload)), now()))
        audit(db, pid, 'EXPERIMENT_DRAFTED', {'experiment_id': sid, 'version': 1})
    return {'experiment_id': sid, 'version': 1, 'status': 'DRAFT', 'criteria_hash': stable_hash(criteria_of(payload)), 'criteria': criteria_of(payload),
            'notice': 'DRAFT. Lock it (pre-register) BEFORE collecting data. A planned experiment is never evidence.'}


@app.post('/api/projects/{pid}/experiments/{sid}/lock')
async def lock_experiment(pid: str, sid: str, req: ExperimentLock, project=Depends(authorize)):
    if project['stopped']:
        raise HTTPException(409, 'Project stopped')
    with conn() as db:
        rows = _exp_rows(db, pid, sid)
        x = rows[-1]
        if x['version'] != req.version or x['status'] != 'DRAFT':
            raise HTTPException(409, f'Only the latest DRAFT version can be locked (latest v{x["version"]} is {x["status"]})')
        if not hmac.compare_digest(x['criteria_hash'], req.criteria_hash):
            raise HTTPException(409, 'criteria_hash mismatch: re-read the draft before locking')
        locked_at = now()
        db.execute('UPDATE experiments SET status=?, locked_at=? WHERE series_id=? AND version=?', ('LOCKED', locked_at, sid, x['version']))
        audit(db, pid, 'EXPERIMENT_PREREGISTERED', {'experiment_id': sid, 'version': x['version'], 'criteria_hash': x['criteria_hash'], 'locked_at': locked_at, 'criteria_catalog_version': criteria.VERSION})
    return {'experiment_id': sid, 'version': x['version'], 'status': 'LOCKED', 'locked_at': locked_at, 'criteria_hash': x['criteria_hash'],
            'notice': 'Criteria are now frozen. Submitting results cannot change them; editing creates a new version and retires old results.'}


@app.post('/api/projects/{pid}/experiments/{sid}/revise', status_code=201)
async def revise_experiment(pid: str, sid: str, req: ExperimentDraft, project=Depends(authorize)):
    """Changing hypothesis/metric/thresholds = NEW version. Prior results stop counting; gates built on them are invalidated."""
    reject_obvious_secrets(jsonstr(req.model_dump()))
    if project['stopped']:
        raise HTTPException(409, 'Project stopped')
    with conn() as db:
        rows = _exp_rows(db, pid, sid)
        prev = rows[-1]
        payload = req.model_dump()
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
    if project['stopped']:
        raise HTTPException(409, 'Project stopped')
    signals = ' '.join(filter(None, [req.method, req.positive_signals, req.negative_signals]))
    if safety.looks_like_injection(signals):
        raise HTTPException(422, 'Result text contains instruction-like content. Remove it.')
    with conn() as db:
        rows = _exp_rows(db, pid, sid)
        x = rows[-1]
        if x['version'] != req.version or x['status'] != 'LOCKED':
            raise HTTPException(409, f'Results are only accepted against the latest LOCKED version (latest v{x["version"]} is {x["status"]}). Lock first; a planned experiment is not evidence.')
        if not hmac.compare_digest(x['criteria_hash'], req.criteria_hash):
            raise HTTPException(409, 'criteria_hash mismatch: results must reference the exact locked criteria')
        if x['result_evidence_id']:
            raise HTTPException(409, 'A result already exists for this version. Create a new version for a repeat run.')
        if req.collected_from < __import__('datetime').date.fromisoformat(x['locked_at'][:10]):
            raise HTTPException(422, f'Results collected before the pre-registration date ({x["locked_at"][:10]}) are not accepted as pre-registered.')
        crit = criteria_of(x['payload'])
        outcome = evaluate_result(crit, req.sample_size, req.positives)
        eid = uuid.uuid4().hex
        db.execute('''INSERT INTO evidence(id,project_id,kind,dimension,claim_id,claim,direction,source_url,title,publisher,author,published_on,retrieved_at,excerpt,
                      url_status,excerpt_status,relevance,independence,method,sample_size,positives,segment,geography,collected_from,collected_to,consent_confirmed,
                      experiment_id,experiment_version,outcome,rate_pct,adverse,positive_signals,negative_signals,dedupe_key,duplicate_of,injection_flag,limitations,created_at)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                   (eid, pid, 'PRE_REGISTERED_EXPERIMENT_RESULT', crit['dimension'] or 'demand', crit['claim_id'], crit['hypothesis'],
                    {'PASS': 'SUPPORTS', 'FAIL': 'CONTRADICTS'}.get(outcome['outcome'], 'UNSURE'), None, None, None, None, None, None, None,
                    'NOT_APPLICABLE', 'NOT_APPLICABLE', 'CLAIM_RELEVANT', 'FOUNDER_REPORTED_NOT_INDEPENDENTLY_VERIFIED', req.method, req.sample_size,
                    req.positives, crit['target_segment'], None, str(req.collected_from), str(req.collected_to), int(req.consent_confirmed),
                    sid, x['version'], outcome['outcome'], outcome['rate_pct'], int(outcome['adverse']), req.positive_signals, req.negative_signals,
                    stable_hash([sid, x['version']]), None, 0, ' '.join(outcome['caveats']) + ' ' + outcome['explanation'], now()))
        db.execute('UPDATE experiments SET result_evidence_id=? WHERE series_id=? AND version=?', (eid, sid, x['version']))
        invalidate_runs(db, pid, 'experiment result recorded', phases=('validate',))
        audit(db, pid, 'EXPERIMENT_RESULT_RECORDED', {'experiment_id': sid, 'version': x['version'], 'evidence_id': eid, 'outcome': outcome['outcome'],
                                                      'n': req.sample_size, 'positives': req.positives, 'criteria_hash': x['criteria_hash']})
    return {'evidence_id': eid, 'experiment_id': sid, 'version': x['version'], 'locked_criteria': crit, 'locked_at': x['locked_at'], **outcome,
            'notice': 'Founder-reported. Compared against the criteria locked BEFORE collection. One passed hypothesis does not validate the business.'}


# ----------------------------------------------------------------------------- hard-denied outbound actions
@app.post('/api/projects/{pid}/external-action', status_code=403)
async def external_action_denied(pid: str, req: PublicActionRequest, project=Depends(authorize)):
    reject_obvious_secrets(req.description)
    with conn() as db:
        audit(db, pid, 'EXTERNAL_ACTION_BLOCKED', {'kind': req.kind, 'description': req.description[:200]})
    raise HTTPException(403, 'Draft-only MVP: publishing, sending, spending, signing, paying, refunding, transferring and contacting are NOT implemented '
                             'and are hard-denied. Phase approval never grants external-action permission.')


HERE = Path(__file__).resolve().parent
STATIC = HERE / 'static'
if STATIC.exists():
    app.mount('/assets', StaticFiles(directory=STATIC), name='assets')


@app.get('/')
async def home():
    return FileResponse(STATIC / 'index.html')

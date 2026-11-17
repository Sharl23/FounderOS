"""Model health / OOM mapping, v0.4 -> v7 SQLite migration, named fixture briefs and gate bypass attempts."""
import asyncio
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, llm, db as dbmod
from app.llm import classify_error, OllamaClient, ModelUnavailable
from .conftest import FakeModel, make_project, refine, run, decide, approved_discovery, TODAY

# The two failures reported on the founder's Windows laptop (verbatim fragments).
GPU_OOM = 'llama runner process has terminated: cudaMalloc failed: out of memory'
CPU_OOM = 'ggml_backend_cpu_buffer_type_alloc_buffer: failed to allocate CPU_REPACK buffer of size 625508352'


@pytest.mark.parametrize('text,status,code', [(GPU_OOM, 500, 'MODEL_OOM_GPU'), (CPU_OOM, 500, 'MODEL_OOM_CPU'),
                                              ('model "qwen2.5:1.5b-instruct" not found, try pulling it first', 404, 'MODEL_NOT_FOUND'),
                                              ('something else broke', 500, 'MODEL_ERROR')])
def test_ollama_error_mapping(text, status, code):
    assert classify_error(text, status) == code


def _client_with(handler):
    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def make(*a, **k):
        k.pop('trust_env', None)
        return real(transport=transport, **{x: y for x, y in k.items() if x in ('timeout',)})
    return make


def test_generate_maps_oom_to_actionable_503(monkeypatch):
    monkeypatch.setattr(llm.httpx, 'AsyncClient', _client_with(lambda req: httpx.Response(500, json={'error': CPU_OOM})))
    class Out(llm.BaseModel):
        a: int
    c = OllamaClient()
    with pytest.raises(ModelUnavailable) as e:
        asyncio.run(c.generate('s', {}, Out))
    assert e.value.code == 'MODEL_OOM_CPU'


def test_model_health_does_not_report_green_from_reachability_alone(monkeypatch):
    def handler(req):
        if req.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': 'qwen2.5:1.5b-instruct'}]})
        if req.url.path == '/api/generate':
            return httpx.Response(500, json={'error': GPU_OOM})
        return httpx.Response(200, json={'models': []})
    monkeypatch.setattr(llm.httpx, 'AsyncClient', _client_with(handler))
    h = asyncio.run(OllamaClient().health(probe=False))
    assert h['model_pulled'] and h['inference_verified'] is False
    h = asyncio.run(OllamaClient().health(probe=True))
    assert h['code'] == 'MODEL_OOM_GPU' and h['inference_verified'] is False and 'OLLAMA_NUM_GPU=0' in h['advice']


def test_model_health_ready_only_after_real_probe(monkeypatch):
    def handler(req):
        if req.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': 'qwen2.5:1.5b-instruct'}]})
        if req.url.path == '/api/generate':
            return httpx.Response(200, json={'response': 'OK'})
        return httpx.Response(200, json={'models': [{'name': 'qwen2.5:1.5b-instruct', 'size': 1_200_000_000, 'size_vram': 0}]})
    monkeypatch.setattr(llm.httpx, 'AsyncClient', _client_with(handler))
    h = asyncio.run(OllamaClient().health(probe=True))
    assert h['code'] == 'READY' and h['inference_verified'] and h['device']['vram_mb'] == 0


def test_conservative_model_options(monkeypatch):
    monkeypatch.setenv('OLLAMA_NUM_GPU', '0')
    monkeypatch.setenv('OLLAMA_NUM_CTX', '1024')
    o = OllamaClient().options(100)
    assert o['num_gpu'] == 0 and o['num_ctx'] == 1024
    monkeypatch.delenv('OLLAMA_NUM_GPU')
    assert 'num_gpu' not in OllamaClient().options(100) and OllamaClient().model == 'qwen2.5:1.5b-instruct'


def test_oom_during_refine_keeps_input_and_reports_code(client, monkeypatch):
    class OOM(FakeModel):
        async def generate(self, *a, **k):
            raise ModelUnavailable('MODEL_OOM_CPU: ' + CPU_OOM, 'MODEL_OOM_CPU')
    pid, h = make_project(client)
    monkeypatch.setattr(main, 'LLM', OOM())
    r = client.post(f'/api/projects/{pid}/refine', headers=h)
    assert r.status_code == 503 and r.json()['detail']['code'] == 'MODEL_OOM_CPU' and 'RAM' in r.json()['detail']['advice']
    s = client.get(f'/api/projects/{pid}', headers=h).json()
    assert s['project']['original_idea'].startswith('An AI planner') and s['brief'] is None   # input kept, nothing simulated


# ---------------------------------------------------------------- migration from a v0.4 database
def test_v04_database_migrates_without_losing_projects_or_decisions(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[2]
    old = subprocess.run(['git', 'show', 'HEAD~1:backend/app/db.py'], cwd=repo, capture_output=True, text=True)
    src = old.stdout if old.returncode == 0 and 'SCHEMA' in old.stdout else None
    if src is None:
        pytest.skip('v0.4 baseline not available in git history')
    ns = {}
    exec(src.split('def now')[0], ns)   # only the v0.4 SCHEMA string and imports
    path = tmp_path / 'v04.sqlite3'
    con = sqlite3.connect(path)
    con.executescript(ns['SCHEMA'])
    token = 'TEST_ONLY-token'
    con.execute('INSERT INTO projects(id, token_hash, original_idea, intake_json, created_at) VALUES(?,?,?,?,?)',
                ('p1', hashlib.sha256(token.encode()).hexdigest(), 'TEST_ONLY v0.4 idea text', json.dumps({'idea': 'x'}), '2026-11-16T10:00:00'))
    con.execute('INSERT INTO decisions(id,project_id,phase,phase_run_id,run_version,action,scope,feedback,acknowledged_risk,actor,brief_version,safety_status,report_hash,input_hash,experiment_versions_json,gate_recommendation,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('d1', 'p1', 'discover', 'r1', 1, 'APPROVE', 'RESEARCH_ONLY', '', 0, 'FOUNDER', 1, 'ALLOW_DISCOVERY', 'h' * 64, 'i' * 64, '[]', 'X', '2026-11-16T10:01:00'))
    con.commit()
    con.close()
    monkeypatch.setenv('FOUNDEROS_DB', str(path))
    monkeypatch.setattr(main, 'LLM', FakeModel())
    with TestClient(main.app) as c:
        s = c.get('/api/projects/p1', headers={'X-Project-Token': token})
        assert s.status_code == 200 and s.json()['project']['original_idea'] == 'TEST_ONLY v0.4 idea text'
        assert s.json()['decisions'][0]['id'] == 'd1' and s.json()['decisions'][0]['criteria_version'] is None
    con = sqlite3.connect(path)
    cols = {r[1] for r in con.execute('PRAGMA table_info(evidence)')}
    assert {'direction_id', 'criterion_id', 'source_hash'} <= cols
    assert con.execute('SELECT version FROM schema_migrations').fetchone()[0] == 'v7'
    with pytest.raises(sqlite3.IntegrityError):
        con.execute('DELETE FROM decisions')


# ---------------------------------------------------------------- named fixture briefs (TEST_ONLY)
STUDY = dict(idea='A digital study planner for Cairo University engineering students who keep missing assignment deadlines. They currently use WhatsApp groups and paper notes. I can build web apps in Python. No interviews done yet.',
             target_customers='Cairo University engineering students', target_market='Cairo, Egypt', budget='1000 EGP', timeline='6 weeks',
             current_workaround='WhatsApp groups and paper notes', values='privacy first, no ads')
FOOD = dict(idea='An AI inventory forecasting web app for small Cairo restaurants that predicts how much stock to order from their daily sales numbers, to reduce food waste. No customer data yet.',
            target_customers='Owners of small restaurants in Cairo', target_market='Cairo, Egypt', budget='2000 EGP', timeline='8 weeks',
            current_workaround='Gut feeling and paper notebooks')
BAD = dict(idea='A crypto savings app that guarantees 30% monthly returns; we hold users\' deposits and post fake testimonials from Cairo University professors.',
           target_market='Cairo, Egypt')


def test_study_planner_brief_permits_research_but_never_proof_or_launch(client):
    pid, h = make_project(client, **STUDY)
    r = refine(client, pid, h)
    assert r['safety']['status'] == 'ALLOW_DISCOVERY'
    approved_discovery(client, pid, h)
    g = run(client, pid, h, 'validate')['gate']
    assert g['verdict'] == 'NEEDS_EVIDENCE' and g['matrix']['demand']['status'] == 'UNKNOWN'
    assert g['permissions'] == {'continue_research': True, 'build': False, 'launch': False, 'external_actions': False}
    blob = json.dumps(g).lower()
    assert 'validated demand' not in blob and 'proven' not in g['headline'].lower()


def test_food_waste_restaurant_brief_not_misclassified(client):
    pid, h = make_project(client, **FOOD)
    a = refine(client, pid, h)['safety']
    out = {r['rule_id']: r['outcome'] for r in a['rules']}
    assert out['physical_goods_exclusion'] == 'CLEAR' and out['financial_crypto_exclusion'] == 'CLEAR'
    assert out['money_or_credentials_dependency'] == 'CLEAR' and out['illegal_in_target_market'] == 'UNKNOWN_SOURCE'
    assert a['status'] != 'BLOCK'


def test_malicious_brief_hits_multiple_hard_stops_and_stays_blocked(client):
    pid, h = make_project(client, **BAD)
    a = refine(client, pid, h)['safety']
    hard = {r['rule_id'] for r in a['rules'] if r['outcome'] == 'HARD_STOP'}
    assert {'financial_crypto_exclusion', 'income_promise_dependency', 'fake_proof_dependency', 'money_or_credentials_dependency'} <= hard
    assert client.post(f'/api/projects/{pid}/phases/discover/run', headers=h).status_code == 403
    assert client.post(f'/api/projects/{pid}/safety/acknowledge', headers=h, json={'brief_version': 1, 'statement': 'Founder approves anyway'}).status_code == 403


# ---------------------------------------------------------------- bypass attempts
def test_direct_api_bypass_attempts(client):
    pid, h = make_project(client, **STUDY)
    refine(client, pid, h)
    # validate before discovery approval
    assert client.post(f'/api/projects/{pid}/phases/validate/run', headers=h).status_code == 409
    d = run(client, pid, h, 'discover')
    # approve with stale brief after an edit
    client.post(f'/api/projects/{pid}/clarify', headers=h, json={'answers': {'budget': '800 EGP'}})
    assert decide(client, pid, h, 'discover', d, 'APPROVE', acknowledge_risk=True, feedback='x').status_code == 409
    # external actions never possible, even after approvals
    for k in ('PUBLISH', 'SEND', 'SPEND', 'SIGN'):
        assert client.post(f'/api/projects/{pid}/external-action', headers=h, json={'kind': k, 'description': 'TEST_ONLY attempt'}).status_code == 403


def test_result_cannot_race_ahead_of_lock(client):
    pid, h = make_project(client, **STUDY)
    approved_discovery(client, pid, h)
    d = client.post(f'/api/projects/{pid}/experiments', headers=h, json={'hypothesis': 'Students will join a consented waitlist', 'target_segment': 'Cairo students',
                    'metric': 'Share who voluntarily join the waitlist', 'success_threshold_pct': 30, 'adverse_threshold_pct': 10, 'min_sample': 10,
                    'consent_method': 'Opt-in explained in person', 'founder_actions': 'Ask classmates face to face', 'cost_estimate': '0',
                    'threshold_origin': 'TEAM_ASSUMPTION', 'time_window_days': 7}).json()
    r = client.post(f'/api/projects/{pid}/experiments/{d["experiment_id"]}/result', headers=h, json={'version': 1, 'criteria_hash': d['criteria_hash'],
                    'sample_size': 10, 'positives': 9, 'method': 'TEST_ONLY form results', 'collected_from': TODAY, 'collected_to': TODAY, 'consent_confirmed': True})
    assert r.status_code == 409


def test_spa_deep_links_serve_app_shell(client):
    for path in ('/projects', '/projects/abc/brief', '/projects/abc/research', '/roadmap'):
        r = client.get(path)
        assert r.status_code == 200 and 'FounderOS' in r.text

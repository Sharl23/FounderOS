"""Happy path, HITL bypass resistance, auditability. (Legacy suite rewritten for the v2 gate contract.)"""
from app import main
from app.llm import ModelUnavailable
from .conftest import make_project, refine, run, decide, approved_discovery, TODAY


def test_full_founder_journey_persists_and_gates(client, project):
    pid, h = project
    state = client.get(f'/api/projects/{pid}', headers=h).json()
    assert state['brief'] is None and state['phases'][2]['status'] == 'LIVE'
    r = refine(client, pid, h)
    brief = r['brief']
    assert brief['original_idea_text'].startswith('An AI planner')
    # v0.8: found in the founder's own words (with a span), not merely inferred by the model.
    assert brief['provenance']['target_customers'] == 'STATED_IN_TEXT'
    assert brief['fields']['target_customers']['spans'][0]['source'] == 'idea'
    assert brief['fields']['current_workaround']['status'] == 'MODEL_SUGGESTED_UNCONFIRMED' and brief['current_workaround'] is None
    assert brief['provenance']['budget'] == 'UNKNOWN' and brief['budget'] is None
    assert len(brief['questions']) <= 3
    assert r['safety']['status'] == 'ALLOW_DISCOVERY'
    # Validation before discovery approval is rejected at the backend.
    assert client.post(f'/api/projects/{pid}/phases/validate/run', headers=h).status_code == 409
    d = run(client, pid, h, 'discover')
    assert d['state'] == 'PENDING_APPROVAL' and d['gate']['approval_scope'] == 'RESEARCH_ONLY'
    assert d['gate']['external_actions_permitted'] is False
    assert client.post(f'/api/projects/{pid}/phases/validate/run', headers=h).status_code == 409
    # Zero evidence: D09 says REPEAT. Plain approval is refused; a recorded, reasoned override is research-only.
    ev = client.get(f'/api/projects/{pid}', headers=h).json()['criteria']['discover']
    assert ev['evaluation']['exit'] == 'REPEAT' and ev['stale'] is False
    assert decide(client, pid, h, 'discover', d, 'APPROVE').status_code == 422
    ok = decide(client, pid, h, 'discover', d, 'APPROVE', acknowledge_risk=True, feedback='TEST_ONLY: design a demand test',
                evaluation_hash=ev['evaluation_hash'])
    assert ok.status_code == 200, ok.text
    # replay / duplicate
    assert decide(client, pid, h, 'discover', d, 'APPROVE', acknowledge_risk=True, feedback='x').status_code == 409
    v = run(client, pid, h, 'validate')
    g = v['gate']
    assert g['verdict'] == 'NEEDS_EVIDENCE' and g['verdict_kind'] == 'BUSINESS_ADVISORY'
    assert g['permissions'] == {'continue_research': True, 'build': False, 'launch': False, 'external_actions': False}
    assert all(m['status'] == 'UNKNOWN' for m in g['matrix'].values())
    assert g['strongest_source']['id'] is None and 'SOURCE UNAVAILABLE' in g['strongest_source']['limitations']
    assert g['next_experiment']['kind'] == 'PROPOSED_EXPERIMENT_NEEDS_FOUNDER_APPROVAL'
    assert 'VALIDATED' not in g['verdict'] and 'PROCEED' not in g['verdict']
    # The validate agent received the backend verdict and cannot change it.
    ctx = main.LLM.calls[-1][1]
    assert ctx['backend_verdict']['verdict'] == 'NEEDS_EVIDENCE'
    assert decide(client, pid, h, 'validate', v, 'APPROVE').status_code == 200  # research-only approval is allowed
    state = client.get(f'/api/projects/{pid}', headers=h).json()
    assert state['passport']['verdict']['verdict'] == 'NEEDS_EVIDENCE'
    dec = state['passport']['founder_decision']
    assert dec['scope'] == 'RESEARCH_ONLY' and dec['brief_version'] == 1 and dec['report_hash'] == v['report_hash']
    assert dec['safety_status'] == 'ALLOW_DISCOVERY' and dec['gate_recommendation'] == 'NEEDS_EVIDENCE'
    assert any(e['event'] == 'FOUNDER_DECISION' for e in state['audit'])


def test_stop_is_enforced(client, project):
    pid, h = project
    d = approved_discovery(client, pid, h)
    v = run(client, pid, h, 'validate')
    assert decide(client, pid, h, 'validate', v, 'STOP').status_code == 200
    assert client.get(f'/api/projects/{pid}', headers=h).json()['project']['stopped'] == 1
    assert client.post(f'/api/projects/{pid}/phases/validate/run', headers=h).status_code == 409
    assert client.post(f'/api/projects/{pid}/refine', headers=h).status_code == 409
    assert client.post(f'/api/projects/{pid}/evidence', headers=h, json={'kind': 'SECONDARY_BACKGROUND', 'claim': 'anything at all here',
                                                                        'url': 'https://testonly-publisher.org/x', 'excerpt': 'twelve characters here'}).status_code == 409


def test_revision_feedback_reaches_next_run_and_old_run_is_stale(client, project):
    pid, h = project
    refine(client, pid, h)
    one = run(client, pid, h, 'discover')
    assert decide(client, pid, h, 'discover', one, 'REVISE').status_code == 422  # feedback required
    assert decide(client, pid, h, 'discover', one, 'REVISE', feedback='Focus on accessibility').status_code == 200
    two = run(client, pid, h, 'discover')
    assert two['version'] == 2 and two['run_id'] != one['run_id']
    assert main.LLM.calls[-1][1]['founder_revision_feedback'] == 'Focus on accessibility'
    assert decide(client, pid, h, 'discover', one, 'APPROVE').status_code == 409  # stale


def test_edited_brief_invalidates_approvals(client, project):
    pid, h = project
    d = approved_discovery(client, pid, h)
    r = client.post(f'/api/projects/{pid}/clarify', headers=h, json={'answers': {'target_market': 'Alexandria'}})
    assert r.status_code == 200 and r.json()['version'] == 2
    state = client.get(f'/api/projects/{pid}', headers=h).json()
    disc = next(x for x in state['phase_runs'] if x['phase'] == 'discover')
    assert disc['state'] == 'INVALIDATED' and 'brief corrected' in disc['invalidated_reason']
    assert any(e['event'] == 'APPROVAL_INVALIDATED' for e in state['audit'])
    assert client.post(f'/api/projects/{pid}/phases/validate/run', headers=h).status_code == 409
    # decision against old brief version is rejected even with the right run id
    assert decide(client, pid, h, 'discover', d, 'APPROVE').status_code == 409


def test_tampered_hash_cross_project_and_auth(client):
    pid, h = make_project(client)
    pid2, h2 = make_project(client, idea='A different idea about bicycle repair bookings in Giza')
    refine(client, pid, h)
    d = run(client, pid, h, 'discover')
    bad = dict(d, report_hash='0' * 64)
    assert decide(client, pid, h, 'discover', bad, 'APPROVE', acknowledge_risk=True, feedback='x').status_code == 409
    # cross-project: project 2's token cannot decide project 1's run
    assert decide(client, pid, h2, 'discover', d, 'APPROVE').status_code == 404
    refine(client, pid2, h2)
    assert decide(client, pid2, h2, 'discover', d, 'APPROVE').status_code == 409
    assert client.get(f'/api/projects/{pid}').status_code == 401
    assert client.get(f'/api/projects/{pid}', headers={'X-Project-Token': 'wrong'}).status_code == 404
    assert decide(client, pid, h, 'discover', d, 'APPROVE', acknowledge_risk=True, feedback='TEST_ONLY').status_code == 200  # the honest one still works


def test_external_actions_hard_denied_and_later_phases_not_simulated(client, project):
    pid, h = project
    for kind in ('PUBLISH', 'SEND', 'SPEND', 'SIGN', 'PAY', 'REFUND', 'TRANSFER', 'CONTACT'):
        assert client.post(f'/api/projects/{pid}/external-action', headers=h, json={'kind': kind, 'description': 'Send marketing email'}).status_code == 403
    assert any(x['event'] == 'EXTERNAL_ACTION_BLOCKED' for x in client.get(f'/api/projects/{pid}', headers=h).json()['audit'])
    refine(client, pid, h)
    for phase in ('build', 'commercial_setup', 'launch', 'operate_learn'):
        assert client.post(f'/api/projects/{pid}/phases/{phase}/run', headers=h).status_code in (404, 409)   # phases 3-6 run through /workflow endpoints
    assert client.post(f'/api/projects/{pid}/phases/nonsense/run', headers=h).status_code == 404


def test_offline_failure_is_visible_not_fake(client, project, monkeypatch):
    pid, h = project

    class Offline:
        model = 'qwen2.5:1.5b-instruct'
        last_latency_ms = None

        async def status(self):
            return {'ollama_reachable': False, 'model_pulled': False}

        async def generate(self, *a, **k):
            raise ModelUnavailable('Ollama is offline')
    monkeypatch.setattr(main, 'LLM', Offline())
    response = client.post(f'/api/projects/{pid}/refine', headers=h)
    assert response.status_code == 503 and 'offline' in response.json()['detail']['message']
    assert response.json()['detail']['note'].startswith('Your input is saved')
    assert client.get(f'/api/projects/{pid}', headers=h).json()['brief'] is None
    assert client.get('/api/health').json()['ollama']['ollama_reachable'] is False


def test_validate_pivot_reopens_discovery_and_archives_experiments(client, project):
    pid, h = project
    approved_discovery(client, pid, h)
    from .conftest import locked_experiment
    x = locked_experiment(client, pid, h)
    v = run(client, pid, h, 'validate')
    assert decide(client, pid, h, 'validate', v, 'PIVOT', feedback='Choose a new customer segment').status_code == 200
    state = client.get(f'/api/projects/{pid}', headers=h).json()
    assert next(r for r in state['phase_runs'] if r['phase'] == 'discover')['state'] == 'PIVOT_REQUESTED'
    assert next(e for e in state['experiments'] if e['id'] == x['experiment_id'])['status'] == 'ARCHIVED_PIVOT'
    assert client.post(f'/api/projects/{pid}/phases/validate/run', headers=h).status_code == 409
    assert client.post(f'/api/projects/{pid}/clarify', headers=h, json={'answers': {'target_customers': 'Public school teachers'}}).status_code == 200
    rerun = run(client, pid, h, 'discover')
    assert rerun['version'] == 2 and main.LLM.calls[-1][1]['revision_type'] == 'PIVOT_REQUESTED'


def test_home_health_and_secret_guard(client, project):
    assert 'FounderOS' in client.get('/').text
    assert client.get('/api/health').json()['mode'] == 'LIVE_LOCAL_OLLAMA_REQUIRED'
    for idea in ['Build an app. password: superSecret1234 and more',
                 'Use this test card 4111 1111 1111 1111 in our startup',
                 'My founder idea uses api_key=secret123456789']:
        assert client.post('/api/projects', json={'idea': idea}).status_code == 422
    pid, h = project
    refine(client, pid, h)
    assert client.post(f'/api/projects/{pid}/clarify', headers=h, json={'answers': {'problem': 'api_key: secret123456789'}}).status_code == 422
    # nothing of that kind reached the DB
    state = client.get(f'/api/projects/{pid}', headers=h).json()
    assert 'secret123456789' not in str(state)


def test_decision_log_is_append_only(client, project):
    pid, h = project
    d = approved_discovery(client, pid, h)
    import sqlite3, os, pytest
    db = sqlite3.connect(os.environ['FOUNDEROS_DB'])
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('UPDATE decisions SET action="STOP"')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('DELETE FROM audit')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('UPDATE phase_runs SET report_json="{}"')
    db.close()

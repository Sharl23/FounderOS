"""Test fixtures. The FakeModel is injected ONLY here; the shipped app has no fake fallback."""
import datetime
import pytest
from fastapi.testclient import TestClient
from app import main
from app.schemas import RefinedBrief, DiscoveryReport, ValidationReport, JudgeOutput, CheckJudgeOutput

TODAY = datetime.date.today().isoformat()


class FakeModel:
    """TEST-ONLY deterministic stand-in for the local LLM."""
    model = 'TEST FAKE MODEL (never used at runtime)'
    last_latency_ms = 0

    def __init__(self, praise=False, judge=None, flags=None, discovery=None, check_judge=None, validation=None):
        self.praise = praise
        self.discovery = discovery      # callable(context) -> DiscoveryReport kwargs, TEST_ONLY
        self.check_judge = check_judge  # callable(context) -> CheckJudgeOutput kwargs, TEST_ONLY
        self.validation = validation    # callable(context) -> ValidationReport | raises, TEST_ONLY
        self.calls = []
        self.judge = judge          # callable(context) -> dict, TEST_ONLY
        self.flags = flags or []    # TEST_ONLY model risk flags

    async def status(self):
        return {'ollama_reachable': False, 'model_pulled': False, 'error': 'test fake'}

    async def generate(self, system, context, output_type, max_tokens=700):
        self.calls.append((output_type.__name__, context))
        if output_type is RefinedBrief:
            return RefinedBrief(idea_summary='AI study planner for university students', problem='Assignment planning is difficult',
                                target_customers='University students', target_market='Cairo', questions=['What is your budget?'],
                                current_workaround='WhatsApp reminders', assumptions=['Students might need better planning'],
                                risk_flags=self.flags)
        if output_type is DiscoveryReport and self.discovery:
            return DiscoveryReport(**self.discovery(context))
        if output_type is CheckJudgeOutput:
            if self.check_judge:
                return CheckJudgeOutput(**self.check_judge(context))
            ids = [e['id'] for e in context['accepted_evidence']]
            return CheckJudgeOutput(check_id=context['check']['id'], rating='MIXED', evidence_ids=ids[:1], reasoning='TEST_ONLY judge.')
        if output_type is ValidationReport and self.validation:
            return self.validation(context)
        if output_type is DiscoveryReport:
            return DiscoveryReport(problem_statement='Students might struggle with assignments',
                                   target_customers=['Egyptian university students'], value_proposition='Plan tasks clearly',
                                   alternatives_unverified=['Paper planners (unverified)'],
                                   hypotheses=['Students may pay 50 EGP/month for planning' if self.praise else 'Students may pay for planning',
                                               'Students currently use WhatsApp reminders as a workaround'],
                                   experiments=['Interview 10 volunteers with consent'], unknowns=['Willingness to pay'],
                                   directions=[{'name': 'Planner for engineering students', 'segment': 'Engineering students', 'value': 'Deadline view'},
                                               {'name': 'Planner for TAs', 'segment': 'Teaching assistants', 'value': 'Class reminders'}])
        if output_type is ValidationReport:
            return ValidationReport(summary='Huge demand, this idea is validated and will definitely succeed' if self.praise
                                    else 'No independent evidence of actual purchasing demand',
                                    market_research_vs_customer_demand='Background sources only; demand untested',
                                    risks=['Demand is not confirmed'], contradictions_or_gaps=['No customer behaviour'],
                                    pricing_hypotheses=['Untested: 50 EGP/month'], business_model_hypotheses=['Subscription (untested)'],
                                    competitor_research_limitations=['No competitor data sourced'])
        if output_type is JudgeOutput:
            if self.judge:
                return JudgeOutput(**self.judge(context))
            ids = [e['id'] for e in context['accepted_evidence']]
            return JudgeOutput(criterion_id=context['criterion']['id'], proposed_score=3, evidence_ids=ids[:1],
                               reasoning='Context-level support from the cited evidence.', caveats=['TEST_ONLY judge'])
        raise AssertionError('Unexpected schema')


@pytest.fixture
def fake():
    return FakeModel()


@pytest.fixture
def client(tmp_path, monkeypatch, fake):
    monkeypatch.setenv('FOUNDEROS_DB', str(tmp_path / 'test.sqlite3'))
    monkeypatch.setattr(main, 'LLM', fake)
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def no_fetch(monkeypatch):
    async def unverified(url, excerpt):
        return 'UNVERIFIED', 'NOT_CHECKED', None, 'Retrieval not performed (test)'
    monkeypatch.setattr(main, 'verify_excerpt', unverified)


@pytest.fixture
def fetch_ok(monkeypatch):
    async def matched(url, excerpt):
        return 'URL_ACCESSIBLE', 'EXCERPT_MATCHED', '2026-11-16T16:00:00+00:00', 'Excerpt found (test)'
    monkeypatch.setattr(main, 'verify_excerpt', matched)


def make_project(client, idea='An AI planner for students who struggle with deadlines', **fields):
    # v0.8: a model-suggested market is never promoted to a confirmed field, so tests state the market as the founder would.
    fields.setdefault('target_market', 'Cairo, Egypt')
    r = client.post('/api/projects', json={'idea': idea, **fields})
    assert r.status_code == 201, r.text
    d = r.json()
    return d['project_id'], {'X-Project-Token': d['access_token']}


def refine(client, pid, h):
    r = client.post(f'/api/projects/{pid}/refine', headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def run(client, pid, h, phase):
    r = client.post(f'/api/projects/{pid}/phases/{phase}/run', headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def decide(client, pid, h, phase, run_json, decision, **extra):
    body = {'run_id': run_json['run_id'], 'report_hash': run_json['report_hash'], 'brief_version': run_json['brief_version'],
            'decision': decision, **extra}
    return client.post(f'/api/projects/{pid}/phases/{phase}/decision', headers=h, json=body)


def approved_discovery(client, pid, h):
    refine(client, pid, h)
    d = run(client, pid, h, 'discover')
    # With zero evidence the D09 gate says REPEAT (PDF p.2); continuing is a recorded founder override, research-only.
    r = decide(client, pid, h, 'discover', d, 'APPROVE', acknowledge_risk=True, feedback='TEST_ONLY: proceed to design a demand test')
    assert r.status_code == 200, r.text
    return d


def locked_experiment(client, pid, h, critical=True, pivot=None, min_sample=10, success=30, adverse=10):
    draft = client.post(f'/api/projects/{pid}/experiments', headers=h, json={
        'hypothesis': 'University students will opt in to a consented waitlist after a plain description',
        'claim_id': 'C-DEM', 'dimension': 'demand', 'target_segment': 'Cairo university students',
        'metric': 'Share of people shown the description who voluntarily leave an email',
        'success_threshold_pct': success, 'adverse_threshold_pct': adverse, 'min_sample': min_sample, 'critical': critical,
        'pivot_alternative': pivot, 'consent_method': 'Explain who I am and why I ask; opt-in only',
        'founder_actions': 'Ask 15 classmates in person; record yes/no honestly', 'cost_estimate': '0 EGP',
        'threshold_origin': 'TEAM_ASSUMPTION', 'time_window_days': 7})
    assert draft.status_code == 201, draft.text
    d = draft.json()
    lock = client.post(f'/api/projects/{pid}/experiments/{d["experiment_id"]}/lock', headers=h,
                       json={'version': d['version'], 'criteria_hash': d['criteria_hash'],
                             'confirm': 'I_PREREGISTER_THESE_CRITERIA_BEFORE_COLLECTING_RESULTS'})
    assert lock.status_code == 200, lock.text
    return lock.json()


@pytest.fixture
def project(client):
    return make_project(client)

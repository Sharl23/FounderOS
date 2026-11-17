"""Adaptive, evidence-honest next-experiment selection: no fabricated business outcomes."""
from app.founder_strategy import propose
from app.decision import risk_register, evaluate_validation
from app.criteria import experiment_design_check


def brief(**kw):
    return {'problem': 'Students miss assignment deadlines',
            'target_customers': 'First year university students aged 18-21',
            'target_market': 'Cairo, Egypt', 'budget': '1000 EGP',
            'timeline': '6 weeks', 'current_workaround': 'Google Calendar',
            'idea_summary': 'Digital study planner', **kw}


def suggestion(data, counted=None, experiments=None):
    register = risk_register(data, None, None, counted or [])
    return propose(data, None, register, experiments or [])


def _e(id, claim_id, dimension, kind='CUSTOMER_BEHAVIOR', direction='SUPPORTS'):
    return {'id': id, 'kind': kind, 'claim_id': claim_id, 'dimension': dimension, 'direction': direction}


def test_no_workaround_targets_problem_not_pitch():
    x = suggestion(brief(current_workaround=None))
    assert x['claim_id'] == 'C-PROB'
    assert 'No current workaround' in x['risk_ranking_note']
    assert 'BEFORE mentioning the solution' in x['founder_actions'][1]
    assert x['evidence_basis']['counted_evidence_ids'] == []
    assert 'ASSUMPTIONS' in x['suggested_criteria']['label']


def test_problem_known_demand_untested_prefers_actual_opt_in():
    x = suggestion(brief())
    assert x['claim_id'] == 'C-DEM'
    assert 'opt in' in x['metric']
    assert 'No accepted evidence IDs' in x['risk_ranking_note']
    assert 'Cairo, Egypt' in x['founder_actions'][0]
    assert 'First year' in x['target_segment']
    assert x['external_actions'].startswith('DRAFT ONLY')
    # v0.10: with 6 weeks available the engine picks the stronger 14-day concierge test (repeat use), so the window follows it.
    assert x['method_chosen']['id'] == 'concierge' and x['constraint_fit']['pilot_days'] == 14
    assert experiment_design_check({
        'metric': x['metric'], 'min_sample': x['suggested_criteria']['min_sample'],
        'success_threshold_pct': x['suggested_criteria']['success_threshold_pct'],
        'adverse_threshold_pct': x['suggested_criteria']['adverse_threshold_pct'],
        'cost_estimate': '0', 'consent_method': x['consent_method'],
        'founder_actions': ' '.join(x['founder_actions']), 'simulated': False,
    }, brief())['status'] == 'PASS'


def test_same_idea_new_evidence_switches_to_competition_then_price():
    b = brief()
    first = _e('proof-of-demand', 'C-DEM', 'demand')
    x = suggestion(b, [first])
    assert x['claim_id'] == 'C-COMP'
    assert 'switch' in x['metric']
    comp = _e('proof-of-switch', 'C-COMP', 'competition')
    y = suggestion(b, [first, comp])
    assert y['claim_id'] == 'C-VIAB'
    assert 'price' in y['founder_actions'][1]


def test_more_evidence_is_cited_not_invented():
    x = suggestion(brief(), [_e('abc', 'C-DEM', 'demand', direction='CONTRADICTS')])
    assert x['claim_id'] == 'C-DEM'
    assert x['evidence_basis']['status'] == 'REFUTED'
    assert x['evidence_basis']['counted_evidence_ids'] == ['abc']
    assert 'abc' in x['risk_ranking_note']
    assert 'https://' not in str(x)


def test_restrictive_time_and_privacy_adjust_plan_without_claiming_certainty():
    b = brief(timeline='3 days', budget='0 EGP', values='No email; strong privacy, no personal data', constraints='No paid tools')
    x = suggestion(b)
    assert x['constraint_fit']['pilot_days'] == 3
    assert x['constraint_fit']['privacy_preserving_metric']
    assert 'no identity captured' in x['metric']
    assert x['suggested_criteria']['time_window_days'] == 3
    assert 'INCONCLUSIVE' in x['constraint_fit']['note']
    assert '0 paid-tool cost' in x['cost_estimate']


def test_unknown_time_is_unknown_not_a_promise():
    x = suggestion(brief(timeline=None))
    assert x['constraint_fit']['available_days_parsed'] is None
    assert 'not parseable' in x['constraint_fit']['note']


def test_minors_only_recruits_adults():
    x = suggestion(brief(target_customers='K-12 students aged 12', current_workaround=None))
    assert 'Consenting adult parents/guardians/teachers' in x['target_segment']
    assert x['constraint_fit']['adult_representatives_only']
    assert 'adult representatives' in x['founder_actions'][0]


def test_locked_experiment_never_overwritten():
    x = suggestion(brief(), experiments=[{'id': 'locked-1', 'version': 2, 'status': 'LOCKED',
                                           'result_evidence_id': None,
                                           'payload': {'hypothesis': 'customers opt in', 'min_sample': 13}}])
    assert x['kind'] == 'RUN_LOCKED_EXPERIMENT'
    assert x['criteria']['min_sample'] == 13


def test_safety_block_keeps_passport_without_experiment():
    # Risk evaluation must not invite further experiment on a prohibited venture.
    b = brief()
    out = evaluate_validation(brief=b, brief_version=1, safety={'status': 'BLOCK'},
                              discovery=None, discovery_version=None, evidence=[], experiments=[])
    assert out['verdict'] == 'BLOCK_DO_NOT_LAUNCH'
    assert out['next_experiment']['kind'] == 'NO_EXPERIMENT_SAFETY_BLOCK'
    assert not out['permissions']['external_actions']


def test_exp_suggestion_api_ignores_unverified_secondary_claims(client, project):
    # No external network call: the API must use the same verified evidence filter as the passport.
    pid, h = project
    assert client.post(f'/api/projects/{pid}/refine', headers=h).status_code == 200
    response = client.get(f'/api/projects/{pid}/experiments/suggest', headers=h)
    assert response.status_code == 200, response.text
    assert response.json()['kind'] == 'PROPOSED_EXPERIMENT_NEEDS_FOUNDER_APPROVAL'
    assert response.json()['evidence_basis']['counted_evidence_ids'] == []

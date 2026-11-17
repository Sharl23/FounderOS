"""v0.10 decision quality: different founders get different, justified decisions. All fixtures are TEST_ONLY."""
import importlib.util
from pathlib import Path

from app.agents import product_architect as pa, website_builder as wb, qa
from app.agents.commercial import CommercialInputs, plan
from app.agents.operations import recommend
from app.decision import evaluate_validation
from app.founder_strategy import parse_budget, choose_method

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('founder_cases', ROOT / 'evals' / 'founder_cases.py')
cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cases)
SAFE = {'status': 'ALLOW_DISCOVERY', 'rules': [], 'counts': {}}


def test_every_evaluation_case_meets_its_written_expectations():
    rows = cases.run_all()
    assert [r['fails'] for r in rows] == [[] for _ in rows], [(r['key'], r['fails']) for r in rows]


def test_evaluation_cases_take_distinct_decision_paths():
    rows = cases.run_all()
    paths = {(r['verdict'], r.get('claim'), r.get('method'), r.get('archetype')) for r in rows}
    assert len(paths) == len(rows)


def test_weak_sources_cannot_raise_the_verdict():
    """Duplicates, unreachable URLs, irrelevant rows, example.com, statements and simulations never create demand."""
    weak = next(c for c in cases.CASES if c['key'] == 'weak')
    out = evaluate_validation(brief=weak['brief'], brief_version=1, safety=SAFE, discovery=None, discovery_version=None, evidence=weak['evidence'], experiments=[])
    base = evaluate_validation(brief=weak['brief'], brief_version=1, safety=SAFE, discovery=None, discovery_version=None, evidence=[], experiments=[])
    assert out['verdict'] == base['verdict'] == 'NEEDS_EVIDENCE'
    assert out['matrix']['demand']['status'] == 'UNKNOWN'
    assert out['next_decision']['confidence']['level'] == 'NONE'
    reasons = ' '.join(x['reason'] for x in out['excluded_evidence'])
    for word in ('DUPLICATE', 'could not be retrieved', 'IRRELEVANT', 'Reserved documentation domain', 'SIMULATED'):
        assert word in reasons


def test_budget_parsing_and_paid_methods():
    assert parse_budget('1000 EGP')['limited'] and parse_budget('')['limited'] and parse_budget('no budget')['amount'] == 0
    assert not parse_budget('$500')['limited'] and parse_budget('$500')['currency'] == 'USD'
    assert parse_budget('2k EGP')['amount'] == 2000
    rich = choose_method('C-DEM', parse_budget('$500'), {'coding': True, 'people': False, 'stated': True}, 7, 'default')
    poor = choose_method('C-DEM', parse_budget('300 EGP'), {'coding': True, 'people': False, 'stated': True}, 7, 'default')
    assert rich[0]['id'] == poor[0]['id'] == 'landing_page_opt_in'   # free method preferred when evidence is equally strong
    ad_rich = next(a for a in rich[1] if 'paid-ad' in a['option'])
    ad_poor = next(a for a in poor[1] if 'paid-ad' in a['option'])
    assert 'costs money for evidence no stronger' in ad_rich['not_chosen_because'] and 'below the TEAM_ASSUMPTION floor' in ad_poor['not_chosen_because']


def test_skills_and_time_change_the_method():
    b = parse_budget('1000 EGP')
    assert choose_method('C-DEM', b, {'coding': False, 'people': True, 'stated': True}, 7, 'x')[0]['id'] == 'neutral_opt_in'
    assert choose_method('C-DEM', b, {'coding': True, 'people': False, 'stated': True}, 7, 'x')[0]['id'] == 'landing_page_opt_in'
    assert choose_method('C-DEM', b, {'coding': True, 'people': False, 'stated': True}, 3, 'x')[0]['id'] == 'neutral_opt_in'   # 5-day page does not fit 3 days
    assert choose_method('C-DEM', b, {'coding': False, 'people': False, 'stated': True}, 42, 'x')[0]['id'] == 'concierge'
    assert choose_method('C-COMP', b, {'coding': False, 'people': False, 'stated': True}, 3, 'x')[0]['id'] == 'side_by_side_task'
    real = choose_method('C-VIAB', parse_budget('$5000'), {'coding': True, 'people': True, 'stated': True}, 60, 'x')
    assert real[0]['id'] != 'real_deposit' and any('never collects real money' in a['not_chosen_because'] for a in real[1])


def test_next_decision_has_all_fields_and_no_probability():
    out = cases.run_case(cases.CASES[0])
    full = evaluate_validation(brief=cases.CASES[0]['brief'], brief_version=1, safety=SAFE, discovery=None, discovery_version=None, evidence=[], experiments=[])
    nd = full['next_decision']
    for k in ('decision', 'why', 'evidence_ids', 'unknowns', 'alternatives', 'trade_off', 'founder_fit', 'next_action',
              'success_criterion', 'what_would_change_it', 'needs_founder_approval', 'confidence', 'limitations', 'cost_and_time'):
        assert k in nd, k
    assert 'not a probability' in nd['confidence']['meaning'] and '%' not in nd['confidence']['level']
    assert 'STARTING ASSUMPTION' in nd['success_criterion'] and nd['cost_and_time']['cost'].startswith('ESTIMATE')
    assert any('Build the full product now' in a['option'] for a in nd['alternatives'])
    assert out['verdict'] == 'NEEDS_EVIDENCE'


def test_three_ventures_three_working_prototypes():
    seen = {}
    for c in cases.CASES[:3]:
        sp = pa.spec(c['brief'], None, 'NEEDS_EVIDENCE', 'DEMO_ONLY')
        files = wb.build(sp, 3)
        assert qa.check(sp, files)['status'] == 'PASS'
        assert 'DEMO-ONLY PROTOTYPE' in files['index.html'] and 'not validated' in files['index.html']
        seen[sp['archetype']] = files
    assert set(seen) == {'planner', 'tracker', 'booking'}
    assert 'id="add-client"' in seen['tracker']['index.html'] and 'id="slots"' in seen['booking']['index.html']
    assert 'No confirmation message was sent' in seen['booking']['app.js']


def test_hostile_brief_text_is_escaped_in_new_prototypes():
    b = {'original_idea_text': 'TEST_ONLY booking app for barbers <script>alert(1)</script> slots', 'target_customers': '<img src=x onerror=alert(1)>'}
    sp = pa.spec(b, None, 'NEEDS_EVIDENCE', 'DEMO_ONLY', {'name': '<script>x</script>'})
    files = wb.build(sp, 1)
    assert sp['archetype'] == 'booking' and '<script>x' not in files['index.html'] and qa.check(sp, files)['status'] == 'PASS'


def test_commercial_decisions_follow_the_numbers():
    loss = plan(CommercialInputs(price=1, variable_cost_per_sale=0.9), {'budget': '$100'})['decision']
    assert loss['top_issue'] == 'NEGATIVE_CONTRIBUTION' and loss['recommendation'].startswith('DO_NOT_ADOPT')
    assert loss['minimum_viable_price'] == 1.24          # (0.9 + 0.30) / (1 - 0.029) = 1.2358 -> 1.24
    far = plan(CommercialInputs(price=10, fixed_costs_monthly=1000, sales_per_month_high=30, evidence_note='TEST_ONLY'), {'budget': '$5000'})['decision']
    assert far['top_issue'] == 'BREAK_EVEN_ABOVE_ALL_SCENARIOS'
    over = plan(CommercialInputs(currency='EGP', price=100, build_cost_one_off=900, fixed_costs_monthly=100, evidence_note='TEST_ONLY'), {'budget': '1000 EGP'})['decision']
    assert over['top_issue'] == 'OVER_BUDGET' and '1200.0 EGP' in over['findings'][0]['reasoning']
    other = plan(CommercialInputs(currency='USD', price=10, evidence_note='TEST_ONLY'), {'budget': '1000 EGP'})['decision']
    assert any(f['code'] == 'BUDGET_NOT_COMPARABLE' for f in other['findings'])   # never converts currencies
    sub = plan(CommercialInputs(price=10, billing='monthly', monthly_churn_pct=10, evidence_note='TEST_ONLY'), {'budget': '$500'})['decision']
    churn = next(f for f in sub['findings'] if f['code'] == 'CHURN_SENSITIVITY')
    assert set(churn['table']) == {'5%', '10%', '20%'} and churn['table']['20%']['avg_months'] == 5.0
    unsupported = plan(CommercialInputs(price=10), {'budget': '$500'})['decision']
    assert unsupported['top_issue'] == 'PRICE_UNSUPPORTED' and 'evidence for the price' in unsupported['missing_inputs']
    assert 'Not a profit forecast' in unsupported['labels']


def test_operate_says_insufficient_evidence_and_names_the_bottleneck():
    few = {'metrics': {'orders_paid': 2, 'checkouts_started': 3, 'refund_rate_pct': 50.0, 'checkout_to_paid_pct': 66.7, 'access_usage_pct': 50.0}}
    r = recommend(few, [], [], [], [])
    assert r['evidence_status'] == 'INSUFFICIENT EVIDENCE' and r['loops_back_to_phase'] == 5 and r['data_sources']['real_observed_sales'] == 0
    many = {'metrics': {'orders_paid': 12, 'checkouts_started': 70, 'refund_rate_pct': 5.0, 'checkout_to_paid_pct': 17.1, 'access_usage_pct': 80.0}}
    r = recommend(many, [], [], [], [])
    assert r['recommendation'] == 'ITERATE' and r['loops_back_to_phase'] == 4 and 'price' in r['next_iteration']
    issue = recommend(many, [], [], [{'status': 'OPEN', 'severity': 'HIGH', 'title': 'Login broken'}], [])
    assert issue['loops_back_to_phase'] == 3 and 'Login broken' in issue['next_iteration']
    failed = recommend(many, [], [], [], [{'reading': 'CLEAR_MISS', 'critical': True}])
    assert failed['recommendation'] in ('STOP', 'PIVOT') and failed['loops_back_to_phase'] == 1


def test_research_is_prioritised_by_the_weakest_critical_claim():
    from app import research
    from app.decision import risk_register
    b = cases.CASES[2]['brief']    # booking: problem, demand and switching supported by behaviour, price untested
    reg = risk_register(b, None, None, cases.CASES[2]['evidence'])
    p = research.plan(b, {'country': 'Egypt'}, reg)
    assert p['priority_order'][0] in ('FEASIBILITY', 'VIABILITY') and p['priority_order'].index('VIABILITY') < p['priority_order'].index('PROBLEM')
    nothing = research.plan(cases.CASES[0]['brief'], {'country': 'Egypt'}, risk_register(cases.CASES[0]['brief'], None, None, []))
    assert nothing['priority_order'][0] in ('PROBLEM', 'MARKET', 'FEASIBILITY', 'VIABILITY')
    market = next(x for x in p['buckets'] if x['id'] == 'MARKET')
    assert 'cannot show demand' in market['limit']
    assert next(x for x in p['buckets'] if x['id'] == 'COMPETITORS')['status'] == 'DISCOVERY_NOT_AVAILABLE'   # never claims "no competitors"

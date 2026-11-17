"""Founder decision-quality evaluation: six founders, one pipeline, explicit expectations.

Every case runs the real decision code (risk register -> verdict -> next decision -> product spec -> prototype QA ->
commercial decision). No model and no network are used, so the results are reproducible. All founders, evidence
rows and results are TEST_ONLY synthetic fixtures: they test FounderOS's reasoning, they are not market data.

    python evals/founder_cases.py          # prints a table and writes evals/founder_eval_results.md

tests/test_founder_eval.py asserts the same expectations, so a regression fails the test suite.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.decision import evaluate_validation  # noqa: E402
from app.agents import product_architect, website_builder, qa, commercial  # noqa: E402
from app.safety import screen  # noqa: E402

SAFE = {'status': 'ALLOW_DISCOVERY', 'rules': [], 'counts': {}}


def behaviour(i, claim, dim):
    return {'id': f'TEST_ONLY-b{i}', 'kind': 'CUSTOMER_BEHAVIOR', 'claim_id': claim, 'dimension': dim, 'direction': 'SUPPORTS',
            'consent_confirmed': 1, 'claim': f'TEST_ONLY observed behaviour for {claim}'}


def background(i, dim='desirability', **kw):
    return {'id': f'TEST_ONLY-s{i}', 'kind': 'SECONDARY_BACKGROUND', 'dimension': dim, 'direction': 'SUPPORTS', 'url_status': 'URL_ACCESSIBLE',
            'excerpt_status': 'EXCERPT_MATCHED', 'relevance': 'CLAIM_RELEVANT', 'claim': 'TEST_ONLY background claim', **kw}


CASES = [
    {'key': 'studyflow', 'title': 'StudyFlow: study planner, Cairo students',
     'brief': {'original_idea_text': 'TEST_ONLY: a digital study planner that turns university assignments and deadlines into a weekly study schedule',
               'problem': 'Students miss assignment deadlines', 'target_customers': 'First-year university students in Cairo',
               'target_market': 'Cairo, Egypt', 'current_workaround': 'Google Calendar and paper lists', 'skills': 'Python and basic web development',
               'budget': '1000 EGP', 'timeline': '6 weeks', 'idea_summary': 'TEST_ONLY study planner'},
     'evidence': [], 'plan': dict(currency='EGP', billing='monthly', price=50, variable_cost_per_sale=2, payment_fee_fixed=3, fixed_costs_monthly=100, build_cost_one_off=0),
     'expect': {'verdict': 'NEEDS_EVIDENCE', 'claim': 'C-DEM', 'method': 'concierge', 'archetype': 'planner', 'confidence': 'NONE',
                'rejected_contains': 'Small paid-ad smoke test', 'commercial_top': 'PRICE_UNSUPPORTED'}},
    {'key': 'freelancer', 'title': 'Freelancer client tracker, one week, no coding',
     'brief': {'original_idea_text': 'TEST_ONLY: a client tracker for independent freelancers to manage clients, projects, tasks and delivery dates',
               'problem': 'Freelancers lose track of client deliverables across chats', 'target_customers': 'Independent freelance graphic designers in Cairo',
               'target_market': 'Cairo, Egypt', 'current_workaround': 'Spreadsheets and WhatsApp chats', 'skills': 'graphic design and client communication',
               'budget': '$50', 'timeline': '1 week', 'idea_summary': 'TEST_ONLY freelancer tracker'},
     'evidence': [behaviour(1, 'C-PROB', 'desirability'), behaviour(2, 'C-DEM', 'demand')],
     'plan': dict(currency='USD', billing='monthly', price=6, variable_cost_per_sale=0.5, fixed_costs_monthly=15, build_cost_one_off=0, monthly_churn_pct=12),
     'expect': {'verdict': 'CONTINUE_TESTING', 'claim': 'C-COMP', 'method': 'switching_trial', 'archetype': 'tracker', 'confidence': 'LOW',
                'rejected_contains': 'Side-by-side', 'commercial_top': 'PRICE_UNSUPPORTED'}},
    {'key': 'booking', 'title': 'Barber booking app, strong demand, no engineering skill',
     'brief': {'original_idea_text': 'TEST_ONLY: an appointment booking app for independent barbers in Giza so customers can book free slots',
               'problem': 'Barbers lose bookings over phone calls', 'target_customers': 'Independent barbers in Giza',
               'target_market': 'Giza, Egypt', 'current_workaround': 'Phone calls and a paper notebook', 'skills': 'customer service and sales',
               'budget': '3000 EGP', 'timeline': '4 weeks', 'idea_summary': 'TEST_ONLY booking app'},
     'evidence': [behaviour(1, 'C-PROB', 'desirability'), behaviour(2, 'C-DEM', 'demand'), behaviour(3, 'C-COMP', 'competition')],
     'plan': dict(currency='EGP', billing='monthly', price=150, variable_cost_per_sale=5, payment_fee_fixed=3, fixed_costs_monthly=400, build_cost_one_off=2000,
                  evidence_note='TEST_ONLY: price taken from a locked commitment test'),
     'expect': {'verdict': 'CONTINUE_TESTING', 'claim': 'C-VIAB', 'method': 'price_split', 'archetype': 'booking', 'confidence': 'MODERATE',
                'fit_contains': 'No web/coding skill', 'commercial_top': 'OVER_BUDGET'}},
    {'key': 'weak', 'title': 'Weak evidence: polished pitch, background sources only',
     'brief': {'original_idea_text': 'TEST_ONLY: a revolutionary AI platform that everyone will love for organising university life',
               'problem': 'Students are disorganised', 'target_customers': 'University students', 'target_market': 'Egypt',
               'current_workaround': 'Various apps', 'skills': '', 'budget': '', 'timeline': '', 'idea_summary': 'TEST_ONLY huge market, proven demand'},
     'evidence': [background(1), background(2, duplicate_of='TEST_ONLY-s1'), background(3, url_status='URL_UNREACHABLE'),
                  background(4, relevance='IRRELEVANT'), background(5, source_url='https://example.com/report'),
                  {'id': 'TEST_ONLY-q1', 'kind': 'CUSTOMER_STATEMENT', 'claim_id': 'C-DEM', 'dimension': 'demand', 'direction': 'SUPPORTS', 'consent_confirmed': 1, 'claim': 'TEST_ONLY: a student said they would use it'},
                  {'id': 'TEST_ONLY-sim', 'kind': 'SIMULATED_RESULT', 'dimension': 'demand', 'direction': 'SUPPORTS', 'claim': 'TEST_ONLY simulated sale'}],
     'plan': None,
     'expect': {'verdict': 'NEEDS_EVIDENCE', 'confidence': 'NONE', 'excluded_at_least': 5}},
    {'key': 'adverse', 'title': 'Adverse result: critical locked test failed',
     'brief': {'original_idea_text': 'TEST_ONLY: a paid exam-week reminder app for university students', 'problem': 'Students forget to rest during exams',
               'target_customers': 'University students in Cairo', 'target_market': 'Cairo, Egypt', 'current_workaround': 'Phone alarms',
               'skills': 'Python', 'budget': '500 EGP', 'timeline': '3 weeks'},
     'evidence': [{'id': 'TEST_ONLY-r1', 'kind': 'PRE_REGISTERED_EXPERIMENT_RESULT', 'experiment_id': 'TEST_ONLY-x1', 'experiment_version': 1,
                   'outcome': 'FAIL', 'adverse': True, 'rate_pct': 0.0, 'sample_size': 20, 'positives': 0, 'dimension': 'demand', 'claim_id': 'C-DEM', 'claim': 'TEST_ONLY locked pre-order test'}],
     'experiments': [{'id': 'TEST_ONLY-x1', 'version': 1, 'status': 'LOCKED', 'criteria_hash': 'TEST_ONLY', 'locked_at': '2026-11-10T00:00:00Z',
                      'result_evidence_id': 'TEST_ONLY-r1',
                      'payload': {'critical': True, 'claim_id': 'C-DEM', 'success_threshold_pct': 30, 'adverse_threshold_pct': 10, 'min_sample': 10,
                                  'pivot_alternative': None, 'threshold_origin': 'TEAM_ASSUMPTION'}}],
     'plan': None,
     'expect': {'verdict': 'STOP_DO_NOT_LAUNCH', 'next_kind': 'REVIEW_CRITICAL_RESULT_BEFORE_MORE_TESTS'}},
    {'key': 'safety', 'title': 'Safety hard stop: crypto signals with guaranteed returns',
     'brief': {'original_idea_text': 'TEST_ONLY: an app that sends students crypto trading signals with guaranteed monthly returns',
               'target_customers': 'University students', 'target_market': 'Cairo, Egypt', 'budget': '1000 EGP', 'timeline': '2 weeks'},
     'evidence': [behaviour(1, 'C-DEM', 'demand')], 'plan': None, 'safety_from_screen': True,
     'expect': {'verdict': 'BLOCK_DO_NOT_LAUNCH', 'next_kind': 'NO_EXPERIMENT_SAFETY_BLOCK', 'confidence': 'NOT_APPLICABLE'}},
]


def run_case(c: dict) -> dict:
    safety = screen(c['brief']['original_idea_text']) if c.get('safety_from_screen') else SAFE
    out = evaluate_validation(brief=c['brief'], brief_version=1, safety=safety, discovery=None, discovery_version=None,
                              evidence=c['evidence'], experiments=c.get('experiments', []))
    nd, nxt = out['next_decision'], out['next_experiment']
    r = {'key': c['key'], 'title': c['title'], 'safety': safety.get('status'), 'verdict': out['verdict'], 'decision': nd['decision'],
         'claim': nxt.get('claim_id'), 'method': (nxt.get('method_chosen') or {}).get('id'), 'next_kind': nxt.get('kind'),
         'confidence': nd['confidence']['level'], 'excluded': len(out['excluded_evidence']),
         'rejected': [a['option'] for a in nd['alternatives']], 'fit': nd['founder_fit'], 'success': nd['success_criterion'],
         'evidence_ids': nd['evidence_ids']}
    if out['verdict'] in ('NEEDS_EVIDENCE', 'CONTINUE_TESTING') and safety.get('status') != 'BLOCK':
        sp = product_architect.spec(c['brief'], None, out['verdict'], 'DEMO_ONLY')
        files = website_builder.build(sp, 1)
        r.update({'archetype': sp['archetype'], 'prototype': sp['name'], 'qa': qa.check(sp, files)['status'], 'status_label': sp['status_label'],
                  'data_fields': sorted({k for rec in (website_builder.demo_records(sp, 1) if isinstance(website_builder.demo_records(sp, 1), list) else
                                                       [website_builder.demo_records(sp, 1)]) for k in (rec.keys() if isinstance(rec, dict) else [])})})
    if c.get('plan'):
        d = commercial.plan(commercial.CommercialInputs(**c['plan']), c['brief'])['decision']
        r.update({'commercial_recommendation': d['recommendation'], 'commercial_top': d['top_issue'],
                  'commercial_findings': [f['code'] for f in d['findings']]})
    return r


def check(c: dict, r: dict) -> list[str]:
    e, fails = c['expect'], []
    for k in ('verdict', 'claim', 'method', 'archetype', 'confidence', 'next_kind', 'commercial_top'):
        if k in e and r.get(k) != e[k]:
            fails.append(f'{k}: expected {e[k]!r}, got {r.get(k)!r}')
    if 'rejected_contains' in e and not any(e['rejected_contains'] in x for x in r['rejected']):
        fails.append(f'alternatives should list {e["rejected_contains"]!r}')
    if 'fit_contains' in e and not any(e['fit_contains'] in x for x in r['fit']):
        fails.append(f'founder fit should mention {e["fit_contains"]!r}')
    if 'excluded_at_least' in e and r['excluded'] < e['excluded_at_least']:
        fails.append(f'only {r["excluded"]} evidence rows excluded')
    if r['verdict'] in ('NEEDS_EVIDENCE', 'CONTINUE_TESTING') and r.get('qa') not in (None, 'PASS'):
        fails.append('prototype QA failed')
    if r['verdict'] not in ('CONTINUE_TESTING',) and 'VALIDATED' in json.dumps(r).upper().replace('NOT VALIDATED', ''):
        fails.append('claims validation')
    return fails


def run_all() -> list[dict]:
    rows = []
    for c in CASES:
        r = run_case(c)
        r['fails'] = check(c, r)
        rows.append(r)
    return rows


def report(rows: list[dict]) -> str:
    distinct = {(r['verdict'], r.get('claim'), r.get('method'), r.get('archetype')) for r in rows}
    lines = ['# Founder decision evaluation (generated by `python evals/founder_cases.py`)', '',
             'Six TEST_ONLY founders run through the same deterministic decision code. No model, no network: reproducible.',
             'Expectations are written in `evals/founder_cases.py` before running; `tests/test_founder_eval.py` enforces them.', '',
             f'Distinct decision paths: **{len(distinct)} of {len(rows)}** founders. Expectations met: **{sum(not r["fails"] for r in rows)} of {len(rows)}**.', '',
             '| Founder | Verdict (code) | Riskiest claim | Method chosen | Prototype | Commercial | Confidence | Result |', '|---|---|---|---|---|---|---|---|']
    for r in rows:
        lines.append(f'| {r["title"]} | {r["verdict"]} | {r.get("claim") or "-"} | {r.get("method") or r.get("next_kind") or "-"} | '
                     f'{(r.get("prototype") or "-") + (" (" + r["archetype"] + ")" if r.get("archetype") else "")} | {r.get("commercial_recommendation") or "-"} | '
                     f'{r["confidence"]} | {"PASS" if not r["fails"] else "FAIL: " + "; ".join(r["fails"])} |')
    lines += ['', '## Per founder', '']
    for r in rows:
        lines += [f'### {r["title"]}', '', f'- Decision: {r["decision"]}', f'- Evidence counted: {", ".join(r["evidence_ids"]) or "none"}; excluded rows: {r["excluded"]}']
        if r['fit']:
            lines.append('- Founder fit: ' + ' '.join(r['fit']))
        if r['rejected']:
            lines.append('- Options rejected: ' + '; '.join(r['rejected']))
        if r['success']:
            lines.append('- Success criterion: ' + r['success'])
        if r.get('commercial_findings'):
            lines.append('- Commercial findings: ' + ', '.join(r['commercial_findings']))
        lines.append('')
    lines += ['## Rubric and limits', '',
              '- Checked automatically: verdict, riskiest claim, chosen method, rejected options, founder-fit reasons, prototype type and QA, commercial finding, '
              'exclusion of weak evidence, no validation claim, safety block.',
              '- Not checked automatically: the quality of wording, or whether a real founder finds the advice useful. That needs real founders.',
              '- Fixtures are synthetic (TEST_ONLY). Passing shows the logic reacts to different inputs as specified; it is not evidence about any market.']
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    rows = run_all()
    text = report(rows)
    (ROOT / 'evals' / 'founder_eval_results.md').write_text(text, encoding='utf-8')
    print(text)
    sys.exit(1 if any(r['fails'] for r in rows) else 0)

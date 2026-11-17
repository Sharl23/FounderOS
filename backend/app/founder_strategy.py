"""Founder-specific next-experiment planning; deterministic and evidence-bounded.

This module NEVER changes a gate verdict, invents demand, sends messages, or locks a
criterion. It converts the founder's recorded constraints and risk-register state
into a reviewable proposal. Numbers are clearly labelled as starting assumptions.
"""
from __future__ import annotations

import re


CLAIMS = ('C-PROB', 'C-DEM', 'C-COMP', 'C-VIAB')


def _text(value, fallback='UNKNOWN', limit=220):
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value).strip()[:limit] if value and str(value).strip() else fallback


def _available_days(raw: str) -> int | None:
    """Read a stated duration, not a promise about how quickly recruitment works."""
    m = re.search(r'\b(\d{1,3})\s*(day|week|month)s?\b', raw.lower())
    if not m:
        return None
    return int(m[1]) * {'day': 1, 'week': 7, 'month': 30}[m[2]]


def _adult_segment(segment: str, brief: dict) -> tuple[str, bool]:
    from .criteria import involves_minors
    if involves_minors(brief, {'target_segment': segment}):
        return f'Consenting adult parents/guardians/teachers relevant to: {segment}'[:300], True
    return segment, False


# ---------------------------------------------------------------- founder constraints
# Budget floors below which a paid method is not proposed. TEAM_ASSUMPTION per currency, not a benchmark or an
# exchange-rate claim: they only stop the engine from suggesting paid tests to a founder with very little money.
PAID_TEST_FLOOR = {'EGP': 5000, 'USD': 100, 'EUR': 100, 'GBP': 100, 'SAR': 400, 'AED': 400}
CODING = r'\b(python|javascript|js|typescript|html|css|web|front-?end|back-?end|full-?stack|developer|programm\w*|cod(e|ing)|react|django|flask|no-?code|bubble|webflow|wordpress|software)\b'
PEOPLE = r'\b(sales|selling|market\w*|interview\w*|community|teach\w*|tutor\w*|customer service|network\w*|events?)\b'


def parse_budget(raw: str) -> dict:
    """Read the founder's stated budget. Unknown stays unknown; it is treated as 'no spend' for planning."""
    t = (raw or '').lower().replace(',', '')
    if not t.strip() or t.strip().upper().startswith('UNKNOWN'):
        return {'amount': None, 'currency': None, 'limited': True, 'why': 'Budget not stated: the plan assumes no money is spent.'}
    if re.search(r'\b(no|zero|nil|without)\s+(budget|money)\b|\bno money\b|\$?\b0\b', t):
        return {'amount': 0, 'currency': None, 'limited': True, 'why': 'Founder stated no budget.'}
    cur = ('EGP' if re.search(r'\b(egp|le|l\.e\.|pounds? egyptian|egyptian pounds?|جنيه)\b', t) else 'USD' if re.search(r'\$|\busd\b|dollars?', t)
           else 'EUR' if re.search(r'€|\beur\b|euros?', t) else 'GBP' if re.search(r'£|\bgbp\b', t) else 'SAR' if re.search(r'\bsar\b|riyal', t)
           else 'AED' if re.search(r'\baed\b|dirham', t) else None)
    m = re.search(r'(\d+(?:\.\d+)?)\s*(k\b|thousand)?', t)
    amount = float(m.group(1)) * (1000 if m and m.group(2) else 1) if m else None
    tight = bool(re.search(r'\b(tight|limited|small|very little|minimal|shoestring)\b', t))
    floor = PAID_TEST_FLOOR.get(cur or '', None)
    limited = tight or amount is None or floor is None or amount < floor
    why = (f'Stated budget {amount:g} {cur or "(currency unknown)"}' if amount is not None else 'Budget amount not parseable') + \
          (f'; below the TEAM_ASSUMPTION floor of {floor} {cur} for any paid test.' if floor and amount is not None and amount < floor else
           '; currency unknown, so paid tests are not proposed.' if floor is None else '; described as limited.' if tight else '; a small paid test is affordable but not required.')
    return {'amount': amount, 'currency': cur, 'limited': limited, 'why': why}


def parse_skills(raw: str) -> dict:
    t = (raw or '').lower()
    return {'stated': bool(t.strip()) and not t.strip().upper().startswith('UNKNOWN'), 'coding': bool(re.search(CODING, t)), 'people': bool(re.search(PEOPLE, t))}


# One entry per method the engine can recommend for a claim. 'default' keeps the long-standing wording.
# cost: FREE (no spend) or PAID; days: ASSUMED minimum running time; strength: 3 = repeated real use, 2 = one observed action,
# 1 = recalled behaviour. needs: 'coding' (founder builds a page) or None. reach: 1 own contacts, 2 a shared page, 3 paid audience.
METHODS = {
    'C-PROB': [
        {'id': 'last_instance_interviews', 'default': True, 'cost': 'FREE', 'days': 3, 'strength': 1, 'needs': None,
         'label': 'Problem interviews about the last real occurrence'},
        {'id': 'workaround_walkthrough', 'cost': 'FREE', 'days': 7, 'strength': 2, 'needs': None,
         'label': 'Workaround walk-through (participant shows the notes, chats or sheets they actually used)',
         'method': 'With permission, ask each participant to show (not describe) how they handled the last occurrence: the chat, sheet, notebook or app they used. Record time spent and what went wrong, BEFORE mentioning the solution.'},
    ],
    'C-DEM': [
        {'id': 'concierge', 'cost': 'FREE', 'days': 14, 'strength': 3, 'needs': None,
         'label': 'Concierge test: deliver the core result by hand to a few people and see if they come back',
         'method': 'Offer to do the core job manually (no product) for 5-8 consenting people from the segment. Count who actually uses the result and who asks for it again the following week; record drop-outs.'},
        {'id': 'landing_page_opt_in', 'cost': 'FREE', 'days': 5, 'strength': 2, 'needs': 'coding', 'reach': 2,
         'label': 'One-page description with an opt-in button that you build yourself',
         'method': 'Build a one-page description with a single opt-in action (no pre-checked boxes, no urgency, no fake numbers). Share it only through channels you have permission to use; count visitors who opt in, including those who leave.'},
        {'id': 'neutral_opt_in', 'default': True, 'cost': 'FREE', 'days': 3, 'strength': 2, 'needs': None,
         'label': 'Neutral description shown in person or by message, with an opt-in'},
        {'id': 'paid_ad_smoke_test', 'cost': 'PAID', 'days': 5, 'strength': 2, 'needs': None, 'reach': 3,
         'label': 'Small paid-ad smoke test',
         'method': 'Run a small, honestly worded ad to a landing page and count opt-ins per visitor. The founder places and pays for the ad; FounderOS never spends money.'},
    ],
    'C-COMP': [
        {'id': 'switching_trial', 'default': True, 'cost': 'FREE', 'days': 7, 'strength': 3, 'needs': None,
         'label': 'Switching trial against the current workaround (uses the DEMO prototype)'},
        {'id': 'side_by_side_task', 'cost': 'FREE', 'days': 2, 'strength': 2, 'needs': None,
         'label': 'Side-by-side task: same task with the current tool and with a paper or demo version',
         'method': 'In one session, ask each participant to do the same real task twice: with the tool they use today and with a clearly labelled demo or paper version. Record time, errors and which one they choose to keep using afterwards.'},
    ],
    'C-VIAB': [
        {'id': 'price_split', 'cost': 'FREE', 'days': 14, 'strength': 3, 'needs': None,
         'label': 'Two-price commitment test across two comparable groups',
         'method': 'Show one ASSUMED price to one group and a higher ASSUMED price to a second, comparable group; ask each for a voluntary, no-payment commitment. Compare commitment rates; do not process payments or claim commitments predict purchases.'},
        {'id': 'price_commitment', 'default': True, 'cost': 'FREE', 'days': 5, 'strength': 2, 'needs': None,
         'label': 'Single-price, no-payment commitment'},
        {'id': 'real_deposit', 'cost': 'PAID', 'days': 7, 'strength': 3, 'needs': 'never',
         'label': 'Refundable real-money deposit',
         'method': 'Not offered: FounderOS never collects money, and a real deposit needs a payment provider and terms reviewed by a professional.'},
    ],
}


def choose_method(cid: str, budget: dict, skills: dict, days: int | None, default_method: str) -> tuple[dict, list[dict]]:
    """Strongest feasible method for this founder; every other option is listed with the reason it was not chosen."""
    window = days if days is not None else 7
    options, chosen = [], None
    for m in METHODS.get(cid, []):
        reasons = []
        if m['needs'] == 'never':
            reasons.append('FounderOS never collects real money')
        if m['cost'] == 'PAID' and budget['limited']:
            reasons.append(f'costs money; {budget["why"]}')
        if m['needs'] == 'coding' and not skills['coding']:
            reasons.append('needs you to build a web page, and no web or coding skill is stated')
        if m['days'] > window:
            reasons.append(f'needs at least {m["days"]} days (ASSUMED); ' + (f'you have {window}' if days is not None else 'timeline not stated, so 7 days are assumed'))
        options.append({**m, 'feasible': not reasons, 'rejected_because': reasons})
    feasible = [o for o in options if o['feasible']]
    # Prefer stronger behavioural evidence, then no spend, then wider reach (a larger, less hand-picked sample), then shorter.
    feasible.sort(key=lambda o: (-o['strength'], o['cost'] != 'FREE', -o.get('reach', 1), o['days']))
    chosen = feasible[0] if feasible else next(o for o in options if o.get('default'))
    if chosen.get('default'):
        chosen = {**chosen, 'method': default_method}
    alternatives = []
    for o in options:
        if o['id'] == chosen['id']:
            continue
        why = '; '.join(o['rejected_because']) if o['rejected_because'] else (
            'weaker evidence than the chosen method' if o['strength'] < chosen['strength'] else
            'costs money for evidence no stronger than a free method' if o['cost'] == 'PAID' else
            'reaches fewer people than the chosen method (smaller, more hand-picked sample)' if o.get('reach', 1) < chosen.get('reach', 1) else
            'takes longer for evidence of the same strength')
        alternatives.append({'option': o['label'], 'cost': o['cost'], 'assumed_days': o['days'], 'not_chosen_because': why})
    return chosen, alternatives


def propose(brief: dict, discovery: dict | None, register: list[dict], experiments: list[dict]) -> dict:
    """Select an action according to what is *not yet supported*, not the LLM's enthusiasm.

    Evidence is already classified by decision.risk_register. Founder-reported
    numbers and workarounds are not independently verified.
    """
    by_id = {r['claim_id']: r for r in register}
    pending = next((x for x in experiments if x['status'] == 'LOCKED' and not x.get('result_evidence_id')), None)
    if pending:
        # Do not generate a competing test while criteria are locked.
        from .decision import criteria_of
        return {'kind': 'RUN_LOCKED_EXPERIMENT', 'experiment_id': pending['id'], 'version': pending['version'],
                'instruction': 'Complete this pre-registered test with genuine, consenting participants. Submit actual results against the frozen criteria; do not change thresholds after seeing data.',
                'criteria': criteria_of(pending['payload']),
                'risk_ranking_note': 'An existing locked test takes precedence over new suggestions.'}

    workaround = _text(brief.get('current_workaround'), '')
    demand = by_id.get('C-DEM', {})
    problem = by_id.get('C-PROB', {})
    competition = by_id.get('C-COMP', {})
    viability = by_id.get('C-VIAB', {})
    supported = lambda r: r.get('assumption_status') == 'SUPPORTED_BY_BEHAVIOR'
    # Problem must be demonstrated in past behaviour when no workaround was identified.
    if not workaround and not supported(problem):
        cid = 'C-PROB'
        selection = 'No current workaround was stated. First verify that the problem happens and how customers handle it today; a product pitch would bias that answer.'
    elif not supported(demand):
        cid = 'C-DEM'
        selection = 'There is no counted customer-behaviour evidence supporting demand for THIS offering. Market reports or positive opinions cannot fill this gap.'
    elif not supported(competition):
        cid = 'C-COMP'
        selection = 'Demand has behavioural support, but the reason to switch away from existing alternatives is still untested.'
    elif not supported(viability):
        cid = 'C-VIAB'
        selection = 'Behavioural demand and switching signals exist, but willingness to commit at a price has not been demonstrated.'
    else:
        cid = 'C-VIAB'
        selection = 'Previous behavioural signals are founder-reported. Replicate a price-commitment test in a fresh group before considering commercial launch.'

    target = by_id.get(cid) or (register[0] if register else {'claim_id': cid, 'category': 'demand', 'exact_claim': 'Target customers will voluntarily use the proposed solution.', 'assumption_status': 'UNTESTED'})
    seg = _text(brief.get('target_customers') or (discovery or {}).get('target_customers'), 'UNKNOWN segment — narrow the segment first', 260)
    seg, minors = _adult_segment(seg, brief)
    market = _text(brief.get('target_market'), 'UNKNOWN market — choose a location', 150)
    budget = _text(brief.get('budget'), 'UNKNOWN budget', 100)
    timeline = _text(brief.get('timeline'), 'UNKNOWN timeline', 100)
    days = _available_days(timeline)
    window = min(7, max(1, days)) if days is not None else 7
    constraints = _text(brief.get('constraints'), '', 500).lower() + ' ' + _text(brief.get('values'), '', 500).lower()
    private = bool(re.search(r'\b(no personal|no email|privacy|anonym|no tracking|no data collection)\b', constraints))
    value = _text((discovery or {}).get('value_proposition') or brief.get('idea_summary'), 'the proposed digital product', 160)
    current = _text(brief.get('current_workaround'), 'UNKNOWN workaround', 160)
    budget_info = parse_budget(_text(brief.get('budget'), ''))
    skills_info = parse_skills(_text(brief.get('skills'), '', 400))

    if cid == 'C-PROB':
        metric = 'Share of consenting adults who used a concrete workaround for a recent occurrence of the stated problem (past 30 days)'
        method = ('Ask about their last real instance of the problem BEFORE mentioning the solution. '
                  'Record the workaround used, how recently, and cases where no problem occurred.')
    elif cid == 'C-COMP':
        metric = 'Share of consenting adults who voluntarily switch from their current workaround to use a demo trial for the same task'
        method = ('Ask each participant to name the real alternative they currently use, then try the same task in a clearly labelled demo. '
                  'Count actual switching behaviour, not which design they say they like.')
    elif cid == 'C-VIAB':
        metric = 'Share of consenting adults who voluntarily commit to an uncharged, non-binding offer at a stated price (no money collected)'
        method = ('Show one explicit ASSUMED price, ask for a voluntary no-payment commitment, and record refusals. '
                  'Do not claim these commitments predict purchases; do not process payments.')
    else:
        metric = ('Share of consenting adults who voluntarily click a privacy-preserving trial invitation (no identity captured)'
                  if private else 'Share of consenting adults who voluntarily opt in to receive a demo invitation (consent required)')
        method = ('Show a neutral one-paragraph description and count who takes the specified action without prompting. '
                  'Record all eligible participants, including declines; avoid claiming signups are sales.')

    chosen, alternatives = choose_method(cid, budget_info, skills_info, days, method)
    method = chosen['method']
    if days is not None:
        window = min(days, max(window, chosen['days']))   # the test runs as long as its method needs, never beyond stated time
    fit = []
    fit.append(budget_info['why'] + (' Only no-spend methods are proposed.' if budget_info['limited'] else ''))
    if skills_info['stated']:
        fit.append('Stated skills include web/coding, so a self-built page is feasible.' if skills_info['coding']
                   else 'No web/coding skill stated: methods that need you to build software are excluded; use the FounderOS DEMO prototype or manual delivery.')
    else:
        fit.append('Skills not stated: methods that need you to build software are excluded until you state them.')
    if days is not None and days <= 7:
        fit.append(f'Short timeline ({days} day(s)): one narrow test only; no full product build before this result.')
    if skills_info['people']:
        fit.append('Stated people-facing skills help with recruiting and interviewing participants.')
    channel = ('Recruit consenting adult representatives through opt-in channels you personally have permission to use.' if minors
               else 'Use your own permitted local or online networks to invite adults who exactly match the stated segment; do not assume access.')
    evidence_ids = list(dict.fromkeys(target.get('evidence_ids', []) + target.get('contradictory_evidence_ids', [])))[:5]
    status = target.get('assumption_status', 'UNTESTED')
    when = f'{market}; {seg}'
    if days is not None and days < 7:
        feasibility = f'Only {days} day(s) stated: use a {window}-day window. If you cannot recruit the minimum sample, report INCONCLUSIVE; never lower the bar after seeing results.'
    elif days is None:
        feasibility = 'Timeline is not parseable; confirm available time before locking a test.'
    else:
        feasibility = f'{timeline} stated; a {window}-day pilot is proposed, not guaranteed to recruit enough participants.'

    assumption_ids = f' Linked accepted evidence: {", ".join(evidence_ids)}.' if evidence_ids else ' No accepted evidence IDs support this claim yet.'
    return {
        'kind': 'PROPOSED_EXPERIMENT_NEEDS_FOUNDER_APPROVAL',
        'claim_id': target['claim_id'], 'dimension': target['category'],
        'hypothesis': f'{_text(target["exact_claim"], limit=350)} (offering: {value})',
        'target_segment': seg, 'metric': metric,
        'consent_method': 'Participants must know who is asking, why, that it is optional, and how to withdraw. No deception or forced incentives.',
        'founder_actions': [
            f'In {when}, {channel} Aim for at least 10 relevant participants; record how many decline or are excluded.',
            method,
            'Record aggregate action counts, negatives and sampling limitations. Personally enter actual results only after locking the criteria. Outreach remains manual and permission-based.'
        ],
        'timebox_estimate': f'ESTIMATE: {window} day(s); stated availability: {timeline}. Recruitment and response are uncertain.',
        'cost_estimate': f'ESTIMATE: 0 paid-tool cost (free in-person/form methods); stated budget: {budget}. Time and travel costs are not measured.',
        'suggested_criteria': {'min_sample': 10, 'success_threshold_pct': 30, 'adverse_threshold_pct': 10,
                               'time_window_days': window, 'threshold_origin': 'TEAM_ASSUMPTION',
                               'label': 'UNVALIDATED STARTING ASSUMPTIONS, NOT BENCHMARKS. Founder must choose meaningful pass/fail thresholds and lock before observing results. n=10 is not statistically conclusive.'},
        'adverse_result_trigger': 'At/under the founder-locked adverse threshold with sufficient relevant participants: investigate STOP/PIVOT, not launch. Fewer participants: INCONCLUSIVE.',
        'risk_ranking_note': selection + f' Risk register {cid} status: {status}.' + assumption_ids,
        'evidence_basis': {'claim_id': cid, 'status': status, 'counted_evidence_ids': evidence_ids,
                           'limitation': 'Founder-reported evidence is not independently verified; secondary research is context, never demand.'},
        'constraint_fit': {'market': market, 'budget': budget, 'timeline': timeline, 'available_days_parsed': days,
                           'pilot_days': window, 'adult_representatives_only': minors,
                           'privacy_preserving_metric': private, 'note': feasibility},
        'method_chosen': {'id': chosen['id'], 'label': chosen['label'], 'cost': chosen['cost'], 'assumed_days': chosen['days'],
                          'evidence_strength': {3: 'repeated real use', 2: 'one observed action', 1: 'recalled past behaviour'}[chosen['strength']]},
        'alternatives_considered': alternatives,
        'trade_off': f'Chosen because it is the strongest behavioural evidence for {cid} that fits your stated budget, skills and time; '
                     'alternatives were rejected for the reasons listed. Stronger evidence usually needs more time.',
        'founder_fit': fit,
        'budget_parsed': budget_info, 'skills_parsed': skills_info,
        'decision_if_test_fails': 'Revisit the specific assumption, segment or channel; a critical pre-registered clear miss may justify STOP/PIVOT.',
        'external_actions': 'DRAFT ONLY. Founder must review and approve; FounderOS never contacts participants, spends money, or launches.',
    }

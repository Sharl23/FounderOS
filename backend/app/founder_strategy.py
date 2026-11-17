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
        'decision_if_test_fails': 'Revisit the specific assumption, segment or channel; a critical pre-registered clear miss may justify STOP/PIVOT.',
        'external_actions': 'DRAFT ONLY. Founder must review and approve; FounderOS never contacts participants, spends money, or launches.',
    }

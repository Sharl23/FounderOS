"""Deterministic, explainable business-decision policy (Decision Passport).

Principles (see docs/business-decision-methodology.md):
- Secondary sources give market CONTEXT only; they never establish demand for this product.
- Stated interest ("I'd buy") is a CUSTOMER_STATEMENT, not demand.
- Demand can only be supported by CUSTOMER_BEHAVIOR or by results of a PRE-REGISTERED experiment
  whose criteria were locked before results were submitted.
- STOP/PIVOT require a pre-committed critical assumption to fail its locked criterion.
- No evidence => NEEDS_EVIDENCE (not "bad idea"). Nothing here ever yields VALIDATED or launch permission.
- Safety BLOCK supersedes everything and is not a business opinion.
No model output is read by this module except to (a) list AI hypotheses as UNTESTED assumptions and
(b) flag over-claims in that output. Model text can never change a verdict.
"""
from __future__ import annotations
import hashlib
import json
import re

DIMENSIONS = {
    'desirability': 'Desirability / problem',
    'demand': 'Demand / traction',
    'competition': 'Competition / differentiation',
    'feasibility': 'Feasibility / safety',
    'viability': 'Viability / distribution & pricing',
}
EVIDENCE_KINDS = ('SECONDARY_BACKGROUND', 'CUSTOMER_STATEMENT', 'CUSTOMER_BEHAVIOR', 'PRE_REGISTERED_EXPERIMENT_RESULT')
POLICY_VERSION = 'decision-policy-2026-11-17.2'
METHODOLOGY = 'docs/business-decision-methodology.md'


def stable_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def norm(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', (text or '').casefold())).strip()


# ---------------------------------------------------------------- experiments
def criteria_of(exp_payload: dict) -> dict:
    keys = ('hypothesis', 'claim_id', 'dimension', 'target_segment', 'metric', 'success_threshold_pct',
            'adverse_threshold_pct', 'min_sample', 'critical', 'pivot_alternative', 'threshold_origin',
            'benchmark_evidence_id', 'time_window_days', 'near_miss_band', 'direction_id')
    return {k: exp_payload.get(k) for k in keys}


def evaluate_result(criteria: dict, n: int, positives: int) -> dict:
    """Compare an observed result with the LOCKED criterion. Tiny samples are never 'proof'."""
    rate = round(100.0 * positives / n, 1) if n else 0.0
    caveats = ['Founder-reported result: not independently verified.',
               f'Sample n={n}; no statistical certainty is claimed. Selection bias and incentives not assessed.']
    if n < int(criteria['min_sample']):
        return {'outcome': 'INCONCLUSIVE', 'rate_pct': rate, 'adverse': False,
                'explanation': f'Only {n} relevant participants; the locked minimum was {criteria["min_sample"]}. Insufficient evidence.',
                'caveats': caveats}
    adverse = rate <= float(criteria['adverse_threshold_pct'])
    band = float(criteria.get('near_miss_band') or 0)
    success = float(criteria['success_threshold_pct'])
    if success > rate >= success * (1 - band) and not adverse:
        return {'outcome': 'NEAR_MISS', 'rate_pct': rate, 'adverse': False,
                'explanation': f'{positives}/{n} = {rate}% is just below the locked success threshold of {success:g}% '
                               f'(within the locked near-miss band of {band:.0%}). Too close to call: repeat or redesign; this is not a pass.',
                'caveats': caveats}
    if rate >= success:
        return {'outcome': 'PASS', 'rate_pct': rate, 'adverse': False,
                'explanation': f'{positives}/{n} = {rate}% met the locked success threshold of {criteria["success_threshold_pct"]}%. '
                               'This hypothesis passed its pre-registered criterion; the business is NOT validated.',
                'caveats': caveats}
    return {'outcome': 'FAIL', 'rate_pct': rate, 'adverse': adverse,
            'explanation': f'{positives}/{n} = {rate}% is below the locked success threshold of {criteria["success_threshold_pct"]}%'
                           + (f' and at/below the adverse trigger of {criteria["adverse_threshold_pct"]}%.' if adverse else '.'),
            'caveats': caveats}


# ---------------------------------------------------------------- evidence classification
def exclusion_reason(e: dict, live_experiments: dict) -> str | None:
    """Why an evidence row cannot count. None means it counts (for its evidence class)."""
    if e.get('duplicate_of'):
        return f'DUPLICATE of {e["duplicate_of"]}: not double-counted.'
    if e.get('injection_flag'):
        return 'Contains instruction-like text (possible prompt injection): excluded and withheld from agents.'
    if e.get('relevance') == 'IRRELEVANT':
        return 'Marked IRRELEVANT to the claim.'
    kind = e['kind']
    if kind == 'SIMULATED_RESULT':
        return 'SIMULATED / NOT COUNTED: a simulated or demo action is never customer behaviour.'
    from .rubric import is_reserved_url
    if is_reserved_url(e.get('final_url') or e.get('source_url')):
        return 'Reserved documentation domain (e.g. example.com): placeholder text, never evidence about customers or markets.'
    if e.get('review_state') == 'EXCLUDED':
        return 'Excluded by the relevance review: ' + (e.get('review_reason') or 'it does not support the claim.')
    if e.get('review_state') == 'CONTEXT_ONLY':
        return 'Context only: the relevance review did not confirm that this source supports the claim for your market and customer.'
    if kind == 'SECONDARY_BACKGROUND':
        if e.get('excerpt_status') == 'METADATA_ONLY':
            return 'METADATA_ONLY: bibliographic metadata/abstract, not an inspected passage. Context only, not counted.'
        if e.get('url_status') == 'FOUNDER_SUPPLIED':
            return None if e.get('excerpt_status') == 'FOUNDER_SUPPLIED_UNVERIFIED' else 'Founder-supplied excerpt without provenance.'
        if e.get('url_status') != 'URL_ACCESSIBLE':
            return 'UNVERIFIED: source URL could not be retrieved.'
        if e.get('excerpt_status') not in ('EXCERPT_MATCHED', 'STRUCTURED_DATUM'):
            return 'UNVERIFIED: excerpt NOT found in retrieved source.'
        if e.get('stale_and_offmarket'):
            return 'Fails the evidence standard: older than the age limit AND about a different geography.'
        return None
    if kind in ('CUSTOMER_STATEMENT', 'CUSTOMER_BEHAVIOR'):
        if not e.get('consent_confirmed'):
            return 'No consent confirmation for participant data.'
        return None
    if kind == 'PRE_REGISTERED_EXPERIMENT_RESULT':
        exp = live_experiments.get(e.get('experiment_id'))
        if not exp or exp['version'] != e.get('experiment_version') or exp['status'] != 'LOCKED':
            return 'Linked experiment version was superseded or archived (criteria changed / pivot): result no longer counts.'
        return None
    return 'Unknown evidence kind.'


def _counts_for_dimension(e: dict, dim: str) -> bool:
    kind = e['kind']
    if dim == 'demand':
        return kind in ('CUSTOMER_BEHAVIOR', 'PRE_REGISTERED_EXPERIMENT_RESULT')
    if dim == 'desirability':
        return kind in ('CUSTOMER_STATEMENT', 'CUSTOMER_BEHAVIOR', 'PRE_REGISTERED_EXPERIMENT_RESULT', 'SECONDARY_BACKGROUND')
    return kind in ('CUSTOMER_BEHAVIOR', 'PRE_REGISTERED_EXPERIMENT_RESULT', 'SECONDARY_BACKGROUND', 'CUSTOMER_STATEMENT')


def _direction(e: dict) -> str:
    if e['kind'] == 'PRE_REGISTERED_EXPERIMENT_RESULT':
        return {'PASS': 'SUPPORTS', 'FAIL': 'CONTRADICTS'}.get(e.get('outcome'), 'UNSURE')
    return e.get('direction') or 'UNSURE'


STRENGTH = {'PRE_REGISTERED_EXPERIMENT_RESULT': 4, 'CUSTOMER_BEHAVIOR': 3, 'CUSTOMER_STATEMENT': 2, 'SECONDARY_BACKGROUND': 1}

LIMITS = {
    'SECONDARY_BACKGROUND': 'Excerpt match proves only that the words appear at the URL, not that they are true, current, or about this product/segment. Market context only.',
    'CUSTOMER_STATEMENT': 'Stated opinions/hypothetical intent are not purchase or usage behavior (Mom Test). Founder-reported.',
    'CUSTOMER_BEHAVIOR': 'Founder-reported behavior, not independently verified; check sample selection and incentives.',
    'PRE_REGISTERED_EXPERIMENT_RESULT': 'Founder-reported result against a locked criterion; small samples give no statistical certainty.',
}


# ---------------------------------------------------------------- risk register
_CAT = [('viability', r'\b(pay|paid|price|pricing|subscri|afford|revenue|cost|margin|budget|monetiz|fee)'),
        ('competition', r'\b(competitor|alternative|instead|switch|existing|incumbent|differen)'),
        ('feasibility', r'\b(build|develop|skill|technical|legal|privacy|regulat|integrat|data)'),
        ('demand', r'\b(sign ?up|use|adopt|download|join|buy|purchase|want|demand|try|engage|retention)'),
        ('desirability', r'\b(problem|struggl|pain|need|difficult|frustrat|waste|hard)')]


def categorize(text: str) -> str:
    t = (text or '').lower()
    for cat, rx in _CAT:
        if re.search(rx, t):
            return cat
    return 'desirability'


def canonical_assumptions(brief: dict, report: dict | None) -> list[dict]:
    tc = (report or {}).get('target_customers') or []
    seg = brief.get('target_customers') or (tc[0] if tc else None) or 'the target segment (UNKNOWN)'
    problem = brief.get('problem') or (report or {}).get('problem_statement') or 'the stated problem (UNKNOWN)'
    return [
        {'claim_id': 'C-PROB', 'category': 'desirability', 'criticality': 'HIGH',
         'exact_claim': f'{seg} experience "{problem[:140]}" often and severely enough to already use a workaround.',
         'impact_if_false': 'No problem worth solving: STOP or pivot to a different problem.'},
        {'claim_id': 'C-DEM', 'category': 'demand', 'criticality': 'HIGH',
         'exact_claim': f'{seg} will take a real, voluntary action (opt-in, trial, commitment) for THIS product.',
         'impact_if_false': 'Building would produce an unused product.'},
        {'claim_id': 'C-COMP', 'category': 'competition', 'criticality': 'MEDIUM',
         'exact_claim': f'Existing alternatives leave a gap that {seg} would switch for.',
         'impact_if_false': 'No reason to switch; differentiation must change.'},
        {'claim_id': 'C-FEAS', 'category': 'feasibility', 'criticality': 'HIGH',
         'exact_claim': 'The founder can deliver an MVP within stated skills, budget, timeline and legal/privacy constraints.',
         'impact_if_false': 'Fatal feasibility barrier: re-scope or stop.'},
        {'claim_id': 'C-VIAB', 'category': 'viability', 'criticality': 'HIGH',
         'exact_claim': 'A payer exists who will pay a price that covers delivery and acquisition costs (unit economics UNTESTED).',
         'impact_if_false': 'Not a sustainable business even if users like it.'},
    ]


def risk_register(brief: dict, discovery: dict | None, discovery_version, counted: list[dict]) -> list[dict]:
    seg = brief.get('target_customers') or 'UNKNOWN segment'
    rows = []
    for c in canonical_assumptions(brief, discovery):
        c['provenance'] = 'FOUNDEROS_CANONICAL_CHECKLIST (Bland/Osterwalder D-F-V + Aulet)'
        rows.append(c)
    for i, h in enumerate((discovery or {}).get('hypotheses', [])[:6], 1):
        cat = categorize(h)
        rows.append({'claim_id': f'H{i}', 'category': cat, 'criticality': 'HIGH' if cat in ('demand', 'viability') else 'MEDIUM',
                     'exact_claim': h, 'provenance': f'AI_HYPOTHESIS (Discovery v{discovery_version}); UNVERIFIED',
                     'impact_if_false': 'Discovery assumption fails; revise value proposition or segment.'})
    for r in rows:
        r['target_segment'] = seg
        sup, con = [], []
        for e in counted:
            linked = e.get('claim_id') == r['claim_id'] or (r['claim_id'].startswith('C-') and not e.get('claim_id')
                                                             and e.get('dimension') == r['category'])
            if not linked:
                continue
            d = _direction(e)
            (sup if d == 'SUPPORTS' else con if d == 'CONTRADICTS' else []).append(e['id'])
        kinds = {e['kind'] for e in counted if e['id'] in sup + con}
        if not sup and not con:
            status = 'UNTESTED'
        elif sup and con:
            status = 'MIXED'
        elif con:
            status = 'REFUTED'
        elif kinds <= {'SECONDARY_BACKGROUND'}:
            status = 'BACKGROUND_ONLY'
        elif kinds <= {'SECONDARY_BACKGROUND', 'CUSTOMER_STATEMENT'}:
            status = 'STATED_ONLY'
        else:
            status = 'SUPPORTED_BY_BEHAVIOR'
        r.update({'assumption_status': status, 'evidence_ids': sup, 'contradictory_evidence_ids': con,
                  'unknowns': [] if status == 'SUPPORTED_BY_BEHAVIOR' else ['No observed customer behavior for this claim.'],
                  'next_test': None})
    order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
    weak = {'UNTESTED': 0, 'REFUTED': 0, 'MIXED': 1, 'BACKGROUND_ONLY': 1, 'STATED_ONLY': 2, 'SUPPORTED_BY_BEHAVIOR': 3}
    rows.sort(key=lambda r: (order[r['criticality']], weak[r['assumption_status']]))
    return rows


# ---------------------------------------------------------------- next experiment
def suggest_experiment(brief: dict, discovery: dict | None, register: list[dict], experiments: list[dict]) -> dict:
    """Next-test proposal is tailored to the evidence gap, segment and founder constraints.

    The experiment is a DRAFT; no criteria are pre-registered and no results counted.
    """
    from .founder_strategy import propose
    return propose(brief, discovery, register, experiments)


# ---------------------------------------------------------------- skeptical reviewer
_OVERCLAIM = re.compile(r"\b(validated|proven|proves|guarantee\w*|will (definitely |certainly )?succeed|huge demand|massive demand|everyone (needs|wants)|no competitors?|no competition|risk[- ]free|sure to|certain to|definitely)\b", re.I)
_NUMBER = re.compile(r"(\$\s?\d[\d,.]*\s?(k|m|bn|million|billion)?|\b\d[\d,.]*\s?(%|percent|million|billion|egp|usd|users|customers|students)\b)", re.I)


def skeptic_review(report: dict) -> list[dict]:
    """Deterministic reviewer: flags over-claims and unsourced numbers in AI text. Never edits the verdict."""
    flags = []

    def walk(value, path):
        if isinstance(value, str):
            for m in _OVERCLAIM.finditer(value):
                flags.append({'field': path, 'text': value[max(0, m.start() - 40):m.end() + 40], 'issue': f'OVER-CLAIM "{m.group(0)}": not supported by the evidence ledger; treat as ASSUMPTION.'})
            for m in _NUMBER.finditer(value):
                flags.append({'field': path, 'text': value[max(0, m.start() - 40):m.end() + 40], 'issue': f'UNSOURCED NUMBER "{m.group(0).strip()}": AI-generated figure with no citation = ASSUMPTION / UNVERIFIED.'})
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f'{path}[{i}]')
        elif isinstance(value, dict):
            for k, v in value.items():
                if not k.startswith('_'):
                    walk(v, f'{path}.{k}' if path else k)
    walk(report, '')
    return flags[:25]


# ---------------------------------------------------------------- the verdict
def evaluate_validation(*, brief: dict, brief_version: int, safety: dict, discovery: dict | None, discovery_version,
                        evidence: list[dict], experiments: list[dict]) -> dict:
    live = {x['id']: x for x in experiments if x['status'] == 'LOCKED'}
    counted, excluded = [], []
    for e in evidence:
        why = exclusion_reason(e, live)
        (excluded.append({'id': e['id'], 'kind': e['kind'], 'reason': why}) if why else counted.append(e))

    matrix = {}
    for dim, label in DIMENSIONS.items():
        rel = [e for e in counted if (e.get('dimension') == dim or (dim == 'demand' and e['kind'] == 'PRE_REGISTERED_EXPERIMENT_RESULT' and e.get('dimension') in (None, 'demand')))
               and _counts_for_dimension(e, dim)]
        sup = [e for e in rel if _direction(e) == 'SUPPORTS']
        con = [e for e in rel if _direction(e) == 'CONTRADICTS']
        status = 'UNKNOWN' if not sup and not con else 'MIXED' if sup and con else 'SUPPORTED' if sup else 'REFUTED'
        classes = sorted({e['kind'] for e in sup + con}, key=lambda k: -STRENGTH[k])
        note = {
            'demand': 'Only customer BEHAVIOR or pre-registered experiment results count here. Secondary sources and stated interest never do.',
            'competition': 'No identified rivals means UNKNOWN, never "no competitors".',
            'viability': 'Price and unit economics are UNTESTED unless real behavior evidence exists.',
            'feasibility': 'Safety screen + founder constraints; no legal compliance is certified.',
            'desirability': 'Customer statements help discover problems but are not demand.',
        }[dim]
        if status == 'SUPPORTED' and classes and set(classes) <= {'SECONDARY_BACKGROUND'}:
            note = 'SUPPORTED by secondary background only (market context). ' + note
        matrix[dim] = {'label': label, 'status': status, 'supporting_ids': [e['id'] for e in sup],
                       'contradicting_ids': [e['id'] for e in con], 'evidence_classes': classes, 'note': note}
    if safety.get('status') == 'REVIEW_REQUIRED' and matrix['feasibility']['status'] == 'UNKNOWN':
        matrix['feasibility']['status'] = 'MIXED'
        matrix['feasibility']['note'] = 'High-stakes domain flagged by safety screen (acknowledged, research-only). ' + matrix['feasibility']['note']

    exp_outcomes = []
    for e in counted:
        if e['kind'] == 'PRE_REGISTERED_EXPERIMENT_RESULT':
            x = live[e['experiment_id']]
            exp_outcomes.append({'experiment_id': x['id'], 'version': x['version'], 'criteria_hash': x['criteria_hash'],
                                 'locked_at': x['locked_at'], 'evidence_id': e['id'], 'outcome': e['outcome'],
                                 'rate_pct': e.get('rate_pct'), 'n': e.get('sample_size'), 'positives': e.get('positives'),
                                 'adverse': bool(e.get('adverse')), 'critical': bool(x['payload'].get('critical')),
                                 'pivot_alternative': x['payload'].get('pivot_alternative'),
                                 'claim_id': x['payload'].get('claim_id'), 'criteria': criteria_of(x['payload'])})

    register = risk_register(brief, discovery, discovery_version, counted)
    nxt = suggest_experiment(brief, discovery, register, experiments)
    for r in register:
        if r['claim_id'] == nxt.get('claim_id'):
            r['next_test'] = nxt.get('metric')

    reasons_for, reasons_against, caveats = [], [], []
    for dim, m in matrix.items():
        if m['supporting_ids']:
            reasons_for.append((STRENGTH[m['evidence_classes'][0]] if m['evidence_classes'] else 0,
                                f'{m["label"]}: supported by {", ".join(m["supporting_ids"][:3])} ({", ".join(m["evidence_classes"])}).'))
        if m['contradicting_ids']:
            reasons_against.append((STRENGTH[m['evidence_classes'][0]] if m['evidence_classes'] else 0,
                                    f'{m["label"]}: contradicted by {", ".join(m["contradicting_ids"][:3])}.'))
    for r in register:
        if r['criticality'] == 'HIGH' and r['assumption_status'] in ('UNTESTED', 'BACKGROUND_ONLY', 'STATED_ONLY'):
            reasons_against.append((0, f'{r["claim_id"]} ({r["category"]}) is {r["assumption_status"]}: {r["exact_claim"][:120]}'))
    stated = [e for e in counted if e['kind'] == 'CUSTOMER_STATEMENT' and _direction(e) == 'SUPPORTS']
    if stated:
        caveats.append(f'{len(stated)} positive customer STATEMENT(s) recorded; stated interest is not demand and does not count toward launch.')

    crit_fail = [o for o in exp_outcomes if o['critical'] and o['outcome'] == 'FAIL']
    passes = [o for o in exp_outcomes if o['outcome'] == 'PASS']
    behavior_sup = [e for e in counted if e['kind'] == 'CUSTOMER_BEHAVIOR' and _direction(e) == 'SUPPORTS' and e.get('dimension') == 'demand']
    for o in exp_outcomes:
        if o['n'] is not None and o['n'] < 30:
            caveats.append(f'Experiment {o["experiment_id"][:8]} v{o["version"]}: n={o["n"]} is small; results describe this sample only.')
    caveats.append('All customer evidence is FOUNDER_REPORTED_NOT_INDEPENDENTLY_VERIFIED unless stated otherwise.')

    if safety.get('status') == 'BLOCK':
        verdict, kind = 'BLOCK_DO_NOT_LAUNCH', 'SAFETY_BLOCK'
        headline = 'Blocked by backend safety policy. This is not a business opinion and cannot be overridden.'
    elif crit_fail:
        o = crit_fail[0]
        if o['pivot_alternative']:
            verdict, kind = 'PIVOT', 'BUSINESS_ADVISORY'
            headline = (f'A critical pre-registered criterion failed ({o["rate_pct"]}% vs locked {o["criteria"]["success_threshold_pct"]}%). '
                        f'Consider the pre-recorded alternative: "{o["pivot_alternative"][:160]}". The alternative is UNTESTED and needs fresh experiments.')
        elif o['adverse']:
            verdict, kind = 'STOP_DO_NOT_LAUNCH', 'BUSINESS_ADVISORY'
            headline = (f'Advisory STOP: the critical assumption {o["claim_id"] or ""} was falsified by its own locked criterion '
                        f'({o["rate_pct"]}% ≤ adverse trigger {o["criteria"]["adverse_threshold_pct"]}%, n={o["n"]}). Do not launch on current evidence.')
        else:
            verdict, kind = 'NEEDS_EVIDENCE', 'BUSINESS_ADVISORY'
            headline = (f'A critical criterion was missed ({o["rate_pct"]}% < {o["criteria"]["success_threshold_pct"]}%) but not at the adverse level. '
                        'Repeat or redesign the test, or record a pivot alternative.')
    elif any(o['outcome'] == 'NEAR_MISS' and o['critical'] for o in exp_outcomes) and not passes:
        o = next(o for o in exp_outcomes if o['outcome'] == 'NEAR_MISS' and o['critical'])
        verdict, kind = 'NEEDS_EVIDENCE', 'BUSINESS_ADVISORY'
        headline = (f'Near miss on a critical pre-registered test ({o["rate_pct"]}% vs locked {o["criteria"]["success_threshold_pct"]}%). '
                    'Too close to call: repeat with a new locked version or a larger sample. Not a pass and not a failure.')
    elif passes or behavior_sup:
        verdict, kind = 'CONTINUE_TESTING', 'BUSINESS_ADVISORY'
        headline = ('Promising but incomplete: some real behavior evidence supports demand. Continue testing the remaining critical assumptions. '
                    'This is NOT validation and NOT permission to build or launch.')
    else:
        verdict, kind = 'NEEDS_EVIDENCE', 'BUSINESS_ADVISORY'
        headline = ('No authentic customer behavior or pre-registered result exists yet, so demand is UNTESTED. '
                    'This is not a judgment that the idea is bad: run the next experiment.')
        if matrix['demand']['status'] == 'REFUTED':
            headline += ' Note: unregistered negative behavior exists; pre-register a test to decide PIVOT/STOP fairly.'

    if verdict == 'BLOCK_DO_NOT_LAUNCH':
        nxt = {'kind': 'NO_EXPERIMENT_SAFETY_BLOCK',
               'instruction': 'Revise the prohibited venture idea and pass the safety screen first. No experiment is authorised.'}
    elif verdict in ('STOP_DO_NOT_LAUNCH', 'PIVOT'):
        nxt = {'kind': 'REVIEW_CRITICAL_RESULT_BEFORE_MORE_TESTS',
               'instruction': 'Review the failed, pre-registered critical criterion and founder decision first. Do not restart tests or claim a pivot is validated.'}

    counted_sorted = sorted(counted, key=lambda e: -STRENGTH[e['kind']])
    strongest = counted_sorted[0] if counted_sorted else None
    unresolved = [{'claim_id': r['claim_id'], 'category': r['category'], 'status': r['assumption_status'], 'claim': r['exact_claim']}
                  for r in register if r['criticality'] == 'HIGH' and r['assumption_status'] != 'SUPPORTED_BY_BEHAVIOR']
    contradictions = [{'dimension': d, 'supporting_ids': m['supporting_ids'], 'contradicting_ids': m['contradicting_ids']}
                      for d, m in matrix.items() if m['status'] == 'MIXED' and m['supporting_ids'] and m['contradicting_ids']]
    change_mind = {
        'NEEDS_EVIDENCE': ['A locked experiment HITTING its criterion with real target customers → CONTINUE_TESTING.',
                           'A critical locked experiment FAILING at/below its adverse trigger → STOP, or PIVOT if an alternative is recorded.'],
        'CONTINUE_TESTING': ['Failure of any remaining critical locked experiment → PIVOT/STOP.',
                             'Evidence that the positive sample was unrepresentative or incentivised → back to NEEDS_EVIDENCE.'],
        'PIVOT': ['Evidence that the failed test was badly targeted (wrong segment/channel) → re-run, NEEDS_EVIDENCE.',
                  'The alternative also failing its own locked test → STOP.'],
        'STOP_DO_NOT_LAUNCH': ['A new, separately pre-registered test with a different segment/problem passing → reconsider via PIVOT.',
                               'Discovery that the test was invalid (wrong population, broken form) → re-run, NEEDS_EVIDENCE.'],
        'BLOCK_DO_NOT_LAUNCH': ['Only a revised brief that removes the prohibited element can be re-screened.'],
    }[verdict]
    recommendation = {
        'NEEDS_EVIDENCE': 'If you want to keep going, collect real evidence first. Do not build or launch on the current evidence.',
        'CONTINUE_TESTING': 'Continue research on the weakest critical assumption. Building or launching would still be premature on current evidence.',
        'PIVOT': 'If the failed result reflects the target segment fairly, test the recorded alternative with a new locked experiment. The pivot is not validated.',
        'STOP_DO_NOT_LAUNCH': 'On current evidence, do not launch. A defensible decision not to launch is a valid outcome. You may record a different course with your reasons.',
        'BLOCK_DO_NOT_LAUNCH': 'Revise the brief to remove the prohibited element, or stop.',
    }[verdict]
    next_decision = next_decision_card(verdict, headline, recommendation, nxt, register, exp_outcomes, change_mind, counted, brief)
    return {
        'verdict': verdict, 'verdict_kind': kind, 'headline': headline, 'recommendation': recommendation,
        'never': 'Never VALIDATED / PROCEED_TO_LAUNCH. No success probability is computed.',
        'matrix': matrix,
        'reasons_for': [t for _, t in sorted(reasons_for, key=lambda x: -x[0])][:3],
        'reasons_against': [t for _, t in sorted(reasons_against, key=lambda x: -x[0])][:3],
        'strongest_source': ({'id': strongest['id'], 'kind': strongest['kind'], 'claim': strongest.get('claim') or 'UNKNOWN claim text',
                              'source_url': strongest.get('source_url'), 'limitations': LIMITS[strongest['kind']]}
                             if strongest else {'id': None, 'kind': None, 'limitations': 'SOURCE UNAVAILABLE: no counted evidence. All market statements are ASSUMPTIONS.'}),
        'unresolved_critical_assumptions': unresolved,
        'contradictions': contradictions,
        'excluded_evidence': excluded,
        'experiment_outcomes': exp_outcomes,
        'risk_register': register,
        'what_would_change_our_mind': change_mind,
        'next_experiment': nxt,
        'next_decision': next_decision,
        'caveats': caveats,
        'permissions': {'continue_research': verdict != 'BLOCK_DO_NOT_LAUNCH', 'build': False, 'launch': False,
                        'external_actions': False},
        'inputs': {'brief_version': brief_version, 'safety_status': safety.get('status'),
                   'safety_policy': safety.get('policy_version'), 'discovery_version': discovery_version,
                   'evidence_snapshot_hash': evidence_snapshot_hash(evidence),
                   'experiment_versions': sorted(f'{x["id"]}:v{x["version"]}:{x["status"]}' for x in experiments),
                   'decision_policy': POLICY_VERSION, 'methodology': METHODOLOGY},
    }


def next_decision_card(verdict, headline, recommendation, nxt, register, exp_outcomes, change_mind, counted, brief) -> dict:
    """One founder-facing answer to: what do I do next, why, on what evidence, and what would change it.

    Built only from values already computed above (verdict, risk register, next experiment). It adds no new
    judgement: confidence describes evidence coverage of the critical claims, never a probability of success.
    """
    critical = [r for r in register if r['claim_id'].startswith('C-')]
    behaviour = [r['claim_id'] for r in critical if r['assumption_status'] == 'SUPPORTED_BY_BEHAVIOR']
    weak = [r for r in critical if r['assumption_status'] != 'SUPPORTED_BY_BEHAVIOR']
    ids = sorted({i for r in critical for i in r.get('evidence_ids', []) + r.get('contradictory_evidence_ids', [])})
    coverage = f'{len(behaviour)} of {len(critical)} critical claims have observed-behaviour support'
    # NONE: no critical claim has behaviour support. LOW: under half. MODERATE: half or more. Never HIGH: customer evidence is
    # founder-reported, and a model's wording can never raise this. Not applicable when a hard rule decided the outcome.
    level = 'NONE' if not behaviour else 'LOW' if len(behaviour) * 2 < len(critical) else 'MODERATE'
    if verdict == 'BLOCK_DO_NOT_LAUNCH':
        level, coverage = 'NOT_APPLICABLE', 'A safety hard stop decided this; evidence cannot change it'
    proposal = nxt.get('kind') == 'PROPOSED_EXPERIMENT_NEEDS_FOUNDER_APPROVAL'
    crit_fail = next((o for o in exp_outcomes if o['critical'] and o['outcome'] == 'FAIL'), None)
    if verdict == 'BLOCK_DO_NOT_LAUNCH':
        decision, action = 'Do not pursue this venture as described.', nxt.get('instruction')
        alternatives = [{'option': 'Remove the prohibited element and re-screen a revised brief', 'not_chosen_because': 'Only you can decide to change the idea; nothing runs until it passes the safety screen.'}]
    elif verdict in ('STOP_DO_NOT_LAUNCH', 'PIVOT'):
        decision = 'Stop and review the failed critical test before anything else.' if verdict == 'STOP_DO_NOT_LAUNCH' else \
            'Review the failed critical test, then decide whether to test the recorded alternative.'
        action = nxt.get('instruction')
        alternatives = [
            {'option': 'REPEAT the same test', 'not_chosen_because': 'Only justified if the test itself was flawed (wrong people, broken form). Record why before re-running.'},
            {'option': 'PIVOT to the recorded alternative', 'not_chosen_because': 'The alternative is untested; it needs its own locked test.' if crit_fail and crit_fail.get('pivot_alternative') else 'No alternative was recorded before the result.'},
            {'option': 'Continue building', 'not_chosen_because': 'A critical assumption failed its own pre-registered criterion.'}]
    elif proposal:
        decision = f'Test {nxt["claim_id"]} ({nxt["dimension"]}) next: {nxt["method_chosen"]["label"]}.'
        action = nxt['founder_actions'][1]
        alternatives = nxt.get('alternatives_considered', []) + [
            {'option': 'Build the full product now', 'not_chosen_because': f'{nxt["claim_id"]} has no observed-behaviour support; building would not answer it.'}]
    else:
        decision, action = recommendation, nxt.get('instruction') or recommendation
        alternatives = []
    crit = (nxt.get('suggested_criteria') or {}) if proposal else {}
    return {
        'decision': decision,
        'why': [headline] + [f'{r["claim_id"]} ({r["category"]}) is {r["assumption_status"]}.' for r in weak[:3]],
        'evidence_ids': ids,
        'evidence_note': 'No counted evidence yet: every claim is an ASSUMPTION.' if not ids else 'IDs refer to the evidence ledger.',
        'unknowns': [f'{r["claim_id"]}: {r["exact_claim"][:140]}' for r in weak],
        'alternatives': alternatives,
        'trade_off': nxt.get('trade_off') if proposal else 'The safest defensible option given a failed or blocked critical check.',
        'founder_fit': nxt.get('founder_fit', []) if proposal else [],
        'next_action': action,
        'cost_and_time': {'cost': nxt.get('cost_estimate'), 'time': nxt.get('timebox_estimate')} if proposal else None,
        'success_criterion': (f'At least {crit.get("success_threshold_pct")}% of at least {crit.get("min_sample")} relevant participants take the action '
                              f'within {crit.get("time_window_days")} days (STARTING ASSUMPTION: you choose and lock the real numbers before collecting results).') if crit else None,
        'what_would_change_it': change_mind,
        'needs_founder_approval': 'Locking the test criteria and every contact with participants are yours; FounderOS sends nothing.' if proposal else 'Recording your decision on this verdict.',
        'confidence': {'level': level, 'basis': coverage, 'meaning': 'Evidence coverage, not a probability of success. Model wording never raises it.'},
        'limitations': ['Customer evidence is founder-reported unless independently verified.', 'Costs, durations and thresholds are ASSUMPTIONS.',
                        'Simulated (MOCKED) sales are never counted as demand.'],
    }


def evidence_snapshot_hash(evidence: list[dict]) -> str:
    return stable_hash(sorted([e['id'], e.get('duplicate_of'), e.get('excerpt_status'), e.get('outcome')] for e in evidence))


def discovery_gate(report: dict, missing: list[str]) -> dict:
    ok = all(bool(report.get(k)) for k in ('problem_statement', 'target_customers', 'hypotheses', 'experiments'))
    reasons = []
    if not ok:
        reasons.append('Required discovery report fields are missing.')
    if missing:
        reasons.append('Founder context still UNKNOWN: ' + ', '.join(missing) + '. Answer clarifications or approve knowingly.')
    reasons.append('Everything in this report is an AI HYPOTHESIS, not evidence. Approval only permits validation research.')
    return {'phase': 'discover', 'recommendation': 'PROCEED_TO_VALIDATION_RESEARCH' if ok and not missing else 'REVISE',
            'reasons': reasons, 'approval_required': True, 'approval_scope': 'RESEARCH_ONLY',
            'external_actions_permitted': False}

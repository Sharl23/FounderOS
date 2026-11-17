"""Versioned, explicit criteria catalog derived from Criteria Types for the Agent Workflow.

This is a transparency/coverage report, NOT a substitute for the existing
backend decision gate. An evidence reference is required before any score counts.
"""
from __future__ import annotations
from datetime import date

VERSION = 'criteria-workflow-2026-11-16.v1'

def criterion(code, phase, label, kind, question, dimension=None, origin='Criteria Types for the Agent Workflow (2026-11-16)', editable=False):
    return dict(id=code, phase=phase, name=label, kind=kind, question=question,
                dimension=dimension, origin=origin, founder_editable=editable,
                evidence_required=kind in ('scored', 'evidence_standard'),
                scale={'UNKNOWN':'No qualified evidence; do not score', '0':'Direct, qualified evidence refutes the criterion', '1':'Weak evidence and serious gaps', '2':'Mixed evidence with material unknowns', '3':'Reasonably supported within the tested segment', '4':'Strong direct and repeatable support'} if kind == 'scored' else None,
                weight=None, pass_mark=None,
                change_control='Founder may propose new version; safety knockouts cannot be disabled' if editable else 'Fixed by policy; review requires versioned change',
                status='NOT_EVALUATED')

DISCOVER = [
    criterion('D01','discover','Ethics & legality','knockout','Does a documented hard-stop rule apply?'),
    criterion('D02','discover','Idea clarity','output_check','Are customer, pain and current workaround specific?'),
    criterion('D03','discover','Problem & customer','scored','Is the problem real and frequent in a reachable segment?', 'desirability'),
    criterion('D04','discover','Demand signals','scored','Do target customers show relevant problem-solving behavior?', 'demand'),
    criterion('D05','discover','Competition & alternatives','scored','What alternatives exist and what is the differentiated gap?', 'competition'),
    criterion('D06','discover','Feasibility & founder fit','scored','Does the MVP fit skills, budget, schedule and constraints?', 'feasibility'),
    criterion('D07','discover','Viability first look','scored','Is a credible, sourced payment model plausible?', 'viability'),
    criterion('D08','discover','Direction ranking','threshold','Which of 2–3 feasible directions ranks first and why?', editable=True),
    criterion('D09','discover','Discover gate rule','threshold','Do the evidence and unknowns permit advance, repeat, pivot or stop?', editable=True),
]
VALIDATE = [
    criterion('V01','validate','Business model coherence','scored','Do customer, value, channel, costs and revenue fit?', 'viability'),
    criterion('V02','validate','Strategy & positioning','scored','Why switch from the current workaround?', 'competition'),
    criterion('V03','validate','Financial fit','knockout','Can the plan satisfy hard financial and time limits?', 'feasibility'),
    criterion('V04','validate','Risk ranking','scored','Which critical assumption is least supported?', 'desirability'),
    criterion('V05','validate','Experiment design','output_check','Is the experiment ethical, falsifiable and behavioral?'),
    criterion('V06','validate','Target setting','threshold','Is the target pre-registered with a rationale or assumption label?', editable=True),
    criterion('V07','validate','Result reading','threshold','Did a real, adequately sampled result pass pre-registered criteria?'),
]
CROSS = [
    criterion('X01','all','Evidence quality','evidence_standard','Are publisher, date, geography, directness, exact text and provenance known?'),
    criterion('X02','all','Founder constraints & values','knockout','Are hard limits and declared values respected?'),
    criterion('X03','all','Safety rules','knockout','Is a non-overridable hard-stop rule triggered?'),
    criterion('X04','all','Approval scope','knockout','Does an action require explicit founder authorization?'),
    criterion('X05','all','Confidence & unknowns','evidence_standard','Is there enough qualified evidence to conclude anything?'),
]
ARCHITECTURE = {
    'build':['Scope fit','Acceptance tests'],
    'commercial':['Pricing logic','Offer structure','Policy completeness','Fair dealing','Compliance flags'],
    'launch':['Positioning & message','Channel selection','Content honesty','Content quality','Launch readiness','Launch targets'],
    'operate':['Metric selection','Support quality','Learning validity','Next-step decision'],
}
CATALOG = DISCOVER + VALIDATE + CROSS

def summarize(evidence, safety_status=None, experiments=None, brief=None):
    """Compute conservative coverage, not market success or numerical grades."""
    experiments = experiments or []
    records = []
    for e in evidence:
        if e.get('duplicate_of') or e.get('injection_flag'):
            continue
        kind = e.get('kind')
        is_secondary = kind == 'SECONDARY_BACKGROUND'
        if is_secondary:
            qualified = (e.get('url_status') == 'URL_ACCESSIBLE' and
                         e.get('excerpt_status') == 'EXCERPT_MATCHED' and
                         e.get('relevance') == 'CLAIM_RELEVANT' and
                         e.get('direction') in ('SUPPORTS','CONTRADICTS'))
        else:
            qualified = bool(e.get('consent_confirmed')) and bool(e.get('method')) and bool(e.get('sample_size'))
        if qualified:
            records.append(e)
    dimension_map = {}
    for e in records:
        dimension_map.setdefault(e['dimension'], []).append(e)
    rows = []
    for entry in CATALOG:
        row = dict(entry)
        dimension = row['dimension']
        matched = dimension_map.get(dimension, []) if dimension else []
        row['evidence_ids'] = [e['id'] for e in matched]
        if row['kind'] == 'scored':
            # Even a qualified source does not automatically justify a SCORE.
            row['status'] = 'EVIDENCE_TO_REVIEW' if matched else 'UNKNOWN'
            row['score'] = None
            row['reason'] = ('Available records need a claim-specific judging pass; no numeric score is inferred.' if matched
                             else 'No qualified, directly relevant evidence for this dimension.')
        elif row['id'] == 'D01' or row['id'] == 'X03':
            row['status'] = 'BLOCK' if safety_status == 'BLOCK' else ('REVIEW' if safety_status == 'REVIEW_REQUIRED' else 'SCREEN_PASSED' if safety_status else 'NOT_RUN')
            row['reason'] = 'Safety is a best-effort policy screen, never legal clearance.'
        elif row['id'] == 'X01':
            row['status'] = 'EVIDENCE_TO_REVIEW' if records else 'UNKNOWN'
            row['reason'] = 'Exact-excerpt match and provenance are necessary, not proof of truth.'
        elif row['id'] == 'X05':
            row['status'] = 'EVIDENCE_TO_REVIEW' if records else 'UNKNOWN'
            row['reason'] = 'Unknowns are explicit; no success probability is calculated.'
        elif row['id'] == 'V06':
            locked = [x for x in experiments if x.get('status') == 'LOCKED']
            row['status'] = 'PRE_REGISTERED' if locked else 'NOT_READY'
            row['reason'] = 'Pass marks must be justified and frozen before seeing results; arbitrary defaults are assumptions.'
        else:
            row['status'] = 'NEEDS_REVIEW'
            row['reason'] = 'This criterion requires a separate explicit check, not a guessed model score.'
        rows.append(row)
    return {'criteria_version': VERSION, 'criteria': rows,
            'qualified_evidence_count': len(records), 'raw_evidence_count': len(evidence),
            'architecture_only': ARCHITECTURE,
            'notice': 'This is an auditable criteria-coverage dashboard, not a new GO/STOP verdict. The existing deterministic backend gate remains authoritative.'}

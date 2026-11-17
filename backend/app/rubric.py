"""Phase-1 team rubric: 67 granular checks, evaluated one at a time and aggregated in code (v0.8).

Data contract: policy/rubric_phase1.yaml. `checks` and `provenance` are the team's text, unchanged,
integrity-checked by sha256 at import. The implementation overlay (sources required, accepted source
types, absence caps, brief conditions) is FounderOS's own labelled assumption.

Architecture (contract §2): the 67 checks are NOT 67 top-level gates.
  D01 aggregates the 12 ethics checks (enforced by safety.py with policy/safety_rules.yaml).
  D03 aggregates 6, D04 5, D05 15, D06 15, D07 14 scored checks.
  D02, D08, D09 and X01–X05 stay distinct.

Granular statuses (scored checks):
  UNKNOWN          no eligible, accepted, relevant evidence (or the judge output was rejected). Never a low score.
  AWAITING_JUDGE   eligible evidence exists but no validated judgment yet. Counts as UNKNOWN.
  WEAK / MIXED / STRONG  validated judgment, capped by code rules below. Mapped to 2 / 3 / 4.
  NOT_APPLICABLE   only where legitimately justified by a code rule (e.g. no demand figures cited at all).
Code rules (the model never decides these):
  * WEAK needs actual negative evidence (a cited CONTRADICTS row) or a directly checkable brief condition.
    "Search returned nothing" is UNKNOWN, never WEAK.
  * STRONG needs >= sources_required independent ORGANISATIONS among supporting rows, at least one
    machine-verified row, and no accepted contradicting row (otherwise capped at MIXED).
  * Absence-type checks (no_blocking_patent, free_alternatives_threat, substitution_threat,
    regulatory_barriers_manageable) are never STRONG: a bounded search is not proof of absence.
  * Only rows whose source_type is accepted for that check count. Academic metadata, simulated results
    and book supporting passages are never eligible.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

PATH = Path(__file__).resolve().parents[1] / 'policy' / 'rubric_phase1.yaml'
RAW = PATH.read_bytes()
DOC = yaml.safe_load(RAW.decode('utf-8'))
VERSION = DOC['version']
FILE_HASH = hashlib.sha256(RAW).hexdigest()
CHECKS = DOC['checks']
PROVENANCE = {p['id']: p for p in DOC['provenance']}
BY_ID = {c['id']: c for c in CHECKS}
OVERLAY = DOC['implementation_overlay']
OV = OVERLAY['checks']
DIM_MAP = DOC['dimension_map']
SOURCE_TYPES = OVERLAY['source_types']
NEVER = set(OVERLAY['never_eligible'])
RATING_SCORE = {k: v for k, v in OVERLAY['rating_to_score'].items() if k in ('WEAK', 'MIXED', 'STRONG')}
MIN_KNOWN = OVERLAY['aggregation']['min_known_checks']
EXPECTED_COUNTS = {'D01': 12, 'D03': 6, 'D04': 5, 'D05': 15, 'D06': 15, 'D07': 14}
SCORED_DIMS = ('D03', 'D04', 'D05', 'D06', 'D07')
DIM_NAMES = {'D01': 'Ethics and legality screen', 'D03': 'Problem and customer', 'D04': 'Demand signals',
             'D05': 'Competition and alternatives', 'D06': 'Feasibility and founder fit', 'D07': 'Viability, first look'}
RATINGS = ('WEAK', 'MIXED', 'STRONG', 'INSUFFICIENT')


class RubricError(RuntimeError):
    pass


def team_hash() -> str:
    canon = json.dumps({'checks': CHECKS, 'provenance': DOC['provenance']}, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canon.encode()).hexdigest()


def validate() -> dict:
    """Schema + integrity validation. Called at import and again at app startup; raises RubricError."""
    problems = []
    ids = [c.get('id') for c in CHECKS]
    if len(ids) != 67:
        problems.append(f'expected 67 checks, found {len(ids)}')
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        problems.append(f'duplicate ids: {dups}')
    if set(ids) != set(PROVENANCE) or len(DOC['provenance']) != len(ids):
        problems.append('provenance ids do not match check ids one-to-one')
    if team_hash() != DOC.get('team_data_sha256'):
        problems.append('team data hash mismatch: rubric text was edited outside the generator')
    for c in CHECKS:
        for k in ('id', 'phase', 'type', 'kind', 'brief_fields', 'research_instruction', 'judge_instruction'):
            if k not in c:
                problems.append(f'{c.get("id")}: missing {k}')
        ji = c.get('judge_instruction') or {}
        need = ('question', 'fail_if') if c.get('kind') == 'knockout' else ('question', 'weak', 'mixed', 'strong')
        for k in need:
            if not ji.get(k):
                problems.append(f'{c.get("id")}: judge_instruction.{k} missing')
        if c.get('type') not in DIM_MAP:
            problems.append(f'{c.get("id")}: unknown type {c.get("type")!r}')
        if c.get('id') not in OV:
            problems.append(f'{c.get("id")}: no implementation overlay')
        else:
            bad = [t for t in OV[c['id']]['accepted_source_types'] if t not in SOURCE_TYPES]
            if bad:
                problems.append(f'{c["id"]}: unknown source types {bad}')
            if OV[c['id']]['aggregates_into'] != DIM_MAP.get(c.get('type')):
                problems.append(f'{c["id"]}: overlay dimension disagrees with type')
    for pid, p in PROVENANCE.items():
        for k in ('book', 'chapter', 'page', 'supporting_passage', 'basis'):
            if k not in p:
                problems.append(f'provenance {pid}: missing {k}')
    counts = {}
    for c in CHECKS:
        counts[DIM_MAP.get(c.get('type'))] = counts.get(DIM_MAP.get(c.get('type')), 0) + 1
    if counts != EXPECTED_COUNTS:
        problems.append(f'per-dimension counts {counts} != {EXPECTED_COUNTS}')
    from . import safety
    eth = [c for c in CHECKS if c['type'] == 'Ethics and legality screen']
    if sorted(c['id'] for c in eth) != sorted(safety.RULE_IDS):
        problems.append('ethics check ids differ from policy/safety_rules.yaml')
    for c in eth:
        r = safety.RULES.get(c['id']) or {}
        if r.get('question') != c['judge_instruction'].get('question') or r.get('fail_if') != c['judge_instruction'].get('fail_if'):
            problems.append(f'{c["id"]}: question/fail_if differ between rubric and safety policy')
    if problems:
        raise RubricError('; '.join(problems))
    return {'ok': True, 'count': len(ids), 'per_dimension': counts}


VALIDATION = validate()
DIMENSION_OF = {c['id']: DIM_MAP[c['type']] for c in CHECKS}
BY_DIMENSION = {d: [c['id'] for c in CHECKS if DIMENSION_OF[c['id']] == d] for d in EXPECTED_COUNTS}
ABSENCE = {k for k, v in OV.items() if v.get('absence_claim_cap')}


def coverage() -> dict:
    return {'version': VERSION, 'file_sha256': FILE_HASH, 'team_data_sha256': DOC['team_data_sha256'], 'total': len(CHECKS),
            'per_dimension': {d: {'name': DIM_NAMES[d], 'count': len(v), 'ids': v} for d, v in BY_DIMENSION.items()},
            'distinct_top_level': ['D02', 'D08', 'D09', 'X01', 'X02', 'X03', 'X04', 'X05'],
            'provenance_note': DOC['provenance_note']}


def catalog() -> dict:
    out = []
    for c in CHECKS:
        out.append({**c, 'dimension': DIMENSION_OF[c['id']], 'provenance': PROVENANCE[c['id']], 'implementation': OV[c['id']]})
    return {'coverage': coverage(), 'checks': out, 'source_types': SOURCE_TYPES, 'never_eligible': sorted(NEVER),
            'rating_to_score': OVERLAY['rating_to_score'], 'aggregation': OVERLAY['aggregation'], 'overlay_origin': OVERLAY['origin']}


# ----------------------------------------------------------------------------- source identity
_MULTI = ('co.uk', 'org.uk', 'ac.uk', 'gov.uk', 'com.eg', 'gov.eg', 'edu.eg', 'org.eg', 'com.sa', 'gov.sa', 'com.au', 'co.in', 'co.jp', 'com.br', 'co.za', 'ac.za', 'gov.ae', 'co.ke', 'com.ng')
RESERVED_HOSTS = re.compile(r'(^|\.)(example\.(com|net|org|edu)|example|test|invalid|localhost)$', re.I)


def registrable(host: str | None) -> str | None:
    if not host:
        return None
    h = host.lower().rstrip('.')
    if h.startswith('www.'):
        h = h[4:]
    parts = h.split('.')
    if len(parts) >= 3 and '.'.join(parts[-2:]) in _MULTI:
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:]) if len(parts) >= 2 else h


def is_reserved_url(url: str | None) -> bool:
    host = urlparse(url or '').hostname
    return bool(host and RESERVED_HOSTS.search(host))


def organisation(e: dict) -> str:
    """Independence is tracked by original publisher/organisation, not by URL or DOI."""
    if e.get('organization'):
        return str(e['organization']).strip().lower()
    if e['kind'] in ('CUSTOMER_STATEMENT', 'CUSTOMER_BEHAVIOR', 'PRE_REGISTERED_EXPERIMENT_RESULT'):
        return 'founder-run research'
    pub = re.sub(r'[^a-z0-9 ]', '', (e.get('publisher') or '').lower()).strip()
    pub = re.sub(r'\b(inc|ltd|llc|plc|the|group|press|publishing|co)\b', '', pub).strip()
    dom = registrable(urlparse(e.get('final_url') or e.get('source_url') or '').hostname)
    if e.get('provider') in ('crossref', 'openalex') and pub:
        return pub
    return dom or pub or f'unknown:{e["id"][:8]}'


def source_type_of(e: dict) -> str:
    if e.get('source_type'):
        return e['source_type']
    if e['kind'] in ('CUSTOMER_STATEMENT', 'CUSTOMER_BEHAVIOR', 'PRE_REGISTERED_EXPERIMENT_RESULT'):
        return 'FOUNDER_CUSTOMER_RESEARCH'
    if e['kind'] == 'SIMULATED_RESULT':
        return 'SIMULATED_RESULT'
    if e.get('excerpt_status') == 'METADATA_ONLY':
        return 'ACADEMIC_METADATA'
    if e.get('excerpt_status') == 'STRUCTURED_DATUM':
        return 'OFFICIAL_STATISTIC'
    if e.get('provider') in ('crossref', 'openalex'):
        return 'ACADEMIC_PASSAGE'
    return 'UNCLASSIFIED'


def machine_verified(e: dict) -> bool:
    return e.get('excerpt_status') in ('EXCERPT_MATCHED', 'STRUCTURED_DATUM') or e['kind'] in ('CUSTOMER_BEHAVIOR', 'PRE_REGISTERED_EXPERIMENT_RESULT')


# ----------------------------------------------------------------------------- eligibility
def eligibility(e: dict, cid: str, quality: dict) -> tuple[bool, str]:
    """Can this ledger row count for check `cid`? Returns (ok, reason)."""
    if e.get('subcriterion_id') != cid:
        return False, 'not linked to this check'
    q = quality.get(e['id']) or {}
    if not q.get('counts') and e.get('url_status') != 'FOUNDER_SUPPLIED':
        return False, q.get('exclusion') or 'did not pass the evidence standard (X01)'
    if e.get('review_state') not in ('ACCEPTED_RELEVANT',):
        return False, f'relevance review: {e.get("review_state") or "not reviewed"} (only ACCEPTED_RELEVANT counts for a granular check)'
    st = source_type_of(e)
    if st in NEVER:
        return False, f'{st} is never evidence for a check'
    if st not in OV[cid]['accepted_source_types']:
        return False, f'source type {st} is not what this check asks for ({", ".join(OV[cid]["accepted_source_types"])})'
    return True, 'eligible'


# ----------------------------------------------------------------------------- brief conditions (deterministic WEAK/N/A)
_PRICE = re.compile(r'(?i)\b(subscription|per month|monthly|annual fee|per user|commission|fee|charge\w*|pric\w*|pay\w*|freemium|licen[cs]e fee|one[- ]time|sell (it|access)|\$\s?\d|\d+\s?(egp|usd|le))\b')
_COSTS = re.compile(r'(?i)\b(cost\w*|hosting|server\w*|salar\w*|spend\w*|expens\w*|api fees?|marketing budget|fixed|variable)\b')
_CONTACTS = re.compile(r'(?i)\b(mentor\w*|advis[eo]r\w*|co-?founder\w*|friend\w*|network|community|communities|contact\w*|incubator|accelerator|professor|colleague\w*|partner\w*)\b')
_PAYER = re.compile(r'(?i)\b(pay|pays|paid by|payer|buyer|budget holder|owners? (pay|would pay)|parents? pay|the (school|company|restaurant|clinic|employer) pays|subscription paid)\b')
_BROAD = re.compile(r'(?i)\b(everyone|everybody|anyone|all people|the general public|general audience|all (users|businesses|students|people|companies))\b')


def brief_condition(cid: str, brief: dict, evidence: list[dict]) -> dict | None:
    """Directly checkable founder-brief conditions. Return {'status','basis'} or None."""
    cond = OV[cid].get('brief_condition')
    text = ' '.join(str(brief.get(k) or '') for k in ('original_idea_text', 'idea_summary', 'problem', 'target_customers', 'budget', 'constraints', 'skills'))
    if cid == 'raw_counts_discounted':
        figures = re.findall(r'\b\d[\d,.]*\s?(%|percent|downloads|visits|views|users|sign-?ups|followers)\b', text, re.I)
        demand_rows = [e for e in evidence if e.get('subcriterion_id') == cid]
        if not figures and not demand_rows:
            return {'status': 'NOT_APPLICABLE', 'basis': 'No demand figures are cited in the brief or linked in the ledger, so there is nothing to discount.'}
        return None
    if not cond:
        return None
    if cond == 'BROAD_SEGMENT':
        seg = brief.get('target_customers') or ''
        if seg and _BROAD.search(seg):
            return {'status': 'WEAK', 'basis': f'Brief condition: the customer segment "{seg}" names everyone or a broad mainstream audience.'}
    if cond == 'NO_PAYER':
        if (brief.get('target_customers') or brief.get('original_idea_text')) and not _PAYER.search(text) and not (brief.get('fields') or {}).get('payer'):
            return {'status': 'WEAK', 'basis': 'Brief condition: the brief names no buyer separately from the users (no statement of who pays).'}
    if cond == 'NO_CONTACTS':
        if not _CONTACTS.search(text):
            return {'status': 'WEAK', 'basis': 'Brief condition: the brief names no contacts, advisers, mentors or communities.'}
    if cond == 'NO_COSTS':
        if not _COSTS.search(text):
            return {'status': 'WEAK', 'basis': 'Brief condition: the brief names no costs of running the product.'}
    if cond == 'NO_CHARGE_METHOD':
        if not _PRICE.search(text):
            return {'status': 'WEAK', 'basis': 'Brief condition: the brief names no way to charge.'}
    return None


# ----------------------------------------------------------------------------- per-check judge contract
_URL = re.compile(r'https?://|www\.', re.I)
_NUM = re.compile(r'\d+(?:[.,]\d+)?')


def judge_input(cid: str, brief: dict, rows: list[dict]) -> tuple[dict, dict]:
    c = BY_ID[cid]
    alias, ev = {}, []
    for i, e in enumerate(rows, 1):
        a = f'E{i}'
        alias[a] = e['id']
        ev.append({'id': a, 'source_type': source_type_of(e), 'organisation': organisation(e), 'direction': e.get('direction'),
                   'claim': (e.get('claim') or '')[:240], 'excerpt': (e.get('excerpt') or '')[:400], 'geography': e.get('geography'),
                   'published': e.get('published_on'), 'n': e.get('sample_size')})
    ji = c['judge_instruction']
    ctx = {'check': {'id': cid, 'question': ji['question'], 'weak': ji.get('weak'), 'mixed': ji.get('mixed'), 'strong': ji.get('strong')},
           'founder_brief': {k: brief.get(k if k != 'idea' else 'idea_summary') for k in c['brief_fields'] if k not in ('time',)} | ({'timeline': brief.get('timeline')} if 'time' in c['brief_fields'] else {}),
           'accepted_evidence': ev,
           'rules': 'Answer this ONE check only. rating is WEAK, MIXED, STRONG or INSUFFICIENT. Cite E-ids. Use only accepted_evidence and the brief. '
                    'If the evidence does not answer the question, return INSUFFICIENT. Do not add facts, numbers, URLs, competitors or sources.'}
    return ctx, alias


def validate_judgment(cid: str, out: dict, alias: dict, rows: list[dict]) -> dict:
    """Code validation + code caps. Returns {valid, rating, evidence_ids, reasoning, caps[], rejected_reason}."""
    res = {'valid': False, 'rating': None, 'evidence_ids': [], 'reasoning': '', 'caps': [], 'rejected_reason': None}
    if str(out.get('check_id') or '').strip() != cid:
        res['rejected_reason'] = f'judge answered {out.get("check_id")!r}, expected {cid}'
        return res
    rating = str(out.get('rating') or '').upper().strip()
    if rating not in RATINGS:
        res['rejected_reason'] = f'rating {rating!r} is not WEAK/MIXED/STRONG/INSUFFICIENT'
        return res
    cited = [str(x).strip() for x in (out.get('evidence_ids') or [])]
    bad = [x for x in cited if x not in alias]
    if bad:
        res['rejected_reason'] = f'cited evidence ids not in the accepted set: {bad}'
        return res
    reasoning = str(out.get('reasoning') or '')[:500]
    if _URL.search(reasoning):
        res['rejected_reason'] = 'judge introduced a URL'
        return res
    by = {e['id']: e for e in rows}
    corpus = ' '.join(str(by[alias[a]].get(k) or '') for a in cited for k in ('claim', 'excerpt', 'sample_size', 'positives', 'published_on')) + ' ' + ' '.join(cited)
    stray = [n for n in _NUM.findall(reasoning) if n not in corpus]
    if stray:
        res['rejected_reason'] = f'judge introduced numbers not in the cited evidence: {stray[:3]}'
        return res
    if rating == 'INSUFFICIENT':
        res.update(valid=True, rating=None, reasoning=reasoning, evidence_ids=[alias[a] for a in cited])
        return res
    if not cited:
        res['rejected_reason'] = 'a rating without cited evidence is UNKNOWN'
        return res
    real = [by[alias[a]] for a in cited]
    caps = []
    if rating == 'WEAK' and not any(e.get('direction') == 'CONTRADICTS' for e in real):
        res.update(valid=True, rating=None, reasoning=reasoning, evidence_ids=[alias[a] for a in cited],
                   caps=['WEAK needs negative evidence (a cited row that challenges the claim); none was cited, so this stays UNKNOWN.'])
        return res
    if rating == 'STRONG':
        need = max(1, OV[cid]['sources_required'])
        orgs = {organisation(e) for e in rows if e.get('direction') == 'SUPPORTS'}
        if len(orgs) < need:
            rating = 'MIXED'
            caps.append(f'STRONG needs {need} independent organisations supporting it; found {len(orgs)}.')
        elif not any(machine_verified(e) for e in real):
            rating = 'MIXED'
            caps.append('STRONG needs at least one machine-verified excerpt or observed customer action; the cited rows are founder-supplied only.')
        elif any(e.get('direction') == 'CONTRADICTS' for e in rows):
            rating = 'MIXED'
            caps.append('Accepted evidence also challenges this check; contradictions are preserved, so the rating is capped at MIXED.')
        if rating == 'STRONG' and cid in ABSENCE:
            rating = 'MIXED'
            caps.append(OV[cid]['absence_claim_cap'])
    res.update(valid=True, rating=rating, reasoning=reasoning, evidence_ids=[alias[a] for a in cited], caps=caps)
    return res


def cache_key(cid: str, rows: list[dict], model: str) -> str:
    return hashlib.sha256(json.dumps([cid, FILE_HASH, model, sorted((e['id'], e.get('direction'), e.get('review_state')) for e in rows)]).encode()).hexdigest()


# ----------------------------------------------------------------------------- evaluation
def _queries_for(cid: str, runs: list[dict]) -> list[dict]:
    return [{'provider': r['provider'], 'query': r['query'], 'status': r['status'], 'error': r.get('error'), 'at': r['created_at']}
            for r in runs if r.get('subcriterion_id') == cid]


def next_step(cid: str, status: str, have: int, need: int) -> str:
    types = ', '.join(SOURCE_TYPES[t].split('.')[0].lower() for t in OV[cid]['accepted_source_types'] if t != 'BRIEF')
    if status in ('UNKNOWN',) and have == 0:
        return f'Find {need or 1} independent source(s) of this kind: {types}. Inspect the page, pick the exact passage, link it to this check and complete the relevance review.'
    if status == 'AWAITING_JUDGE':
        return 'Evidence is linked. Press "Judge this check" (one local-model call), or re-evaluate the Discover gate.'
    if status in ('MIXED', 'WEAK') and have < need:
        return f'{need - have} more independent organisation(s) would let the judge reach a firmer rating.'
    if status == 'STRONG':
        return 'Keep the sources; look for evidence that would challenge this (contradictions are kept).'
    return 'Add evidence from a different organisation, especially any that challenges the claim.'


def evaluate_check(cid: str, brief: dict, evidence: list[dict], quality: dict, judgment: dict | None, runs: list[dict],
                   safety_rows: dict | None = None) -> dict:
    c = BY_ID[cid]
    ov = OV[cid]
    base = {'id': cid, 'dimension': DIMENSION_OF[cid], 'type': c['type'], 'kind': c['kind'], 'question': c['judge_instruction']['question'],
            'definitions': {k: v for k, v in c['judge_instruction'].items() if k != 'question'}, 'research_instruction': c['research_instruction'],
            'brief_fields': c['brief_fields'], 'sources_required': ov['sources_required'], 'accepted_source_types': ov['accepted_source_types'],
            'provenance': PROVENANCE[cid], 'absence_claim_cap': ov.get('absence_claim_cap'), 'queries_tried': _queries_for(cid, runs),
            'status': 'UNKNOWN', 'score': None, 'basis': None, 'evidence_ids': [], 'supporting_ids': [], 'contradicting_ids': [],
            'rejected': [], 'independent_organisations': [], 'caps': [], 'reasoning': ''}
    if c['kind'] == 'knockout':
        row = (safety_rows or {}).get(cid) or {}
        base['status'] = row.get('outcome') or 'NOT_SCREENED'
        base['basis'] = (row.get('reasons') or [None])[0] or ('No issue detected by the written rule. This is not legal clearance.' if row.get('outcome') == 'CLEAR' else None)
        base['spans'] = row.get('spans') or []
        base['official_source'] = row.get('official_source')
        base['next_step'] = ('Attach an official regulator/statute page on the Safety screen.' if cid in ('illegal_in_target_market', 'regulated_or_sensitive_area')
                             else 'Enforced by the written safety rule; revise the brief if it is flagged.')
        return base
    linked = [e for e in evidence if e.get('subcriterion_id') == cid]
    ok_rows = []
    for e in linked:
        good, why = eligibility(e, cid, quality)
        (ok_rows.append(e) if good else base['rejected'].append({'id': e['id'], 'reason': why}))
    base['evidence_ids'] = [e['id'] for e in ok_rows]
    base['supporting_ids'] = [e['id'] for e in ok_rows if e.get('direction') == 'SUPPORTS']
    base['contradicting_ids'] = [e['id'] for e in ok_rows if e.get('direction') == 'CONTRADICTS']
    base['independent_organisations'] = sorted({organisation(e) for e in ok_rows})
    base['sources_accepted'] = len(base['independent_organisations'])
    cond = brief_condition(cid, brief, evidence)
    if not ok_rows:
        if cond:
            base.update(status=cond['status'], basis=cond['basis'], score=RATING_SCORE.get(cond['status']))
        else:
            base['basis'] = 'No eligible, accepted, relevant evidence is linked to this check. UNKNOWN is not a low score.'
        base['next_step'] = next_step(cid, base['status'], 0, ov['sources_required'])
        base['missing'] = f'{ov["sources_required"]} independent source(s) of an accepted type' if ov['sources_required'] else 'nothing external required'
        return base
    if not judgment:
        base.update(status='AWAITING_JUDGE', basis=f'{len(ok_rows)} eligible row(s) from {base["sources_accepted"]} organisation(s) await a judging pass.')
    elif not judgment.get('valid'):
        base.update(status='UNKNOWN', basis='Judge output rejected by code: ' + str(judgment.get('rejected_reason')))
    elif judgment.get('rating') is None:
        base.update(status='UNKNOWN', basis=judgment.get('reasoning') or 'The judge found the evidence insufficient.', caps=judgment.get('caps', []))
    else:
        base.update(status=judgment['rating'], score=RATING_SCORE[judgment['rating']], basis='Validated judgment, capped by code rules.',
                    reasoning=judgment.get('reasoning', ''), caps=judgment.get('caps', []), cited_ids=judgment.get('evidence_ids', []))
    if cond and cond['status'] == 'WEAK' and base['status'] in ('UNKNOWN', 'AWAITING_JUDGE'):
        base['caps'] = base['caps'] + [cond['basis']]
    base['next_step'] = next_step(cid, base['status'], base['sources_accepted'], ov['sources_required'])
    base['missing'] = None if base['sources_accepted'] >= ov['sources_required'] else f'{ov["sources_required"] - base["sources_accepted"]} more independent organisation(s)'
    return base


def aggregate(dim: str, rows: list[dict]) -> dict:
    known = [r for r in rows if r['status'] in RATING_SCORE]
    na = [r for r in rows if r['status'] == 'NOT_APPLICABLE']
    unknown = [r for r in rows if r['status'] not in RATING_SCORE and r['status'] != 'NOT_APPLICABLE']
    # A dimension score needs >= MIN_KNOWN rated checks AND at least one rating grounded in linked evidence:
    # brief-condition WEAKs alone never produce a dimension score.
    evidence_based = [r for r in known if r.get('evidence_ids')]
    score = round(sum(RATING_SCORE[r['status']] for r in known) / len(known), 1) if len(known) >= MIN_KNOWN and evidence_based else None
    return {'dimension': dim, 'name': DIM_NAMES[dim], 'checks': len(rows), 'known': len(known), 'min_known': MIN_KNOWN, 'unknown': len(unknown), 'not_applicable': len(na),
            'score': score, 'counts': {s: sum(1 for r in rows if r['status'] == s) for s in ('STRONG', 'MIXED', 'WEAK', 'AWAITING_JUDGE', 'UNKNOWN', 'NOT_APPLICABLE')},
            'evidence_based': len(evidence_based),
            'rule': f'Mean of mapped ratings (WEAK 2, MIXED 3, STRONG 4) when at least {MIN_KNOWN} checks are rated and at least one rating rests on linked evidence; otherwise no granular score.'}


RISK_ORDER = ('D04', 'D03', 'D07', 'D06', 'D05')


def evaluate(brief: dict, evidence: list[dict], quality: dict, judgments: dict, runs: list[dict], safety_assessment: dict | None) -> dict:
    srows = {r['rule_id']: r for r in (safety_assessment or {}).get('rules', [])}
    checks = [evaluate_check(c['id'], brief, evidence, quality, judgments.get(c['id']), runs, srows) for c in CHECKS]
    by_dim = {d: [r for r in checks if r['dimension'] == d] for d in EXPECTED_COUNTS}
    dims = {d: aggregate(d, by_dim[d]) for d in SCORED_DIMS}
    d01 = by_dim['D01']
    dims['D01'] = {'dimension': 'D01', 'name': DIM_NAMES['D01'], 'checks': 12,
                   'counts': {s: sum(1 for r in d01 if r['status'] == s) for s in ('HARD_STOP', 'REVIEW_REQUIRED', 'UNKNOWN_SOURCE', 'CLEAR', 'NOT_APPLICABLE', 'NOT_SCREENED')},
                   'rule': 'Any HARD_STOP stops the venture (non-overridable). REVIEW_REQUIRED needs your research-only acknowledgement. CLEAR is not legal clearance.'}
    return {'version': VERSION, 'file_sha256': FILE_HASH, 'checks': checks, 'dimensions': dims,
            'priority': [r['id'] for d in RISK_ORDER for r in by_dim[d] if r['status'] in ('UNKNOWN', 'AWAITING_JUDGE')][:12]}


def judgeable(evidence: list[dict], quality: dict, only: str | None = None) -> list[tuple[str, list[dict]]]:
    out = []
    for d in RISK_ORDER:
        for cid in BY_DIMENSION[d]:
            if only and only not in (cid, d):
                continue
            rows = [e for e in evidence if eligibility(e, cid, quality)[0]]
            if rows:
                out.append((cid, rows))
    return out


# ----------------------------------------------------------------------------- research queries per check
_STOP = set('a an and are as at be by for from has have i in into is it its my of on or our so that the their them they this to was we what when which who will with would want build tool app simple help helps using use based'.split())


def keyphrase(text: str | None, n: int = 5) -> str:
    """Content words in their original order; never cuts a word in half."""
    words, seen = [], set()
    for w in re.findall(r"[A-Za-z؀-ۿ][A-Za-z؀-ۿ0-9'\-]*", text or ''):
        lw = w.lower()
        if lw in _STOP or lw in seen or len(lw) < 3:
            continue
        seen.add(lw)
        words.append(w)
        if len(words) >= n:
            break
    return ' '.join(words)


SUFFIX = {
    'must_have_pain': 'forum complaints', 'current_workaround_pain': 'how do you currently', 'narrow_early_adopter': 'association directory',
    'paying_customer_identified': 'who pays pricing', 'reachable_path_to_customers': 'community group association', 'problem_framed_from_customer_view': 'forum',
    'current_alternatives_in_use': 'software tools used', 'paid_alternatives_exist': 'pricing', 'customer_own_words': 'reddit forum',
    'action_over_stated_interest': 'case study customers', 'substitutes_in_use': 'alternatives', 'direct_competitors_mapped': 'software competitors',
    'competitor_target_segments': 'pricing plans', 'competitor_weak_points': 'reviews complaints', 'price_gaps': 'pricing', 'underserved_segment': 'small businesses underserved',
    'incumbent_differentiation_level': 'comparison', 'dominant_player_edge': 'market share', 'retaliation_risk': 'price cut competitor response',
    'substitution_threat': 'new technology', 'entry_barriers_for_newcomers': 'barriers to entry', 'difference_hard_to_copy': 'feature copied competitor',
    'difference_valued_by_customers': 'reviews', 'price_war_exposure': 'price war', 'market_maturity_crowding': 'market growth competitors',
    'skills_match_product': 'developer skills required', 'market_understanding': 'buyer behaviour', 'skill_gaps_fillable': 'freelancer cost',
    'help_network_available': 'founder community', 'critical_resources_available': 'resources needed', 'specialized_talent_available': 'salary survey',
    'no_blocking_patent': 'patent', 'regulatory_barriers_manageable': 'regulation licence', 'startup_cash_within_budget': 'cost to build',
    'unexpected_costs_buffer': 'hidden costs overruns', 'cash_source_explained': 'bootstrapping funding', 'own_funds_cover_first_version': 'MVP cost no-code',
    'breakeven_time_fit': 'break-even time', 'time_commitment_fit': 'hours per week build', 'build_parts_manageable': 'architecture components',
    'revenue_streams_named': 'pricing model', 'known_model_precedent': 'business model', 'comparable_firms_revenue': 'revenue', 'buyers_show_willingness_to_pay': 'pre-order crowdfunding',
    'payer_identified': 'who pays', 'enough_payers_at_price': 'number of customers price', 'price_vs_substitutes': 'price', 'free_alternatives_threat': 'free',
    'charge_not_easily_bypassed': 'platform leakage commission', 'price_covers_costs': 'cost to serve', 'cost_structure_understood': 'cost structure',
    'free_tier_converts': 'freemium conversion', 'recurring_revenue': 'subscription churn', 'existing_paying_habit': 'spend on',
}


def check_queries(cid: str, brief: dict) -> dict:
    """Queries built from STRUCTURED brief fields (segment, problem, place). Never from truncated raw text."""
    fields = brief.get('fields') or {}

    def fv(k):
        f = fields.get(k) or {}
        return f.get('value') if f.get('status') in ('FORM_FIELD', 'FOUNDER_CONFIRMED', 'STATED_IN_TEXT') else brief.get(k)
    seg = keyphrase(re.sub(r'\(.*?\)', '', fv('target_customers') or ''), 3)
    prob = keyphrase(fv('problem'), 4)
    tm = (fields.get('target_market') or {}).get('typed') or {}
    place = tm.get('city') or tm.get('country') or keyphrase(fv('target_market'), 2)
    topic = keyphrase(brief.get('idea_summary'), 4)
    suffix = SUFFIX.get(cid, '')
    core = ' '.join(x for x in (seg, prob or topic) if x)
    q = ' '.join(x for x in (core, suffix, place if cid not in ('no_blocking_patent', 'skills_match_product', 'known_model_precedent') else '') if x).strip()
    types = OV[cid]['accepted_source_types']
    from urllib.parse import quote_plus
    manual = [{'label': 'Open web search', 'url': 'https://duckduckgo.com/?q=' + quote_plus(q)}]
    if 'PATENT_RECORD' in types:
        manual.insert(0, {'label': 'Search Google Patents', 'url': 'https://patents.google.com/?q=' + quote_plus(keyphrase(brief.get('idea_summary') or core, 6))})
    if 'OFFICIAL_SOURCE' in types and place:
        manual.append({'label': 'Search government sites', 'url': 'https://duckduckgo.com/?q=' + quote_plus(f'{topic} regulation {place} site:gov' + ('.eg' if tm.get('country') == 'Egypt' else ''))})
    academic = 'ACADEMIC_PASSAGE' in types
    return {'check_id': cid, 'query': q, 'built_from': {'segment': seg or None, 'problem': prob or None, 'place': place or None, 'topic': topic or None},
            'automated_providers': (['openalex', 'crossref'] if academic else []),
            'automated_note': ('Academic indexes return metadata about papers. Only an inspected passage can count, and only as background for this check.'
                               if academic else 'No compliant automated search exists for this source type in FounderOS. Use the manual search links and paste pages to inspect.'),
            'manual_searches': manual}

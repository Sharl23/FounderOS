"""Criteria engine: all 9 Discover, 7 Validate and 5 cross-cutting criteria from policy/criteria.yaml.

Criteria PDF rules implemented here (p.10 "Seven rules"):
 1 criteria live in their own file (policy/criteria.yaml), not in prompts;
 2 the policy version+hash and the project's config hash are stored with every evaluation/decision;
 3 the judge is asked about ONE criterion per call;
 4 the judge sees only accepted ledger evidence (gatherer and judge are separate);
 5 every score needs a reason and an evidence reference, otherwise UNKNOWN;
 6 arithmetic and pass marks are applied here, in code — the model never picks the exit;
 7 founders may adjust weights/pass marks before a run; safety knockouts stay fixed.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
from datetime import date
from pathlib import Path

import yaml

POLICY_PATH = Path(__file__).resolve().parents[1] / 'policy' / 'criteria.yaml'
POLICY = yaml.safe_load(POLICY_PATH.read_text(encoding='utf-8'))
VERSION = POLICY['version']
POLICY_HASH = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
SCALE = POLICY['scale_anchored_1_5']
CAPS = POLICY['evidence_caps']

DISCOVER = POLICY['discover']['criteria']
VALIDATE = POLICY['validate']['criteria']
CROSS = POLICY['cross_cutting']['criteria']
ARCHITECTURE = POLICY['architecture_only']
BY_ID = {c['id']: c for c in DISCOVER + VALIDATE + CROSS}
assert len(DISCOVER) == 9 and len(VALIDATE) == 7 and len(CROSS) == 5
assert sum(len(v['criteria']) for v in ARCHITECTURE.values()) == 17
KINDS = ('knockout', 'scored', 'evidence_standard', 'threshold', 'output_check')
assert all(c['kind'] in KINDS for c in BY_ID.values())

SCORED_DISCOVER = [c['id'] for c in DISCOVER if c['kind'] == 'scored']          # D03–D07
SCORED_VALIDATE = ['V01', 'V02', 'V03']                                          # V03 'scored otherwise'
JUDGEABLE = set(SCORED_DISCOVER + SCORED_VALIDATE)


def stable_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


# ----------------------------------------------------------------------------- founder-adjustable config
def default_config() -> dict:
    weights = {c['id']: c['weight'] for c in DISCOVER + VALIDATE if c.get('weight') is not None}
    d09 = BY_ID['D09']['thresholds']
    return {'weights': weights,
            'discover_gate': {'pass_mark': d09['pass_mark'], 'pivot_mark': d09['pivot_mark'], 'max_unknown_scored': d09['max_unknown_scored']},
            'evidence': {'max_age_years': BY_ID['X01']['max_age_years']},
            'results': {'near_miss_band': BY_ID['V06']['near_miss_band']},
            'origin': 'TEAM_ASSUMPTION defaults from policy/criteria.yaml'}


EDITABLE_WEIGHTS = {c['id'] for c in DISCOVER + VALIDATE if c.get('founder_editable') and c.get('weight') is not None}


def apply_changes(base: dict, changes: dict) -> dict:
    """Validate a founder change. Knockouts, safety and exit semantics are not configurable."""
    cfg = copy.deepcopy(base)
    allowed_top = {'weights', 'discover_gate', 'evidence', 'results'}
    bad = set(changes) - allowed_top
    if bad:
        raise ValueError(f'Not editable: {sorted(bad)}. Safety rules, knockouts and exit semantics cannot be changed.')
    for k, v in (changes.get('weights') or {}).items():
        if k not in EDITABLE_WEIGHTS:
            raise ValueError(f'Weight for {k} is not founder-editable.')
        if not isinstance(v, (int, float)) or not 0 < v <= 10:
            raise ValueError('Weights must be numbers in (0, 10].')
        cfg['weights'][k] = v
    g = changes.get('discover_gate') or {}
    for k, v in g.items():
        if k not in ('pass_mark', 'pivot_mark', 'max_unknown_scored'):
            raise ValueError(f'discover_gate.{k} is not editable')
        cfg['discover_gate'][k] = v
    dg = cfg['discover_gate']
    if not (1 <= dg['pivot_mark'] < dg['pass_mark'] <= 5):
        raise ValueError('Need 1 <= pivot_mark < pass_mark <= 5.')
    if not (isinstance(dg['max_unknown_scored'], int) and 0 <= dg['max_unknown_scored'] <= 5):
        raise ValueError('max_unknown_scored must be an integer 0–5.')
    if 'evidence' in changes:
        age = changes['evidence'].get('max_age_years')
        if not isinstance(age, int) or not 1 <= age <= 30:
            raise ValueError('max_age_years must be an integer 1–30.')
        cfg['evidence']['max_age_years'] = age
    if 'results' in changes:
        band = changes['results'].get('near_miss_band')
        if not isinstance(band, (int, float)) or not 0 <= band <= 0.5:
            raise ValueError('near_miss_band must be between 0 and 0.5.')
        cfg['results']['near_miss_band'] = band
    cfg['origin'] = 'FOUNDER_ADJUSTED (labelled assumptions, set before the run)'
    return cfg


# ----------------------------------------------------------------------------- X01 evidence quality
STRENGTH = {'PRE_REGISTERED_EXPERIMENT_RESULT': 4, 'CUSTOMER_BEHAVIOR': 3, 'CUSTOMER_STATEMENT': 2, 'SECONDARY_BACKGROUND': 1}


def _year(s):
    m = re.search(r'(19|20)\d{2}', str(s or ''))
    return int(m.group(0)) if m else None


def evidence_quality(e: dict, brief: dict | None, cfg: dict, live_experiments: dict | None = None) -> dict:
    """X01: grade one ledger row. Returns {counts: bool, grade, flags[], exclusion}."""
    from .decision import exclusion_reason
    flags = []
    reason = exclusion_reason(e, live_experiments if live_experiments is not None else {})
    if e.get('excerpt_status') == 'METADATA_ONLY':
        reason = reason or 'METADATA_ONLY: bibliographic metadata/abstract, not an inspected passage.'
    if reason:
        return {'counts': False, 'grade': 'EXCLUDED', 'exclusion': reason, 'flags': flags}
    kind = e['kind']
    if kind == 'SECONDARY_BACKGROUND':
        grade = 'CONTEXT_ONLY'
        y = _year(e.get('published_on'))
        if not y:
            flags.append('Publication date unknown.')
        elif date.today().year - y > cfg['evidence']['max_age_years']:
            flags.append(f'Published {y}: older than {cfg["evidence"]["max_age_years"]} years.')
        if not (e.get('publisher') or e.get('title')):
            flags.append('Publisher/title unknown.')
        target = ((brief or {}).get('target_market') or '').lower()
        geo = (e.get('geography') or '').lower()
        if not geo:
            flags.append('Geography not stated: relevance to the target market unknown.')
        elif target and not any(w in target for w in re.findall(r'[a-z]{4,}', geo)) and not any(w in geo for w in re.findall(r'[a-z]{4,}', target)):
            flags.append(f'Geography "{e.get("geography")}" does not match target market "{(brief or {}).get("target_market")}".')
        if e.get('relevance') != 'CLAIM_RELEVANT' and e.get('review_state') != 'ACCEPTED_RELEVANT':
            flags.append('Relevance to the claim not confirmed by the founder.')
        if e.get('url_status') == 'FOUNDER_SUPPLIED':
            flags.append('Founder-supplied excerpt: the page could not be fetched, so it was NOT automatically verified.')
        stale = any(f.startswith('Published ') for f in flags)
        offmarket = any(f.startswith('Geography "') for f in flags)
        if stale and offmarket:
            return {'counts': False, 'grade': 'EXCLUDED', 'flags': flags,
                    'exclusion': 'Fails the evidence standard: older than the age limit AND about a different geography.'}
        if flags:
            grade = 'CONTEXT_WEAK'
    elif kind == 'CUSTOMER_STATEMENT':
        grade = 'DIRECT_STATEMENT'
        flags.append('Stated opinion, not behaviour. Founder-reported.')
    elif kind == 'CUSTOMER_BEHAVIOR':
        grade = 'DIRECT_BEHAVIOR'
        flags.append('Founder-reported, not independently verified.')
    else:
        grade = 'LOCKED_RESULT'
        flags.append('Founder-reported result against locked criteria.')
    if e.get('sample_size') and e['sample_size'] < 10 and kind != 'SECONDARY_BACKGROUND':
        flags.append(f'Small sample (n={e["sample_size"]}).')
    return {'counts': True, 'grade': grade, 'exclusion': None, 'flags': flags}


def annotate(evidence: list[dict], brief: dict | None, cfg: dict) -> list[dict]:
    """Mark rows that fail X01 on recency+geography so the verdict engine excludes them consistently."""
    out = []
    for e in evidence:
        e = dict(e)
        if e['kind'] == 'SECONDARY_BACKGROUND':
            q = evidence_quality(e, brief, cfg, {})
            e['stale_and_offmarket'] = q['grade'] == 'EXCLUDED' and (q['exclusion'] or '').startswith('Fails the evidence standard')
        out.append(e)
    return out


def _accepted(evidence, quality, dimension, cid):
    out = []
    for e in evidence:
        q = quality[e['id']]
        if not q['counts']:
            continue
        if e.get('criterion_id') and e.get('criterion_id') != cid:
            continue
        if e.get('criterion_id') == cid or e.get('dimension') == dimension:
            out.append(e)
    return out


# ----------------------------------------------------------------------------- hard limits (D06, V03, X02)
def _money(s):
    if s is None:
        return None
    t = str(s).lower().replace(',', '')
    if re.search(r'\b(zero|none|no budget|free)\b', t) or re.fullmatch(r'\s*0\s*\w*\s*', t):
        return 0.0
    m = re.search(r'(\d+(\.\d+)?)\s*(k)?', t)
    if not m:
        return None
    return float(m.group(1)) * (1000 if m.group(3) else 1)


def _days(s):
    if s is None:
        return None
    from .brief_extract import duration
    r = duration(str(s))
    return r[0] if r else None


def hard_limits(brief: dict, experiments: list[dict]) -> dict:
    budget, days = _money(brief.get('budget')), _days(brief.get('timeline'))
    checks, fails = [], []
    for x in experiments:
        if x['status'] not in ('DRAFT', 'LOCKED'):
            continue
        p = x['payload']
        cost = _money(p.get('cost_estimate'))
        window = p.get('time_window_days') or _days(p.get('timebox_estimate'))
        if budget is not None and cost is not None:
            ok = cost <= budget
            checks.append(f'Experiment {x["id"][:8]} v{x["version"]}: cost {cost:g} vs budget {budget:g} — {"OK" if ok else "EXCEEDS"}')
            if not ok:
                fails.append(checks[-1])
        if days is not None and window is not None:
            ok = float(window) <= days
            checks.append(f'Experiment {x["id"][:8]} v{x["version"]}: {float(window):g} days vs timeline {days:g} days — {"OK" if ok else "EXCEEDS"}')
            if not ok:
                fails.append(checks[-1])
    unknown = []
    if budget is None:
        unknown.append('budget not stated or not a number')
    if days is None:
        unknown.append('timeline not stated in days/weeks/months')
    status = 'FAIL' if fails else ('UNKNOWN' if unknown and not checks else 'PASS')
    return {'status': status, 'budget': budget, 'timeline_days': days, 'checks': checks, 'failures': fails, 'unknown': unknown}


# ----------------------------------------------------------------------------- judge contract
_URL = re.compile(r'https?://|www\.', re.I)
_NUM = re.compile(r'\d+(?:[.,]\d+)?')


def judge_input(cid: str, brief: dict, rows: list[dict], quality: dict) -> tuple[dict, dict]:
    """Build the bounded judge context. Evidence ids are aliased E1..En for a small model."""
    c = BY_ID[cid]
    alias = {}
    ev = []
    for i, e in enumerate(rows, 1):
        a = f'E{i}'
        alias[a] = e['id']
        ev.append({'id': a, 'class': e['kind'], 'quality': quality[e['id']]['grade'], 'direction': e.get('direction'),
                   'claim': (e.get('claim') or '')[:240], 'excerpt': (e.get('excerpt') or '')[:400],
                   'segment': e.get('segment'), 'geography': e.get('geography'), 'n': e.get('sample_size'),
                   'positives': e.get('positives'), 'outcome': e.get('outcome'), 'flags': quality[e['id']]['flags'][:3]})
    ctx = {'criterion': {'id': cid, 'name': c['name'], 'question': c['question'], 'scale': SCALE},
           'founder_constraints': {k: brief.get(k) for k in ('target_customers', 'target_market', 'budget', 'timeline', 'skills', 'values')},
           'accepted_evidence': ev,
           'rules': 'Score ONLY from accepted_evidence. Cite evidence ids (E1..). If evidence is insufficient return proposed_score null. Do not add facts, numbers, URLs or competitors not in the evidence.'}
    return ctx, alias


def validate_judgment(cid: str, out: dict, alias: dict, rows: list[dict], brief: dict) -> dict:
    """Backend validation of a judge output. Returns {valid, score, evidence_ids, reasoning, caveats, rejected_reason, capped}."""
    res = {'valid': False, 'score': None, 'evidence_ids': [], 'reasoning': '', 'caveats': [], 'rejected_reason': None, 'capped': None}
    if out.get('criterion_id') != cid:
        res['rejected_reason'] = f'judge answered criterion {out.get("criterion_id")!r}, expected {cid}'
        return res
    cited = [str(x).strip() for x in (out.get('evidence_ids') or [])]
    bad = [x for x in cited if x not in alias]
    if bad:
        res['rejected_reason'] = f'cited evidence ids not in the accepted ledger: {bad}'
        return res
    reasoning = str(out.get('reasoning') or '')[:600]
    caveats = [str(x)[:200] for x in (out.get('caveats') or [])][:4]
    text = reasoning + ' ' + ' '.join(caveats)
    if _URL.search(text):
        res['rejected_reason'] = 'judge introduced a URL not in the evidence'
        return res
    by_id = {e['id']: e for e in rows}
    corpus = ' '.join(str(by_id[alias[a]].get(k) or '') for a in cited for k in ('claim', 'excerpt', 'sample_size', 'positives', 'rate_pct', 'published_on'))
    corpus += ' ' + ' '.join(str(brief.get(k) or '') for k in ('budget', 'timeline', 'target_market', 'target_customers'))
    corpus += ' ' + ' '.join(cited) + ' 1 2 3 4 5'
    stray = [n for n in _NUM.findall(text) if n not in corpus]
    if stray:
        res['rejected_reason'] = f'judge introduced numbers not present in cited evidence: {stray[:4]}'
        return res
    score = out.get('proposed_score')
    if score is None:
        res.update(valid=True, reasoning=reasoning, caveats=caveats, evidence_ids=[alias[a] for a in cited])
        return res
    if not isinstance(score, int) or not 1 <= score <= 5:
        res['rejected_reason'] = f'score {score!r} outside the 1–5 scale'
        return res
    if not cited:
        res['rejected_reason'] = 'a score without an evidence reference is UNKNOWN (PDF p.10 rule 5)'
        return res
    real = [by_id[alias[a]] for a in cited]
    strongest = max(real, key=lambda e: STRENGTH[e['kind']])
    cap = CAPS[strongest['kind']]
    if cid == 'D04' and POLICY.get('demand_requires_behavior') and not any(e['kind'] in ('CUSTOMER_BEHAVIOR', 'PRE_REGISTERED_EXPERIMENT_RESULT') for e in real):
        cap = min(cap, 3)
    dirs = {e.get('direction') if e['kind'] != 'PRE_REGISTERED_EXPERIMENT_RESULT' else {'PASS': 'SUPPORTS', 'FAIL': 'CONTRADICTS'}.get(e.get('outcome'), 'UNSURE') for e in real}
    if dirs == {'CONTRADICTS'} and score > 2:
        res['rejected_reason'] = 'score is inconsistent with the cited evidence, which only contradicts the claim'
        return res
    if score > cap:
        res['capped'] = f'proposed {score} capped to {cap}: strongest cited evidence is {strongest["kind"]}'
        score = cap
    res.update(valid=True, score=score, evidence_ids=[alias[a] for a in cited], reasoning=reasoning, caveats=caveats)
    return res


def judge_cache_key(cid, rows, quality, model):
    return stable_hash([cid, POLICY_HASH, model, sorted((e['id'], quality[e['id']]['grade'], e.get('direction')) for e in rows)])


# ----------------------------------------------------------------------------- shared prep
def prepare(brief: dict, evidence: list[dict], experiments: list[dict], cfg: dict):
    live = {x['id']: x for x in experiments if x['status'] == 'LOCKED'}
    quality = {e['id']: evidence_quality(e, brief, cfg, live) for e in evidence}
    return quality


def _row(cid, **kw):
    c = BY_ID[cid]
    base = {'id': cid, 'name': c['name'], 'kind': c['kind'], 'question': c['question'], 'pdf_page': c.get('pdf_page'),
            'origin': c['origin'], 'status': 'UNKNOWN', 'score': None, 'evidence_ids': [], 'reasoning': '', 'caveats': [],
            'unknown': True, 'details': {}}
    base.update(kw)
    return base


def _scored(cid, brief, evidence, quality, judgments):
    c = BY_ID[cid]
    rows = _accepted(evidence, quality, c.get('dimension'), cid)
    if not rows:
        return _row(cid, status='UNKNOWN', reasoning='No accepted, relevant evidence. UNKNOWN is not a low score.',
                    details={'accepted_evidence': 0})
    j = (judgments or {}).get(cid)
    ids = [e['id'] for e in rows]
    if not j:
        return _row(cid, status='AWAITING_JUDGE', evidence_ids=ids,
                    reasoning=f'{len(rows)} accepted evidence row(s) await a judging pass. Until then this counts as UNKNOWN.',
                    details={'accepted_evidence': len(rows)})
    if not j.get('valid'):
        return _row(cid, status='UNKNOWN', evidence_ids=ids, reasoning='Judge output was rejected by backend validation: ' + str(j.get('rejected_reason')),
                    details={'accepted_evidence': len(rows), 'judge': j})
    if j.get('score') is None:
        return _row(cid, status='UNKNOWN', evidence_ids=j['evidence_ids'], reasoning=j.get('reasoning') or 'Judge found the evidence insufficient.',
                    caveats=j.get('caveats', []), details={'accepted_evidence': len(rows), 'judge': j})
    cav = list(j.get('caveats', []))
    if j.get('capped'):
        cav.append(j['capped'])
    return _row(cid, status='SCORED', score=j['score'], evidence_ids=j['evidence_ids'], reasoning=j['reasoning'], caveats=cav,
                unknown=False, details={'accepted_evidence': len(rows), 'judge': j, 'scale_meaning': SCALE[str(j['score'])]})


def _cross(brief, safety, safety_ack, evidence, quality, experiments, agent_flags, approvals_scope, blocked_actions):
    rows = []
    counted = [e for e in evidence if quality[e['id']]['counts']]
    excluded = [{'id': e['id'], 'reason': quality[e['id']]['exclusion']} for e in evidence if not quality[e['id']]['counts']]
    grades = {}
    for e in counted:
        grades.setdefault(quality[e['id']]['grade'], []).append(e['id'])
    rows.append(_row('X01', status='APPLIED' if evidence else 'UNKNOWN', unknown=not counted,
                     evidence_ids=[e['id'] for e in counted],
                     reasoning=f'{len(counted)} accepted, {len(excluded)} excluded. Excerpt match proves only that the words appear at the URL.',
                     details={'grades': grades, 'excluded': excluded}))
    hl = hard_limits(brief, experiments)
    vals = next((r for r in (safety or {}).get('rules', []) if r['rule_id'] == 'founder_values_conflict'), None)
    vconf = vals and vals['outcome'] == 'REVIEW_REQUIRED'
    x02 = 'FAIL' if hl['status'] == 'FAIL' or (vconf and not safety_ack) else ('UNKNOWN' if hl['status'] == 'UNKNOWN' else 'PASS')
    rows.append(_row('X02', status=x02, unknown=x02 == 'UNKNOWN',
                     reasoning=('Hard limit exceeded. ' if hl['status'] == 'FAIL' else '') + (
                         'Values conflict flagged' + (' and acknowledged (research only).' if safety_ack else ' and not acknowledged.') if vconf else 'No values conflict detected.'),
                     details={'hard_limits': hl}))
    st = (safety or {}).get('status')
    x03 = 'FAIL' if st == 'BLOCK' or agent_flags else ('REVIEW_REQUIRED' if st == 'REVIEW_REQUIRED' and not safety_ack else 'PASS' if st else 'UNKNOWN')
    rows.append(_row('X03', status=x03, unknown=x03 == 'UNKNOWN',
                     reasoning=f'Brief screen: {st or "not run"}. ' + (f'{len(agent_flags)} agent output passage(s) proposed a prohibited tactic.' if agent_flags else 'Agent outputs re-screened: no prohibited tactic.'),
                     details={'agent_output_flags': agent_flags, 'policy_version': (safety or {}).get('policy_version')}))
    rows.append(_row('X04', status='PASS', unknown=False,
                     reasoning='Every approval is RESEARCH_ONLY. Publish/send/spend/sign/pay are not implemented and hard-deny (HTTP 403).',
                     details={'approval_scope': approvals_scope, 'blocked_external_action_attempts': blocked_actions}))
    return rows, counted, excluded, hl


def _x05(rows, counted, excluded):
    unknown = [r['id'] for r in rows if r['unknown']]
    return _row('X05', status='INSUFFICIENT' if len(counted) == 0 else 'REPORTED', unknown=False,
                reasoning=f'{len(unknown)} criteria UNKNOWN; {len(counted)} accepted and {len(excluded)} excluded evidence rows. No probability or confidence percentage is computed.',
                details={'unknown_criteria': unknown, 'accepted_evidence': len(counted), 'excluded_evidence': len(excluded)})


# ----------------------------------------------------------------------------- Discover gate
def _gsum(r):
    return {k: r.get(k) for k in ('id', 'status', 'score', 'basis', 'evidence_ids', 'supporting_ids', 'contradicting_ids', 'independent_organisations',
                                  'sources_required', 'caps', 'question')}


def granular_signature(granular: dict | None):
    return sorted((r['id'], r['status']) for r in (granular or {}).get('checks', []))


def _with_granular(row: dict, granular: dict | None) -> dict:
    """Fold the team rubric's granular checks into D03–D07. Code aggregation only; UNKNOWN never becomes a number."""
    if not granular:
        return row
    agg = granular['dimensions'].get(row['id'])
    if not agg:
        return row
    row['details']['granular'] = [_gsum(r) for r in granular['checks'] if r['dimension'] == row['id']]
    row['details']['granular_summary'] = agg
    if agg['score'] is not None:
        ids = sorted({i for r in granular['checks'] if r['dimension'] == row['id'] for i in r.get('evidence_ids') or []})
        prev = (row['status'], row['score'])
        row.update(status='SCORED', score=agg['score'], unknown=False, evidence_ids=ids,
                   reasoning=f'Aggregated from {agg["known"]} of {agg["checks"]} rated team-rubric checks ({agg["counts"]["STRONG"]} strong, '
                             f'{agg["counts"]["MIXED"]} mixed, {agg["counts"]["WEAK"]} weak); {agg["unknown"]} unknown. {agg["rule"]}')
        row['details']['score_source'] = 'GRANULAR_RUBRIC'
        if prev[0] == 'SCORED':
            row['caveats'].append(f'A dimension-level judgment ({prev[1]}) also exists; the granular aggregate is used.')
    else:
        row['details']['score_source'] = 'DIMENSION_JUDGE' if row['status'] == 'SCORED' else 'NONE'
        if row['status'] != 'SCORED':
            row['reasoning'] = (row['reasoning'] + f' Team rubric: {agg["known"]} of {agg["checks"]} checks rated; at least {agg["min_known"]} are needed for a dimension score.').strip()
    return row


def evaluate_discover(*, brief: dict, brief_version: int, safety: dict | None, safety_ack: bool, discovery: dict | None,
                      discovery_run_id: str | None, evidence: list[dict], experiments: list[dict], judgments: dict, cfg: dict,
                      approvals_scope: str = 'RESEARCH_ONLY', blocked_actions: int = 0, granular: dict | None = None) -> dict:
    quality = prepare(brief, evidence, experiments, cfg)
    rows = []
    st = (safety or {}).get('status')
    d01 = 'FAIL' if st == 'BLOCK' else ('REVIEW_REQUIRED' if st == 'REVIEW_REQUIRED' and not safety_ack else 'PASS' if st else 'UNKNOWN')
    rows.append(_row('D01', status=d01, unknown=d01 == 'UNKNOWN',
                     reasoning={'FAIL': 'Hard stop (non-overridable).', 'REVIEW_REQUIRED': 'Flagged; founder research-only acknowledgment needed.',
                                'PASS': 'No hard stop' + (' (flags acknowledged for research only).' if st == 'REVIEW_REQUIRED' else '.'), 'UNKNOWN': 'Screen not run.'}[d01],
                     details={'safety_status': st, 'counts': (safety or {}).get('counts')}))
    if brief.get('fields'):
        from .brief_extract import d02 as _d02
        dd = _d02(brief['fields'])
        parts = []
        if dd['missing']:
            parts.append('Not stated: ' + ', '.join(dd['missing']) + '.')
        if dd['model_suggested_unconfirmed']:
            parts.append('Only suggested by the model, not confirmed by you: ' + ', '.join(dd['model_suggested_unconfirmed']) + '.')
        if dd['parser_failed']:
            parts.append('The parser failed on: ' + ', '.join(dd['parser_failed']) + ' (this is a software fault, not a missing answer).')
        rows.append(_row('D02', status=dd['status'], unknown=False,
                         reasoning=(' '.join(parts) + ' Answer the question on the Brief page.') if parts else 'Customer, pain and current workaround are captured in your own words or answers.',
                         caveats=[f'{f} was found in your text; please confirm it' for f in dd['stated_in_text_please_confirm']],
                         details={**dd, 'brief_version': brief_version}))
    else:  # briefs created before v0.8 (no typed fields)
        prov = brief.get('provenance', {})
        missing = [f for f in ('target_customers', 'problem', 'current_workaround') if not brief.get(f)]
        inferred = [f for f in ('target_customers', 'problem', 'current_workaround') if brief.get(f) and prov.get(f) == 'INFERRED_UNCONFIRMED']
        rows.append(_row('D02', status='FAIL' if missing else 'PASS', unknown=False,
                         reasoning=('Missing: ' + ', '.join(missing) + '. Answer the clarification on the Brief page.') if missing else 'Customer, pain and current workaround are named.',
                         caveats=[f'{f} is model-inferred and unconfirmed' for f in inferred], details={'missing': missing, 'inferred_unconfirmed': inferred, 'legacy_brief': True}))
    for cid in SCORED_DISCOVER:
        rows.append(_with_granular(_scored(cid, brief, evidence, quality, judgments), granular))
    if granular:
        d01row = rows[0]
        d01row['details']['granular'] = [_gsum(r) for r in granular['checks'] if r['dimension'] == 'D01']
        d01row['details']['granular_summary'] = granular['dimensions']['D01']
    hl = hard_limits(brief, experiments)
    d06 = next(r for r in rows if r['id'] == 'D06')
    d06['details']['hard_limits'] = hl
    if hl['status'] == 'FAIL':
        d06['caveats'].append('HARD LIMIT exceeded: ' + '; '.join(hl['failures']))
    # D08 direction ranking
    directions = (discovery or {}).get('directions') or []
    ranked = []
    for d in directions:
        did = d.get('id')
        linked = [e for e in evidence if e.get('direction_id') == did and quality[e['id']]['counts']]
        dirn = lambda e: {'PASS': 'SUPPORTS', 'FAIL': 'CONTRADICTS'}.get(e.get('outcome'), e.get('direction')) if e['kind'] == 'PRE_REGISTERED_EXPERIMENT_RESULT' else e.get('direction')
        sup = sum(1 for e in linked if dirn(e) == 'SUPPORTS')
        con = sum(1 for e in linked if dirn(e) == 'CONTRADICTS')
        beh = sum(1 for e in linked if e['kind'] in ('CUSTOMER_BEHAVIOR', 'PRE_REGISTERED_EXPERIMENT_RESULT') and dirn(e) == 'SUPPORTS')
        ranked.append({'direction_id': did, 'name': d.get('name'), 'evidence_ids': [e['id'] for e in linked], 'supporting': sup,
                       'contradicting': con, 'behaviour_support': beh, 'net': sup - con})
    with_ev = [r for r in ranked if r['evidence_ids']]
    if len(with_ev) < 2:
        rows.append(_row('D08', status='UNKNOWN', reasoning=f'{len(with_ev)} of {len(directions)} candidate directions have linked accepted evidence; ranking needs at least two. No ranking is manufactured.',
                         details={'directions': ranked}))
    else:
        order = sorted(with_ev, key=lambda r: (-r['behaviour_support'], -r['net']))
        for i, r in enumerate(order):
            r['rank'] = i + 1
            if i and (r['behaviour_support'], r['net']) == (order[i - 1]['behaviour_support'], order[i - 1]['net']):
                r['rank'] = order[i - 1]['rank']
                r['tie'] = True
        ties = any(r.get('tie') for r in order)
        rows.append(_row('D08', status='RANKED_WITH_TIE' if ties else 'RANKED', unknown=False, evidence_ids=[i for r in order for i in r['evidence_ids']],
                         reasoning='Ranked by behaviour-backed support, then net accepted support. ' + ('Tie: the evidence does not separate the leaders.' if ties else ''),
                         details={'directions': order + [r for r in ranked if not r['evidence_ids']]}))
    agent_flags = (discovery or {}).get('_safety_flags') or []
    cross, counted, excluded, _ = _cross(brief, safety, safety_ack, evidence, quality, experiments, agent_flags, approvals_scope, blocked_actions)
    # D09 gate (code only)
    g = cfg['discover_gate']
    w = cfg['weights']
    scored = {r['id']: r for r in rows if r['id'] in SCORED_DISCOVER}
    known = {k: r['score'] for k, r in scored.items() if r['status'] == 'SCORED'}
    unknown_n = len(SCORED_DISCOVER) - len(known)
    mean = round(sum(w[k] * s for k, s in known.items()) / sum(w[k] for k in known), 2) if known else None
    reasons = []
    if d01 == 'FAIL':
        exit_ = 'STOP'
        reasons.append('D01 hard stop: the system must not work on this idea.')
    elif d01 == 'REVIEW_REQUIRED':
        exit_ = 'REVIEW_REQUIRED'
        reasons.append('D01 flags need the founder\'s research-only acknowledgment.')
    elif any(known.get(k) is not None and known[k] <= g['pivot_mark'] for k in ('D03', 'D04')):
        exit_ = 'PIVOT'
        low = [f'{k}={known[k]}' for k in ('D03', 'D04') if known.get(k) is not None and known[k] <= g['pivot_mark']]
        reasons.append(f'Accepted evidence scores {", ".join(low)} at or below the pivot mark {g["pivot_mark"]}.')
    else:
        rep = []
        if rows[1]['status'] == 'FAIL':
            rep.append('D02 idea clarity incomplete.')
        if hl['status'] == 'FAIL':
            rep.append('D06 hard limit exceeded.')
        if agent_flags:
            rep.append('An agent output proposed a prohibited tactic (X03); revise before going on.')
        if unknown_n > g['max_unknown_scored']:
            rep.append(f'{unknown_n} of 5 scored criteria are UNKNOWN (more than {g["max_unknown_scored"]} allowed): gather evidence in Research, then re-evaluate.')
        if mean is not None and mean < g['pass_mark']:
            rep.append(f'Weighted mean of known scores {mean} is below the pass mark {g["pass_mark"]}.')
        exit_ = 'REPEAT' if rep else 'GO_ON'
        reasons += rep or [f'Known weighted mean {mean} ≥ pass mark {g["pass_mark"]} with {unknown_n} unknown(s) (≤ {g["max_unknown_scored"]}).']
    rows.append(_row('D09', status=exit_, unknown=False, reasoning=' '.join(reasons),
                     details={'exit': exit_, 'weighted_mean_known': mean, 'known_scores': known, 'unknown_scored': unknown_n,
                              'thresholds': g, 'weights': {k: w[k] for k in SCORED_DISCOVER},
                              'permission_if_approved': 'VALIDATION_RESEARCH_ONLY'}))
    allrows = rows + cross
    allrows.append(_x05(allrows, counted, excluded))
    body = _wrap('discover', allrows, exit_, reasons, brief_version, safety, cfg, evidence, quality, discovery_run_id, experiments, granular)
    if granular:
        body['rubric'] = {'version': granular['version'], 'file_sha256': granular['file_sha256'], 'dimensions': granular['dimensions'], 'priority': granular['priority']}
    return body


def _wrap(phase, rows, exit_, reasons, brief_version, safety, cfg, evidence, quality, run_id, experiments, granular=None):
    fingerprint = {'phase': phase, 'brief_version': brief_version, 'safety': (safety or {}).get('status'),
                   'safety_policy': (safety or {}).get('policy_hash'), 'criteria_policy': POLICY_HASH, 'config': stable_hash(cfg),
                   'run_id': run_id, 'evidence': sorted((e['id'], quality[e['id']]['grade']) for e in evidence),
                   'experiments': sorted((x['id'], x['version'], x['status'], x.get('result_evidence_id')) for x in experiments)}
    if granular is not None:
        fingerprint['rubric'] = granular_signature(granular)
    body = {'phase': phase, 'exit': exit_, 'reasons': reasons, 'criteria': rows,
            'unknown_count': sum(1 for r in rows if r['unknown']),
            'criteria_version': VERSION, 'criteria_policy_hash': POLICY_HASH, 'config': cfg, 'config_hash': stable_hash(cfg),
            'quality': quality, 'fingerprint': fingerprint, 'fingerprint_hash': stable_hash(fingerprint)}
    body['evaluation_hash'] = stable_hash({k: v for k, v in body.items()})
    return body


def judgeable_rows(phase: str, brief: dict, evidence: list[dict], experiments: list[dict], cfg: dict):
    quality = prepare(brief, evidence, experiments, cfg)
    ids = SCORED_DISCOVER if phase == 'discover' else SCORED_VALIDATE
    out = []
    for cid in ids:
        rows = _accepted(evidence, quality, BY_ID[cid].get('dimension'), cid)
        if rows:
            out.append((cid, rows, quality))
    return out


# ----------------------------------------------------------------------------- Validate criteria
BEHAVIORAL = re.compile(r'\b(opt[- ]?in|sign[- ]?up|signed|join\w*|leave (an |their )?email|book\w*|pre-?order|click\w*|download\w*|use[sd]?|return\w*|complete\w*|pay|paid|commit\w*|attend\w*|reply|replied|enrol\w*|register\w*|submit\w*|install\w*|share[sd]?|trial|waitlist|deposit)\b', re.I)
OPINION = re.compile(r'\b(would you|would they|like the idea|interested in|think about|opinion|rate the idea|how much would you pay|survey of interest|say they)\b', re.I)


def experiment_design_check(p: dict, brief: dict) -> dict:
    """V05 output check (code part). Returns {status, items: {name: {ok, why}}}."""
    from . import safety
    items = {}
    metric = p.get('metric') or ''
    items['behavioral_metric'] = {'ok': bool(BEHAVIORAL.search(metric)) and not OPINION.search(metric),
                                  'why': 'Metric must count an action people take (opt-in, sign-up, pre-order, use), not opinions.'}
    items['can_fail'] = {'ok': p.get('success_threshold_pct') is not None and p.get('adverse_threshold_pct') is not None
                         and float(p['adverse_threshold_pct']) < float(p['success_threshold_pct']) and int(p.get('min_sample') or 0) >= 1,
                         'why': 'Needs a success threshold, a lower adverse trigger and a sample floor, so the test can fail.'}
    budget = _money(brief.get('budget'))
    cost = _money(p.get('cost_estimate'))
    items['low_cost_within_budget'] = {'ok': cost is not None and (budget is None or cost <= budget),
                                       'why': f'Cost estimate must be stated as a number and fit the budget ({brief.get("budget") or "UNKNOWN"}).'}
    consent = p.get('consent_method') or ''
    items['honest_consent'] = {'ok': len(consent) >= 10 and not re.search(r'\b(no need|not needed|skip|without (telling|consent)|hidden|secret\w*|deceiv\w*|trick\w*)\b', consent, re.I),
                               'why': 'Participants must knowingly consent; no deception.'}
    acts = p.get('founder_actions') or ''
    items['founder_runs_it'] = {'ok': len(acts) >= 10 and not re.search(r'\b(the ai|founderos|the agent|automatically|bot)\b[^.]{0,30}\b(send|email|post|contact|message|call)\w*', acts, re.I),
                                'why': 'The founder runs it personally; FounderOS never contacts anyone.'}
    text = ' '.join(str(p.get(k) or '') for k in ('hypothesis', 'metric', 'consent_method', 'founder_actions', 'pivot_alternative'))
    blocks = safety.find_blocks(text)
    items['no_prohibited_tactic'] = {'ok': not blocks, 'why': 'No fake sign-ups, impersonation, payments or other never-rules.',
                                     'findings': [b['rule_id'] for b in blocks]}
    sim_words = bool(SIMULATION.search(text))
    if p.get('simulated'):
        items['labelled_simulation'] = {'ok': True, 'why': 'SIMULATED / NOT COUNTED: a demo only. Its result is stored apart from real results and never counts as demand.'}
    else:
        items['real_action_not_simulated'] = {'ok': not sim_words, 'why': 'The test describes a simulated or hypothetical action. Rewrite it as a real, voluntary action, or mark it SIMULATED / NOT COUNTED.'}
    if involves_minors(brief, p):
        seg = p.get('target_segment') or ''
        adult_seg = bool(re.search(r'(?i)\b(parents?|guardians?|teachers?|school (staff|administrators?|leaders?)|principals?|adults?|tutors?|caregivers?)\b', seg))
        child_contact = bool(re.search(r'(?i)\b(children|kids|pupils|minors|students under 18|k-?12 students)\b[^.]{0,40}\b(sign\w*|join\w*|contact\w*|message\w*|survey\w*|interview\w*|recruit\w*)\b|'
                                       r'\b(contact\w*|message\w*|survey\w*|interview\w*|recruit\w*|dm)\b[^.]{0,40}\b(children|kids|pupils|minors)\b', text + ' ' + seg))
        items['adults_only_with_minors'] = {'ok': bool(p.get('participants_adults_only')) and adult_seg and not child_contact,
                                           'why': 'This venture involves minors: test only with consenting adults (parents, guardians, teachers) in a research-only setting, '
                                                  'confirm adults-only, and never recruit or contact children. FounderOS collects no personal data about anyone.'}
    return {'status': 'PASS' if all(v['ok'] for v in items.values()) else 'FAIL', 'items': items, 'simulated': bool(p.get('simulated'))}


SIMULATION = re.compile(r'(?i)\b(simulat\w*|hypothetical (sign|wait|user|customer|participant|buyer|parent)\w*|mock (sign|wait|user|customer|purchase)\w*|'
                        r'fake (sign|wait|user|customer|purchase|data)\w*|pretend\w*|dummy (data|users?|participants?)|synthetic (users?|data|participants?|customers?)|'
                        r'role[- ]?play\w*|imaginary (users?|customers?))\b')
_MINORS = re.compile(r'(?i)\b(children|kids|child|k-?12|minors?|pupils?|primary school|secondary school|high[- ]school students|teen(ager)?s?|under[- ]18|schoolchildren)\b')


def involves_minors(brief: dict, p: dict | None = None) -> bool:
    txt = ' '.join(str((brief or {}).get(k) or '') for k in ('original_idea_text', 'idea_summary', 'problem', 'target_customers'))
    txt += ' ' + ' '.join(str((p or {}).get(k) or '') for k in ('hypothesis', 'target_segment'))
    return bool(_MINORS.search(txt))


def target_setting_check(p: dict, evidence_ids_accepted: set) -> dict:
    """V06: threshold origin, sample, time window."""
    origin = p.get('threshold_origin')
    bench = p.get('benchmark_evidence_id')
    problems = []
    if origin not in ('TEAM_ASSUMPTION', 'CITED_BENCHMARK'):
        problems.append('Label where the threshold comes from: TEAM_ASSUMPTION or CITED_BENCHMARK.')
    if origin == 'CITED_BENCHMARK' and bench not in evidence_ids_accepted:
        problems.append('CITED_BENCHMARK must reference an accepted ledger row.')
    if not p.get('time_window_days'):
        problems.append('Set a time window (days).')
    if not p.get('min_sample'):
        problems.append('Set a sample floor.')
    return {'status': 'PASS' if not problems else 'FAIL', 'problems': problems}


READING = {'PASS': 'HIT', 'NEAR_MISS': 'NEAR_MISS', 'FAIL': 'CLEAR_MISS', 'INCONCLUSIVE': 'TOO_LITTLE_DATA'}


def evaluate_validate(*, brief: dict, brief_version: int, safety: dict | None, safety_ack: bool, discovery: dict | None,
                      evidence: list[dict], experiments: list[dict], judgments: dict, cfg: dict, register: list[dict],
                      run_id: str | None = None, approvals_scope='RESEARCH_ONLY', blocked_actions=0) -> dict:
    quality = prepare(brief, evidence, experiments, cfg)
    rows = [_scored('V01', brief, evidence, quality, judgments), _scored('V02', brief, evidence, quality, judgments)]
    hl = hard_limits(brief, experiments)
    v03 = _scored('V03', brief, evidence, quality, judgments)
    v03['details']['hard_limits'] = hl
    if hl['status'] == 'FAIL':
        v03.update(status='FAIL', unknown=False, reasoning='KNOCKOUT: ' + '; '.join(hl['failures']))
    elif hl['status'] == 'UNKNOWN' and v03['status'] in ('UNKNOWN', 'AWAITING_JUDGE'):
        v03['reasoning'] = 'Hard limits cannot be checked (' + '; '.join(hl['unknown']) + '). ' + v03['reasoning']
    rows.append(v03)
    weak = {'UNTESTED': 3, 'REFUTED': 3, 'BACKGROUND_ONLY': 2, 'STATED_ONLY': 2, 'MIXED': 1, 'SUPPORTED_BY_BEHAVIOR': 0}
    crit = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
    ranked = sorted(register, key=lambda r: -(crit[r['criticality']] * weak[r['assumption_status']]))
    top = ranked[0] if ranked else None
    locked = [x for x in experiments if x['status'] == 'LOCKED']
    targets_top = bool(top and any(x['payload'].get('claim_id') == top['claim_id'] for x in locked))
    rows.append(_row('V04', status='RANKED' if ranked else 'UNKNOWN', unknown=not ranked,
                     reasoning=(f'Top risk {top["claim_id"]} ({top["category"]}, {top["criticality"]}, {top["assumption_status"]}). '
                                + ('A locked experiment targets it.' if targets_top else 'No locked experiment targets it yet — the demand test should attack this one (PDF p.5).')) if top else 'No register.',
                     details={'ranking': [{'claim_id': r['claim_id'], 'category': r['category'], 'criticality': r['criticality'],
                                           'status': r['assumption_status'], 'risk_points': crit[r['criticality']] * weak[r['assumption_status']],
                                           'claim': r['exact_claim']} for r in ranked[:8]], 'formula': 'criticality(3/2/1) × weakness(3..0), TEAM_ASSUMPTION'}))
    latest = sorted(experiments, key=lambda x: (x['created_at'], x['version']))[-1] if experiments else None
    if latest:
        v05 = experiment_design_check(latest['payload'], brief)
        rows.append(_row('V05', status=v05['status'], unknown=False, reasoning=f'Latest experiment {latest["id"][:8]} v{latest["version"]}: ' +
                         ('all checklist items pass.' if v05['status'] == 'PASS' else 'fails: ' + ', '.join(k for k, v in v05['items'].items() if not v['ok'])),
                         details=v05))
        acc = {e['id'] for e in evidence if quality[e['id']]['counts']}
        v06 = target_setting_check(latest['payload'], acc)
        st6 = 'LOCKED' if latest['status'] == 'LOCKED' and v06['status'] == 'PASS' else ('DRAFT_NOT_LOCKED' if latest['status'] == 'DRAFT' else v06['status'])
        rows.append(_row('V06', status=st6, unknown=st6 != 'LOCKED',
                         reasoning=('Target frozen ' + str(latest.get('locked_at')) + f'; threshold origin {latest["payload"].get("threshold_origin")}.') if st6 == 'LOCKED' else ('Not locked yet. ' + ' '.join(v06['problems'])),
                         details={'experiment': latest['id'], 'version': latest['version'], 'criteria_hash': latest['criteria_hash'], **v06}))
    else:
        rows.append(_row('V05', status='NOT_DESIGNED', reasoning='No experiment drafted yet.'))
        rows.append(_row('V06', status='NOT_SET', reasoning='No target frozen yet.'))
    results = [e for e in evidence if e['kind'] == 'PRE_REGISTERED_EXPERIMENT_RESULT' and quality[e['id']]['counts']]
    if results:
        last = results[-1]
        reading = READING.get(last.get('outcome'), 'TOO_LITTLE_DATA')
        rows.append(_row('V07', status=reading, unknown=reading == 'TOO_LITTLE_DATA', evidence_ids=[last['id']],
                         reasoning=f'{last.get("positives")}/{last.get("sample_size")} = {last.get("rate_pct")}% compared in code with the locked criteria. Founder-reported; not generalizable beyond this experiment.',
                         details={'outcome': last.get('outcome'), 'experiment_id': last.get('experiment_id'), 'version': last.get('experiment_version')}))
    else:
        rows.append(_row('V07', status='NO_RESULT', reasoning='No result against a live locked experiment. A planned experiment is never evidence.'))
    agent_flags = []
    cross, counted, excluded, _ = _cross(brief, safety, safety_ack, evidence, quality, experiments, agent_flags, approvals_scope, blocked_actions)
    allrows = rows + cross
    allrows.append(_x05(allrows, counted, excluded))
    return _wrap('validate', allrows, None, [], brief_version, safety, cfg, evidence, quality, run_id, experiments)


def catalog() -> dict:
    return {'version': VERSION, 'policy_hash': POLICY_HASH, 'source': POLICY['source'], 'scale': SCALE, 'evidence_caps': CAPS,
            'discover': DISCOVER, 'validate': VALIDATE, 'cross_cutting': CROSS, 'architecture_only': ARCHITECTURE,
            'defaults': default_config()}

"""Validation prose: a deterministic explanation of the code verdict, plus a checker for the model's narrative (v0.8).

The code verdict is authoritative. In the v0.7 trial the 1.5B model wrote truncated fragments and the
categorical "No customer behavior or demand exists", where the correct statement is "No evidence of customer
behavior was recorded." This module:
  * writes the authoritative explanation from the verdict object (no model involved);
  * rewrites categorical absence claims into "no evidence ... was recorded";
  * drops fragments (no verb-like content, cut off mid-sentence) and labels them;
  * flags any sentence that contradicts the verdict (validated / proven / ready to launch / demand confirmed).
"""
from __future__ import annotations
import re

UNKNOWN = 'Unknown / not provided'

_ABSENCE = [
    (re.compile(r"(?i)\bno (customer )?(behaviou?r|demand)( or (demand|behaviou?r))? (exists|exist|is present)\b"), 'No evidence of customer behaviour was recorded'),
    (re.compile(r"(?i)\bthere is no (customer )?(demand|interest|market)( for (this|the product|it))?\b"), 'No evidence of customer demand was recorded'),
    (re.compile(r"(?i)\b(customers|people|users) (do not|don't) (want|need) (this|it|the product)\b"), 'No evidence was recorded about whether customers want this'),
    (re.compile(r"(?i)\bno competitors?( exist)?\b"), 'No competitors were identified in the recorded evidence'),
    (re.compile(r"(?i)\bthe market (does not exist|is empty)\b"), 'No evidence about the market was recorded'),
]
_CONTRADICT = re.compile(r"(?i)\b(validated|is proven|proves (that )?(demand|the market)|demand (is )?(confirmed|proven|validated)|ready to (launch|build)|guarantee\w*|will succeed|go ahead and (build|launch))\b")


def _sentences(s: str) -> list[str]:
    return [x.strip() for x in re.split(r'(?<=[.!?])\s+', s or '') if x.strip()]


def is_fragment(s: str) -> bool:
    t = s.strip()
    if len(t.split()) < 4:
        return True
    if not re.search(r'[.!?)"”]$', t):
        return True
    return False


def clean_text(s: str, verdict: str) -> tuple[str, list[dict]]:
    notes, out = [], []
    for sent in _sentences(s):
        orig = sent
        for rx, rep in _ABSENCE:
            if rx.search(sent):
                sent = rx.sub(rep, sent)
                notes.append({'kind': 'REWORDED_ABSENCE_CLAIM', 'original': orig, 'issue': 'A categorical absence claim was reworded: the ledger can only show that no evidence was recorded.'})
        cm = _CONTRADICT.search(sent)
        negated = cm and re.search(r"(?i)\b(not|never|no|isn't|cannot|can't|nor|without)\b[^.]{0,40}$", sent[:cm.start()])
        if cm and not negated:
            notes.append({'kind': 'CONTRADICTS_VERDICT', 'original': orig, 'issue': f'Removed: this sentence contradicts the code verdict ({verdict}).'})
            continue
        if is_fragment(sent):
            notes.append({'kind': 'FRAGMENT_REMOVED', 'original': orig, 'issue': 'Removed an incomplete fragment from the model output.'})
            continue
        out.append(sent)
    return ' '.join(out), notes


def clean_report(report: dict, verdict: str) -> dict:
    r = dict(report)
    notes = []
    for k in ('summary', 'market_research_vs_customer_demand'):
        if isinstance(r.get(k), str):
            r[k], n = clean_text(r[k], verdict)
            notes += [{**x, 'field': k} for x in n]
            if not r[k]:
                r[k] = UNKNOWN
    for k in ('risks', 'contradictions_or_gaps', 'pricing_hypotheses', 'business_model_hypotheses', 'competitor_research_limitations'):
        items = []
        for i, item in enumerate(r.get(k) or []):
            txt = item if re.search(r'[.!?]$', item.strip()) else item.strip() + '.'
            c, n = clean_text(txt, verdict)
            notes += [{**x, 'field': f'{k}[{i}]'} for x in n]
            if c:
                items.append(c)
        r[k] = items
    r['_prose_checks'] = notes
    return r


def verdict_explanation(gate: dict) -> dict:
    """Authoritative plain-language explanation built only from the verdict object."""
    m = gate.get('matrix') or {}
    outcomes = gate.get('experiment_outcomes') or []
    behaviour = [d for d, x in m.items() if 'CUSTOMER_BEHAVIOR' in (x.get('evidence_classes') or []) or 'PRE_REGISTERED_EXPERIMENT_RESULT' in (x.get('evidence_classes') or [])]
    lines = [gate.get('headline') or UNKNOWN]
    if not outcomes:
        lines.append('No result has been recorded against a locked demand test.')
    for o in outcomes:
        lines.append(f'Locked test {o["experiment_id"][:8]} v{o["version"]}: {o["positives"]} of {o["n"]} people did the action ({o["rate_pct"]}%), '
                     f'against a locked pass mark of {o["criteria"]["success_threshold_pct"]}% and a stop signal of {o["criteria"]["adverse_threshold_pct"]}%.')
    if not behaviour:
        lines.append('No evidence of customer behaviour was recorded in the ledger.')
    excl = gate.get('excluded_evidence') or []
    if excl:
        lines.append(f'{len(excl)} ledger record(s) were not counted; each has a stated reason below.')
    per_dim = {x.get('label', d): x.get('status', 'UNKNOWN') for d, x in m.items()}
    return {'source': 'CODE (deterministic, authoritative)', 'verdict': gate.get('verdict'), 'lines': lines, 'dimensions': per_dim,
            'permissions': 'Approval allows more research only. Building, launching, publishing, sending, spending and payments are never enabled.'}

"""Deterministic quality guard for the Discover agent's output (v0.8).

Observed in the v0.7 trial with qwen2.5:1.5b: invented percentages ("up to 50%"), generic adoption goals,
unrealistic tests (a 100-person webinar on a $200 budget) and a direction that jumped to an unrelated
customer and place ("AUC University" for Cairo restaurants). This guard:
  1. finds invented quantitative facts (numbers not present in the founder's brief),
  2. finds unsupported geographic shifts (places not in the brief),
  3. finds directions whose segment shares nothing with the brief's customer/problem/idea,
  4. flags generic, non-falsifiable hypotheses and tests that exceed the stated budget/time.
The caller retries the model ONCE with the issues listed; if issues remain, `degrade` removes the
offending items and labels the rest. Everything stays labelled HYPOTHESIS.
"""
from __future__ import annotations
import re

from .brief_extract import _CITIES, _COUNTRY_WORDS, money, duration

_NUM = re.compile(r"(?i)(?:up to |over |more than |about |around |nearly |~)?(?:\$|egp |usd )?\b\d[\d,.]*\s?(?:%|percent|k\b|million|billion|x\b|times|hours?|minutes?|people|participants|users|customers|restaurants|students|attendees)?")
_PLACES = {**{k: v[0] for k, v in _CITIES.items()}, **{k: v for k, v in _COUNTRY_WORDS.items()},
           'new york': 'New York', 'california': 'California', 'europe': 'Europe', 'asia': 'Asia', 'africa': 'Africa', 'silicon valley': 'Silicon Valley',
           'auc': 'AUC (American University in Cairo)', 'american university': 'American University', 'cairo university': 'Cairo University',
           'nile university': 'Nile University', 'ain shams': 'Ain Shams University', 'harvard': 'Harvard', 'mit': 'MIT'}
_GENERIC = re.compile(r"(?i)\b(increase (adoption|engagement|awareness)|improve (efficiency|the experience)|enhance\w*|revolutioni[sz]\w*|leverag\w*|empower\w*|seamless\w*|drive growth|boost\w*)\b")
_TEST_SIZE = re.compile(r"(?i)\b(\d{2,6})[- ]?(person|people|participant|attendee|user|customer|restaurant|student)s?\b|\b(webinar|conference|ad campaign|paid ads?|billboard|tv)\b")
_STOP = set('a an and are as at be by for from has have in into is it its of on or that the their this to was with who will can our your more less new small local'.split())


def _words(s: str) -> set:
    return {w for w in re.findall(r'[a-z؀-ۿ]{3,}', (s or '').lower()) if w not in _STOP}


def _brief_text(brief: dict) -> str:
    # Founder's own words and captured fields only: the model's own idea_summary is not a source of facts.
    return ' '.join(str(brief.get(k) or '') for k in ('original_idea_text', 'problem', 'target_customers', 'current_workaround',
                                                     'skills', 'budget', 'timeline', 'target_market', 'values', 'constraints'))


def _numbers_in(s: str) -> set:
    return {re.sub(r'[,\s]', '', m) for m in re.findall(r'\d[\d,.]*', s or '')}


def review(report: dict, brief: dict) -> list[dict]:
    """Return issues: {kind, field, text, issue, severity}. Severity HIGH triggers retry/removal."""
    issues = []
    btxt = _brief_text(brief)
    blow = btxt.lower()
    bnums = _numbers_in(btxt)
    bwords = _words(btxt)

    def walk(v, path):
        if isinstance(v, str):
            for m in _NUM.finditer(v):
                raw = m.group(0).strip()
                nums = _numbers_in(raw)
                if not nums or nums <= bnums:
                    continue
                if re.fullmatch(r'[1-5]', raw):       # list numbering / small counts are not quantitative claims
                    continue
                issues.append({'kind': 'INVENTED_NUMBER', 'field': path, 'text': raw, 'severity': 'HIGH',
                               'issue': f'"{raw}" is a figure that does not appear in your brief or any accepted evidence. Treat it as an unsourced assumption.'})
            low = v.lower()
            for k, name in _PLACES.items():
                if re.search(r'\b' + re.escape(k) + r'\b', low) and not re.search(r'\b' + re.escape(k) + r'\b', blow):
                    issues.append({'kind': 'GEOGRAPHIC_OR_INSTITUTION_SHIFT', 'field': path, 'text': name, 'severity': 'HIGH',
                                   'issue': f'Mentions {name}, which your brief does not mention. The agent may have shifted market or customer.'})
            if path.startswith(('hypotheses', 'opportunities', 'value_proposition')) and _GENERIC.search(v) and not re.search(r'\d|%', v):
                issues.append({'kind': 'GENERIC_CLAIM', 'field': path, 'text': v[:120], 'severity': 'LOW',
                               'issue': 'Generic goal with nothing observable to falsify. Rewrite as "X people do Y within Z days".'})
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f'{path}[{i}]')
        elif isinstance(v, dict):
            for k, x in v.items():
                if not k.startswith('_'):
                    walk(x, f'{path}.{k}' if path else k)
    walk(report, '')
    # Direction consistency: a direction's segment+value must share content with the brief.
    for i, d in enumerate(report.get('directions') or []):
        dw = _words(f'{d.get("segment", "")} {d.get("name", "")} {d.get("value", "")}')
        if not (dw & bwords):
            issues.append({'kind': 'INCONSISTENT_DIRECTION', 'field': f'directions[{i}]', 'text': d.get('name', ''), 'severity': 'HIGH',
                           'issue': f'Direction "{d.get("name")}" ({d.get("segment")}) shares no customer, problem or product term with your brief.'})
    # Tests that exceed stated limits.
    budget = money(str(brief.get('budget') or ''))
    days = duration(str(brief.get('timeline') or ''))
    for i, t in enumerate(report.get('experiments') or []):
        m = _TEST_SIZE.search(t or '')
        if m:
            big = m.group(1) and int(m.group(1)) > 40
            costly = m.group(3) and m.group(3).lower() in ('conference', 'ad campaign', 'paid ads', 'paid ad', 'billboard', 'tv')
            if big or costly or (m.group(3) and m.group(3).lower() == 'webinar'):
                issues.append({'kind': 'UNREALISTIC_TEST', 'field': f'experiments[{i}]', 'text': t[:120], 'severity': 'LOW',
                               'issue': 'This test may not fit your stated budget ' + (f'({budget[0]:g} {budget[1] or ""})' if budget else '(unknown)') +
                                        ' and time ' + (f'({days[0]:g} days)' if days else '(unknown)') + '. Prefer 10–20 one-to-one conversations or a consented waitlist.'})
    return issues


def high(issues):
    return [i for i in issues if i['severity'] == 'HIGH']


def correction_message(issues) -> str:
    lines = [f'- {i["field"]}: {i["issue"]}' for i in high(issues)[:8]]
    return ('Your previous answer broke these rules. Rewrite it using ONLY the founder brief: no numbers, places, institutions or customer '
            'groups that are not in the brief; every direction must serve the brief\'s customer and problem.\n' + '\n'.join(lines))


def degrade(report: dict, issues: list[dict]) -> dict:
    """Remove offending items after a failed retry; never invent replacements."""
    r = dict(report)
    bad_dirs = {int(re.search(r'\[(\d+)\]', i['field']).group(1)) for i in issues if i['kind'] == 'INCONSISTENT_DIRECTION'}
    for i in issues:
        if i['kind'] == 'GEOGRAPHIC_OR_INSTITUTION_SHIFT' and i['field'].startswith('directions['):
            bad_dirs.add(int(re.search(r'\[(\d+)\]', i['field']).group(1)))
    if bad_dirs:
        r['directions'] = [d for j, d in enumerate(r.get('directions') or []) if j not in bad_dirs]
        r['_removed_directions'] = [d for j, d in enumerate(report.get('directions') or []) if j in bad_dirs]

    def scrub(v):
        if isinstance(v, str):
            for i in issues:
                if i['kind'] == 'INVENTED_NUMBER' and i['text'] in v:
                    v = v.replace(i['text'], '[unsourced figure removed]')
            return v
        if isinstance(v, list):
            return [scrub(x) for x in v]
        return v
    for k in ('problem_statement', 'value_proposition', 'viability_first_look', 'hypotheses', 'opportunities', 'feasibility_notes', 'experiments', 'unknowns', 'alternatives_unverified'):
        if k in r:
            r[k] = scrub(r[k])
    return r

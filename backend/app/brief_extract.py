"""Deterministic brief-field extraction with exact source spans (v0.8).

Why: in the v0.7 trial a 1.5B model left clearly stated fields (Cairo, $200, six weeks, skills)
as UNKNOWN, so D02 failed falsely. Extraction of stated facts is now done by code from the
founder's own words; every value carries the exact span it came from. The model's suggestions
are kept separately and are never treated as confirmed.

Field status vocabulary:
  FORM_FIELD                  typed by the founder in the form field
  FOUNDER_CONFIRMED           confirmed or corrected by the founder on the Brief page
  STATED_IN_TEXT              found by this parser in the founder's own words (span shown; please confirm)
  MODEL_SUGGESTED_UNCONFIRMED proposed by the local model, not found in the founder's words
  NOT_STATED                  the founder's words do not state it (ask one clear question)
  PARSER_FAILED               the extractor raised an error (distinct from "not stated")
"""
from __future__ import annotations
import re

FIELDS = ('problem', 'target_customers', 'current_workaround', 'skills', 'budget', 'timeline', 'target_market', 'values', 'constraints')
D02_REQUIRED = ('target_customers', 'problem', 'current_workaround')
COUNTS_AS_CAPTURED = ('FORM_FIELD', 'FOUNDER_CONFIRMED', 'STATED_IN_TEXT')

QUESTIONS = {
    'current_workaround': 'What do these customers do today about this problem? (Doing nothing, a spreadsheet, a paper notebook, WhatsApp, a competitor app, or "I don\'t know yet" are all valid answers.)',
    'problem': 'In one sentence, what goes wrong for the customer today, in their words?',
    'target_customers': 'Who exactly has this problem? Name the narrowest group (role, size, place).',
    'target_market': 'Which country and city will you start in?',
    'budget': 'How much money can you spend before the first sale (amount and currency)?',
    'timeline': 'How much time do you have (weeks or months)?',
    'skills': 'Which of the needed skills do you have yourself?',
    'values': 'Which values will you not compromise on? (optional)',
    'constraints': 'Any other limits? (optional)',
}

_NUMWORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
             'eleven': 11, 'twelve': 12, 'a few': 3, 'a couple of': 2, 'a': 1, 'an': 1}
_UNIT_DAYS = {'day': 1, 'week': 7, 'month': 30, 'year': 365}
_CURRENCY = r'(?:\$|usd|us\$|dollars?|egp|le|l\.e\.|e£|£|gbp|€|eur|euros?|sar|aed|riyals?|dirhams?|pounds?|جنيه)'
_CITIES = {
    'cairo': ('Cairo', 'Egypt'), 'giza': ('Giza', 'Egypt'), 'alexandria': ('Alexandria', 'Egypt'), 'mansoura': ('Mansoura', 'Egypt'),
    'riyadh': ('Riyadh', 'Saudi Arabia'), 'jeddah': ('Jeddah', 'Saudi Arabia'), 'dubai': ('Dubai', 'United Arab Emirates'),
    'abu dhabi': ('Abu Dhabi', 'United Arab Emirates'), 'amman': ('Amman', 'Jordan'), 'lagos': ('Lagos', 'Nigeria'),
    'nairobi': ('Nairobi', 'Kenya'), 'london': ('London', 'United Kingdom'), 'casablanca': ('Casablanca', 'Morocco'),
    'tunis': ('Tunis', 'Tunisia'), 'beirut': ('Beirut', 'Lebanon'), 'doha': ('Doha', 'Qatar'),
}
_COUNTRY_WORDS = {
    'egypt': 'Egypt', 'egyptian': 'Egypt', 'saudi arabia': 'Saudi Arabia', 'saudi': 'Saudi Arabia', 'uae': 'United Arab Emirates',
    'united arab emirates': 'United Arab Emirates', 'jordan': 'Jordan', 'morocco': 'Morocco', 'tunisia': 'Tunisia', 'kenya': 'Kenya',
    'nigeria': 'Nigeria', 'united states': 'United States', 'usa': 'United States', 'united kingdom': 'United Kingdom', 'uk': 'United Kingdom',
    'germany': 'Germany', 'france': 'France', 'india': 'India', 'canada': 'Canada', 'turkey': 'Turkey', 'pakistan': 'Pakistan',
    'lebanon': 'Lebanon', 'qatar': 'Qatar', 'kuwait': 'Kuwait',
}
_SKILLS = [
    ('Python', r'python'), ('Machine learning', r'machine[- ]learning|\bml\b|deep learning'), ('Basic web development', r'basic web(?: dev\w*)?|web dev\w*|html|css|front[- ]?end|full[- ]?stack|web apps?'),
    ('JavaScript', r'javascript|\bjs\b|react|node(?:\.js)?'), ('Data analysis', r'data analy\w+|analytics|\bsql\b|excel'),
    ('Design', r'\bui\b|\bux\b|figma|graphic design|product design'), ('Marketing', r'marketing|social media|seo'), ('Sales', r'\bsales\b|selling'),
    ('Mobile development', r'flutter|android|ios|mobile dev\w*|kotlin|swift'), ('Teaching', r'teach\w*|tutor\w*'),
    ('Accounting / finance', r'accounting|bookkeeping'), ('No-code tools', r'no[- ]code|bubble|airtable|zapier'),
]
_WORKAROUND = re.compile(
    r"(?i)\b(currently|today|right now|at the moment|nowadays|instead|for now)\b[^.!?\n]{0,120}\b(use|uses|using|rely|relies|track|tracks|do|does|write|writes|ask|asks|keep|keeps|guess|guesses|order|orders|handle|handles)\b[^.!?\n]*"
    r"|\b(they|owners?|managers?|students?|parents?|teachers?|customers?|people|we)\s+(use|rely on|track (it|this|them) (in|with|on)|write (it|this|them) (in|on|down)|keep (it|them) in|just guess|guess|do nothing|ignore it)\b[^.!?\n]*"
    r"|\b(spreadsheets?|excel|pen and paper|paper notebooks?|notebooks?|whatsapp groups?|by hand|manually)\b[^.!?\n]{0,60}")
_PROBLEM = re.compile(r"(?i)[^.!?\n]*\b(problem|struggl\w*|waste\w*|wasting|pain|hard to|difficult|lose|losing|loses|can'?t|cannot|frustrat\w*|miss(es|ing)?|overwhelm\w*|too (much|many|expensive|slow)|spend too|no (easy|good) way|lack(s|ing)?|behind in)\b[^.!?\n]*[.!?]?")
_UNVERIFIED = re.compile(r"(?i)\b(not (yet )?verified|haven'?t (yet )?(verified|talked|spoken|asked|validated)|unverified|i (assume|believe|think|guess)|not sure|no evidence yet|untested)\b")
_BROAD = re.compile(r"(?i)\b(everyone|everybody|anyone|all people|the general public|general audience|all (users|businesses|students|people|companies))\b")
_SEGMENT_LEAD = re.compile(
    r"(?i)\b(?:for|targeting|aimed at|serving|helps?|helping|to help|built for|designed for|used by)\s+((?:small|medium|large|independent|local|busy|first[- ]time|new|young|working|cairo|egyptian|k-12|high[- ]school|university|college|\d+(?:st|nd|rd|th)[- ]year)?[\w\s\-–/()]{3,90}?)"
    r"(?=\s+(?:who|that|which|to|in|by|with|so|because|and (?:help|reduce|track))\b|[,.;:!?\n]|$)")
_EMPLOYEES = re.compile(r"(?i)\(?\b(\d{1,4})\s*(?:-|–|—|to)\s*(\d{1,5})\s*(?:employees|staff|people|workers|seats)\b\)?")
_MINORS = re.compile(r"(?i)\b(children|kids|child|k-?12|minors?|pupils?|primary school|secondary school|high[- ]school students|teen(?:ager)?s?|under[- ]18|schoolchildren|students aged (?:[5-9]|1[0-7]))\b")


def _span(source: str, m: re.Match, group=0) -> dict:
    return {'source': source, 'start': m.start(group), 'end': m.end(group), 'text': m.group(group).strip()}


def money(text: str):
    """Return (amount, currency, span-match) for the first stated budget, or None."""
    t = text or ''
    if re.search(r'(?i)\b(no budget|zero budget|budget (of|is) (zero|0|nothing)|without any money)\b', t):
        m = re.search(r'(?i)\b(no budget|zero budget|budget (of|is) (zero|0|nothing)|without any money)\b', t)
        return 0.0, None, m
    pat = re.compile(r'(?i)(' + _CURRENCY + r')\s?(\d[\d,]*(?:\.\d+)?)\s?(k|thousand)?\b|\b(\d[\d,]*(?:\.\d+)?)\s?(k|thousand)?\s?(' + _CURRENCY + r')(?![a-z])')
    for m in pat.finditer(t):
        if m.group(2):
            amount, k, cur = m.group(2), m.group(3), m.group(1)
        else:
            amount, k, cur = m.group(4), m.group(5), m.group(6)
        try:
            val = float(amount.replace(',', '')) * (1000 if k else 1)
        except ValueError:
            continue
        c = cur.lower()
        code = 'USD' if c in ('$', 'usd', 'us$', 'dollar', 'dollars') else 'EGP' if c in ('egp', 'le', 'l.e.', 'e£', 'جنيه') else 'GBP' if c in ('£', 'gbp') \
            else 'EUR' if c in ('€', 'eur', 'euro', 'euros') else 'SAR' if c in ('sar', 'riyal', 'riyals') else 'AED' if c in ('aed', 'dirham', 'dirhams') else c.upper()
        if c in ('pound', 'pounds'):
            code = 'EGP_OR_GBP_AMBIGUOUS'
        return val, code, m
    return None


def duration(text: str):
    t = text or ''
    m = re.search(r'(?i)\b(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|a few|a couple of|an?)\s+(day|week|month|year)s?\b', t)
    if not m:
        return None
    n = m.group(1).lower()
    num = float(n) if re.match(r'\d', n) else _NUMWORDS[n]
    return num * _UNIT_DAYS[m.group(2).lower()], m


def _first(rx, text):
    return rx.search(text or '')


def extract(idea: str) -> dict:
    """Extract fields from the founder's own idea text. Returns {field: {value, status, spans, typed, note}}."""
    out = {}
    text = idea or ''

    def run(name, fn):
        try:
            out[name] = fn() or {'value': None, 'status': 'NOT_STATED', 'spans': [], 'typed': {}}
        except Exception as exc:  # noqa: BLE001 - parser failure must be distinguishable from "not stated"
            out[name] = {'value': None, 'status': 'PARSER_FAILED', 'spans': [], 'typed': {}, 'note': f'extractor error: {type(exc).__name__}'}

    def budget():
        r = money(text)
        if not r:
            return None
        val, cur, m = r
        shown = m.group(0).strip()
        return {'value': shown, 'status': 'STATED_IN_TEXT', 'spans': [_span('idea', m)], 'typed': {'amount': val, 'currency': cur}}

    def timeline():
        r = duration(text)
        if not r:
            return None
        days, m = r
        return {'value': m.group(0).strip(), 'status': 'STATED_IN_TEXT', 'spans': [_span('idea', m)], 'typed': {'days': days}}

    def market():
        low = text.lower()
        spans, city, country = [], None, None
        for k, (c, ctry) in _CITIES.items():
            m = re.search(r'\b' + re.escape(k) + r'\b', low)
            if m:
                city, country = c, ctry
                spans.append({'source': 'idea', 'start': m.start(), 'end': m.end(), 'text': text[m.start():m.end()]})
                break
        for k, ctry in _COUNTRY_WORDS.items():
            m = re.search(r'\b' + re.escape(k) + r'\b', low)
            if m:
                if country and ctry != country:
                    return {'value': None, 'status': 'NOT_STATED', 'spans': spans, 'typed': {}, 'note': 'More than one country mentioned; please choose one.'}
                country = ctry
                spans.append({'source': 'idea', 'start': m.start(), 'end': m.end(), 'text': text[m.start():m.end()]})
                break
        if not country:
            return None
        return {'value': f'{city}, {country}' if city else country, 'status': 'STATED_IN_TEXT', 'spans': spans,
                'typed': {'city': city, 'country': country}}

    def skills():
        found, spans = [], []
        # Only look inside sentences where the founder talks about themselves.
        for sm in re.finditer(r"(?i)[^.!?\n]*\b(i|we|my|our|me)\b[^.!?\n]*", text):
            sent = sm.group(0)
            if not re.search(r"(?i)\b(know|skills?|can|have|experience|background|good at|built|studied|develop\w*|use)\b", sent):
                continue
            for name, rx in _SKILLS:
                m = re.search(r'(?i)\b(?:' + rx + r')', sent)
                if m and name not in found:
                    found.append(name)
                    spans.append({'source': 'idea', 'start': sm.start() + m.start(), 'end': sm.start() + m.end(), 'text': m.group(0)})
        if not found:
            return None
        return {'value': ', '.join(found), 'status': 'STATED_IN_TEXT', 'spans': spans, 'typed': {'skills': found}}

    def customers():
        m = _first(_SEGMENT_LEAD, text)
        emp = _first(_EMPLOYEES, text)
        if not m:
            return None
        seg = re.sub(r'\s+', ' ', m.group(1)).strip(' -–')
        seg = re.sub(r'(?i)^(the|a|an)\s+', '', seg)
        if len(seg) < 3 or re.fullmatch(r'(?i)(me|us|them|it|you)', seg):
            return None
        spans = [_span('idea', m, 1)]
        typed = {'broad': bool(_BROAD.search(seg))}
        value = seg
        if emp:
            spans.append(_span('idea', emp))
            typed['size_employees'] = [int(emp.group(1)), int(emp.group(2))]
            if emp.group(0) not in value:
                value = f'{seg} ({emp.group(1)}–{emp.group(2)} employees)'
        return {'value': value, 'status': 'STATED_IN_TEXT', 'spans': spans, 'typed': typed}

    def problem():
        cands = list(_PROBLEM.finditer(text))
        if not cands:
            return None
        # Prefer a sentence about the customer's pain over one describing the founder's solution.
        solution = re.compile(r"(?i)\b(build|app|tool|platform|website|software|i want|we want|we will|i will|my product|our product|predicts?)\b")
        m = next((c for c in cands if not solution.search(c.group(0))), cands[0])
        sent = m.group(0).strip()
        typed = {'pain_verified': False if _UNVERIFIED.search(text) else None}
        note = 'You said this pain is not yet verified.' if typed['pain_verified'] is False else None
        r = {'value': sent, 'status': 'STATED_IN_TEXT', 'spans': [{'source': 'idea', 'start': m.start(), 'end': m.end(), 'text': sent}], 'typed': typed}
        if note:
            r['note'] = note
        return r

    def workaround():
        m = _first(_WORKAROUND, text)
        if not m:
            return None
        # Report the whole sentence that states the workaround, with its exact offsets.
        s0 = max(text.rfind('.', 0, m.start()), text.rfind('\n', 0, m.start()), text.rfind('!', 0, m.start()), text.rfind('?', 0, m.start())) + 1
        ends = [i for i in (text.find(ch, m.end() - 1) for ch in '.!?\n') if i != -1]
        s1 = min(ends) + 1 if ends else len(text)
        sent = text[s0:s1].strip()
        start = text.index(sent, s0)
        return {'value': sent, 'status': 'STATED_IN_TEXT', 'spans': [{'source': 'idea', 'start': start, 'end': start + len(sent), 'text': sent}], 'typed': {}}

    run('budget', budget)
    run('timeline', timeline)
    run('target_market', market)
    run('skills', skills)
    run('target_customers', customers)
    run('problem', problem)
    run('current_workaround', workaround)
    for k in ('values', 'constraints'):
        out[k] = {'value': None, 'status': 'NOT_STATED', 'spans': [], 'typed': {}}
    out['_signals'] = {'mentions_minors': bool(_MINORS.search(text)), 'pain_stated_unverified': bool(_UNVERIFIED.search(text))}
    return out


def typed_for(field: str, value: str | None) -> dict:
    """Typed values for a founder-typed field (form or clarification)."""
    if not value:
        return {}
    if field == 'budget':
        r = money(value)
        if r:
            return {'amount': r[0], 'currency': r[1]}
        m = re.search(r'\d[\d,]*(?:\.\d+)?', value)
        return {'amount': float(m.group(0).replace(',', '')), 'currency': None} if m else {}
    if field == 'timeline':
        r = duration(value)
        return {'days': r[0]} if r else {}
    if field == 'target_market':
        low = value.lower()
        for k, (c, ctry) in _CITIES.items():
            if re.search(r'\b' + re.escape(k) + r'\b', low):
                return {'city': c, 'country': ctry}
        for k, ctry in _COUNTRY_WORDS.items():
            if re.search(r'\b' + re.escape(k) + r'\b', low):
                return {'city': None, 'country': ctry}
    if field == 'target_customers':
        return {'broad': bool(_BROAD.search(value))}
    return {}


def merge(idea: str, intake: dict, answers: dict, confirmed: list | None = None, model: dict | None = None, previous: dict | None = None) -> dict:
    """Combine sources with fixed precedence: founder clarification > form > parser (own words) > model suggestion.

    Returns {field: {value, status, spans, typed, model_suggestion?, question?}}.
    `confirmed` lists fields the founder confirmed as written (they keep their value, status becomes FOUNDER_CONFIRMED).
    """
    parsed = extract(idea)
    confirmed = set(confirmed or [])
    prev = previous or {}
    out = {}
    for f in FIELDS:
        p = parsed.get(f) or {'value': None, 'status': 'NOT_STATED', 'spans': [], 'typed': {}}
        mv = (model or {}).get(f)
        if answers.get(f):
            row = {'value': answers[f], 'status': 'FOUNDER_CONFIRMED', 'spans': [{'source': f'clarification:{f}', 'start': 0, 'end': len(answers[f]), 'text': answers[f]}],
                   'typed': typed_for(f, answers[f])}
        elif intake.get(f):
            row = {'value': intake[f], 'status': 'FORM_FIELD', 'spans': [{'source': f'form:{f}', 'start': 0, 'end': len(intake[f]), 'text': intake[f]}],
                   'typed': typed_for(f, intake[f])}
        elif f in confirmed and (prev.get(f) or {}).get('value'):
            row = dict(prev[f])
            row['status'] = 'FOUNDER_CONFIRMED'
        elif p['status'] in ('STATED_IN_TEXT', 'PARSER_FAILED'):
            row = dict(p)
        elif mv:
            row = {'value': mv, 'status': 'MODEL_SUGGESTED_UNCONFIRMED', 'spans': [], 'typed': typed_for(f, mv),
                   'note': 'Suggested by the local model; not found in your words. Confirm or correct it.'}
        else:
            row = dict(p)
        if mv and row['status'] != 'MODEL_SUGGESTED_UNCONFIRMED' and str(mv).strip() != str(row.get('value') or '').strip():
            row['model_suggestion'] = mv
        if row['status'] in ('NOT_STATED', 'PARSER_FAILED', 'MODEL_SUGGESTED_UNCONFIRMED'):
            row['question'] = QUESTIONS.get(f)
        out[f] = row
    out['_signals'] = parsed.get('_signals', {})
    return out


def legacy_provenance(fields: dict) -> dict:
    m = {'FORM_FIELD': 'EXPLICIT', 'FOUNDER_CONFIRMED': 'EXPLICIT', 'STATED_IN_TEXT': 'STATED_IN_TEXT',
         'MODEL_SUGGESTED_UNCONFIRMED': 'INFERRED_UNCONFIRMED', 'NOT_STATED': 'UNKNOWN', 'PARSER_FAILED': 'UNKNOWN'}
    return {f: m[fields[f]['status']] for f in FIELDS if f in fields}


def d02(fields: dict) -> dict:
    """Idea-clarity check (D02) computed from typed fields. Model suggestions never count as captured."""
    missing, unconfirmed, failed = [], [], []
    for f in D02_REQUIRED:
        st = (fields.get(f) or {}).get('status', 'NOT_STATED')
        if st == 'PARSER_FAILED':
            failed.append(f)
        elif st == 'MODEL_SUGGESTED_UNCONFIRMED':
            unconfirmed.append(f)
        elif st not in COUNTS_AS_CAPTURED:
            missing.append(f)
    to_confirm = [f for f in D02_REQUIRED if (fields.get(f) or {}).get('status') == 'STATED_IN_TEXT']
    status = 'PASS' if not (missing or unconfirmed or failed) else 'FAIL'
    return {'status': status, 'missing': missing, 'model_suggested_unconfirmed': unconfirmed, 'parser_failed': failed,
            'stated_in_text_please_confirm': to_confirm,
            'questions': {f: QUESTIONS[f] for f in missing + unconfirmed + failed}}

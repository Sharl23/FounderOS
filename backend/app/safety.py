"""Trusted, deterministic safety policy. No LLM is consulted and no LLM can override it.

This is a conservative English keyword/pattern screen, NOT a legal review and NOT a complete
abuse detector. It errs toward BLOCK for organizer MUST-NEVER rules and toward REVIEW_REQUIRED
for high-stakes domains. Only founder-supplied text is screened (never model output as a
substitute for the founder's words).
"""
from __future__ import annotations
import re

POLICY_VERSION = 'safety-policy-2026-11-17.2'

# A nearby negation ("we will never buy fake reviews", "detect scams") turns a match into a
# value statement. Commas break the window so "no worries, write fake reviews" is still caught.
_NEG = re.compile(r"(?i)\b(no|not|never|without|avoid\w*|don'?t|do not|won'?t|will not|refus\w*|prevent\w*|"
                  r"detect\w*|against|ban\w*|prohibit\w*|stop\w*|fight\w*|combat\w*|report\w*|flag\w*|anti|"
                  r"protect\w*|warn\w*|spot\w*|identify\w*|block\w*|remov\w*|educat\w*|awareness)\b[^.;,!?\n]{0,28}$")

# (rule_id, organizer rule, pattern, reason, safe revision, negation_can_excuse)
_BLOCK = [
    ('FAKE_SOCIAL_PROOF', 'Never generate fake reviews, testimonials, or sign-ups',
     r"\b(fake|fabricat\w*|made[- ]up|bogus|phony|phoney|invent(ed|ing)?|synthetic|sock ?puppet\w*|astroturf\w*)\b[^.;!?\n]{0,30}\b(reviews?|testimonials?|sign[- ]?ups?|ratings?|followers|customers?|users|interviews?|surveys?|survey (results|responses)|waitlist|traction|downloads|endorsements?|case stud(y|ies)|social proof)\b"
     r"|\b(buy|buying|purchase|purchasing|pay for|paying for)\s+(\w+\s+){0,3}(reviews?|testimonials?|sign[- ]?ups?|ratings?|followers|likes|endorsements?)\b"
     r"|\b(generate|generating|auto[- ]?generate\w*|ai[- ]generated|write|writing|post|posting)\s+(\w+\s+){0,2}(5[- ]star |five[- ]star |positive |glowing )(reviews?|testimonials?|ratings?)\b"
     r"|\b(generate|generating|auto[- ]?generate\w*|ai[- ]generated)\s+(\w+\s+){0,2}(reviews?|testimonials?|sign[- ]?ups?|endorsements?)\b",
     'The brief asks for fabricated reviews, testimonials, sign-ups, customers or research results.',
     'Collect real, consented feedback from real people and log it in the evidence ledger as founder-reported.', True),
    ('IMPERSONATION', 'Never impersonate the founder, customers, or other brands',
     r"\b(impersonat\w*|pretend(ing)? to be|pose as|posing as|masquerad\w*|spoof\w*|clone (the |their |a )?(brand|website|site|app|login page)|look[- ]?alike (site|page|brand|domain)|deepfake\w*|fake (accounts?|profiles?|identit(y|ies)|personas?)|in the name of (a |an |the )?(real|famous|well[- ]known|another) (brand|company|person))\b",
     'The brief involves impersonating a person, customer or brand.',
     'Use your own clearly identified brand and identity in every communication.', True),
    ('INCOME_GUARANTEE', 'Never promise income or guarantee success',
     r"\bguarante\w*\b[^.;!?\n]{0,40}\b(income|profits?|returns?|earnings|revenue|success|roi|rich|salary|wealth|money|to make)\b"
     r"|\bpromis(e|es|ing)\s+(\w+\s+){0,3}(income|profits|returns|earnings|success|wealth|to make money)\b"
     r"|\b(get[- ]rich[- ]quick|double your money|risk[- ]free (income|returns?|profits?)|passive income guaranteed)\b",
     'The brief promises income, returns or guaranteed success.',
     'Describe outcomes as untested hypotheses; never promise earnings or success to anyone.', True),
    ('MONEY_MOVEMENT', 'Never hold, transfer, or refund money on its own; leave payments out completely',
     r"\b(you|founder ?os|the ai|ai agents?|the agents?|the assistant|the bot|co-?founder agent|the system)\b[^.;!?\n]{0,50}\b(hold|holds|keep|keeps|transfer|transfers|wire|wires|refund|refunds|charge|charges|collect|collects|move|moves|withdraw|withdraws|pay|pays|process|processes|send|sends)\b[^.;!?\n]{0,30}\b(money|funds|payments?|deposits?|refunds?|cash|egp|usd|dollars|pounds|wallets?|bank transfers?)\b"
     r"|\b(hold|transfer|refund|move|wire|send)\s+(\w+\s+){0,3}(money|funds|refunds?|payments?)\s+(\w+\s+){0,3}(automatically|on (its|your) own|without (my |founder |human )?approval)\b",
     'The brief asks the system to hold, move, charge or refund money.',
     'FounderOS drafts pricing hypotheses only. Any real payment must be handled by the founder outside this system.', True),
    ('UNAPPROVED_EXTERNAL_ACTION', 'Never publish, send, or spend anything without approval',
     r"\b(publish|post|send|email|message|spend|buy|purchase|sign|launch|deploy|contact|outreach|advertis\w*)\w*\b[^.;!?\n]{0,50}\bwithout (asking|waiting|(my |the founder'?s? |founder |human |any |explicit |prior )?(approval|permission|review|consent|confirmation|sign[- ]?off))\b"
     r"|\b(you|founder ?os|the ai|ai agents?|the agents?|the assistant|the bot)\b[^.;!?\n]{0,30}\b(auto(matically)?|autonomously|on (its|your) own|by (it|your)self)\b[^.;!?\n]{0,30}\b(publish|post|send|email|message|spend|buy|purchase|sign|launch|contact)\w*\b"
     r"|\b(you|founder ?os|the ai|ai agents?|the agents?|the assistant|the bot)\s+(should |can |must |will |to )?(publish|post|send|email|spend|buy|purchase|sign|launch|contact)\w*\b[^.;!?\n]{0,50}\b(on my behalf|for me|immediately|right away|now)\b"
     r"|\b(skip|bypass|no need for)\s+(\w+\s+){0,2}(approval|permission|sign[- ]?off)\b"
     r"|\b(spam\w*|mass[- ]?(email|dm|messag)\w*|blast\w* (emails?|messages?) to (scraped|purchased|bought))\b",
     'The brief asks for publishing, sending, spending or signing without specific founder approval.',
     'Every external action needs a separate, action-specific founder approval. This MVP performs none.', True),
    ('CREDENTIAL_STORAGE', 'Never store passwords or card details',
     r"\b(store|stores|storing|save|saves|saving|keep|keeps|keeping|remember|log|logs|logging|collect|collects|collecting|harvest\w*|record|records|ask for)\b[^.;!?\n]{0,50}\b(card (details|numbers?|data)|credit ?card (numbers?|details|data)|debit ?card (numbers?|details)|cvv|cvc|bank(ing)? (logins?|passwords?|credentials)|one[- ]time (codes?|passwords?)|otp codes?)\b"
     r"|\b(store|save|keep|remember|log|record|collect|harvest\w*)\s+(\w+\s+){0,2}(my|our|their|customers'?|users'?|clients'?|plain[- ]?text|account)\s+(\w+\s+)?(passwords?|login credentials|credentials|logins?)\b"
     r"|\bplain[- ]?text passwords?\b",
     'The brief asks to store passwords, card details or other credentials.',
     'Never collect credentials or card data. Remove this requirement.', True),
    ('PROMPT_INJECTION', 'Approval rules cannot be changed by prompt text',
     r"\b(ignore|disregard|forget|override|overrule|bypass|disable|turn off)\b[^.;!?\n]{0,30}\b(instructions?|system prompt|safety (rules?|polic(y|ies)|checks?)|approval (rules?|gates?|process|requirements?)|guardrails?|your rules|the rules|all rules|previous rules|prior rules|gates?)\b"
     r"|\b(auto[- ]?approv\w*|approve (it|this|everything|all( phases)?|the (gate|phase|idea))( \w+){0,2} (yourself|automatically|for me|without me)|mark (it|this|the idea|demand|the business) (as )?(validated|approved|verified|proven)|you are now (the|a|an|in)|act as (the )?(founder|admin|administrator|system)|developer mode|jailbreak\w*|system override)\b",
     'The brief contains instructions that try to change approval or safety rules.',
     'Remove the instruction. Gates are enforced by backend code and cannot be changed by text.', False),
    ('FRAUD_OR_ILLEGAL', 'Deceptive, fraudulent or illegal operation',
     r"\b(phish\w*|scam\w*|ponzi|pyramid scheme|money launder\w*|launder(ing)? (money|funds|cash)|counterfeit\w*|forg(ed|ing|ery) (documents?|signatures?|ids?|certificates?|papers?)|stolen (data|cards?|accounts?|credentials)|steal\w* (data|passwords?|accounts?|identit\w*|credentials)|hack(ing)? into|crack(ing)? (accounts?|passwords?)|malware|ransomware|spyware|stalkerware|keylogger\w*|credential stuffing|fake (documents?|ids?|id cards?|certificates?|degrees?|diplomas?|invoices?|prescriptions?|receipts?)|sell\w* (personal|private|user|customer) data|scrap\w* (personal|private) (data|information) without|catfish\w*|blackmail\w*|extort\w*|dox+\w*|(mislead|deceiv|trick)\w* (customers|users|investors|people|buyers|students)|dark pattern\w*|bait[- ]and[- ]switch|pump[- ]and[- ]dump|(take|write|do) (their|students'?|others'?) (exams?|theses|thesis|assignments) for (them|money)|exam cheating|cheat(ing)? (on|in) (exams?|tests?))\b",
     'The brief describes a deceptive, fraudulent or illegal operation.',
     'Reframe around a lawful, transparent service that users knowingly opt into.', True),
]

_REVIEW = [
    ('HEALTH', r"\b(medical|medicine|medications?|diagnos\w*|patients?|clinic\w*|hospital\w*|therap\w*|mental health|drugs?|pharmac\w*|prescription\w*|symptoms?|disease\w*|doctors?|diet pills?|supplements?|pregnan\w*)\b",
     'Health-related domain: wrong information can harm people; health data is sensitive.'),
    ('FINANCE', r"\b(invest\w*|loans?|lending|credit scor\w*|insurance|trading|forex|crypto\w*|stocks?|securities|banking|fintech|e-?wallets?|remittance\w*|money transfers?|micro[- ]?financ\w*|tax (advice|filing))\b",
     'Financial domain: often licensed/regulated. FounderOS itself never handles payments or money.'),
    ('MINORS', r"\b(child(ren)?|kids?|minors?|under[- ]?1[0-8]|school ?(children|kids|students|pupils)|high[- ]school\w*|teen(s|agers?)?|toddlers?|bab(y|ies)|k[- ]?12|primary school|preparatory school|parents)\b",
     'Product may involve minors: consent, guardianship and child-data protections apply.'),
    ('LEGAL', r"\b(legal advice|lawyers?|law firm|contracts? (review|drafting)|court\w*|immigration|visas?|litigation|notar\w*)\b",
     'Legal-services domain: advice may be restricted to licensed professionals.'),
    ('SENSITIVE_DATA', r"\b(personal data|private data|biometric\w*|face recognition|facial recognition|location (tracking|data)|track(ing)? (users|people|employees|students|location)|surveillance|monitor(ing)? (employees|students|children|users|people)|national ids?|id (cards?|numbers?)|health records?|scrap\w*|data brokers?|contact lists?|passwords?|password manager)\b",
     'Collection or processing of personal/sensitive data: consent and data-protection duties apply.'),
    ('PEOPLE_DECISIONS', r"\b(hiring decisions?|screen(ing)? (candidates|applicants|tenants)|background checks?|tenants?|evict\w*)\b",
     'High-stakes decisions about people (employment/housing): fairness and legal risk.'),
]

_BLOCK_C = [(a, b, re.compile(p, re.I), d, e, n) for a, b, p, d, e, n in _BLOCK]
_REVIEW_C = [(a, re.compile(p, re.I), d) for a, p, d in _REVIEW]


def _hits(rx, text, allow_negation=True):
    out = []
    for m in rx.finditer(text):
        before = text[max(0, m.start() - 40):m.start()]
        if allow_negation and _NEG.search(before):
            continue
        out.append(text[max(0, m.start() - 25):m.end() + 25].strip().replace('\n', ' ')[:160])
        if len(out) >= 2:
            break
    return out


def find_blocks(text: str) -> list[dict]:
    text = text or ''
    findings = []
    for rule_id, rule, rx, why, fix, neg_ok in _BLOCK_C:
        hits = _hits(rx, text, allow_negation=neg_ok)
        if hits:
            findings.append({'rule_id': rule_id, 'severity': 'BLOCK', 'organizer_rule': rule,
                             'reason': why, 'matched_text': hits, 'safe_revision': fix})
    return findings


def feasibility_notes(fields: dict) -> list[str]:
    notes = []
    if not fields.get('budget'):
        notes.append('Budget UNKNOWN: experiment cost cannot be checked against constraints.')
    elif re.search(r'^\s*(0|zero|none|no budget)\b', str(fields.get('budget')), re.I):
        notes.append('Stated budget is zero: only free experiments (interviews, manual opt-in forms) are feasible.')
    if not fields.get('timeline'):
        notes.append('Timeline UNKNOWN: experiment time-boxes are estimates only.')
    if not fields.get('skills'):
        notes.append('Founder skills UNKNOWN: build feasibility cannot be assessed.')
    return notes


def screen(text: str, fields: dict | None = None) -> dict:
    """Deterministic assessment of founder-supplied text. Persisted per brief version."""
    text = text or ''
    findings = find_blocks(text)
    for rule_id, rx, why in _REVIEW_C:
        hits = _hits(rx, text, allow_negation=False)
        if hits:
            findings.append({'rule_id': rule_id, 'severity': 'REVIEW', 'organizer_rule': None, 'reason': why,
                             'matched_text': hits,
                             'safe_revision': 'Research-only discovery is allowed after you acknowledge this risk. Consult a qualified professional before building or launching.'})
    status = 'BLOCK' if any(f['severity'] == 'BLOCK' for f in findings) else 'REVIEW_REQUIRED' if findings else 'ALLOW_DISCOVERY'
    return {
        'status': status, 'policy_version': POLICY_VERSION, 'findings': findings,
        'feasibility_notes': feasibility_notes(fields or {}),
        'limitations': [
            'Deterministic English keyword/pattern screen enforced by backend code. It is not a legal review and certifies nothing.',
            'It can miss harmful ideas and can flag harmless ones. "High-stakes" does not mean illegal.',
            'A BLOCK cannot be overridden by founder approval or by model output. Revise the brief instead.',
        ],
    }


_INJ = next(rx for rid, _, rx, _, _, _ in _BLOCK_C if rid == 'PROMPT_INJECTION')


def looks_like_injection(text: str) -> bool:
    return bool(_INJ.search(text or ''))

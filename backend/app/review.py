"""Evidence relevance review (v0.8): 'the words appeared' is not 'the claim is supported'.

Pipeline states shown to the founder:
  CANDIDATE_METADATA -> PAGE_FETCHED -> EXCERPT_MATCHED   (verification: done by code)
  then the review result:  ACCEPTED_RELEVANT | CONTEXT_ONLY | EXCLUDED   (decided by code from five explicit answers)

The five relevance questions (each YES / NO / UNSURE, some NOT_APPLICABLE):
  claim_supported  Does the passage itself support (or challenge) the claim — not just mention the same words?
  geography        Is it about your target market (country/city)?
  buyer_user       Is it about your customer or buyer group?
  method           Is the method credible for this claim (a count of actions, a survey, an official dataset, an opinion piece...)?
  date             Is it recent enough (within the age limit) or dated at all?
Only ACCEPTED_RELEVANT rows can count toward a granular rubric check.
"""
from __future__ import annotations
import re
from typing import Literal

from pydantic import BaseModel

from .rubric import is_reserved_url

YN = Literal['YES', 'NO', 'UNSURE']
YNA = Literal['YES', 'NO', 'UNSURE', 'NOT_APPLICABLE']

QUESTIONS = {
    'claim_supported': 'Does the passage itself support or challenge your claim (not just use the same words)?',
    'geography': 'Is it about your target market (country or city)?',
    'buyer_user': 'Is it about your customer or buyer group?',
    'method': 'Is the method credible for this claim (counted actions, official data, a real survey), not just an opinion?',
    'date': 'Is it dated and recent enough for this decision?',
}


class RelevanceChecks(BaseModel):
    claim_supported: YN = 'UNSURE'
    geography: YNA = 'UNSURE'
    buyer_user: YNA = 'UNSURE'
    method: YNA = 'UNSURE'
    date: YNA = 'UNSURE'


_STOP = set('a an and are as at be by for from has have in into is it its of on or that the their this to was were with who will can more than not no our your they them these those which what when where how about also very'.split())


def _stems(s: str) -> set:
    return {w[:5] for w in re.findall(r'[a-z؀-ۿ]{3,}', (s or '').lower()) if w not in _STOP}


def term_overlap(claim: str, excerpt: str) -> int:
    return len(_stems(claim) & _stems(excerpt))


def decide(checks: dict | None, *, claim: str, excerpt: str | None, url: str | None, verified: bool,
           founder_supplied: bool = False, metadata_only: bool = False, customer_research: bool = False) -> tuple[str | None, str, list[str]]:
    """Return (review_state, reason, flags). review_state None = legacy client without a review (dimension-level only)."""
    flags = []
    if url and is_reserved_url(url):
        return 'EXCLUDED', 'Reserved documentation domain (e.g. example.com): placeholder text, never evidence.', flags
    if metadata_only:
        return 'CONTEXT_ONLY', 'Bibliographic metadata or abstract only: not an inspected passage.', flags
    if not customer_research and not verified and not founder_supplied:
        return 'EXCLUDED', 'The excerpt was not found at the URL, so nothing was verified.', flags
    if excerpt and not customer_research:
        ov = term_overlap(claim, excerpt)
        if ov == 0:
            return 'EXCLUDED', 'The passage shares no key term with your claim: the words on the page do not support it.', flags
        if ov == 1:
            flags.append('Only one key term is shared between the claim and the passage; check that it really supports the claim.')
    if founder_supplied:
        flags.append('Founder-supplied excerpt: not automatically verified at the URL.')
    if checks is None:
        if customer_research:
            return 'ACCEPTED_RELEVANT', 'Founder-run research with consent (founder-reported, not independently verified).', flags
        return None, 'No relevance review submitted (legacy API client): counts at dimension level only, never for a granular check.', flags
    c = RelevanceChecks(**checks).model_dump()
    if c['claim_supported'] == 'NO':
        return 'EXCLUDED', 'You said the passage does not support or challenge the claim.', flags
    if c['geography'] == 'NO':
        return 'EXCLUDED', 'About a different market than your target market.', flags
    no = [k for k in ('buyer_user', 'method', 'date') if c[k] == 'NO']
    if no:
        return 'CONTEXT_ONLY', 'Kept as context: ' + ', '.join(QUESTIONS[k].split('(')[0].strip().rstrip('?').lower() for k in no) + ' — answered no.', flags
    unsure = [k for k, v in c.items() if v == 'UNSURE']
    if unsure:
        return 'CONTEXT_ONLY', 'Kept as context until you can answer: ' + ', '.join(unsure).replace('_', ' ') + '.', flags
    return 'ACCEPTED_RELEVANT', 'All five relevance questions answered yes (or not applicable).', flags


def legacy_relevance(state: str | None, fallback: str) -> str:
    return {'ACCEPTED_RELEVANT': 'CLAIM_RELEVANT', 'EXCLUDED': 'IRRELEVANT', 'CONTEXT_ONLY': 'UNSURE'}.get(state, fallback)

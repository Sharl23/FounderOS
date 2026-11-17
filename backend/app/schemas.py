"""Typed boundaries shared by the founder-facing API and the local LLM."""
from __future__ import annotations
from datetime import date
from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel, Field, field_validator, model_validator

BRIEF_FIELDS = ('problem', 'target_customers', 'skills', 'budget', 'timeline', 'target_market', 'values', 'constraints')
Dimension = Literal['desirability', 'demand', 'competition', 'feasibility', 'viability']


class ProjectCreate(BaseModel):
    idea: str = Field(min_length=12, max_length=6000)
    target_customers: str | None = Field(default=None, max_length=300)
    skills: str | None = Field(default=None, max_length=500)
    budget: str | None = Field(default=None, max_length=100)
    timeline: str | None = Field(default=None, max_length=100)
    target_market: str | None = Field(default=None, max_length=200)
    values: str | None = Field(default=None, max_length=800)
    constraints: str | None = Field(default=None, max_length=800)


# ---- LLM output contracts (kept small so a 1.5B CPU model answers quickly and validly)
class RefinedBrief(BaseModel):
    idea_summary: str
    problem: str | None = None
    target_customers: str | None = None
    skills: str | None = None
    budget: str | None = None
    timeline: str | None = None
    target_market: str | None = None
    values: str | None = None
    constraints: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class DiscoveryReport(BaseModel):
    problem_statement: str
    target_customers: list[str] = Field(min_length=1)
    value_proposition: str
    alternatives_unverified: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(min_length=1)
    unknowns: list[str] = Field(default_factory=list)
    experiments: list[str] = Field(min_length=1)


class ValidationReport(BaseModel):
    summary: str
    market_research_vs_customer_demand: str
    risks: list[str] = Field(default_factory=list)
    contradictions_or_gaps: list[str] = Field(default_factory=list)
    pricing_hypotheses: list[str] = Field(default_factory=list)
    business_model_hypotheses: list[str] = Field(default_factory=list)
    competitor_research_limitations: list[str] = Field(default_factory=list)


# ---- founder requests
class ClarifyRequest(BaseModel):
    answers: dict[str, str] = Field(min_length=1, max_length=10)

    @field_validator('answers')
    @classmethod
    def nonempty_answers(cls, answers):
        bad = [k for k in answers if k not in BRIEF_FIELDS]
        if bad:
            raise ValueError(f'Allowed fields: {list(BRIEF_FIELDS)}')
        if any(len(v) > 1500 or not v.strip() for v in answers.values()):
            raise ValueError('Answers must contain 1–1500 non-whitespace characters')
        return answers


class SafetyAck(BaseModel):
    brief_version: int
    statement: str = Field(min_length=10, max_length=600)


class DecisionRequest(BaseModel):
    run_id: str
    report_hash: str = Field(min_length=64, max_length=64)
    brief_version: int
    decision: Literal['APPROVE', 'REVISE', 'PIVOT', 'STOP']
    feedback: str = Field(default='', max_length=2000)
    acknowledge_risk: bool = False


class EvidenceAdd(BaseModel):
    kind: Literal['SECONDARY_BACKGROUND', 'CUSTOMER_STATEMENT', 'CUSTOMER_BEHAVIOR'] = 'SECONDARY_BACKGROUND'
    dimension: Dimension = 'desirability'
    claim_id: str | None = Field(default=None, max_length=12)
    claim: str = Field(min_length=8, max_length=800)
    direction: Literal['SUPPORTS', 'CONTRADICTS', 'UNSURE'] = 'UNSURE'
    relevance: Literal['CLAIM_RELEVANT', 'IRRELEVANT', 'UNSURE'] = 'UNSURE'
    # secondary sources
    url: str | None = Field(default=None, max_length=2000)
    excerpt: str | None = Field(default=None, max_length=1600)
    title: str | None = Field(default=None, max_length=300)
    publisher: str | None = Field(default=None, max_length=200)
    author: str | None = Field(default=None, max_length=200)
    published_on: str | None = Field(default=None, max_length=40)
    geography: str | None = Field(default=None, max_length=120)
    # founder-run customer research
    method: str | None = Field(default=None, max_length=600)
    sample_size: int | None = Field(default=None, ge=1, le=100000)
    positives: int | None = Field(default=None, ge=0, le=100000)
    segment: str | None = Field(default=None, max_length=300)
    collected_from: date | None = None
    collected_to: date | None = None
    consent_confirmed: bool = False
    positive_signals: str | None = Field(default=None, max_length=1000)
    negative_signals: str | None = Field(default=None, max_length=1000)

    @field_validator('url')
    @classmethod
    def public_https_only(cls, value):
        if value is None:
            return value
        p = urlparse(value)
        if p.scheme != 'https' or not p.hostname or p.username or p.password:
            raise ValueError('Only HTTPS URLs without userinfo are supported')
        return value

    @model_validator(mode='after')
    def by_kind(self):
        if self.kind == 'SECONDARY_BACKGROUND':
            if not self.url or not self.excerpt or len(self.excerpt.strip()) < 12:
                raise ValueError('Secondary sources need a public HTTPS url and an exact excerpt (12+ chars).')
        else:
            if not self.method or not self.sample_size or not self.collected_from:
                raise ValueError('Customer evidence needs method, number of relevant participants and collection date.')
            if not self.consent_confirmed:
                raise ValueError('Confirm participants knowingly consented. Do not log data from people who did not.')
            if self.positives is not None and self.positives > self.sample_size:
                raise ValueError('positives cannot exceed sample_size')
            if self.collected_to and self.collected_to < self.collected_from:
                raise ValueError('collected_to is before collected_from')
            if self.collected_from > date.today():
                raise ValueError('Results cannot be dated in the future')
        return self


class ExperimentDraft(BaseModel):
    hypothesis: str = Field(min_length=10, max_length=600)
    claim_id: str | None = Field(default='C-DEM', max_length=12)
    dimension: Dimension = 'demand'
    target_segment: str = Field(min_length=3, max_length=300)
    metric: str = Field(min_length=10, max_length=400)
    success_threshold_pct: float = Field(gt=0, le=100)
    adverse_threshold_pct: float = Field(ge=0, lt=100)
    min_sample: int = Field(ge=1, le=100000)
    critical: bool = True
    pivot_alternative: str | None = Field(default=None, max_length=400)
    consent_method: str = Field(min_length=10, max_length=600)
    founder_actions: str = Field(min_length=10, max_length=1200)
    timebox_estimate: str = Field(default='ESTIMATE: unknown', max_length=120)
    cost_estimate: str = Field(default='ESTIMATE: unknown', max_length=120)

    @model_validator(mode='after')
    def thresholds(self):
        if self.adverse_threshold_pct >= self.success_threshold_pct:
            raise ValueError('adverse threshold must be below the success threshold')
        return self


class ExperimentLock(BaseModel):
    version: int
    criteria_hash: str = Field(min_length=64, max_length=64)
    confirm: Literal['I_PREREGISTER_THESE_CRITERIA_BEFORE_COLLECTING_RESULTS']


class ExperimentResult(BaseModel):
    version: int
    criteria_hash: str = Field(min_length=64, max_length=64)
    sample_size: int = Field(ge=1, le=100000)
    positives: int = Field(ge=0, le=100000)
    method: str = Field(min_length=10, max_length=600)
    collected_from: date
    collected_to: date
    consent_confirmed: bool
    positive_signals: str | None = Field(default=None, max_length=1000)
    negative_signals: str | None = Field(default=None, max_length=1000)

    @model_validator(mode='after')
    def sane(self):
        if self.positives > self.sample_size:
            raise ValueError('positives cannot exceed sample_size')
        if self.collected_to < self.collected_from:
            raise ValueError('collected_to is before collected_from')
        if self.collected_to > date.today():
            raise ValueError('Results cannot be dated in the future')
        if not self.consent_confirmed:
            raise ValueError('Confirm participants knowingly consented.')
        return self


class PublicActionRequest(BaseModel):
    kind: Literal['PUBLISH', 'SEND', 'SPEND', 'SIGN', 'PAY', 'REFUND', 'TRANSFER', 'CONTACT']
    description: str = Field(min_length=5, max_length=500)

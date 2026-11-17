"""STUBBED offline stand-in for the local model, used ONLY by scripts/demo_run.py when Ollama is not reachable.

It is not a language model and is never loaded by the app. Everything it returns is either the founder's own words,
copied back, or a fixed, clearly labelled placeholder hypothesis. Every agent-log entry it touches carries the model
name below, so nobody can mistake its output for a model result.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.schemas import RefinedBrief, DiscoveryReport, ValidationReport, JudgeOutput, CheckJudgeOutput  # noqa: E402

LABEL = 'STUBBED offline stand-in (no model ran)'


def _find(ctx, *keys):
    """Pull the founder's own text out of the request context, wherever the app put it."""
    if isinstance(ctx, dict):
        for k in keys:
            v = ctx.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        for v in ctx.values():
            hit = _find(v, *keys)
            if hit:
                return hit
    return None


class DemoStubModel:
    model = LABEL
    last_latency_ms = 0

    async def status(self):
        return {'ollama_reachable': False, 'model_pulled': False, 'error': LABEL}

    async def generate(self, system, context, output_type, max_tokens=700):
        idea = _find(context, 'founder_input', 'original_idea_text', 'idea', 'idea_summary') or 'the founder idea'
        if output_type is RefinedBrief:
            return RefinedBrief(idea_summary=idea[:300], problem=_find(context, 'problem') or 'STUBBED: problem not yet stated by the founder',
                                target_customers=_find(context, 'target_customers') or 'STUBBED: customer not yet stated by the founder',
                                target_market=_find(context, 'target_market') or 'STUBBED: market not yet stated',
                                questions=['Who exactly has this problem most often?', 'What do they use today instead?'],
                                current_workaround=_find(context, 'current_workaround') or 'STUBBED: unknown',
                                assumptions=['STUBBED placeholder: demand is unknown until a demand test is run'], risk_flags=[])
        if output_type is DiscoveryReport:
            return DiscoveryReport(problem_statement=f'ASSUMPTION (stubbed hypothesis): {idea[:240]}',
                                   target_customers=[_find(context, 'target_customers') or 'Unconfirmed customer segment'],
                                   value_proposition='ASSUMPTION (stubbed hypothesis): untested value proposition taken from the founder idea',
                                   alternatives_unverified=['Asking friends or classmates (unverified)', 'General map apps (unverified)'],
                                   hypotheses=['ASSUMPTION (stubbed hypothesis): the target customer has this problem often enough to act on it',
                                               'ASSUMPTION (stubbed hypothesis): the current workaround is slow or unreliable'],
                                   experiments=['Run a consented, opt-in waitlist test with a pre-registered pass mark'],
                                   unknowns=['Willingness to pay', 'How often the problem occurs'],
                                   directions=[{'name': 'Narrow first segment', 'segment': 'One campus', 'value': 'Smaller test, faster learning'},
                                               {'name': 'Different job to be done', 'segment': 'Same users', 'value': 'Re-check the problem first'}])
        if output_type is ValidationReport:
            return ValidationReport(summary='STUBBED: no model ran. The verdict comes from code: no independent evidence of purchasing demand.',
                                    market_research_vs_customer_demand='No accepted evidence; demand untested',
                                    risks=['Demand is not confirmed'], contradictions_or_gaps=['No recorded customer behaviour'],
                                    pricing_hypotheses=['ASSUMPTION: untested price point'], business_model_hypotheses=['ASSUMPTION: subscription (untested)'],
                                    competitor_research_limitations=['No competitor data was sourced in this demo run'])
        if output_type is CheckJudgeOutput:
            ids = [e['id'] for e in context.get('accepted_evidence', [])]
            return CheckJudgeOutput(check_id=context['check']['id'], rating='MIXED', evidence_ids=ids[:1], reasoning='STUBBED: no model ran.')
        if output_type is JudgeOutput:
            ids = [e['id'] for e in context.get('accepted_evidence', [])]
            return JudgeOutput(criterion_id=context['criterion']['id'], proposed_score=3, evidence_ids=ids[:1],
                               reasoning='STUBBED: no model ran.', caveats=['STUBBED offline stand-in'])
        raise RuntimeError(f'Unexpected schema {output_type.__name__}')

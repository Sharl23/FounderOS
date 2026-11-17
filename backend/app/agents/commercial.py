"""Commercial agent (Phase 4): pricing hypotheses, business-model alternatives, unit economics, break-even.

All arithmetic is deterministic code. Every input the founder has not evidenced is an ASSUMPTION, and every
output is a CALCULATED SCENARIO, never a verified financial outcome. This is not financial or legal advice.
"""
from __future__ import annotations
import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Package(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    price: float = Field(ge=0, le=100000)
    includes: list[str] = Field(default_factory=list, max_length=8)


class CommercialInputs(BaseModel):
    currency: str = Field(default='USD', pattern='^[A-Z]{3}$')
    billing: Literal['one_time', 'monthly'] = 'one_time'
    price: float = Field(gt=0, le=100000)
    variable_cost_per_sale: float = Field(default=0, ge=0, le=100000)
    payment_fee_pct: float = Field(default=2.9, ge=0, le=30)
    payment_fee_fixed: float = Field(default=0.30, ge=0, le=100)
    fixed_costs_monthly: float = Field(default=0, ge=0, le=10_000_000)
    build_cost_one_off: float = Field(default=0, ge=0, le=10_000_000)
    sales_per_month_low: int = Field(default=2, ge=0, le=1_000_000)
    sales_per_month_base: int = Field(default=10, ge=0, le=1_000_000)
    sales_per_month_high: int = Field(default=30, ge=0, le=1_000_000)
    monthly_churn_pct: float = Field(default=10, gt=0, le=100)
    packages: list[Package] = Field(default_factory=list, max_length=4)
    evidence_note: str | None = Field(default=None, max_length=600)

    @model_validator(mode='after')
    def ordered(self):
        if not (self.sales_per_month_low <= self.sales_per_month_base <= self.sales_per_month_high):
            raise ValueError('Sales scenarios must be ordered: low <= base <= high')
        return self


def r2(x):
    from decimal import Decimal, ROUND_HALF_UP
    return float(Decimal(str(round(x, 9))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def unit_economics(i: CommercialInputs, price: float | None = None) -> dict:
    p = i.price if price is None else price
    fee = p * i.payment_fee_pct / 100 + i.payment_fee_fixed
    contribution = p - fee - i.variable_cost_per_sale
    margin = contribution / p * 100 if p else 0
    be = math.ceil(i.fixed_costs_monthly / contribution) if contribution > 0 else None
    if contribution > 0 and i.fixed_costs_monthly == 0:
        be = 0
    scen = {}
    for k in ('low', 'base', 'high'):
        n = getattr(i, f'sales_per_month_{k}')
        profit = n * contribution - i.fixed_costs_monthly
        payback = math.ceil(i.build_cost_one_off / profit) if profit > 0 and i.build_cost_one_off else (0 if profit > 0 else None)
        scen[k] = {'sales_per_month': n, 'revenue': r2(n * p), 'fees': r2(n * fee), 'variable_costs': r2(n * i.variable_cost_per_sale),
                   'contribution': r2(n * contribution), 'fixed_costs': r2(i.fixed_costs_monthly), 'profit_per_month': r2(profit),
                   'months_to_recover_build_cost': payback, 'label': 'CALCULATED SCENARIO from ASSUMPTION inputs'}
    ltv = r2(contribution / (i.monthly_churn_pct / 100)) if i.billing == 'monthly' else r2(contribution)
    return {'price': r2(p), 'fee_per_sale': r2(fee), 'contribution_per_sale': r2(contribution), 'contribution_margin_pct': r2(margin),
            'break_even_sales_per_month': be, 'break_even_note': ('Never breaks even: each sale loses money after fees and variable costs.' if be is None
                                                                 else f'{be} sale(s) per month cover the fixed costs.'),
            'lifetime_contribution_per_customer': ltv, 'scenarios': scen}


MODELS = {
    'one_time': ('One-time purchase', 'Simple to explain; revenue stops unless new buyers keep coming.'),
    'monthly': ('Subscription', 'Recurring revenue if people keep using it; churn decides everything.'),
    'freemium': ('Free tier + paid upgrade', 'Lowers the barrier; most free users never pay, so test conversion first.'),
    'per_use': ('Pay per use', 'Fits occasional use; revenue is lumpy.'),
    'b2b_license': ('Business licence (per site)', 'Fewer, larger customers; a longer sales cycle.'),
}


def plan(i: CommercialInputs, brief: dict) -> dict:
    ue = unit_economics(i)
    hyps = []
    for mult, tag in ((0.5, 'lower'), (1.0, 'entered'), (2.0, 'higher')):
        u = unit_economics(i, i.price * mult)
        hyps.append({'hypothesis': f'Customers will pay {u["price"]} {i.currency} ({tag} price point)', 'price': u['price'],
                     'contribution_per_sale': u['contribution_per_sale'], 'break_even_sales_per_month': u['break_even_sales_per_month'],
                     'status': 'HYPOTHESIS: untested. Test with a pre-registered demand test before relying on it.'})
    pk = [p.model_dump() | {'unit_economics': {k: v for k, v in unit_economics(i, p.price).items() if k != 'scenarios'}} for p in i.packages] or \
         [{'name': 'Standard', 'price': i.price, 'includes': ['Access to the digital product'], 'unit_economics': {k: v for k, v in ue.items() if k != 'scenarios'}}]
    country = ((((brief.get('fields') or {}).get('target_market') or {}).get('typed') or {}).get('country')) or 'your target country'
    checklist = [
        {'item': 'Terms of service (draft)', 'status': 'TO DO', 'note': 'What the buyer gets, access period, acceptable use.'},
        {'item': 'Refund policy (draft)', 'status': 'TO DO', 'note': f'Must meet consumer rules in {country}; check with a qualified professional.'},
        {'item': 'Privacy notice', 'status': 'TO DO', 'note': 'What personal data is collected (FounderOS collects none in the prototype).'},
        {'item': 'Business registration and tax', 'status': 'TO DO', 'note': f'Requirements in {country} are not checked by FounderOS.'},
        {'item': 'Payment provider account', 'status': 'NOT CREATED', 'note': 'FounderOS never creates accounts. Checkout is MOCKED / TEST MODE.'},
    ]
    return {'inputs': i.model_dump(), 'unit_economics': ue, 'pricing_hypotheses': hyps, 'packages': pk,
            'business_models': [{'id': k, 'name': v[0], 'trade_off': v[1], 'selected': k == i.billing} for k, v in MODELS.items()],
            'terms_checklist': checklist,
            'payment_provider': {'status': 'MOCKED', 'detail': 'No payment provider is configured. Live payment processing is disabled in code; only the built-in TEST MODE simulator exists.'},
            'labels': {'inputs': 'ASSUMPTION unless the evidence note says otherwise', 'outputs': 'CALCULATED SCENARIO, not a verified financial outcome',
                       'advice': 'Not financial, tax or legal advice.'}}

"""Operations Analyst agent (Phase 6): metrics derived ONLY from recorded events, plus labelled manual/mock metrics,
feedback with provenance, issues, and a rule-based recommendation (continue / iterate / pivot / stop / collect more data).

Every number names its source: DERIVED_FROM_EVENTS (orders/payment events/entitlements in this venture's database),
MANUAL (typed by the founder), or MOCK_DEMO (demo scenario, never treated as real performance).
In this build all sales events are MOCKED / TEST MODE, so derived sales metrics describe the simulation only.
"""
from __future__ import annotations

MIN_ORDERS = 10


def derived(orders: list[dict], events: list[dict], ents: list[dict]) -> dict:
    checkouts = len(orders)
    paid = [o for o in orders if o['status'] in ('PAID', 'REFUNDED')]
    refunded = [o for o in orders if o['status'] == 'REFUNDED']
    buyers = {}
    for o in paid:
        buyers[o['buyer_ref']] = buyers.get(o['buyer_ref'], 0) + 1
    repeat = sum(1 for n in buyers.values() if n > 1)
    gross = sum(o['amount_cents'] for o in paid)
    fees = sum(e['fee_cents'] for e in events if e['result'] == 'PAID_AND_DELIVERED')
    refunds = sum(o['amount_cents'] for o in refunded)
    used = [e for e in ents if e['deliveries'] > 0]
    m = {
        'checkouts_started': checkouts, 'orders_paid': len(paid), 'orders_refunded': len(refunded),
        'checkout_to_paid_pct': round(len(paid) / checkouts * 100, 1) if checkouts else None,
        'refund_rate_pct': round(len(refunded) / len(paid) * 100, 1) if paid else None,
        'unique_buyers': len(buyers), 'repeat_buyers': repeat, 'repeat_buyer_pct': round(repeat / len(buyers) * 100, 1) if buyers else None,
        'gross_cents': gross, 'fees_cents': fees, 'refunds_cents': refunds, 'net_cents': gross - fees - refunds,
        'access_links_used': len(used), 'access_usage_pct': round(len(used) / len(ents) * 100, 1) if ents else None,
        'duplicate_events_ignored': 0,
    }
    return {'source': 'DERIVED_FROM_EVENTS', 'mode': 'MOCKED / TEST MODE events', 'metrics': m}


def recommend(d: dict, manual: list[dict], feedback: list[dict], issues: list[dict], experiments: list[dict]) -> dict:
    m = d['metrics']
    reasons, rec = [], None
    open_high = [i for i in issues if i['status'] == 'OPEN' and i['severity'] == 'HIGH']
    if open_high:
        rec = 'ITERATE'
        reasons.append(f'{len(open_high)} open high-severity issue(s): fix before anything else.')
    if m['orders_paid'] < MIN_ORDERS:
        reasons.append(f'Only {m["orders_paid"]} paid order(s) recorded; at least {MIN_ORDERS} are needed before conversion or refund rates mean anything.')
        rec = rec or 'COLLECT_MORE_DATA'
    else:
        if m['refund_rate_pct'] is not None and m['refund_rate_pct'] >= 30:
            rec = 'ITERATE'
            reasons.append(f'Refund rate {m["refund_rate_pct"]}% is at or above 30%: buyers are not getting what they expected.')
        if m['checkout_to_paid_pct'] is not None and m['checkout_to_paid_pct'] < 20:
            rec = rec or 'ITERATE'
            reasons.append(f'Only {m["checkout_to_paid_pct"]}% of checkouts are paid.')
        if m['access_usage_pct'] is not None and m['access_usage_pct'] < 30:
            rec = 'PIVOT' if rec == 'ITERATE' else (rec or 'ITERATE')
            reasons.append(f'Only {m["access_usage_pct"]}% of buyers used their access: the product may not solve the problem.')
        if not rec:
            rec = 'CONTINUE'
            reasons.append('Recorded events show no red flag against the fixed thresholds.')
    neg = [f for f in feedback if f.get('sentiment') == 'NEGATIVE']
    if feedback and len(neg) / len(feedback) >= 0.5:
        rec = 'ITERATE' if rec in (None, 'CONTINUE', 'COLLECT_MORE_DATA') else rec
        reasons.append(f'{len(neg)} of {len(feedback)} feedback items are negative.')
    failed = [x for x in experiments if x.get('reading') == 'CLEAR_MISS' and x.get('critical')]
    if failed:
        rec = 'STOP' if rec != 'CONTINUE' else 'PIVOT'
        reasons.append(f'{len(failed)} critical demand test(s) were clear misses.')
    mock_only = all(x['source'] == 'MOCK_DEMO' for x in manual) if manual else True
    return {'recommendation': rec, 'reasons': reasons,
            'caveat': 'All sales events are MOCKED / TEST MODE' + (' and all manual metrics are MOCK_DEMO' if mock_only else '') +
                      ', so this recommendation is about the simulation, not real performance.',
            'thresholds': {'min_paid_orders': MIN_ORDERS, 'refund_rate_iterate_pct': 30, 'checkout_to_paid_min_pct': 20, 'access_usage_min_pct': 30}}


NEG = ('confus', 'slow', 'broken', 'bug', 'expensive', "doesn't", 'does not', 'hard to', 'useless', 'missing', 'wrong', 'refund')
POS = ('useful', 'love', 'great', 'helpful', 'easy', 'saved', 'works')


def sentiment(text: str) -> str:
    t = text.lower()
    n, p = sum(w in t for w in NEG), sum(w in t for w in POS)
    return 'NEGATIVE' if n > p else 'POSITIVE' if p > n else 'NEUTRAL'


def proposal_from(rec: dict, feedback: list[dict]) -> dict | None:
    """Turn a finding into a revision proposal for Phase 3 (prototype) or Phase 1 (brief). Never applied without approval."""
    r = rec['recommendation']
    if r in ('ITERATE',):
        lines = []
        for f in feedback:
            t = f['text'].lower()
            if 'search' in t and ('hard' in t or 'missing' in t):
                lines.append('show search')
            if 'filter' in t:
                import re
                m = re.search(r'filter (?:for|by) ([a-z \-]{3,25}?)(?= and | but |[,.;!?]|$)', t)
                if m:
                    lines.append(f'add filter: {m.group(1).strip().title()}')
        return {'target_phase': 3, 'rationale': 'Operate & Learn recommends ITERATE: ' + ' '.join(rec['reasons'][:2]),
                'change': {'feedback_commands': lines or ['headline: Revised after early feedback'], 'source': 'feedback + recorded events'}}
    if r in ('PIVOT', 'STOP'):
        return {'target_phase': 1, 'rationale': f'Operate & Learn recommends {r}: ' + ' '.join(rec['reasons'][:2]),
                'change': {'constraints': f'Operate & Learn finding ({r}): ' + '; '.join(rec['reasons'][:2])[:400], 'source': 'recorded events'}}
    return None

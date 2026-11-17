"""Sales & Delivery agent (Phase 5, steps 1-2): offer + sales-page DRAFT from the approved commercial plan and build.

The sales page is a draft for the founder. FounderOS has no code that publishes it, and it never contains
testimonials, ratings, scarcity, countdowns, income promises or claims of validated demand.
"""
from __future__ import annotations
import html
import re

BANNED = re.compile(r'(?i)\b(testimonial|reviews?|rated|\d(\.\d)? ?stars?|only \d+ left|limited time|offer ends|countdown|guarantee[ds]?|'
                    r'earn|income|profit|proven|validated|thousands of (users|customers)|best in|#1)\b')


def offer(spec: dict | None, plan: dict, package_index: int = 0) -> dict:
    pk = plan['packages'][min(package_index, len(plan['packages']) - 1)]
    name = (spec or {}).get('name') or 'Digital product'
    return {'product': f'{name}: prototype access', 'package': pk['name'], 'price': pk['price'], 'currency': plan['inputs']['currency'],
            'billing': plan['inputs']['billing'], 'delivers': 'Access link to the generated prototype files (DEMO-ONLY digital artifact)',
            'includes': pk.get('includes') or ['Access to the digital product'], 'mode': 'MOCKED / TEST MODE'}


def sales_page(o: dict, spec: dict | None) -> str:
    e = html.escape
    feats = ''.join(f'<li>{e(f["title"])}</li>' for f in (spec or {}).get('features', []))
    inc = ''.join(f'<li>{e(x)}</li>' for x in o['includes'])
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(o['product'])} (DRAFT)</title></head><body>
<p><strong>DRAFT SALES PAGE: not published. MOCKED / TEST MODE checkout only.</strong></p>
<h1>{e(o['product'])}</h1>
<p>{e((spec or {}).get('headline') or '')}</p>
<h2>What you get</h2><ul>{inc}</ul>
<h2>What it does</h2><ul>{feats}</ul>
<p>Price: {e(f"{o['price']:.2f}")} {e(o['currency'])} ({'per month' if o['billing'] == 'monthly' else 'one-time'}).</p>
<p>This is an early prototype with demonstration data. It is not validated and makes no promise of results.</p>
</body></html>"""
    return body


def check_page(page: str) -> list[str]:
    text = re.sub(r'<[^>]+>', ' ', page)
    text = text.replace('not validated', '').replace('no promise of results', '')
    return sorted({m.group(0).lower() for m in BANNED.finditer(text)})

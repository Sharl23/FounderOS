"""Revision agent (Phase 3 loop): founder feedback -> explicit spec overrides. Deterministic and auditable.

Understood commands (one per line, case-insensitive):
  name: <text> | headline: <text> | add filter: <text> | remove filter: <text> | color: <#RRGGBB or name>
  type: directory|forecast|practice|planner | hide search | show search
Anything else is kept as a note and reported as NOT APPLIED (nothing is guessed).
"""
from __future__ import annotations
import re

COLORS = {'teal': '#0E6E62', 'blue': '#1D4ED8', 'green': '#15803D', 'purple': '#6D28D9', 'orange': '#C2410C', 'red': '#B91C1C', 'black': '#111827', 'navy': '#1E3A8A'}


def parse(feedback: str, current: dict) -> tuple[dict, list[dict]]:
    o = {k: current.get(k) for k in ('name', 'headline', 'accent', 'archetype', 'show_search')}
    o['attributes'] = list(current.get('attributes') or [])
    log = []
    for raw in (feedback or '').splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r'(?i)^(name|title)\s*:\s*(.{2,60})$', line)
        if m:
            o['name'] = m.group(2).strip(); log.append({'line': line, 'applied': True, 'change': f'name -> {o["name"]}'}); continue
        m = re.match(r'(?i)^headline\s*:\s*(.{2,140})$', line)
        if m:
            o['headline'] = m.group(1).strip(); log.append({'line': line, 'applied': True, 'change': 'headline changed'}); continue
        m = re.match(r'(?i)^add (filter|feature)\s*:\s*(.{2,30})$', line)
        if m:
            v = m.group(2).strip()
            if v not in o['attributes'] and len(o['attributes']) < 8:
                o['attributes'].append(v)
            log.append({'line': line, 'applied': True, 'change': f'filter "{v}" added'}); continue
        m = re.match(r'(?i)^remove (filter|feature)\s*:\s*(.{2,30})$', line)
        if m:
            v = m.group(2).strip()
            o['attributes'] = [a for a in o['attributes'] if a.lower() != v.lower()]
            log.append({'line': line, 'applied': True, 'change': f'filter "{v}" removed'}); continue
        m = re.match(r'(?i)^colou?r\s*:\s*(#[0-9a-f]{6}|[a-z]+)$', line)
        if m:
            v = m.group(1).lower()
            c = v if v.startswith('#') else COLORS.get(v)
            log.append({'line': line, 'applied': bool(c), 'change': f'accent -> {c}' if c else f'unknown colour {v}'})
            if c:
                o['accent'] = c
            continue
        m = re.match(r'(?i)^type\s*:\s*(directory|forecast|practice|planner)$', line)
        if m:
            o['archetype'] = m.group(1).lower(); log.append({'line': line, 'applied': True, 'change': f'prototype type -> {o["archetype"]}'}); continue
        if re.match(r'(?i)^(hide|remove) search$', line):
            o['show_search'] = False; log.append({'line': line, 'applied': True, 'change': 'search box hidden'}); continue
        if re.match(r'(?i)^show search$', line):
            o['show_search'] = True; log.append({'line': line, 'applied': True, 'change': 'search box shown'}); continue
        log.append({'line': line, 'applied': False, 'change': 'NOT APPLIED: not a recognised command; kept as a note for the founder.'})
    return o, log

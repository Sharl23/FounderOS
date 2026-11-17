"""QA agent (Phase 3, step 4): static checks of generated files against safety rules and acceptance criteria.

No generated code is ever executed on the server. Checks are textual/structural only.
"""
from __future__ import annotations
import re
from html.parser import HTMLParser

from .website_builder import FILES

MAX_BYTES = 120_000
FORBIDDEN_JS = [
    (r'\beval\s*\(', 'eval'), (r'\bnew\s+Function\s*\(', 'Function constructor'), (r'\bfetch\s*\(', 'network fetch'),
    (r'XMLHttpRequest', 'XMLHttpRequest'), (r'WebSocket', 'WebSocket'), (r'document\.cookie', 'cookie access'),
    (r'localStorage|sessionStorage|indexedDB', 'browser storage'), (r'\.innerHTML\s*=', 'innerHTML assignment'),
    (r'window\.(parent|top|opener)', 'parent-frame access'), (r'import\s*\(', 'dynamic import'), (r'postMessage', 'postMessage'),
]
FORBIDDEN_HTML = [(r'<[^>]*\son[a-z]+\s*=', 'inline event handler'), (r'<[^>]*(src|href|action)\s*=\s*"?https?://', 'external URL'), (r'<iframe|<object|<embed', 'embedded frame/object'),
                  (r'<[^>]*javascript:', 'javascript: URL'), (r'<form[^>]+action\s*=', 'form posting elsewhere'),
                  (r'(?i)\b(testimonial|5 stars|★★★★★|only \d+ left|offer ends|countdown)\b', 'fake social proof or urgency')]
REQUIRED_IDS = {'directory': ['list', 'filters', 'area', 'detail'], 'forecast': ['log', 'forecast', 'history'],
                'practice': ['question', 'choices', 'feedback'], 'planner': ['add', 'list']}
CHECK_EVIDENCE = {'list': r'id="list"', 'search': r'id="search"', 'filters': r'class="feature"', 'detail': r'<dialog id="detail"', 'shortlist': r'id="shortlist"',
                  'form': r'<form id="(log|add)"', 'table': r'<table id="(history|list)"', 'forecast': r'id="forecast"', 'warning': r'(id="warning"|Overdue)',
                  'quiz': r'id="question"', 'feedback': r'id="feedback"', 'score': r'id="retry"', 'done': r"textContent = 'Done'"}


class _Tags(HTMLParser):
    VOID = {'meta', 'link', 'input', 'br', 'img', 'hr', 'source', 'col', 'area', 'base', 'wbr'}

    def __init__(self):
        super().__init__()
        self.stack, self.errors, self.ids = [], [], []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if 'id' in d:
            self.ids.append(d['id'])
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f'unexpected </{tag}>')
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()


def check(spec: dict, files: dict) -> dict:
    items = []

    def add(cid, ok, why):
        items.append({'id': cid, 'ok': bool(ok), 'why': why})
    add('file_set', set(files) == set(FILES), f'Exactly the allowed files: {", ".join(FILES)}.')
    add('size', all(len(v.encode()) <= MAX_BYTES for v in files.values()), f'Each file under {MAX_BYTES // 1000} KB.')
    p = _Tags()
    p.feed(files.get('index.html', ''))
    add('html_well_formed', not p.errors and not [t for t in p.stack if t not in ('html', 'body')], 'HTML tags open and close in order. ' + '; '.join(p.errors[:3]))
    dups = sorted({i for i in p.ids if p.ids.count(i) > 1})
    add('unique_ids', not dups, 'Element ids are unique.' + (f' Duplicates: {dups}' if dups else ''))
    add('required_elements', all(i in p.ids for i in REQUIRED_IDS[spec['archetype']]), 'Core interface elements exist: ' + ', '.join(REQUIRED_IDS[spec['archetype']]))
    html = files.get('index.html', '')
    js = files.get('app.js', '')
    bad_html = [why for rx, why in FORBIDDEN_HTML if re.search(rx, html)]
    add('html_safe', not bad_html, 'No inline handlers, external URLs, frames, fake proof or urgency.' + (f' Found: {bad_html}' if bad_html else ''))
    bad_js = [why for rx, why in FORBIDDEN_JS if re.search(rx, js)]
    add('js_safe', not bad_js, 'No eval, network, storage, innerHTML or parent-frame access.' + (f' Found: {bad_js}' if bad_js else ''))
    add('only_local_assets', 'src="app.js"' in html and 'href="styles.css"' in html and not re.search(r'(src|href)="(?!app\.js|styles\.css)', html), 'Loads only its own app.js and styles.css.')
    add('demo_labelled', 'DEMO DATA' in html and 'DEMO' in js, 'The page and the data say DEMO DATA.')
    add('status_labelled', spec['status_label'].split(':')[0] in html, 'The page states its prototype status.')
    add('js_braces_balanced', js.count('{') == js.count('}') and js.count('(') == js.count(')'), 'Basic JS bracket balance (no execution).')
    stories = []
    for f in spec['features']:
        stories.append({'feature': f['id'], 'title': f['title'], 'ok': bool(re.search(CHECK_EVIDENCE.get(f['check'], '$^'), html + js))})
    add('features_present', all(s['ok'] for s in stories), 'Every specified feature has its interface element.')
    ok = all(i['ok'] for i in items)
    return {'status': 'PASS' if ok else 'FAIL', 'items': items, 'features': stories,
            'method': 'Static inspection only: no generated code is executed on the server.'}

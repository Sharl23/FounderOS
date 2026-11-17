"""Website Builder agent (Phase 3, step 3): spec -> static website files (index.html, styles.css, app.js, README.txt).

Safety by construction:
  * Output is a fixed set of four static files; the file names are constants (no path from input, so no traversal).
  * Every founder/brief string goes into HTML through html.escape and into JS only as JSON data,
    rendered with textContent (never innerHTML), so brief text cannot become markup or code.
  * The JS is our own template code: no network calls, no storage, no eval, no external URLs.
  * Records are generated placeholders labelled DEMO DATA. No real businesses, reviews or bookings.
"""
from __future__ import annotations
import html
import json
import random

FILES = ('index.html', 'styles.css', 'app.js', 'README.txt')


def _js_data(obj) -> str:
    s = json.dumps(obj, ensure_ascii=False, indent=1)
    return s.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


def demo_records(spec: dict, seed: int) -> list[dict]:
    rnd = random.Random(seed)
    k = spec['archetype']
    sing = spec['entity']['singular'].title()
    if k == 'directory':
        out = []
        for i in range(1, 13):
            feats = sorted(rnd.sample(spec['attributes'], k=min(len(spec['attributes']), rnd.randint(1, 3))))
            out.append({'id': i, 'name': f'Demo {sing} {i:02d}', 'area': rnd.choice(spec['areas']), 'features': feats,
                        'hours': rnd.choice(['08:00–22:00', '09:00–18:00', '10:00–00:00', '07:00–20:00']),
                        'note': 'DEMO DATA: placeholder record, not a real place.'})
        return out
    if k == 'forecast':
        items = [f'Demo {spec["entity"]["singular"]} {c}' for c in 'ABC']
        rows = []
        for d in range(1, 11):
            for it in items:
                base = {items[0]: 12, items[1]: 7, items[2]: 20}[it]
                rows.append({'day': f'Day {d:02d}', 'item': it, 'used': max(0, base + rnd.randint(-3, 3))})
        return rows
    if k == 'practice':
        qs = []
        for i in range(1, 7):
            a, b = rnd.randint(2, 12), rnd.randint(2, 12)
            ans = a * b
            choices = sorted({ans, ans + rnd.choice([1, 2, 10]), ans - rnd.choice([1, 2]), ans + a})
            qs.append({'q': f'DEMO question {i}: {a} × {b} = ?', 'choices': choices, 'answer': ans})
        return qs
    return [{'title': f'Demo {spec["entity"]["singular"]} {i}', 'due_in_days': d, 'done': False} for i, d in enumerate([-1, 1, 2, 5, 9], 1)]


CSS = """:root{--accent:%(accent)s;--ink:#16211D;--paper:#F5F7F6;--rule:#D5DDD9;--muted:#5B6B65}
*{box-sizing:border-box}body{margin:0;font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:var(--paper)}
.demo-banner{background:#7A2E0E;color:#fff;padding:8px 16px;font-size:14px;text-align:center}
header.top{padding:28px 20px 12px;max-width:1080px;margin:0 auto}h1{margin:0 0 4px;font-size:28px}p.lead{margin:0;color:var(--muted)}
main{max-width:1080px;margin:0 auto;padding:12px 20px 40px}
.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:12px 0 18px}
input,select,button{font:inherit}input[type=search],input[type=text],input[type=number],input[type=date],select{padding:8px 10px;border:1px solid var(--rule);border-radius:6px;background:#fff}
button{padding:8px 14px;border-radius:6px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer}button.ghost{background:#fff;color:var(--accent)}
.chips label{display:inline-flex;gap:6px;align-items:center;margin-right:10px;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
.card{background:#fff;border:1px solid var(--rule);border-radius:8px;padding:14px;cursor:pointer}.card:focus{outline:3px solid var(--accent)}
.card h3{margin:0 0 4px;font-size:17px}.tag{display:inline-block;font-size:12px;border:1px solid var(--rule);border-radius:99px;padding:1px 8px;margin:2px 4px 0 0}
.muted{color:var(--muted)}.empty{padding:24px;text-align:center;color:var(--muted)}
table{width:100%%;border-collapse:collapse;background:#fff}th,td{border-bottom:1px solid var(--rule);padding:6px 8px;text-align:left}
.warn{background:#FFF4E5;border:1px solid #E8A33D;padding:8px 12px;border-radius:6px}.ok{color:#0E6E62}.bad{color:#9B1C1C}
dialog{border:1px solid var(--rule);border-radius:10px;max-width:440px}footer{max-width:1080px;margin:0 auto;padding:16px 20px;color:var(--muted);font-size:13px}
"""


def _shell(spec: dict, body: str) -> str:
    e = html.escape
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(spec['name'])} (DEMO-ONLY PROTOTYPE)</title><link rel="stylesheet" href="styles.css"></head>
<body>
<div class="demo-banner" id="demo-banner">{e(spec['status_label'])} All records are DEMO DATA.</div>
<header class="top"><h1 id="app-title">{e(spec['name'])}</h1><p class="lead" id="headline">{e(spec['headline'])}</p></header>
<main>
{body}
</main>
<footer>Generated by FounderOS Website Builder from the venture brief. Static prototype: no accounts, no payments, no data leaves this page.</footer>
<script src="app.js"></script>
</body></html>
"""


def _directory(spec):
    e = html.escape
    chips = ''.join(f'<label><input type="checkbox" class="feature" value="{e(a)}"> {e(a)}</label>' for a in spec['attributes'])
    areas = ''.join(f'<option value="{e(a)}">{e(a)}</option>' for a in spec['areas'])
    search = (f'<label for="search" class="muted">Search</label><input type="search" id="search" placeholder="Name or area">' if spec.get('show_search', True) else '')
    body = f"""<section class="controls" aria-label="Search and filters">{search}
<label for="area" class="muted">Area</label><select id="area"><option value="">All areas</option>{areas}</select>
<div class="chips" id="filters" role="group" aria-label="Features">{chips}</div>
<span class="muted" id="count" aria-live="polite"></span></section>
<section class="grid" id="list" aria-label="{e(spec['entity']['plural'].title())}"></section>
<p class="muted" id="shortlist-note">Shortlist (this session only): <span id="shortlist">none</span></p>
<dialog id="detail"><h2 id="d-name"></h2><p id="d-area" class="muted"></p><p id="d-hours"></p><div id="d-features"></div><p class="muted" id="d-note"></p>
<p><button id="d-fav" class="ghost">Add to shortlist</button> <button id="d-close">Close</button></p></dialog>"""
    js = """'use strict';
const SPEC = %(spec)s;
const DATA = %(data)s;
const $ = (id) => document.getElementById(id);
const fav = new Set();
function matches(r) {
  const q = ($('search') ? $('search').value : '').trim().toLowerCase();
  const area = $('area').value;
  const need = [...document.querySelectorAll('.feature:checked')].map((x) => x.value);
  if (q && !(r.name.toLowerCase().includes(q) || r.area.toLowerCase().includes(q))) return false;
  if (area && r.area !== area) return false;
  return need.every((f) => r.features.includes(f));
}
function render() {
  const list = $('list'); list.textContent = '';
  const rows = DATA.filter(matches);
  $('count').textContent = rows.length + ' of ' + DATA.length + ' demo ' + SPEC.entity.plural;
  if (!rows.length) { const p = document.createElement('p'); p.className = 'empty'; p.textContent = 'No demo ' + SPEC.entity.plural + ' match these filters.'; list.appendChild(p); return; }
  for (const r of rows) {
    const c = document.createElement('article'); c.className = 'card'; c.tabIndex = 0; c.dataset.id = r.id;
    const h = document.createElement('h3'); h.textContent = r.name; c.appendChild(h);
    const a = document.createElement('div'); a.className = 'muted'; a.textContent = r.area + ' · ' + r.hours; c.appendChild(a);
    for (const f of r.features) { const t = document.createElement('span'); t.className = 'tag'; t.textContent = f; c.appendChild(t); }
    c.addEventListener('click', () => open(r)); c.addEventListener('keydown', (e) => { if (e.key === 'Enter') open(r); });
    list.appendChild(c);
  }
}
let current = null;
function open(r) {
  current = r; $('d-name').textContent = r.name; $('d-area').textContent = r.area; $('d-hours').textContent = 'Hours: ' + r.hours;
  $('d-features').textContent = 'Features: ' + r.features.join(', '); $('d-note').textContent = r.note;
  $('d-fav').textContent = fav.has(r.id) ? 'Remove from shortlist' : 'Add to shortlist'; $('detail').showModal();
}
$('d-close').addEventListener('click', () => $('detail').close());
$('d-fav').addEventListener('click', () => { if (fav.has(current.id)) fav.delete(current.id); else fav.add(current.id);
  $('shortlist').textContent = DATA.filter((r) => fav.has(r.id)).map((r) => r.name).join(', ') || 'none'; $('detail').close(); });
if ($('search')) $('search').addEventListener('input', render);
$('area').addEventListener('change', render);
document.querySelectorAll('.feature').forEach((x) => x.addEventListener('change', render));
render();
"""
    return body, js


def _forecast(spec):
    e = html.escape
    sing = e(spec['entity']['singular'])
    body = f"""<section aria-labelledby="log-h"><h2 id="log-h">Log today's usage</h2>
<form id="log" class="controls"><label for="item">{sing.title()}</label><select id="item"></select>
<label for="used">Used</label><input type="number" id="used" min="0" step="1" required>
<label for="planned">Planned order for tomorrow</label><input type="number" id="planned" min="0" step="1">
<button type="submit">Add entry</button></form><p id="form-msg" class="muted" aria-live="polite"></p></section>
<section aria-labelledby="fc-h"><h2 id="fc-h">Suggested quantity for tomorrow</h2><p class="muted">Method: average of the last 7 entries for each {sing} (DEMO DATA history). A planning aid, not a guarantee.</p>
<table id="forecast"><thead><tr><th>{sing.title()}</th><th>Last 7 avg</th><th>Suggested</th></tr></thead><tbody></tbody></table><p id="warning" class="warn" hidden></p></section>
<section aria-labelledby="hist-h"><h2 id="hist-h">History</h2><table id="history"><thead><tr><th>Day</th><th>{sing.title()}</th><th>Used</th></tr></thead><tbody></tbody></table></section>"""
    js = """'use strict';
const SPEC = %(spec)s;
const DATA = %(data)s;
const $ = (id) => document.getElementById(id);
const items = [...new Set(DATA.map((r) => r.item))];
for (const it of items) { const o = document.createElement('option'); o.value = it; o.textContent = it; $('item').appendChild(o); }
function avg7(item) { const rows = DATA.filter((r) => r.item === item).slice(-7); return rows.reduce((s, r) => s + r.used, 0) / Math.max(rows.length, 1); }
function render() {
  const fb = $('forecast').querySelector('tbody'); fb.textContent = '';
  for (const it of items) { const tr = document.createElement('tr'); const a = avg7(it);
    for (const v of [it, a.toFixed(1), String(Math.ceil(a))]) { const td = document.createElement('td'); td.textContent = v; tr.appendChild(td); } fb.appendChild(tr); }
  const hb = $('history').querySelector('tbody'); hb.textContent = '';
  for (const r of DATA.slice(-15).reverse()) { const tr = document.createElement('tr');
    for (const v of [r.day, r.item, String(r.used)]) { const td = document.createElement('td'); td.textContent = v; tr.appendChild(td); } hb.appendChild(tr); }
}
$('log').addEventListener('submit', (e) => { e.preventDefault();
  const used = Number($('used').value); if (!Number.isFinite(used) || used < 0) { $('form-msg').textContent = 'Enter a number of 0 or more.'; return; }
  DATA.push({ day: 'Today', item: $('item').value, used: used });
  const planned = Number($('planned').value); const f = avg7($('item').value);
  const w = $('warning');
  if (planned && planned > f * 1.3) { w.hidden = false; w.textContent = 'Planned ' + planned + ' is more than 130% of the usual ' + f.toFixed(1) + '. Check before ordering.'; } else { w.hidden = true; }
  $('form-msg').textContent = 'Entry added (kept in this page only).'; render(); });
render();
"""
    return body, js


def _practice(spec):
    body = """<section aria-live="polite"><p id="progress" class="muted"></p><h2 id="question"></h2><div id="choices" class="controls"></div><p id="feedback"></p>
<p><button id="next" hidden>Next</button> <button id="retry" class="ghost" hidden>Retry</button></p></section>"""
    js = """'use strict';
const SPEC = %(spec)s;
const DATA = %(data)s;
const $ = (id) => document.getElementById(id);
let i = 0, score = 0;
function show() {
  $('feedback').textContent = ''; $('next').hidden = true; $('choices').textContent = '';
  if (i >= DATA.length) { $('question').textContent = 'Score: ' + score + ' / ' + DATA.length; $('progress').textContent = 'Finished'; $('retry').hidden = false; return; }
  const q = DATA[i]; $('progress').textContent = 'Question ' + (i + 1) + ' of ' + DATA.length; $('question').textContent = q.q;
  for (const c of q.choices) { const b = document.createElement('button'); b.className = 'ghost choice'; b.textContent = String(c);
    b.addEventListener('click', () => { const right = c === q.answer; if (right) score++;
      $('feedback').textContent = right ? 'Correct.' : 'Not quite: the answer is ' + q.answer + '.'; $('feedback').className = right ? 'ok' : 'bad';
      document.querySelectorAll('.choice').forEach((x) => { x.disabled = true; }); $('next').hidden = false; });
    $('choices').appendChild(b); }
}
$('next').addEventListener('click', () => { i++; show(); });
$('retry').addEventListener('click', () => { i = 0; score = 0; $('retry').hidden = true; show(); });
show();
"""
    return body, js


def _planner(spec):
    e = html.escape
    body = f"""<form id="add" class="controls"><label for="title">{e(spec['entity']['singular'].title())}</label><input type="text" id="title" maxlength="120" required>
<label for="due">Due in (days)</label><input type="number" id="due" value="3" min="-30" max="365"><button type="submit">Add</button></form><p id="form-msg" class="muted" aria-live="polite"></p>
<p class="muted">Done: <span id="done-count">0</span></p><table id="list"><thead><tr><th>{e(spec['entity']['singular'].title())}</th><th>Due</th><th>Status</th><th></th></tr></thead><tbody></tbody></table>"""
    js = """'use strict';
const SPEC = %(spec)s;
const DATA = %(data)s;
const $ = (id) => document.getElementById(id);
function render() {
  const tb = $('list').querySelector('tbody'); tb.textContent = '';
  const rows = DATA.filter((r) => !r.done).sort((a, b) => a.due_in_days - b.due_in_days);
  for (const r of rows) { const tr = document.createElement('tr');
    const st = r.due_in_days < 0 ? 'Overdue' : r.due_in_days <= 2 ? 'Due soon' : 'Planned';
    for (const v of [r.title, r.due_in_days + ' day(s)', st]) { const td = document.createElement('td'); td.textContent = v; tr.appendChild(td); }
    if (st !== 'Planned') tr.className = st === 'Overdue' ? 'bad' : 'warn';
    const td = document.createElement('td'); const b = document.createElement('button'); b.className = 'ghost'; b.textContent = 'Done';
    b.addEventListener('click', () => { r.done = true; render(); }); td.appendChild(b); tr.appendChild(td); tb.appendChild(tr); }
  $('done-count').textContent = String(DATA.filter((r) => r.done).length);
}
$('add').addEventListener('submit', (e) => { e.preventDefault(); const t = $('title').value.trim();
  if (!t) { $('form-msg').textContent = 'Give it a title.'; return; }
  DATA.push({ title: t, due_in_days: Number($('due').value) || 0, done: false }); $('title').value = ''; $('form-msg').textContent = 'Added (kept in this page only).'; render(); });
render();
"""
    return body, js


BUILDERS = {'directory': _directory, 'forecast': _forecast, 'practice': _practice, 'planner': _planner}


def build(spec: dict, seed: int) -> dict:
    body, js = BUILDERS[spec['archetype']](spec)
    public_spec = {k: spec[k] for k in ('name', 'archetype', 'entity', 'attributes', 'areas')}
    files = {
        'index.html': _shell(spec, body),
        'styles.css': CSS % {'accent': spec['accent'] if _hex(spec['accent']) else '#0E6E62'},
        'app.js': '/* DEMO DATA: every record below is a generated placeholder, not a real business, person, review or booking. */\n' + js.replace('%(spec)s', _js_data(public_spec)).replace('%(data)s', _js_data(demo_records(spec, seed))),
        'README.txt': (f"{spec['name']}: {spec['status_label']}\n\nStatic prototype generated by FounderOS (Website Builder agent).\n"
                       f"Open index.html in a browser. No server, no accounts, no payments, no network calls.\n"
                       f"All records are DEMO DATA placeholders, not real {spec['entity']['plural']}.\n\n"
                       f"User stories:\n" + '\n'.join(f"- {s['id']}: As {s['as_a']}, I want {s['i_want']} so that {s['so_that']}." for s in spec['user_stories']) + '\n'),
    }
    return files


def _hex(v):
    import re
    return bool(re.fullmatch(r'#[0-9A-Fa-f]{6}', v or ''))

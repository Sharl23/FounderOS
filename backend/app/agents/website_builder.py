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
    if k == 'tracker':
        clients = [f'Demo Client {c}' for c in 'ABC']
        projects = []
        for i, (c, due) in enumerate([(0, -2), (0, 6), (1, 2), (2, 12)], 1):
            tasks = [{'title': f'Demo task {i}.{j}', 'done': rnd.random() < 0.4} for j in range(1, rnd.randint(3, 5))]
            projects.append({'id': i, 'client': clients[c], 'title': f'Demo project {i}', 'due_in_days': due, 'status': spec['attributes'][min(i - 1, 3)], 'tasks': tasks})
        return {'clients': clients, 'projects': projects}
    if k == 'booking':
        days = ['Day 1', 'Day 2', 'Day 3', 'Day 4', 'Day 5']
        times = ['10:00', '11:00', '12:00', '14:00', '15:00', '16:00']
        slots = [{'id': f'{d}-{t}', 'day': d, 'time': t} for d in days for t in times]
        taken = rnd.sample(slots, k=5)
        bookings = [{'slot': x['id'], 'ref': f'DEMO-{i:02d}', 'service': rnd.choice(spec['attributes'])} for i, x in enumerate(taken, 1)]
        return {'slots': slots, 'bookings': bookings}
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
    """A functional, local-only study planner with a seven-day workload schedule."""
    e = html.escape
    body = f"""<section class="warn" aria-label="Prototype limitations">DEMO-ONLY: sample tasks are fictional. Your edits stay in this browser tab; this is not a validated product.</section>
<form id="add" class="controls"><label for="title">{e(spec['entity']['singular'].title())}</label><input type="text" id="title" maxlength="120" required>
<label for="due">Due in (days)</label><input type="number" id="due" value="3" min="-30" max="365" required>
<label for="hours">Estimated hours</label><input type="number" id="hours" value="2" min="0.5" max="100" step="0.5" required>
<button type="submit">Add task</button></form>
<p id="form-msg" class="muted" aria-live="polite"></p>
<section aria-label="Weekly study plan"><h2>Personalized 7-day study plan</h2>
<div class="controls"><label for="daily">Study hours available per day</label><input type="number" id="daily" value="2" min="0.5" max="16" step="0.5">
<button type="button" id="generate">Generate plan</button></div>
<p class="muted">Tasks are prioritized by deadline. The scheduler fills each day's available hours, and flags work that cannot fit before a deadline. This is a deterministic demo scheduler, not an AI-generated timetable.</p>
<div id="schedule" aria-live="polite"></div></section>
<h2>Tasks</h2><p class="muted">Completed: <span id="done-count">0</span></p>
<table id="list"><thead><tr><th>Task</th><th>Due</th><th>Hours left</th><th>Status</th><th>Action</th></tr></thead><tbody></tbody></table>"""
    js = """'use strict';
const SPEC = %(spec)s;
const DATA = %(data)s;
const $ = (id) => document.getElementById(id);
DATA.forEach(r => { r.hours = 2; }); // DEMO DATA: fictional estimates
function safeNumber(value, fallback) { const n = Number(value); return Number.isFinite(n) ? n : fallback; }
function render() {
  const tb = $('list').querySelector('tbody'); tb.textContent = '';
  const rows = DATA.filter(r => !r.done).sort((a,b) => a.due_in_days - b.due_in_days);
  for (const r of rows) {
    const tr = document.createElement('tr');
    const st = r.due_in_days < 0 ? 'Overdue' : r.due_in_days <= 2 ? 'Due soon' : 'Planned';
    for (const v of [r.title, r.due_in_days + ' day(s)', r.hours + ' h', st]) {
      const td = document.createElement('td'); td.textContent = String(v); tr.appendChild(td);
    }
    if (st !== 'Planned') tr.className = st === 'Overdue' ? 'bad' : 'warn';
    const td = document.createElement('td'); const b = document.createElement('button');
    b.className = 'ghost'; b.textContent = 'Done';
    b.addEventListener('click', () => { r.done = true; render(); generatePlan(); });
    td.appendChild(b); tr.appendChild(td); tb.appendChild(tr);
  }
  $('done-count').textContent = String(DATA.filter(r => r.done).length);
}
function scheduleTasks(tasks, dailyHours) {
  const capacity = Array(7).fill(dailyHours);
  const days = Array.from({length:7}, () => []);
  const warnings = [];
  const ordered = tasks.filter(r => !r.done).map(r => ({
    title: String(r.title), due: safeNumber(r.due_in_days, 0), remaining: Math.max(0, safeNumber(r.hours, 2))
  })).sort((a,b) => a.due - b.due);
  for (const task of ordered) {
    if (task.due < 0) { warnings.push(task.title + ': overdue; needs immediate review'); continue; }
    const last = Math.min(6, Math.floor(task.due));
    for (let d=0; d<=last && task.remaining > 0.001; d++) {
      const h = Math.min(capacity[d], task.remaining);
      if (h > 0.001) { days[d].push({title:task.title, hours:h}); capacity[d]-=h; task.remaining-=h; }
    }
    if (task.remaining > 0.001) warnings.push(task.title + ': ' + task.remaining.toFixed(1) + ' h cannot fit before its deadline');
  }
  return {days, warnings};
}
function generatePlan() {
  const daily = safeNumber($('daily').value, 0);
  const root = $('schedule'); root.textContent = '';
  if (daily < 0.5 || daily > 16) { root.textContent = 'Choose between 0.5 and 16 study hours per day.'; return; }
  const result = scheduleTasks(DATA, daily);
  const table = document.createElement('table'); const head = document.createElement('thead');
  const hr = document.createElement('tr');
  for (const name of ['Day', 'Planned work', 'Total hours']) { const th=document.createElement('th'); th.textContent=name; hr.appendChild(th); }
  head.appendChild(hr); table.appendChild(head);
  const tbody=document.createElement('tbody');
  result.days.forEach((entries, i) => {
    const tr=document.createElement('tr');
    const values=['Day '+(i+1), entries.length ? entries.map(x=>x.title+' ('+x.hours.toFixed(1)+' h)').join('; ') : 'Free / catch up', entries.reduce((s,x)=>s+x.hours,0).toFixed(1)+' h'];
    values.forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.appendChild(td);});tbody.appendChild(tr);
  });
  table.appendChild(tbody);root.appendChild(table);
  result.warnings.forEach(w=>{const p=document.createElement('p');p.className='warn';p.textContent='Attention: '+w;root.appendChild(p);});
}
$('add').addEventListener('submit', e => { e.preventDefault();
  const t=$('title').value.trim(); const due=Number($('due').value); const hours=Number($('hours').value);
  if (!t || !Number.isInteger(due) || due < -30 || due > 365 || !Number.isFinite(hours) || hours < 0.5 || hours > 100) {
    $('form-msg').textContent='Enter a task, a valid deadline and estimated hours.'; return;
  }
  DATA.push({title:t,due_in_days:due,hours,done:false});$('title').value='';
  $('form-msg').textContent='Task added in this browser tab (not saved to a server).';render();generatePlan();
});
$('generate').addEventListener('click',generatePlan);
render();generatePlan();
"""
    return body, js


def _tracker(spec):
    """Freelancer-style client and project tracker: clients -> projects -> tasks, with a progress view."""
    body = """<section class="warn" aria-label="Prototype limitations">DEMO-ONLY: clients and projects are fictional. Edits stay in this browser tab; nothing is saved, sent or invoiced.</section>
<div class="grid">
<form id="add-client" class="card"><h3>Add client</h3><label for="client-name">Client name</label><input type="text" id="client-name" maxlength="80" required>
<button type="submit">Add client</button></form>
<form id="add-project" class="card"><h3>Add project</h3><label for="project-client">Client</label><select id="project-client" required></select>
<label for="project-title">Project title</label><input type="text" id="project-title" maxlength="100" required>
<label for="project-due">Delivery in (days)</label><input type="number" id="project-due" value="7" min="-60" max="365" required>
<button type="submit">Add project</button></form>
<form id="add-task" class="card"><h3>Add task</h3><label for="task-project">Project</label><select id="task-project" required></select>
<label for="task-title">Task</label><input type="text" id="task-title" maxlength="100" required>
<button type="submit">Add task</button></form>
</div>
<p id="form-msg" class="muted" aria-live="polite"></p>
<h2>Projects</h2>
<table id="projects"><thead><tr><th>Project</th><th>Client</th><th>Delivery</th><th>Progress</th><th>Flag</th><th>Open tasks</th></tr></thead><tbody></tbody></table>
<h2>Progress by client</h2><div id="progress" aria-live="polite"></div>"""
    js = """'use strict';
const SPEC = %(spec)s;
const DATA = %(data)s;
const $ = (id) => document.getElementById(id);
function pct(p) { return p.tasks.length ? Math.round(100 * p.tasks.filter(t => t.done).length / p.tasks.length) : 0; }
function flag(p) {
  const open = p.tasks.filter(t => !t.done).length;
  if (p.tasks.length && open === 0) return 'Delivered';
  if (p.due_in_days < 0) return 'Late';
  if (p.due_in_days <= 3) return 'At risk';
  return 'On track';
}
function cell(tr, text, cls) { const td = document.createElement('td'); td.textContent = String(text); if (cls) td.className = cls; tr.appendChild(td); return td; }
function fillSelect(sel, values) {
  const keep = sel.value; sel.textContent = '';
  for (const [v, label] of values) { const o = document.createElement('option'); o.value = String(v); o.textContent = label; sel.appendChild(o); }
  if ([...sel.options].some(o => o.value === keep)) sel.value = keep;
}
function render() {
  fillSelect($('project-client'), DATA.clients.map(c => [c, c]));
  fillSelect($('task-project'), DATA.projects.map(p => [p.id, p.title + ' (' + p.client + ')']));
  const tb = $('projects').querySelector('tbody'); tb.textContent = '';
  for (const p of [...DATA.projects].sort((a, b) => a.due_in_days - b.due_in_days)) {
    const tr = document.createElement('tr'); const f = flag(p);
    cell(tr, p.title); cell(tr, p.client); cell(tr, p.due_in_days < 0 ? Math.abs(p.due_in_days) + ' day(s) ago' : 'in ' + p.due_in_days + ' day(s)');
    const prog = cell(tr, ''); const bar = document.createElement('progress'); bar.max = 100; bar.value = pct(p);
    bar.setAttribute('aria-label', p.title + ' progress'); prog.appendChild(bar); prog.appendChild(document.createTextNode(' ' + pct(p) + '%'));
    cell(tr, f, f === 'Late' ? 'bad' : f === 'At risk' ? 'warn' : f === 'Delivered' ? 'ok' : '');
    const td = cell(tr, '');
    for (const t of p.tasks.filter(t => !t.done)) {
      const b = document.createElement('button'); b.className = 'ghost'; b.type = 'button'; b.textContent = 'Done: ' + t.title;
      b.addEventListener('click', () => { t.done = true; render(); }); td.appendChild(b);
    }
    if (!p.tasks.some(t => !t.done)) td.textContent = p.tasks.length ? 'none' : 'no tasks yet';
    tb.appendChild(tr);
  }
  const root = $('progress'); root.textContent = '';
  for (const c of DATA.clients) {
    const ps = DATA.projects.filter(p => p.client === c);
    const open = ps.reduce((n, p) => n + p.tasks.filter(t => !t.done).length, 0);
    const next = ps.filter(p => flag(p) !== 'Delivered').sort((a, b) => a.due_in_days - b.due_in_days)[0];
    const late = ps.filter(p => flag(p) === 'Late').length;
    const line = document.createElement('p'); line.className = late ? 'bad' : '';
    line.textContent = c + ': ' + ps.length + ' project(s), ' + open + ' open task(s), ' + (late ? late + ' late, ' : '') + 'next delivery: ' + (next ? next.title + ' (' + next.due_in_days + ' day(s))' : 'none');
    root.appendChild(line);
  }
}
function msg(t) { $('form-msg').textContent = t; }
$('add-client').addEventListener('submit', e => { e.preventDefault();
  const n = $('client-name').value.trim();
  if (!n) return msg('Enter a client name.');
  if (DATA.clients.some(c => c.toLowerCase() === n.toLowerCase())) return msg('That client already exists.');
  DATA.clients.push(n); $('client-name').value = ''; msg('Client added in this browser tab.'); render();
});
$('add-project').addEventListener('submit', e => { e.preventDefault();
  const c = $('project-client').value, t = $('project-title').value.trim(), d = Number($('project-due').value);
  if (!c || !t || !Number.isInteger(d) || d < -60 || d > 365) return msg('A project needs a client, a title and a whole number of days.');
  DATA.projects.push({id: Math.max(0, ...DATA.projects.map(p => p.id)) + 1, client: c, title: t, due_in_days: d, tasks: []});
  $('project-title').value = ''; msg('Project added. Add its tasks next.'); render();
});
$('add-task').addEventListener('submit', e => { e.preventDefault();
  const p = DATA.projects.find(x => String(x.id) === $('task-project').value), t = $('task-title').value.trim();
  if (!p || !t) return msg('Choose a project and enter a task.');
  p.tasks.push({title: t, done: false}); $('task-title').value = ''; msg('Task added to ' + p.title + '.'); render();
});
render();
"""
    return body, js


def _booking(spec):
    """Appointment booking: free/taken slots, validated booking form, confirmation, cancellation."""
    e = html.escape
    options = ''.join(f'<option value="{e(a)}">{e(a)}</option>' for a in spec['attributes'])
    body = f"""<section class="warn" aria-label="Prototype limitations">DEMO-ONLY: slots and bookings are fictional. No message, reminder or payment is sent; nothing leaves this browser tab.</section>
<h2>Free slots (next 5 days)</h2><div id="slots" class="grid" aria-live="polite"></div>
<h2>Book an appointment</h2>
<form id="book" class="controls"><label for="ref">Client reference</label><input type="text" id="ref" maxlength="40" pattern="[A-Za-z0-9 _\\-]+" required placeholder="e.g. initials">
<label for="service">Service</label><select id="service" required>{options}</select>
<label for="slot">Slot</label><select id="slot" required></select>
<button type="submit">Book</button></form>
<p id="form-msg" class="muted" aria-live="polite"></p>
<section id="confirmation" class="card" hidden aria-live="polite"></section>
<h2>Bookings</h2><table id="bookings"><thead><tr><th>Slot</th><th>Client reference</th><th>Service</th><th>Action</th></tr></thead><tbody></tbody></table>"""
    js = """'use strict';
const SPEC = %(spec)s;
const DATA = %(data)s;
const $ = (id) => document.getElementById(id);
const taken = () => new Set(DATA.bookings.map(b => b.slot));
const label = (id) => { const s = DATA.slots.find(x => x.id === id); return s ? s.day + ' ' + s.time : id; };
function render() {
  const t = taken();
  const grid = $('slots'); grid.textContent = '';
  for (const day of [...new Set(DATA.slots.map(s => s.day))]) {
    const card = document.createElement('div'); card.className = 'card';
    const h = document.createElement('h3'); h.textContent = day; card.appendChild(h);
    for (const s of DATA.slots.filter(x => x.day === day)) {
      const tag = document.createElement('span'); tag.className = 'tag ' + (t.has(s.id) ? 'bad' : 'ok');
      tag.textContent = s.time + (t.has(s.id) ? ' taken' : ' free'); card.appendChild(tag);
    }
    grid.appendChild(card);
  }
  const sel = $('slot'); const keep = sel.value; sel.textContent = '';
  for (const s of DATA.slots.filter(x => !t.has(x.id))) { const o = document.createElement('option'); o.value = s.id; o.textContent = s.day + ' ' + s.time; sel.appendChild(o); }
  if ([...sel.options].some(o => o.value === keep)) sel.value = keep;
  const tb = $('bookings').querySelector('tbody'); tb.textContent = '';
  for (const b of [...DATA.bookings].sort((x, y) => DATA.slots.findIndex(s => s.id === x.slot) - DATA.slots.findIndex(s => s.id === y.slot))) {
    const tr = document.createElement('tr');
    for (const v of [label(b.slot), b.ref, b.service]) { const td = document.createElement('td'); td.textContent = v; tr.appendChild(td); }
    const td = document.createElement('td'); const btn = document.createElement('button'); btn.className = 'ghost'; btn.type = 'button';
    btn.textContent = 'Cancel';
    btn.addEventListener('click', () => { DATA.bookings = DATA.bookings.filter(x => x !== b); $('form-msg').textContent = 'Booking cancelled; ' + label(b.slot) + ' is free again.'; render(); });
    td.appendChild(btn); tr.appendChild(td); tb.appendChild(tr);
  }
}
$('book').addEventListener('submit', e => { e.preventDefault();
  const ref = $('ref').value.trim(), service = $('service').value, slot = $('slot').value;
  if (!/^[A-Za-z0-9 _-]{1,40}$/.test(ref)) { $('form-msg').textContent = 'Enter a short client reference (letters, digits, spaces).'; return; }
  if (!SPEC.attributes.includes(service)) { $('form-msg').textContent = 'Choose a service.'; return; }
  if (!DATA.slots.some(s => s.id === slot)) { $('form-msg').textContent = 'Choose a slot.'; return; }
  if (taken().has(slot)) { $('form-msg').textContent = 'That slot was just taken. Choose another.'; render(); return; }
  DATA.bookings.push({slot, ref, service});
  const c = $('confirmation'); c.hidden = false; c.textContent = '';
  const h = document.createElement('h3'); h.textContent = 'Booking recorded (DEMO)'; c.appendChild(h);
  const p = document.createElement('p'); p.textContent = ref + ': ' + service + ' on ' + label(slot) + '. No confirmation message was sent; this prototype cannot send anything.'; c.appendChild(p);
  $('ref').value = ''; $('form-msg').textContent = ''; render();
});
render();
"""
    return body, js


BUILDERS = {'directory': _directory, 'forecast': _forecast, 'practice': _practice, 'planner': _planner, 'tracker': _tracker, 'booking': _booking}


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

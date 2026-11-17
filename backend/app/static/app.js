/* FounderOS v0.8 client. Every action below calls the real backend; nothing is simulated in the browser.
   Routes: /projects, /projects/:id/{brief,safety,discovery,research,experiments,decision,audit}, /roadmap, /help */
(() => {
  'use strict';
  const main = document.getElementById('main');
  const live = document.getElementById('live');
  const dlg = document.getElementById('dlg');

  // ------------------------------------------------------------------ utilities
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const short = (s, n = 8) => (s ? String(s).slice(0, n) : '—');
  const when = (s) => { if (!s) return '—'; const d = new Date(s); return isNaN(d) ? esc(s) : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }); };
  const announce = (t) => { live.textContent = ''; setTimeout(() => { live.textContent = t; }, 30); };
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage may be unavailable */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } },
  };
  // Project capability tokens live only in this browser. Migrate the v0.2–v0.4 single-session key.
  const projects = () => {
    const p = store.get('founderos_projects', {});
    const legacy = store.get('founderos_session', null);
    if (legacy && legacy.project_id && !p[legacy.project_id]) { p[legacy.project_id] = { token: legacy.access_token, name: 'Earlier project', created: null }; store.set('founderos_projects', p); }
    return p;
  };
  const tokenFor = (pid) => (projects()[pid] || {}).token;

  const LABEL = {
    ALLOW_DISCOVERY: 'Allowed for research', REVIEW_REQUIRED: 'Needs your review', BLOCK: 'Hard stop', HARD_STOP: 'Hard stop', CLEAR: 'No issue found',
    UNKNOWN_SOURCE: 'Source not checked', NOT_APPLICABLE: 'Not applicable', GO_ON: 'Go on to validation research', REPEAT: 'Repeat with more evidence',
    PIVOT: 'Pivot', STOP: 'Stop', NEEDS_EVIDENCE: 'Needs evidence', CONTINUE_TESTING: 'Continue testing', STOP_DO_NOT_LAUNCH: 'Stop: do not launch',
    BLOCK_DO_NOT_LAUNCH: 'Blocked: do not launch', PASS: 'Pass', FAIL: 'Fail', SCORED: 'Scored', UNKNOWN: 'Unknown', AWAITING_JUDGE: 'Awaiting judge',
    RANKED: 'Ranked', RANKED_WITH_TIE: 'Ranked, with a tie', APPLIED: 'Applied', REPORTED: 'Reported', INSUFFICIENT: 'Insufficient',
    NOT_DESIGNED: 'Not designed', NOT_SET: 'Not set', DRAFT_NOT_LOCKED: 'Draft, not locked', LOCKED: 'Locked', NO_RESULT: 'No result yet',
    HIT: 'Hit', NEAR_MISS: 'Near miss', CLEAR_MISS: 'Clear miss', TOO_LITTLE_DATA: 'Too little data', PENDING_APPROVAL: 'Waiting for your decision',
    APPROVED: 'Approved (research only)', REVISE_REQUESTED: 'Revision requested', PIVOT_REQUESTED: 'Pivot requested', STOPPED: 'Stopped', INVALIDATED: 'Out of date',
    DRAFT: 'Draft', SUPERSEDED: 'Superseded', ARCHIVED_PIVOT: 'Archived by pivot', CANDIDATE_METADATA: 'Candidate (metadata)', FETCHED: 'Page inspected',
    FETCH_FAILED: 'Could not fetch', EVIDENCE_ADDED: 'In the ledger', REJECTED: 'Rejected', OK: 'OK', NO_RESULTS: 'No results', OFFLINE: 'Offline',
    RATE_LIMITED: 'Rate limited', ACCESS_DENIED: 'Access denied', PROVIDER_ERROR: 'Provider error', NOT_AVAILABLE: 'Not available',
    DISCOVERY_NOT_AVAILABLE: 'Not searched automatically', INVALID_QUERY: 'Invalid query', EXCERPT_MATCHED: 'Excerpt verified', NOT_MATCHED: 'Excerpt not found',
    NOT_CHECKED: 'Not checked', METADATA_ONLY: 'Metadata only', STRUCTURED_DATUM: 'Official datum', URL_ACCESSIBLE: 'Page reached', UNVERIFIED: 'Unverified',
    CONTEXT_ONLY: 'Context only', CONTEXT_WEAK: 'Context, weak', DIRECT_STATEMENT: 'Customer statement', DIRECT_BEHAVIOR: 'Customer behaviour',
    LOCKED_RESULT: 'Locked-test result', EXCLUDED: 'Excluded', READY: 'Model ready', MODEL_OOM_CPU: 'it ran out of RAM', MODEL_OOM_GPU: 'it ran out of GPU memory',
    STATED_IN_TEXT: 'In your words, please confirm', FORM_FIELD: 'Typed by you', FOUNDER_CONFIRMED: 'Confirmed by you', MODEL_SUGGESTED_UNCONFIRMED: 'Model suggestion',
    NOT_STATED: 'Not stated', PARSER_FAILED: 'Parser failed', WEAK: 'Weak', STRONG: 'Strong', ACCEPTED_RELEVANT: 'Accepted, relevant', PAGE_FETCHED: 'Page fetched',
    FOUNDER_SUPPLIED_UNVERIFIED: 'Pasted by you, not verified', FOUNDER_SUPPLIED: 'Pasted by you', SIMULATED_NOT_COUNTED: 'Simulated, not counted', SIMULATED_RESULT: 'Simulated, not counted',
    TIMEOUT: 'Timed out', TLS_VERIFY_FAILED: 'Certificate check failed', NOT_SCREENED: 'Not screened', NOT_GIVEN_OPTIONAL: 'None given (optional here)', PROVIDED: 'Given',
    MISSING_BUT_REQUIRED: 'Missing (required)', HYPOTHESIS: 'Hypothesis',
    OLLAMA_UNREACHABLE: 'Ollama is not reachable', MODEL_NOT_FOUND: 'the model is not installed', MODEL_TIMEOUT: 'it timed out', MODEL_BAD_OUTPUT: 'its answer was malformed twice', MODEL_ERROR: 'Ollama returned an error', SUPPORTED: 'Supported', REFUTED: 'Refuted', MIXED: 'Mixed',
  };
  const TONE = {
    clear: ['STRONG', 'ACCEPTED_RELEVANT', 'FORM_FIELD', 'FOUNDER_CONFIRMED', 'PROVIDED', 'SUPPORTED', 'ALLOW_DISCOVERY', 'CLEAR', 'PASS', 'SCORED', 'GO_ON', 'CONTINUE_TESTING', 'HIT', 'LOCKED', 'APPROVED', 'EXCERPT_MATCHED', 'URL_ACCESSIBLE', 'OK', 'READY', 'EVIDENCE_ADDED', 'RANKED', 'STRUCTURED_DATUM', 'DIRECT_BEHAVIOR', 'LOCKED_RESULT', 'APPLIED', 'REPORTED'],
    hold: ['WEAK', 'STATED_IN_TEXT', 'MODEL_SUGGESTED_UNCONFIRMED', 'FOUNDER_SUPPLIED_UNVERIFIED', 'FOUNDER_SUPPLIED', 'TIMEOUT', 'MIXED', 'REVIEW_REQUIRED', 'REPEAT', 'NEEDS_EVIDENCE', 'NEAR_MISS', 'AWAITING_JUDGE', 'PENDING_APPROVAL', 'DRAFT', 'DRAFT_NOT_LOCKED', 'PIVOT', 'RANKED_WITH_TIE', 'CONTEXT_WEAK', 'METADATA_ONLY', 'RATE_LIMITED', 'REVISE_REQUESTED', 'PIVOT_REQUESTED', 'INSUFFICIENT', 'TOO_LITTLE_DATA', 'DIRECT_STATEMENT'],
    stop: ['PARSER_FAILED', 'TLS_VERIFY_FAILED', 'SIMULATED_NOT_COUNTED', 'SIMULATED_RESULT', 'MISSING_BUT_REQUIRED', 'REFUTED', 'BLOCK', 'HARD_STOP', 'STOP', 'STOP_DO_NOT_LAUNCH', 'BLOCK_DO_NOT_LAUNCH', 'FAIL', 'CLEAR_MISS', 'FETCH_FAILED', 'REJECTED', 'STOPPED', 'NOT_MATCHED', 'OFFLINE', 'ACCESS_DENIED', 'PROVIDER_ERROR', 'EXCLUDED'],
    info: ['NOT_GIVEN_OPTIONAL', 'PAGE_FETCHED', 'HYPOTHESIS', 'CANDIDATE_METADATA', 'FETCHED', 'CONTEXT_ONLY', 'SUPERSEDED', 'ARCHIVED_PIVOT', 'INVALIDATED'],
  };
  const tone = (code) => Object.keys(TONE).find((t) => TONE[t].includes(code)) || 'unknown';
  const label = (code) => LABEL[code] || String(code || '—').replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
  const chip = (code, title) => `<span class="chip ${tone(code)}" title="${esc(title || code)}">${esc(label(code))}</span>`;
  const RULE_NAME = {
    illegal_in_target_market: 'Legal in the target market', regulated_or_sensitive_area: 'Sensitive or regulated area', physical_goods_exclusion: 'Digital product, not physical goods',
    financial_crypto_exclusion: 'No financial or crypto functions', health_legal_advice_exclusion: 'No health or legal advice', advice_in_disguise: 'No advice in disguise',
    income_promise_dependency: 'No income promises', fake_proof_dependency: 'No fake reviews, sign-ups or urgency', impersonation_dependency: 'No impersonation',
    money_or_credentials_dependency: 'No money handling or stored credentials', harm_to_people: 'No harm to people', founder_values_conflict: 'Fits your stated values',
    SYSTEM_PROMPT_INJECTION: 'Instructions that try to change the rules', SYSTEM_UNAPPROVED_EXTERNAL_ACTION: 'External actions without your approval',
  };
  const DIM = { desirability: 'Problem and customer', demand: 'Demand', competition: 'Competition and alternatives', feasibility: 'Feasibility', viability: 'Viability and pricing' };
  const FIELD = { problem: 'Problem', target_customers: 'Customer', current_workaround: 'What they use today', target_market: 'Market and location', skills: 'Your skills',
    budget: 'Budget', timeline: 'Time available', values: 'Your values', constraints: 'Constraints' };

  // ------------------------------------------------------------------ API
  class ApiError extends Error { constructor(status, detail) { super(typeof detail === 'string' ? detail : (detail && detail.message) || 'Request failed'); this.status = status; this.detail = detail; } }
  async function api(path, { method = 'GET', body, pid } = {}) {
    const headers = { 'Content-Type': 'application/json' };
    const t = pid && tokenFor(pid);
    if (t) headers['X-Project-Token'] = t;
    let res;
    try { res = await fetch('/api' + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) }); }
    catch (e) { throw new ApiError(0, 'FounderOS server is not reachable. Is Docker still running?'); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(res.status, data.detail ?? data);
    return data;
  }
  let RUBRIC = null;   // team rubric catalogue (67 checks), fetched once
  async function rubricCatalog() { if (!RUBRIC) RUBRIC = await api('/rubric'); return RUBRIC; }
  const DIMNAME = { D01: 'Ethics and legality', D03: 'Problem and customer', D04: 'Demand signals', D05: 'Competition and alternatives', D06: 'Feasibility and founder fit', D07: 'Viability, first look' };
  const SRC_TYPE = { CUSTOMER_VOICE: 'Customers in their own words (forum, review)', INDUSTRY_REPORT: 'Industry report or reputable publication', OFFICIAL_SOURCE: 'Statute, regulator or government page',
    COMPANY_PAGE: "A company's own page", PRICING_PAGE: "A company's public price list", PATENT_RECORD: 'Patent record', TALENT_MARKET: 'Job, salary or freelancer listing',
    DIRECTORY_OR_COMMUNITY: 'Community, directory or platform', ACADEMIC_PASSAGE: 'Passage from a paper (background)', OFFICIAL_STATISTIC: 'Official statistic', FOUNDER_CUSTOMER_RESEARCH: 'Your own customer research' };
  const unknownText = (v) => (v == null || v === '' ? '<span class="faint">Unknown / not provided</span>' : esc(v));

  function errorHtml(e) {
    const d = e.detail;
    const status = e.status ? ` (HTTP ${e.status})` : '';
    if (d && typeof d === 'object' && d.code) {
      return `<div class="notice error" role="alert"><b>The local model could not answer: ${esc(label(d.code))}${status}.</b> <span class="small faint">${esc(d.code)}</span>
        <p>${esc(d.advice || '')}</p><p class="small muted">${esc(d.note || '')} Details: ${esc(d.message || '')}</p></div>`;
    }
    let msg = typeof d === 'string' ? d : (d && d.message) || e.message;
    if (Array.isArray(d)) msg = d.map((x) => `${(x.loc || []).slice(1).join('.')}: ${x.msg}`).join('; ');
    const list = d && (d.failed || (d.findings || []).map((f) => `${RULE_NAME[f.rule_id] || f.rule_id}: ${f.reason}`));
    const what = { 401: 'You are not signed in to this project in this browser.', 403: 'Not allowed by policy.', 404: 'Not found, or this browser does not hold the project key.',
      409: 'Not possible in the current state.', 422: 'Some input needs fixing.' }[e.status] || 'Something went wrong.';
    return `<div class="notice error" role="alert"><b>${esc(what)}${status}</b><p>${esc(msg)}</p>${list && list.length ? `<ul class="bullets small">${list.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}</div>`;
  }
  function flash(html) { const slot = document.getElementById('flash'); if (slot) { slot.innerHTML = html; slot.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } }
  function ok(msg) { flash(`<div class="notice info" role="status">${esc(msg)}</div>`); announce(msg); }

  // Long actions show real elapsed time, never fake progress.
  async function busy(btn, text, fn) {
    const before = btn ? btn.innerHTML : '';
    let s = 0, timer;
    if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spin" aria-hidden="true"></span>${esc(text)}`; timer = setInterval(() => { s++; btn.innerHTML = `<span class="spin" aria-hidden="true"></span>${esc(text)} ${s} s`; }, 1000); }
    announce(text);
    try { return await fn(); }
    catch (e) { flash(errorHtml(e)); announce('Error: ' + e.message); return null; }
    finally { clearInterval(timer); if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = before; } }
  }

  function dialog({ title, body, confirm = 'Confirm', danger = false, cancel = 'Cancel', onConfirm }) {
    dlg.innerHTML = `<form method="dialog"><div class="d-body"><h2 id="dlg-title">${esc(title)}</h2>${body}<div id="dlg-err"></div></div>
      <div class="d-foot"><button class="btn quiet" value="cancel" type="submit">${esc(cancel)}</button><button class="btn ${danger ? 'danger' : ''}" value="ok" id="dlg-ok" type="button">${esc(confirm)}</button></div></form>`;
    dlg.showModal();
    const okBtn = dlg.querySelector('#dlg-ok');
    okBtn.onclick = async () => {
      const form = dlg.querySelector('form');
      if (!form.reportValidity()) return;
      okBtn.disabled = true;
      try { await onConfirm(new FormData(form)); dlg.close(); }
      catch (e) { if (!e.keepOpen) dlg.querySelector('#dlg-err').innerHTML = errorHtml(e); else okBtn.textContent = 'Test again'; }
      finally { okBtn.disabled = false; }
    };
    const first = dlg.querySelector('textarea, input, select');
    (first || okBtn).focus();
  }

  // ------------------------------------------------------------------ routing
  const STEPS = [['brief', 'Brief'], ['safety', 'Safety'], ['discovery', 'Discover'], ['research', 'Research'], ['experiments', 'Demand tests'], ['decision', 'Decision']];
  function parse() {
    const p = location.pathname.replace(/\/+$/, '') || '/projects';
    let m;
    if ((m = p.match(/^\/projects\/([a-f0-9]{32})(?:\/(\w+))?$/))) return { view: m[2] || 'brief', pid: m[1] };
    if (p === '/' || p === '/projects') return { view: 'projects' };
    if (p === '/roadmap') return { view: 'roadmap' };
    if (p === '/help') return { view: 'help' };
    return { view: 'notfound' };
  }
  let navigated = false;   // move focus to <main> only after in-app navigation, never on first load (keeps the skip link first)
  function go(path, replace) { if (replace) history.replaceState({}, '', path); else history.pushState({}, '', path); navigated = true; render(); window.scrollTo(0, 0); }
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[data-link]');
    if (a && !e.metaKey && !e.ctrlKey && a.origin === location.origin) { e.preventDefault(); go(a.getAttribute('href')); }
  });
  window.addEventListener('popstate', () => { navigated = true; render(); });

  let snap = null;   // last snapshot of the current project
  async function load(pid) { snap = await api(`/projects/${pid}`, { pid }); const p = projects(); if (p[pid]) { p[pid].name = snap.project.name; store.set('founderos_projects', p); } return snap; }

  function stepState(s, key) {
    if (!s) return 'todo';
    const st = s.safety && s.safety.status, ack = s.safety && s.safety.acknowledged_at;
    const disc = s.phase_runs.find((r) => r.phase === 'discover'), val = s.phase_runs.find((r) => r.phase === 'validate');
    switch (key) {
      case 'brief': return s.brief ? 'done' : 'attention';
      case 'safety': return !st ? 'todo' : st === 'BLOCK' ? 'blocked' : (st === 'ALLOW_DISCOVERY' || ack) ? 'done' : 'attention';
      case 'discovery': return !disc ? 'todo' : disc.state === 'APPROVED' ? 'done' : disc.state === 'PENDING_APPROVAL' ? 'attention' : 'todo';
      case 'research': return s.evidence.length ? 'done' : 'todo';
      case 'experiments': return s.experiments.some((x) => x.status === 'LOCKED') ? 'done' : s.experiments.length ? 'attention' : 'todo';
      case 'decision': return !val ? 'todo' : val.state === 'PENDING_APPROVAL' ? 'attention' : ['APPROVED', 'STOPPED'].includes(val.state) ? 'done' : 'todo';
    }
    return 'todo';
  }
  const STEP_HINT = { done: 'done', attention: 'needs you', blocked: 'stopped', todo: '' };
  function renderNav(route) {
    const steps = document.getElementById('nav-steps');
    document.getElementById('nav-venture-title').hidden = !route.pid;
    steps.innerHTML = route.pid ? STEPS.map(([k, name], i) => {
      const st = stepState(snap, k);
      return `<a href="/projects/${route.pid}/${k}" data-link data-state="${st}" ${route.view === k ? 'aria-current="page"' : ''}>
        <span class="num" aria-hidden="true">${st === 'done' ? '✓' : i + 1}</span><span>${name}</span><span class="hint">${STEP_HINT[st]}</span></a>`;
    }).join('') + `<a href="/projects/${route.pid}/audit" data-link ${route.view === 'audit' ? 'aria-current="page"' : ''}><span class="num" aria-hidden="true">≣</span><span>Decision log</span></a>` : '';
    for (const [id, v] of [['nav-projects', 'projects'], ['nav-roadmap', 'roadmap'], ['nav-help', 'help']]) {
      const el = document.getElementById(id);
      if (route.view === v) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
    }
  }
  function crumb(title, sub) { document.getElementById('crumb-title').textContent = title; document.getElementById('crumb-sub').textContent = sub; document.title = `${title} | FounderOS`; }

  async function render() {
    const route = parse();
    snap = null;
    main.innerHTML = '<p class="muted" role="status">Loading…</p>';
    try {
      if (route.pid) {
        if (!tokenFor(route.pid)) { renderNav(route); crumb('Project key not found', 'This browser does not hold the key for this project'); main.innerHTML = noKey(); return; }
        await load(route.pid);
      }
      renderNav(route);
      const view = VIEWS[route.view] || VIEWS.notfound;
      await view(route);
      if (navigated) main.focus({ preventScroll: true });
    } catch (e) {
      renderNav(route);
      main.innerHTML = `<div id="flash"></div>${errorHtml(e)}<p><a href="/projects" data-link>Back to projects</a></p>`;
    }
  }
  const noKey = () => `<h1>Project key not found</h1><div class="empty"><h2>This browser does not hold the key for this project</h2>
    <p>Project keys are stored only in the browser that created the project; FounderOS never shows or recovers them. Open the project in that browser, or start a new venture.</p>
    <p><a class="btn secondary" href="/projects" data-link>Go to projects</a></p></div>`;

  function head(title, lede, right = '') { return `<div class="page-head"><div><h1>${esc(title)}</h1>${lede ? `<p class="lede">${lede}</p>` : ''}</div>${right}</div><div id="flash"></div>`; }
  function nextPanel(title, items) { return `<aside class="next" aria-label="What happens next"><h2>${esc(title)}</h2><ol>${items.map((i) => `<li>${i}</li>`).join('')}</ol></aside>`; }
  function actionbar(back, fwd) {
    const b = back ? `<a class="btn quiet" href="${back[0]}" data-link>Back: ${esc(back[1])}</a>` : '<span></span>';
    let f = '';
    if (fwd) f = fwd.disabled ? `<span class="row"><span class="why-disabled">${esc(fwd.reason)}</span><span class="btn" aria-disabled="true">${esc(fwd.label)}</span></span>`
      : `<a class="btn" href="${fwd.href}" data-link>${esc(fwd.label)}</a>`;
    return `<div class="actionbar no-print">${b}${f}</div>`;
  }

  // ------------------------------------------------------------------ model status
  const modelBtn = document.getElementById('model-status');
  async function modelStatus() {
    try {
      const h = await api('/health');
      const o = h.ollama || {};
      modelBtn.dataset.s = o.ollama_reachable && o.model_pulled ? 'warn' : 'bad';
      document.getElementById('model-label').textContent = !o.ollama_reachable ? 'Model offline' : !o.model_pulled ? 'Model not installed' : `${h.model}: installed`;
      modelBtn.title = 'Installed is not the same as working. Click to run a real one-token test.';
      if (modelBtn.dataset.verified === '1' && o.model_pulled) { modelBtn.dataset.s = 'ok'; document.getElementById('model-label').textContent = `${h.model}: ready`; }
    } catch (e) { modelBtn.dataset.s = 'bad'; document.getElementById('model-label').textContent = 'Server unreachable'; }
  }
  modelBtn.addEventListener('click', () => {
    dialog({ title: 'Local model check', confirm: 'Run a real test', body: `<p>This sends one tiny prompt to your local model to prove it can load and answer. On a laptop CPU the first load can take a minute.</p><div id="probe-out"></div>`,
      onConfirm: async () => {
        const out = dlg.querySelector('#probe-out');
        out.innerHTML = '<p class="muted" role="status">Testing…</p>';
        const h = await api('/model/health?probe=1');
        modelBtn.dataset.verified = h.inference_verified ? '1' : '0';
        out.innerHTML = `<dl class="facts small"><dt>Model</dt><dd>${esc(h.model)}</dd><dt>Ollama</dt><dd>${esc(h.host)}</dd>
          <dt>Result</dt><dd>${chip(h.code || (h.inference_verified ? 'READY' : 'UNKNOWN'))}${h.probe_ms ? ` in ${h.probe_ms} ms` : ''}</dd>
          ${h.device ? `<dt>Device</dt><dd>${h.device.vram_mb ? `${h.device.vram_mb} MB on GPU` : 'Running on CPU'} (${esc(h.device.note)})</dd>` : ''}
          <dt>Settings</dt><dd>context ${esc(h.settings.num_ctx)}, GPU layers ${h.settings.num_gpu ?? 'automatic'}, timeout ${esc(h.settings.timeout_s)} s</dd></dl>
          ${h.advice ? `<div class="notice warn"><b>What to do</b><p>${esc(h.advice)}</p></div>` : ''}`;
        modelStatus();
        throw Object.assign(new Error('done'), { keepOpen: true });
      } });
  });

  document.getElementById('theme-toggle').addEventListener('click', (e) => {
    const dark = document.documentElement.dataset.theme !== 'dark';
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    e.currentTarget.textContent = dark ? 'Light' : 'Dark';
    store.set('founderos_theme', dark ? 'dark' : 'light');
  });
  if (document.documentElement.dataset.theme === 'dark') document.getElementById('theme-toggle').textContent = 'Light';

  // ------------------------------------------------------------------ views
  const VIEWS = {};

  VIEWS.notfound = async () => { crumb('Not found', ''); main.innerHTML = `${head('This page does not exist', '')}<p><a href="/projects" data-link>Go to projects</a></p>`; };

  // ---------------- Projects
  VIEWS.projects = async () => {
    crumb('Projects', 'Start a venture or continue one');
    const saved = projects();
    const ids = Object.keys(saved);
    const draft = store.get('founderos_draft_new', {});
    const f = (name, lab, opts = {}) => {
      const v = esc(draft[name] || '');
      const input = opts.area ? `<textarea id="f-${name}" name="${name}" rows="${opts.rows || 3}" ${opts.req ? 'required minlength="12"' : ''} maxlength="${opts.max || 600}">${v}</textarea>`
        : `<input id="f-${name}" name="${name}" value="${v}" maxlength="${opts.max || 300}" ${opts.req ? 'required' : ''}>`;
      return `<div class="field"><label for="f-${name}">${esc(lab)}${opts.req ? '' : ' <span class="opt">(optional)</span>'}</label>${input}${opts.help ? `<p class="help">${esc(opts.help)}</p>` : ''}</div>`;
    };
    main.innerHTML = `${head('Ventures', 'FounderOS helps you decide whether an idea deserves more of your time, using evidence rather than enthusiasm. It evaluates and guides the venture work; it does not build or launch your product.')}
      <div class="cols"><div class="stack">
        ${ids.length ? `<section class="panel" aria-labelledby="p-list"><header><h2 id="p-list">Continue a venture</h2></header><div class="projects" id="project-list">${ids.map((id) => `<div class="project-row" data-pid="${id}"><div><div class="name">${esc(saved[id].name || 'Untitled venture')}</div><div class="sub">Loading status…</div></div><span></span></div>`).join('')}</div></section>` : ''}
        <section class="panel" aria-labelledby="new-h"><header><h2 id="new-h">Start a venture</h2><span class="small muted">Your words are stored exactly as written</span></header>
        <form id="new-form" novalidate>
          <fieldset><legend>The idea</legend>
            ${f('idea', 'Describe the idea in your own words', { area: true, req: true, rows: 5, max: 6000, help: 'What would you build, for whom, and why now? Anything you leave out stays unknown; FounderOS will not fill it in silently.' })}
            <div class="grid2">${f('name', 'Venture name', { max: 80 })}${f('problem', 'The pain you want to solve', { max: 600 })}</div>
          </fieldset>
          <fieldset><legend>Who it is for</legend><div class="grid2">
            ${f('target_customers', 'Customer segment', { help: 'Be narrow: "3rd-year engineering students at Cairo University".' })}
            ${f('target_market', 'Location or market', { help: 'One country or city, e.g. "Cairo, Egypt". Needed for legal and market checks.' })}</div>
            ${f('current_workaround', 'What do they use today instead?', { max: 400 })}
          </fieldset>
          <fieldset><legend>Your limits and values</legend><div class="grid3">
            ${f('skills', 'Your skills')}${f('budget', 'Budget', { help: 'e.g. 1000 EGP' })}${f('timeline', 'Time available', { help: 'e.g. 6 weeks' })}</div>
            <div class="grid2">${f('values', 'Values you will not compromise', { max: 800 })}${f('constraints', 'Other constraints', { max: 800 })}</div>
          </fieldset>
          <div class="row"><button class="btn" type="submit" id="create-btn">Create venture</button><span class="small muted">Next you will refine the brief with the local model and run the safety screen.</span></div>
        </form></section>
      </div>
      ${nextPanel('How a venture moves', ['Refine your brief into fields, each marked as yours, inferred or unknown.', 'Run the twelve safety checks. Hard stops cannot be overridden.',
        'Discover: the local model proposes hypotheses; code scores only what evidence supports.', 'Research: gather and verify sources. Nothing counts until you review it.',
        'Demand tests: lock your pass mark before collecting real results.', 'Decision: the code gives the verdict; you decide what happens next, for research only.'])}
      </div>`;
    const form = document.getElementById('new-form');
    form.addEventListener('input', () => store.set('founderos_draft_new', Object.fromEntries(new FormData(form))));
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!form.reportValidity()) return;
      const data = Object.fromEntries([...new FormData(form)].filter(([, v]) => String(v).trim()));
      await busy(document.getElementById('create-btn'), 'Creating', async () => {
        const r = await api('/projects', { method: 'POST', body: data });
        const p = projects(); p[r.project_id] = { token: r.access_token, name: r.name, created: new Date().toISOString() }; store.set('founderos_projects', p);
        store.del('founderos_draft_new');
        go(`/projects/${r.project_id}/brief`);
      });
    });
    for (const id of ids) {
      const row = main.querySelector(`[data-pid="${id}"]`);
      api(`/projects/${id}/summary`, { pid: id }).then((s) => {
        const status = s.stopped ? chip('STOPPED') : s.verdict ? chip(s.verdict) : s.discover_exit ? chip(s.discover_exit) : s.safety ? chip(s.safety) : '<span class="chip">Not refined</span>';
        row.outerHTML = `<a class="project-row" href="/projects/${id}/${s.verdict ? 'decision' : s.discover ? 'discovery' : s.safety ? 'safety' : 'brief'}" data-link>
          <div><div class="name">${esc(s.name)}</div><div class="sub">Created ${when(s.created_at)}, brief v${s.brief_version || 0}, ${s.evidence} evidence record${s.evidence === 1 ? '' : 's'}</div></div>${status}</a>`;
      }).catch(() => {
        row.innerHTML = `<div><div class="name">${esc(saved[id].name || 'Venture')}</div><div class="sub">This key no longer opens a project (the database may have been reset).</div></div><button class="btn quiet small" data-forget="${id}" type="button">Forget</button>`;
        row.querySelector('[data-forget]').onclick = () => { const p = projects(); delete p[id]; store.set('founderos_projects', p); render(); };
      });
    }
  };

  // ---------------- Brief
  VIEWS.brief = async ({ pid }) => {
    const s = snap, b = s.brief;
    crumb(s.project.name, `Brief${b ? `, version ${b.version}` : ''}`);
    const intake = s.project.intake || {};
    const stopped = s.current.stopped;
    let right;
    if (!b) {
      right = `<section class="panel"><header><h2>Structured brief</h2>${chip('UNKNOWN', 'Not refined yet')}</header>
        <p>Your local model will turn your words into structured fields. Fields you typed stay exactly as written; anything it infers is marked for you to confirm.</p>
        <dl class="facts small">${Object.keys(FIELD).map((k) => `<dt>${FIELD[k]}</dt><dd>${intake[k] ? `${esc(intake[k])} <span class="prov EXPLICIT">Yours</span>` : '<span class="faint">Unknown</span>'}</dd>`).join('')}</dl>
        <div class="row" style="margin-top:14px"><button class="btn" id="refine-btn" ${stopped ? 'disabled' : ''}>Refine and check safety</button><span class="small muted">Runs on your computer. On a CPU this can take a minute or more.</span></div></section>`;
    } else {
      const p = b.payload, fields = p.fields || {};
      const d02 = p.d02_preview;
      const legacy = !p.fields;
      const rowFor = (k) => {
        const f = fields[k] || { status: (p.provenance || {})[k] === 'EXPLICIT' ? 'FORM_FIELD' : p[k] ? 'MODEL_SUGGESTED_UNCONFIRMED' : 'NOT_STATED', value: p[k], spans: [] };
        const sp = (f.spans || [])[0];
        const src = sp ? (sp.source === 'idea' ? `From your words: “${esc(sp.text)}”` : sp.source.startsWith('form') ? 'Typed in the form' : 'Your answer') : '';
        const confirmable = !stopped && f.value && ['STATED_IN_TEXT', 'MODEL_SUGGESTED_UNCONFIRMED'].includes(f.status);
        const placeholder = f.status === 'NOT_STATED' || f.status === 'PARSER_FAILED' ? 'Type your answer' : 'Type a correction';
        return `<div class="field-row" data-field="${k}"><span class="k">${FIELD[k]}${['target_customers', 'problem', 'current_workaround'].includes(k) ? ' <span class="req" title="Needed for idea clarity (D02)">*</span>' : ''}</span>${chip(f.status)}
          <div class="v ${f.value ? '' : 'unknown'}">${f.value ? esc(f.value) : f.status === 'PARSER_FAILED' ? 'The parser failed here. This is a software fault, not a missing answer.' : 'Not stated'}
            ${src ? `<div class="small faint">${src}</div>` : ''}${f.status === 'MODEL_SUGGESTED_UNCONFIRMED' ? '<div class="small faint">Suggested by the local model; it is not in your words and does not count until you confirm it.</div>' : ''}
            ${f.model_suggestion ? `<div class="small faint">The model suggested: “${esc(f.model_suggestion)}” (not used)</div>` : ''}${f.note && f.status !== 'MODEL_SUGGESTED_UNCONFIRMED' ? `<div class="small faint">${esc(f.note)}</div>` : ''}
            ${f.question && !f.value ? `<div class="small question">${esc(f.question)}</div>` : ''}</div>
          ${stopped ? '' : `<div class="v"><label class="sr-only" for="c-${k}">Answer or correct ${FIELD[k]}</label><input id="c-${k}" name="${k}" placeholder="${placeholder}" maxlength="1500">
            ${confirmable ? `<label class="check small"><input type="checkbox" name="confirm" value="${k}"> Correct as written</label>` : ''}</div>`}</div>`;
      };
      const d02Box = d02 ? `<div class="notice ${d02.status === 'PASS' ? 'info' : 'warn'}" style="margin:0 0 14px"><b>Idea clarity (D02): ${d02.status === 'PASS' ? 'customer, pain and current workaround are captured' : 'not yet'}</b>
          ${d02.missing.length ? `<p>Not stated yet: ${d02.missing.map((k) => FIELD[k].toLowerCase()).join(', ')}.</p>` : ''}
          ${d02.model_suggested_unconfirmed.length ? `<p>Only suggested by the model: ${d02.model_suggested_unconfirmed.map((k) => FIELD[k].toLowerCase()).join(', ')}. Confirm or correct them.</p>` : ''}
          ${d02.parser_failed.length ? `<p>The parser failed on: ${d02.parser_failed.map((k) => FIELD[k].toLowerCase()).join(', ')}. Type the answer instead.</p>` : ''}
          ${d02.stated_in_text_please_confirm.length ? `<p class="small">Found in your words, please check: ${d02.stated_in_text_please_confirm.map((k) => FIELD[k].toLowerCase()).join(', ')}.</p>` : ''}</div>` : '';
      right = `<section class="panel" aria-labelledby="sb-h"><header><h2 id="sb-h">Structured brief</h2><span class="small muted">Version ${b.version}${legacy ? ', created before v0.8' : ''}</span></header>
        ${d02Box}
        <p class="small muted">Values come from, in order: your answers, the form, then your own words (with the exact phrase shown). The model's suggestions never count until you confirm them.</p>
        <form id="clarify-form">${Object.keys(FIELD).map(rowFor).join('')}
        ${stopped ? '' : '<div class="row" style="margin-top:12px"><button class="btn" type="submit" id="clarify-btn">Save answers and confirmations</button><span class="small muted">Creates a new brief version, re-runs the safety screen and retires approvals based on the old version.</span></div>'}
        </form>
        ${(p.assumptions || []).length ? `<details class="adv"><summary>Model assumptions (not facts, ${p.assumptions.length})</summary><ul class="bullets small">${p.assumptions.map((q) => `<li>${esc(q)}</li>`).join('')}</ul></details>` : ''}
        ${stopped ? '' : '<div class="row" style="margin-top:12px"><button class="btn quiet small" id="refine-btn">Refine again with the model</button></div>'}
      </section>`;
    }
    const missing = b ? ['target_customers', 'problem', 'current_workaround', 'target_market'].filter((k) => !b.payload[k]) : [];
    const spans = b && b.payload.fields ? Object.entries(b.payload.fields).filter(([k]) => k !== '_signals').flatMap(([k, f]) => (f.spans || []).filter((x) => x.source === 'idea').map((x) => ({ ...x, k }))) : [];
    const marked = (() => { const t = s.project.original_idea; const ss = spans.slice().sort((a, c) => a.start - c.start); let out = '', i = 0;
      for (const x of ss) { if (x.start < i) continue; out += esc(t.slice(i, x.start)) + `<mark title="${esc(FIELD[x.k])}">${esc(t.slice(x.start, x.end))}</mark>`; i = x.end; } return out + esc(t.slice(i)); })();
    const st = s.safety && s.safety.status;
    main.innerHTML = `${head('Your brief', 'Your original words on the left; the structured version the agents will use on the right. Nothing marked unknown is guessed later.')}
      ${stopped ? '<div class="notice warn">This venture was stopped by you. It is read-only.</div>' : ''}
      <div class="cols"><div class="brief-grid">
        <section class="panel"><header><h2>Your words</h2><span class="small muted">Stored exactly${spans.length ? '; highlighted phrases were used for fields' : ''}</span></header><div class="original">${marked}</div></section>
        ${right}
      </div>
      ${nextPanel('What happens next', [b ? (missing.length ? `Fill in: ${missing.map((k) => FIELD[k].toLowerCase()).join(', ')}. Idea clarity (D02) needs customer, pain and current workaround.` : 'Customer, pain and workaround are named.') : 'Refine the brief.',
        st ? `Safety screen: ${chip(st)}` : 'The safety screen runs automatically after refinement.', 'Then open Safety to read the twelve checks.'])}
      </div>
      ${actionbar(['/projects', 'Projects'], b ? { href: `/projects/${pid}/safety`, label: 'Continue to safety' } : { disabled: true, label: 'Continue to safety', reason: 'Refine the brief first.' })}`;
    const rb = document.getElementById('refine-btn');
    if (rb) rb.onclick = () => busy(rb, 'Refining with your local model', async () => { const r = await api(`/projects/${pid}/refine`, { method: 'POST', pid }); await render(); ok(`Brief version ${r.version} saved. Safety screen: ${label(r.safety.status)}.`); });
    const cf = document.getElementById('clarify-form');
    if (cf) {
      cf.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(cf);
        const confirm = fd.getAll('confirm');
        const answers = Object.fromEntries([...fd].filter(([k, v]) => k !== 'confirm' && String(v).trim()));
        const toConfirm = confirm.filter((k) => !answers[k]);
        if (!Object.keys(answers).length && !toConfirm.length) { flash('<div class="notice warn">Type an answer, or tick “Correct as written” on at least one field.</div>'); return; }
        await busy(document.getElementById('clarify-btn'), 'Saving', async () => {
          let r = null;
          if (Object.keys(answers).length) r = await api(`/projects/${pid}/clarify`, { method: 'POST', pid, body: { answers } });
          if (toConfirm.length) r = await api(`/projects/${pid}/brief/confirm`, { method: 'POST', pid, body: { fields: toConfirm } });
          await render();
          const d = r.brief && r.brief.d02_preview;
          ok(`Saved as brief version ${r.version}. Safety re-screened: ${label(r.safety.status)}.${d ? ` Idea clarity (D02): ${d.status === 'PASS' ? 'pass' : 'not yet'}.` : ''}`);
        });
      });
    }
  };

  // ---------------- Safety
  VIEWS.safety = async ({ pid }) => {
    const s = snap;
    crumb(s.project.name, 'Safety and eligibility');
    if (!s.safety) {
      main.innerHTML = `${head('Safety and eligibility', 'Twelve written checks run before any research.')}<div class="empty"><h2>Not screened yet</h2><p>The screen runs when you refine your brief.</p><p><a class="btn" href="/projects/${pid}/brief" data-link>Go to the brief</a></p></div>`;
      return;
    }
    const a = s.safety.assessment, st = s.safety.status, acked = !!s.safety.acknowledged_at;
    const t = st === 'BLOCK' ? 'stop' : st === 'REVIEW_REQUIRED' && !acked ? 'hold' : 'clear';
    const jur = a.jurisdiction || {};
    const gateBody = st === 'BLOCK'
      ? `<p class="why">At least one hard stop applies. No approval can override it, including yours. Change the idea on the brief page and the screen runs again.</p>
         <div class="gate-actions"><a class="btn secondary" href="/projects/${pid}/brief" data-link>Revise the brief</a></div>`
      : st === 'REVIEW_REQUIRED'
        ? (acked ? `<p class="why">You acknowledged the flags on ${when(s.safety.acknowledged_at)}: “${esc(s.safety.ack_statement)}”. That permits research only.</p>`
          : `<p class="why">Some checks need your judgement. You may continue with desk research and tests you run yourself. This does not certify legality and allows no publishing, building or launch.</p>
             <form id="ack-form" class="gate-actions"><div class="field"><label for="ack-st">In your own words, what you understand</label><textarea id="ack-st" name="statement" required minlength="10" rows="2" placeholder="I understand this involves personal data and will get advice before building."></textarea></div>
             <label class="check"><input type="checkbox" required> I understand this permits research only, for brief version ${s.brief.version}.</label>
             <div class="row" style="margin-top:10px"><button class="btn" id="ack-btn">Acknowledge for research only</button><a class="btn quiet" href="/projects/${pid}/brief" data-link>Revise the brief instead</a></div></form>`)
        : '<p class="why">No check stopped or flagged this brief. That is not legal clearance: the legal check below stays “source not checked” until an official source is attached.</p>';
    const rows = a.rules.map((r) => {
      const span = (r.spans || [])[0];
      const quote = span ? (span.conflicts_with ? `“${esc(span.text)}” in your values vs “${esc(span.conflicts_with.text)}” in ${esc(span.conflicts_with.field)}` : `“${esc(span.text)}”`) : '';
      return `<tr><td><b>${esc(RULE_NAME[r.rule_id] || r.rule_id)}</b><div class="small faint">${esc(r.rule_id)}</div></td><td>${chip(r.outcome)}</td>
        <td>${esc(r.reasons[0] || '')}${quote ? `<div class="small">Brief phrase: ${quote}</div>` : ''}${r.detected_by.includes('MODEL_CLASSIFIER_ESCALATION') ? '<div class="small faint">Flagged by the local model (can only ask for your review).</div>' : ''}
        <details class="adv"><summary>Rule and source</summary><dl class="facts small"><dt>Question</dt><dd>${esc(r.question)}</dd><dt>Fails if</dt><dd>${esc(r.fail_if)}</dd>
        <dt>Source needed</dt><dd>${esc(r.source_needed || r.research_instruction)}</dd>
        ${r.official_source ? `<dt>Official source</dt><dd><a href="${esc(r.official_source.url)}" target="_blank" rel="noopener noreferrer">${esc(r.official_source.url)}</a>, ${chip(r.official_source.excerpt_status)} ${r.official_source.official_domain ? '' : '(not an official-looking domain)'}</dd>` : '<dt>Official source</dt><dd>Not found or not checked</dd>'}
        ${r.attempted_searches && r.attempted_searches.length ? `<dt>Searches</dt><dd>${r.attempted_searches.map((q) => `${esc(q.query)} <span class="faint">(proposed, not run automatically)</span>`).join('<br>')}</dd>` : ''}
        <dt>Origin of this rule</dt><dd>${esc(r.provenance)}</dd>${r.founder_review_scope ? `<dt>Your review allows</dt><dd>${esc(r.founder_review_scope)}</dd>` : ''}</dl></details></td></tr>`;
    }).join('');
    const hits = a.rules.filter((r) => ['HARD_STOP', 'REVIEW_REQUIRED'].includes(r.outcome));
    const hitList = hits.length ? `<ul class="plain small" style="margin-top:8px">${hits.map((r) => { const sp = (r.spans || [])[0];
      return `<li>${chip(r.outcome)} <b>${esc(RULE_NAME[r.rule_id] || r.rule_id)}</b>${sp ? `: “${esc(sp.conflicts_with ? sp.conflicts_with.text : sp.text)}”` : ''}<div class="muted">${esc(r.reasons[0] || '')}</div></li>`; }).join('')}</ul>` : '';
    const guards = (a.system_guards || []).map((g) => `<div class="notice error"><b>${esc(RULE_NAME[g.guard_id] || g.guard_id)}</b><p>${esc(g.reason)} Phrase: “${esc(g.spans[0].text)}”.</p></div>`).join('');
    const counts = a.counts || {};
    main.innerHTML = `${head('Safety and eligibility', 'Twelve written checks, applied by code before any research. Grey areas come to you; hard stops end the run.')}
      <div class="cols"><div class="stack">
        <section class="gate" data-tone="${t}" aria-labelledby="sg"><div class="gate-body"><div class="gate-kicker">Safety screen for brief version ${s.brief.version}</div>
          <p class="verdict" id="sg">${esc(label(st))}${st === 'REVIEW_REQUIRED' && acked ? ', acknowledged' : ''}</p>
          <p class="small muted">${counts.HARD_STOP || 0} hard stop, ${counts.REVIEW_REQUIRED || 0} need review, ${counts.UNKNOWN_SOURCE || 0} source not checked, ${counts.CLEAR || 0} no issue found. Jurisdiction: ${esc(jur.country || jur.status || 'unknown')}.</p>
          ${hitList}${gateBody}</div></section>
        ${guards}
        <section class="panel"><header><h2>The twelve checks</h2><span class="small muted">Policy ${esc(a.policy_version)}</span></header>
          <div class="table-wrap"><table class="stack-table"><thead><tr><th scope="col" style="width:26%">Check</th><th scope="col" style="width:16%">Result</th><th scope="col">Why</th></tr></thead><tbody>${rows}</tbody></table></div>
          <p class="small muted">${a.limitations.map(esc).join(' ')}</p></section>
        ${st !== 'BLOCK' && !s.current.stopped ? `<details class="panel"><summary><b>Attach an official source</b> <span class="small muted">for the legal or regulated-area check</span></summary>
          <p class="small muted">Only a regulator, statute or government page counts, and only if FounderOS can fetch it and find your exact excerpt on it. A blog or forum never counts.</p>
          <form id="src-form"><div class="grid2"><div class="field"><label for="src-rule">Check</label><select id="src-rule" name="rule_id"><option value="illegal_in_target_market">Legal in the target market</option><option value="regulated_or_sensitive_area">Sensitive or regulated area</option></select></div>
          <div class="field"><label for="src-find">What the source says</label><select id="src-find" name="finding"><option value="SETS_RULES">Sets rules that apply</option><option value="REQUIRES_LICENCE">Requires a licence I can obtain</option><option value="REQUIRES_UNOBTAINABLE_LICENCE">Requires a licence I cannot obtain</option><option value="PROHIBITS">Prohibits the activity</option><option value="DOES_NOT_ADDRESS">Does not address it</option></select></div></div>
          <div class="field"><label for="src-url">Official page (https)</label><input id="src-url" name="url" type="url" required placeholder="https://"></div>
          <div class="field"><label for="src-ex">Exact excerpt from that page</label><textarea id="src-ex" name="excerpt" rows="2" required minlength="12"></textarea></div>
          <button class="btn secondary" id="src-btn">Fetch and verify</button></form></details>` : ''}
      </div>
      ${nextPanel('What happens next', [st === 'BLOCK' ? 'Revise the idea; the screen re-runs on every new brief version.' : st === 'REVIEW_REQUIRED' && !acked ? 'Acknowledge the flags for research only, or revise the brief.' : 'Run the discovery agent.',
        'The screen runs again on every brief change and on agent outputs.', 'Nobody, including you, can switch off a hard stop.'])}
      </div>
      ${actionbar([`/projects/${pid}/brief`, 'Brief'], st === 'BLOCK' ? { disabled: true, label: 'Continue to discover', reason: 'A hard stop applies.' } : st === 'REVIEW_REQUIRED' && !acked ? { disabled: true, label: 'Continue to discover', reason: 'Acknowledge the flags first.' } : { href: `/projects/${pid}/discovery`, label: 'Continue to discover' })}`;
    const af = document.getElementById('ack-form');
    if (af) af.addEventListener('submit', async (e) => { e.preventDefault(); if (!af.reportValidity()) return; await busy(document.getElementById('ack-btn'), 'Saving', async () => {
      await api(`/projects/${pid}/safety/acknowledge`, { method: 'POST', pid, body: { brief_version: s.brief.version, statement: new FormData(af).get('statement') } }); await render(); ok('Acknowledged for research only.'); }); });
    const sf = document.getElementById('src-form');
    if (sf) sf.addEventListener('submit', async (e) => { e.preventDefault(); if (!sf.reportValidity()) return; await busy(document.getElementById('src-btn'), 'Fetching', async () => {
      const r = await api(`/projects/${pid}/safety/sources`, { method: 'POST', pid, body: Object.fromEntries(new FormData(sf)) }); await render();
      ok(`Source recorded: ${label(r.url_status)}, ${label(r.excerpt_status)}, ${r.official_domain ? 'official-looking domain' : 'not an official domain'}. Safety now: ${label(r.safety_status)}.`); }); });
  };

  // ---------------- criteria table (shared)
  function criteriaTable(rows, pid) {
    return `<div class="table-wrap"><table><thead><tr><th scope="col">Criterion</th><th scope="col">Kind</th><th scope="col">Result</th><th scope="col">Score</th><th scope="col">Why</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td><b>${esc(r.name)}</b><div class="small faint">${esc(r.id)}, PDF p.${esc(r.pdf_page)}</div></td><td class="small">${esc(r.kind.replace('_', ' '))}</td>
        <td>${chip(r.status)}</td><td>${r.score != null ? `<span class="score">${r.score}</span><span class="small faint">/5</span>` : '<span class="faint">—</span>'}</td>
        <td class="small">${esc(r.reasoning)}${(r.caveats || []).length ? `<div class="faint">${r.caveats.map(esc).join(' ')}</div>` : ''}
        ${(r.evidence_ids || []).length ? `<div>Evidence: ${r.evidence_ids.map((id) => `<a href="/projects/${pid}/research?ev=${id}" data-link>${short(id)}</a>`).join(', ')}</div>` : ''}
        ${granularBlock(r, pid)}</td></tr>`).join('')}
      </tbody></table></div>`;
  }
  function granularBlock(r, pid) {
    const g = r.details && r.details.granular;
    if (!g || !g.length) return '';
    const sum = r.details.granular_summary || {};
    const c = sum.counts || {};
    const head = r.id === 'D01' ? `${g.length} ethics checks` : `${sum.known || 0} of ${g.length} team checks rated (${c.STRONG || 0} strong, ${c.MIXED || 0} mixed, ${c.WEAK || 0} weak), ${sum.unknown || 0} unknown`;
    return `<details class="granular"><summary>${esc(head)}</summary>
      <p class="small faint">${esc(sum.rule || '')}${r.details.score_source ? ` Score source: ${esc(label(r.details.score_source).toLowerCase())}.` : ''}</p>
      <ul class="plain">${g.map((x) => `<li class="gcheck">${chip(x.status)} <a href="/projects/${pid}/research?tab=matrix&check=${esc(x.id)}" data-link>${esc(x.question)}</a>
        <span class="faint">${esc(x.id)}${x.sources_required ? `, ${(x.independent_organisations || []).length}/${x.sources_required} sources` : ''}</span></li>`).join('')}</ul></details>`;
  }

  async function decideFlow(pid, run, rec, evalHash, action) {
    const against = ['REPEAT', 'PIVOT', 'REVISE', 'STOP_DO_NOT_LAUNCH'].includes(rec);
    const phaseName = run.phase === 'discover' ? 'discovery' : 'validation';
    const texts = {
      APPROVE: { title: run.phase === 'discover' ? 'Approve validation research?' : 'Approve more research?', confirm: 'Approve research only',
        body: `<p>This records your decision on ${phaseName} version ${run.version} (brief v${run.brief_version}, report ${short(run.report_hash)}). It allows FounderOS to help you design and evaluate demand tests. It never allows building, launching, publishing, sending, spending or signing.</p>
        ${against ? `<div class="notice warn"><b>The gate says ${esc(label(rec))}.</b><p>You can choose a different course, but you must give your reason. It is logged.</p></div>
        <div class="field"><label for="d-fb">Your reason</label><textarea id="d-fb" name="feedback" required minlength="5" rows="3"></textarea></div>
        <label class="check"><input type="checkbox" name="ack" required> I have read the gate's reasons and choose to continue research anyway.</label>`
        : '<div class="field"><label for="d-fb">Note <span class="opt">(optional)</span></label><textarea id="d-fb" name="feedback" rows="2"></textarea></div>'}` },
      REVISE: { title: `Ask the agent to revise the ${phaseName}?`, confirm: 'Request revision', body: '<p>Your feedback goes into the next run. This report is kept, unchanged, in the log.</p><div class="field"><label for="d-fb">What should change?</label><textarea id="d-fb" name="feedback" required minlength="5" rows="3"></textarea></div>' },
      PIVOT: { title: 'Pivot?', confirm: 'Record pivot', body: `<p>A pivot resets work downstream: ${run.phase === 'validate' ? 'discovery reopens and locked tests are archived.' : 'validation is retired.'} The new direction is untested.</p><div class="field"><label for="d-fb">Which direction, and why?</label><textarea id="d-fb" name="feedback" required minlength="5" rows="3"></textarea></div>` },
      STOP: { title: 'Stop this venture?', confirm: 'Stop the venture', danger: true, body: '<p>Stopping is enforced: no further runs, evidence or tests. The full record stays readable. A defensible decision not to launch is a good outcome.</p><div class="field"><label for="d-fb">Reason <span class="opt">(optional)</span></label><textarea id="d-fb" name="feedback" rows="2"></textarea></div>' },
    }[action];
    dialog({ ...texts, onConfirm: async (fd) => {
      const body = { run_id: run.id, report_hash: run.report_hash, brief_version: run.brief_version, decision: action, feedback: fd.get('feedback') || '', acknowledge_risk: fd.get('ack') === 'on' };
      if (evalHash) body.evaluation_hash = evalHash;
      const r = await api(`/projects/${pid}/phases/${run.phase}/decision`, { method: 'POST', pid, body });
      await render(); ok(`Recorded: ${label(r.state)}. Scope: ${r.scope === 'RESEARCH_ONLY' ? 'research only' : 'none'}. Nothing external happened.`);
    } });
  }
  function gateButtons(run, pid, rec, evalHash) {
    if (!run || run.state !== 'PENDING_APPROVAL' || snap.current.stopped) return '';
    const stop = rec === 'STOP';
    return `<div class="gate-actions row" data-run="${run.id}">${stop ? '' : '<button class="btn" data-decide="APPROVE">Approve research</button>'}<button class="btn secondary" data-decide="REVISE">Revise</button><button class="btn secondary" data-decide="PIVOT">Pivot</button><button class="btn danger" data-decide="STOP">Stop venture</button></div>`;
  }
  function wireGate(run, pid, rec, evalHash) { main.querySelectorAll('[data-decide]').forEach((b) => b.onclick = () => decideFlow(pid, run, rec, evalHash, b.dataset.decide)); }

  // ---------------- Discovery
  VIEWS.discovery = async ({ pid }) => {
    const s = snap;
    crumb(s.project.name, 'Discover');
    const run = s.phase_runs.find((r) => r.phase === 'discover');
    const st = s.safety && s.safety.status, cleared = st === 'ALLOW_DISCOVERY' || (st === 'REVIEW_REQUIRED' && s.safety.acknowledged_at);
    const canRun = s.brief && cleared && !s.current.stopped && !(run && ['PENDING_APPROVAL', 'APPROVED'].includes(run.state));
    const why = !s.brief ? 'Refine the brief first.' : !cleared ? (st === 'BLOCK' ? 'A hard stop applies.' : 'Acknowledge the safety flags first.') : s.current.stopped ? 'This venture is stopped.' : 'Waiting for your decision on the current run.';
    const ev = s.criteria.discover, e = ev && ev.evaluation;
    const runBtn = `<button class="btn ${run ? 'secondary' : ''}" id="disc-run" ${canRun ? '' : 'disabled'}>${run ? 'Run again with your feedback' : 'Run the discovery agent'}</button>${canRun ? '' : `<span class="why-disabled">${esc(why)}</span>`}`;
    if (!run) {
      main.innerHTML = `${head('Discover', 'A separate agent on your local model proposes the problem, beachhead customer, alternatives, hypotheses and cheap tests. Everything it writes is a hypothesis.')}
        <div class="empty"><h2>No discovery yet</h2><p>On a laptop CPU the agent can take a minute or more. You will decide what happens next; nothing continues automatically.</p><div class="row">${runBtn}</div></div>
        ${actionbar([`/projects/${pid}/safety`, 'Safety'], { disabled: true, label: 'Continue to research', reason: 'Run discovery first.' })}`;
      wireRun();
      return;
    }
    const r = run.report;
    const list = (xs) => (xs || []).length ? `<ul class="bullets">${xs.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : '<p class="faint">None given.</p>';
    const flags = (r._safety_flags || []);
    const tone2 = e ? ({ GO_ON: 'clear', STOP: 'stop', PIVOT: 'hold', REPEAT: 'hold', REVIEW_REQUIRED: 'hold' }[e.exit] || 'unknown') : 'unknown';
    const unknownN = e ? e.criteria.filter((c) => c.unknown).length : null;
    main.innerHTML = `${head('Discover', 'Hypotheses from your local model, then a gate decided by code from the evidence you have.', `<div class="row no-print">${runBtn}</div>`)}
      <div class="notice info small"><b>Everything in the cards below is a hypothesis</b> written by the local model from your brief. None of it is evidence and no customer was contacted.</div>
      ${run.invalidated_reason ? `<div class="notice warn">This run is out of date: ${esc(run.invalidated_reason)}. Run it again.</div>` : ''}
      ${flags.length ? `<div class="notice error"><b>The agent proposed a prohibited tactic</b><p>${flags.map((f) => `${esc(RULE_NAME[f.rule_id] || f.rule_id)} in “${esc(f.text.slice(0, 120))}”`).join('; ')}. The gate asks you to revise.</p></div>` : ''}
      <div class="cols"><div class="stack">
        <div class="cards">
          <section class="card wide"><h3>Problem and customer <span class="small faint">hypothesis</span></h3><p>${esc(r.problem_statement)}</p>
            <dl class="facts small"><dt>Who uses it</dt><dd>${unknownText(r.beachhead_user)}</dd><dt>Who pays</dt><dd>${unknownText(r.beachhead_payer)}</dd><dt>Target groups</dt><dd>${(r.target_customers || []).map(esc).join('; ')}</dd></dl></section>
          <section class="card"><h3>What they use today <span class="chip unknown" title="not sourced">Unverified</span></h3>${list(r.alternatives_unverified)}<p class="small faint">Listed by the model, not found by search. “None found” never means no competitors.</p></section>
          <section class="card"><h3>Value proposition</h3><p>${esc(r.value_proposition)}</p>${(r.opportunities || []).length ? `<h3 style="margin-top:10px">Opportunities</h3>${list(r.opportunities)}` : ''}</section>
          <section class="card"><h3>Feasibility for you</h3>${list(r.feasibility_notes)}</section>
          <section class="card"><h3>Viability, first look <span class="chip hold plain">Untested</span></h3><p>${esc(r.viability_first_look || 'No charging idea given.')}</p></section>
          <section class="card wide"><h3>Falsifiable hypotheses</h3>${list(r.hypotheses)}</section>
          <section class="card"><h3>Candidate directions</h3>${(r.directions || []).length ? r.directions.map((d) => `<div class="dir"><span class="tag" aria-label="Direction ${esc(d.id)}">${esc(d.id)}</span><div><b>${esc(d.name)}</b><div class="small muted">${esc(d.segment)}: ${esc(d.value)}</div></div></div>`).join('') : '<p class="faint">None given.</p>'}</section>
          <section class="card"><h3>Most critical unknowns</h3>${list(r.unknowns)}<h3 style="margin-top:10px">Cheap tests it suggests</h3>${list(r.experiments)}</section>
        </div>
        ${r._quality && ((r._quality.first_pass_issues || []).length || r._quality.degraded) ? `<section class="panel"><header><h2>Quality check on the model's output</h2>${chip(r._quality.degraded ? 'REVIEW_REQUIRED' : 'PASS', 'Code check')}</header>
          <p class="small muted">Code compared the model's text with your brief: ${r._quality.attempts} attempt(s)${r._quality.degraded ? '; problems that remained after one retry were removed, not replaced' : ''}.</p>
          <ul class="bullets small">${(r._quality.remaining_issues || []).map((i) => `<li>${esc(i.issue)}</li>`).join('') || '<li>The retry fixed the problems found in the first answer.</li>'}</ul>
          ${(r._removed_directions || []).length ? `<p class="small">Removed directions: ${r._removed_directions.map((d) => `“${esc(d.name)}” (${esc(d.segment)})`).join('; ')}.</p>` : ''}</section>` : ''}
        ${(r._skeptic_flags || []).length ? `<details class="panel"><summary><b>Skeptic review</b> <span class="small muted">${r._skeptic_flags.length} over-claims or unsourced numbers in the agent's text</span></summary><ul class="bullets small">${r._skeptic_flags.map((f) => `<li>${esc(f.issue)}</li>`).join('')}</ul></details>` : ''}
        <section class="gate" data-tone="${tone2}" aria-labelledby="dg"><div class="gate-body">
          <div class="gate-kicker">Discover gate, decided by code (criterion D09), run v${run.version}</div>
          <p class="verdict" id="dg">${e ? esc(label(e.exit)) : 'Not evaluated'}</p>
          ${e ? `<div class="why">${e.reasons.map((x) => `<p>${esc(x)}</p>`).join('')}</div><p class="small muted">${unknownN} of ${e.criteria.length} criteria unknown. Unknown is not zero. Settings: pass mark ${e.config.discover_gate.pass_mark}, pivot mark ${e.config.discover_gate.pivot_mark}, at most ${e.config.discover_gate.max_unknown_scored} unknown scores (team assumptions).</p>` : ''}
          ${ev && ev.stale ? `<div class="notice warn"><b>Evidence or settings changed since this evaluation.</b><p>Re-evaluate before deciding.</p><button class="btn secondary" id="reeval">Re-evaluate criteria</button></div>` : ''}
          <p class="small">State: ${chip(run.state)} ${run.state === 'APPROVED' ? 'Approval allows validation research only.' : ''}</p>
          ${ev && ev.stale ? '' : gateButtons(run, pid, e && e.exit)}
        </div></section>
        ${e ? `<section class="panel"><header><h2>Criteria scorecard</h2><span class="small muted">${esc(e.criteria_version)}</span></header>${criteriaTable(e.criteria, pid)}
          <div class="row" style="margin-top:12px"><button class="btn secondary small" id="reeval2">Re-evaluate after new evidence</button><span class="small muted">The judge scores one criterion at a time, only from evidence in your ledger, and code checks every reference.</span></div></section>` : ''}
        ${settingsPanel(s)}
        <details class="adv"><summary>Advanced: raw report and hashes</summary><p class="small">Report hash <code>${esc(run.report_hash)}</code>, evaluation <code>${esc(e && e.evaluation_hash)}</code>, model ${esc(run.model)}, ${run.latency_ms} ms.</p><pre>${esc(JSON.stringify(r, null, 2))}</pre></details>
      </div>
      ${nextPanel('What happens next', [e && e.exit === 'REPEAT' ? 'Gather evidence in Research, then re-evaluate. Or approve with a recorded reason to start designing a demand test.' : 'Read the gate and decide.',
        'Approving allows validation research only.', 'Revise sends your feedback to the agent; Pivot resets downstream work.'])}
      </div>
      ${actionbar([`/projects/${pid}/safety`, 'Safety'], { href: `/projects/${pid}/research`, label: 'Continue to research' })}`;
    wireRun();
    wireGate({ ...run, phase: 'discover' }, pid, e && e.exit, e && ev.evaluation_hash);
    for (const id of ['reeval', 'reeval2']) { const b = document.getElementById(id); if (b) b.onclick = () => busy(b, 'Evaluating', async () => { const x = await api(`/projects/${pid}/criteria/evaluate`, { method: 'POST', pid }); await render(); ok(`Re-evaluated with ${x.judge_calls} judge call(s). Gate: ${label(x.evaluation.exit)}.`); }); }
    wireSettings(pid);
    function wireRun() { const b = document.getElementById('disc-run'); if (b) b.onclick = () => busy(b, 'Running the discovery agent', async () => { const x = await api(`/projects/${pid}/phases/discover/run`, { method: 'POST', pid }); await render(); ok(`Discovery version ${x.version} ready in ${Math.round(x.latency_ms / 1000)} s. Gate: ${label(x.evaluation && x.evaluation.exit)}.`); }); }
  };

  function settingsPanel(s) {
    const c = s.criteria.config;
    return `<details class="panel"><summary><b>Criteria settings</b> <span class="small muted">version ${s.criteria.config_version}, ${esc(c.origin)}</span></summary>
      <p class="small muted">These weights and pass marks are your team's assumptions, not industry benchmarks. Change them before a run; a change creates a new version and retires approvals made under the old one. Safety checks and knockouts cannot be changed.</p>
      <form id="cfg-form"><div class="grid3">${Object.entries(c.weights).map(([k, v]) => `<div class="field"><label for="w-${k}">Weight ${esc(k)}</label><input id="w-${k}" name="w.${k}" type="number" min="0.5" max="10" step="0.5" value="${v}"></div>`).join('')}</div>
      <div class="grid3"><div class="field"><label for="g-pass">Discover pass mark (1–5)</label><input id="g-pass" name="g.pass_mark" type="number" min="1.5" max="5" step="0.5" value="${c.discover_gate.pass_mark}"></div>
      <div class="field"><label for="g-piv">Pivot mark</label><input id="g-piv" name="g.pivot_mark" type="number" min="1" max="4.5" step="0.5" value="${c.discover_gate.pivot_mark}"></div>
      <div class="field"><label for="g-unk">Most unknown scores allowed</label><input id="g-unk" name="g.max_unknown_scored" type="number" min="0" max="5" step="1" value="${c.discover_gate.max_unknown_scored}"></div>
      <div class="field"><label for="g-age">Oldest source, years</label><input id="g-age" name="e.max_age_years" type="number" min="1" max="30" value="${c.evidence.max_age_years}"></div>
      <div class="field"><label for="g-nm">Near-miss band</label><input id="g-nm" name="r.near_miss_band" type="number" min="0" max="0.5" step="0.05" value="${c.results.near_miss_band}"></div></div>
      <button class="btn secondary small" id="cfg-btn">Save as new settings version</button></form></details>`;
  }
  function wireSettings(pid) {
    const f = document.getElementById('cfg-form');
    if (!f) return;
    f.addEventListener('submit', async (e) => {
      e.preventDefault();
      const changes = { weights: {}, discover_gate: {}, evidence: {}, results: {} };
      for (const [k, v] of new FormData(f)) {
        const [g, n] = k.split('.');
        const num = Number(v);
        if (g === 'w') changes.weights[n] = num; else if (g === 'g') changes.discover_gate[n] = n === 'max_unknown_scored' ? Math.round(num) : num;
        else if (g === 'e') changes.evidence[n] = Math.round(num); else changes.results[n] = num;
      }
      await busy(document.getElementById('cfg-btn'), 'Saving', async () => { const r = await api(`/projects/${pid}/criteria/config`, { method: 'POST', pid, body: { changes } }); await render(); ok(`Settings version ${r.version} saved. Re-run to apply.`); });
    });
  }

  // ---------------- Research
  const RS_TABS = [['matrix', 'Criteria matrix'], ['plan', 'Plan and run'], ['sources', 'Sources'], ['ledger', 'Evidence ledger'], ['customers', 'Your customer research']];
  const DIM_OF_D = { D03: 'desirability', D04: 'demand', D05: 'competition', D06: 'feasibility', D07: 'viability' };
  const REL_Q = [['claim_supported', 'Does the passage itself support or challenge your claim, not just use the same words?', false],
    ['geography', 'Is it about your target market (country or city)?', true], ['buyer_user', 'Is it about your customer or buyer group?', true],
    ['method', 'Is the method credible for this claim (counted actions, official data, a real survey), not just opinion?', true], ['date', 'Is it dated and recent enough?', true]];
  function relevanceFields(prefix) {
    return `<fieldset class="relevance"><legend>Relevance review <span class="opt">(all five decide whether it counts)</span></legend>
      <p class="help">Words appearing on the page is not the same as the claim being supported. Only “Yes” or “Not applicable” on all five makes a source count for a check.</p>
      ${REL_Q.map(([k, q, na]) => `<div class="rq"><span>${esc(q)}</span><select name="rel.${k}" aria-label="${esc(q)}" id="${prefix}-${k}"><option value="UNSURE">Unsure</option><option value="YES">Yes</option><option value="NO">No</option>${na ? '<option value="NOT_APPLICABLE">Not applicable</option>' : ''}</select></div>`).join('')}</fieldset>`;
  }
  function collectRelevance(fd) {
    const out = {}; let any = false;
    for (const [k] of REL_Q) { const v = fd['rel.' + k]; if (v) { out[k] = v; any = true; } delete fd['rel.' + k]; }
    return any ? out : null;
  }
  function checkOptions(cat, dim, selected) {
    const groups = ['D03', 'D04', 'D05', 'D06', 'D07'].filter((d) => !dim || d === dim);
    return `<option value="">Not linked to a team check</option>${groups.map((d) => `<optgroup label="${esc(DIMNAME[d])}">${cat.checks.filter((c) => c.dimension === d).map((c) => `<option value="${esc(c.id)}" ${c.id === selected ? 'selected' : ''}>${esc(c.judge_instruction.question.slice(0, 90))}</option>`).join('')}</optgroup>`).join('')}`;
  }
  const CLAIM_HELP = 'One sentence this source speaks to, in plain words. Good: “Small Cairo restaurants throw away unsold ingredients every week.” Not: “restaurants”, “AI”, or the page title.';
  VIEWS.research = async ({ pid }) => {
    const s = snap;
    crumb(s.project.name, 'Research');
    if (!s.brief) { main.innerHTML = `${head('Research', '')}<div class="empty"><h2>Refine the brief first</h2><p>The research plan is built from your brief.</p><a class="btn" href="/projects/${pid}/brief" data-link>Go to the brief</a></div>`; return; }
    const params = new URLSearchParams(location.search);
    const tab = params.get('tab') || (params.get('ev') ? 'ledger' : 'matrix');
    const [plan, rs] = await Promise.all([api(`/projects/${pid}/research/plan`, { pid }), api(`/projects/${pid}/research`, { pid }), rubricCatalog()]);
    const blocked = s.safety && s.safety.status === 'BLOCK';
    const ev = s.criteria.discover;
    main.innerHTML = `${head('Research', 'Gather sources, inspect the actual pages, and add exact passages to your evidence ledger. Finding a source is not verifying it, and a published article never proves demand for your product.')}
      ${blocked ? '<div class="notice error"><b>Hard stop.</b><p>No research runs for an idea that hits a hard stop.</p></div>' : ''}
      <div class="tabs" role="tablist">${RS_TABS.map(([k, n]) => `<button role="tab" aria-selected="${k === tab}" data-tab="${k}">${n}${k === 'sources' ? `<span class="count">${rs.candidates.length}</span>` : k === 'ledger' ? `<span class="count">${s.evidence.length}</span>` : ''}</button>`).join('')}</div>
      <div class="${tab === 'matrix' ? '' : 'cols'}"><div id="tab-body"></div>
      ${tab === 'matrix' ? '' : nextPanel('What happens next', ['Run the plan, or inspect pages you found yourself.', 'Add exact passages to the ledger; you choose what each one supports or challenges.',
        `Re-evaluate the Discover criteria${ev && ev.stale ? ' (evidence has changed)' : ''}.`, 'Then design a demand test: the only route to evidence of demand.'])}</div>
      <div class="row no-print" style="margin-top:16px"><button class="btn secondary" id="rs-eval" ${s.phase_runs.some((r) => r.phase === 'discover') ? '' : 'disabled'}>Re-evaluate Discover criteria</button>${ev && ev.stale ? chip('INVALIDATED', 'Evidence changed since the last evaluation') : ''}</div>
      ${actionbar([`/projects/${pid}/discovery`, 'Discover'], { href: `/projects/${pid}/experiments`, label: 'Continue to demand tests' })}`;
    main.querySelectorAll('[data-tab]').forEach((b) => b.onclick = () => { history.replaceState({}, '', `/projects/${pid}/research?tab=${b.dataset.tab}`); VIEWS.research({ pid }); });
    const evb = document.getElementById('rs-eval');
    evb.onclick = () => busy(evb, 'Evaluating', async () => { const x = await api(`/projects/${pid}/criteria/evaluate`, { method: 'POST', pid }); await load(pid); ok(`Re-evaluated with ${x.judge_calls} judge call(s). Discover gate: ${label(x.evaluation.exit)}.`); });
    const body = document.getElementById('tab-body');
    if (tab === 'matrix') await renderMatrix(body, pid, params.get('check'), blocked);
    else if (tab === 'plan') renderPlan(body, pid, plan, rs, blocked);
    else if (tab === 'sources') renderSources(body, pid, rs, plan);
    else if (tab === 'ledger') renderLedger(body, pid, params.get('ev'));
    else renderCustomers(body, pid);
  };

  async function renderMatrix(body, pid, focus, blocked) {
    const [m, cat] = await Promise.all([api(`/projects/${pid}/rubric`, { pid }), rubricCatalog()]);
    if (!m.checks.length) { body.innerHTML = `<div class="empty"><p>${esc(m.note || 'Refine the brief first.')}</p></div>`; return; }
    const sel = m.checks.find((c) => c.id === focus) || m.checks.find((c) => c.id === (m.priority || [])[0]) || m.checks.find((c) => c.kind === 'scored');
    const groups = ['D03', 'D04', 'D05', 'D06', 'D07', 'D01'];
    const dimHead = (d) => { const a = m.dimensions[d] || {}; const c = a.counts || {};
      return d === 'D01' ? `${c.HARD_STOP || 0} hard stop, ${c.REVIEW_REQUIRED || 0} review, ${c.CLEAR || 0} clear`
        : `${a.score != null ? `score ${a.score}/5, ` : 'no score yet, '}${a.known || 0}/${a.checks} rated`; };
    body.innerHTML = `<div class="matrix">
      <nav class="mx-list" aria-label="Team rubric checks">
        <p class="small muted">${m.coverage.total} team checks under the original dimensions. Rubric ${esc(m.version)}.</p>
        ${(m.priority || []).length ? `<p class="small"><b>Highest decision risk first:</b> start with demand and problem checks.</p>` : ''}
        ${groups.map((d) => `<details ${d === sel.dimension || (d !== 'D01' && !focus && d === 'D04') ? 'open' : ''}><summary><b>${esc(d)} ${esc(DIMNAME[d])}</b><span class="small faint">${esc(dimHead(d))}</span></summary>
          <ul class="plain">${m.checks.filter((c) => c.dimension === d).map((c) => `<li><a href="/projects/${pid}/research?tab=matrix&check=${esc(c.id)}" data-link ${c.id === sel.id ? 'aria-current="true"' : ''}>${chip(c.status)}<span>${esc(c.question)}</span></a></li>`).join('')}</ul></details>`).join('')}
      </nav>
      <section class="panel mx-detail" aria-labelledby="mx-h">${checkDetail(sel, cat, pid, blocked)}</section></div>`;
    wireCheck(body, sel, pid);
  }
  function checkDetail(c, cat, pid, blocked) {
    const p = c.provenance || {};
    const defs = c.kind === 'knockout' ? `<dt>Fails if</dt><dd>${esc(c.definitions.fail_if)}</dd>`
      : ['weak', 'mixed', 'strong'].map((k) => `<dt>${chip(k.toUpperCase())}</dt><dd>${esc(c.definitions[k])}</dd>`).join('');
    const evLink = (id) => `<a href="/projects/${pid}/research?ev=${id}" data-link>${short(id)}</a>`;
    const sr = c.search || {};
    const types = (c.accepted_source_types || []).filter((t) => t !== 'BRIEF');
    return `<header><div><div class="small faint">${esc(c.dimension)} ${esc(DIMNAME[c.dimension])} · ${esc(c.id)}</div><h2 id="mx-h">${esc(c.question)}</h2></div>${chip(c.status)}</header>
      <p class="small">${esc(c.basis || '')}</p>${(c.caps || []).map((x) => `<p class="small notice warn">${esc(x)}</p>`).join('')}${c.reasoning ? `<p class="small muted">Judge: ${esc(c.reasoning)}</p>` : ''}
      <dl class="facts small defs">${defs}</dl>
      ${c.kind === 'knockout' ? `<p class="small">${esc(c.next_step || '')} <a href="/projects/${pid}/safety" data-link>Open the safety screen</a>.</p>` : `
      <h3>What counts as evidence here</h3>
      <p class="small">${esc(c.research_instruction)}</p>
      <dl class="facts small"><dt>Sources required</dt><dd>${c.sources_required || 'none external'} independent organisation(s); <b>${(c.independent_organisations || []).length}</b> accepted${(c.independent_organisations || []).length ? ` (${c.independent_organisations.map(esc).join(', ')})` : ''}</dd>
        <dt>Accepted source types</dt><dd>${types.map((t) => esc(SRC_TYPE[t] || t)).join('; ')}</dd>
        ${c.absence_claim_cap ? `<dt>Limit</dt><dd>${esc(c.absence_claim_cap)}</dd>` : ''}
        <dt>Supports</dt><dd>${(c.supporting_ids || []).length ? c.supporting_ids.map(evLink).join(', ') : '<span class="faint">none</span>'}</dd>
        <dt>Challenges</dt><dd>${(c.contradicting_ids || []).length ? c.contradicting_ids.map(evLink).join(', ') : '<span class="faint">none</span>'}</dd>
        ${(c.rejected || []).length ? `<dt>Not counted</dt><dd><ul class="plain">${c.rejected.map((x) => `<li>${evLink(x.id)}: ${esc(x.reason)}</li>`).join('')}</ul></dd>` : ''}
        <dt>Searches tried</dt><dd>${(c.queries_tried || []).length ? c.queries_tried.map((q) => `${esc(q.provider)} “${esc(q.query)}”: ${chip(q.status, q.error)}`).join('<br>') : '<span class="faint">none yet</span>'}</dd>
        <dt>Next step</dt><dd>${esc(c.next_step || '')}</dd></dl>
      <div class="mx-actions">
        <div><b class="small">Search for this check</b><p class="small"><code>${esc(sr.query || '')}</code></p><p class="small muted">${esc(sr.automated_note || '')}</p>
          <div class="row">${(sr.automated_providers || []).length && !blocked ? `<button class="btn secondary small" id="mx-run">Search ${sr.automated_providers.map((x) => x === 'openalex' ? 'OpenAlex' : 'Crossref').join(' and ')}</button>` : ''}
          ${(sr.manual_searches || []).map((x) => `<a class="btn quiet small" href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.label)}</a>`).join('')}</div></div>
        <div class="row">${(c.evidence_ids || []).length ? `<button class="btn small" id="mx-judge">Judge this check (one local-model call)</button>` : '<span class="why-disabled">Judging needs at least one accepted, linked source.</span>'}</div>
      </div>
      <details class="panel inset" ${blocked ? '' : ''}><summary><b>Add a source for this check</b></summary>
        <form id="mx-add"><div class="grid2"><div class="field"><label for="mx-url">Page (https)</label><input id="mx-url" name="url" type="url" required placeholder="https://"></div>
          <div class="field"><label for="mx-type">What kind of source is it?</label><select id="mx-type" name="source_type" required>${types.map((t) => `<option value="${t}">${esc(SRC_TYPE[t] || t)}</option>`).join('')}</select></div></div>
        <div class="field"><label for="mx-ex">Exact passage, copied from the page</label><textarea id="mx-ex" name="excerpt" rows="3" required minlength="12" maxlength="1200"></textarea><p class="help">FounderOS fetches the page and checks these exact words are on it.</p></div>
        <div class="field"><label for="mx-claim">Claim it bears on</label><input id="mx-claim" name="claim" required minlength="8" maxlength="800"><p class="help">${esc(CLAIM_HELP)}</p></div>
        <div class="grid3"><div class="field"><label for="mx-pub">Publisher or organisation</label><input id="mx-pub" name="publisher" maxlength="200" placeholder="Who published it"></div>
          <div class="field"><label for="mx-date">Published</label><input id="mx-date" name="published_on" maxlength="40" placeholder="2025 or 2025-03-01"></div>
          <div class="field"><label for="mx-geo">Geography it describes</label><input id="mx-geo" name="geography" maxlength="120" placeholder="e.g. Egypt"></div>
          <div class="field"><label for="mx-dir">Supports or challenges the check?</label><select id="mx-dir" name="direction"><option value="SUPPORTS">Supports</option><option value="CONTRADICTS">Challenges</option><option value="UNSURE">Unsure</option></select></div></div>
        ${relevanceFields('mx')}
        <label class="check small"><input type="checkbox" name="founder_supplied_excerpt"> If FounderOS cannot fetch the page (paywall, certificate or size error), keep it as a passage I copied myself. It will be labelled “pasted by you, not verified” and can never make a check strong on its own.</label>
        <div class="row" style="margin-top:10px"><button class="btn secondary small" id="mx-add-btn">Fetch, verify and add</button></div></form></details>`}
      <details class="adv"><summary>Why this check exists (team-supplied reference)</summary><dl class="facts small"><dt>Source</dt><dd>${esc(p.book)}</dd><dt>Chapter</dt><dd>${esc(p.chapter)}</dd><dt>Page</dt><dd>${esc(p.page)}</dd>
        <dt>Passage</dt><dd>“${esc(p.supporting_passage)}”</dd><dt>Basis</dt><dd>${esc(p.basis)}</dd></dl>
        <p class="small faint">Supplied by the team and not independently checked against the book. It is the reason for the check, never evidence that your venture meets it.</p></details>`;
  }
  function wireCheck(body, c, pid) {
    const rerender = async () => { await load(pid); await VIEWS.research({ pid }); };
    const run = body.querySelector('#mx-run');
    if (run) run.onclick = () => busy(run, 'Searching', async () => {
      const items = c.search.automated_providers.map((pr) => ({ bucket: { D03: 'PROBLEM', D04: 'MARKET', D05: 'COMPETITORS', D06: 'FEASIBILITY', D07: 'VIABILITY' }[c.dimension] || 'PROBLEM', provider: pr, query: c.search.query.slice(0, 160), subcriterion_id: c.id }));
      const r = await api(`/projects/${pid}/research/run`, { method: 'POST', pid, body: { items } });
      await rerender();
      flash(`<div class="notice info">${r.runs.map((x) => `${esc(x.provider)}: ${esc(label(x.status))}${x.error ? ` (${esc(x.error)})` : ''}, ${x.new_candidates} new candidate(s)`).join('; ')}. Candidates are metadata about papers: open the Sources tab, inspect the page and pick a passage before anything can count.</div>`);
    });
    const j = body.querySelector('#mx-judge');
    if (j) j.onclick = () => busy(j, 'Judging', async () => { const r = await api(`/projects/${pid}/rubric/judge`, { method: 'POST', pid, body: { only: c.id, max_calls: 1 } }); await rerender();
      const x = r.judged[c.id] || {}; ok(x.valid ? `Judged: ${label(x.rating || 'UNKNOWN')}${(x.caps || []).length ? ' (capped by code)' : ''}.` : `Judge output rejected: ${x.rejected_reason || 'no eligible evidence'}. The check stays unknown.`); });
    const f = body.querySelector('#mx-add');
    if (f) f.addEventListener('submit', async (e) => { e.preventDefault(); if (!f.reportValidity()) return;
      const fd = Object.fromEntries([...new FormData(f)].filter(([, v]) => String(v).trim()));
      const rel = collectRelevance(fd);
      const body2 = { ...fd, kind: 'SECONDARY_BACKGROUND', dimension: DIM_OF_D[c.dimension], subcriterion_id: c.id, relevance_checks: rel, founder_supplied_excerpt: !!fd.founder_supplied_excerpt, relevance: 'UNSURE' };
      await busy(document.getElementById('mx-add-btn'), 'Fetching and checking', async () => { const r = await api(`/projects/${pid}/evidence`, { method: 'POST', pid, body: body2 }); await rerender();
        flash(`<div class="notice ${r.review_state === 'ACCEPTED_RELEVANT' ? 'info' : 'warn'}"><b>Added to the ledger: ${esc(label(r.review_state || 'UNKNOWN'))}.</b><p>${esc(r.review_reason || '')} Page: ${esc(label(r.url_status))}, excerpt: ${esc(label(r.excerpt_status))}.${(r.review_flags || []).length ? ' ' + r.review_flags.map(esc).join(' ') : ''}</p></div>`); }); });
  }

  function renderPlan(body, pid, plan, rs, blocked) {
    const prov = plan.providers;
    body.innerHTML = `<div class="stack">
      <section class="panel"><header><h2>Research plan from your brief</h2><span class="small muted">Brief v${plan.brief_version}</span></header>
        <p class="small muted">${esc(plan.notice)} Ranking by keyword overlap is an exploratory heuristic only.</p>
        <form id="plan-form">${plan.buckets.map((b) => `<div class="bucket"><h3>${esc(b.title)}</h3><p class="small">${esc(b.question)}</p>
          ${b.items.map((it, i) => `<div class="query"><label class="check"><input type="checkbox" name="sel" value="${esc(b.id)}|${i}" checked><span class="prov-name">${esc(prov[it.provider].name)}</span></label>
            ${it.query != null ? `<label class="sr-only" for="q-${b.id}-${i}">Query</label><input id="q-${b.id}-${i}" name="q:${b.id}|${i}" value="${esc(it.query)}" maxlength="160">` : `<span>${esc(it.indicator)} <span class="small faint">official national statistic</span></span>`}<span></span></div>`).join('')}
          ${b.status === 'DISCOVERY_NOT_AVAILABLE' ? `<p class="small">${chip('DISCOVERY_NOT_AVAILABLE')}</p>` : ''}
          <p class="small muted">${esc(b.caution)}</p>
          ${b.manual.length ? `<p class="small">Search yourself: ${b.manual.map((m) => `<a href="${esc(m.open_in_browser)}" target="_blank" rel="noopener noreferrer">${esc(m.query)}</a>`).join(', ')}. Paste pages you want verified in the Sources tab.</p>` : ''}</div>`).join('')}
        <div class="row"><button class="btn" id="plan-run" ${blocked ? 'disabled' : ''}>Run selected searches</button><span class="small muted">Sends only the queries shown to the providers listed. Free public services; they may throttle or be offline.</span></div></form></section>
      <section class="panel"><header><h2>Providers and what they cannot do</h2></header><div class="table-wrap"><table><thead><tr><th>Provider</th><th>Covers</th><th>Does not cover</th></tr></thead><tbody>
        ${Object.values(prov).map((p) => `<tr><td><b>${esc(p.name)}</b><div class="small faint">${esc(p.access)}</div></td><td class="small">${esc(p.covers)}</td><td class="small">${esc(p.does_not_cover)}</td></tr>`).join('')}</tbody></table></div></section>
      <section class="panel"><header><h2>Search history</h2></header>${rs.runs.length ? `<div class="table-wrap"><table><thead><tr><th>When</th><th>Bucket</th><th>Provider</th><th>Query</th><th>Status</th><th>Results</th></tr></thead><tbody>
        ${rs.runs.map((r) => `<tr><td class="small">${when(r.created_at)}</td><td>${esc(r.bucket)}</td><td>${esc(prov[r.provider] ? prov[r.provider].name : r.provider)}</td><td class="small">${esc(r.query)}</td><td>${chip(r.status, r.error)}${r.error ? `<div class="small faint">${esc(r.error)}</div>` : ''}</td><td>${r.result_count}</td></tr>`).join('')}</tbody></table></div>` : '<p class="faint">No searches run yet.</p>'}</section></div>`;
    const f = document.getElementById('plan-form');
    f.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(f);
      const items = fd.getAll('sel').map((key) => { const [bid, i] = key.split('|'); const b = plan.buckets.find((x) => x.id === bid); const it = b.items[Number(i)];
        return { bucket: bid, provider: it.provider, query: it.query != null ? (fd.get(`q:${key}`) || it.query) : null, indicator: it.indicator || null }; });
      if (!items.length) { flash('<div class="notice warn">Select at least one search.</div>'); return; }
      await busy(document.getElementById('plan-run'), 'Searching', async () => {
        const r = await api(`/projects/${pid}/research/run`, { method: 'POST', pid, body: { items } });
        const okN = r.runs.filter((x) => x.status === 'OK').length;
        history.replaceState({}, '', `/projects/${pid}/research?tab=sources`); await load(pid); await VIEWS.research({ pid });
        flash(`<div class="notice ${okN ? 'ok' : 'warn'}"><b>${okN} of ${r.runs.length} searches returned results.</b><p>${r.runs.map((x) => `${esc(x.provider)} (${esc(x.bucket)}): ${esc(label(x.status))}${x.error ? `, ${esc(x.error)}` : ''}`).join('; ')}. Candidates are not evidence until you review them.</p></div>`);
      });
    });
  }

  function candFilter(c, s) {
    if (['REJECTED', 'FETCH_FAILED'].includes(c.state)) return 'excluded';
    if (c.state === 'EVIDENCE_ADDED') { const e = s.evidence.find((x) => x.id === c.evidence_id); return e && ['EXCERPT_MATCHED', 'STRUCTURED_DATUM'].includes(e.excerpt_status) ? 'verified' : 'context'; }
    return 'unreviewed';
  }
  function renderSources(body, pid, rs, plan) {
    const s = snap;
    const f = new URLSearchParams(location.search).get('f') || 'unreviewed';
    const groups = { unreviewed: 'Unreviewed', verified: 'Verified excerpt', context: 'Context only', excluded: 'Excluded' };
    const counts = Object.fromEntries(Object.keys(groups).map((k) => [k, rs.candidates.filter((c) => candFilter(c, s) === k).length]));
    const dirs = ((s.phase_runs.find((r) => r.phase === 'discover') || {}).report || {}).directions || [];
    const list = rs.candidates.filter((c) => candFilter(c, s) === f);
    body.innerHTML = `<div class="stack">
      <section class="panel"><header><h2>Inspect a page you found</h2></header>
        <form id="insp-form" class="grid2"><div class="field"><label for="i-url">Public page (https)</label><input id="i-url" name="url" type="url" required placeholder="https://"></div>
        <div class="field"><label for="i-q">Words to look for <span class="opt">(optional)</span></label><input id="i-q" name="query" maxlength="160" placeholder="e.g. students deadlines price"></div>
        <div class="field"><label for="i-b">Research bucket</label><select id="i-b" name="bucket">${plan.buckets.map((b) => `<option value="${b.id}">${esc(b.title)}</option>`).join('')}</select></div>
        <div class="field" style="align-self:end"><button class="btn secondary" id="insp-btn">Fetch and inspect</button></div></form>
        <p class="small muted">FounderOS fetches the page itself (public https only, private addresses blocked, every redirect re-checked) and offers passages that really appear on it.</p></section>
      <div class="tabs" role="tablist" aria-label="Filter sources">${Object.entries(groups).map(([k, n]) => `<button role="tab" aria-selected="${k === f}" data-f="${k}">${n}<span class="count">${counts[k]}</span></button>`).join('')}</div>
      ${list.length ? list.map((c) => sourceCard(c, dirs)).join('') : `<div class="empty"><p>${f === 'unreviewed' ? 'No unreviewed candidates. Run the plan or inspect a page.' : 'Nothing here.'}</p></div>`}</div>`;
    body.querySelectorAll('[data-f]').forEach((b) => b.onclick = () => { history.replaceState({}, '', `/projects/${pid}/research?tab=sources&f=${b.dataset.f}`); renderSources(body, pid, rs, plan); });
    const insp = document.getElementById('insp-form');
    insp.addEventListener('submit', async (e) => { e.preventDefault(); if (!insp.reportValidity()) return;
      await busy(document.getElementById('insp-btn'), 'Fetching', async () => { const c = await api(`/projects/${pid}/research/inspect`, { method: 'POST', pid, body: Object.fromEntries(new FormData(insp)) });
        await refreshSources(pid, plan); flash(c.state === 'FETCHED' ? `<div class="notice ok">Page inspected: ${c.fetch.passages.length} passages offered from the actual page text.</div>` : `<div class="notice error"><b>Could not fetch.</b><p>${esc(c.fetch && c.fetch.error)}</p></div>`); }); });
    body.querySelectorAll('[data-fetch]').forEach((b) => b.onclick = () => busy(b, 'Fetching', async () => { const c = await api(`/projects/${pid}/research/candidates/${b.dataset.fetch}/fetch`, { method: 'POST', pid }); await refreshSources(pid, plan);
      flash(c.state === 'FETCHED' ? '<div class="notice ok">Page inspected.</div>' : `<div class="notice warn"><b>Could not fetch the page.</b><p>${esc(c.fetch && c.fetch.error)}. It stays metadata only.</p></div>`); }));
    body.querySelectorAll('[data-reject]').forEach((b) => b.onclick = () => dialog({ title: 'Reject this source?', confirm: 'Reject', body: '<div class="field"><label for="rj">Why?</label><input id="rj" name="reason" required minlength="3" maxlength="300" placeholder="Off-topic, wrong country, too old…"></div>',
      onConfirm: async (fd) => { await api(`/projects/${pid}/research/candidates/${b.dataset.reject}/reject`, { method: 'POST', pid, body: { reason: fd.get('reason') } }); await refreshSources(pid, plan); } }));
    body.querySelectorAll('form[data-add]').forEach((form) => form.addEventListener('submit', async (e) => {
      e.preventDefault(); if (!form.reportValidity()) return;
      const fd = Object.fromEntries([...new FormData(form)].filter(([, v]) => String(v).trim()));
      fd.relevance_checks = collectRelevance(fd); fd.paste_confirm = !!fd.paste_confirm;
      await busy(form.querySelector('button[type=submit]'), 'Adding', async () => { const r = await api(`/projects/${pid}/research/candidates/${form.dataset.add}/add`, { method: 'POST', pid, body: fd }); await load(pid); await refreshSources(pid, plan);
        flash(`<div class="notice ${r.review_state === 'ACCEPTED_RELEVANT' ? 'info' : 'warn'}"><b>Added to the ledger: ${esc(label(r.excerpt_status))}, review ${esc(label(r.review_state || 'NOT_CHECKED').toLowerCase())}.</b><p>${esc(r.review_reason || '')}${r.duplicate_of ? ' Duplicate of an earlier source, so it is not counted twice.' : ''}${r.injection_flag ? ' It contains instruction-like text and is excluded.' : ''} Re-evaluate the criteria to use it.</p></div>`); });
    }));
  }
  async function refreshSources(pid, plan) { const rs = await api(`/projects/${pid}/research`, { pid }); await load(pid); renderSources(document.getElementById('tab-body'), pid, rs, plan); }

  function sourceCard(c, dirs) {
    const p = c.payload || {}, fx = c.fetch || {};
    const meta = [c.publisher || fx.meta && fx.meta.publisher, c.year && `published ${c.year}`, fx.meta && fx.meta.published_on && `dated ${fx.meta.published_on}`, p.geography, c.doi && `DOI ${c.doi}`].filter(Boolean);
    const cat = RUBRIC || { checks: [] };
    const typeOpts = Object.entries(SRC_TYPE).filter(([k]) => k !== 'FOUNDER_CUSTOMER_RESEARCH').map(([k, v]) => `<option value="${k}" ${(c.provider === 'crossref' || c.provider === 'openalex') && k === 'ACADEMIC_PASSAGE' ? 'selected' : ''}>${esc(v)}</option>`).join('');
    const addForm = (use, extra) => `<details class="adv"><summary>Add to ledger…</summary><form data-add="${c.id}"><input type="hidden" name="use" value="${use}">${extra}
      <div class="field"><label>Claim this bears on</label><input name="claim" required minlength="8" maxlength="800" placeholder="e.g. Small Cairo restaurants throw away unsold ingredients every week"><p class="help">${esc(CLAIM_HELP)}</p></div>
      <div class="grid2"><div class="field"><label>Team check it informs <span class="opt">(needed for the criteria matrix)</span></label><select name="subcriterion_id">${checkOptions(cat, null, p.subcriterion_id)}</select></div>
      <div class="field"><label>What kind of source is it?</label><select name="source_type"><option value="">Not sure</option>${typeOpts}</select></div>
      <div class="field"><label>Dimension</label><select name="dimension">${Object.entries(DIM).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></div>
      <div class="field"><label>Does it support or challenge the claim?</label><select name="direction"><option value="UNSURE">Unsure</option><option value="SUPPORTS">Supports</option><option value="CONTRADICTS">Challenges</option></select></div>
      <div class="field"><label>Geography it describes</label><input name="geography" maxlength="120" value="${esc(p.geography || '')}" placeholder="e.g. Egypt"></div>
      <div class="field"><label>Candidate direction <span class="opt">(optional)</span></label><select name="direction_id"><option value="">None</option>${dirs.map((d) => `<option value="${esc(d.id)}">${esc(d.id)}: ${esc(d.name)}</option>`).join('')}</select></div></div>
      ${relevanceFields('c' + c.id.slice(0, 6))}
      <button class="btn small" type="submit">Add to ledger</button></form></details>`;
    let inner = '';
    if (c.state === 'FETCHED' && fx.passages) {
      inner = `${fx.paywall_suspected ? '<div class="notice warn small">This looked like a paywall or a very short page. Read the full source yourself.</div>' : ''}
        ${fx.truncated ? `<div class="notice warn small">${esc(fx.truncation_note)}</div>` : ''}${fx.reserved_domain ? '<div class="notice error small">This is a reserved documentation domain (like example.com). Its text is placeholder text and is always excluded.</div>' : ''}
        <p class="small muted">Passages from the fetched page, ordered by word overlap (a rough heuristic). Pick one; FounderOS stores it only if it is really on the page.</p>
        <form data-add="${c.id}"><input type="hidden" name="use" value="PASSAGE">${fx.passages.map((ps, i) => `<label class="passage check"><input type="radio" name="excerpt" value="${esc(ps.text)}" ${i === 0 && !ps.injection_flag ? 'checked' : ''} required><span>${esc(ps.text)}${ps.injection_flag ? ' <span class="chip stop">Instruction-like text</span>' : ''}</span></label>`).join('')}
        ${addForm('PASSAGE', '').replace(/^<details[^>]*><summary>[^<]*<\/summary><form[^>]*><input[^>]*>/, '').replace(/<\/form><\/details>$/, '')}</form>`;
    } else if (c.state === 'FETCH_FAILED') {
      inner = `<p class="small">${chip(fx.error_code || 'FETCH_FAILED')} ${esc(fx.error || '')}</p>${fx.advice ? `<p class="small muted">${esc(fx.advice)}</p>` : ''}
        ${fx.error_code === 'BLOCKED_ADDRESS' ? '' : `<div class="row"><button class="btn quiet small" data-fetch="${c.id}">Try again</button></div>
        <details class="adv"><summary>Paste the passage yourself</summary>${addForm('FOUNDER_PASTE', `<div class="field"><label>Passage you copied from this page</label><textarea name="excerpt" rows="3" required minlength="12" maxlength="1200"></textarea></div>
          <label class="check small"><input type="checkbox" name="paste_confirm" required> I copied this from the page above myself. It will be labelled “pasted by you, not verified”.</label>`).replace(/^<details[^>]*><summary>[^<]*<\/summary>/, '').replace(/<\/details>$/, '')}</details>`}
        ${p.abstract ? `<details class="adv"><summary>Provider abstract (metadata only)</summary><blockquote>${esc(p.abstract)}</blockquote>${addForm('ABSTRACT_METADATA', '<p class="small muted">Added as metadata only: kept as context, never counted in scores.</p>')}</details>` : ''}`;
    } else if (c.state === 'CANDIDATE_METADATA') {
      inner = `${p.abstract ? `<p class="small muted">Provider abstract, metadata only:</p><blockquote>${esc(p.abstract.slice(0, 500))}${p.abstract.length > 500 ? '…' : ''}</blockquote>` : '<p class="small faint">Title and metadata only. Inspect the page to see what it actually says.</p>'}
        <div class="row">${c.url ? `<button class="btn secondary small" data-fetch="${c.id}">Inspect the page</button>` : ''}<button class="btn quiet small" data-reject="${c.id}">Reject</button></div>
        ${p.abstract ? `<details class="adv"><summary>Add the abstract as context only</summary>${addForm('ABSTRACT_METADATA', '')}</details>` : ''}`;
    } else if (c.state === 'EVIDENCE_ADDED') {
      inner = `<p class="small">In the ledger as <a href="/projects/${snap.project.id}/research?ev=${c.evidence_id}" data-link>${short(c.evidence_id)}</a>.</p>`;
    } else if (c.state === 'REJECTED') inner = `<p class="small">Rejected: ${esc(c.reject_reason)}</p>`;
    if (c.provider === 'worldbank' && c.state === 'FETCHED') {
      inner = `<blockquote>${esc(p.datum)}</blockquote><p class="small muted">${esc(p.limitation)}</p><div class="row"><button class="btn quiet small" data-reject="${c.id}">Reject</button></div>${addForm('STRUCTURED_DATUM', '')}`;
    }
    return `<article class="source" id="cand-${c.id}"><div class="row" style="justify-content:space-between"><span class="title" data-k="t">${esc((fx.meta && fx.meta.title && (!c.title || c.title === c.url)) ? fx.meta.title : (c.title || c.url))}</span>${chip(c.provider === 'worldbank' && c.state === 'FETCHED' ? 'STRUCTURED_DATUM' : c.state)}</div>
      ${c.url ? `<div class="url"><a href="${esc(fx.final_url || c.url)}" target="_blank" rel="noopener noreferrer">${esc(fx.final_url || c.url)}</a></div>` : ''}
      <div class="meta"><span>${esc((PROV_NAMES[c.provider] || c.provider))}</span>${meta.map((m) => `<span>${esc(m)}</span>`).join('')}${fx.retrieved_at ? `<span>fetched ${when(fx.retrieved_at)}</span>` : ''}</div>${inner}</article>`;
  }
  const PROV_NAMES = { crossref: 'Crossref metadata', openalex: 'OpenAlex metadata', worldbank: 'World Bank Indicators', founder_url: 'Page you supplied', founder_manual: 'Entered by you' };

  function renderLedger(body, pid, focus) {
    const s = snap;
    const q = (s.criteria.discover && s.criteria.discover.evaluation && s.criteria.discover.evaluation.quality) || {};
    body.innerHTML = s.evidence.length ? `<section class="panel"><header><h2>Evidence ledger</h2><span class="small muted">Immutable; add a challenging record instead of editing</span></header>
      <ul class="plain">${s.evidence.map((e) => { const g = q[e.id];
        return `<li id="ev-${e.id}" ${focus === e.id ? 'style="background:var(--accent-tint);padding-left:8px"' : ''}><div class="row" style="justify-content:space-between"><b>${esc(e.claim)}</b><span class="row">${e.review_state ? chip(e.review_state, e.review_reason) : ''}${g ? chip(g.grade, g.exclusion || g.flags.join(' ')) : ''}${chip(e.excerpt_status !== 'NOT_APPLICABLE' ? e.excerpt_status : e.independence === 'FOUNDER_REPORTED_NOT_INDEPENDENTLY_VERIFIED' ? 'DIRECT_STATEMENT' : 'UNKNOWN')}</span></div>
          <div class="meta small muted">${esc(e.kind.replace(/_/g, ' ').toLowerCase())}, ${esc(DIM[e.dimension] || e.dimension)}, ${e.direction === 'SUPPORTS' ? 'supports' : e.direction === 'CONTRADICTS' ? 'challenges' : 'direction unsure'}${e.direction_id ? `, direction ${esc(e.direction_id)}` : ''}${e.criterion_id ? `, criterion ${esc(e.criterion_id)}` : ''}${e.subcriterion_id ? `, check <a href="/projects/${pid}/research?tab=matrix&check=${esc(e.subcriterion_id)}" data-link>${esc(e.subcriterion_id)}</a>` : ''}${e.source_type ? `, ${esc((SRC_TYPE[e.source_type] || e.source_type).toLowerCase())}` : ''}, id ${short(e.id)}</div>
          ${e.review_reason ? `<div class="small muted">Review: ${esc(e.review_reason)}</div>` : ''}
          ${e.excerpt ? `<blockquote>${esc(e.excerpt)}</blockquote>` : ''}
          ${e.source_url ? `<div class="url small"><a href="${esc(e.final_url || e.source_url)}" target="_blank" rel="noopener noreferrer">${esc(e.final_url || e.source_url)}</a> ${esc([e.publisher, e.published_on, e.geography].filter(Boolean).join(', '))}${e.retrieved_at ? `, retrieved ${when(e.retrieved_at)}` : ''}</div>` : ''}
          ${e.method ? `<div class="small">${esc(e.method)}: n=${esc(e.sample_size)}${e.positives != null ? `, ${esc(e.positives)} positive` : ''}, ${esc(e.collected_from)}${e.collected_to ? ` to ${esc(e.collected_to)}` : ''}. Founder-reported, not independently verified.</div>` : ''}
          ${g && g.flags.length ? `<div class="small faint">${g.flags.map(esc).join(' ')}</div>` : ''}${g && g.exclusion ? `<div class="small" style="color:var(--stop)">Not counted: ${esc(g.exclusion)}</div>` : ''}
          ${!g ? `<div class="small faint">${esc(e.limitations)}</div>` : ''}</li>`; }).join('')}</ul></section>`
      : '<div class="empty"><h2>The ledger is empty</h2><p>Add verified passages from Sources, or record your own customer research. With no evidence, every scored criterion stays unknown and the verdict is “Needs evidence”.</p></div>';
    if (focus) { const el = document.getElementById(`ev-${focus}`); if (el) el.scrollIntoView({ block: 'center' }); }
  }

  function renderCustomers(body, pid) {
    const today = new Date().toISOString().slice(0, 10);
    body.innerHTML = `<section class="panel"><header><h2>Record research you ran yourself</h2></header>
      <p class="small muted">Interviews, sign-ups or usage you observed with real people who agreed to take part. FounderOS never contacts anyone and never invents participants. Everything here stays labelled “founder-reported, not independently verified”.</p>
      <form id="cust-form"><div class="grid2"><div class="field"><label for="c-kind">What you observed</label><select id="c-kind" name="kind"><option value="CUSTOMER_STATEMENT">What people said (interviews, surveys)</option><option value="CUSTOMER_BEHAVIOR">What people did (opt-ins, sign-ups, use)</option></select><p class="help">Statements help you understand the problem but never count as demand.</p></div>
      <div class="field"><label for="c-dim">Dimension</label><select id="c-dim" name="dimension">${Object.entries(DIM).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></div></div>
      <div class="field"><label for="c-claim">Finding</label><input id="c-claim" name="claim" required minlength="8" maxlength="800" placeholder="e.g. 4 of 12 students joined the waitlist"></div>
      <div class="grid3"><div class="field"><label for="c-method">Method</label><input id="c-method" name="method" required minlength="10" maxlength="600" placeholder="12 in-person interviews about past deadlines"></div>
      <div class="field"><label for="c-n">Relevant participants</label><input id="c-n" name="sample_size" type="number" min="1" required></div>
      <div class="field"><label for="c-pos">Positive responses <span class="opt">(optional)</span></label><input id="c-pos" name="positives" type="number" min="0"></div>
      <div class="field"><label for="c-from">Collected from</label><input id="c-from" name="collected_from" type="date" max="${today}" required></div>
      <div class="field"><label for="c-to">Collected to <span class="opt">(optional)</span></label><input id="c-to" name="collected_to" type="date" max="${today}"></div>
      <div class="field"><label for="c-dir">Supports or challenges?</label><select id="c-dir" name="direction"><option value="UNSURE">Unsure</option><option value="SUPPORTS">Supports</option><option value="CONTRADICTS">Challenges</option></select></div></div>
      <div class="grid2"><div class="field"><label for="c-ps">Positive signals <span class="opt">(optional)</span></label><input id="c-ps" name="positive_signals" maxlength="1000"></div><div class="field"><label for="c-ns">Negative signals <span class="opt">(optional)</span></label><input id="c-ns" name="negative_signals" maxlength="1000"></div></div>
      <label class="check"><input type="checkbox" name="consent_confirmed" required> These were real people who knowingly agreed to take part. Nothing here is invented or paid for.</label>
      <div class="row" style="margin-top:12px"><button class="btn secondary" id="cust-btn">Add to ledger</button></div></form></section>`;
    const f = document.getElementById('cust-form');
    f.addEventListener('submit', async (e) => { e.preventDefault(); if (!f.reportValidity()) return;
      const d = Object.fromEntries([...new FormData(f)].filter(([, v]) => String(v).trim()));
      d.consent_confirmed = !!d.consent_confirmed; d.sample_size = Number(d.sample_size); if (d.positives) d.positives = Number(d.positives);
      await busy(document.getElementById('cust-btn'), 'Saving', async () => { await api(`/projects/${pid}/evidence`, { method: 'POST', pid, body: d }); await load(pid); f.reset(); ok('Recorded as founder-reported evidence.'); });
    });
  }

  // ---------------- Demand tests
  VIEWS.experiments = async ({ pid }) => {
    const s = snap;
    crumb(s.project.name, 'Demand tests');
    if (!s.brief) { main.innerHTML = `${head('Demand tests', '')}<div class="empty"><h2>Refine the brief first</h2><a class="btn" href="/projects/${pid}/brief" data-link>Go to the brief</a></div>`; return; }
    let sug = null;
    try { sug = await api(`/projects/${pid}/experiments/suggest`, { pid }); } catch (e) { /* shown below */ }
    const series = {};
    s.experiments.forEach((x) => (series[x.id] = series[x.id] || []).push(x));
    const accepted = s.evidence.filter((e) => !e.duplicate_of && !e.injection_flag);
    const dirs = ((s.phase_runs.find((r) => r.phase === 'discover') || {}).report || {}).directions || [];
    const draft = store.get(`founderos_exp_${pid}`, null);
    const minors = /\b(children|kids|child|k-?12|minors?|pupils?|teen(ager)?s?|under[- ]18|schoolchildren)\b/i.test(`${s.project.original_idea} ${s.brief.payload.target_customers || ''}`);
    main.innerHTML = `${head('Demand tests', 'The only way to learn whether people want this: watch what they do. You fix the pass mark before collecting any result, and code reads the result against it.')}
      <div class="cols"><div class="stack">
        ${sug && sug.kind === 'PROPOSED_EXPERIMENT_NEEDS_FOUNDER_APPROVAL' ? `<section class="panel"><header><h2>Suggested next test</h2>${chip('DRAFT', 'A suggestion, not a plan you approved')}</header>
          <p>${esc(sug.hypothesis)}</p><dl class="facts small"><dt>Who</dt><dd>${esc(sug.target_segment)}</dd><dt>What you measure</dt><dd>${esc(sug.metric)}</dd><dt>Consent</dt><dd>${esc(sug.consent_method)}</dd>
          <dt>You do</dt><dd>${sug.founder_actions.map(esc).join(' ')}</dd><dt>Time and cost</dt><dd>${esc(sug.timebox_estimate)}; ${esc(sug.cost_estimate)}</dd>
          <dt>Suggested pass mark</dt><dd>${sug.suggested_criteria.success_threshold_pct}% of at least ${sug.suggested_criteria.min_sample} people; stop signal at ${sug.suggested_criteria.adverse_threshold_pct}% or below. <span class="faint">${esc(sug.suggested_criteria.label)}</span></dd>
          <dt>Why this one</dt><dd>${esc(sug.risk_ranking_note || '')}</dd></dl><button class="btn secondary small" id="use-sug" style="margin-top:10px">Start a draft from this</button></section>`
          : sug && sug.kind === 'RUN_LOCKED_EXPERIMENT' ? `<div class="notice info"><b>Run your locked test.</b><p>${esc(sug.instruction)}</p></div>` : ''}
        <section class="panel" id="exp-panel"><header><h2 id="exp-title">Design a test</h2><span class="small muted">Nothing is evidence until results arrive</span></header>
          <form id="exp-form"><input type="hidden" name="_revise">
            <div class="field"><label for="x-h">Hypothesis</label><textarea id="x-h" name="hypothesis" required minlength="10" maxlength="600" rows="2"></textarea></div>
            <div class="grid2"><div class="field"><label for="x-seg">Who you will test with</label><input id="x-seg" name="target_segment" required minlength="3" maxlength="300"></div>
            <div class="field"><label for="x-m">What people must do (the metric)</label><input id="x-m" name="metric" required minlength="10" maxlength="400" placeholder="Share who voluntarily join the waitlist"><p class="help">An action, not an opinion. “Would you use it?” does not pass.</p></div></div>
            <div class="grid3"><div class="field"><label for="x-n">Minimum people</label><input id="x-n" name="min_sample" type="number" min="1" required value="10"></div>
            <div class="field"><label for="x-s">Pass mark (%)</label><input id="x-s" name="success_threshold_pct" type="number" min="1" max="100" required value="30"></div>
            <div class="field"><label for="x-a">Stop signal at or below (%)</label><input id="x-a" name="adverse_threshold_pct" type="number" min="0" max="99" required value="10"></div>
            <div class="field"><label for="x-o">Where the pass mark comes from</label><select id="x-o" name="threshold_origin" required><option value="TEAM_ASSUMPTION">My assumption (labelled as such)</option><option value="CITED_BENCHMARK">A benchmark in my ledger</option></select></div>
            <div class="field"><label for="x-b">Benchmark evidence <span class="opt">(if cited)</span></label><select id="x-b" name="benchmark_evidence_id"><option value="">None</option>${accepted.map((e) => `<option value="${e.id}">${short(e.id)}: ${esc(e.claim.slice(0, 60))}</option>`).join('')}</select></div>
            <div class="field"><label for="x-w">Time window (days)</label><input id="x-w" name="time_window_days" type="number" min="1" max="365" required value="7"></div>
            <div class="field"><label for="x-c">Cost (number)</label><input id="x-c" name="cost_estimate" required value="0" maxlength="120"><p class="help">Checked against your budget (${esc(s.brief.payload.budget || 'unknown')}).</p></div>
            <div class="field"><label for="x-d">Direction tested <span class="opt">(optional)</span></label><select id="x-d" name="direction_id"><option value="">None</option>${dirs.map((d) => `<option value="${esc(d.id)}">${esc(d.id)}: ${esc(d.name)}</option>`).join('')}</select></div>
            <div class="field"><label for="x-cl">Claim tested</label><select id="x-cl" name="claim_id"><option value="C-DEM">Demand (C-DEM)</option><option value="C-PROB">Problem (C-PROB)</option><option value="C-VIAB">Willingness to pay (C-VIAB)</option><option value="C-COMP">Reason to switch (C-COMP)</option></select></div></div>
            <div class="field"><label for="x-con">How people consent</label><input id="x-con" name="consent_method" required minlength="10" maxlength="600" value="I explain who I am and why I ask; joining is optional and they can withdraw."></div>
            <div class="field"><label for="x-act">What you will do yourself</label><textarea id="x-act" name="founder_actions" required minlength="10" maxlength="1200" rows="2"></textarea></div>
            <div class="field"><label for="x-pv">If it fails, which direction would you test next? <span class="opt">(optional)</span></label><input id="x-pv" name="pivot_alternative" maxlength="400"></div>
            <div class="grid2"><div class="field"><label for="x-rec">How you will recruit people</label><input id="x-rec" name="recruitment_method" maxlength="600" placeholder="e.g. Visit 15 restaurants in Nasr City in person"></div>
            <div class="field"><label for="x-exc">Who you will exclude, and why <span class="opt">(optional)</span></label><input id="x-exc" name="exclusions" maxlength="600" placeholder="e.g. Friends and family; chains with 50+ staff"></div></div>
            <div class="field"><label for="x-lim">Known limitations <span class="opt">(optional)</span></label><input id="x-lim" name="limitations" maxlength="600" placeholder="e.g. One neighbourhood only; small sample"></div>
            ${minors ? `<div class="notice warn small"><b>This venture involves children.</b><p>Test only with consenting adults (parents, guardians, teachers) in a research-only setting. Never recruit, message or survey children. FounderOS collects no personal data about anyone.</p>
              <label class="check"><input type="checkbox" name="participants_adults_only"> Only consenting adults will take part; no child will be contacted.</label></div>` : '<input type="hidden" name="participants_adults_only" value="">'}
            <label class="check"><input type="checkbox" name="critical" checked> This test checks a critical assumption: a clear miss at the stop signal should mean stop or pivot.</label>
            <label class="check"><input type="checkbox" name="simulated"> This is a demo or simulation, not a real test. It will be marked <b>SIMULATED / NOT COUNTED</b> and its result can never count as demand.</label>
            <div class="row" style="margin-top:12px"><button class="btn secondary" id="exp-save">Save draft</button><span class="small muted">Drafts are checked (V05) before you can lock them.</span></div></form></section>
        ${Object.values(series).reverse().map((rows) => expSeries(rows, pid)).join('') || '<div class="empty"><p>No tests yet. A planned test is never evidence.</p></div>'}
      </div>
      ${nextPanel('What happens next', ['Save a draft and fix anything the design check flags.', 'Lock it: the pass mark is frozen with a timestamp and hash.', 'Run it yourself, then enter the real result. Code reads it: hit, near miss, clear miss or too little data.', 'Then open Decision to run validation.'])}
      </div>
      ${actionbar([`/projects/${pid}/research`, 'Research'], s.phase_runs.some((r) => r.phase === 'discover' && r.state === 'APPROVED') ? { href: `/projects/${pid}/decision`, label: 'Continue to decision' } : { disabled: true, label: 'Continue to decision', reason: 'Approve research at the Discover gate first.' })}`;
    const f = document.getElementById('exp-form');
    const fill = (o) => { for (const [k, v] of Object.entries(o || {})) { const el = f.elements[k]; if (!el || v == null) continue; if (el.type === 'checkbox') el.checked = !!v; else el.value = v; } };
    if (draft) fill(draft);
    f.addEventListener('input', () => { const d = Object.fromEntries(new FormData(f)); d.critical = f.elements.critical.checked; d.simulated = f.elements.simulated.checked; store.set(`founderos_exp_${pid}`, d); });
    const us = document.getElementById('use-sug');
    if (us) us.onclick = () => { fill({ hypothesis: sug.hypothesis.slice(0, 600), target_segment: sug.target_segment.slice(0, 300), metric: sug.metric.slice(0, 400), consent_method: sug.consent_method.slice(0, 600),
      founder_actions: sug.founder_actions.join(' ').slice(0, 1200), min_sample: sug.suggested_criteria.min_sample, success_threshold_pct: sug.suggested_criteria.success_threshold_pct,
      adverse_threshold_pct: sug.suggested_criteria.adverse_threshold_pct, time_window_days: sug.suggested_criteria.time_window_days, claim_id: sug.claim_id, cost_estimate: '0' }); f.elements.hypothesis.focus(); };
    f.addEventListener('submit', async (e) => {
      e.preventDefault(); if (!f.reportValidity()) return;
      const d = Object.fromEntries([...new FormData(f)].filter(([, v]) => String(v).trim()));
      const rev = d._revise; delete d._revise;
      for (const k of ['min_sample', 'success_threshold_pct', 'adverse_threshold_pct', 'time_window_days']) d[k] = Number(d[k]);
      d.critical = f.elements.critical.checked; d.simulated = f.elements.simulated.checked;
      d.participants_adults_only = !!(f.elements.participants_adults_only && f.elements.participants_adults_only.checked); d.dimension = d.claim_id === 'C-PROB' ? 'desirability' : d.claim_id === 'C-VIAB' ? 'viability' : d.claim_id === 'C-COMP' ? 'competition' : 'demand';
      d.timebox_estimate = `ESTIMATE: ${d.time_window_days} days`;
      await busy(document.getElementById('exp-save'), 'Saving', async () => {
        const r = await api(rev ? `/projects/${pid}/experiments/${rev}/revise` : `/projects/${pid}/experiments`, { method: 'POST', pid, body: d });
        store.del(`founderos_exp_${pid}`); await render(); ok(`Draft saved (version ${r.version}). ${r.notice}`);
      });
    });
    main.querySelectorAll('[data-lock]').forEach((b) => b.onclick = () => {
      const x = s.experiments.find((e) => e.id === b.dataset.lock && e.version === Number(b.dataset.v));
      dialog({ title: 'Lock this test?', confirm: 'Lock and timestamp', body: `<p>Locking freezes the pass mark (${x.payload.success_threshold_pct}% of at least ${x.payload.min_sample}), the stop signal (${x.payload.adverse_threshold_pct}%), the time window and where the number comes from (${label(x.payload.threshold_origin)}). Results must be collected after now. Changing anything later creates a new version and retires its results.</p>
        <label class="check"><input type="checkbox" required name="c"> I have not collected any results for this test yet.</label>`,
        onConfirm: async () => { await api(`/projects/${pid}/experiments/${x.id}/lock`, { method: 'POST', pid, body: { version: x.version, criteria_hash: x.criteria_hash, confirm: 'I_PREREGISTER_THESE_CRITERIA_BEFORE_COLLECTING_RESULTS' } }); await render(); ok('Locked. Run the test, then enter the real result.'); } });
    });
    main.querySelectorAll('[data-revise]').forEach((b) => b.onclick = () => { const x = s.experiments.filter((e) => e.id === b.dataset.revise).pop(); fill({ ...x.payload, _revise: x.id });
      document.getElementById('exp-title').textContent = `Edit as version ${x.version + 1}`; f.scrollIntoView({ behavior: 'smooth' }); flash(`<div class="notice warn">Saving creates version ${x.version + 1}. Version ${x.version} and any result against it stop counting.</div>`); });
    main.querySelectorAll('form[data-result]').forEach((rf) => rf.addEventListener('submit', async (e) => {
      e.preventDefault(); if (!rf.reportValidity()) return;
      const x = s.experiments.find((ex) => ex.id === rf.dataset.result && ex.status === 'LOCKED');
      const d = Object.fromEntries([...new FormData(rf)].filter(([, v]) => String(v).trim()));
      d.version = x.version; d.criteria_hash = x.criteria_hash; d.sample_size = Number(d.sample_size); d.positives = Number(d.positives); d.consent_confirmed = !!d.consent_confirmed;
      await busy(rf.querySelector('button'), 'Reading the result', async () => { const r = await api(`/projects/${pid}/experiments/${x.id}/result`, { method: 'POST', pid, body: d }); await render(); ok(`${label(r.reading)}: ${r.explanation}`); });
    }));
  };

  function expSeries(rows, pid) {
    const x = rows[rows.length - 1], p = x.payload, today = new Date().toISOString().slice(0, 10);
    const dc = x.design_check;
    const resultEv = x.result_evidence_id && snap.evidence.find((e) => e.id === x.result_evidence_id);
    return `<section class="panel ${p.simulated ? 'simulated' : ''}"><header><h2>${esc(p.hypothesis.slice(0, 90))}</h2><span class="row">${p.simulated ? chip('SIMULATED_NOT_COUNTED', 'A demo; never counts as demand') : ''}${chip(x.status)}</span></header>
      ${p.simulated ? '<div class="notice error small"><b>SIMULATED / NOT COUNTED.</b> This is a demo. Its result is kept apart from real results and never counts toward any verdict.</div>' : ''}
      <dl class="facts small"><dt>Version</dt><dd>${x.version}${rows.length > 1 ? ` (earlier: ${rows.slice(0, -1).map((r) => `v${r.version} ${label(r.status).toLowerCase()}`).join(', ')})` : ''}</dd>
      <dt>Metric</dt><dd>${esc(p.metric)}</dd><dt>Pass mark</dt><dd>${p.success_threshold_pct}% of at least ${p.min_sample} people within ${p.time_window_days || '?'} days; stop signal ≤ ${p.adverse_threshold_pct}%; near miss within ${Math.round((p.near_miss_band || 0) * 100)}% below</dd>
      <dt>Number comes from</dt><dd>${esc(label(p.threshold_origin || 'NOT_SET'))}${p.benchmark_evidence_id ? ` (evidence ${short(p.benchmark_evidence_id)})` : ''}</dd>
      <dt>Recruitment</dt><dd>${unknownText(p.recruitment_method)}</dd><dt>Exclusions</dt><dd>${unknownText(p.exclusions)}</dd><dt>Consent</dt><dd>${unknownText(p.consent_method)}</dd>
      <dt>Limitations</dt><dd>${unknownText(p.limitations)}</dd>
      ${x.locked_at ? `<dt>Locked</dt><dd>${when(x.locked_at)}</dd>` : '<dt>Locked</dt><dd><span class="faint">Not locked: a plan, not a result</span></dd>'}</dl>
      ${x.status === 'DRAFT' ? `<div class="gate-actions"><h3>Design check (V05)</h3><ul class="plain small">${Object.entries(dc.items).map(([k, v]) => `<li>${chip(v.ok ? 'PASS' : 'FAIL')} ${esc(k.replace(/_/g, ' '))}${v.ok ? '' : `: ${esc(v.why)}`}</li>`).join('')}</ul>
        <div class="row">${dc.status === 'PASS' ? `<button class="btn" data-lock="${x.id}" data-v="${x.version}">Lock this test</button>` : '<span class="why-disabled">Fix the failing checks to lock.</span>'}<button class="btn quiet small" data-revise="${x.id}">Edit</button></div></div>` : ''}
      ${x.status === 'LOCKED' && !x.result_evidence_id ? `<form data-result="${x.id}" class="gate-actions"><h3>Enter the real result</h3><div class="grid3">
        <div class="field"><label>People who took part</label><input name="sample_size" type="number" min="1" required></div><div class="field"><label>Of them, did the action</label><input name="positives" type="number" min="0" required></div>
        <div class="field"><label>Method</label><input name="method" required minlength="10" maxlength="600" placeholder="Waitlist form shared in 2 lectures"></div>
        <div class="field"><label>Collected from</label><input name="collected_from" type="date" min="${(x.locked_at || '').slice(0, 10)}" max="${today}" required></div><div class="field"><label>Collected to</label><input name="collected_to" type="date" max="${today}" required></div>
        <div class="field"><label>Negative signals <span class="opt">(optional)</span></label><input name="negative_signals" maxlength="1000"></div>
        <div class="field"><label>How people were recruited</label><input name="recruitment_method" required minlength="5" maxlength="600" value="${esc(p.recruitment_method || '')}"></div>
        <div class="field"><label>Who was excluded <span class="opt">(optional)</span></label><input name="exclusions" maxlength="600" value="${esc(p.exclusions || '')}"></div>
        <div class="field"><label>Limitations <span class="opt">(optional)</span></label><input name="limitations" maxlength="600"></div></div>
        <label class="check"><input type="checkbox" name="consent_confirmed" required> Real participants who consented. Nothing invented.</label>
        <div class="row" style="margin-top:10px"><button class="btn">Submit result</button><button type="button" class="btn quiet small" data-revise="${x.id}">Change the test (new version)</button></div></form>` : ''}
      ${x.reading ? `<div class="gate-actions"><p>${chip(x.reading)} ${esc(resultEv ? `${resultEv.positives} of ${resultEv.sample_size} people did the action (${resultEv.rate_pct}%)` : '')}</p>
        ${resultEv ? (() => { let m = {}; try { m = JSON.parse(resultEv.meta_json || '{}'); } catch (e) { m = {}; } return `<dl class="facts small"><dt>Denominator</dt><dd>${esc(resultEv.sample_size)}</dd><dt>Numerator</dt><dd>${esc(resultEv.positives)}</dd>
          <dt>Dates</dt><dd>${esc(resultEv.collected_from)} to ${esc(resultEv.collected_to)}</dd><dt>Consent</dt><dd>${resultEv.consent_confirmed ? 'Confirmed by you' : 'Not confirmed'}</dd>
          <dt>Recruitment</dt><dd>${unknownText(m.recruitment_method)}</dd><dt>Exclusions</dt><dd>${unknownText(m.exclusions)}</dd>
          <dt>Locked pass mark / stop</dt><dd>${esc(p.success_threshold_pct)}% / ${esc(p.adverse_threshold_pct)}% (${esc(label(p.threshold_origin || 'NOT_SET'))})</dd><dt>Limitations</dt><dd>${unknownText(m.limitations)}</dd></dl>`; })() : ''}<p class="small muted">${esc(resultEv ? resultEv.limitations : '')}</p>
        <a href="/projects/${pid}/research?ev=${x.result_evidence_id}" data-link class="small">See it in the ledger</a> <button class="btn quiet small" data-revise="${x.id}">Repeat with new criteria</button></div>` : ''}
    </section>`;
  }

  // ---------------- Decision
  VIEWS.decision = async ({ pid }) => {
    const s = snap;
    crumb(s.project.name, 'Decision');
    const disc = s.phase_runs.find((r) => r.phase === 'discover');
    const val = s.phase_runs.find((r) => r.phase === 'validate');
    const canRun = disc && disc.state === 'APPROVED' && !s.current.stopped && !(val && ['PENDING_APPROVAL', 'APPROVED'].includes(val.state));
    const why = !disc || disc.state !== 'APPROVED' ? 'Approve research at the Discover gate first.' : s.current.stopped ? 'This venture is stopped.' : 'Decide on the current run first, or choose Revise to run again.';
    const runBtn = `<button class="btn ${val ? 'secondary' : ''}" id="val-run" ${canRun ? '' : 'disabled'}>${val ? 'Run validation again' : 'Run validation'}</button>${canRun ? '' : `<span class="why-disabled">${esc(why)}</span>`}`;
    if (!val) {
      main.innerHTML = `${head('Decision', 'Validation reads your ledger and locked tests, code computes the verdict, and the validation agent explains it.')}
        <div class="empty"><h2>No validation yet</h2><p>With no customer behaviour or locked-test result, the honest verdict will be “Needs evidence”. That is not a judgement that the idea is bad.</p><div class="row">${runBtn}</div></div>`;
      wireVal(); return;
    }
    const g = val.gate, r = val.report, pp = s.passport;
    const tn = { NEEDS_EVIDENCE: 'hold', CONTINUE_TESTING: 'clear', PIVOT: 'hold', STOP_DO_NOT_LAUNCH: 'stop', BLOCK_DO_NOT_LAUNCH: 'stop' }[g.verdict] || 'unknown';
    const evLink = (id) => `<a href="/projects/${pid}/research?ev=${id}" data-link>${short(id)}</a>`;
    const ids = (a) => a && a.length ? a.map(evLink).join(', ') : '<span class="faint">none</span>';
    const dec = pp.founder_decision;
    main.innerHTML = `${head('Decision passport', `Validation v${val.version}, brief v${val.brief_version}, ${when(val.created_at)}.`, `<div class="row no-print">${runBtn}<button class="btn quiet" id="print">Print or save as PDF</button></div>`)}
      ${val.invalidated_reason ? `<div class="notice warn">This passport is out of date: ${esc(val.invalidated_reason)}. Run validation again.</div>` : ''}
      <div class="cols"><div class="stack">
        <section class="gate" data-tone="${tn}" aria-labelledby="vg"><div class="gate-body"><div class="gate-kicker">Verdict computed by code, not by the model (code ${esc(g.verdict)})</div>
          <p class="verdict" id="vg">${esc(label(g.verdict))}</p>
          ${g.explanation ? `<ul class="why plain">${g.explanation.lines.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : `<p class="why">${esc(g.headline)}</p>`}
          <p><b>If you continue:</b> ${esc(g.recommendation)}</p>
          ${(g.simulated_results_not_counted || []).length ? `<p class="small">${chip('SIMULATED_NOT_COUNTED')} ${g.simulated_results_not_counted.length} simulated test(s) exist and are not counted.</p>` : ''}
          <p class="small muted">Allows: continue research ${g.permissions.continue_research ? 'yes' : 'no'}; build no; launch no; any external action no. ${esc(g.never)}</p>
          ${gateButtons({ ...val, phase: 'validate' }, pid, g.verdict)}
          ${dec ? `<p class="small">Your decision: ${chip(dec.action === 'APPROVE' ? 'APPROVED' : dec.action === 'STOP' ? 'STOPPED' : dec.action + '_REQUESTED')} ${when(dec.created_at)}${dec.feedback ? `, “${esc(dec.feedback)}”` : ''}${dec.acknowledged_risk ? ' (you chose a different course than the gate)' : ''}.</p>` : ''}
        </div></section>
        <section class="panel"><header><h2>Five dimensions</h2><span class="small muted">Click an id to see the exact evidence</span></header><div class="table-wrap"><table><thead><tr><th>Dimension</th><th>Status</th><th>Supported by</th><th>Challenged by</th><th>Note</th></tr></thead><tbody>
          ${Object.values(g.matrix).map((m) => `<tr><td><b>${esc(m.label)}</b></td><td>${chip(m.status)}${m.evidence_classes && m.evidence_classes.length ? `<div class="small faint">${esc(m.evidence_classes.map((k) => label(k).toLowerCase()).join(', '))}</div>` : ''}</td><td>${ids(m.supporting_ids)}</td><td>${ids(m.contradicting_ids)}</td><td class="small">${esc(m.note)}</td></tr>`).join('')}</tbody></table></div></section>
        <div class="cards"><section class="card"><h3>Reasons for</h3>${g.reasons_for.length ? `<ul class="bullets small">${g.reasons_for.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : '<p class="faint small">No accepted evidence supports it yet.</p>'}</section>
          <section class="card"><h3>Reasons against</h3>${g.reasons_against.length ? `<ul class="bullets small">${g.reasons_against.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : '<p class="faint small">None recorded.</p>'}</section>
          <section class="card"><h3>Strongest source</h3>${g.strongest_source.id ? `<p class="small">${evLink(g.strongest_source.id)} ${esc(label(g.strongest_source.kind))}: ${esc(g.strongest_source.claim)}</p>` : `<p>${chip('UNKNOWN', 'Source unavailable')} Source unavailable</p>`}<p class="small muted">${esc(g.strongest_source.limitations)}</p></section>
          <section class="card"><h3>What would change this</h3><ul class="bullets small">${g.what_would_change_our_mind.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></section>
          <section class="card wide"><h3>Unresolved critical assumptions</h3><ul class="plain small">${g.unresolved_critical_assumptions.map((u) => `<li>${chip(u.status === 'UNTESTED' ? 'UNKNOWN' : u.status === 'REFUTED' ? 'FAIL' : 'REVIEW_REQUIRED', u.status)} <b>${esc(u.claim_id)}</b> ${esc(u.claim)}</li>`).join('') || '<li>None.</li>'}</ul></section>
          ${g.contradictions.length ? `<section class="card wide"><h3>Contradictions</h3><ul class="bullets small">${g.contradictions.map((c) => `<li>${esc(DIM[c.dimension] || c.dimension)}: ${ids(c.supporting_ids)} against ${ids(c.contradicting_ids)}</li>`).join('')}</ul></section>` : ''}
          ${g.experiment_outcomes.length ? `<section class="card wide"><h3>Locked tests read against their criteria</h3><ul class="plain small">${g.experiment_outcomes.map((o) => `<li>${chip(({ PASS: 'HIT', FAIL: 'CLEAR_MISS', INCONCLUSIVE: 'TOO_LITTLE_DATA', NEAR_MISS: 'NEAR_MISS' })[o.outcome])} ${esc(o.positives)}/${esc(o.n)} = ${esc(o.rate_pct)}% against ${esc(o.criteria.success_threshold_pct)}% (locked ${when(o.locked_at)}), evidence ${evLink(o.evidence_id)}</li>`).join('')}</ul></section>` : ''}
          ${g.excluded_evidence.length ? `<section class="card wide"><h3>Not counted</h3><ul class="bullets small">${g.excluded_evidence.map((x) => `<li>${evLink(x.id)}: ${esc(x.reason)}</li>`).join('')}</ul></section>` : ''}
        </div>
        ${g.criteria ? `<section class="panel"><header><h2>Validate criteria</h2><span class="small muted">${esc(g.criteria.criteria_version)}, ${g.criteria.unknown_count} unknown</span></header>${criteriaTable(g.criteria.criteria, pid)}</section>` : ''}
        <section class="panel"><header><h2>The local model's commentary</h2>${chip('HYPOTHESIS', 'AI text explaining a code verdict; checked against it')}</header>
          <p class="small muted">Secondary to the verdict above. Code removes fragments and sentences that contradict the verdict, and rewrites “X does not exist” as “no evidence of X was recorded”.</p>
          ${r._model_error ? `<div class="notice warn small">${esc(r._model_error)}</div>` : ''}
          <p>${unknownText(r.summary)}</p><dl class="facts small"><dt>Research vs demand</dt><dd>${unknownText(r.market_research_vs_customer_demand)}</dd><dt>Risks</dt><dd>${unknownText((r.risks || []).join('; '))}</dd>
          <dt>Gaps</dt><dd>${unknownText((r.contradictions_or_gaps || []).join('; '))}</dd><dt>Pricing ideas (untested)</dt><dd>${unknownText((r.pricing_hypotheses || []).join('; '))}</dd>
          <dt>Business model ideas (untested)</dt><dd>${unknownText((r.business_model_hypotheses || []).join('; '))}</dd></dl>
          ${(r._prose_checks || []).length ? `<details class="adv"><summary>${r._prose_checks.length} correction(s) made to the model's text</summary><ul class="bullets small">${r._prose_checks.map((n) => `<li>${esc(n.issue)} <span class="faint">Original: “${esc(n.original)}”</span></li>`).join('')}</ul></details>` : ''}
          ${(r._skeptic_flags || []).length ? `<div class="notice warn small"><b>Skeptic review flagged ${r._skeptic_flags.length} passage(s)</b><ul class="bullets">${r._skeptic_flags.map((f) => `<li>${esc(f.issue)}</li>`).join('')}</ul></div>` : ''}</section>
        <details class="adv"><summary>Advanced: hashes and raw verdict</summary><p class="small">Report <code>${esc(val.report_hash)}</code>, evidence snapshot <code>${esc(g.inputs.evidence_snapshot_hash)}</code>, decision policy ${esc(g.inputs.decision_policy)}, safety policy ${esc(g.inputs.safety_policy)}.</p><pre>${esc(JSON.stringify(g, null, 2))}</pre></details>
      </div>
      ${nextPanel('What happens next', [g.next_experiment && g.next_experiment.kind === 'RUN_LOCKED_EXPERIMENT' ? 'Run your locked test and enter the real result.' : 'Design and lock the next demand test.', 'Approving allows more research only. Nothing is ever published, sent, spent or signed.', `<a href="/projects/${pid}/audit" data-link>See the decision log</a>.`])}
      </div>`;
    wireVal();
    wireGate({ ...val, phase: 'validate' }, pid, g.verdict);
    document.getElementById('print').onclick = () => window.print();
    function wireVal() { const b = document.getElementById('val-run'); if (b) b.onclick = () => busy(b, 'Running validation', async () => { const x = await api(`/projects/${pid}/phases/validate/run`, { method: 'POST', pid }); await render(); ok(`Verdict: ${label(x.gate.verdict)}.`); }); }
  };

  // ---------------- Audit
  VIEWS.audit = async ({ pid }) => {
    const s = snap;
    crumb(s.project.name, 'Decision log');
    main.innerHTML = `${head('Decision log', 'Every founder decision, bound to the exact versions it was made on. The log is append-only in SQLite (application-level protection, not tamper-proof storage).')}
      <section class="panel"><header><h2>Your decisions</h2><span class="small muted">Newest first</span></header>${(s.decision_log || []).length ? `<ol class="decisions">
        ${s.decision_log.map((d) => `<li class="decision"><div class="d-top"><div><b>${esc(d.phase === 'discover' ? 'Discover' : 'Validate')} run v${esc(d.run_version)}</b> <span class="small muted">${when(d.at)}</span></div>
          ${chip(d.decision === 'APPROVE' ? 'APPROVED' : d.decision === 'STOP' ? 'STOPPED' : d.decision + '_REQUESTED')}</div>
          <dl class="facts small">
            <dt>Your decision</dt><dd>${esc(d.decision_label)}; scope ${esc(d.scope === 'RESEARCH_ONLY' ? 'research only' : d.scope.toLowerCase())}. Never enabled: ${esc(d.never_enabled.join(', '))}.</dd>
            <dt>Gate said</dt><dd>${chip(d.gate_said)}${d.founder_overrode_gate ? ' <span class="small">You chose a different course and gave a reason.</span>' : ''}</dd>
            <dt>Your reason</dt><dd>${d.reason ? `“${esc(d.reason)}”` : ''} ${chip(d.reason_status)}</dd>
            <dt>Bound to</dt><dd>brief v${esc(d.bound_to.brief_version)}; safety ${esc(label(d.bound_to.safety_status).toLowerCase())} (policy <code>${short(d.bound_to.safety_policy_hash)}</code>); report <code>${short(d.bound_to.report_hash)}</code>;
              criteria ${esc(d.bound_to.criteria_version)}; evaluation <code>${short(d.bound_to.evaluation_hash)}</code>${typeof d.bound_to.discover_evaluation_version === 'number' ? ` v${d.bound_to.discover_evaluation_version}` : ''}; rubric ${esc(d.bound_to.rubric_version)}
              ${d.tests.length ? `; tests ${d.tests.map((x) => `${short(x.id, 6)} v${x.version} ${label(x.status).toLowerCase()}${x.simulated ? ' (simulated)' : ''}`).join(', ')}` : ''}
              ${d.refs_not_stored.length ? `<div class="faint">Not stored for this record (it predates the field): ${esc(d.refs_not_stored.join(', '))}.</div>` : ''}</dd></dl></li>`).join('')}</ol>` : '<p class="faint">No decisions yet.</p>'}</section>
      <section class="panel" style="margin-top:18px"><header><h2>Timeline</h2><span class="small muted">Latest ${s.audit.length} events</span></header><ul class="timeline">
        ${s.audit.map((a) => `<li><time datetime="${esc(a.created_at)}">${when(a.created_at)}</time><div><b>${esc(a.event.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase()))}</b><div class="small muted">${esc(Object.entries(a.details).filter(([, v]) => v !== null && v !== '' && !(Array.isArray(v) && !v.length)).slice(0, 6).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join('; ').slice(0, 260))}</div></div></li>`).join('')}</ul></section>`;
  };

  // ---------------- Roadmap & help
  VIEWS.roadmap = async () => {
    crumb('Six-phase roadmap', 'What is live and what is architecture only');
    const c = await api('/criteria');
    const live = [['Discover', 'live', 'Brief, safety, discovery, research and the Discover gate run in this prototype.', c.discover], ['Validate', 'live', 'Demand tests, locked targets, result reading and the decision passport run in this prototype.', c.validate]];
    const later = [['Build', 'build', 'Smallest product that delivers validated value; finished when its acceptance tests pass.'], ['Commercial setup', 'commercial_setup', 'Price and policy drafts for human review. No payments, ever.'],
      ['Launch', 'launch', 'Marketing drafts only; nothing is published without a separate, specific approval.'], ['Operate and learn', 'operate_learn', 'Real, opt-in results decide double down, adjust, pivot back or shut down.']];
    main.innerHTML = `${head('Six business phases', 'Research, demand tests and the decision passport are steps inside the two live phases. The other four are documented with their criteria and are not implemented; nothing here pretends they run.')}
      <section class="panel">${live.map(([n, , d, crit], i) => `<div class="phase" data-live="1"><span class="n">${i + 1}</span><div><h2>${n} ${chip('PASS', 'Implemented')}<span class="small muted"> Live</span></h2><p class="muted">${d}</p>
        <ul class="bullets small">${crit.map((x) => `<li><b>${esc(x.id)} ${esc(x.name)}</b> (${esc(x.kind.replace('_', ' '))}): ${esc(x.question)}</li>`).join('')}</ul></div></div>`).join('')}
        ${later.map(([n, k, d], i) => `<div class="phase"><span class="n">${i + 3}</span><div><h2>${n} <span class="chip plain">Architecture only</span></h2><p class="muted">${d}</p>
        <ul class="bullets small">${c.architecture_only[k].criteria.map((x) => `<li><b>${esc(x.id)} ${esc(x.name)}</b> (${esc(x.kind.replace('_', ' '))}): ${esc(x.question)}</li>`).join('')}</ul></div></div>`).join('')}</section>
      <section class="panel" style="margin-top:18px"><h2>Applied at every live gate</h2><ul class="bullets small">${c.cross_cutting.map((x) => `<li><b>${esc(x.id)} ${esc(x.name)}</b> (${esc(x.kind.replace('_', ' '))}): ${esc(x.question)}</li>`).join('')}</ul>
      <p class="small muted">Criteria file ${esc(c.version)}, source: “${esc(c.source.title)}”, ${esc(c.source.date)}.</p></section>`;
  };
  VIEWS.help = async () => {
    crumb('How it works', 'Plain-language guide');
    main.innerHTML = `${head('How FounderOS works', 'It helps you decide, with evidence, whether an idea is worth more of your time. It does not build, publish or sell anything.')}
      <div class="stack"><section class="panel"><h2>Who decides what</h2><dl class="facts"><dt>Your local model</dt><dd>Refines your brief, drafts hypotheses, proposes scores one criterion at a time, and explains verdicts. Everything it writes is a hypothesis.</dd>
        <dt>Code</dt><dd>Runs the twelve safety checks, verifies sources, applies pass marks and picks every gate exit. The model cannot change a verdict.</dd>
        <dt>You</dt><dd>Approve, revise, pivot or stop at each gate. Approval means more research only.</dd></dl></section>
      <section class="panel"><h2>What the words mean</h2><dl class="facts small"><dt>Unknown</dt><dd>No accepted evidence. Never treated as a zero or a middle score.</dd><dt>Excerpt verified</dt><dd>The exact words were found on the fetched page. It does not mean they are true.</dd>
        <dt>Metadata only</dt><dd>A title or abstract from an index. Context, never counted.</dd><dt>Founder-reported</dt><dd>Results you entered. FounderOS cannot check them independently.</dd>
        <dt>Needs evidence</dt><dd>No real customer behaviour yet. Not a judgement that the idea is bad.</dd><dt>Near miss</dt><dd>A locked test came just under its pass mark. Repeat or redesign.</dd></dl></section>
      <section class="panel"><h2>If the model will not load</h2><p class="small">Click the model status in the top bar to run a real test. Out-of-memory on GPU: set <code>OLLAMA_NUM_GPU=0</code>. Out-of-memory on CPU: close heavy apps and set <code>OLLAMA_NUM_CTX=1024</code>. See the README for Windows steps. FounderOS never switches to another model or shows simulated answers.</p></section></div>`;
  };

  // ------------------------------------------------------------------ boot
  modelStatus();
  setInterval(modelStatus, 30000);
  if (location.pathname === '/') history.replaceState({}, '', '/projects');
  render();
})();

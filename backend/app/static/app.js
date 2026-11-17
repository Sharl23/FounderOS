(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  let session = JSON.parse(localStorage.getItem('founderos_session') || 'null');
  let state = null;
  let suggestion = null;
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pretty = (d) => JSON.stringify(d, null, 2);
  const stamp = (x) => x ? new Date(x).toLocaleString() : '—';
  const short = (id) => id ? String(id).slice(0, 8) : '—';
  const list = (arr, f = esc) => (arr && arr.length) ? '<ul>' + arr.map(x => '<li>' + f(x) + '</li>').join('') + '</ul>' : '<span class="small">none</span>';
  function tell(message, ok = false) { const e = $('alert'); e.textContent = message; e.className = 'alert' + (ok ? ' ok' : ''); window.scrollTo({top: 0, behavior: 'smooth'}); }
  function clearAlert() { $('alert').className = 'alert hide'; }
  function detail(d) { if (typeof d === 'string') return d; if (d && d.message) return d.message + (d.findings ? ' ' + d.findings.map(f => f.rule_id + ': ' + f.reason).join(' | ') : ''); return pretty(d); }
  async function api(path, method = 'GET', body) {
    const headers = {'Content-Type': 'application/json'};
    if (session) headers['X-Project-Token'] = session.access_token;
    const response = await fetch('/api' + path, {method, headers, body: body !== undefined ? JSON.stringify(body) : undefined});
    const data = await response.json().catch(() => ({detail: 'Unexpected server response'}));
    if (!response.ok) throw new Error('HTTP ' + response.status + ': ' + detail(data.detail));
    return data;
  }
  async function act(button, fn, label = 'Working with local model…') {
    const before = button?.textContent;
    if (button) { button.disabled = true; button.textContent = label; }
    clearAlert();
    try { await fn(); } catch (e) { tell(e.message || String(e)); } finally { if (button) { button.disabled = false; button.textContent = before; } }
  }
  // Client-side multi-page journey: never changes backend authorization or gate logic.
  const JOURNEY = [
    {id:'idea', title:'Your Idea', desc:'Refine the founder brief; confirm unknowns before research.', cards:['refine-card']},
    {id:'safety', title:'Safety', desc:'Review hard-stop rules, risk flags and founder constraints.', cards:['safety-card']},
    {id:'discovery', title:'Discovery', desc:'Understand customer, problem and hypotheses; decide at the approval gate.', cards:['discover-card']},
    {id:'evidence', title:'Research & Evidence', desc:'Find candidate sources and record verified excerpts; keep demand separate.', cards:['evidence-card']},
    {id:'experiment', title:'Demand Experiments', desc:'Pre-register measurable tests before collecting honest customer results.', cards:['experiment-card']},
    {id:'decision', title:'Validation & Decision', desc:'Get a transparent verdict and decide with the founder in control.', cards:['validate-card','passport-card','roadmap-card','decision-list','audit-list']}
  ];
  let activeView = sessionStorage.getItem('founderos_view') || 'idea';
  function navigate(view, scroll = true) {
    if (!JOURNEY.some(x => x.id === view)) view = 'idea';
    activeView = view; sessionStorage.setItem('founderos_view', view);
    const v = JOURNEY.find(x => x.id === view), index = JOURNEY.indexOf(v);
    const workspace = $('workspace');
    if (workspace) {
      const cards = workspace.querySelectorAll('section.card');
      cards.forEach(card => {
        // The project status compact card always remains accessible.
        if (card.classList.contains('compact')) { card.classList.remove('journey-hidden'); return; }
        card.classList.toggle('journey-hidden', !v.cards.includes(card.id));
      });
      // Decision log/audit may live within a section without ID; ensure anything
      // outside the six page cards is only visible on the decision page.
      const visibleIds = new Set(v.cards);
      [...workspace.children].filter(x => x.tagName === 'SECTION' && !x.classList.contains('compact') && !x.id).forEach(x=>x.classList.toggle('journey-hidden',view!=='decision'));
    }
    $('journey-step').textContent = 'STEP ' + String(index + 1).padStart(2,'0') + ' / 06';
    $('journey-title').textContent = v.title;
    $('journey-description').textContent = v.desc;
    $('journey-back').disabled = index === 0;
    $('journey-next').disabled = index === JOURNEY.length - 1;
    $('journey-next').textContent = index === JOURNEY.length - 2 ? 'Review verdict →' : 'Next step →';
    $('workspace-nav').querySelectorAll('[data-view]').forEach(b => {
      b.classList.toggle('selected', b.dataset.view === view);
      b.setAttribute('aria-current', b.dataset.view===view?'step':'false');
    });
    if (view === 'evidence' && session) { loadResearchPlan(); loadCriteria(); }
    if(scroll) $('journey-toolbar').scrollIntoView({behavior:'smooth',block:'start'});
  }
  function initJourney() {
    $('workspace-nav').innerHTML = JOURNEY.map((v,i) => `<button class="journey-nav-item" type="button" data-view="${v.id}"><span>${String(i+1).padStart(2,'0')}</span>${esc(v.title)}</button>`).join('');
    $('workspace-nav').addEventListener('click', e => { const b=e.target.closest('[data-view]'); if (b) navigate(b.dataset.view); });
    $('journey-back').onclick = () => navigate(JOURNEY[Math.max(0,JOURNEY.findIndex(x=>x.id===activeView)-1)].id);
    $('journey-next').onclick = () => navigate(JOURNEY[Math.min(JOURNEY.length-1,JOURNEY.findIndex(x=>x.id===activeView)+1)].id);
    // Deep links to evidence still work after all pages have been separated.
    document.addEventListener('click', e=>{ if(e.target.closest('a[href^="#ev-"]')) navigate('evidence',false); });
    navigate(activeView,false);
    $('view-roadmap-link').onclick = e => {e.preventDefault(); navigate('decision'); document.getElementById('roadmap-card')?.scrollIntoView({behavior:'smooth'});};
  }
  async function loadResearchPlan() {
    const div = $('research-suggestions');
    if (!session) return;
    try {
      const data = await api('/projects/' + session.project_id + '/research-plan');
      div.innerHTML = data.queries.map(q => `<button type="button" class="query-card" data-query="${esc(q.query)}"><strong>${esc(q.title)}</strong><span>${esc(q.query)}</span><small>${esc(q.purpose)}</small></button>`).join('');
      div.querySelectorAll('[data-query]').forEach(b => b.onclick=()=>{
        $('research-form').elements.query.value = b.dataset.query;
        $('research-form').scrollIntoView({behavior:'smooth',block:'center'});
        $('research-form').elements.query.focus();
      });
    } catch (e) {div.textContent='Could not build research suggestions: '+e.message;}
  }
  async function loadCriteria() {
    if (!session) return;
    try {
      const data = await api('/projects/' + session.project_id + '/criteria');
      $('criteria-version').textContent = data.criteria_version;
      const rows = data.criteria;
      const unknown = rows.filter(x=>x.status==='UNKNOWN').length;
      $('criteria-stats').innerHTML = `<div><b>${esc(data.qualified_evidence_count)}</b><span>Qualified records*</span></div><div><b>${esc(unknown)}</b><span>Unknown criteria</span></div><div><b>${esc(rows.length)}</b><span>Active criteria</span></div>`;
      const groups = [['discover','Discover — nine criteria'],['validate','Validate — seven criteria'],['all','Across every gate — five criteria']];
      $('criteria-rows').innerHTML = groups.map(([phase, name])=>`<h4>${esc(name)}</h4>` +
        rows.filter(x=>x.phase===phase).map(x=>`<div class="criterion-row"><div><strong>${esc(x.id)} · ${esc(x.name)}</strong><span>${esc(x.question)}</span><small>${esc(x.reason)}</small></div><span class="criterion-status">${esc(x.status)}</span></div>`).join('')).join('') +
        '<p class="hint">*Qualified = relevant, non-duplicate records meeting basic provenance conditions; no truth or customer demand independently verified.</p>';
    } catch(e){$('criteria-rows').textContent='Criteria unavailable: '+e.message;}
  }
  async function findResearch(query) {
    const results = $('research-results');
    results.innerHTML = '<p class="hint">Searching live Crossref metadata…</p>';
    try {
      const payload = await api('/research/crossref?q=' + encodeURIComponent(query));
      if(!payload.results.length) {results.innerHTML='<p class="hint">No indexed publications found. This is not evidence that research does not exist.</p>';return;}
      results.innerHTML = '<p class="hint">These are bibliographic leads, NOT inspected evidence. Open the publication; check its geography, methods and relevance; copy an exact excerpt yourself.</p>' + payload.results.map(r=> `<article class="research-result"><div class="research-label">CANDIDATE · NOT VERIFIED · ${esc(r.topic_match === 'POSSIBLE' ? 'Possible title match' : 'Weak title match')}</div><h4>${esc(r.title)}</h4><p>${esc(r.publisher || 'Publisher unknown')} · ${esc(r.year || 'Year unknown')} · ${esc(r.type || '')}</p><p class="small">Title keywords matching query: ${esc((r.matched_query_terms||[]).join(', ') || 'none')}. Read methods, geography and sample before use.</p><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">Open publication ↗</a> <button class="ghost smal" type="button" data-prefill="${esc(r.id)}">Use citation metadata</button></article>`).join('');
      results.querySelectorAll('[data-prefill]').forEach(b=>b.onclick=()=>{
        const r=payload.results.find(x=>x.id===b.dataset.prefill);
        if(!r)return;
        const form=$('evidence-src'); form.elements.url.value=r.url; form.elements.title.value=r.title + ' / ' + (r.publisher||''); form.elements.published_on.value=r.year ? String(r.year):'';
        form.elements.claim.value=''; form.elements.excerpt.value=''; form.elements.direction.value='UNSURE';form.elements.relevance.value='UNSURE';
        form.scrollIntoView({behavior:'smooth'});
        tell('Citation metadata copied. YOU must add a specific supported claim and exact excerpt from the publication; no evidence was recorded.',true);
      });
    } catch(err) {results.textContent='Research index unavailable: '+err.message+'. Manual evidence entry still works. No source was fabricated.';}
  }
  function formData(form) { const d = Object.fromEntries(new FormData(form)); for (const k in d) if (d[k] === '') d[k] = null; form.querySelectorAll('input[type=checkbox]').forEach(c => d[c.name] = c.checked); form.querySelectorAll('input[type=number]').forEach(n => { if (d[n.name] != null) d[n.name] = Number(d[n.name]); }); return d; }

  async function health() {
    try {
      const h = await api('/health');
      const ok = h.ollama && h.ollama.ollama_reachable && h.ollama.model_pulled;
      $('model-status').textContent = ok ? 'Local model ready: ' + h.model : (h.ollama.ollama_reachable ? 'Ollama up, model NOT pulled: ' + h.model : 'Ollama NOT reachable — AI steps will fail honestly');
      $('model-dot').style.background = ok ? '#71dfad' : '#ff8a8a';
      $('model-tag').textContent = '◉ ' + h.model + (ok ? '' : ' (unavailable)');
    } catch (e) { $('model-status').textContent = 'API unreachable'; }
  }

  async function refresh() {
    if (!session) { $('new-project').classList.remove('hide'); $('workspace').classList.add('hide'); $('journey-toolbar').classList.add('hide'); return; }
    state = await api('/projects/' + session.project_id);
    $('new-project').classList.add('hide'); $('workspace').classList.remove('hide'); $('journey-toolbar').classList.remove('hide'); navigate(activeView,false);
    const p = state.project, b = state.brief, s = state.safety, cur = state.current;
    const disc = state.phase_runs.find(x => x.phase === 'discover');
    const val = state.phase_runs.find(x => x.phase === 'validate');
    $('project-id').textContent = short(p.id) + '…';
    $('project-name-display').textContent = (b?.payload?.idea_summary || p.original_idea || 'Founder workspace').slice(0, 88);
    $('brief-version').textContent = b ? 'v' + b.version : '—';
    $('safety-label').textContent = s ? s.status : 'NOT SCREENED';
    $('state-label').textContent = p.stopped ? 'STOPPED' : (val?.state ? 'VALIDATE ' + val.state : disc?.state ? 'DISCOVER ' + disc.state : b ? 'BRIEF READY' : 'ONBOARDING');
    $('evidence-count').textContent = state.evidence.length;
    if (activeView === 'evidence') { loadResearchPlan(); loadCriteria(); }
    $('original-text').textContent = p.original_idea;
    renderBrief(b);
    renderSafety(s, b);
    renderClarifications(b);
    const blocked = s && s.status === 'BLOCK';
    const cleared = s && (s.status === 'ALLOW_DISCOVERY' || (s.status === 'REVIEW_REQUIRED' && s.acknowledged_at));
    renderDiscovery(disc);
    $('discover-btn').disabled = !b || p.stopped || blocked || !cleared || Boolean(disc && ['PENDING_APPROVAL', 'APPROVED'].includes(disc.state));
    $('refine-btn').disabled = p.stopped;
    $('validate-btn').disabled = !disc || disc.state !== 'APPROVED' || p.stopped || Boolean(val && ['PENDING_APPROVAL', 'APPROVED'].includes(val.state));
    const evLocked = p.stopped || Boolean(val && ['PENDING_APPROVAL', 'APPROVED'].includes(val.state));
    $('evidence-src').querySelector('button').disabled = evLocked; $('evidence-cust').querySelector('button').disabled = evLocked;
    renderGate('discover-decision', disc, b);
    renderGate('validate-decision', val, b);
    renderValidation(val);
    renderEvidence(state.evidence);
    renderExperiments(state.experiments, p.stopped);
    renderPassport(state.passport, state.evidence);
    renderLog(state.decisions, state.audit);
    if (b && !suggestion && !p.stopped) loadSuggestion();
  }

  function renderDiscovery(disc) {
    const n=$('discover-output');
    if(!disc){n.className='output empty';n.textContent='Run Discovery to see hypotheses, audiences and recommended tests.';return;}
    const r=disc.report||{};
    n.className='output';
    n.innerHTML=`<div class="report-lead"><div class="small">Run v${disc.version} · ${esc(disc.state)} · ${disc.latency_ms} ms · AI HYPOTHESES ONLY</div><h3>${esc(r.problem_statement||'Problem not established')}</h3><p>${esc(r.value_proposition||'Value proposition unknown')}</p></div>`
      + `<div class="report-grid"><div class="field"><b>Who might use it</b>${list(r.target_customers)}</div><div class="field"><b>Alternatives (unverified)</b>${list(r.alternatives_unverified)}</div><div class="field"><b>Hypotheses to test</b>${list(r.hypotheses)}</div><div class="field"><b>Unknowns</b>${list(r.unknowns)}</div></div>`
      + `<div class="field"><b>Proposed experiments — not results</b>${list(r.experiments)}</div>`
      + '<details class="advanced"><summary>Technical report and provenance</summary><pre>'+esc(pretty({version:disc.version,brief_version:disc.brief_version,model:disc.model,report:r}))+'</pre></details>';
  }
  function renderJson(id, data, placeholder) { const n = $(id); if (!data) { n.textContent = placeholder; n.className = 'output empty'; return; } n.className = 'output'; n.textContent = pretty(data); }

  function renderBrief(b) {
    const n = $('brief-fields');
    if (!b) { n.className = 'output empty'; n.textContent = 'No refined brief yet.'; return; }
    const pl = b.payload, prov = pl.provenance || {};
    const tag = (k) => `<span class="tag ${esc(prov[k] || 'UNKNOWN')}">${esc(prov[k] || 'UNKNOWN')}</span>`;
    n.className = 'output';
    n.innerHTML = ['idea_summary', 'problem', 'target_customers', 'target_market', 'skills', 'budget', 'timeline', 'values', 'constraints'].map(k =>
      `<div class="field"><b>${esc(k.replace(/_/g, ' '))}</b> ${k === 'idea_summary' ? '<span class="tag INFERRED_UNCONFIRMED">AI SUMMARY</span>' : tag(k)}<div>${esc(pl[k] ?? '—')}</div></div>`).join('')
      + (pl.assumptions?.length ? `<div class="field"><b>model assumptions (NOT facts)</b>${list(pl.assumptions)}</div>` : '')
      + (pl.questions?.length ? `<div class="field"><b>clarification questions</b>${list(pl.questions)}</div>` : '')
      + `<div class="small">brief v${b.version} · ${esc(pl.model || '')} · ${pl.latency_ms ? pl.latency_ms + ' ms' : ''}</div>`;
  }

  function renderClarifications(b) {
    const div = $('clarify-fields');
    if (!b || state.project.stopped) { div.innerHTML = ''; return; }
    const keys = ['problem', 'target_customers', 'target_market', 'skills', 'budget', 'timeline', 'values', 'constraints'];
    div.innerHTML = '<h3>Correct or complete the brief</h3><p class="small">Any change creates a new brief version, re-runs the safety screen and invalidates approvals built on the old version.</p><form id="clarify-form"><div class="two">'
      + keys.map(k => `<label>${esc(k.replace(/_/g, ' '))} <span class="tag ${esc(b.payload.provenance?.[k] || 'UNKNOWN')}">${esc(b.payload.provenance?.[k] || 'UNKNOWN')}</span><input name="${k}" placeholder="${esc(b.payload[k] || 'unknown — fill if you know')}"></label>`).join('')
      + '</div><div class="actions"><button class="secondary" type="submit">Save corrections (new brief version)</button></div></form>';
    $('clarify-form').addEventListener('submit', async (ev) => { ev.preventDefault(); await act(ev.submitter, async () => {
      const answers = Object.fromEntries([...new FormData(ev.target)].filter(([, v]) => String(v).trim()));
      if (!Object.keys(answers).length) throw Error('Enter at least one correction.');
      const r = await api('/projects/' + session.project_id + '/clarify', 'POST', {answers});
      await refresh(); tell('Brief v' + r.version + ' saved. Safety: ' + r.safety.status + '. Dependent approvals invalidated.', true);
    }, 'Saving…'); });
  }

  function renderSafety(s, b) {
    const out = $('safety-output'), ack = $('safety-ack'), pill = $('safety-pill');
    if (!s) { out.className = 'output empty'; out.textContent = 'Refine the brief to run the screen.'; ack.innerHTML = ''; pill.textContent = '—'; return; }
    pill.textContent = s.status; pill.className = 'pill ' + s.status;
    const a = s.assessment;
    out.className = 'output';
    out.innerHTML = `<div class="verdict ${esc(s.status)}">${esc(s.status)}</div><div class="small">policy ${esc(a.policy_version)} · brief v${s.brief_version}${s.acknowledged_at ? ' · acknowledged ' + esc(stamp(s.acknowledged_at)) + ' (research only)' : ''}</div>`
      + (a.findings.length ? a.findings.map(f => `<div class="finding ${esc(f.severity)}"><b>${esc(f.severity)} · ${esc(f.rule_id)}</b>${f.organizer_rule ? '<div class="small">Organizer rule: ' + esc(f.organizer_rule) + '</div>' : ''}<div>${esc(f.reason)}</div><div class="small">Matched: ${f.matched_text.map(esc).join(' … ')}</div><div class="small"><b>Safe revision:</b> ${esc(f.safe_revision)}</div></div>`).join('') : '<p>No prohibited or high-stakes patterns found. This does not certify legality.</p>')
      + (a.feasibility_notes.length ? '<div class="field"><b>Feasibility notes</b>' + list(a.feasibility_notes) + '</div>' : '')
      + '<div class="field"><b>Limitations</b>' + list(a.limitations) + '</div>';
    if (s.status === 'REVIEW_REQUIRED' && !s.acknowledged_at && !state.project.stopped) {
      ack.innerHTML = `<form id="ack-form"><label>Acknowledge flagged risks (research only, no legal certification)<input name="statement" required minlength="10" placeholder="e.g. I understand this is a health-related domain and will consult a professional before building."></label><div class="actions"><button class="secondary" type="submit">Acknowledge for brief v${b.version} ↗</button></div></form>`;
      $('ack-form').addEventListener('submit', async (ev) => { ev.preventDefault(); await act(ev.submitter, async () => {
        await api('/projects/' + session.project_id + '/safety/acknowledge', 'POST', {brief_version: b.version, statement: new FormData(ev.target).get('statement')});
        await refresh(); tell('Risk acknowledged for research only.', true); }, 'Saving…'); });
    } else if (s.status === 'BLOCK') {
      ack.innerHTML = '<p class="warn">This brief is blocked by backend policy. Approval cannot override it. Correct the brief above (new version) or start a new founder brief.</p>';
    } else ack.innerHTML = '';
  }

  function renderGate(id, run, b) {
    const div = $(id);
    if (!run) { div.innerHTML = ''; return; }
    const g = run.gate, rec = g.verdict || g.recommendation;
    let html = `<div class="gate"><strong>Gate · ${esc(run.state)}${run.invalidated_reason ? ' · ' + esc(run.invalidated_reason) : ''}</strong><span class="pill ${esc(rec)}">${esc(rec)}</span><p class="small">${esc((g.reasons || [g.headline]).join(' '))}</p><p class="small">Bound to brief v${run.brief_version} · report ${esc(short(run.report_hash))}… · approval scope: RESEARCH ONLY · external actions: never</p>`;
    if (run.state === 'PENDING_APPROVAL' && !state.project.stopped) {
      const caution = ['STOP_DO_NOT_LAUNCH', 'PIVOT', 'REVISE'].includes(rec);
      html += `<label>Founder feedback / reasons (required for Revise, Pivot${caution ? ', and for approving against the recommendation' : ''})<textarea rows="2" class="decision-feedback" placeholder="What should change, or why you choose a different course?"></textarea></label>`
        + (caution ? '<label class="warn"><input type="checkbox" class="risk-ack inline">I have read the recommendation and knowingly choose a different course. This permits research only.</label>' : '')
        + `<div class="actions"><button data-action="APPROVE">Approve (research only)</button><button class="secondary" data-action="REVISE">Revise</button><button class="secondary" data-action="PIVOT">Pivot</button><button class="danger" data-action="STOP">Stop project</button></div>`;
    }
    div.innerHTML = html + '</div>';
    div.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', async () => {
      await act(button, async () => {
        const action = button.dataset.action;
        if (action === 'STOP' && !confirm('Stop this project? This is enforced: no further runs are possible.')) return;
        const payload = {run_id: run.id, report_hash: run.report_hash, brief_version: run.brief_version, decision: action,
                         feedback: div.querySelector('.decision-feedback')?.value || '', acknowledge_risk: div.querySelector('.risk-ack')?.checked || false};
        const r = await api('/projects/' + session.project_id + '/phases/' + run.phase + '/decision', 'POST', payload);
        suggestion = null; await refresh(); tell('Decision recorded: ' + r.state + ' (scope ' + r.scope + '). No external action was taken.', true);
      }, 'Recording…');
    }));
  }

  function renderValidation(val) {
    const n = $('validate-output');
    if (!val) { n.className = 'output empty'; n.textContent = 'Approve the latest discovery first.'; return; }
    const r = val.report;
    n.className = 'output';
    n.innerHTML = `<div class="small">v${val.version} · ${esc(val.state)} · ${esc(val.model)} · ${val.latency_ms} ms</div>`
      + `<div class="field"><b>Agent summary (explains the backend verdict; cannot change it)</b><div>${esc(r.summary)}</div></div>`
      + `<div class="field"><b>Market research vs customer demand</b><div>${esc(r.market_research_vs_customer_demand)}</div></div>`
      + `<div class="field"><b>Risks</b>${list(r.risks)}</div><div class="field"><b>Contradictions / gaps</b>${list(r.contradictions_or_gaps)}</div>`
      + `<div class="field"><b>Pricing hypotheses (UNTESTED)</b>${list(r.pricing_hypotheses)}</div><div class="field"><b>Business model hypotheses (UNTESTED)</b>${list(r.business_model_hypotheses)}</div>`
      + `<div class="field"><b>Competitor research limitations</b>${list(r.competitor_research_limitations)}</div>`
      + (r._skeptic_flags?.length ? `<div class="field warn"><b>Skeptic reviewer flags (${r._skeptic_flags.length})</b>${list(r._skeptic_flags, f => esc(f.issue) + ' <span class="small">in ' + esc(f.field) + '</span>')}</div>` : '<div class="small">Skeptic reviewer: no over-claims or unsourced numbers detected in agent text.</div>');
  }

  function renderEvidence(evidence) {
    $('evidence-list').innerHTML = evidence.length ? evidence.map(e => `<div class="evidence-row" id="ev-${esc(e.id)}"><strong><code>${esc(short(e.id))}</code> ${esc(e.kind)} · ${esc(e.dimension)} · ${esc(e.direction)}${e.duplicate_of ? ' · <span class="tag UNKNOWN">DUPLICATE of ' + esc(short(e.duplicate_of)) + '</span>' : ''}${e.injection_flag ? ' · <span class="tag BLOCK">EXCLUDED (injection)</span>' : ''}</strong><div>${esc(e.claim)}</div>`
      + (e.source_url ? `<div class="small">${esc(e.title || '')} ${esc(e.publisher || '')} ${esc(e.published_on || '')} · <a href="${esc(e.source_url)}" target="_blank" rel="noopener noreferrer">${esc(e.source_url)}</a> · <span class="tag ${e.url_status === 'URL_ACCESSIBLE' ? 'EXPLICIT' : 'BLOCK'}">${esc(e.url_status)}</span> <span class="tag ${e.excerpt_status === 'EXCERPT_MATCHED' ? 'EXPLICIT' : 'BLOCK'}">${esc(e.excerpt_status)}</span> · retrieved ${esc(stamp(e.retrieved_at))}</div><div class="small">“${esc(e.excerpt)}”</div>` : `<div class="small">${esc(e.method || '')} · n=${esc(e.sample_size)} · positives=${esc(e.positives ?? '—')} · ${esc(e.collected_from || '')}→${esc(e.collected_to || '')} · <span class="tag INFERRED_UNCONFIRMED">${esc(e.independence)}</span>${e.outcome ? ' · outcome <b>' + esc(e.outcome) + '</b> (' + esc(e.rate_pct) + '%) vs experiment ' + esc(short(e.experiment_id)) + ' v' + esc(e.experiment_version) : ''}</div>`)
      + `<div class="small">${esc(e.limitations)}</div></div>`).join('') : '<p class="hint">No evidence recorded. The verdict will say NEEDS_EVIDENCE; it will not pretend otherwise.</p>';
  }

  async function loadSuggestion() {
    try { suggestion = await api('/projects/' + session.project_id + '/experiments/suggest'); } catch (e) { suggestion = null; return; }
    const n = $('experiment-suggestion'); n.className = 'output';
    if (suggestion.kind === 'RUN_LOCKED_EXPERIMENT') { n.innerHTML = `<b>Run your locked experiment ${esc(short(suggestion.experiment_id))} v${suggestion.version}</b><div>${esc(suggestion.instruction)}</div><pre>${esc(pretty(suggestion.criteria))}</pre>`; return; }
    n.innerHTML = `<div class="small">${esc(suggestion.kind)} · claim ${esc(suggestion.claim_id)} · ${esc(suggestion.dimension)}</div><div class="field"><b>Hypothesis</b><div>${esc(suggestion.hypothesis)}</div></div><div class="field"><b>Target segment</b><div>${esc(suggestion.target_segment)}</div></div><div class="field"><b>Observable metric</b><div>${esc(suggestion.metric)}</div></div><div class="field"><b>Consent</b><div>${esc(suggestion.consent_method)}</div></div><div class="field"><b>You do</b>${list(suggestion.founder_actions)}</div><div class="field"><b>Estimates</b><div>${esc(suggestion.timebox_estimate)} · ${esc(suggestion.cost_estimate)}</div></div><div class="field"><b>Suggested criteria (NOT evidence)</b><div>min n ${suggestion.suggested_criteria.min_sample} · success ≥ ${suggestion.suggested_criteria.success_threshold_pct}% · adverse ≤ ${suggestion.suggested_criteria.adverse_threshold_pct}%</div><div class="small">${esc(suggestion.suggested_criteria.label)}</div></div><div class="small">${esc(suggestion.adverse_result_trigger)} ${esc(suggestion.external_actions)}</div>`;
  }

  $('experiment-new').onclick = () => {
    const f = $('experiment-form'); f.classList.remove('hide');
    if (suggestion && suggestion.kind !== 'RUN_LOCKED_EXPERIMENT') {
      f.hypothesis.value = suggestion.hypothesis.slice(0, 600); f.claim_id.value = suggestion.claim_id; f.dimension.value = suggestion.dimension; f.target_segment.value = suggestion.target_segment.slice(0, 300);
      f.metric.value = suggestion.metric.slice(0, 400); f.consent_method.value = suggestion.consent_method.slice(0, 600); f.founder_actions.value = suggestion.founder_actions.join(' ').slice(0, 1200);
      f.min_sample.value = suggestion.suggested_criteria.min_sample; f.success_threshold_pct.value = suggestion.suggested_criteria.success_threshold_pct; f.adverse_threshold_pct.value = suggestion.suggested_criteria.adverse_threshold_pct;
      f.timebox_estimate.value = suggestion.timebox_estimate.slice(0, 120); f.cost_estimate.value = suggestion.cost_estimate.slice(0, 120);
    }
    f.scrollIntoView({behavior: 'smooth'});
  };
  $('experiment-form').addEventListener('submit', async (ev) => { ev.preventDefault(); await act(ev.submitter, async () => {
    const d = formData(ev.target);
    const r = await api('/projects/' + session.project_id + '/experiments', 'POST', d);
    ev.target.classList.add('hide'); suggestion = null; await refresh(); tell('Draft ' + short(r.experiment_id) + ' saved. Lock it before collecting any data.', true);
  }, 'Saving…'); });

  function renderExperiments(experiments, stopped) {
    const bySeries = {};
    experiments.forEach(x => { (bySeries[x.id] = bySeries[x.id] || []).push(x); });
    const div = $('experiment-list');
    div.innerHTML = Object.values(bySeries).map(rows => rows.map(x => {
      const c = x.payload;
      let html = `<div class="evidence-row"><strong><code>${esc(short(x.id))}</code> v${x.version} · <span class="tag ${x.status === 'LOCKED' ? 'EXPLICIT' : x.status === 'DRAFT' ? 'INFERRED_UNCONFIRMED' : 'UNKNOWN'}">${esc(x.status)}</span>${x.locked_at ? ' · pre-registered ' + esc(stamp(x.locked_at)) : ''}</strong><div>${esc(c.hypothesis)}</div><div class="small">${esc(c.target_segment)} · metric: ${esc(c.metric)} · min n ${c.min_sample} · success ≥ ${c.success_threshold_pct}% · adverse ≤ ${c.adverse_threshold_pct}% · ${c.critical ? 'CRITICAL' : 'non-critical'}${c.pivot_alternative ? ' · pivot alt: ' + esc(c.pivot_alternative) : ''} · hash ${esc(short(x.criteria_hash))}…</div>${x.result_evidence_id ? `<div class="small">Result recorded as evidence <a href="#ev-${esc(x.result_evidence_id)}">${esc(short(x.result_evidence_id))}</a></div>` : ''}`;
      const latest = rows[rows.length - 1] === x;
      if (latest && !stopped && x.status === 'DRAFT') html += `<div class="actions"><button class="secondary smal" data-lock="${esc(x.id)}" data-v="${x.version}" data-h="${esc(x.criteria_hash)}">Lock / pre-register v${x.version} ↗</button><button class="ghost smal" data-revise="${esc(x.id)}">Edit (new version)</button></div>`;
      if (latest && !stopped && x.status === 'LOCKED' && !x.result_evidence_id) html += `<form class="result-form" data-sid="${esc(x.id)}" data-v="${x.version}" data-h="${esc(x.criteria_hash)}"><div class="two"><label>Relevant participants (n)<input name="sample_size" type="number" min="1" required></label><label>Positives<input name="positives" type="number" min="0" required></label><label>Method<input name="method" required minlength="10"></label><label>Collected from<input name="collected_from" type="date" required></label><label>Collected to<input name="collected_to" type="date" required></label></div><label>Positive signals<input name="positive_signals"></label><label>Negative signals<input name="negative_signals"></label><label class="warn"><input type="checkbox" name="consent_confirmed" class="inline">Participants consented; nothing invented or incentivized.</label><div class="actions"><button class="secondary smal" type="submit">Submit founder-reported result ↗</button><button class="ghost smal" type="button" data-revise="${esc(x.id)}">Change criteria (new version, retires results)</button></div></form>`;
      if (latest && !stopped && x.status === 'LOCKED' && x.result_evidence_id) html += `<div class="actions"><button class="ghost smal" data-revise="${esc(x.id)}">Repeat with new criteria (new version)</button></div>`;
      return html + '</div>';
    }).join('')).join('') || '<p class="hint">No experiments yet.</p>';
    div.querySelectorAll('[data-lock]').forEach(b => b.onclick = () => act(b, async () => {
      if (!confirm('Pre-register these criteria now? After locking they cannot be edited; a change creates a new version.')) return;
      await api('/projects/' + session.project_id + '/experiments/' + b.dataset.lock + '/lock', 'POST', {version: Number(b.dataset.v), criteria_hash: b.dataset.h, confirm: 'I_PREREGISTER_THESE_CRITERIA_BEFORE_COLLECTING_RESULTS'});
      suggestion = null; await refresh(); tell('Experiment pre-registered. Collect data now; submit results against the frozen criteria.', true); }, 'Locking…'));
    div.querySelectorAll('[data-revise]').forEach(b => b.onclick = () => {
      const x = experiments.filter(e => e.id === b.dataset.revise).pop(); const f = $('experiment-form'); f.classList.remove('hide');
      for (const k in x.payload) if (f[k] !== undefined) { if (f[k].type === 'checkbox') f[k].checked = Boolean(x.payload[k]); else f[k].value = x.payload[k] ?? ''; }
      f.dataset.revise = x.id; f.scrollIntoView({behavior: 'smooth'}); tell('Editing creates version ' + (x.version + 1) + '; results against v' + x.version + ' will stop counting.', true);
    });
    div.querySelectorAll('.result-form').forEach(f => f.addEventListener('submit', async (ev) => { ev.preventDefault(); await act(ev.submitter, async () => {
      const d = formData(f); d.version = Number(f.dataset.v); d.criteria_hash = f.dataset.h;
      const r = await api('/projects/' + session.project_id + '/experiments/' + f.dataset.sid + '/result', 'POST', d);
      suggestion = null; await refresh(); tell('Result: ' + r.outcome + ' (' + r.rate_pct + '%). ' + r.explanation, true); }, 'Saving…'); }));
  }
  // revise handler: the experiment form submit checks data-revise
  const expForm = $('experiment-form');
  expForm.addEventListener('submit', async (ev) => {
    if (!expForm.dataset.revise) return; ev.stopImmediatePropagation(); ev.preventDefault();
    await act(ev.submitter, async () => { const r = await api('/projects/' + session.project_id + '/experiments/' + expForm.dataset.revise + '/revise', 'POST', formData(expForm)); delete expForm.dataset.revise; expForm.classList.add('hide'); suggestion = null; await refresh(); tell('Version ' + r.version + ' drafted. ' + r.notice, true); }, 'Saving…');
  }, true);

  function renderPassport(pp, evidence) {
    const div = $('passport'), pill = $('passport-pill');
    if (!pp) { div.innerHTML = '<p class="hint">No validation run yet. The passport appears after the first evidence-based verdict.</p>'; pill.textContent = '—'; return; }
    const g = pp.verdict; pill.textContent = g.verdict; pill.className = 'pill ' + g.verdict;
    const evLink = (id) => `<a href="#ev-${esc(id)}"><code>${esc(short(id))}</code></a>`;
    const ids = (arr) => arr.length ? arr.map(evLink).join(' ') : '<span class="tag UNKNOWN">none</span>';
    div.innerHTML = `<div class="verdict ${esc(g.verdict)}">${esc(g.verdict)} <small>${esc(g.verdict_kind)}</small></div><p>${esc(g.headline)}</p><p><b>Conditional recommendation:</b> ${esc(g.recommendation)}</p><p class="small">${esc(g.never)} · brief v${pp.brief_version} · safety ${esc(pp.safety_status)} · discovery v${esc(g.inputs.discovery_version)} · report ${esc(short(pp.report_hash))}… · evidence snapshot ${esc(short(g.inputs.evidence_snapshot_hash))}… · ${esc(g.inputs.decision_policy)} · ${esc(stamp(pp.created_at))} · state ${esc(pp.state)}${pp.invalidated_reason ? ' (' + esc(pp.invalidated_reason) + ')' : ''}</p>`
      + '<table class="matrix"><tr><th>Dimension</th><th>Status</th><th>Supporting</th><th>Contradicting</th><th>Note</th></tr>' + Object.values(g.matrix).map(m => `<tr><td>${esc(m.label)}</td><td><span class="tag ${esc(m.status)}">${esc(m.status)}</span></td><td>${ids(m.supporting_ids)}</td><td>${ids(m.contradicting_ids)}</td><td class="small">${esc(m.note)}</td></tr>`).join('') + '</table>'
      + `<div class="two"><div class="field"><b>Top reasons FOR</b>${list(g.reasons_for)}</div><div class="field"><b>Top reasons AGAINST</b>${list(g.reasons_against)}</div></div>`
      + `<div class="field"><b>Strongest existing source</b><div>${g.strongest_source.id ? evLink(g.strongest_source.id) + ' ' + esc(g.strongest_source.kind) + ' — ' + esc(g.strongest_source.claim) + (g.strongest_source.source_url ? ' · <a href="' + esc(g.strongest_source.source_url) + '" target="_blank" rel="noopener noreferrer">source</a>' : '') : '<span class="tag BLOCK">SOURCE UNAVAILABLE</span>'}</div><div class="small">${esc(g.strongest_source.limitations)}</div></div>`
      + `<div class="field"><b>Unresolved critical assumptions</b>${list(g.unresolved_critical_assumptions, u => '<code>' + esc(u.claim_id) + '</code> <span class="tag ' + esc(u.status) + '">' + esc(u.status) + '</span> ' + esc(u.claim))}</div>`
      + `<div class="field"><b>Credible contradictions</b>${list(g.contradictions, c => esc(c.dimension) + ': ' + ids(c.supporting_ids) + ' vs ' + ids(c.contradicting_ids))}</div>`
      + `<div class="field"><b>Excluded evidence (not counted)</b>${list(g.excluded_evidence, x => evLink(x.id) + ' ' + esc(x.kind) + ' — ' + esc(x.reason))}</div>`
      + `<div class="field"><b>Pre-registered experiment outcomes</b>${list(g.experiment_outcomes, o => esc(short(o.experiment_id)) + ' v' + o.version + ' locked ' + esc(stamp(o.locked_at)) + ' · <b>' + esc(o.outcome) + '</b> ' + esc(o.rate_pct) + '% (n=' + esc(o.n) + ') vs success ≥ ' + esc(o.criteria.success_threshold_pct) + '% / adverse ≤ ' + esc(o.criteria.adverse_threshold_pct) + '% · evidence ' + evLink(o.evidence_id))}</div>`
      + `<div class="field"><b>Assumption risk register</b><table class="matrix"><tr><th>ID</th><th>Category</th><th>Crit.</th><th>Status</th><th>Claim</th><th>Provenance</th><th>For</th><th>Against</th></tr>${g.risk_register.map(r => `<tr><td><code>${esc(r.claim_id)}</code></td><td>${esc(r.category)}</td><td>${esc(r.criticality)}</td><td><span class="tag ${esc(r.assumption_status)}">${esc(r.assumption_status)}</span></td><td>${esc(r.exact_claim)}<div class="small">if false: ${esc(r.impact_if_false)}</div></td><td class="small">${esc(r.provenance)}</td><td>${ids(r.evidence_ids)}</td><td>${ids(r.contradictory_evidence_ids)}</td></tr>`).join('')}</table></div>`
      + `<div class="field"><b>What would change our mind?</b>${list(g.what_would_change_our_mind)}</div><div class="field"><b>Caveats</b>${list(g.caveats)}</div>`
      + `<div class="field"><b>Permissions granted by this verdict</b><div>continue research: ${g.permissions.continue_research} · build: ${g.permissions.build} · launch: ${g.permissions.launch} · external actions: ${g.permissions.external_actions}</div></div>`
      + `<div class="field"><b>Founder decision on this exact report</b><div>${pp.founder_decision ? esc(pp.founder_decision.action) + ' · scope ' + esc(pp.founder_decision.scope) + ' · ' + esc(stamp(pp.founder_decision.created_at)) + (pp.founder_decision.feedback ? ' · “' + esc(pp.founder_decision.feedback) + '”' : '') + (pp.founder_decision.acknowledged_risk ? ' · <span class="tag BLOCK">chose a different course than recommended</span>' : '') : '<span class="tag UNKNOWN">PENDING — no decision recorded</span>'}</div></div>`;
  }

  function renderLog(decisions, audit) {
    $('decision-list').innerHTML = decisions.length ? '<table class="matrix"><tr><th>When</th><th>Phase</th><th>Action</th><th>Scope</th><th>Run</th><th>Brief</th><th>Safety</th><th>Report hash</th><th>Gate said</th><th>Experiments at decision</th><th>Reason</th></tr>' + decisions.map(d => `<tr><td class="small">${esc(stamp(d.created_at))}</td><td>${esc(d.phase)}</td><td><b>${esc(d.action)}</b>${d.acknowledged_risk ? ' ⚠' : ''}</td><td>${esc(d.scope)}</td><td><code>${esc(short(d.phase_run_id))}</code> v${d.run_version}</td><td>v${d.brief_version}</td><td>${esc(d.safety_status)}</td><td><code>${esc(short(d.report_hash))}</code></td><td>${esc(d.gate_recommendation)}</td><td class="small">${esc(d.experiment_versions.map(x => short(x.id) + ' v' + x.version + ' ' + x.status).join(', ') || '—')}</td><td class="small">${esc(d.feedback || '—')}</td></tr>`).join('') + '</table>' : '<p class="hint">No founder decisions yet.</p>';
    $('audit-list').innerHTML = audit.length ? audit.map(e => `<div class="event"><strong>${esc(e.event.replace(/_/g, ' '))}</strong><span class="small">${esc(Object.entries(e.details).map(([k, v]) => k + '=' + (typeof v === 'object' ? JSON.stringify(v) : v)).join(' · ')).slice(0, 220)}</span><time>${esc(stamp(e.created_at))}</time></div>`).join('') : '<p>No events yet.</p>';
  }

  document.querySelectorAll('.tab').forEach(t => t.onclick = () => { document.querySelectorAll('.tab').forEach(x => x.classList.remove('active')); t.classList.add('active'); $('evidence-src').classList.toggle('hide', t.dataset.tab !== 'src'); $('evidence-cust').classList.toggle('hide', t.dataset.tab !== 'cust'); });
  $('create-form').addEventListener('submit', async (ev) => { ev.preventDefault(); await act(ev.submitter, async () => {
    const data = formData(ev.target);
    const project = await api('/projects', 'POST', data);
    session = {project_id: project.project_id, access_token: project.access_token};
    localStorage.setItem('founderos_session', JSON.stringify(session)); suggestion = null;
    await refresh(); navigate('idea',false);
    tell(project.prescreen.status === 'BLOCK' ? 'Workspace created, but the pre-screen found prohibited content: ' + project.prescreen.findings.map(f => f.rule_id).join(', ') + '. Click Refine to see the full safety assessment.' : 'Workspace created. Click "Refine idea" to begin.', project.prescreen.status !== 'BLOCK');
  }, 'Creating…'); });
  $('switch-project').onclick = () => { if (confirm('Start a new founder brief? The current project stays in SQLite; save its token first if you want to return.')) { localStorage.removeItem('founderos_session'); session = null; state = null; suggestion = null; refresh(); } };
  $('refine-btn').onclick = (ev) => act(ev.currentTarget, async () => { const t = performance.now(); const r = await api('/projects/' + session.project_id + '/refine', 'POST'); suggestion = null; await refresh(); $('refine-latency').textContent = 'observed ' + Math.round(performance.now() - t) + ' ms round-trip' + (r.latency_ms ? ' (model ' + r.latency_ms + ' ms)' : ' (model not called: safety block)'); tell('Brief v' + r.version + ' ready · safety: ' + r.safety.status + '. Review provenance tags and correct anything inferred.', r.safety.status !== 'BLOCK'); });
  $('discover-btn').onclick = (ev) => act(ev.currentTarget, async () => { const r = await api('/projects/' + session.project_id + '/phases/discover/run', 'POST'); suggestion = null; await refresh(); tell('Discovery v' + r.version + ' ready in ' + r.latency_ms + ' ms. Review the hypotheses and decide at the gate.', true); });
  $('validate-btn').onclick = (ev) => act(ev.currentTarget, async () => { const r = await api('/projects/' + session.project_id + '/phases/validate/run', 'POST'); await refresh(); tell('Verdict: ' + r.gate.verdict + ' (' + r.latency_ms + ' ms). Read the Decision Passport, then decide.', true); navigate('decision'); });
  $('evidence-src').addEventListener('submit', async (ev) => { ev.preventDefault(); await act(ev.submitter, async () => { const d = formData(ev.target); d.kind = 'SECONDARY_BACKGROUND'; const r = await api('/projects/' + session.project_id + '/evidence', 'POST', d); await refresh(); tell('Recorded ' + short(r.id) + ': ' + r.url_status + ' / ' + r.excerpt_status + (r.duplicate_of ? ' · DUPLICATE (not double-counted)' : '') + '. ' + r.limitations, true); }, 'Fetching…'); });
  $('evidence-cust').addEventListener('submit', async (ev) => { ev.preventDefault(); await act(ev.submitter, async () => { const r = await api('/projects/' + session.project_id + '/evidence', 'POST', formData(ev.target)); await refresh(); tell('Recorded ' + short(r.id) + ' as ' + r.independence + '. ' + r.limitations, true); }, 'Saving…'); });
  $('research-form').addEventListener('submit', async ev => {ev.preventDefault(); const b=ev.submitter; await act(b,()=>findResearch(ev.target.elements['query'].value),'Searching…');});
  initJourney();
  health(); setInterval(health, 20000);
  refresh().catch(e => { tell('Saved session could not be restored: ' + e.message); });
})();

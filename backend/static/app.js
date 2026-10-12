/* Synapt Supply Chain — Disruption Assistant console (plain JavaScript, no build step).
 * One file, one section per view. Every call goes to the FastAPI service under /api. */
'use strict';

const API = '/api';
const $ = (id) => document.getElementById(id);
const state = { meta: null, health: null, loaded: {}, analysis: null, network: null };

/* ------------------------------------------------------------------ helpers */
async function api(method, path, body) {
  const opt = { method, headers: {} };
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const res = await fetch(API + path, opt);
  if (res.status === 401) { window.location.href = '/login'; throw new Error('Sign in required'); }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const d = data && data.detail;
    throw new Error(typeof d === 'string' ? d : (d ? JSON.stringify(d) : `HTTP ${res.status}`));
  }
  return data;
}
const get = (p) => api('GET', p);
const post = (p, b = {}) => api('POST', p, b);

const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const md = (t) => (window.marked ? window.marked.parse(esc(t || '').replace(/&gt;/g, '>')) : `<p>${esc(t)}</p>`);
const num = (v, d = 0) => (v === null || v === undefined || Number.isNaN(+v) ? '—' : (+v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));
const money = (v) => {
  if (v === null || v === undefined) return '—';
  const a = Math.abs(v);
  return (v < 0 ? '−$' : '$') + (a >= 1e6 ? (a / 1e6).toFixed(2) + 'M' : a >= 1e3 ? (a / 1e3).toFixed(0) + 'K' : a.toFixed(0));
};
const pct = (v, d = 0) => (v === null || v === undefined ? '—' : (100 * v).toFixed(d) + '%');
const days = (v) => (v === null || v === undefined ? '—' : `${Math.round(v)} d`);
const signed = (v, f) => (v > 0 ? '+' : '') + f(v);
const pill = (txt, cls = '') => `<span class="pill ${cls}">${esc(txt)}</span>`;
const levelCls = (l) => ({ Critical: 'bad', High: 'warn', Elevated: 'info', Normal: 'ok', Strong: 'ok', Moderate: 'warn', Weak: 'bad' }[l] || '');
const prioCls = (l) => (String(l).startsWith('P1') ? 'bad' : String(l).startsWith('P2') ? 'warn' : String(l).startsWith('P3') ? 'info' : 'ok');
const yes = (b) => (b ? 'yes' : 'no');

function toast(msg) {
  const t = $('toast');
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, 3500);
}
/** Records an action in the server-side history (artifacts/history.json); never blocks the UI. */
function track(kind, title, summary = '', data = null, ref = null) {
  state.loaded.history = false;
  post('/history', { kind, title: String(title || kind).slice(0, 200), summary: String(summary || '').slice(0, 600), data, ref })
    .catch((e) => console.warn('history not saved:', e.message));
}
function busy(btn, on, label) {
  if (!btn) return;
  if (on) { btn.dataset.label = btn.textContent; btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> ${esc(label || 'Working')}`; }
  else { btn.disabled = false; btn.textContent = btn.dataset.label || btn.textContent; }
}
async function guarded(btn, label, fn) {
  busy(btn, true, label);
  try { return await fn(); } catch (e) { toast(e.message); console.error(e); return null; } finally { busy(btn, false); }
}
function bars(rows, fmt = (v) => num(v, 1), color = 'var(--brand)') {
  const max = Math.max(...rows.map((r) => Math.abs(r[1]) || 0), 1e-9);
  return `<div class="bars">${rows.map(([l, v, c]) => `<div class="bar-row"><span class="lbl" title="${esc(l)}">${esc(l)}</span>
    <div class="bar-track"><div class="bar-fill" style="width:${(100 * Math.abs(v || 0)) / max}%;background:${c || color}"></div></div>
    <span class="val">${fmt(v)}</span></div>`).join('')}</div>`;
}
function table(cols, rows, opts = {}) {
  if (!rows || !rows.length) return `<p class="muted">${esc(opts.empty || 'No rows.')}</p>`;
  const head = cols.map((c) => `<th>${esc(c[0])}</th>`).join('');
  const body = rows.map((r, i) => `<tr${opts.rowAttr ? ' ' + opts.rowAttr(r, i) : ''}>${cols.map((c) => `<td class="${c[2] || ''}">${c[1](r, i)}</td>`).join('')}</tr>`).join('');
  return `<table class="data-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}
function rangeBar(val, r, max) {
  if (!r) return '';
  const m = max || Math.max(r.p90 || val, val) * 1.1 || 1;
  return `<div class="range"><div class="band" style="left:${(100 * r.p10) / m}%;width:${(100 * (r.p90 - r.p10)) / m}%"></div>
    <div class="mark" style="left:calc(${(100 * val) / m}% - 1px)"></div></div>`;
}

/* ------------------------------------------------------------------ incident forms (built from /api/meta) */
const FIELDS = [
  ['disruption_type', 'Disruption type'], ['industry', 'Industry'], ['supplier_tier', 'Supplier tier'],
  ['supplier_region', 'Supplier region'], ['supplier_size', 'Supplier size'], ['has_backup_supplier', 'Backup supplier'],
  ['disruption_severity', 'Severity (1–5)'], ['response_type', 'Response strategy'], ['response_time_days', 'Response time (days)'],
];
const DEFAULT_INC = { disruption_type: 'Cyber Attack', industry: 'Electronics', supplier_tier: 2, supplier_region: 'Asia-Pacific',
  supplier_size: 'Large', has_backup_supplier: false, disruption_severity: 4, response_type: 'Inventory Buffer', response_time_days: 3 };

function incidentForm(container, prefix, { optional = false, values = DEFAULT_INC, fields = FIELDS } = {}) {
  const o = (state.meta && state.meta.options) || {};
  $(container).innerHTML = fields.map(([k, label]) => {
    const v = optional ? '' : values[k];
    let ctl;
    if (k === 'has_backup_supplier') {
      ctl = `<select id="${prefix}-${k}">${optional ? '<option value="">—</option>' : ''}<option value="true"${v === true ? ' selected' : ''}>Yes</option><option value="false"${v === false ? ' selected' : ''}>No</option></select>`;
    } else if (k === 'response_time_days') {
      ctl = `<input id="${prefix}-${k}" type="number" min="0" max="365" value="${optional ? '' : esc(v)}">`;
    } else {
      const opts = o[k] || [];
      ctl = `<select id="${prefix}-${k}">${optional ? '<option value="">—</option>' : ''}${opts.map((x) => `<option${String(x) === String(v) ? ' selected' : ''}>${esc(x)}</option>`).join('')}</select>`;
    }
    return `<label>${esc(label)}${ctl}</label>`;
  }).join('');
}
function readIncident(prefix, fields = FIELDS) {
  const out = {};
  for (const [k] of fields) {
    const el = $(`${prefix}-${k}`);
    if (!el || el.value === '') continue;
    if (k === 'has_backup_supplier') out[k] = el.value === 'true';
    else if (['supplier_tier', 'disruption_severity', 'response_time_days'].includes(k)) out[k] = parseInt(el.value, 10);
    else out[k] = el.value;
  }
  return out;
}

/* ------------------------------------------------------------------ navigation */
const VIEWS = {
  overview: ['Control Tower', 'Live picture of risk, incidents and learning across the supply base.'],
  cockpit: ['Incident Cockpit', 'A supervisor agent decides which agent runs next to investigate, predict, plan and audit a new disruption. No LLM in the loop: rules, Synapt MCP, ML and templates.'],
  search: ['Search & Ask', 'Synapt graph-RAG answers and hybrid search over 100,000 historical disruptions.'],
  graph: ['Knowledge Graph', 'What Synapt holds, the reasoning subgraph it walked, playbooks and graph insights.'],
  simulator: ['Impact Simulator', 'Predicted impact with P10–P90 ranges, drivers, counterfactuals and the root-cause chain.'],
  decision: ['Decision Studio', 'Response options compared in money, and triage across several incidents.'],
  warning: ['Early Warning', 'External signals and supplier risk scores for the next 90 days.'],
  portfolio: ['Portfolio & Network', 'Risk across the supplier portfolio and the knock-on effect of a supplier outage.'],
  incidents: ['Incident Desk', 'Open incidents, SLA clocks, escalation and tracked actions with real outcomes.'],
  quality: ['Quality & Learning', 'Evaluation results, model accuracy, operator feedback and Synapt answer quality.'],
  history: ['History', 'Everything done in the console, saved on the server so it is the same on every device.'],
};
const LOADERS = {};

function show(tab) {
  if (!VIEWS[tab]) tab = 'overview';
  document.querySelectorAll('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.view-panel').forEach((p) => p.classList.toggle('active', p.id === `view-${tab}`));
  $('view-title').textContent = VIEWS[tab][0];
  $('view-sub').textContent = VIEWS[tab][1];
  $('sidebar').classList.remove('open');
  if (location.hash !== `#${tab}`) history.replaceState(null, '', `#${tab}`);
  state.tab = tab;
  loadView(tab);
}
function loadView(tab) {
  if (!LOADERS[tab] || state.loaded[tab]) return;
  state.loaded[tab] = true;
  LOADERS[tab]().catch((e) => { state.loaded[tab] = false; if (state.ready) toast(e.message); });
}

/* ------------------------------------------------------------------ status */
async function refreshHealth() {
  try {
    const h = await get('/health');
    state.health = h;
    const s = h.synapt || {};
    const synOk = s.configured && h.status !== 'error' && !s.last_error;
    $('dot-synapt').className = 'dot ' + (synOk ? 'ok' : s.configured ? 'warn' : 'bad');
    $('st-synapt').textContent = !s.configured ? 'not configured' : h.status === 'error' ? 'unreachable' : s.last_error ? `error (${s.last_failed_tool || 'call'})` : 'connected';
    $('st-synapt').title = s.last_error || h.error || '';
    const m = h.models || {};
    $('dot-models').className = 'dot ' + (m.ready && !m.fallback ? 'ok' : m.ready ? 'warn' : 'bad');
    $('st-models').textContent = m.training ? 'training' : m.fallback ? 'cohort stats' : m.ready ? 'ready' : 'loading';
    const l = h.llm || {};
    $('dot-llm').className = 'dot ' + (l.configured ? 'ok' : 'warn');
    $('st-llm').textContent = l.configured ? (l.judge_model || l.model || 'configured') : 'not set';
    $('st-llm').title = l.base_url || '';
    $('provider-pill').textContent = `provider ${s.provider_id || '—'}`;
    $('boot-banner').hidden = h.status === 'ready';
    if (h.status === 'error') $('boot-banner').textContent = `Start-up failed: ${h.error || 'unknown error'}. Synapt is required; check backend/.env and restart.`;
    if (h.status === 'ready' && !state.ready) {  // backend just finished loading: (re)load the open view
      state.ready = true;
      if (state.tab) { state.loaded[state.tab] = false; loadView(state.tab); }
    } else if (h.status !== 'ready') {
      setTimeout(refreshHealth, 4000);
    }
    return h;
  } catch (e) {
    $('st-synapt').textContent = 'API down';
    $('dot-synapt').className = 'dot bad';
    return null;
  }
}

/* ================================================================== CONTROL TOWER */
LOADERS.overview = async () => {
  Tower.mount();
  const [ov, ins] = await Promise.all([get('/overview'), get('/insights')]);
  const fb = ov.feedback || {};
  $('ov-kpis').innerHTML = [
    ['Historical cases', num(ov.cases), 'indexed for search'],
    ['Suppliers monitored', num(ov.suppliers), 'early-warning scored'],
    ['Active signals', num(ov.signals_active), 'external alerts'],
    ['Open incidents', num(ov.incidents_open), `${num(ov.actions_open)} open actions`],
    ['SLA breached', num(ov.sla_breached), `${num(ov.escalated)} escalated`],
    ['Feedback', num(fb.total), `avg ${num(fb.avg_rating, 1)}★ · ${num(fb.with_outcomes)} outcomes`],
  ].map(([l, v, s]) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join('');
  $('badge-breached').hidden = !ov.sla_breached;
  $('badge-breached').textContent = ov.sla_breached || '';
  const lv = ov.early_warning || {};
  $('ov-levels').innerHTML = bars(['Critical', 'High', 'Elevated', 'Normal'].map((k) => [k, lv[k] || 0, `var(--${{ Critical: 'red', High: 'amber', Elevated: 'brand', Normal: 'green' }[k]})`]), (v) => num(v));
  const h = state.health || (await refreshHealth()) || {};
  const s = h.synapt || {};
  $('ov-health').innerHTML = `<dl class="stat-list">
    <dt>Synapt provider</dt><dd>${esc(s.provider_id || '—')}</dd>
    <dt>Synapt connection</dt><dd>${s.last_error ? pill('last call failed', 'bad') : pill('connected', 'ok')}</dd>
    <dt>Region tokens learned</dt><dd>${num(s.region_tokens_learned)}</dd>
    <dt>Dataset rows</dt><dd>${num((h.data || {}).rows)}</dd>
    <dt>Models trained</dt><dd>${esc((h.models || {}).trained_at || '—')}</dd>
    <dt>Judge LLM (evaluation only)</dt><dd>${esc((h.llm || {}).judge_model || '—')}</dd></dl>`;
  $('ov-risks').innerHTML = table([
    ['Supplier', (r) => `<b>${esc(r.supplier_name)}</b><div class="muted small">${esc(r.industry)} · ${esc(r.supplier_region)} · Tier ${r.supplier_tier}</div>`],
    ['Level', (r) => pill(r.level, levelCls(r.level))],
    ['90-day probability', (r) => pct(r.probability_90d), 'num'],
    ['Backup', (r) => yes(r.has_backup_supplier)],
    ['Main driver', (r) => esc(((r.drivers || [])[0] || {}).text || '—')],
    ['First action', (r) => esc((r.actions || [])[0] || '—')],
  ], (ov.top_risks || []).slice(0, 6));
  $('ov-bytype').innerHTML = bars((ins.by_type || []).map((r) => [r.key, r.avg_recovery]), (v) => `${num(v)} d`, 'var(--cyan)');
  $('ov-bysev').innerHTML = bars((ins.by_severity || []).map((r) => [`Severity ${r.key}`, r.avg_impact]), (v) => `${num(v, 1)}%`, 'var(--violet)');
};

/* ================================================================== INCIDENT COCKPIT */
const SAMPLE = 'Ransomware attack on our Tier 2 electronics supplier in Asia-Pacific has halted their ERP and shipments. No backup supplier is qualified. Severity 4.';

function agentCards() {
  const agents = (state.meta && state.meta.agents) || [];
  $('ck-agents').innerHTML = agents.map((a) => (a.id === 'supervisor'
    ? `<div class="agent supervisor" id="ag-supervisor"><div class="n">${esc(a.name)}</div>
    <div class="s">${esc(a.description)}</div><ol class="route-log" id="ck-route"></ol></div>`
    : `<div class="agent" id="ag-${a.id}"><div class="n">${esc(a.name.replace(' Agent', ''))}</div>
    <div class="s">${esc(a.description)}</div><div class="t"></div></div>`)).join('');
}
// One supervisor decision: which agent(s) run next and why
function routeItem(d) {
  const next = (d.next || []).map((n) => (n === 'finish' ? 'finish' : n.replace(/_/g, ' '))).join(' + ');
  return `<li><b>${esc(next)}</b> <span class="muted">· ${esc(d.reason)}</span></li>`;
}
function showRoute(d) {
  const el = $('ag-supervisor');
  if (!el) return;
  el.className = (d.next || []).includes('finish') ? 'agent supervisor done' : 'agent supervisor running';
  $('ck-route').insertAdjacentHTML('beforeend', routeItem(d));
}

async function streamAnalyze(payload, onEvent) {
  const res = await fetch(`${API}/analyze/stream`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* keep status */ }
    throw new Error(msg);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  let result = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const blocks = buf.split('\n\n');
    buf = blocks.pop() || '';
    for (const b of blocks) {
      const line = b.trim();
      if (!line.startsWith('data:')) continue;
      const ev = JSON.parse(line.slice(5).trim());
      if (ev.type === 'error') throw new Error(ev.error);
      if (ev.type === 'result') result = ev.data;
      else onEvent(ev);
    }
  }
  return result;
}

async function runAnalysis() {
  const desc = $('ck-desc').value.trim();
  const incident = readIncident('ckf');
  if (!desc && !incident.disruption_type) { toast('Describe the disruption or pick a disruption type.'); return; }
  agentCards();
  $('ck-error').hidden = true;
  $('ck-result').hidden = true;
  const btn = $('ck-run');
  busy(btn, true, 'Agents working');
  const t0 = performance.now();
  try {
    const payload = { description: desc || null, incident: Object.keys(incident).length ? incident : null,
      use_graph: $('ck-graph').checked, judge: $('ck-judge').checked, top_k: 8 };
    const r = await streamAnalyze(payload, (ev) => {
      if (ev.type === 'route') { showRoute(ev); return; }
      const el = $(`ag-${ev.agent}`);
      if (!el) return;
      if (ev.type === 'agent_start') el.className = 'agent running';
      if (ev.type === 'agent_done') {
        el.className = 'agent done';
        el.querySelector('.s').textContent = ev.summary || 'done';
        el.querySelector('.t').textContent = `${num(ev.ms)} ms`;
      }
    });
    if (!r) throw new Error('No result returned');
    state.analysis = r;
    renderAnalysis(r, performance.now() - t0);
    trackAnalysis(r, desc);
  } catch (e) {
    $('ck-error').textContent = e.message;
    $('ck-error').hidden = false;
  } finally { busy(btn, false); }
}

function trackAnalysis(r, desc, where = 'Incident Cockpit') {
  const inc = r.incident || {}; const pr = (r.impact || {}).priority || {}; const plan = r.plan || {};
  track('analysis', desc ? desc.slice(0, 120) : `${inc.disruption_type} · ${inc.industry || ''}`,
    `${pr.level || ''} · ${plan.primary_strategy || ''} · loss ${money((r.recovery || {}).predicted_revenue_loss)} · full recovery ${days((r.recovery || {}).predicted_full_days)} · fact-check ${(r.fact_check || {}).passed ? 'passed' : 'flagged'} (${where})`,
    { description: desc, incident: inc, priority: pr.level, strategy: plan.primary_strategy, judge: (r.judge || {}).verdict }, r.analysis_id);
}
function renderAnalysis(r, ms) {
  const imp = r.impact || {};
  const p = imp.prediction || {};
  const pr = imp.priority || {};
  const inc = r.incident || {};
  const cls = r.classification || {};
  const g = r.graph || {};
  const sm = r.search_meta || {};
  $('ck-head').innerHTML = `
    <div class="card"><div class="muted small">Priority</div><div class="big">${pill(pr.level || '—', prioCls(pr.level))}</div>
      <div class="muted">score ${num(pr.score, 1)}/100 · ${esc(pr.action_sla || '')}</div></div>
    <div class="card"><div class="muted small">Classified incident (${esc(cls.method || 'structured')})</div>
      <div class="chips">${['disruption_type', 'industry', 'supplier_region', 'supplier_size'].filter((k) => inc[k]).map((k) => pill(inc[k], 'info')).join('')}
      ${inc.supplier_tier ? pill('Tier ' + inc.supplier_tier) : ''}${inc.disruption_severity ? pill('Severity ' + inc.disruption_severity) : ''}
      ${inc.has_backup_supplier !== undefined && inc.has_backup_supplier !== null ? pill(inc.has_backup_supplier ? 'backup' : 'no backup', inc.has_backup_supplier ? 'ok' : 'bad') : ''}</div>
      ${(r.warnings || []).map((w) => `<div class="muted small">⚠ ${esc(w)}</div>`).join('')}</div>
    <div class="card"><div class="muted small">Evidence</div>
      <div class="big">${num((r.cases || []).length)} cases</div>
      <div class="muted">via ${esc(sm.semantic_source || '—')} · ${g.answer ? 'Synapt graph answer ✓' : 'no graph answer'} · ${num(ms / 1000, 1)} s</div></div>`;

  const fc = r.fact_check || {};
  $('ck-fc').innerHTML = fc.passed ? pill('fact-check passed', 'ok') : pill(`${(fc.final || []).length} unverified figure(s)`, 'warn');
  $('ck-briefing').innerHTML = md(r.summary) + ((fc.final || []).length ? `<div class="alert warn">${fc.final.map(esc).join('<br>')}</div>` : '');

  const plan = r.plan || {};
  $('ck-plan-method').textContent = plan.method || '';
  const acts = (a) => (a || []).map((x) => (typeof x === 'string' ? `<li>${esc(x)}</li>` : `<li>${esc(x.action)} <span class="muted small">· ${esc(x.owner || '')} · ${esc(x.timeframe || '')}</span></li>`)).join('');
  $('ck-plan').innerHTML = `<div class="chips">${pill('Primary: ' + (plan.primary_strategy || '—'), 'ok')}${pill('Secondary: ' + (plan.secondary_strategy || '—'))}
      ${plan.procedure ? pill('Synapt playbook: ' + plan.procedure.name, 'cyan') : ''}</div>
    <p class="muted">${esc(plan.rationale || '')}</p>
    <h4>Immediate</h4><ol class="steps">${acts(plan.immediate_actions)}</ol>
    ${(plan.short_term_actions || []).length ? `<h4>Short term</h4><ul class="steps">${acts(plan.short_term_actions)}</ul>` : ''}
    ${(plan.long_term_actions || []).length ? `<h4>Long term</h4><ul class="steps">${acts(plan.long_term_actions)}</ul>` : ''}
    ${(plan.risks || []).length ? `<h4>Risks</h4><ul class="steps">${acts(plan.risks)}</ul>` : ''}
    ${(plan.cited_cases || []).length ? `<div class="muted small">Cited cases: ${plan.cited_cases.map(esc).join(', ')}</div>` : ''}`;
  $('fb-strategy').innerHTML = ['', ...((state.meta && state.meta.options.response_type) || [])].map((s) => `<option${s === plan.primary_strategy ? ' selected' : ''}>${esc(s)}</option>`).join('');

  $('ck-pred').innerHTML = predictionBlock(p);
  const rec = r.recovery || {};
  const cp = rec.cohort_full_recovery_percentiles || {};
  $('ck-recovery').innerHTML = `<dl class="stat-list">
      <dt>Strategy</dt><dd>${esc(rec.strategy || '—')}</dd>
      <dt>Partial / full recovery</dt><dd>${days(rec.predicted_partial_days)} / ${days(rec.predicted_full_days)}</dd>
      <dt>Similar cohort (n=${num(rec.cohort_size)}) P25 · P50 · P75</dt><dd>${days(cp.p25)} · ${days(cp.p50)} · ${days(cp.p75)}</dd>
      <dt>Permanent supplier change</dt><dd>${pct(rec.supplier_change_probability)}</dd>
      <dt>Resilience</dt><dd>${rec.resilience ? `${num(rec.resilience.score, 1)}/100 ${pill(rec.resilience.band, levelCls(rec.resilience.band))}` : '—'}</dd></dl>
    <h4 style="margin-top:12px">Milestones</h4><div class="milestones">${(rec.milestones || []).map((m) => `<div><b>Day ${num(m.day)}</b> · ${esc(m.label)}</div>`).join('')}</div>
    ${(rec.resilience_actions || []).length ? `<h4 style="margin-top:12px">Resilience actions</h4><ul class="steps">${rec.resilience_actions.map((a) => `<li>${esc(a)}</li>`).join('')}</ul>` : ''}`;

  $('ck-cases').innerHTML = casesTable(r.cases || []);
  const st = (r.strategies || {}).strategies || [];
  $('ck-strats').innerHTML = `<div class="muted small">Cohort: ${esc(((r.strategies || {}).scope || []).join(', '))} · n=${num((r.strategies || {}).n)}</div>` + table([
    ['Strategy', (s) => `<b>${esc(s.strategy)}</b>`], ['Cases', (s) => num(s.cases), 'num'],
    ['Avg full recovery', (s) => days(s.avg_full_recovery), 'num'], ['Avg loss', (s) => money(s.avg_revenue_loss), 'num'],
    ['Feedback ×', (s) => num(s.feedback_boost, 2), 'num'], ['Score', (s) => num(s.effectiveness, 1), 'num'],
  ], st);

  const j = r.judge;
  $('ck-judge-out').innerHTML = j ? `<div class="chips">${pill(j.verdict, j.verdict === 'approve' ? 'ok' : 'warn')}${pill(`overall ${pct(j.overall_score)}`)}${pill(j.method === 'llm' ? 'LLM judge' : 'rule audit', 'violet')}</div>
    ${Object.entries(j.scores || {}).map(([k, v]) => `<div class="score-row"><span>${esc(k)}</span><div class="bar-track"><div class="bar-fill" style="width:${v * 20}%;background:${v >= 4 ? 'var(--green)' : v >= 3 ? 'var(--amber)' : 'var(--red)'}"></div></div><b>${v}</b></div>`).join('')}
    <p class="muted small">${esc(j.summary || '')}</p>
    ${(j.issues || []).length ? `<div class="alert warn">${j.issues.map(esc).join('<br>')}</div>` : ''}` : '<p class="muted">Judge skipped.</p>';

  $('ck-synapt-card').hidden = !g.answer && !g.error;
  const q = g.quality || {};
  $('ck-synapt').innerHTML = g.answer ? `<div class="chips">${pill(`confidence ${num(g.confidence, 2)}`, 'cyan')}${pill(`knowledge ${num(q.knowledge_confidence, 2)}`)}${pill(`procedural ${num(q.procedural_confidence, 2)}`)}${pill(`graph ${num(q.graph_confidence, 2)}`)}
      ${(g.trust || {}).degraded ? pill('degraded: ' + ((g.trust.reasons || []).join(', ')), 'warn') : ''}${pill(`${(g.nodes || []).length} nodes · ${(g.edges || []).length} edges`)}</div>
      <div class="md">${md(g.answer)}</div>` : `<p class="muted">${esc(g.error || '')}</p>`;
  $('ck-whatif-out').innerHTML = '';
  $('ck-inc-msg').textContent = '';
  $('fb-msg').textContent = '';
  $('ck-result').hidden = false;
}

function predictionBlock(p) {
  const rg = p.ranges || {};
  const rows = [
    ['Production impact', p.production_impact_pct, rg.production_impact_pct, (v) => `${num(v, 1)}%`, 100],
    ['Revenue loss', p.revenue_loss_usd, rg.revenue_loss_usd, money],
    ['Partial recovery', p.partial_recovery_days, rg.partial_recovery_days, days],
    ['Full recovery', p.full_recovery_days, rg.full_recovery_days, days],
  ];
  const sup = p.support || {};
  return rows.map(([l, v, r, f, max]) => `<div style="margin-bottom:10px"><div class="row" style="margin:0"><span>${l}</span><span class="spacer"></span><b>${f(v)}</b>
      <span class="muted small">${r ? `P10 ${f(r.p10)} – P90 ${f(r.p90)}` : ''}</span></div>${rangeBar(v, r, max)}</div>`).join('')
    + `<div class="chips">${pill(`risk ${p.risk_level || '—'} · ${pct(p.risk_probability)}`, levelCls(p.risk_level))}
      ${p.resilience_score ? pill(`resilience ${num(p.resilience_score.score, 1)} ${p.resilience_score.band}`, levelCls(p.resilience_score.band)) : ''}
      ${sup.level ? pill(`${sup.matching_cases} matching cases (${sup.level})`) : ''}</div>
      ${sup.warning ? `<div class="alert warn">${esc(sup.warning)}</div>` : ''}`;
}

function casesTable(cases) {
  const html = table([
    ['Case', (c) => `<b class="mono">${esc(c.disruption_id)}</b>`],
    ['Type', (c) => esc(c.disruption_type)], ['Industry', (c) => esc(c.industry)],
    ['Tier', (c) => c.supplier_tier, 'num'], ['Region', (c) => esc(c.supplier_region)],
    ['Sev', (c) => c.disruption_severity, 'num'], ['Backup', (c) => yes(c.has_backup_supplier)],
    ['Impact', (c) => `${num(c.production_impact_pct, 1)}%`, 'num'], ['Loss', (c) => money(c.revenue_loss_usd), 'num'],
    ['Response', (c) => esc(c.response_type)], ['Full rec.', (c) => days(c.full_recovery_days), 'num'],
    ['Source', (c) => (c.from_synapt ? pill('via Synapt', 'cyan') : pill(Object.keys(c.legs || {}).join('+') || 'local'))],
  ], cases, { rowAttr: (c, i) => `class="clickable" data-case="${i}"` });
  return html;
}
document.addEventListener('click', (e) => {
  const tr = e.target.closest('tr[data-case]');
  if (!tr) return;
  const next = tr.nextElementSibling;
  if (next && next.classList.contains('expand')) { next.remove(); return; }
  const tbl = tr.closest('table');
  const src = tbl.dataset.src === 'search' ? state.searchRows : (state.analysis || {}).cases;
  const c = (src || [])[+tr.dataset.case];
  if (!c) return;
  const ex = document.createElement('tr');
  ex.className = 'expand';
  ex.innerHTML = `<td colspan="20">${esc(c.text || '')}</td>`;
  tr.after(ex);
});

async function whatIfFromAnalysis(btn) {
  const inc = (state.analysis || {}).incident;
  if (!inc) return;
  const w = await guarded(btn, 'Simulating', () => post('/whatif', inc));
  if (w) $('ck-whatif-out').innerHTML = whatIfTable(w);
}
function whatIfTable(w) {
  const rows = [...(w.scenarios || []), ...(w.combined ? [w.combined] : [])];
  return table([
    ['If…', (s) => esc(s.label)],
    ['Full recovery', (s) => signed((s.delta || {}).full_recovery_days || 0, (v) => `${num(v)} d`), 'num'],
    ['Revenue loss', (s) => signed((s.delta || {}).revenue_loss_usd || 0, money), 'num'],
    ['Risk', (s) => signed((s.delta || {}).risk_probability || 0, (v) => `${num(100 * v, 1)} pt`), 'num'],
  ], rows);
}

async function openIncidentFromAnalysis(btn) {
  const id = (state.analysis || {}).analysis_id;
  if (!id) { toast('Run an analysis first.'); return; }
  const r = await guarded(btn, 'Opening', () => post('/incidents', { analysis_id: id }));
  if (r) track('incident', `Opened incident: ${r.title || r.priority || ''}`, `${r.priority || ''} · SLA ${r.sla_hours || '—'} h`, { incident_id: r.id, analysis_id: id }, r.id);
  if (r) { $('ck-inc-msg').innerHTML = `Opened ${pill(r.priority || 'incident', prioCls(r.priority))} — see Incident Desk.`; state.loaded.incidents = false; }
}

async function sendFeedback(btn) {
  const a = state.analysis;
  if (!a) return;
  const n = (id) => ($(id).value === '' ? null : +$(id).value);
  const body = { analysis_id: a.analysis_id, rating: +$('fb-rating').value, helpful: $('fb-helpful').value === '' ? null : $('fb-helpful').value === 'true',
    chosen_strategy: $('fb-strategy').value || null, comment: $('fb-comment').value || null,
    actual_full_recovery_days: n('fb-recovery'), actual_revenue_loss_usd: n('fb-loss'), actual_production_impact_pct: n('fb-impact') };
  const r = await guarded(btn, 'Sending', () => post('/feedback', body));
  if (r) track('feedback', `Rated analysis ${body.rating}★`, `${body.chosen_strategy || ''}${body.actual_full_recovery_days ? ` · actual recovery ${body.actual_full_recovery_days} d` : ''}${r.synapt_sent ? ' · sent to Synapt' : ''}`, body, a.analysis_id);
  if (r) $('fb-msg').textContent = `Saved${r.synapt_sent ? ' and sent to Synapt (trident_feedback)' : ''}.`;
}

/* ================================================================== SEARCH & ASK */
async function runAsk(btn) {
  const q = $('ask-q').value.trim() || $('ask-q').placeholder;
  const r = await guarded(btn, 'Asking Synapt', () => post('/ask', { question: q, top_k: 6, use_graph: true }));
  if (!r) return;
  const g = r.graph || {};
  track('ask', q, (r.answer || '').replace(/\s+/g, ' ').slice(0, 240), { question: q, method: r.method, answer: r.answer, sources: (r.sources || []).map((c) => c.disruption_id) });
  $('ask-out').innerHTML = `<div class="chips">${pill(r.method === 'synapt' ? 'answer: Synapt graph-RAG' : 'answer: ' + r.method, r.method === 'synapt' ? 'cyan' : 'warn')}
      ${g.confidence !== undefined ? pill(`confidence ${num(g.confidence, 2)}`) : ''}${pill(`sources via ${r.semantic_source}`)}</div>
    <div class="md">${md(r.answer)}</div>
    <details><summary class="muted small">${(r.sources || []).length} supporting cases</summary>${(r.sources || []).map((c) => `<p class="small"><b class="mono">${esc(c.disruption_id)}</b> ${esc(c.text || '')}</p>`).join('')}</details>`;
}
async function runSearch(btn) {
  const q = $('sr-q').value.trim() || $('sr-q').placeholder;
  const f = readIncident('srf', SEARCH_FIELDS);
  const filters = {};
  for (const [k, v] of Object.entries(f)) filters[k] = k === 'has_backup_supplier' ? v : [v];
  const r = await guarded(btn, 'Searching', () => post('/search', { query: q, top_k: +$('sr-k').value, mode: $('sr-mode').value, filters: Object.keys(filters).length ? filters : null }));
  if (!r) return;
  state.searchRows = r.results || [];
  $('sr-meta').innerHTML = `${num(r.count)} results · semantic leg: ${pill(r.semantic_source || '—', 'cyan')} · ${num(r.latency_ms)} ms
    ${(r.warnings || []).map((w) => `<div class="muted small">⚠ ${esc(w)}</div>`).join('')}`;
  track('search', q, `${r.count} results · ${$('sr-mode').value} · semantic leg ${r.semantic_source}`, { query: q, mode: $('sr-mode').value, filters, results: state.searchRows.slice(0, 10).map((c) => c.disruption_id) });
  $('sr-out').innerHTML = casesTable(state.searchRows).replace('<table class="data-table">', '<table class="data-table" data-src="search">');
}
const SEARCH_FIELDS = FIELDS.filter(([k]) => ['disruption_type', 'industry', 'supplier_region', 'supplier_tier', 'has_backup_supplier'].includes(k));

/* ================================================================== KNOWLEDGE GRAPH */
LOADERS.graph = async () => {
  const k = await get('/synapt/knowledge');
  const s = k.stats || {};
  $('kg-stats').innerHTML = [['Documents', s.doc_count], ['Graph nodes', s.nodes], ['Chunks', s.chunks], ['Entities', s.entities],
    ['Procedures', s.procedures], ['Edges', s.edges]].map(([l, v]) => `<div class="kpi"><div class="l">${l}</div><div class="v">${num(v)}</div><div class="s">${esc(k.provider_id || '')}</div></div>`).join('');
  $('kg-ins-key').innerHTML = (k.insights || []).map((i) => `<option value="${esc(i.key)}" title="${esc(i.description)}">${esc(i.title)}</option>`).join('');
  $('kg-proc-type').innerHTML = ((state.meta && state.meta.options.disruption_type) || []).map((t) => `<option>${esc(t)}</option>`).join('');
};
async function runGraph(btn) {
  const q = $('kg-q').value.trim() || $('kg-q').placeholder;
  const g = await guarded(btn, 'Walking the graph', () => post('/synapt/graph', { question: q, hops: null }));
  if (!g) return;
  drawGraph(g.nodes || [], g.edges || []);
  track('graph', q, `confidence ${num(g.confidence, 2)} · ${(g.nodes || []).length} nodes · ${(g.answer || '').replace(/\s+/g, ' ').slice(0, 160)}`, { question: q, answer: g.answer, confidence: g.confidence });
  const qq = g.quality || {};
  $('kg-answer').innerHTML = md(g.answer || '_No answer._');
  $('kg-quality').innerHTML = `<div class="chips">${pill(`confidence ${num(g.confidence, 2)}`, 'cyan')}${pill(`graph ${num(qq.graph_confidence, 2)}`)}${pill(`knowledge ${num(qq.knowledge_confidence, 2)}`)}
    ${pill(`intent ${g.intent || '—'}`)}${(g.trust || {}).degraded ? pill('degraded', 'warn') : pill('trusted', 'ok')}${pill(`${num(g.latency_s, 1)} s`)}</div>`;
}
function drawGraph(nodes, edges) {
  const svg = $('kg-svg');
  if (!nodes.length) { svg.innerHTML = '<text x="20" y="30">No subgraph returned.</text>'; return; }
  const cx = 260; const cy = 210;
  const byHop = {};
  nodes.slice(0, 60).forEach((n) => { (byHop[n.hop || 0] = byHop[n.hop || 0] || []).push(n); });
  const pos = {};
  const color = { Procedure: 'var(--green)', Step: 'var(--green)', Chunk: 'var(--ink-3)', Document: 'var(--ink-3)', Entity: 'var(--brand)', Concept: 'var(--violet)' };
  Object.entries(byHop).forEach(([hop, list]) => {
    const r = +hop === 0 ? (list.length > 1 ? 55 : 0) : 55 + 70 * +hop;
    list.forEach((n, i) => { const a = (2 * Math.PI * i) / list.length + +hop * 0.4; pos[n.id] = [cx + Math.min(r, 190) * Math.cos(a), cy + Math.min(r, 190) * Math.sin(a), n]; });
  });
  const lines = edges.filter((e) => pos[e.source] && pos[e.target]).map((e) => {
    const [x1, y1] = pos[e.source]; const [x2, y2] = pos[e.target];
    return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="var(--line)" stroke-width="1.2"><title>${esc(e.type)}</title></line>`;
  }).join('');
  const dots = Object.values(pos).map(([x, y, n]) => `<g><circle cx="${x}" cy="${y}" r="${5 + 8 * (n.relevance || 0)}" fill="${color[n.type] || 'var(--cyan)'}" opacity=".85"><title>${esc(n.type)} · ${esc(n.description || n.name)}</title></circle>
    ${(n.relevance || 0) > 0.6 ? `<text x="${x + 9}" y="${y + 3}">${esc((n.name || '').slice(0, 26))}</text>` : ''}</g>`).join('');
  svg.innerHTML = [1, 2, 3].map((h) => `<circle cx="${cx}" cy="${cy}" r="${Math.min(55 + 70 * h, 190)}" fill="none" stroke="var(--line)" stroke-dasharray="3 4"/>`).join('') + lines + dots;
  const types = [...new Set(nodes.map((n) => n.type))];
  $('kg-legend').innerHTML = `${nodes.length} nodes, ${edges.length} edges; rings = hops from the question. Types: ${types.map(esc).join(', ')}`;
}
async function runProcedure(btn) {
  const t = $('kg-proc-type').value;
  const r = await guarded(btn, 'Loading', () => get(`/synapt/procedures?query=${encodeURIComponent(`Respond to a ${t} disruption`)}`));
  if (!r) return;
  const p = (r.procedures || []).find((x) => (x.name || '').toLowerCase().includes(t.toLowerCase())) || (r.procedures || [])[0];
  if (p) track('playbook', p.name, `${(p.steps || []).length} steps from the Synapt Procedure Store`, { name: p.name, steps: (p.steps || []).map((x) => x.text) });
  $('kg-proc-out').innerHTML = p ? `<h4>${esc(p.name)}</h4><p class="muted small">${esc(p.intent || '')}</p><ol class="steps">${(p.steps || []).map((s) => `<li>${esc(s.text)}</li>`).join('')}</ol>` : '<p class="muted">No playbook found.</p>';
}
async function runInsight(btn) {
  const key = $('kg-ins-key').value;
  const r = await guarded(btn, 'Running', () => get(`/synapt/insights/${encodeURIComponent(key)}`));
  if (!r) return;
  const rows = r.rows || [];
  const cols = rows.length ? Object.keys(rows[0]).map((c) => [c, (x) => esc(typeof x[c] === 'object' ? JSON.stringify(x[c]) : x[c])]) : [];
  track('insight', r.title || key, `${rows.length} rows`, { key, rows: rows.slice(0, 20) });
  $('kg-ins-out').innerHTML = `<p class="muted small">${esc(r.description || '')}</p>` + table(cols, rows) + (r.cypher ? `<details><summary class="muted small">Cypher</summary><code>${esc(r.cypher)}</code></details>` : '');
}

/* ================================================================== SIMULATOR */
LOADERS.simulator = async () => { incidentForm('sim-fields', 'sim'); };
async function runSimulator(btn) {
  const inc = readIncident('sim');
  const r = await guarded(btn, 'Predicting', () => Promise.all([post('/predict', inc), post('/explain', inc), post('/whatif', inc), post('/rootcause', inc)]));
  if (!r) return;
  const [p, e, w, rc] = r;
  $('sim-pred').innerHTML = predictionBlock(p.prediction || {});
  const ex = ((e.explanation || {}).full_recovery_days || {});
  $('sim-explain').innerHTML = `<p class="muted small">Contribution of each input to the predicted full recovery (days) vs a typical case.</p>`
    + bars((ex.local || []).slice(0, 8).map((x) => [`${x.label}: ${x.value}`, x.contribution, x.contribution > 0 ? 'var(--red)' : 'var(--green)']), (v) => signed(v, (z) => `${num(z, 1)} d`));
  $('sim-whatif').innerHTML = whatIfTable(w);
  $('sim-root').innerHTML = `<div class="chips">${pill('Root cause: ' + (rc.root_cause || '—'), 'bad')}</div><div class="milestones">${(rc.chain || []).map((c) => `<div><b>${esc(c.when)}</b> · ${esc(c.stage)} <span class="muted small">(${esc(c.kind)}) ${esc(c.detail)}</span></div>`).join('')}</div>
    <h4 style="margin-top:12px">Made it worse</h4><ul class="steps">${(rc.contributing || []).map((c) => `<li>${esc(c.text)}</li>`).join('') || '<li class="muted">—</li>'}</ul>
    <h4>Helped</h4><ul class="steps">${(rc.mitigating || []).map((c) => `<li>${esc(c.text)}</li>`).join('') || '<li class="muted">—</li>'}</ul>`;
  $('sim-out').hidden = false;
  const pp = p.prediction || {};
  track('simulation', `${inc.disruption_type} · ${inc.industry} · Tier ${inc.supplier_tier} · severity ${inc.disruption_severity}`,
    `impact ${num(pp.production_impact_pct, 1)}% · loss ${money(pp.revenue_loss_usd)} · full recovery ${days(pp.full_recovery_days)} · risk ${pp.risk_level} · root cause ${rc.root_cause}`,
    { incident: inc, prediction: pp });
}

/* ================================================================== DECISION STUDIO */
LOADERS.decision = async () => { incidentForm('dec-fields', 'dec', { fields: FIELDS.filter(([k]) => k !== 'response_type') }); };
async function runDecision(btn) {
  const inc = readIncident('dec');
  const d = await guarded(btn, 'Comparing', () => post('/decision', { incident: inc, costs: null }));
  if (!d) return;
  const rec = (d.scenarios || []).find((s) => s.key === d.recommended) || {};
  track('decision', `${inc.disruption_type} · ${inc.industry} · severity ${inc.disruption_severity}`, `Recommended: ${rec.label || d.recommended} · net benefit ${money(rec.net_benefit_usd)}`,
    { incident: inc, recommended: d.recommended, scenarios: (d.scenarios || []).map((x) => ({ option: x.label, loss: x.revenue_loss_usd, net_benefit: x.net_benefit_usd })) });
  $('dec-out').innerHTML = `<div class="card"><h3>Recommended: ${esc(rec.label || d.recommended)} ${pill('net benefit ' + money(rec.net_benefit_usd), 'ok')}</h3>
    <p class="muted">${esc(d.why || '')}</p>${d.hint ? `<div class="alert info">${esc(d.hint)}</div>` : ''}
    <div class="table-container">${table([
      ['Option', (s) => `<b>${esc(s.label)}</b>${s.key === d.recommended ? ' ' + pill('recommended', 'ok') : ''}${s.hypothetical ? ' ' + pill('hypothetical', 'violet') : ''}`],
      ['Outage', (s) => days(s.outage_days), 'num'], ['Full recovery', (s) => days(s.full_recovery_days), 'num'],
      ['Revenue loss', (s) => money(s.revenue_loss_usd), 'num'], ['Mitigation cost', (s) => money(s.mitigation_cost_usd), 'num'],
      ['Net benefit', (s) => money(s.net_benefit_usd), 'num'], ['Days saved', (s) => num(s.days_saved), 'num'],
      ['ROI', (s) => (s.roi === null || s.roi === undefined ? '—' : `${num(s.roi, 1)}×`), 'num'],
    ], d.scenarios || [])}</div>
    <details><summary class="muted small">Cost assumptions</summary><pre class="mono small">${esc(JSON.stringify(d.assumptions, null, 1))}</pre></details></div>`;
}
async function runTriage(btn) {
  const lines = $('tri-in').value.split('\n').map((l) => l.trim()).filter(Boolean);
  const incidents = lines.map((l, i) => {
    const [t, ind, tier, reg, sev, bk] = l.split(',').map((x) => x.trim());
    return { disruption_type: t, industry: ind, supplier_tier: +tier || null, supplier_region: reg, disruption_severity: +sev || null,
      has_backup_supplier: /^y/i.test(bk || ''), label: `#${i + 1} ${t}` };
  });
  const r = await guarded(btn, 'Ranking', () => post('/prioritize', { incidents }));
  if (!r) return;
  track('triage', `Prioritised ${(r.ranked || []).length} incidents`, (r.ranked || []).map((x) => `${x.rank}. ${x.label} ${x.priority.level.split(' ')[0]}`).join(' · '), { incidents, ranked: (r.ranked || []).map((x) => ({ rank: x.rank, label: x.label, priority: x.priority.level, score: x.priority.score })) });
  $('tri-out').innerHTML = table([
    ['Rank', (x) => x.rank, 'num'], ['Incident', (x) => esc(x.label)], ['Priority', (x) => pill(x.priority.level, prioCls(x.priority.level))],
    ['Score', (x) => num(x.priority.score, 1), 'num'], ['SLA', (x) => esc(x.priority.action_sla)],
    ['Impact', (x) => `${num(x.prediction.production_impact_pct, 1)}%`, 'num'], ['Loss', (x) => money(x.prediction.revenue_loss_usd), 'num'],
    ['Full recovery', (x) => days(x.prediction.full_recovery_days), 'num'],
  ], r.ranked || []);
}

/* ================================================================== EARLY WARNING */
LOADERS.warning = async () => { await Promise.all([loadSignals(), loadEarlyWarning()]); };
async function loadSignals() {
  const sigs = await get('/signals');
  $('sig-list').innerHTML = table([
    ['Signal', (s) => `<b>${esc(s.headline)}</b><div class="muted small">${esc(s.source)} · ${new Date(s.ts * 1000).toLocaleString()}</div>`],
    ['Type', (s) => esc(s.disruption_type || '—')], ['Region', (s) => esc(s.region || '—')], ['Severity', (s) => num(s.severity), 'num'],
    ['Active', (s) => `<button class="btn small ${s.active ? '' : 'ghost'}" data-sig-toggle="${esc(s.id)}" data-active="${s.active ? 1 : 0}">${s.active ? 'Active' : 'Off'}</button>`],
    ['Synapt', (s) => (s.synapt_sent ? pill('sent', 'cyan') : `<button class="btn small ghost" data-sig-synapt="${esc(s.id)}">Send</button>`)],
  ], sigs || [], { empty: 'No signals yet. Add one or fetch live hazards.' });
}
async function loadEarlyWarning() {
  const r = await post('/early-warning', { csv: null });
  $('ew-method').textContent = r.method || '';
  $('ew-levels').innerHTML = `<div class="chips">${Object.entries(r.levels || {}).map(([k, v]) => pill(`${k}: ${v}`, levelCls(k))).join('')}</div>`;
  $('ew-list').innerHTML = table([
    ['Supplier', (s) => `<b>${esc(s.supplier_name)}</b><div class="muted small">${esc(s.industry)} · ${esc(s.supplier_region)} · Tier ${s.supplier_tier}</div>`],
    ['Level', (s) => pill(s.level, levelCls(s.level))], ['Score', (s) => num(s.score, 1), 'num'],
    ['Trend', (s) => signed(s.trend || 0, (v) => num(v, 1)), 'num'], ['90-day prob.', (s) => pct(s.probability_90d), 'num'],
    ['Drivers', (s) => (s.drivers || []).slice(0, 2).map((d) => `<div class="small">${esc(d.text)}</div>`).join('')],
    ['Worst case', (s) => (s.worst_case ? `${esc(s.worst_case.disruption_type)} · ${money(s.worst_case.revenue_loss_usd)} · ${days(s.worst_case.full_recovery_days)}` : '—')],
  ], r.suppliers || []);
}
document.addEventListener('click', async (e) => {
  const t = e.target.closest('[data-sig-toggle]');
  const s = e.target.closest('[data-sig-synapt]');
  if (t) { await api('PATCH', `/signals/${t.dataset.sigToggle}`, { active: t.dataset.active !== '1' }).catch((x) => toast(x.message)); await loadSignals(); loadEarlyWarning(); }
  if (s) { await guarded(s, 'Sending', () => post(`/signals/${s.dataset.sigSynapt}/synapt`, {})); await loadSignals(); }
});
async function addSignal(btn) {
  const h = $('sig-head').value.trim();
  if (h.length < 8) { toast('Headline must be at least 8 characters.'); return; }
  const r = await guarded(btn, 'Adding', () => post('/signals', { headline: h, detail: '', send_to_synapt: $('sig-synapt').checked }));
  if (r) track('signal', h, `${r.disruption_type || 'unclassified'} · ${r.region || 'unknown region'}${$('sig-synapt').checked ? ' · sent to Synapt' : ''}`, r, r.id);
  if (r) { $('sig-head').value = ''; $('sig-msg').textContent = `Added: ${r.disruption_type || 'unclassified'} in ${r.region || 'unknown region'}.`; await loadSignals(); loadEarlyWarning(); }
}
async function fetchLive(btn) {
  const r = await guarded(btn, 'Fetching', () => post('/signals/fetch-live', {}));
  if (r) track('signal', 'Fetched live hazard alerts (GDACS)', `${r.added ?? r.count ?? 0} new alert(s)`);
  if (r) { $('sig-msg').textContent = `Live feed: ${r.added ?? r.count ?? 0} new alert(s).`; await loadSignals(); loadEarlyWarning(); }
}

/* ================================================================== PORTFOLIO & NETWORK */
LOADERS.portfolio = async () => {
  const n = await post('/network', { csv: null });
  state.network = n;
  $('nw-supplier').innerHTML = (n.nodes || []).filter((x) => x.kind === 'supplier').map((x) => `<option>${esc(x.name)}</option>`).join('');
  $('nw-type').innerHTML = '<option value="">Most likely disruption</option>' + ((state.meta && state.meta.options.disruption_type) || []).map((t) => `<option>${esc(t)}</option>`).join('');
  $('nw-meta').innerHTML = `${num(n.products)} products · single-sourced: ${(n.single_sourced_products || []).map((p) => pill(p, 'warn')).join(' ') || 'none'} · ${esc(n.note || '')}`;
};
async function loadPortfolioSample(btn) {
  await guarded(btn, 'Loading', async () => {
    const res = await fetch(`${API}/portfolio/sample`);
    $('pf-csv').value = await res.text();
  });
}
async function runPortfolio(btn) {
  if (!$('pf-csv').value.trim()) await loadPortfolioSample();
  const r = await guarded(btn, 'Scoring', () => post('/portfolio', { csv: $('pf-csv').value, severity: +$('pf-sev').value }));
  if (!r) return;
  const s = r.summary || {};
  track('portfolio', `Scored ${r.count} suppliers (severity ${r.severity_assumed})`, `avg risk index ${num(s.avg_risk_index, 1)} · ${s.critical_or_high} critical/high · expected loss ${money(s.expected_loss_total)}`,
    { summary: s, top: (r.suppliers || []).slice(0, 5).map((x) => ({ supplier: x.supplier_name, band: x.band, risk_index: x.risk_index })) });
  $('pf-summary').innerHTML = `<div class="chips">${pill(`${r.count} suppliers`)}${pill(`avg risk index ${num(s.avg_risk_index, 1)}`)}${pill(`${s.critical_or_high} critical/high`, 'bad')}${pill(`${s.without_backup} without backup`, 'warn')}${pill(`expected loss ${money(s.expected_loss_total)}`)}</div>`;
  const hm = r.heatmap || {};
  const cell = (reg, t) => (hm.cells || []).find((c) => c.region === reg && c.tier === t) || {};
  const shade = (v) => (v === null || v === undefined ? 'var(--surface-2)' : v >= 70 ? 'var(--red-soft)' : v >= 50 ? 'var(--amber-soft)' : v >= 30 ? 'var(--brand-soft)' : 'var(--green-soft)');
  $('pf-heat').innerHTML = `<h4>Risk heat-map (region × tier)</h4><div class="heat" style="grid-template-columns:120px repeat(${(hm.tiers || []).length},1fr)">
    <div></div>${(hm.tiers || []).map((t) => `<div class="hdr">Tier ${t}</div>`).join('')}
    ${(hm.regions || []).map((reg) => `<div class="hdr" style="text-align:left;align-self:center">${esc(reg)}</div>${(hm.tiers || []).map((t) => { const c = cell(reg, t); return `<div class="cell" style="background:${shade(c.avg_risk_index)}" title="${esc((c.names || []).join(', '))}">${c.suppliers ? `<b>${num(c.avg_risk_index)}</b><div class="small">${c.suppliers} sup.</div>` : '·'}</div>`; }).join('')}`).join('')}</div>`;
  $('pf-list').innerHTML = table([
    ['Supplier', (x) => `<b>${esc(x.supplier_name)}</b><div class="muted small">${esc(x.products || '')}</div>`],
    ['Band', (x) => pill(x.band, levelCls(x.band))], ['Risk index', (x) => num(x.risk_index, 1), 'num'],
    ['Exp. loss', (x) => money(x.expected_revenue_loss_usd), 'num'], ['Exp. recovery', (x) => days(x.expected_full_recovery_days), 'num'],
  ], (r.suppliers || []).slice(0, 15));
}
async function runOffline(btn) {
  const r = await guarded(btn, 'Simulating', () => post('/network/offline', { supplier: $('nw-supplier').value, csv: null, disruption_type: $('nw-type').value || null }));
  if (!r) return;
  const total = (r.affected || []).reduce((a, x) => a + (x.revenue_at_risk_usd || 0), 0);
  track('network', `${r.supplier} offline (${r.disruption_type})`, `shortage ${days(r.shortage_days)} · revenue at risk ${money(total)} · ${(r.affected || []).length} products`, { supplier: r.supplier, disruption_type: r.disruption_type, revenue_at_risk: total });
  $('nw-out').innerHTML = `<div class="chips">${pill(r.disruption_type, 'info')}${pill(`full recovery ${days(r.full_recovery_days)}`)}${pill(`inventory cover ${days(r.inventory_days)}`)}${pill(`shortage ${days(r.shortage_days)}`, r.shortage_days > 0 ? 'bad' : 'ok')}${pill(`revenue at risk ${money(total)}`, 'bad')}</div>`
    + table([
      ['Product', (x) => `<b>${esc(x.product)}</b>`], ['Line', (x) => esc(x.line)], ['Customer', (x) => esc(x.customer)],
      ['Share from supplier', (x) => pct(x.share_from_supplier), 'num'], ['Other suppliers', (x) => esc((x.other_suppliers || []).join(', ') || 'none — single-sourced')],
      ['Lost orders', (x) => num(x.lost_orders), 'num'], ['Revenue at risk', (x) => money(x.revenue_at_risk_usd), 'num'],
    ], r.affected || [], { empty: 'No products depend on this supplier.' });
}

/* ================================================================== INCIDENT DESK */
LOADERS.incidents = async () => { await loadIncidents(); };
async function loadIncidents() {
  const list = await get('/incidents');
  if (!list || !list.length) { $('inc-list').innerHTML = '<div class="card muted">No incidents yet. Open one from the Incident Cockpit or load demo incidents.</div>'; return; }
  $('inc-list').innerHTML = list.map((i) => {
    const p = i.prediction || {};
    const left = i.remaining_hours;
    return `<div class="card"><div class="inc-card"><div>
      <h3>${pill(i.priority, prioCls(i.priority))} ${esc(i.title)} ${pill(i.status, i.status === 'resolved' ? 'ok' : 'info')} ${i.breached ? pill('SLA breached', 'bad') : ''} ${i.escalated ? pill('escalated', 'warn') : ''}</h3>
      <div class="muted small">Owner ${esc(i.owner)} · opened ${new Date(i.ts * 1000).toLocaleString()} · SLA ${i.sla_hours} h · ${left >= 0 ? `${num(left, 1)} h left` : `${num(-left, 1)} h overdue`}</div>
      <div class="chips">${pill(`impact ${num(p.production_impact_pct, 1)}%`)}${pill(`loss ${money(p.revenue_loss_usd)}`)}${pill(`full recovery ${days(p.full_recovery_days)}`)}</div>
      <div class="inc-actions">${(i.actions || []).map((a) => `<div class="action ${a.status === 'done' ? 'done' : ''}">
          <input type="checkbox" data-action="${esc(a.id)}" ${a.status === 'done' ? 'checked' : ''} aria-label="Done">
          <span>${esc(a.title)} <span class="muted small">· ${esc(a.owner)}</span></span>
          <span class="muted small">${a.actual_recovery_days ? `actual ${days(a.actual_recovery_days)}` : a.due_ts ? 'due ' + new Date(a.due_ts * 1000).toLocaleDateString() : ''}</span></div>`).join('')}</div>
      <div class="row"><input placeholder="New action" data-new-action="${esc(i.id)}"><button class="btn small" data-add-action="${esc(i.id)}">Add</button></div>
    </div><div>
      <h4>Escalation chain</h4><div class="esc">${(i.escalation_chain || []).map((e) => pill(`${e.role} · +${e.after_hours} h`, e.notified ? 'warn' : '')).join('')}</div>
      <h4 style="margin-top:12px">Status</h4>
      <div class="row wrap">${['open', 'mitigating', 'resolved'].map((s) => `<button class="btn small ${i.status === s ? 'primary' : 'ghost'}" data-inc-status="${esc(i.id)}" data-status="${s}">${s}</button>`).join('')}</div>
      <p class="muted small">${num(i.actions_done)}/${num((i.actions || []).length)} actions done</p>
    </div></div></div>`;
  }).join('');
}
document.addEventListener('change', async (e) => {
  const cb = e.target.closest('[data-action]');
  if (!cb) return;
  const body = { status: cb.checked ? 'done' : 'open' };
  if (cb.checked) {
    const rec = prompt('Actual recovery days for this action (optional, feeds retraining):', '');
    if (rec) body.actual_recovery_days = +rec;
  }
  await api('PATCH', `/actions/${cb.dataset.action}`, body).catch((x) => toast(x.message));
  track('incident', `Action ${cb.checked ? 'completed' : 'reopened'}: ${cb.closest('.action').innerText.trim().slice(0, 120)}`, body.actual_recovery_days ? `actual recovery ${body.actual_recovery_days} d` : '', body, cb.dataset.action);
  loadIncidents();
});
document.addEventListener('click', async (e) => {
  const add = e.target.closest('[data-add-action]');
  const st = e.target.closest('[data-inc-status]');
  if (add) {
    const inp = document.querySelector(`[data-new-action="${add.dataset.addAction}"]`);
    if (!inp.value.trim()) return;
    await post(`/incidents/${add.dataset.addAction}/actions`, { title: inp.value.trim(), owner: 'Operations', due_hours: 24 }).catch((x) => toast(x.message));
    track('incident', `Action added: ${inp.value.trim()}`, 'owner Operations · due in 24 h', null, add.dataset.addAction);
    loadIncidents();
  }
  if (st) {
    await api('PATCH', `/incidents/${st.dataset.incStatus}`, { status: st.dataset.status }).catch((x) => toast(x.message));
    track('incident', `Incident marked ${st.dataset.status}`, st.closest('.card').querySelector('h3').innerText.replace(/\s+/g, ' ').slice(0, 160), null, st.dataset.incStatus);
    loadIncidents();
  }
});

/* ================================================================== QUALITY & LEARNING */
LOADERS.quality = async () => { await Promise.all([loadEval(), loadModels(), loadFeedback(), loadSynaptQuality()]); };
const METRIC_LABEL = { AnswerRelevancyMetric: 'Answer relevancy', FaithfulnessMetric: 'Faithfulness', ContextualRelevancyMetric: 'Contextual relevancy' };
async function loadEval() {
  const [st, r] = await Promise.all([get('/evaluate/status'), get('/evaluate/results').catch(() => null)]);
  $('ev-status').textContent = st.running ? `running ${st.progress}/${st.total} (${st.current || ''})` : st.error ? `error: ${st.error}` : '';
  if (st.running) setTimeout(() => loadEval().catch(() => {}), 5000);
  if (!r || !r.summary) { $('ev-summary').innerHTML = '<p class="muted">No evaluation results yet.</p>'; return; }
  const s = r.summary;
  const deep = Object.entries(s.deepeval || {}).map(([k, v]) => [METRIC_LABEL[k] || k, v, v >= 0.8 ? 'var(--green)' : v >= 0.6 ? 'var(--amber)' : 'var(--red)']);
  const det = [['Classification accuracy', s.classification_accuracy], ['Fact-check pass rate', s.fact_check_pass_rate], ['Runtime rule audit', s.rule_audit_overall],
    ['LLM judge (overall)', s.llm_judge_overall], ['Retrieval type precision', s.retrieval_type_precision], ['Guardrail suite', s.guardrail_pass_rate]].filter((x) => x[1] !== null && x[1] !== undefined);
  $('ev-summary').innerHTML = `<p class="muted small">Run ${esc(r.ran_at)} · ${r.n_cases} cases · ${r.n_llm_cases} scored by the judge LLM (${esc(r.evaluator_model || '—')}) · avg ${num((s.avg_latency_ms || 0) / 1000, 1)} s per analysis</p>
    <div class="grid g2"><div><h4>DeepEval</h4>${bars(deep, (v) => pct(v, 1))}</div><div><h4>Deterministic &amp; judge</h4>${bars(det.map(([k, v]) => [k, v, 'var(--brand)']), (v) => pct(v, 1))}</div></div>`;
}
async function runEval(btn) {
  const r = await guarded(btn, 'Starting', () => post('/evaluate', { limit: 5, use_graph: false, include_feedback: false }));
  if (r) { toast('Evaluation started (uses the judge LLM).'); track('evaluation', 'Started evaluation (5 golden cases)', 'DeepEval + LLM judge + deterministic checks'); loadEval(); }
}
async function loadModels() {
  const m = await get('/models');
  const rows = Object.entries(m.targets || {}).map(([k, v]) => ({ k, ...v }));
  $('md-out').innerHTML = `<p class="muted small">Trained ${esc(m.trained_at)} on ${num(m.n_rows)} rows</p>` + table([
    ['Target', (t) => esc(t.label)], ['R² / AUC', (t) => (t.auc !== undefined ? `AUC ${num(t.auc, 3)}` : num(t.r2, 3)), 'num'],
    ['MAE', (t) => (t.mae !== undefined ? num(t.mae, t.k === 'revenue_loss_usd' ? 0 : 2) : '—'), 'num'],
    ['P10–P90 coverage', (t) => (t.interval_coverage !== undefined ? pct(t.interval_coverage, 1) : '—'), 'num'],
  ], rows);
}
async function retrain(btn) {
  const r = await guarded(btn, 'Retraining', () => post('/models/retrain', {}));
  if (r) { $('md-msg').textContent = 'Retraining started in the background.'; setTimeout(() => loadModels().catch(() => {}), 15000); }
}
async function loadFeedback() {
  const f = await get('/feedback/stats');
  $('fb-stats').innerHTML = `<div class="chips">${pill(`${f.total} ratings`)}${pill(`avg ${num(f.avg_rating, 2)}★`)}${pill(`${pct(f.helpful_rate)} helpful`)}${pill(`${f.with_outcomes} with real outcomes`, 'ok')}${pill(`${f.sent_to_synapt} sent to Synapt`, 'cyan')}</div>
    <h4>Strategy re-weighting from feedback</h4>` + table([
    ['Disruption type', (b) => esc(b.disruption_type)], ['Strategy', (b) => esc(b.strategy)], ['Boost', (b) => `×${num(b.boost, 3)}`, 'num'],
  ], f.boosts || [], { empty: 'No boosts yet.' });
}
async function loadSynaptQuality() {
  const q = await get('/synapt/quality');
  const s = q.summary || {};
  $('sq-out').innerHTML = `<p class="muted small">${q.n} logged Synapt answers</p>` + bars([
    ['Answer confidence', s.confidence], ['Knowledge confidence', s.knowledge_confidence], ['Procedural confidence', s.procedural_confidence],
    ['Graph confidence', s.graph_confidence], ['Degraded rate', s.degraded_rate, 'var(--amber)']].filter((x) => x[1] !== undefined && x[1] !== null).map(([k, v, c]) => [k, v, c || 'var(--cyan)']), (v) => num(v, 3));
}

/* ================================================================== HISTORY
 * Everything done in the console, stored server-side in artifacts/history.json, so the list is the same
 * on every device that opens the app. Analyses re-open in full from feedback.db via /api/analyses/{id}. */
const KIND_LABEL = { analysis: 'Analysis', ask: 'Question', search: 'Search', graph: 'Graph query', simulation: 'Simulation',
  decision: 'Decision', triage: 'Triage', portfolio: 'Portfolio', network: 'Network outage', signal: 'Signal', incident: 'Incident',
  feedback: 'Feedback', evaluation: 'Evaluation', playbook: 'Playbook', insight: 'Graph insight' };
const KIND_CLS = { analysis: 'info', ask: 'cyan', graph: 'cyan', playbook: 'cyan', insight: 'cyan', search: '', simulation: 'violet',
  decision: 'ok', triage: 'warn', incident: 'bad', feedback: 'ok', signal: 'warn' };
state.historyKind = '';
LOADERS.history = async () => { await loadHistory(); };
async function loadHistory() {
  const q = $('hist-q').value.trim();
  const r = await get(`/history?limit=500${state.historyKind ? `&kind=${state.historyKind}` : ''}${q ? `&q=${encodeURIComponent(q)}` : ''}`);
  $('hist-kinds').innerHTML = `<button type="button" class="btn small ${!state.historyKind ? 'primary' : 'ghost'}" data-hist-kind="">All ${r.total}</button>`
    + Object.entries(r.counts).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<button type="button" class="btn small ${state.historyKind === k ? 'primary' : 'ghost'}" data-hist-kind="${esc(k)}">${esc(KIND_LABEL[k] || k)} ${n}</button>`).join('');
  if (!r.entries.length) { $('hist-list').innerHTML = '<p class="muted">Nothing recorded yet. Every analysis, question, simulation, decision and incident action you take is saved here.</p>'; return; }
  let day = '';
  $('hist-list').innerHTML = r.entries.map((e) => {
    const d = new Date(e.ts * 1000);
    const dl = d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
    const head = dl !== day ? `<div class="hist-day">${esc(dl)}</div>` : '';
    day = dl;
    return `${head}<div class="hist-item" data-hist-id="${esc(e.id)}"><span class="hist-time mono">${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
      ${pill(KIND_LABEL[e.kind] || e.kind, KIND_CLS[e.kind] || '')}<div class="hist-text"><b>${esc(e.title)}</b><div class="muted small">${esc(e.summary)}</div></div></div>`;
  }).join('');
}
async function openHistory(id) {
  document.querySelectorAll('.hist-item').forEach((x) => x.classList.toggle('on', x.dataset.histId === id));
  const e = await get(`/history/${id}`);
  const canOpen = e.kind === 'analysis' && e.ref;
  const rerun = { ask: 'ask', search: 'search', graph: 'graph' }[e.kind];
  $('hist-detail').innerHTML = `<div class="chips">${pill(KIND_LABEL[e.kind] || e.kind, KIND_CLS[e.kind] || '')}${pill(new Date(e.ts * 1000).toLocaleString())}${e.ref ? pill('ref ' + e.ref) : ''}</div>
    <h3>${esc(e.title)}</h3><p class="muted">${esc(e.summary)}</p>
    <div class="row wrap">${canOpen ? `<button class="btn primary small" type="button" data-hist-open="${esc(e.ref)}">Open full analysis</button>` : ''}
      ${rerun ? `<button class="btn small" type="button" data-hist-rerun="${rerun}" data-hist-text="${esc((e.data || {}).question || (e.data || {}).query || e.title)}">Run again</button>` : ''}
      <button class="btn ghost small" type="button" data-hist-del="${esc(e.id)}">Delete entry</button></div>
    ${(e.data || {}).answer ? `<div class="md">${md(e.data.answer)}</div>` : ''}
    ${e.data && Object.keys(e.data).length ? `<details${e.data.answer ? '' : ' open'}><summary class="muted small">Stored inputs and result</summary><pre class="mono small hist-json">${esc(JSON.stringify(e.data, null, 1))}</pre></details>` : ''}`;
}
async function reopenAnalysis(id, btn) {
  const a = await guarded(btn, 'Loading', () => get(`/analyses/${id}`));
  if (!a) return;
  const r = { ...a.report, analysis_id: a.id };
  state.analysis = r;
  show('cockpit');
  agentCards();
  (r.trace || []).forEach((t) => {
    const el = $(`ag-${t.agent}`);
    if (el) { el.className = 'agent done'; el.querySelector('.s').textContent = t.summary || ''; el.querySelector('.t').textContent = `${num(t.ms)} ms`; }
  });
  (r.decisions || []).forEach(showRoute);
  $('ck-desc').value = (a.input || {}).description || '';
  renderAnalysis(r, r.total_ms || 0);
  toast(`Re-opened analysis from ${new Date(a.ts * 1000).toLocaleString()} (not re-run)`);
}
document.addEventListener('click', async (e) => {
  const k = e.target.closest('[data-hist-kind]');
  const it = e.target.closest('[data-hist-id]');
  const op = e.target.closest('[data-hist-open]');
  const rr = e.target.closest('[data-hist-rerun]');
  const del = e.target.closest('[data-hist-del]');
  if (k) { state.historyKind = k.dataset.histKind; loadHistory().catch((x) => toast(x.message)); }
  if (it) openHistory(it.dataset.histId).catch((x) => toast(x.message));
  if (op) reopenAnalysis(op.dataset.histOpen, op);
  if (rr) {
    const tab = rr.dataset.histRerun; const txt = rr.dataset.histText;
    if (tab === 'ask') { show('search'); $('ask-q').value = txt; $('ask-run').click(); }
    if (tab === 'search') { show('search'); $('sr-q').value = txt; $('sr-run').click(); }
    if (tab === 'graph') { show('graph'); $('kg-q').value = txt; $('kg-run').click(); }
  }
  if (del) {
    await api('DELETE', `/history/${del.dataset.histDel}`).catch((x) => toast(x.message));
    $('hist-detail').innerHTML = '<p class="muted">Entry deleted.</p>';
    loadHistory();
  }
});

/* ================================================================== 3D CONTROL TOWER
 * Multi-modal logistics world (ported from the React/three-fiber version to plain three.js).
 * Regions are islands around your home island (the plant). Trucks run on land, container ships berth
 * alongside quays and sail curved sea routes, B747 freighters fly full airport-to-airport operations
 * sequenced through the hub. A selected disruption type halts the transport modes it would really hit.
 * three.js is loaded from the CDN (import map in index.html) only when this view is opened. */
const Tower = (() => {
  // ---------------------------------------------------------------- 2D vector maths + timelines (pure)
  const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
  const mul = (a, k) => [a[0] * k, a[1] * k];
  const len = (a) => Math.hypot(a[0], a[1]);
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  const norm = (a) => { const l = len(a) || 1; return [a[0] / l, a[1] / l]; };
  const ease = (t) => t * t * (3 - 2 * t);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
  const headingOf = (d) => Math.atan2(d[1], d[0]);

  function lineSamples(p, q, step) {
    const n = Math.max(1, Math.ceil(dist(p, q) / step));
    return Array.from({ length: n + 1 }, (_, i) => lerp(p, q, i / n));
  }
  function quadSamples(p0, c, p1, step) {
    const n = Math.max(2, Math.ceil((dist(p0, c) + dist(c, p1)) / step));
    return Array.from({ length: n + 1 }, (_, i) => {
      const t = i / n; const u = 1 - t;
      return [u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0], u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]];
    });
  }
  function cubicSamples(p0, p1, p2, p3, step) {
    const n = Math.max(4, Math.ceil((dist(p0, p1) + dist(p1, p2) + dist(p2, p3)) / step));
    return Array.from({ length: n + 1 }, (_, i) => {
      const t = i / n; const u = 1 - t;
      const a = u * u * u; const b = 3 * u * u * t; const c = 3 * u * t * t; const d = t * t * t;
      return [a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]];
    });
  }
  function roundedPath(pts, r = 0.7, step = 0.06) {
    const out = [pts[0]];
    let cur = pts[0];
    for (let i = 1; i < pts.length; i++) {
      const p = pts[i];
      if (i < pts.length - 1) {
        const din = norm(sub(p, pts[i - 1])); const dout = norm(sub(pts[i + 1], p));
        const rr = Math.min(r, dist(pts[i - 1], p) / 2, dist(p, pts[i + 1]) / 2);
        const pin = sub(p, mul(din, rr)); const pout = add(p, mul(dout, rr));
        out.push(...lineSamples(cur, pin, step).slice(1), ...quadSamples(pin, p, pout, step).slice(1));
        cur = pout;
      } else out.push(...lineSamples(cur, p, step).slice(1));
    }
    return out;
  }
  const smin = (a, b, k = 0.6) => -k * Math.log(Math.exp(-a / k) + Math.exp(-b / k));
  const trapezoid = (v0, vm, v1, ramp) => (s, S) => Math.max(Math.min(v0, v1, vm),
    Math.min(vm, v0 + (vm - v0) * (s / ramp), v1 + (vm - v1) * ((S - s) / ramp)));
  const kinematic = (v0, v1) => (s, S) => Math.sqrt(Math.max(0, v0 * v0 + (v1 * v1 - v0 * v0) * (S ? s / S : 1)));

  function addMove(track, pts, { v, y = 0, rev = false, gear = true, air = false, bias = 0, maxYawRate = air ? Infinity : 1.2 }) {
    const cum = [0];
    for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + dist(pts[i - 1], pts[i]));
    const S = cum[cum.length - 1];
    const at = (f, s) => (typeof f === 'function' ? f(s, S) : f);
    const limit = pts.map((p, i) => {
      if (!Number.isFinite(maxYawRate) || i === 0 || i === pts.length - 1) return Infinity;
      const a = sub(p, pts[i - 1]); const b = sub(pts[i + 1], p);
      const turn = Math.abs(wrap(headingOf(b) - headingOf(a)));
      const ds = (len(a) + len(b)) / 2;
      return turn > 1e-4 ? maxYawRate * (ds / turn) : Infinity;
    });
    const lim = limit.map((_, i) => Math.min(...limit.slice(Math.max(0, i - 6), i + 7)));
    const last = track[track.length - 1];
    pts.forEach((p, i) => {
      if (i === 0 && last && dist([last.x, last.z], p) < 1e-6) return;
      const vv = Math.max(0.04, Math.min(at(v, cum[i]), lim[i]));
      track.push({ x: p[0], z: p[1], y: at(y, cum[i]), v: vv, rev, gear: at(gear, cum[i]), air, bias: at(bias, cum[i]) });
    });
    return S;
  }
  function addHold(track, dt, extra = {}) { track.push({ ...track[track.length - 1], v: 0, dt, hold: true, ...extra }); }
  function addTurn(track, fromYaw, toYaw, dt, to = null, steps = 40) {
    const last = track[track.length - 1];
    const start = [last.x, last.z];
    const dy = wrap(toYaw - fromYaw);
    for (let i = 1; i <= steps; i++) {
      const k = ease(i / steps);
      const p = to ? lerp(start, to, k) : start;
      track.push({ ...last, x: p[0], z: p[1], v: 0, dt: dt / steps, hold: true, yaw: fromYaw + dy * k });
    }
  }
  function finalize(track) {
    const n = track.length;
    const t = new Float32Array(n); const x = new Float32Array(n); const y = new Float32Array(n); const z = new Float32Array(n);
    const yaw = new Float32Array(n); const pitch = new Float32Array(n); const bank = new Float32Array(n);
    const gear = new Uint8Array(n); const spd = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const s = track[i];
      if (s.yaw !== undefined) { yaw[i] = s.yaw; continue; }
      if (s.hold && i > 0) { yaw[i] = yaw[i - 1]; continue; }
      let d = null;
      for (let j = i + 1; j < Math.min(n, i + 6); j++) {
        if (track[j].hold) break;
        if (dist([track[j].x, track[j].z], [s.x, s.z]) > 1e-5) { d = [track[j].x - s.x, track[j].z - s.z]; break; }
      }
      if (!d && i > 0) d = [s.x - track[i - 1].x, s.z - track[i - 1].z];
      yaw[i] = d && len(d) > 1e-6 ? headingOf(d) + (s.rev ? Math.PI : 0) : (i ? yaw[i - 1] : 0);
    }
    for (let i = 1; i < n; i++) yaw[i] = yaw[i - 1] + wrap(yaw[i] - yaw[i - 1]);
    for (let i = 0; i < n; i++) {
      const s = track[i];
      x[i] = s.x; y[i] = s.y; z[i] = s.z; gear[i] = s.gear ? 1 : 0; spd[i] = s.v;
      if (i === 0) { t[i] = 0; continue; }
      if (s.dt !== undefined) { t[i] = t[i - 1] + s.dt; continue; }
      const p = track[i - 1];
      t[i] = t[i - 1] + Math.hypot(s.x - p.x, s.z - p.z, s.y - p.y) / Math.max(0.04, (s.v + p.v) / 2);
    }
    for (let i = 0; i < n; i++) {
      const s = track[i];
      let fpa = 0; let bk = 0;
      if (s.air && i > 0 && i < n - 1) {
        const a = track[i - 1]; const b = track[i + 1];
        const h = Math.hypot(b.x - a.x, b.z - a.z) || 1e-6;
        fpa = Math.atan2(b.y - a.y, h);
        const kappa = wrap(yaw[i + 1] - yaw[i - 1]) / h;
        bk = clamp(Math.atan((s.v * s.v * kappa) / 6), -0.5, 0.5);
      }
      pitch[i] = fpa + (s.bias || 0);
      bank[i] = bk;
    }
    const smooth = (arr, w) => {
      const src = Float32Array.from(arr);
      for (let i = 0; i < n; i++) {
        let acc = 0; let c = 0;
        for (let j = Math.max(0, i - w); j <= Math.min(n - 1, i + w); j++) { acc += src[j]; c++; }
        arr[i] = acc / c;
      }
    };
    smooth(pitch, 4); smooth(bank, 8);
    return { t, x, y, z, yaw, pitch, bank, gear, spd, duration: t[n - 1], n };
  }
  function sampleAt(tl, tau, out = {}) {
    const T = tl.duration;
    const q = ((tau % T) + T) % T;
    let lo = 0; let hi = tl.n - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (tl.t[mid] <= q) lo = mid; else hi = mid; }
    const span = tl.t[hi] - tl.t[lo];
    const f = span > 0 ? Math.min(1, (q - tl.t[lo]) / span) : 0;
    const L = (arr) => arr[lo] + (arr[hi] - arr[lo]) * f;
    out.x = L(tl.x); out.y = L(tl.y); out.z = L(tl.z);
    out.yaw = L(tl.yaw); out.pitch = L(tl.pitch); out.bank = L(tl.bank);
    out.gear = tl.gear[f < 0.5 ? lo : hi] === 1; out.v = L(tl.spd);
    return out;
  }

  // airports + aircraft operations
  const TAXI_OFF = 1.6; const STAND_OFF = 4.0; const STAND_GAP = 2.6;
  function makeAirport(a, b, n, standCount = 1) {
    const d = norm(sub(b, a)); const L = dist(a, b);
    const at = (s, off) => add(add(a, mul(d, s)), mul(n, off));
    const stands = Array.from({ length: standCount }, (_, k) => {
      const s = L / 2 + (k - (standCount - 1) / 2) * STAND_GAP;
      return { s, pos: at(s, STAND_OFF) };
    });
    return { a, b, d, n, L, at, stands, connA: -0.8, exitS: 0.9 * L, tdS: 0.15 * L, lineupS: 0.5, rollFrac: 0.55 };
  }
  const PLANE = { push: 0.8, taxi: 1.8, rot: 3.6, climb: 4.6, cruise: 5.4, app: 3.6, alt: 8.5, climbGrad: 0.28, glideGrad: 0.16, gY: 0.25 };
  const FINAL = 9;
  const parkedSample = (ap, k) => ({ x: ap.stands[k].pos[0], z: ap.stands[k].pos[1], y: PLANE.gY, v: 0, rev: false, gear: true, air: false, bias: 0, yaw: headingOf(ap.n) });
  function departure(tr, ap, k, ev, tag) {
    const st = ap.stands[k];
    const K = ap.at(st.s, TAXI_OFF);
    ev[`${tag}Push`] = tr.length - 1;
    addMove(tr, roundedPath([st.pos, K, ap.at(st.s + 1.3, TAXI_OFF)], 1.2), { v: trapezoid(0.05, PLANE.push, 0.05, 0.5), y: PLANE.gY, rev: true });
    addHold(tr, 1.2);
    addMove(tr, roundedPath([ap.at(st.s + 1.3, TAXI_OFF), ap.at(ap.connA, TAXI_OFF), ap.at(ap.connA, 0), ap.at(ap.lineupS, 0)], 0.65),
      { v: trapezoid(0.05, PLANE.taxi, 0.05, 1.0), y: PLANE.gY });
    addHold(tr, 1.5);
    const lo = ap.at(ap.lineupS + ap.L * ap.rollFrac, 0);
    addMove(tr, lineSamples(ap.at(ap.lineupS, 0), lo, 0.08), {
      v: kinematic(0.15, PLANE.rot), y: PLANE.gY, bias: (s, S) => 0.17 * clamp((s / S - 0.75) / 0.25, 0, 1),
    });
    ev[`${tag}LO`] = tr.length - 1;
    return lo;
  }
  function flight(tr, from, lo, to, ev, tag) {
    const td = to.at(to.tdS, 0);
    const c1 = add(lo, mul(from.d, 4));
    const fix = sub(td, mul(to.d, FINAL));
    const k = clamp(dist(c1, fix) * 0.4, 3, 16);
    const pts = [...lineSamples(lo, c1, 0.15),
      ...cubicSamples(c1, add(c1, mul(from.d, k)), sub(fix, mul(to.d, k)), fix, 0.15).slice(1),
      ...lineSamples(fix, td, 0.15).slice(1)];
    ev[`${tag}AirStart`] = tr.length - 1;
    addMove(tr, pts, {
      air: true,
      y: (s, S) => PLANE.gY + Math.max(0, smin(smin(PLANE.climbGrad * s, PLANE.alt), PLANE.glideGrad * (S - s))),
      v: (s, S) => (s < 6 ? PLANE.rot + (PLANE.cruise - PLANE.rot) * (s / 6)
        : S - s < FINAL ? PLANE.app + (PLANE.cruise - PLANE.app) * ((S - s) / FINAL) : PLANE.cruise),
      gear: (s, S) => s < 2.5 || S - s < FINAL + 1,
      bias: (s, S) => (S - s < FINAL ? 0.2 + 0.06 * clamp(1 - (S - s), 0, 1) : 0.06),
    });
    ev[`${tag}TD`] = tr.length - 1;
    return td;
  }
  function arrival(tr, ap, k, ev, tag) {
    const st = ap.stands[k];
    const r1 = ap.at(ap.exitS - 0.6, 0);
    addMove(tr, lineSamples(ap.at(ap.tdS, 0), r1, 0.08), { v: kinematic(PLANE.app, 1.4), y: PLANE.gY, bias: (s) => Math.max(0, 0.12 * (1 - s / 0.8)) });
    addMove(tr, roundedPath([r1, ap.at(ap.exitS + 0.3, 0), ap.at(ap.exitS + 0.3, TAXI_OFF), ap.at(st.s, TAXI_OFF), st.pos], 0.75),
      { v: trapezoid(1.4, PLANE.taxi, 0.05, 1.0), y: PLANE.gY });
    ev[`${tag}Stand`] = tr.length - 1;
  }
  function buildPlaneTimeline(region, hub, hubStand, dwellRegion, dwellHub) {
    const tr = [parkedSample(region, 0)];
    const ev = {};
    addHold(tr, Math.max(0.1, dwellRegion));
    const lo1 = departure(tr, region, 0, ev, 'reg');
    flight(tr, region, lo1, hub, ev, 'out');
    arrival(tr, hub, hubStand, ev, 'hub');
    addHold(tr, Math.max(0.1, dwellHub));
    const lo2 = departure(tr, hub, hubStand, ev, 'hub');
    flight(tr, hub, lo2, region, ev, 'ret');
    arrival(tr, region, 0, ev, 'reg2');
    tr.push({ ...parkedSample(region, 0), dt: 0.5, hold: true });
    const tl = finalize(tr);
    tl.events = Object.fromEntries(Object.entries(ev).map(([key, i]) => [key, tl.t[i]]));
    return tl;
  }
  function scheduleFleet(regionAirports, hub) {
    const n = regionAirports.length;
    const stand = (i) => i % hub.stands.length;
    if (n === 1) {
      const tl = buildPlaneTimeline(regionAirports[0], hub, 0, 4, 8);
      return { fleet: [{ timeline: tl, offset: 0 }] };
    }
    const probe = regionAirports.map((ap, i) => buildPlaneTimeline(ap, hub, stand(i), 0, 0));
    const maxArr = Math.max(...probe.map((tl) => tl.events.hubStand - tl.events.outTD + 2.5));
    const maxDep = Math.max(...probe.map((tl) => tl.events.hubLO - tl.events.hubPush + 1.0));
    const base = probe.map((tl) => tl.duration);
    const taxiIn = probe.map((tl) => tl.events.hubStand - tl.events.outTD);
    const slot = Math.max(maxArr + maxDep + 3, ...base.map((b, i) => (b + maxArr + 2.5 - taxiIn[i] + 4) / (n - 1)));
    const period = n * slot;
    return {
      fleet: regionAirports.map((ap, i) => {
        const dwellHub = slot + maxArr - 1.5 - taxiIn[i];
        const tl = buildPlaneTimeline(ap, hub, stand(i), period - base[i] - dwellHub, dwellHub);
        return { timeline: tl, offset: tl.events.outTD - (i * slot + 2.5) };
      }),
    };
  }
  const SHIP = { sea: 1.5, berth: 0.12, dwell: 6, turn: 7 };
  function buildShipTimeline({ port, pier, u, p }) {
    const A = add(port, mul(u, 2.8)); const Aoff = add(A, mul(u, 2.0));
    const B = add(add(pier, mul(u, -1.7)), mul(p, 1.35)); const Boff = add(B, mul(p, 1.6));
    const hA = p; const hB = u;
    const tr = [{ x: A[0], z: A[1], y: 0, v: 0, rev: false, gear: false, air: false, bias: 0, yaw: headingOf(mul(hA, -1)) }];
    const voyage = (from, hFrom, to, hTo) => {
      const k = clamp(dist(from, to) * 0.35, 3, 14);
      addMove(tr, cubicSamples(from, add(from, mul(hFrom, k)), sub(to, mul(hTo, k)), to, 0.12), { v: trapezoid(SHIP.berth, SHIP.sea, SHIP.berth, 2.5) });
    };
    addHold(tr, SHIP.dwell);
    addTurn(tr, headingOf(mul(hA, -1)), headingOf(hA), SHIP.turn, Aoff);
    voyage(Aoff, hA, B, hB);
    addHold(tr, SHIP.dwell);
    addTurn(tr, headingOf(hB), headingOf(mul(hB, -1)), SHIP.turn, Boff);
    voyage(Boff, mul(hB, -1), A, mul(hA, -1));
    const tl = finalize(tr);
    const k = clamp(dist(Aoff, B) * 0.35, 3, 14);
    tl.outbound = cubicSamples(Aoff, add(Aoff, mul(hA, k)), sub(B, mul(hB, k)), B, 0.5);
    tl.anchor = add(add(A, mul(u, 5.5)), mul(p, 2.5));
    tl.anchorYaw = headingOf(u);
    return tl;
  }

  // ---------------------------------------------------------------- world layout (pure)
  const RISK = { Low: '#22c55e', Medium: '#3b82f6', High: '#f59e0b', Critical: '#ef4444' };
  const DISRUPTED_AT = 0.6;
  const MODE_IMPACT = {
    'Port Congestion': { sea: true, crane: true }, 'Labor Strike': { sea: true, crane: true, truck: true },
    Geopolitical: { sea: true, air: true }, 'Natural Disaster': { sea: true, air: true }, 'Cyber Attack': { air: true }, 'Factory Incident': {},
  };
  const REGION_POS = { 'North America': [-38, -12.6], 'South America': [-24, 26.5], Europe: [5.7, -36.8], 'Africa/Middle East': [28.8, 20.7], 'Asia-Pacific': [40.2, -11.5] };
  const SPACING = 3.4; const HUB_R = 10.5; const HUB_SEED = 9.1; const HUB_POS = [0, -2]; const SEA_Y = -0.5;
  const HUB_AIRPORT = makeAirport([-5.2, 6.9], [5.2, 6.9], [0, -1], 3);
  const coast = (a, seed) => 1.07 + 0.07 * Math.sin(3 * a + seed) + 0.04 * Math.sin(5 * a + seed * 2.1) + 0.02 * Math.sin(11 * a + seed * 3.7);

  function layoutWorld(suppliers) {
    const byRegion = {};
    suppliers.forEach((s) => { (byRegion[s.supplier_region] = byRegion[s.supplier_region] || []).push(s); });
    const sites = [];
    const regions = Object.entries(byRegion).map(([region, list], ri) => {
      const C = REGION_POS[region] || [0, 40 + ri * 8];
      const u = norm([-C[0], -C[1]]); const p = [-u[1], u[0]];
      const cols = Math.min(3, list.length); const rows = Math.ceil(list.length / cols);
      const R = Math.hypot(cols * SPACING, rows * SPACING) / 2 + 9;
      const seed = ri * 1.7 + 0.6;
      const mySites = list.map((s, i) => ({ ...s, pos: [C[0] + ((i % cols) - (cols - 1) / 2) * SPACING, C[1] + (Math.floor(i / cols) - (rows - 1) / 2) * SPACING] }));
      sites.push(...mySites);
      const port = add(C, mul(u, R * coast(Math.atan2(u[1], u[0]), seed) - 1.0));
      const pier = mul([-u[0], -u[1]], HUB_R * coast(Math.atan2(-u[1], -u[0]), HUB_SEED) - 0.6);
      const rwc = add(C, mul(u, -(R - 1.8)));
      const airport = makeAirport(add(rwc, mul(p, -4)), add(rwc, mul(p, 4)), u, 1);
      return { region, C, u, p, R, seed, count: list.length, sites: mySites, port, pier, airport };
    });
    return { sites, regions };
  }
  function regionStatus(world, disruption) {
    const hit = (s) => !!disruption && ((s.by_type || []).find((t) => t.disruption_type === disruption)?.risk_probability ?? 0) >= DISRUPTED_AT;
    const modes = MODE_IMPACT[disruption] || {};
    const out = {};
    world.regions.forEach((r) => {
      const sitesHit = world.sites.filter((s) => s.supplier_region === r.region && hit(s)).length;
      const on = sitesHit > 0;
      out[r.region] = { sitesHit, sea: on && !!modes.sea, air: on && !!modes.air, crane: on && !!modes.crane, truck: on && !!modes.truck };
    });
    return { hit, byRegion: out };
  }
  function inAirport(ap, p, margin = 0) {
    const rel = [p[0] - ap.a[0], p[1] - ap.a[1]];
    const s = rel[0] * ap.d[0] + rel[1] * ap.d[1];
    const off = rel[0] * ap.n[0] + rel[1] * ap.n[1];
    return s > -2.2 - margin && s < ap.L + 2.2 + margin && off > -1.6 - margin && off < STAND_OFF + 2.6 + margin;
  }
  const distToSeg = (p, a, b) => {
    const ab = [b[0] - a[0], b[1] - a[1]];
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / ((ab[0] ** 2 + ab[1] ** 2) || 1)));
    return dist(p, [a[0] + ab[0] * t, a[1] + ab[1] * t]);
  };
  const wave = (x, z, t) => 0.045 * Math.sin(0.33 * x + t * 0.9) + 0.035 * Math.sin(0.41 * z - t * 0.7) + 0.02 * Math.sin(0.8 * (x + z) + t * 1.3);
  function rng(seed) {
    let s = Math.abs(Math.floor(seed * 9301 + 49297)) % 233280;
    return () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  }
  const SIZE = { Large: [2.5, 1.7, 2.1], Medium: [2.0, 1.3, 1.7], Small: [1.5, 1.0, 1.3] };
  const CONTAINER_COLORS = ['#c2410c', '#1d4ed8', '#15803d', '#b45309', '#0e7490', '#6d28d9', '#be123c', '#475569'];
  const TREE_GREENS = ['#2f7d32', '#3f8f3a', '#4b9b3f', '#2e6b30', '#5aa64a'];
  const VIEWS3D = { network: { label: 'Network', position: [60, 52, 60], zoom: 7.5, target: [0, 0, 0] },
    hub: { label: 'Hub airport', position: [14, 14, 22], zoom: 44, target: [-0.5, 0, 4.2] } };

  // ---------------------------------------------------------------- renderer state
  let T = null; // three.js namespace + addons
  const S = { data: null, world: null, traffic: null, disruption: null, view: 'network', selected: null, hover: null,
    root: null, anims: [], sites: [], renderer: null, labels: null, scene: null, camera: null, controls: null, clock: null,
    running: false, steps: {}, result: null, busy: false, error: null, asOf: null };

  // ---------------------------------------------------------------- three.js object helpers
  const matCache = {}; const geoCache = {};
  const mat = (color, o = {}) => { const k = color + JSON.stringify(o); return matCache[k] || (matCache[k] = new T.MeshStandardMaterial({ color, ...o })); };
  const basic = (color, o = {}) => { const k = 'b' + color + JSON.stringify(o); return matCache[k] || (matCache[k] = new T.MeshBasicMaterial({ color, ...o })); };
  const geo = (kind, ...args) => { const k = kind + args.join(','); return geoCache[k] || (geoCache[k] = new T[kind](...args)); };
  function mesh(g, m, pos = [0, 0, 0], { rot, scale, cast = false, recv = false } = {}) {
    const o = new T.Mesh(g, m);
    o.position.set(...pos);
    if (rot) o.rotation.set(...rot);
    if (scale !== undefined) (Array.isArray(scale) ? o.scale.set(...scale) : o.scale.setScalar(scale));
    o.castShadow = cast; o.receiveShadow = recv;
    return o;
  }
  const box = (w, h, d, color, pos, o = {}) => mesh(geo('BoxGeometry', w, h, d), o.m || mat(color, o.mo || {}), pos, o);
  function group(pos = [0, 0, 0], rotY = 0, ...children) {
    const g = new T.Group(); g.position.set(...pos); g.rotation.y = rotY;
    children.flat().forEach((c) => c && g.add(c));
    return g;
  }
  function label(html, cls, pos) {
    const div = document.createElement('div');
    div.className = cls; div.innerHTML = html;
    const o = new T.CSS2DObject(div);
    o.position.set(...pos);
    return o;
  }
  const anim = (fn) => S.anims.push(fn);

  // ---------------------------------------------------------------- terrain
  function ocean() {
    const g = new T.PlaneGeometry(260, 260, 96, 96);
    const m = mesh(g, mat('#4aa6e3', { roughness: 0.32, metalness: 0.02 }), [0, SEA_Y, 0], { rot: [-Math.PI / 2, 0, 0], recv: true });
    const pos = g.attributes.position;
    anim((t) => {
      for (let i = 0; i < pos.count; i++) pos.setZ(i, wave(pos.getX(i), -pos.getY(i), t));
      pos.needsUpdate = true; g.computeVertexNormals();
    });
    return m;
  }
  function coastShape(R, seed, scale = 1) {
    const shape = new T.Shape();
    for (let i = 0; i <= 80; i++) {
      const a = (i / 80) * Math.PI * 2; const r = R * coast(a, seed) * scale;
      if (i === 0) shape.moveTo(Math.cos(a) * r, -Math.sin(a) * r); else shape.lineTo(Math.cos(a) * r, -Math.sin(a) * r);
    }
    return shape;
  }
  function island(c, R, seed, tint = '#9cc97a', alert = false) {
    const rot = [-Math.PI / 2, 0, 0];
    return group([c[0], 0, c[1]], 0,
      mesh(new T.ShapeGeometry(coastShape(R, seed, 1.3)), mat('#5ec8d8', { transparent: true, opacity: 0.55, roughness: 0.3 }), [0, SEA_Y + 0.07, 0], { rot }),
      mesh(new T.ExtrudeGeometry(coastShape(R, seed, 1.07), { depth: 0.32, bevelEnabled: true, bevelThickness: 0.05, bevelSize: 0.25, bevelSegments: 2, curveSegments: 4 }),
        mat('#e9d8a6', { roughness: 0.95 }), [0, -0.62, 0], { rot, recv: true }),
      mesh(new T.ExtrudeGeometry(coastShape(R, seed, 1.0), { depth: 0.42, bevelEnabled: true, bevelThickness: 0.06, bevelSize: 0.18, bevelSegments: 2, curveSegments: 4 }),
        mat(alert ? '#c9b48f' : tint, { roughness: 0.95 }), [0, -0.48, 0], { rot, recv: true }));
  }
  const pad = (center, w, d, color = '#d5d9df') => box(w, 0.03, d, color, [center[0], 0.015, center[1]], { recv: true, mo: { roughness: 0.9 } });
  function road(from, to, active) {
    const L = Math.hypot(to[0] - from[0], to[1] - from[1]);
    const ang = Math.atan2(to[1] - from[1], to[0] - from[0]);
    const g = group([(from[0] + to[0]) / 2, 0.03, (from[1] + to[1]) / 2], -ang,
      box(L, 0.03, 0.6, active ? '#7f1d1d' : '#3f4752', [0, 0, 0], { recv: true, mo: { roughness: 0.85 } }),
      [-0.27, 0.27].map((z) => box(L, 0.005, 0.03, '#d6d3d1', [0, 0.018, z])));
    const dashes = Math.max(0, Math.floor(L / 0.8) - 1);
    for (let i = 0; i < dashes; i++) g.add(box(0.34, 0.005, 0.04, active ? '#fca5a5' : '#facc15', [-L / 2 + 0.8 * (i + 1), 0.018, 0]));
    return g;
  }
  function tree(p, s, c, pine) {
    const g = group([p[0], 0, p[1]]); g.scale.setScalar(s);
    if (pine) {
      g.add(mesh(geo('CylinderGeometry', 0.06, 0.08, 0.4, 6), mat('#6b4423'), [0, 0.2, 0], { cast: true }),
        mesh(geo('ConeGeometry', 0.42, 0.8, 7), mat(c, { flatShading: true }), [0, 0.65, 0], { cast: true }),
        mesh(geo('ConeGeometry', 0.3, 0.6, 7), mat(c, { flatShading: true }), [0, 1.05, 0], { cast: true }));
    } else {
      g.add(mesh(geo('CylinderGeometry', 0.06, 0.09, 0.5, 6), mat('#6b4423'), [0, 0.25, 0], { cast: true }),
        mesh(geo('IcosahedronGeometry', 0.45, 0), mat(c, { flatShading: true }), [0, 0.75, 0], { cast: true }),
        mesh(geo('IcosahedronGeometry', 0.3, 0), mat(c, { flatShading: true }), [0.2, 0.62, 0.12], { cast: true }));
    }
    return g;
  }
  function scenery(c, R, seed, blocked, count = 44) {
    const r = rng(seed * 100 + 7); const g = group();
    let trees = 0; let hills = 0;
    for (let i = 0; i < 260 && trees < count; i++) {
      const a = r() * Math.PI * 2; const rad = Math.sqrt(r()) * R * coast(a, seed) * 0.9;
      const p = [c[0] + Math.cos(a) * rad, c[1] + Math.sin(a) * rad];
      const s = 0.6 + r() * 0.6; const col = TREE_GREENS[Math.floor(r() * TREE_GREENS.length)]; const kind = r() > 0.45;
      if (!blocked(p, 0.9)) { g.add(tree(p, s, col, kind)); trees++; }
    }
    for (let i = 0; i < 40 && hills < 3; i++) {
      const a = r() * Math.PI * 2; const rad = (0.55 + r() * 0.3) * R;
      const p = [c[0] + Math.cos(a) * rad, c[1] + Math.sin(a) * rad]; const s = 0.9 + r() * 0.8;
      if (!blocked(p, 2.2)) { g.add(mesh(geo('IcosahedronGeometry', 1, 1), mat('#7fb35f', { flatShading: true, roughness: 1 }), [p[0], -0.05, p[1]], { scale: [s * 1.6, s * 0.55, s * 1.3], cast: true, recv: true })); hills++; }
    }
    return g;
  }
  function clouds() {
    const r = rng(42); const g = group();
    const cs = Array.from({ length: 5 }).map(() => ({ x: -70 + r() * 140, z: -50 + r() * 100, y: 17 + r() * 4, s: 0.55 + r() * 0.45, v: 0.5 + r() * 0.5,
      puffs: Array.from({ length: 5 }).map(() => [r() * 3 - 1.5, r() * 0.6, r() * 1.6 - 0.8, 0.9 + r() * 0.8]) }));
    cs.forEach((c) => {
      const cg = group([c.x, c.y, c.z]); cg.scale.setScalar(c.s);
      c.puffs.forEach((p) => cg.add(mesh(new T.IcosahedronGeometry(p[3], 1), mat('#ffffff', { transparent: true, opacity: 0.72, roughness: 1, flatShading: true, depthWrite: false }), [p[0], p[1], p[2]], { cast: true })));
      g.add(cg);
    });
    anim((t, dt) => g.children.forEach((cg, i) => { cg.position.x += cs[i].v * dt; if (cg.position.x > 80) cg.position.x = -80; }));
    return g;
  }

  // ---------------------------------------------------------------- containers, port, crane
  const container = (pos, color, size = [0.9, 0.42, 0.4]) => box(size[0], size[1], size[2], color, pos, { cast: true, recv: true, mo: { roughness: 0.75 } });
  function yard(cols = 3, rows = 2, layers = 2, seed = 0) {
    const g = group();
    for (let l = 0; l < layers; l++) for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      if ((c + r + l + seed) % 5 === 4 && l > 0) continue;
      g.add(container([c * 0.95, 0.21 + l * 0.43, r * 0.45], CONTAINER_COLORS[(c * 7 + r * 13 + l * 5 + seed) % CONTAINER_COLORS.length]));
    }
    return g;
  }
  function gantryCrane(frozen) {
    const steel = frozen ? '#9ca3af' : '#e0a21b';
    const g = group();
    [-0.75, 0.75].forEach((z) => [-0.9, 0.9].forEach((x) => g.add(box(0.13, 3.2, 0.13, steel, [x, 1.6, z], { cast: true }))));
    [-0.75, 0.75].forEach((z) => g.add(box(1.9, 0.12, 0.12, steel, [0, 0.5, z], { cast: true })));
    g.add(box(4.6, 0.22, 1.7, steel, [0.9, 3.25, 0], { cast: true }), box(0.6, 0.45, 0.8, '#f1f5f9', [-0.9, 3.55, 0], { cast: true }));
    const cable = box(0.025, 1, 0.025, '#111827', [0, -0.15, 0]);
    const load = group([0, -0.5, 0], 0, container([0, 0, 0], '#c2410c'));
    const trolley = group([-0.6, 3.05, 0], 0, box(0.45, 0.22, 0.6, '#334155', [0, 0, 0], { cast: true }), cable, load);
    g.add(trolley);
    if (!frozen) {
      anim((t) => {
        const cyc = (t % 9) / 9;
        let x; let drop; let loaded;
        if (cyc < 0.3) { x = T.MathUtils.lerp(-0.6, 2.6, ease(cyc / 0.3)); drop = 0.3; loaded = false; } else if (cyc < 0.45) { x = 2.6; drop = 0.3 + Math.sin(((cyc - 0.3) / 0.15) * Math.PI) * 1.6; loaded = cyc > 0.375; } else if (cyc < 0.75) { x = T.MathUtils.lerp(2.6, -0.6, ease((cyc - 0.45) / 0.3)); drop = 0.3; loaded = true; } else { x = -0.6; drop = 0.3 + Math.sin(((cyc - 0.75) / 0.25) * Math.PI) * 1.4; loaded = cyc < 0.875; }
        trolley.position.x = x; cable.scale.y = drop; cable.position.y = -drop / 2;
        load.position.y = -drop - 0.22; load.visible = loaded;
      });
    }
    return g;
  }
  function port(at, u, frozen, text, seed) {
    const g = group([at[0], 0, at[1]], -Math.atan2(u[1], u[0]),
      box(5.4, 0.06, 4.6, '#c9ced6', [-0.6, 0, 0], { recv: true }),
      box(1.0, 0.5, 4.6, '#a8afb9', [1.75, -0.22, 0], { recv: true, cast: true }),
      [-1.7, -0.6, 0.6, 1.7].map((z) => mesh(geo('CylinderGeometry', 0.07, 0.09, 0.2, 8), mat('#1f2937'), [2.1, 0.12, z])),
      group([0.8, 0, 0], 0, gantryCrane(frozen)),
      group([-2.9, 0, -1.9], 0, yard(2, 4, 3, seed)), group([-2.9, 0, 0.6], 0, yard(2, 3, 2, seed + 3)));
    if (text) g.add(label(esc(text), `ct-tag ${frozen ? 'ct-tag-red' : ''}`, [0, 4.4, 0]));
    return g;
  }
  function pier(at, u) {
    return group([at[0], 0, at[1]], -Math.atan2(u[1], u[0]),
      box(2.8, 0.45, 1.5, '#a8afb9', [-1.2, -0.2, 0], { recv: true, cast: true }),
      [-2.3, -1.3, -0.3].map((x) => mesh(geo('CylinderGeometry', 0.07, 0.09, 0.2, 8), mat('#1f2937'), [x, 0.08, 0.62])),
      box(0.1, 1.1, 0.1, '#e5e7eb', [-0.6, 0.55, -0.5], { cast: true }),
      mesh(geo('SphereGeometry', 0.08, 8, 8), basic('#f59e0b'), [-0.6, 1.12, -0.5]));
  }

  // ---------------------------------------------------------------- ship
  let HULL_LOW; let HULL_HIGH; let WAKE;
  function shipGeos() {
    if (HULL_LOW) return;
    const s = new T.Shape();
    s.moveTo(-1.9, -0.5); s.lineTo(1.2, -0.5); s.quadraticCurveTo(1.85, -0.45, 2.15, 0);
    s.quadraticCurveTo(1.85, 0.45, 1.2, 0.5); s.lineTo(-1.9, 0.5); s.quadraticCurveTo(-2.05, 0, -1.9, -0.5);
    HULL_LOW = new T.ExtrudeGeometry(s, { depth: 0.22, bevelEnabled: true, bevelThickness: 0.03, bevelSize: 0.03, bevelSegments: 1 });
    HULL_HIGH = new T.ExtrudeGeometry(s, { depth: 0.32, bevelEnabled: true, bevelThickness: 0.03, bevelSize: 0.03, bevelSegments: 1 });
    WAKE = new T.BufferGeometry();
    WAKE.setAttribute('position', new T.Float32BufferAttribute([0, 0, 0, -3.4, 0, 1.0, -3.4, 0, -1.0], 3));
    WAKE.computeVertexNormals();
  }
  function shipModel(halted, seed) {
    shipGeos();
    const g = group([0, 0, 0], 0,
      mesh(HULL_LOW, mat('#9f1d1d', { roughness: 0.6 }), [0, -0.05, 0], { rot: [-Math.PI / 2, 0, 0], cast: true }),
      mesh(HULL_HIGH, mat(halted ? '#7f1d1d' : '#1f2f4a', { roughness: 0.5 }), [0, 0.2, 0], { rot: [-Math.PI / 2, 0, 0], cast: true }),
      box(3.7, 0.03, 0.95, '#8b9199', [0.1, 0.55, 0]));
    for (let b = 0; b < 6; b++) {
      const tiers = 2 + ((b + seed) % 2);
      for (let l = 0; l < tiers; l++) for (let r = 0; r < 3; r++) {
        g.add(container([-0.95 + b * 0.52, 0.71 + l * 0.255, -0.29 + r * 0.29], CONTAINER_COLORS[(b * 3 + l + r * 5 + seed) % CONTAINER_COLORS.length], [0.5, 0.25, 0.27]));
      }
    }
    g.add(box(0.42, 0.85, 0.85, '#f8fafc', [-1.55, 0.98, 0], { cast: true }), box(0.46, 0.1, 1.15, '#f8fafc', [-1.55, 1.45, 0], { cast: true }),
      box(0.02, 0.1, 0.8, '#0f172a', [-1.33, 1.3, 0]), box(0.22, 0.4, 0.3, '#1e3a8a', [-1.8, 1.55, 0], { cast: true }),
      box(0.23, 0.07, 0.31, '#111827', [-1.8, 1.78, 0]), mesh(geo('CylinderGeometry', 0.02, 0.02, 0.5, 6), mat('#e5e7eb'), [1.75, 0.82, 0]));
    return g;
  }
  function ship(tl, halted, phase, seed) {
    const g = group([0, 0, 0], 0, shipModel(halted, seed));
    const wake = mesh(WAKE, basic('#ffffff', { transparent: true, opacity: 0.4, side: T.DoubleSide, depthWrite: false }), [-1.9, 0.06, 0]);
    g.add(wake);
    const st = {};
    anim((t) => {
      let x; let z; let yaw; let v;
      if (halted) { [x, z] = tl.anchor; yaw = tl.anchorYaw + Math.sin(t * 0.15) * 0.3; v = 0; } else { sampleAt(tl, t + phase, st); ({ x, z, yaw, v } = st); }
      const fx = Math.cos(yaw); const fz = Math.sin(yaw);
      const pitch = (wave(x + fx * 0.9, z + fz * 0.9, t) - wave(x - fx * 0.9, z - fz * 0.9, t)) * 0.55;
      g.position.set(x, SEA_Y + wave(x, z, t) - 0.08, z);
      g.rotation.set(Math.sin(t * 0.9 + phase) * 0.03, -yaw, pitch, 'YZX');
      wake.visible = v > 0.35; wake.scale.set(Math.min(1, v / 1.5), 1, 1);
    });
    return g;
  }

  // ---------------------------------------------------------------- B747 freighter + airport
  const PLANE_SCALE = 0.6; const FUS_R = 0.185;
  const WING_PTS = [[0.62, 0.16], [-0.82, 1.83], [-1.02, 1.83], [-0.6, 0.62], [-0.38, 0.16]];
  const STAB_PTS = [[-1.42, 0.05], [-1.86, 0.66], [-1.98, 0.66], [-1.86, 0.05]];
  const DIHEDRAL = 0.12; const WING_Y = -0.09;
  const xLE = (z) => 0.62 - ((z - 0.16) / 1.67) * 1.44;
  const wingY = (z) => WING_Y + Math.abs(z) * Math.tan(DIHEDRAL);
  const mirror = (pts) => pts.map(([x, z]) => [x, -z]);
  let PG = null;
  function planeGeos() {
    if (PG) return PG;
    const planform = (pts, depth) => { const s = new T.Shape(); pts.forEach(([x, z], i) => (i ? s.lineTo(x, -z) : s.moveTo(x, -z))); return new T.ExtrudeGeometry(s, { depth, bevelEnabled: false }); };
    const profile = (pts, depth) => { const s = new T.Shape(); pts.forEach(([x, y], i) => (i ? s.lineTo(x, y) : s.moveTo(x, y))); return new T.ExtrudeGeometry(s, { depth, bevelEnabled: false }); };
    PG = {
      fus: new T.LatheGeometry([[0, -2.0], [0.035, -1.98], [0.07, -1.9], [0.11, -1.72], [0.15, -1.45], [0.175, -1.15], [FUS_R, -0.85],
        [FUS_R, 1.4], [0.18, 1.6], [0.165, 1.74], [0.14, 1.85], [0.105, 1.93], [0.06, 1.98], [0, 2.0]].map(([r, y]) => new T.Vector2(r, y)), 24),
      wingR: planform(WING_PTS, 0.035), wingL: planform(mirror(WING_PTS), 0.035),
      stabR: planform(STAB_PTS, 0.022), stabL: planform(mirror(STAB_PTS), 0.022),
      fin: profile([[-1.18, 0.16], [-1.78, 0.98], [-1.96, 0.98], [-1.97, 0.12]], 0.035),
      winglet: profile([[-0.82, 0], [-0.97, 0.17], [-1.05, 0.17], [-1.02, 0]], 0.014),
    };
    return PG;
  }
  function blink(pos, color, rate = 1.2, offset = 0, size = 0.035) {
    const m = mesh(geo('SphereGeometry', size, 6, 6), basic(color), pos);
    anim((t) => { m.visible = ((t + offset) * rate) % 1 < 0.14; });
    return m;
  }
  function bogie(x, z, wheels = 4) {
    const pts = wheels === 2 ? [[0, -0.035], [0, 0.035]] : [[-0.05, -0.04], [-0.05, 0.04], [0.05, -0.04], [0.05, 0.04]];
    return group([x, 0, z], 0, box(0.02, 0.13, 0.02, '#94a3b8', [0, -0.23, 0]),
      pts.map(([dx, dz]) => mesh(geo('CylinderGeometry', 0.045, 0.045, 0.03, 10), mat('#111827'), [dx, -0.297, dz], { rot: [Math.PI / 2, 0, 0] })));
  }
  function b747(grounded, accent = '#1d4ed8') {
    const G = planeGeos();
    const tail = grounded ? '#dc2626' : accent;
    const WHITE = '#f8fafc'; const GREY = '#dfe4ea';
    const flat = [-Math.PI / 2, 0, 0];
    const g = group();
    g.scale.setScalar(PLANE_SCALE);
    g.add(mesh(G.fus, mat(WHITE, { roughness: 0.35 }), [0, 0, 0], { rot: [0, 0, -Math.PI / 2], cast: true }),
      mesh(geo('SphereGeometry', 1, 24, 14), mat(WHITE, { roughness: 0.35 }), [1.3, 0.1, 0], { scale: [0.68, 0.16, 0.15], cast: true }),
      mesh(geo('BoxGeometry', 0.07, 0.03, 0.17), mat('#0f172a', { roughness: 0.2 }), [1.87, 0.165, 0], { rot: [0, 0, -0.55] }),
      [1, -1].map((s) => box(3.0, 0.03, 0.01, accent, [0.25, 0.04, s * (FUS_R - 0.002)])),
      mesh(geo('SphereGeometry', 1, 18, 10), mat('#cbd5e1'), [0.2, -0.1, 0], { scale: [1.65, 0.1, 0.16] }));
    const wr = group([0, WING_Y, 0]); wr.rotation.x = -DIHEDRAL;
    wr.add(mesh(G.wingR, mat(GREY, { roughness: 0.5 }), [0, 0, 0], { rot: flat, cast: true }), mesh(G.winglet, mat(tail), [0, 0.03, 1.83], { rot: [-0.35, 0, 0], cast: true }));
    const wl = group([0, WING_Y, 0]); wl.rotation.x = DIHEDRAL;
    wl.add(mesh(G.wingL, mat(GREY, { roughness: 0.5 }), [0, 0, 0], { rot: flat, cast: true }), mesh(G.winglet, mat(tail), [0, 0.03, -1.83 - 0.014], { rot: [0.35, 0, 0], cast: true }));
    const sr = group([0, 0.04, 0]); sr.rotation.x = -DIHEDRAL; sr.add(mesh(G.stabR, mat(GREY), [0, 0, 0], { rot: flat, cast: true }));
    const sl = group([0, 0.04, 0]); sl.rotation.x = DIHEDRAL; sl.add(mesh(G.stabL, mat(GREY), [0, 0, 0], { rot: flat, cast: true }));
    g.add(wr, wl, sr, sl, mesh(G.fin, mat(tail), [0, 0, -0.0175], { cast: true }));
    [0.66, 1.14, -0.66, -1.14].forEach((z) => {
      const e = { z, x: xLE(Math.abs(z)) + 0.07, y: wingY(z) - 0.11 };
      g.add(group([e.x, e.y, e.z], 0,
        mesh(geo('CylinderGeometry', 0.072, 0.06, 0.32, 18), mat('#e5e7eb', { metalness: 0.25, roughness: 0.35 }), [0, 0, 0], { rot: [0, 0, Math.PI / 2], cast: true }),
        mesh(geo('CylinderGeometry', 0.062, 0.062, 0.006, 18), mat('#1f2937'), [0.161, 0, 0], { rot: [0, 0, Math.PI / 2] }),
        mesh(geo('ConeGeometry', 0.045, 0.09, 12), mat('#64748b'), [-0.2, 0, 0], { rot: [0, 0, Math.PI / 2] }),
        box(0.26, 0.07, 0.016, GREY, [-0.06, 0.08, 0])));
    });
    const gear = group([0, 0, 0], 0, bogie(1.55, 0, 2), bogie(-0.3, 0.13), bogie(-0.3, -0.13), bogie(-0.05, 0.37), bogie(-0.05, -0.37));
    g.add(gear,
      mesh(geo('SphereGeometry', 0.025, 6, 6), basic('#22c55e'), [-0.9, wingY(1.83) + 0.01, 1.84]),
      mesh(geo('SphereGeometry', 0.025, 6, 6), basic('#ef4444'), [-0.9, wingY(1.83) + 0.01, -1.84]),
      blink([0.1, 0.27, 0], '#ef4444', 1.1), blink([0.1, -0.2, 0], '#ef4444', 1.1, 0.5),
      blink([-1.0, wingY(1.83), 1.86], '#ffffff', 0.9, 0.2), blink([-1.0, wingY(1.83), -1.86], '#ffffff', 0.9, 0.2), blink([-2.0, 0.05, 0], '#ffffff', 0.9, 0.6));
    g.userData.gear = gear;
    return g;
  }
  function aircraft(timeline, offset, grounded) {
    const model = b747(grounded);
    const g = group([0, 0, 0], 0, model);
    const st = {};
    anim((t) => {
      if (grounded) {
        g.position.set(timeline.x[0], timeline.y[0], timeline.z[0]); g.rotation.set(0, -timeline.yaw[0], 0, 'YZX');
        model.userData.gear.visible = true; return;
      }
      sampleAt(timeline, t + offset, st);
      g.position.set(st.x, st.y, st.z); g.rotation.set(st.bank, -st.yaw, st.pitch, 'YZX');
      model.userData.gear.visible = st.gear;
    });
    return g;
  }
  function airport(ap, terminal = true) {
    const side = Math.sign(ap.n[0] * -ap.d[1] + ap.n[1] * ap.d[0]) || 1;
    const Z = (off) => off * side;
    const L = ap.L; const W = 1.2;
    const standXs = ap.stands.map((s) => s.s);
    const x0 = Math.min(...standXs) - 1.6; const x1 = Math.max(...standXs) + 1.6;
    const exitX = ap.exitS + 0.3;
    const strip = (a, b, z, w, y, color) => box(Math.abs(b - a), 0.02, w, color, [(a + b) / 2, y, z], { recv: true, mo: { roughness: 0.9 } });
    const g = group([ap.a[0], 0.03, ap.a[1]], -Math.atan2(ap.d[1], ap.d[0]),
      strip(-1.6, L + 1.6, 0, W + 1.0, -0.012, '#c3d5b0'), strip(-1.2, L + 1.2, 0, W, 0, '#2f343b'));
    for (let i = 0; i < Math.floor((L - 1.4) / 0.7); i++) g.add(strip(0.9 + i * 0.7, 1.2 + i * 0.7, 0, 0.05, 0.012, '#f8fafc'));
    [-0.42, -0.28, -0.14, 0.14, 0.28, 0.42].forEach((z) => g.add(strip(0.05, 0.55, z * W * 1.4, 0.06, 0.012, '#f8fafc'), strip(L - 0.55, L - 0.05, z * W * 1.4, 0.06, 0.012, '#f8fafc')));
    [-0.3, 0.3].forEach((z) => g.add(strip(ap.tdS - 0.2, ap.tdS + 0.35, z * W, 0.12, 0.012, '#f8fafc')));
    g.add(strip(ap.connA - 0.3, exitX + 0.3, Z(TAXI_OFF), 0.6, 0.002, '#4b5563'), strip(ap.connA - 0.3, exitX + 0.3, Z(TAXI_OFF), 0.035, 0.014, '#facc15'));
    [ap.connA, exitX].forEach((x) => g.add(box(0.6, 0.02, TAXI_OFF, '#4b5563', [x, 0.002, Z(TAXI_OFF / 2)], { recv: true })));
    g.add(box(x1 - x0, 0.02, STAND_OFF + 1.6 - TAXI_OFF - 0.3, '#c8cdd4', [(x0 + x1) / 2, -0.001, Z((TAXI_OFF + 0.3 + STAND_OFF + 1.6) / 2)], { recv: true }));
    standXs.forEach((x) => g.add(box(0.035, 0.01, STAND_OFF + 0.9 - TAXI_OFF, '#facc15', [x, 0.014, Z((TAXI_OFF + STAND_OFF + 0.9) / 2)]),
      box(0.5, 0.01, 0.05, '#facc15', [x, 0.014, Z(STAND_OFF + 1.25)])));
    [1.5, 1.85, 2.2].forEach((dx) => [-0.25, 0, 0.25].forEach((z) => g.add(mesh(geo('SphereGeometry', 0.035, 6, 6), basic('#fde68a'), [-dx, 0.03, z]))));
    g.add(group([x1 + 0.9, 0, Z(STAND_OFF + 1.2)], 0,
      mesh(geo('CylinderGeometry', 0.16, 0.22, 1.8, 10), mat('#e5e7eb'), [0, 0.9, 0], { cast: true }),
      mesh(geo('CylinderGeometry', 0.36, 0.28, 0.3, 10), mat('#1e3a5f', { metalness: 0.4, roughness: 0.2 }), [0, 1.95, 0], { cast: true }),
      mesh(geo('CylinderGeometry', 0.38, 0.38, 0.05, 10), mat('#f1f5f9'), [0, 2.18, 0])));
    if (terminal) {
      g.add(group([(x0 + x1) / 2, 0, Z(STAND_OFF + 2.2)], 0,
        box(x1 - x0 - 0.4, 0.8, 0.9, '#e2e8f0', [0, 0.4, 0], { cast: true, recv: true }), box(x1 - x0 - 0.3, 0.06, 1.0, '#1d4ed8', [0, 0.82, 0])));
    }
    g.add(group([L + 1.4, 0, Z(-1.3)], 0, mesh(geo('CylinderGeometry', 0.015, 0.015, 0.7, 6), mat('#94a3b8'), [0, 0.35, 0]),
      mesh(geo('ConeGeometry', 0.05, 0.25, 8), mat('#f97316'), [-0.14, 0.68, 0], { rot: [0, 0, Math.PI / 2] })));
    return g;
  }

  // ---------------------------------------------------------------- road vehicles
  function truck(from, to, halted, phase, period = 22, color = '#c2410c') {
    const dir = norm([to[0] - from[0], to[1] - from[1]]);
    const lane = mul([-dir[1], dir[0]], 0.14);
    const g = group([0, 0, 0], 0,
      box(1.0, 0.08, 0.38, '#1f2937', [-0.25, 0.14, 0], { cast: true }),
      container([-0.25, 0.4, 0], halted ? '#9ca3af' : color, [0.92, 0.42, 0.38]),
      box(0.34, 0.44, 0.4, halted ? '#dc2626' : '#f1f5f9', [0.42, 0.29, 0], { cast: true }),
      box(0.02, 0.17, 0.34, '#0f172a', [0.6, 0.36, 0], { mo: { metalness: 0.5, roughness: 0.2 } }),
      [-0.6, -0.15, 0.42].map((x) => [-0.2, 0.2].map((z) => mesh(geo('CylinderGeometry', 0.08, 0.08, 0.06, 10), mat('#111827'), [x, 0.08, z], { rot: [Math.PI / 2, 0, 0] }))).flat(),
      [0.13, -0.13].map((z) => box(0.02, 0.05, 0.07, '#fef9c3', [0.6, 0.18, z], { m: basic('#fef9c3') })));
    const base = -Math.atan2(dir[1], dir[0]);
    if (halted) {
      const p = add(lerp(from, to, 0.12), lane);
      g.position.set(p[0], 0.05, p[1]); g.rotation.y = base;
      return g;
    }
    anim((t) => {
      const cyc = ((t + phase * period) % period) / period;
      let k; let yaw;
      if (cyc < 0.42) { k = ease(cyc / 0.42); yaw = base; } else if (cyc < 0.5) { k = 1; yaw = base + Math.PI * ease((cyc - 0.42) / 0.08); } else if (cyc < 0.92) { k = 1 - ease((cyc - 0.5) / 0.42); yaw = base + Math.PI; } else { k = 0; yaw = base + Math.PI + Math.PI * ease((cyc - 0.92) / 0.08); }
      const side = cyc >= 0.5 && cyc < 0.92 ? -1 : 1;
      const p = add(lerp(from, to, k), mul(lane, side));
      g.position.set(p[0], 0.05, p[1]); g.rotation.y = yaw;
    });
    return g;
  }
  function forklift(a, b, phase) {
    const fork = group([0.42, 0.12, 0], 0, box(0.3, 0.03, 0.26, '#475569', [0, 0, 0]), box(0.3, 0.16, 0.28, '#b45309', [0.02, 0.1, 0], { cast: true }));
    const g = group([0, 0, 0], 0, box(0.5, 0.26, 0.36, '#facc15', [0, 0.2, 0], { cast: true }), box(0.24, 0.18, 0.32, '#1f2937', [-0.12, 0.42, 0], { cast: true }),
      box(0.36, 0.03, 0.34, '#111827', [-0.02, 0.62, 0]), box(0.05, 0.8, 0.3, '#475569', [0.27, 0.45, 0]), fork);
    anim((t) => {
      const s = Math.sin(t * 0.6 + phase);
      const p = lerp(a, b, (s + 1) / 2);
      g.position.set(p[0], 0.03, p[1]);
      g.rotation.y = -Math.atan2(b[1] - a[1], b[0] - a[0]) + (Math.cos(t * 0.6 + phase) < 0 ? Math.PI : 0);
      fork.position.y = 0.12 + Math.max(0, s) * 0.4;
    });
    return g;
  }
  function smoke(at) {
    const g = group(at);
    const puffs = Array.from({ length: 6 }).map(() => mesh(geo('IcosahedronGeometry', 0.5, 1), new T.MeshStandardMaterial({ color: '#e5e7eb', transparent: true, opacity: 0.4, depthWrite: false })));
    puffs.forEach((p) => g.add(p));
    anim((t) => puffs.forEach((m, i) => {
      const k = (t * 0.25 + i / 6) % 1;
      m.position.set(k * 0.5, k * 2.6, -k * 1.4); m.scale.setScalar(0.2 + k * 0.45); m.material.opacity = 0.55 * (1 - k);
    }));
    return g;
  }

  // ---------------------------------------------------------------- sites + hub
  function pin(color) {
    const g = group([0, 3.1, 0], 0, mesh(geo('ConeGeometry', 0.28, 0.6, 16), mat(color), [0, 0, 0], { rot: [Math.PI, 0, 0], cast: true }),
      mesh(geo('SphereGeometry', 0.3, 20, 20), mat(color), [0, 0.42, 0]));
    anim((t) => { g.position.y = 3.1 + Math.sin(t * 3) * 0.15; });
    return g;
  }
  function flare() {
    const m = mesh(geo('RingGeometry', 1.3, 1.55, 40), new T.MeshBasicMaterial({ color: '#ef4444', transparent: true, opacity: 0.5 }), [0, 0.06, 0], { rot: [-Math.PI / 2, 0, 0] });
    anim((t) => { const k = (t * 0.8) % 1; m.scale.setScalar(1 + k * 1.6); m.material.opacity = 0.55 * (1 - k); });
    return m;
  }
  function site(s, disrupted) {
    const [w, h, d] = SIZE[s.supplier_size] || SIZE.Medium;
    const tone = RISK[s.band] || RISK.Medium;
    const selected = S.selected && S.selected.supplier_name === s.supplier_name;
    const roofMat = new T.MeshStandardMaterial({ color: tone, emissive: '#ef4444', emissiveIntensity: 0 });
    const body = mesh(new T.RoundedBoxGeometry(w, h, d, 2, 0.06), mat(selected ? '#ffffff' : '#eef1f5', { roughness: 0.7 }), [0, h / 2 + 0.03, 0], { cast: true, recv: true });
    const g = group([s.pos[0], 0, s.pos[1]], 0, pad([0.2, 0.2], w + 1.5, d + 1.3), body,
      mesh(geo('BoxGeometry', w + 0.1, 0.08, d + 0.1), roofMat, [0, h + 0.07, 0]),
      [-1, 0, 1].map((k) => box(w / 3 + 0.05, 0.05, d + 0.1, tone, [k * w / 3, h + 0.2, 0], { rot: [0, 0, 0.35], cast: true })),
      [-0.3, 0.3].map((x) => box(w * 0.25, 0.7, 0.03, '#64748b', [x * w, 0.42, d / 2 + 0.01])),
      box(w * 0.85, 0.12, 0.02, '#1e3a5f', [0, h * 0.78, d / 2 + 0.01], { mo: { metalness: 0.4, roughness: 0.2 } }),
      Array.from({ length: s.supplier_tier }).map((_, i) => box(0.03, 0.1, d * 0.6, tone, [-w / 2 - 0.01, h - 0.25 - i * 0.18, 0])),
      mesh(geo('CylinderGeometry', 0.1, 0.13, 1.1, 10), mat('#9ca3af'), [w / 2 - 0.3, h + 0.6, -d / 2 + 0.3], { cast: true }),
      group([w / 2 + 0.25, 0.03, -d / 2 + 0.1], 0, yard(1, 2, s.supplier_size === 'Large' ? 2 : 1, s.supplier_tier)),
      !s.has_backup_supplier ? box(0.12, 0.6, 0.12, '#f97316', [-w / 2 + 0.25, h + 0.5, -d / 2 + 0.25]) : null,
      disrupted ? flare() : null,
      selected ? pin('#2563eb') : disrupted ? pin('#ef4444') : null);
    if (disrupted) anim((t) => { roofMat.emissiveIntensity = 0.35 + Math.sin(t * 5) * 0.25; });
    const tip = label(`<strong>${esc(s.supplier_name)}</strong><span>${esc(s.risk_index)} · ${esc(s.band)}</span>`, 'ct-label', [0, h + 1.0, 0]);
    tip.visible = !!selected;
    g.add(tip);
    g.traverse((o) => { o.userData.site = s; });
    S.sites.push({ s, group: g, tip });
    return g;
  }
  function hub() {
    return group([HUB_POS[0], 0, HUB_POS[1]], 0,
      pad([0, 0.3], 13, 6.6, '#cfd4db'),
      mesh(new T.RoundedBoxGeometry(5, 2.4, 3.6, 2, 0.1), mat('#2f6fed', { roughness: 0.6 }), [0, 1.23, 0], { cast: true, recv: true }),
      box(5.2, 0.2, 3.8, '#e5e7eb', [0, 2.5, 0], { cast: true }),
      [-1.6, 1.6].map((dx) => [-0.9, 0.9].map((dz) => box(0.5, 0.2, 0.5, '#9ca3af', [dx, 2.7, dz]))).flat(),
      [-1.5, -0.5, 0.5, 1.5].map((dx) => box(0.8, 1.1, 0.04, '#1e3a8a', [dx, 0.6, 1.81])),
      mesh(geo('CylinderGeometry', 0.22, 0.3, 3.2, 12), mat('#b91c1c'), [-2.0, 2.9, -1.2], { cast: true }),
      mesh(geo('CylinderGeometry', 0.24, 0.24, 0.25, 12), mat('#f8fafc'), [-2.0, 3.6, -1.2]),
      smoke([-2.0, 4.6, -1.2]),
      group([3.2, 0.03, -0.9], 0, yard(2, 4, 2, 3)), group([-5.6, 0.03, -0.9], 0, yard(2, 4, 3, 5)),
      label('Your plant', 'ct-tag ct-tag-blue', [0, 3.6, 0]));
  }
  function dashedLine(points, color, opacity, dash, gap) {
    const g = new T.BufferGeometry().setFromPoints(points.map(([x, y, z]) => new T.Vector3(x, y, z)));
    const l = new T.Line(g, new T.LineDashedMaterial({ color, dashSize: dash, gapSize: gap, transparent: true, opacity }));
    l.computeLineDistances();
    return l;
  }
  const pierRoadEnd = (p) => add(HUB_POS, [Math.sign(p[0] || 1) * 6.6, 0.4]);

  function buildWorld() {
    S.anims = []; S.sites = [];
    const world = S.world; const traffic = S.traffic;
    const { hit, byRegion } = regionStatus(world, S.disruption);
    const root = group();
    root.add(ocean(), clouds(), island([0, 0], HUB_R, HUB_SEED, '#a3cf81'));
    const hubBlocked = (p, m) => (Math.abs(p[0] - HUB_POS[0]) < 7.0 + m && Math.abs(p[1] - HUB_POS[1] - 0.3) < 3.5 + m)
      || inAirport(HUB_AIRPORT, p, m * 0.6)
      || world.regions.some((r) => distToSeg(p, r.pier, pierRoadEnd(r.pier)) < 0.7 + m || Math.hypot(p[0] - r.pier[0], p[1] - r.pier[1]) < 2.2 + m);
    root.add(scenery([0, 0], HUB_R, HUB_SEED, hubBlocked, 36), hub(), airport(HUB_AIRPORT, false),
      label('Air cargo hub · runway 09', 'ct-tag', [0, 0.1, HUB_AIRPORT.a[1] + 2.0]),
      forklift([2.4, -0.2], [4.9, -0.2], 0), forklift([-2.6, 0.0], [-5.0, 0.0], 1.7));
    world.regions.forEach((r, ri) => {
      const st = byRegion[r.region];
      const blocked = (p, m) => r.sites.some((s) => Math.hypot(p[0] - s.pos[0], p[1] - s.pos[1]) < 2.3 + m)
        || r.sites.some((s) => distToSeg(p, s.pos, r.port) < 0.7 + m)
        || Math.hypot(p[0] - r.port[0], p[1] - r.port[1]) < 4.2 + m || inAirport(r.airport, p, m * 0.6);
      root.add(island(r.C, r.R, r.seed, '#9cc97a', st.sitesHit > 0), scenery(r.C, r.R, r.seed, blocked),
        label(`${esc(r.region)}<span>${r.count} site${r.count > 1 ? 's' : ''}${st.sitesHit ? ` · ${st.sitesHit} at risk` : ''}</span>`, 'ct-region', [r.C[0], 0.1, r.C[1] + r.R * 1.2 + 1.2]),
        airport(r.airport), port(r.port, r.u, st.crane, st.crane ? 'Port halted' : st.sea ? 'Berth closed' : null, ri * 3));
      r.sites.forEach((s, i) => {
        const halted = hit(s) || st.truck;
        const toPort = norm([r.port[0] - s.pos[0], r.port[1] - s.pos[1]]);
        root.add(road(s.pos, r.port, halted), site(s, hit(s)),
          truck(add(s.pos, mul(toPort, 1.6)), add(r.port, mul(r.u, -2.6)), halted, (i * 0.31 + ri * 0.17) % 1, 18 + (i % 3) * 3, CONTAINER_COLORS[(i + ri) % CONTAINER_COLORS.length]));
      });
      const fl = traffic.air.fleet[ri];
      const tl = fl.timeline; const t0 = tl.events.outAirStart; const t1 = tl.events.outTD;
      const sm = {};
      const airPts = Array.from({ length: 70 }, (_, k) => { sampleAt(tl, t0 + ((t1 - t0) * k) / 69, sm); return [sm.x, sm.y, sm.z]; });
      const seaPts = traffic.ships[ri].outbound.map(([x, z]) => [x, SEA_Y + 0.12, z]);
      root.add(pier(r.pier, r.u), road(r.pier, pierRoadEnd(r.pier), st.sea),
        truck(add(r.pier, mul(r.u, -0.4)), pierRoadEnd(r.pier), st.sea, ri * 0.27, 20, CONTAINER_COLORS[(ri * 2) % CONTAINER_COLORS.length]),
        dashedLine(seaPts, st.sea ? '#ef4444' : '#e0f2fe', st.sea ? 0.9 : 0.55, 0.7, 0.5), ship(traffic.ships[ri], st.sea, ri * 9.7, ri),
        dashedLine(airPts, st.air ? '#ef4444' : '#7dd3fc', st.air ? 0.85 : 0.35, 0.45, 0.55), aircraft(tl, fl.offset, st.air));
    });
    return root;
  }
  function rebuild() {
    if (S.root) {
      S.root.traverse((o) => { if (o.isCSS2DObject && o.element.parentNode) o.element.parentNode.removeChild(o.element); });
      S.scene.remove(S.root);
    }
    S.root = buildWorld();
    S.scene.add(S.root);
  }

  // ---------------------------------------------------------------- overlay UI
  function kpis() {
    const d = S.data; const s = d.suppliers; const dis = S.disruption;
    const pr = (x) => ((x.by_type || []).find((t) => t.disruption_type === dis) || {});
    const hitN = dis ? s.filter((x) => (pr(x).risk_probability ?? 0) >= DISRUPTED_AT).length : d.summary.critical_or_high;
    const loss = dis ? s.reduce((a, x) => a + (pr(x).revenue_loss_usd || 0), 0) : d.summary.expected_loss_total;
    const st = regionStatus(S.world, dis).byRegion;
    const halted = Object.values(st).reduce((a, r) => ({ sea: a.sea + (r.sea ? 1 : 0), air: a.air + (r.air ? 1 : 0), cranes: a.cranes + (r.crane ? 1 : 0) }), { sea: 0, air: 0, cranes: 0 });
    const res = (s.reduce((a, x) => a + x.resilience.score, 0) / s.length).toFixed(1);
    const card = (ic, l, v, tone) => `<div class="ct-card ct-kpi"><span class="ct-kpi-icon" style="background:${tone}1a;color:${tone}">${ic}</span><div><div class="ct-kpi-label">${l}</div><div class="ct-kpi-value">${v}</div></div></div>`;
    $('ct-kpis').innerHTML = card('🏭', 'Supplier sites', s.length, '#2563eb') + card('⚠️', dis ? `Hit by ${esc(dis)}` : 'Critical / high risk', hitN, '#ef4444')
      + card('💲', dis ? 'Exposure if it hits all' : 'Expected exposure', money(loss), '#f59e0b') + card('🛡️', 'Avg resilience', res, '#16a34a');
    $('ct-fresh').innerHTML = `🕒 Scored ${S.asOf ? S.asOf.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'} · severity ${d.severity_assumed} · sample portfolio
      <button type="button" id="ct-reload" title="Re-score the sample portfolio">↻</button>`;
    $('ct-reload').onclick = () => load(true);
    const nRegions = Object.keys(st).length;
    $('ct-chips').hidden = false;
    $('ct-chips').innerHTML = `<span class="ct-eyebrow">Simulate</span><button type="button" class="${!dis ? 'on' : ''}" data-ct-dis="">Normal operations</button>`
      + d.disruption_types.map((t) => `<button type="button" class="${dis === t ? 'on danger' : ''}" data-ct-dis="${esc(t)}">${esc(t)}</button>`).join('')
      + (dis ? `<span class="ct-halted">🚢 ${halted.sea}/${nRegions} sea lanes ✈️ ${halted.air}/${nRegions} air routes ⚓ ${halted.cranes} ports stopped${!Object.keys(MODE_IMPACT[dis] || {}).length ? ' · site-level only' : ''}</span>` : '');
    $('ct-views').innerHTML = '<span class="ct-eyebrow">View</span>' + Object.entries(VIEWS3D).map(([k, v]) => `<button type="button" class="${S.view === k ? 'on' : ''}" data-ct-view="${k}">${v.label}</button>`).join('');
  }
  function panel() {
    const el = $('ct-panel'); const site0 = S.selected;
    $('ct-hint').hidden = !!site0;
    if (!site0) { el.hidden = true; return; }
    const dis = S.disruption; const type = dis || site0.worst_case.disruption_type;
    const r = S.result;
    el.hidden = false;
    el.innerHTML = `<div class="ct-panel-head"><div><div class="ct-eyebrow">${esc(site0.supplier_region)} · Tier ${site0.supplier_tier} · ${esc(site0.supplier_size)}</div>
        <h3>${esc(site0.supplier_name)}</h3><div class="ct-sub">${esc(site0.industry)} · ${site0.has_backup_supplier ? 'backup supplier qualified' : 'single source (no backup)'}</div></div>
        <button class="ct-icon-btn" type="button" id="ct-close" aria-label="Close">✕</button></div>
      <div class="ct-stats"><div><span>Risk index</span><strong style="color:${RISK[site0.band]}">${esc(site0.risk_index)}</strong><em>${esc(site0.band)}</em></div>
        <div><span>Resilience</span><strong>${esc(site0.resilience.score)}</strong><em>${esc(site0.resilience.band)}</em></div>
        <div><span>Exp. recovery</span><strong>${Math.round(site0.expected_full_recovery_days)}d</strong><em>weighted</em></div></div>
      <div class="ct-eyebrow" style="margin-top:14px">High-impact risk by disruption type</div>
      <div class="ct-bars">${(site0.by_type || []).map((t) => `<div class="ct-bar ${t.disruption_type === dis ? 'on' : ''}"><span>${esc(t.disruption_type)}</span>
        <div><i style="width:${t.risk_probability * 100}%;background:${t.risk_probability >= DISRUPTED_AT ? '#ef4444' : '#3b82f6'}"></i></div><b>${Math.round(t.risk_probability * 100)}%</b></div>`).join('')}</div>
      <div class="ct-note">Worst case: <strong>${esc(site0.worst_case.disruption_type)}</strong>, ${money(site0.worst_case.revenue_loss_usd)} and ${esc(site0.worst_case.full_recovery_days)} days to recover.
        ${(site0.drivers || []).length ? ` Drivers: ${site0.drivers.map(esc).join(', ')}.` : ''}</div>
      <button class="ct-btn" type="button" id="ct-run" ${S.busy ? 'disabled' : ''}>${S.busy ? 'Agents working…' : `▶ Simulate a ${esc(type)} here`}</button>
      ${S.error ? `<div class="ct-error">${esc(S.error)}</div>` : ''}
      ${Object.keys(S.steps).length ? `<ol class="ct-steps">${Object.values(S.steps).map((s) => `<li class="${s.status}"><b>${esc(s.name)}</b>${s.summary ? `<span>${esc(s.summary)}</span>` : ''}</li>`).join('')}</ol>` : ''}
      ${r ? `<div class="ct-result"><div class="ct-stats"><div><span>Priority</span><strong>${esc(((r.impact || {}).priority || {}).level ? r.impact.priority.level.split(' ')[0] : '—')}</strong><em>${esc((r.impact || {}).priority ? r.impact.priority.action_sla : '')}</em></div>
          <div><span>Loss</span><strong>${money((r.recovery || {}).predicted_revenue_loss)}</strong><em>with ${esc((r.recovery || {}).strategy || '')}</em></div>
          <div><span>Recovery</span><strong>${esc((r.recovery || {}).predicted_full_days)}d</strong><em>partial ${esc((r.recovery || {}).predicted_partial_days)}d</em></div></div>
          <div class="ct-eyebrow" style="margin-top:12px">Response: ${esc((r.plan || {}).primary_strategy)} → secondary ${esc((r.plan || {}).secondary_strategy)}</div>
          ${(r.plan || {}).procedure ? `<ol class="ct-playbook">${r.plan.procedure.steps.slice(2, 6).map((s) => `<li>${esc(s.text)}</li>`).join('')}</ol>` : ''}
          <div class="ct-sub" style="margin-top:8px">🛡️ Judge: ${esc((r.judge || {}).verdict)} (${Math.round(((r.judge || {}).overall_score || 0) * 100)}%) · fact-check ${(r.fact_check || {}).passed ? 'passed' : 'flagged'}</div></div>` : ''}`;
    $('ct-close').onclick = () => select(null);
    $('ct-run').onclick = () => simulate(type);
  }
  async function simulate(type) {
    const s = S.selected; const sev = S.data.severity_assumed || 3;
    S.busy = true; S.steps = {}; S.result = null; S.error = null; panel();
    const description = `${type} disruption at ${s.supplier_name}, a ${s.supplier_size.toLowerCase()} Tier ${s.supplier_tier} ${s.industry} supplier in ${s.supplier_region}. `
      + `${s.has_backup_supplier ? 'A backup supplier is qualified.' : 'There is no backup supplier.'} Severity ${sev}/5.`;
    try {
      S.result = await streamAnalyze({ description, use_graph: true, judge: true, top_k: 8,
        incident: { disruption_type: type, industry: s.industry, supplier_region: s.supplier_region, supplier_tier: s.supplier_tier,
          supplier_size: s.supplier_size, has_backup_supplier: s.has_backup_supplier, disruption_severity: sev } },
      (ev) => {
        if (ev.type === 'route') S.steps.supervisor = { status: (ev.next || []).includes('finish') ? 'done' : 'running', name: ev.name, summary: ev.reason };
        if (ev.type === 'agent_start') S.steps[ev.agent] = { status: 'running', name: ev.name };
        if (ev.type === 'agent_done') S.steps[ev.agent] = { status: 'done', name: ev.name, summary: ev.summary };
        if (S.selected === s) panel();
      });
      if (S.result) trackAnalysis(S.result, description, 'Control Tower');
    } catch (e) { S.error = e.message; }
    S.busy = false;
    if (S.selected === s) panel();
  }
  function select(s) {
    S.selected = s; S.steps = {}; S.result = null; S.error = null;
    rebuild(); panel();
  }
  function setView(k) {
    S.view = k;
    const v = VIEWS3D[k];
    S.camera.position.set(...v.position); S.camera.zoom = v.zoom; S.camera.updateProjectionMatrix();
    S.controls.target.set(...v.target); S.controls.update();
    if (S.data) kpis();
  }

  // ---------------------------------------------------------------- lifecycle
  async function load(rescore = false) {
    const csv = await (await fetch(`${API}/portfolio/sample`)).text();
    S.data = await post('/portfolio', { csv, severity: 3 });
    S.asOf = new Date();
    S.world = layoutWorld(S.data.suppliers);
    S.traffic = { ships: S.world.regions.map((r) => buildShipTimeline(r)), air: scheduleFleet(S.world.regions.map((r) => r.airport), HUB_AIRPORT) };
    if (rescore) S.selected = null;
    rebuild(); kpis(); panel();
  }
  function resize() {
    const el = $('tower-canvas');
    const w = el.clientWidth; const h = el.clientHeight;
    if (!w || !h) return;
    S.renderer.setSize(w, h); S.labels.setSize(w, h);
    Object.assign(S.camera, { left: -w / 2, right: w / 2, top: h / 2, bottom: -h / 2 });
    S.camera.updateProjectionMatrix();
  }
  function pick(ev) {
    const rect = S.renderer.domElement.getBoundingClientRect();
    const p = new T.Vector2(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
    const ray = new T.Raycaster();
    ray.setFromCamera(p, S.camera);
    const hitObj = ray.intersectObjects(S.sites.map((x) => x.group), true)[0];
    return hitObj ? hitObj.object.userData.site : null;
  }
  async function mount() {
    if (S.renderer) return;
    try {
      const [three, oc, css2d, rb] = await Promise.all([import('three'), import('three/addons/controls/OrbitControls.js'),
        import('three/addons/renderers/CSS2DRenderer.js'), import('three/addons/geometries/RoundedBoxGeometry.js')]);
      T = { ...three, OrbitControls: oc.OrbitControls, CSS2DRenderer: css2d.CSS2DRenderer, CSS2DObject: css2d.CSS2DObject, RoundedBoxGeometry: rb.RoundedBoxGeometry };
    } catch (e) {
      $('ct-loading').textContent = `3D view unavailable (could not load three.js: ${e.message})`;
      return;
    }
    const el = $('tower-canvas');
    S.renderer = new T.WebGLRenderer({ antialias: true, alpha: true });
    S.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    S.renderer.shadowMap.enabled = true;
    el.appendChild(S.renderer.domElement);
    S.labels = new T.CSS2DRenderer();
    Object.assign(S.labels.domElement.style, { position: 'absolute', inset: '0', pointerEvents: 'none' });
    el.appendChild(S.labels.domElement);
    S.scene = new T.Scene();
    S.camera = new T.OrthographicCamera(-1, 1, 1, -1, -300, 700);
    S.controls = new T.OrbitControls(S.camera, S.renderer.domElement);
    Object.assign(S.controls, { enableDamping: true, minZoom: 5, maxZoom: 80, maxPolarAngle: Math.PI / 2.5, minPolarAngle: Math.PI / 7 });
    S.scene.add(new T.AmbientLight('#ffffff', 0.75), new T.HemisphereLight('#ffffff', '#dbe4f0', 0.5));
    const sun = new T.DirectionalLight('#ffffff', 1.15);
    sun.position.set(25, 40, 15); sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -60, right: 60, top: 60, bottom: -60 });
    S.scene.add(sun);
    setView('network');
    resize();
    new ResizeObserver(resize).observe(el);
    // click a site (ignore drags), hover shows its label
    let down = null;
    S.renderer.domElement.addEventListener('pointerdown', (e) => { down = [e.clientX, e.clientY]; });
    S.renderer.domElement.addEventListener('pointerup', (e) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
      const s = pick(e);
      if (s || S.selected) select(s);
    });
    S.renderer.domElement.addEventListener('pointermove', (e) => {
      if (e.buttons) return;
      const s = pick(e);
      const name = s ? s.supplier_name : null;
      if (name === S.hover) return;
      S.hover = name;
      S.renderer.domElement.style.cursor = s ? 'pointer' : 'auto';
      S.sites.forEach((x) => { x.tip.visible = x.s.supplier_name === name || (S.selected && x.s.supplier_name === S.selected.supplier_name); });
    });
    $('tower').addEventListener('click', (e) => {
      const d = e.target.closest('[data-ct-dis]');
      const v = e.target.closest('[data-ct-view]');
      if (d) { S.disruption = d.dataset.ctDis || null; rebuild(); kpis(); panel(); }
      if (v) setView(v.dataset.ctView);
    });
    for (let i = 0; ; i++) {  // the backend may still be loading the dataset and models
      try { await load(); break; } catch (e) {
        if (i >= 30) { $('ct-loading').textContent = `Could not score the portfolio: ${e.message}`; return; }
        await new Promise((r) => setTimeout(r, 3000));
      }
    }
    $('ct-loading').hidden = true;
    S.clock = new T.Clock();
    const loop = () => {
      requestAnimationFrame(loop);
      const dt = Math.min(0.1, S.clock.getDelta());
      // only animate while the Control Tower is on screen
      if (document.hidden || !$('view-overview').classList.contains('active')) return;
      const t = S.clock.elapsedTime;
      S.anims.forEach((fn) => fn(t, dt));
      S.controls.update();
      S.renderer.render(S.scene, S.camera);
      S.labels.render(S.scene, S.camera);
    };
    loop();
  }
  return { mount, _state: S }; // _state: read-only handle for debugging in the browser console
})();

/* ================================================================== boot */
function bind(id, fn) { const el = $(id); if (el) el.addEventListener('click', () => fn(el)); }
function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem('sc-theme'); } catch { /* storage blocked */ }
  if (saved) document.documentElement.dataset.theme = saved;
  bind('themeBtn', () => {
    const r = document.documentElement;
    const dark = r.dataset.theme ? r.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    r.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('sc-theme', r.dataset.theme); } catch { /* ignore */ }
  });
}

async function boot() {
  initTheme();
  document.querySelectorAll('.nav-item').forEach((b) => b.addEventListener('click', () => show(b.dataset.tab)));
  bind('menuBtn', () => $('sidebar').classList.toggle('open'));
  bind('ck-sample', () => { $('ck-desc').value = SAMPLE; });
  bind('ck-run', runAnalysis);
  bind('ck-whatif', whatIfFromAnalysis);
  bind('ck-open-inc', openIncidentFromAnalysis);
  bind('fb-send', sendFeedback);
  bind('ask-run', runAsk);
  bind('sr-run', runSearch);
  bind('kg-run', runGraph);
  bind('kg-proc-run', runProcedure);
  bind('kg-ins-run', runInsight);
  bind('sim-run', runSimulator);
  bind('dec-run', runDecision);
  bind('tri-run', runTriage);
  bind('sig-add', addSignal);
  bind('sig-live', fetchLive);
  bind('pf-sample', loadPortfolioSample);
  bind('pf-run', runPortfolio);
  bind('nw-run', runOffline);
  bind('inc-refresh', () => loadIncidents().catch((e) => toast(e.message)));
  bind('inc-seed', async (b) => { await guarded(b, 'Loading', () => post('/incidents/seed-demo', {})); loadIncidents(); });
  bind('ev-run', runEval);
  bind('md-retrain', retrain);
  bind('hist-refresh', () => loadHistory().catch((e) => toast(e.message)));
  bind('hist-clear', async () => {
    if (!confirm('Delete every history entry? Saved analyses stay in the database.')) return;
    await api('DELETE', '/history').catch((e) => toast(e.message));
    $('hist-detail').innerHTML = ''; loadHistory();
  });
  $('hist-q').addEventListener('keydown', (e) => { if (e.key === 'Enter') loadHistory().catch((x) => toast(x.message)); });
  [['ask-q', 'ask-run'], ['sr-q', 'sr-run'], ['kg-q', 'kg-run']].forEach(([i, b]) => $(i).addEventListener('keydown', (e) => { if (e.key === 'Enter') $(b).click(); }));

  await refreshHealth();
  for (let i = 0; i < 40 && !state.meta; i++) {
    try { state.meta = await get('/meta'); } catch { await new Promise((r) => setTimeout(r, 3000)); }
  }
  incidentForm('ck-fields', 'ckf', { optional: true });
  incidentForm('sr-filters', 'srf', { optional: true, fields: SEARCH_FIELDS });
  agentCards();
  show(location.hash.slice(1) || 'overview');
  setInterval(refreshHealth, 30000);
}
document.addEventListener('DOMContentLoaded', boot);

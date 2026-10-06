// API Client for the FastAPI backend

const BASE_URL = '/api';

async function handleResponse(res) {
  if (res.status === 401) {
    // deployed with a password gate: session missing or expired
    window.location.href = '/login';
    throw new Error('Sign in required');
  }
  if (!res.ok) {
    let msg = `HTTP error ${res.status}`;
    try {
      const err = await res.json();
      msg = err.detail || err.message || JSON.stringify(err);
    } catch {
      msg = await res.text();
    }
    throw new Error(msg);
  }
  return res.json();
}

export async function fetchHealth() {
  return handleResponse(await fetch(`${BASE_URL}/health`));
}

export async function fetchMeta() {
  return handleResponse(await fetch(`${BASE_URL}/meta`));
}

export async function searchDisruptions(body) {
  return handleResponse(await fetch(`${BASE_URL}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }));
}

export async function classifyIncident(description) {
  return handleResponse(await fetch(`${BASE_URL}/classify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description }),
  }));
}

export async function prioritizeIncidents(incidents) {
  return handleResponse(await fetch(`${BASE_URL}/prioritize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ incidents }),
  }));
}

export async function predictIncident(incident) {
  return handleResponse(await fetch(`${BASE_URL}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(incident),
  }));
}

export async function explainIncident(incident) {
  return handleResponse(await fetch(`${BASE_URL}/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(incident),
  }));
}

export async function askCopilot(question, filters = null, top_k = 6, use_graph = true) {
  return handleResponse(await fetch(`${BASE_URL}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, filters, top_k, use_graph }),
  }));
}

export async function analyzeIncident(payload) {
  return handleResponse(await fetch(`${BASE_URL}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }));
}

export async function streamAnalyze(payload, onEvent, onError, onComplete) {
  try {
    const res = await fetch(`${BASE_URL}/analyze/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.status === 401) { window.location.href = '/login'; return; }
    if (!res.ok) {
      let errText = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        errText = err.detail || JSON.stringify(err);
      } catch {
        errText = await res.text();
      }
      throw new Error(errText);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const block of lines) {
        const trimmed = block.trim();
        if (trimmed.startsWith('data:')) {
          const jsonStr = trimmed.slice(5).trim();
          try {
            const ev = JSON.parse(jsonStr);
            if (ev.type === 'error') {
              onError(new Error(ev.error));
              return;
            }
            onEvent(ev);
            if (ev.type === 'result') {
              onComplete(ev.data);
            }
          } catch (e) {
            console.error('Failed to parse SSE line:', jsonStr, e);
          }
        }
      }
    }
  } catch (err) {
    onError(err);
  }
}

export async function submitFeedback(feedback) {
  return handleResponse(await fetch(`${BASE_URL}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(feedback),
  }));
}

export async function fetchFeedbackStats() {
  return handleResponse(await fetch(`${BASE_URL}/feedback/stats`));
}

export async function fetchInsights() {
  return handleResponse(await fetch(`${BASE_URL}/insights`));
}

export async function fetchModelsMeta() {
  return handleResponse(await fetch(`${BASE_URL}/models`));
}

export async function triggerRetrain() {
  return handleResponse(await fetch(`${BASE_URL}/models/retrain`, {
    method: 'POST',
  }));
}

export async function fetchEvalStatus() {
  return handleResponse(await fetch(`${BASE_URL}/evaluate/status`));
}

export async function fetchEvalResults() {
  return handleResponse(await fetch(`${BASE_URL}/evaluate/results`));
}

export async function runEvaluation(params = {}) {
  return handleResponse(await fetch(`${BASE_URL}/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  }));
}

// ---------------------------------------------------------------- what-if, portfolio, Synapt knowledge
const postJson = async (path, body) => handleResponse(await fetch(`${BASE_URL}${path}`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
}));

export const fetchWhatIf = (incident) => postJson('/whatif', incident);

export const scorePortfolio = (csv, severity = 3) => postJson('/portfolio', { csv, severity });

export async function fetchPortfolioSample() {
  const res = await fetch(`${BASE_URL}/portfolio/sample`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return res.text();
}

export async function fetchSynaptKnowledge() {
  return handleResponse(await fetch(`${BASE_URL}/synapt/knowledge`));
}

export async function fetchSynaptInsight(key) {
  return handleResponse(await fetch(`${BASE_URL}/synapt/insights/${encodeURIComponent(key)}`));
}

export const querySynaptGraph = (question, hops = null) => postJson('/synapt/graph', { question, hops });

export async function fetchSynaptProcedures(query) {
  return handleResponse(await fetch(`${BASE_URL}/synapt/procedures?query=${encodeURIComponent(query)}`));
}

export async function fetchSynaptEpisodes(query = '', top_k = 5) {
  return handleResponse(await fetch(`${BASE_URL}/synapt/episodes?query=${encodeURIComponent(query)}&top_k=${top_k}`));
}

export const labelWithSynapt = (description) => postJson('/synapt/label', { description });

export async function fetchSynaptQuality() {
  return handleResponse(await fetch(`${BASE_URL}/synapt/quality`));
}

// ---------------------------------------------------------------- decision support, early warning, incident desk
const getJson = async (path) => handleResponse(await fetch(`${BASE_URL}${path}`));
const patchJson = async (path, body) => handleResponse(await fetch(`${BASE_URL}${path}`, {
  method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
}));

export const fetchOverview = () => getJson('/overview');
export const fetchDecision = (incident, costs = null) => postJson('/decision', { incident, costs });
export const fetchRootCause = (incident) => postJson('/rootcause', incident);
export const fetchRootCauseSynapt = (incident) => postJson('/rootcause/synapt', incident);
export const fetchEarlyWarning = (csv = null) => postJson('/early-warning', { csv });
export const fetchSignals = () => getJson('/signals');
export const addSignal = (headline, detail = '', send_to_synapt = false) => postJson('/signals', { headline, detail, send_to_synapt });
export const toggleSignal = (id, active) => patchJson(`/signals/${id}`, { active });
export const signalToSynapt = (id) => postJson(`/signals/${id}/synapt`, {});
export const fetchLiveSignals = () => postJson('/signals/fetch-live', {});
export const fetchNetwork = (csv = null) => postJson('/network', { csv });
export const fetchOffline = (supplier, csv = null, disruption_type = null) => postJson('/network/offline', { supplier, csv, disruption_type });
export const fetchIncidents = () => getJson('/incidents');
export const openIncident = (analysis_id) => postJson('/incidents', { analysis_id });
export const seedIncidents = () => postJson('/incidents/seed-demo', {});
export const patchIncident = (id, body) => patchJson(`/incidents/${id}`, body);
export const addIncidentAction = (id, body) => postJson(`/incidents/${id}/actions`, body);
export const patchAction = (id, body) => patchJson(`/actions/${id}`, body);

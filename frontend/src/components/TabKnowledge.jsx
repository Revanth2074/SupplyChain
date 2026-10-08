import React, { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { BookOpen, Brain, Database, Lock, Network, Search, Tags } from 'lucide-react';
import {
  fetchSynaptEpisodes, fetchSynaptInsight, fetchSynaptKnowledge, fetchSynaptProcedures,
  labelWithSynapt, querySynaptGraph,
} from '../api';
import { Callout, PageHeader, Section, Skeleton, Spinner, SynaptPassCard } from './ui';

const TYPE_COLORS = {
  Procedure: '#a78bfa', Step: '#7c3aed', BusinessProcess: '#059669', Chunk: '#64748b', Document: '#94a3b8',
  Entity: '#38bdf8', Concept: '#d97706', Organization: '#f472b6', Episode: '#fb923c',
};
const color = (t) => TYPE_COLORS[t] || '#1d4ed8';

const EXAMPLES = [
  'Which response strategy recovers fastest for a Labor Strike?',
  'How should we respond to a cyber attack at a supplier with no backup?',
  'What happened with port congestion at Asia-Pacific electronics suppliers?',
];

/** Radial layout: ring = hop distance from the question's seed nodes. */
function layout(nodes, W, H) {
  const rings = {};
  nodes.forEach((n) => { const h = Math.min(n.hop ?? 2, 3); (rings[h] = rings[h] || []).push(n); });
  const pos = {};
  const cx = W / 2; const cy = H / 2;
  Object.entries(rings).forEach(([h, list]) => {
    const r = Number(h) === 0 && list.length === 1 ? 0 : 55 + Number(h) * ((Math.min(W, H) / 2 - 70) / 3);
    list.forEach((n, i) => {
      const a = (2 * Math.PI * i) / list.length + Number(h) * 0.6;
      pos[n.id] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
    });
  });
  return pos;
}

function GraphExplorer() {
  const [q, setQ] = useState(EXAMPLES[0]);
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sel, setSel] = useState(null);
  const [hideChunks, setHideChunks] = useState(true);

  const run = async (question = q) => {
    setLoading(true); setError(null); setSel(null);
    try { setRes(await querySynaptGraph(question)); } catch (e) { setError(e.message); } finally { setLoading(false); }
  };

  const W = 760; const H = 520;
  const view = useMemo(() => {
    if (!res?.nodes) return null;
    let nodes = res.nodes.filter((n) => !(hideChunks && n.type === 'Chunk'));
    nodes = [...nodes].sort((a, b) => (b.relevance ?? 0) - (a.relevance ?? 0)).slice(0, 60);
    const ids = new Set(nodes.map((n) => n.id));
    const edges = (res.edges || []).filter((e) => ids.has(e.source) && ids.has(e.target));
    const labelled = new Set(nodes.slice(0, 6).map((n) => n.id));
    return { nodes, edges, labelled, pos: layout(nodes, W, H) };
  }, [res, hideChunks]);

  const types = useMemo(() => [...new Set((view?.nodes || []).map((n) => n.type))], [view]);

  return (
    <Section
      icon={Network}
      iconColor="#a78bfa"
      title="Reasoning-graph explorer"
      subtitle="Ask Synapt a question and see the subgraph its trident_query traversed: rings show hop distance from the matched seed nodes."
    >
      <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
        <input className="input-field" style={{ flex: '1 1 320px' }} value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run()} placeholder="Ask the knowledge graph…" />
        <button className="btn btn-primary" onClick={() => run()} disabled={loading || !q.trim()}>
          {loading ? <Spinner /> : <Search size={16} />} Traverse graph
        </button>
      </div>
      <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.6rem' }}>
        {EXAMPLES.map((e) => (
          <button key={e} className="btn btn-ghost" style={{ fontSize: '0.74rem', padding: '0.2rem 0.5rem' }} onClick={() => { setQ(e); run(e); }}>{e}</button>
        ))}
      </div>
      {error && <Callout tone="danger" style={{ marginTop: '1rem' }}>{error}</Callout>}
      {loading && <div style={{ marginTop: '1rem' }}><Skeleton height={360} /><p className="section-sub" style={{ marginTop: '0.5rem' }}>Graph traversal usually takes 20–40 seconds.</p></div>}
      {res && !loading && view && (
        <div className="grid-auto" style={{ '--min': '380px', marginTop: '1rem', alignItems: 'start' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem', flexWrap: 'wrap', gap: '0.4rem' }}>
              <span className="section-sub">{view.nodes.length} nodes · {view.edges.length} edges shown (of {res.nodes.length} traversed)</span>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
                <input type="checkbox" checked={hideChunks} onChange={(e) => setHideChunks(e.target.checked)} /> hide text chunks
              </label>
            </div>
            <svg viewBox={`0 0 ${W} ${H}`} className="graph-svg" role="img" aria-label="Synapt reasoning subgraph">
              {[1, 2, 3].map((h) => (
                <circle key={h} cx={W / 2} cy={H / 2} r={55 + h * ((Math.min(W, H) / 2 - 70) / 3)} fill="none" stroke="rgba(15, 23, 42, 0.06)" strokeDasharray="3 5" />
              ))}
              {view.edges.map((e, i) => {
                const a = view.pos[e.source]; const b = view.pos[e.target];
                const on = sel && (sel.id === e.source || sel.id === e.target);
                return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={on ? '#7c3aed' : 'rgba(148,163,184,0.25)'} strokeWidth={on ? 1.6 : 1} />;
              })}
              {view.nodes.map((n) => {
                const p = view.pos[n.id];
                const r = 6 + 10 * (n.relevance ?? 0.3);
                return (
                  <g key={n.id} className="gnode" onClick={() => setSel(n)} transform={`translate(${p.x},${p.y})`}>
                    <circle r={r} fill={color(n.type)} fillOpacity={sel?.id === n.id ? 1 : 0.8} stroke={sel?.id === n.id ? '#fff' : 'rgba(0,0,0,0.4)'} />
                    {view.labelled.has(n.id) || sel?.id === n.id ? (
                      <text y={r + 12} textAnchor="middle" fontSize="10" fill="#334155">{(n.name || '').slice(0, 28)}</text>
                    ) : null}
                    <title>{`${n.type}: ${n.name}`}</title>
                  </g>
                );
              })}
            </svg>
            <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
              {types.map((t) => (
                <span key={t} style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ width: 9, height: 9, borderRadius: '50%', background: color(t) }} /> {t}
                </span>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
            {sel ? (
              <div className="glass-card">
                <div className="eyebrow" style={{ color: color(sel.type) }}>{sel.type} · hop {sel.hop ?? '—'}</div>
                <div style={{ fontWeight: 600, color: 'var(--text-strong)', margin: '0.2rem 0 0.4rem' }}>{sel.name}</div>
                {sel.description && <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{sel.description}</p>}
                <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
                  {sel.relevance != null && <span className="badge badge-primary">relevance {Number(sel.relevance).toFixed(2)}</span>}
                  {sel.confidence != null && <span className="badge badge-cyan">confidence {Number(sel.confidence).toFixed(2)}</span>}
                  {sel.health && <span className={`badge ${sel.health === 'intact' ? 'badge-success' : 'badge-warning'}`}>{sel.health}</span>}
                </div>
              </div>
            ) : (
              <p className="section-sub">Click a node to inspect it.</p>
            )}
            <div>
              <div className="eyebrow" style={{ marginBottom: '0.4rem' }}>Synapt answer</div>
              <div className="markdown-body" style={{ fontSize: '0.84rem' }}><ReactMarkdown>{res.answer}</ReactMarkdown></div>
            </div>
            <div>
              <div className="eyebrow" style={{ marginBottom: '0.4rem' }}>Synapt quality signals (Retrieval Pass Card inputs)</div>
              <SynaptPassCard quality={res.quality} compact />
            </div>
            {res.procedures?.length > 0 && (
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                Playbooks used: {res.procedures.map((p) => <span key={p} className="badge badge-purple" style={{ marginRight: 4 }}>{p}</span>)}
              </div>
            )}
          </div>
        </div>
      )}
    </Section>
  );
}

function GraphInsights({ insights }) {
  const [key, setKey] = useState(insights?.[0]?.key);
  const [data, setData] = useState({});
  const [error, setError] = useState(null);
  const [showCypher, setShowCypher] = useState(false);

  useEffect(() => {
    if (!key || data[key]) return;
    setError(null);
    fetchSynaptInsight(key).then((d) => setData((prev) => ({ ...prev, [key]: d }))).catch((e) => setError(e.message));
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const d = data[key];
  const cols = d?.rows?.length ? Object.keys(d.rows[0]) : [];
  return (
    <Section
      icon={Database}
      iconColor="#38bdf8"
      title="Ask the graph"
      subtitle="Read-only Cypher over the Synapt knowledge graph, from fixed templates."
      right={<span className="badge badge-success" title="trident_cypher can read every tenant's graph, so each template is pinned to this provider_id and free-form Cypher is not accepted."><Lock size={12} /> provider-scoped</span>}
    >
      <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '0.9rem' }}>
        {(insights || []).map((i) => (
          <button key={i.key} className={`btn ${key === i.key ? 'btn-primary' : 'btn-secondary'}`} style={{ fontSize: '0.76rem', padding: '0.35rem 0.7rem' }} onClick={() => setKey(i.key)} title={i.description}>
            {i.title}
          </button>
        ))}
      </div>
      {error && <Callout tone="danger">{error}</Callout>}
      {!d && !error && <Skeleton height={160} />}
      {d && (
        <>
          <p className="section-sub" style={{ marginBottom: '0.6rem' }}>{d.description} · {d.rows.length} rows · {d.latency_ms} ms</p>
          <div className="table-wrap" style={{ maxHeight: 360, overflowY: 'auto' }}>
            <table className="table">
              <thead><tr>{cols.map((c) => <th key={c}>{c.replaceAll('_', ' ')}</th>)}</tr></thead>
              <tbody>
                {d.rows.map((r, i) => (
                  <tr key={i}>{cols.map((c) => <td key={c} className={typeof r[c] === 'number' ? 'num' : undefined}>{typeof r[c] === 'number' ? Number(r[c]).toLocaleString(undefined, { maximumFractionDigits: 3 }) : String(r[c] ?? '—')}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
          <button className="btn btn-ghost" style={{ fontSize: '0.74rem', marginTop: '0.5rem', padding: '0.2rem 0.4rem' }} onClick={() => setShowCypher(!showCypher)}>
            {showCypher ? 'Hide' : 'Show'} Cypher
          </button>
          {showCypher && <pre style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: '#4338ca', whiteSpace: 'pre-wrap', background: 'var(--bg-surface)', padding: '0.7rem', borderRadius: 8, marginTop: '0.4rem' }}>{d.cypher}</pre>}
        </>
      )}
    </Section>
  );
}

function Playbooks() {
  const [procs, setProcs] = useState(null);
  const [open, setOpen] = useState(0);
  const [error, setError] = useState(null);
  useEffect(() => {
    fetchSynaptProcedures('Respond to a supply chain disruption playbook')
      .then((d) => setProcs((d.procedures || []).filter((p) => p.name?.startsWith('Respond to')).sort((a, b) => a.name.localeCompare(b.name))))
      .catch((e) => setError(e.message));
  }, []);
  return (
    <Section icon={BookOpen} iconColor="#7c3aed" title="Response playbooks (Synapt procedure store)" subtitle="SOPs ingested as structured procedures; the Response Planning agent follows the matching one.">
      {error && <Callout tone="danger">{error}</Callout>}
      {!procs && !error && <Skeleton height={200} />}
      {procs && procs.length === 0 && <Callout tone="warning">No playbooks found. Run <code>python synapt/ingest_to_synapt.py --only sops</code> in backend/.</Callout>}
      {procs && procs.length > 0 && (
        <>
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '0.8rem' }}>
            {procs.map((p, i) => (
              <button key={p.name} className={`btn ${open === i ? 'btn-primary' : 'btn-secondary'}`} style={{ fontSize: '0.76rem', padding: '0.35rem 0.7rem' }} onClick={() => setOpen(i)}>
                {p.name.replace('Respond to a ', '').replace(' disruption', '')}
              </button>
            ))}
          </div>
          <p className="section-sub" style={{ marginBottom: '0.6rem' }}><strong style={{ color: 'var(--text-body)' }}>{procs[open].name}.</strong> Intent: {procs[open].intent}</p>
          <ol className="steps">{procs[open].steps.map((s) => <li key={s.n}>{s.text}</li>)}</ol>
        </>
      )}
    </Section>
  );
}

function MemoryAndLabels({ knowledge }) {
  const [q, setQ] = useState('Union strike at a Tier 1 brake supplier in Germany, automotive, no backup supplier');
  const [eps, setEps] = useState(null);
  const [lab, setLab] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const run = async () => {
    setBusy(true); setError(null);
    try {
      const [e, l] = await Promise.all([fetchSynaptEpisodes(q, 4), labelWithSynapt(q)]);
      setEps(e); setLab(l);
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };
  const store = knowledge?.episodes?.store;
  const FIELDS = [['disruption_type', 'Disruption type'], ['industry', 'Industry'], ['supplier_region', 'Region'], ['response_type', 'Response strategy'], ['recovery_outcome', 'Recovery outcome']];
  return (
    <Section icon={Brain} iconColor="#fb923c" title="Episodic memory & Synapt-native labelling"
      subtitle="Past situations Synapt remembers, and how Synapt would label a new incident compared with the app's own classifier and strategy model.">
      <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
        <input className="input-field" style={{ flex: '1 1 320px' }} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && run()} />
        <button className="btn btn-primary" onClick={run} disabled={busy || !q.trim()}>{busy ? <Spinner /> : <Tags size={16} />} Recall & label</button>
      </div>
      <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.6rem' }}>
        {store && <span className="badge badge-cyan">episode store: {store.episode_count} episode(s)</span>}
        <span className={`badge ${knowledge?.has_ticket_store ? 'badge-success' : 'badge-warning'}`}>
          ticket store: {knowledge?.has_ticket_store ? 'available' : 'not created yet'}
        </span>
      </div>
      {!knowledge?.has_ticket_store && knowledge && (
        <Callout tone="info" style={{ marginTop: '0.7rem' }}>
          Synapt only creates a ticket store (needed for <code>trident_label_ticket</code> and mined episodes) from the console's
          Data Ingestion › Ticketing source. Upload <code>knowledge_base/tickets/disruption_tickets.xlsx</code> there; until then the labels
          below come from a vote over the nearest Synapt-retrieved cases.
        </Callout>
      )}
      {error && <Callout tone="danger" style={{ marginTop: '0.8rem' }}>{error}</Callout>}
      {(eps || lab) && (
        <div className="grid-auto" style={{ '--min': '340px', marginTop: '1rem', alignItems: 'start' }}>
          <div>
            <div className="eyebrow" style={{ marginBottom: '0.5rem' }}>Recalled episodes</div>
            {(eps?.episodes || []).length === 0 && <p className="section-sub">No similar episodes yet. Episodes accumulate as the agent answers questions.</p>}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {(eps?.episodes || []).map((e) => (
                <div key={e.episode_id} className="glass-card" style={{ padding: '0.7rem' }}>
                  <div style={{ display: 'flex', gap: '0.35rem', marginBottom: '0.3rem', flexWrap: 'wrap' }}>
                    <span className="badge badge-warning">{e.origin}</span>
                    {e.score != null && <span className="badge badge-primary">similarity {Number(e.score).toFixed(2)}</span>}
                    {e.times_seen != null && <span className="badge badge-cyan">seen {e.times_seen}×</span>}
                  </div>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{e.summary}</p>
                </div>
              ))}
            </div>
          </div>
          {lab && (
            <div>
              <div className="eyebrow" style={{ marginBottom: '0.5rem' }}>Synapt vs app ({lab.synapt.method}{lab.synapt.neighbours ? `, ${lab.synapt.neighbours} neighbours` : ''})</div>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Field</th><th>Synapt top label</th><th>App</th><th></th></tr></thead>
                  <tbody>
                    {FIELDS.map(([f, label]) => {
                      const top = lab.synapt.fields?.[f]?.[0];
                      const agree = lab.agreement?.[f];
                      return (
                        <tr key={f}>
                          <td>{label}</td>
                          <td>{top ? <>{top.value} <span className="num" style={{ color: 'var(--text-muted)' }}>({Math.round(top.confidence * 100)}%, n={top.support})</span></> : '—'}</td>
                          <td>{lab.app.fields?.[f] ?? (f === 'recovery_outcome' ? <span style={{ color: 'var(--text-muted)' }}>n/a</span> : '—')}</td>
                          <td>{agree == null ? '' : agree ? <span className="badge badge-success">agree</span> : <span className="badge badge-warning">differs</span>}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {lab.synapt.fastest_response?.length > 0 && (
                <p className="section-sub" style={{ marginTop: '0.6rem' }}>
                  Fastest recovery among Synapt neighbours: {lab.synapt.fastest_response.slice(0, 3).map((r) => `${r.strategy} (${r.avg_full_recovery}d, n=${r.cases})`).join(' · ')}
                </p>
              )}
              <p className="section-sub" style={{ marginTop: '0.3rem' }}>App response strategy = top of the statistics + ML effectiveness ranking.</p>
            </div>
          )}
        </div>
      )}
    </Section>
  );
}

export default function TabKnowledge() {
  const [k, setK] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { fetchSynaptKnowledge().then(setK).catch((e) => setError(e.message)); }, []);
  const s = k?.stats;
  return (
    <div className="page">
      <PageHeader
        icon={Network}
        title="Synapt Knowledge Graph"
        subtitle="Everything the assistant pulls from the Synapt context substrate: the reasoning subgraph behind answers, provider-scoped graph analytics, response playbooks and episodic memory."
        right={s && (
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            <span className="badge badge-primary">{s.doc_count} docs</span>
            <span className="badge badge-primary">{s.chunks} chunks</span>
            <span className="badge badge-purple">{s.nodes} nodes · {s.edges} edges</span>
            <span className="badge badge-cyan">{s.procedures} playbooks</span>
          </div>
        )}
      />
      {error && <Callout tone="danger">Synapt unavailable: {error}</Callout>}
      <GraphExplorer />
      <div className="grid-auto" style={{ '--min': '460px', gap: '1.5rem', alignItems: 'start' }}>
        {k ? <GraphInsights insights={k.insights} /> : <Skeleton height={300} />}
        <Playbooks />
      </div>
      <MemoryAndLabels knowledge={k} />
    </div>
  );
}

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  Play,
  RotateCcw,
  CheckCircle,
  Clock,
  ShieldAlert,
  AlertCircle,
  TrendingDown,
  DollarSign,
  Calendar,
  Layers,
  ChevronDown,
  ChevronUp,
  Award,
  Send,
  Star,
  ExternalLink,
  Sparkles,
  ShieldCheck,
  FileText,
  GitBranch
} from 'lucide-react';
import { streamAnalyze, submitFeedback } from '../api';

const PRESETS = [
  {
    name: 'Ransomware on Tier 2 Avionics (APAC)',
    text: 'A critical ransomware attack on our Tier 2 avionics electronics supplier in Asia-Pacific has completely halted ERP systems and shipments. No backup supplier is qualified. Disruption severity looks high (4/5). Production impact is severe and customer deadlines are at risk.',
    fields: { disruption_type: 'Cyber Attack', industry: 'Aerospace', supplier_tier: 2, supplier_region: 'Asia-Pacific', has_backup_supplier: false, disruption_severity: 4 }
  },
  {
    name: 'Shanghai Port Congestion (Electronics)',
    text: 'Severe container congestion at Shanghai port is delaying shipments of critical microcontrollers from our Tier 1 electronics supplier. We do have a secondary qualified backup supplier in Vietnam. Severity is moderate (3/5).',
    fields: { disruption_type: 'Port Congestion', industry: 'Electronics', supplier_tier: 1, supplier_region: 'Asia-Pacific', has_backup_supplier: true, disruption_severity: 3 }
  },
  {
    name: 'Automotive Strike (Europe)',
    text: 'An unexpected union strike at a medium-sized Tier 1 supplier plant in Germany has frozen production of specialized brake assemblies. No backup supplier exists. Severity 3/5.',
    fields: { disruption_type: 'Labor Strike', industry: 'Automotive', supplier_tier: 1, supplier_region: 'Europe', has_backup_supplier: false, disruption_severity: 3 }
  },
  {
    name: 'Pharma API Plant Explosion (North America)',
    text: 'A major factory explosion damaged the sole active pharmaceutical ingredient (API) synthesis line of our Tier 1 supplier in North America. Critical severity 5/5, single source, estimated 60% production shutdown.',
    fields: { disruption_type: 'Factory Incident', industry: 'Pharmaceuticals', supplier_tier: 1, supplier_region: 'North America', has_backup_supplier: false, disruption_severity: 5 }
  }
];

const AGENT_META = {
  intake: { title: 'Intake & Classification Agent', role: 'Input validation & intent extraction' },
  investigator: { title: 'Investigation Agent', role: 'Synapt MCP Graph RAG + BM25 keyword search' },
  impact: { title: 'Impact Assessment Agent', role: 'HistGradientBoosting ML prediction & risk prioritization' },
  planner: { title: 'Response Planning Agent', role: 'Strategy effectiveness ranking & tactical action plan' },
  recovery: { title: 'Recovery Analysis Agent', role: 'Cohort recovery percentiles & resilience scoring' },
  reporter: { title: 'Report Agent', role: 'Executive leadership briefing synthesis' },
  judge: { title: 'LLM-as-Judge Agent', role: 'Groundedness & safety audit' },
};

export default function TabWorkflow({ options }) {
  const [description, setDescription] = useState(PRESETS[0].text);
  const [customFields, setCustomFields] = useState(PRESETS[0].fields);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [running, setRunning] = useState(false);
  const [activeStep, setActiveStep] = useState(null);
  const [stepsState, setStepsState] = useState({});
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  // Feedback state
  const [rating, setRating] = useState(5);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState('');

  const loadPreset = (preset) => {
    setDescription(preset.text);
    setCustomFields(preset.fields);
  };

  const handleStartWorkflow = () => {
    setRunning(true);
    setResult(null);
    setError(null);
    setStepsState({});
    setActiveStep('intake');
    setFeedbackSent(false);

    const payload = {
      description,
      incident: customFields,
      use_graph: true,
      judge: true,
      top_k: 8,
    };

    streamAnalyze(
      payload,
      (ev) => {
        if (ev.type === 'agent_start') {
          setActiveStep(ev.agent);
          setStepsState((prev) => ({
            ...prev,
            [ev.agent]: { status: 'running', name: ev.name },
          }));
        } else if (ev.type === 'agent_done') {
          setStepsState((prev) => ({
            ...prev,
            [ev.agent]: { status: 'done', name: ev.name, ms: ev.ms, summary: ev.summary, data: ev.data },
          }));
        }
      },
      (err) => {
        setError(err.message || String(err));
        setRunning(false);
        setActiveStep(null);
      },
      (data) => {
        setResult(data);
        setRunning(false);
        setActiveStep(null);
      }
    );
  };

  const handleFeedbackSubmit = async () => {
    if (!result?.analysis_id) return;
    try {
      const resp = await submitFeedback({
        analysis_id: result.analysis_id,
        rating,
        comment: feedbackComment,
        chosen_strategy: result.plan?.primary_strategy,
      });
      setFeedbackSent(true);
      setFeedbackMsg(`Feedback recorded! Synapt MCP forward: ${resp.synapt_sent ? 'Sent' : 'Stored locally'}.`);
    } catch (e) {
      setFeedbackMsg(`Failed to submit feedback: ${e.message}`);
    }
  };

  return (
    <div style={{ maxWidth: '1440px', margin: '0 auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Top Banner / Scenario Selector */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
          <div>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <Sparkles size={22} color="#6366f1" />
              Multi-Agent Supply Chain Disruption Cockpit
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Autonomous 7-agent workflow investigating historical precedents via Synapt MCP, forecasting impact & auditing recovery playbooks.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {PRESETS.map((p, idx) => (
              <button
                key={idx}
                onClick={() => loadPreset(p)}
                className="btn btn-secondary"
                style={{ fontSize: '0.78rem', padding: '0.4rem 0.75rem' }}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>

        {/* Input Area */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <textarea
            className="textarea-field"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the disruption (e.g., supplier, region, nature of failure, backup status)..."
            style={{ fontSize: '0.95rem', resize: 'vertical' }}
          />

          {/* Advanced override toggle */}
          <div>
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="btn btn-ghost"
              style={{ fontSize: '0.8rem', padding: '0.2rem 0.5rem' }}
            >
              {showAdvanced ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {showAdvanced ? 'Hide Structured Overrides' : 'Adjust Structured Parameters'}
            </button>
          </div>

          {showAdvanced && (
            <div className="glass-card" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Disruption Type</label>
                <select
                  className="select-field"
                  value={customFields.disruption_type || ''}
                  onChange={(e) => setCustomFields({ ...customFields, disruption_type: e.target.value })}
                >
                  <option value="">(Auto Detect)</option>
                  {options?.disruption_type?.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Industry</label>
                <select
                  className="select-field"
                  value={customFields.industry || ''}
                  onChange={(e) => setCustomFields({ ...customFields, industry: e.target.value })}
                >
                  <option value="">(Auto Detect)</option>
                  {options?.industry?.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Supplier Tier</label>
                <select
                  className="select-field"
                  value={customFields.supplier_tier || ''}
                  onChange={(e) => setCustomFields({ ...customFields, supplier_tier: Number(e.target.value) })}
                >
                  <option value="">(Auto Detect)</option>
                  <option value="1">Tier 1 (Direct)</option>
                  <option value="2">Tier 2 (Sub-tier)</option>
                  <option value="3">Tier 3 (Raw materials)</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Region</label>
                <select
                  className="select-field"
                  value={customFields.supplier_region || ''}
                  onChange={(e) => setCustomFields({ ...customFields, supplier_region: e.target.value })}
                >
                  <option value="">(Auto Detect)</option>
                  {options?.supplier_region?.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Disruption Severity (1-5)</label>
                <select
                  className="select-field"
                  value={customFields.disruption_severity || 3}
                  onChange={(e) => setCustomFields({ ...customFields, disruption_severity: Number(e.target.value) })}
                >
                  {[1, 2, 3, 4, 5].map((s) => <option key={s} value={s}>Severity {s}</option>)}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Backup Supplier</label>
                <select
                  className="select-field"
                  value={customFields.has_backup_supplier === undefined ? '' : String(customFields.has_backup_supplier)}
                  onChange={(e) => setCustomFields({ ...customFields, has_backup_supplier: e.target.value === 'true' })}
                >
                  <option value="false">No Backup (Single Source)</option>
                  <option value="true">Qualified Backup Available</option>
                </select>
              </div>
            </div>
          )}

          {/* Action button */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
            <button
              onClick={handleStartWorkflow}
              disabled={running || !description.trim()}
              className="btn btn-primary"
              style={{ padding: '0.65rem 1.5rem', fontSize: '0.95rem' }}
            >
              {running ? (
                <>
                  <div className="animate-spin" style={{ width: 16, height: 16, border: '2px solid #fff', borderTopColor: 'transparent', borderRadius: '50%' }} />
                  Investigating Multi-Agent Workflow...
                </>
              ) : (
                <>
                  <Play size={18} fill="#fff" />
                  Execute Autonomous Investigation
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="glass-panel" style={{ padding: '1rem', borderLeft: '4px solid var(--accent-danger)', background: 'rgba(239, 68, 68, 0.1)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <AlertCircle size={20} color="var(--accent-danger)" />
            <strong style={{ color: '#fca5a5' }}>Workflow Error:</strong>
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* 7-Agent Interactive Timeline */}
      <div className="glass-panel" style={{ padding: '1.25rem' }}>
        <h3 style={{ fontSize: '1rem', marginBottom: '0.85rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Layers size={18} color="var(--accent-primary)" />
          Multi-Agent Pipeline Progression (SSE Stream)
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
          {Object.entries(AGENT_META).map(([id, meta]) => {
            const st = stepsState[id];
            const isCurrent = activeStep === id;
            const isDone = st?.status === 'done';

            return (
              <div
                key={id}
                className="glass-card"
                style={{
                  borderLeft: isCurrent
                    ? '3px solid var(--accent-primary)'
                    : isDone
                    ? '3px solid var(--accent-success)'
                    : '1px solid var(--border-subtle)',
                  background: isCurrent ? 'rgba(99, 102, 241, 0.12)' : 'var(--bg-surface)',
                  padding: '0.75rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: isCurrent ? '#a5b4fc' : isDone ? '#6ee7b7' : 'var(--text-muted)' }}>
                    {meta.title.split(' ')[0]}
                  </span>
                  {isCurrent && (
                    <span className="badge badge-primary animate-pulse-slow" style={{ fontSize: '0.65rem' }}>Active</span>
                  )}
                  {isDone && (
                    <span className="badge badge-success" style={{ fontSize: '0.65rem' }}>{st.ms}ms</span>
                  )}
                  {!isCurrent && !isDone && (
                    <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Waiting</span>
                  )}
                </div>
                <div style={{ fontSize: '0.8rem', fontWeight: 500, color: '#fff', marginBottom: '0.2rem' }}>
                  {meta.title}
                </div>
                <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', lineHeight: 1.3 }}>
                  {st?.summary || meta.role}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Results Display */}
      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Executive KPI Callouts */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
            {/* Priority Card */}
            <div className="glass-card" style={{ borderTop: '3px solid #ef4444' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>PRIORITY LEVEL</span>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.3rem' }}>
                <span style={{ fontSize: '1.5rem', fontWeight: 700, color: '#fff' }}>
                  {result.impact?.priority?.level}
                </span>
                <span style={{ fontSize: '0.85rem', color: '#fca5a5' }}>
                  Score {result.impact?.priority?.score}/100
                </span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.35rem' }}>
                SLA: {result.impact?.priority?.action_sla}
              </p>
            </div>

            {/* Production Impact */}
            <div className="glass-card" style={{ borderTop: '3px solid #f59e0b' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>EST. PRODUCTION IMPACT</span>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.3rem' }}>
                <span style={{ fontSize: '1.5rem', fontWeight: 700, color: '#fcd34d' }}>
                  {result.impact?.prediction?.production_impact_pct}%
                </span>
                <TrendingDown size={18} color="#f59e0b" />
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.35rem' }}>
                Risk Probability: {(result.impact?.prediction?.risk_probability * 100).toFixed(1)}% ({result.impact?.prediction?.risk_level})
              </p>
            </div>

            {/* Financial Loss */}
            <div className="glass-card" style={{ borderTop: '3px solid #6366f1' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>EST. REVENUE LOSS</span>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.3rem' }}>
                <span style={{ fontSize: '1.5rem', fontWeight: 700, color: '#fff' }}>
                  ${Number(result.impact?.prediction?.revenue_loss_usd).toLocaleString()}
                </span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.35rem' }}>
                HistGradientBoosting prediction
              </p>
            </div>

            {/* Recovery Time */}
            <div className="glass-card" style={{ borderTop: '3px solid #10b981' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>RECOVERY HORIZON</span>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.3rem' }}>
                <span style={{ fontSize: '1.5rem', fontWeight: 700, color: '#6ee7b7' }}>
                  {result.recovery?.predicted_full_days} Days
                </span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  (Partial ≈{result.recovery?.predicted_partial_days}d)
                </span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.35rem' }}>
                Resilience: {result.impact?.prediction?.resilience_score?.score}/100 ({result.impact?.prediction?.resilience_score?.band})
              </p>
            </div>
          </div>

          {/* Section: Executive Briefing & Action Plan */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(460px, 1fr))', gap: '1.5rem' }}>
            {/* Executive Briefing */}
            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <h3 style={{ fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <FileText size={20} color="#6366f1" />
                  Executive Disruption Briefing
                </h3>
                <span className="badge badge-purple">Synthesized by Report Agent</span>
              </div>
              <div className="markdown-body">
                <ReactMarkdown>{result.summary}</ReactMarkdown>
              </div>
            </div>

            {/* Action Plan */}
            <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <h3 style={{ fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Award size={20} color="#10b981" />
                  Recommended Response Strategy
                </h3>
                <span className="badge badge-success">
                  Primary: {result.plan?.primary_strategy}
                </span>
              </div>

              <div style={{ background: 'rgba(99, 102, 241, 0.08)', padding: '0.85rem', borderRadius: '8px', border: '1px solid rgba(99, 102, 241, 0.2)' }}>
                <strong style={{ color: '#a5b4fc', fontSize: '0.85rem' }}>Strategic Rationale:</strong>
                <p style={{ fontSize: '0.85rem', color: '#e2e8f0', marginTop: '0.3rem' }}>
                  {result.plan?.rationale}
                </p>
                <div style={{ marginTop: '0.5rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  Fallback Alternative: <strong>{result.plan?.secondary_strategy}</strong>
                </div>
              </div>

              {/* Immediate Actions */}
              <div>
                <h4 style={{ fontSize: '0.9rem', color: '#f8fafc', marginBottom: '0.5rem' }}>
                  Immediate Action Items (0-72h):
                </h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {result.plan?.immediate_actions?.map((act, i) => (
                    <div key={i} className="glass-card" style={{ padding: '0.65rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
                      <div>
                        <div style={{ fontSize: '0.85rem', fontWeight: 500, color: '#fff' }}>
                          {act.action}
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          Owner: <strong style={{ color: '#cbd5e1' }}>{act.owner}</strong>
                        </span>
                      </div>
                      <span className="badge badge-warning" style={{ whiteSpace: 'nowrap' }}>
                        {act.timeframe}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Risks & Mitigation */}
              {result.plan?.risks?.length > 0 && (
                <div>
                  <h4 style={{ fontSize: '0.85rem', color: '#fca5a5', marginBottom: '0.4rem' }}>
                    Identified Operational Risks:
                  </h4>
                  <ul style={{ paddingLeft: '1.2rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    {result.plan?.risks?.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}
            </div>
          </div>

          {/* Section: Historical Precedents & Synapt Subgraph */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <h3 style={{ fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <GitBranch size={20} color="#06b6d4" />
                  Synapt Knowledge Graph & Similar Precedents ({result.cases?.length} Retrieved)
                </h3>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  Grounded across {result.search_meta?.semantic_source || 'Synapt MCP'} and local BM25 index
                </p>
              </div>
              {result.graph?.confidence && (
                <span className="badge badge-cyan">
                  Graph Confidence: {(result.graph.confidence * 100).toFixed(0)}%
                </span>
              )}
            </div>

            {/* Subgraph Answer if present */}
            {result.graph?.answer && (
              <div style={{ background: 'rgba(6, 182, 212, 0.08)', padding: '0.85rem', borderRadius: '8px', border: '1px solid rgba(6, 182, 212, 0.25)', marginBottom: '1rem' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#67e8f9' }}>
                  SYNAPT TRIDENT GRAPH-RAG DIRECT ANSWER:
                </span>
                <p style={{ fontSize: '0.85rem', color: '#e2e8f0', marginTop: '0.35rem' }}>
                  {result.graph.answer}
                </p>
              </div>
            )}

            {/* Case Cards Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '0.85rem' }}>
              {result.cases?.slice(0, 6).map((c) => (
                <div key={c.disruption_id} className="glass-card" style={{ padding: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#a5b4fc', fontSize: '0.88rem' }}>
                      {c.disruption_id}
                    </span>
                    <div style={{ display: 'flex', gap: '0.35rem' }}>
                      {c.from_synapt && <span className="badge badge-purple" style={{ fontSize: '0.65rem' }}>Synapt</span>}
                      {c.similarity !== null && (
                        <span className="badge badge-success" style={{ fontSize: '0.65rem' }}>
                          {(c.similarity * 100).toFixed(0)}% Match
                        </span>
                      )}
                    </div>
                  </div>

                  <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                    {c.text}
                  </p>

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.4rem', marginTop: 'auto' }}>
                    <span>Strategy: <strong style={{ color: '#fff' }}>{c.response_type}</strong></span>
                    <span>Recovery: <strong style={{ color: '#6ee7b7' }}>{c.full_recovery_days}d</strong></span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Section: LLM-as-Judge Audit Scorecard */}
          {result.judge && (
            <div className="glass-panel" style={{ padding: '1.5rem', borderLeft: `4px solid ${result.judge.verdict === 'approve' ? '#10b981' : '#f59e0b'}` }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div>
                  <h3 style={{ fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <ShieldCheck size={20} color={result.judge.verdict === 'approve' ? '#10b981' : '#f59e0b'} />
                    LLM-as-Judge Audit Evaluation
                  </h3>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    Evaluated by {result.judge.model || 'Auditor'} via 6-dimension supply chain rubric
                  </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <span className={`badge ${result.judge.verdict === 'approve' ? 'badge-success' : 'badge-warning'}`} style={{ fontSize: '0.85rem', padding: '0.3rem 0.8rem' }}>
                    VERDICT: {result.judge.verdict?.toUpperCase()}
                  </span>
                  <span style={{ fontSize: '1.2rem', fontWeight: 700, color: '#fff' }}>
                    {(result.judge.overall_score * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* Rubric scores */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
                {Object.entries(result.judge.scores || {}).map(([crit, sc]) => (
                  <div key={crit} className="glass-card" style={{ padding: '0.6rem', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'capitalize' }}>{crit}</div>
                    <div style={{ fontSize: '1.2rem', fontWeight: 700, color: sc >= 4 ? '#6ee7b7' : sc === 3 ? '#fcd34d' : '#fca5a5' }}>
                      {sc} / 5
                    </div>
                  </div>
                ))}
              </div>

              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                <strong>Auditor Summary:</strong> {result.judge.summary}
              </div>
            </div>
          )}

          {/* Section: Continuous Improvement & Feedback Loop */}
          <div className="glass-panel" style={{ padding: '1.5rem', background: 'linear-gradient(180deg, rgba(99, 102, 241, 0.05) 0%, rgba(22, 28, 46, 0.7) 100%)' }}>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <RotateCcw size={18} color="#6366f1" />
              Continuous Improvement Feedback Loop
            </h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
              Ratings feed into strategy preference multipliers, while query ID ({result.analysis_id}) is forwarded back to Synapt MCP <code>trident_feedback</code>.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxWidth: '600px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{ fontSize: '0.85rem', color: '#fff' }}>Rating:</span>
                {[1, 2, 3, 4, 5].map((s) => (
                  <button
                    key={s}
                    onClick={() => setRating(s)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                  >
                    <Star size={22} fill={s <= rating ? '#f59e0b' : 'none'} color={s <= rating ? '#f59e0b' : '#64748b'} />
                  </button>
                ))}
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>({rating} of 5 stars)</span>
              </div>

              <input
                className="input-field"
                type="text"
                placeholder="Optional feedback: Did this strategy work? Were recovery estimates accurate?"
                value={feedbackComment}
                onChange={(e) => setFeedbackComment(e.target.value)}
              />

              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <button
                  onClick={handleFeedbackSubmit}
                  disabled={feedbackSent}
                  className="btn btn-primary"
                  style={{ fontSize: '0.85rem', padding: '0.5rem 1rem' }}
                >
                  <Send size={15} />
                  {feedbackSent ? 'Feedback Recorded' : 'Submit Feedback to Assistant & Synapt'}
                </button>
                {feedbackMsg && (
                  <span style={{ fontSize: '0.8rem', color: '#6ee7b7' }}>{feedbackMsg}</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

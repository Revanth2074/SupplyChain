import React, { useState, useEffect } from 'react';
import {
  CheckCircle2,
  Play,
  RotateCcw,
  ShieldCheck,
  AlertCircle,
  TrendingUp,
  Cpu,
  Database,
  RefreshCw,
  Star
} from 'lucide-react';
import {
  fetchEvalStatus,
  fetchEvalResults,
  runEvaluation,
  fetchFeedbackStats,
  triggerRetrain,
  fetchSynaptQuality
} from '../api';
import { Section, SynaptPassCard } from './ui';

export default function TabEval() {
  const [evalStatus, setEvalStatus] = useState(null);
  const [evalResults, setEvalResults] = useState(null);
  const [feedbackStats, setFeedbackStats] = useState(null);
  const [running, setRunning] = useState(false);
  const [retraining, setRetraining] = useState(false);
  const [retrainMsg, setRetrainMsg] = useState(null);
  const [useGraph, setUseGraph] = useState(true);
  const [synQuality, setSynQuality] = useState(null);

  useEffect(() => {
    fetchSynaptQuality().then(setSynQuality).catch(() => {});
  }, [evalResults]);

  const loadData = async () => {
    try {
      const [st, fb] = await Promise.all([
        fetchEvalStatus(),
        fetchFeedbackStats(),
      ]);
      setEvalStatus(st);
      setFeedbackStats(fb);

      if (st.has_results) {
        const res = await fetchEvalResults();
        setEvalResults(res);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(async () => {
      try {
        const st = await fetchEvalStatus();
        setEvalStatus(st);
        if (st.running) {
          setRunning(true);
        } else if (running) {
          setRunning(false);
          const res = await fetchEvalResults();
          setEvalResults(res);
        }
      } catch (e) {
        // ignore polling errors
      }
    }, 4000);
    return () => clearInterval(interval);
  }, [running]);

  const handleStartEval = async () => {
    setRunning(true);
    try {
      await runEvaluation({ limit: 4, use_graph: useGraph, include_feedback: true });
    } catch (err) {
      alert(`Eval launch error: ${err.message}`);
      setRunning(false);
    }
  };

  const handleRetrain = async () => {
    setRetraining(true);
    setRetrainMsg(null);
    try {
      const resp = await triggerRetrain();
      setRetrainMsg(`Models retraining started in background! Incorporated ${resp.feedback_rows} user-reported outcomes.`);
    } catch (err) {
      setRetrainMsg(`Retraining failed: ${err.message}`);
    } finally {
      setRetraining(false);
    }
  };

  return (
    <div className="page">
      {/* Header */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h2 style={{ fontSize: '1.3rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <CheckCircle2 size={22} color="#10b981" />
              DeepEval Suite & Continuous Improvement Center
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Rigorous RAG & agent evaluation via DeepEval metrics (Faithfulness, Relevancy, G-Eval Recommendation & Impact Quality) plus continuous learning from user feedback.
            </p>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <label style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', gap: '0.35rem', alignItems: 'center' }}
              title="Adds Synapt graph-RAG to each test case (about 40s per case) so Synapt's own quality scores are recorded next to DeepEval.">
              <input type="checkbox" checked={useGraph} onChange={(e) => setUseGraph(e.target.checked)} disabled={running} />
              Include Synapt graph-RAG
            </label>
            <button
              onClick={handleStartEval}
              disabled={running}
              className="btn btn-primary"
            >
              {running ? (
                <>
                  <div className="animate-spin" style={{ width: 16, height: 16, border: '2px solid #fff', borderTopColor: 'transparent', borderRadius: '50%' }} />
                  Evaluating Test Cases ({evalStatus?.progress || 0} / {evalStatus?.total || '...'})
                </>
              ) : (
                <>
                  <Play size={16} fill="#fff" />
                  Run DeepEval Test Suite
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {evalResults?.n_fallback_cases > 0 && (
        <div className="glass-card" style={{ borderLeft: '4px solid #d97706', fontSize: '0.86rem' }}>
          <strong>{evalResults.n_fallback_cases} of {evalResults.n_cases} cases could not be scored by the LLM judge</strong>
          {' '}(the judge gateway was unavailable). DeepEval and the LLM judge are averaged over the {evalResults.n_llm_cases} judged cases only; the workflow itself never uses the LLM.
          {evalResults.summary.fallback_mode && (
            <span style={{ color: 'var(--text-muted)' }}>
              {' '}Unjudged cases: rule classifier {(evalResults.summary.fallback_mode.classification_accuracy * 100).toFixed(1)}% accurate,
              rule audit {(evalResults.summary.fallback_mode.rule_audit_overall * 100).toFixed(0)}%,
              fact-check {(evalResults.summary.fallback_mode.fact_check_pass_rate * 100).toFixed(0)}%.
            </span>
          )}
        </div>
      )}

      {/* DeepEval Summary Scores */}
      {evalResults?.summary && (
        <div className="grid-auto" style={{ '--min': '200px' }}>
          {/* Classification Accuracy */}
          <div className="glass-card" style={{ borderLeft: '4px solid #2563eb' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>CLASSIFICATION ACCURACY</span>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--text-strong)', marginTop: '0.2rem' }}>
              {evalResults.summary.classification_accuracy ? `${(evalResults.summary.classification_accuracy * 100).toFixed(1)}%` : 'N/A'}
            </div>
            <span style={{ fontSize: '0.72rem', color: '#4338ca' }}>Golden Disruption Cases</span>
          </div>

          {/* Retrieval Precision */}
          <div className="glass-card" style={{ borderLeft: '4px solid #06b6d4' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>RETRIEVAL TYPE PRECISION</span>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#0e7490', marginTop: '0.2rem' }}>
              {evalResults.summary.retrieval_type_precision ? `${(evalResults.summary.retrieval_type_precision * 100).toFixed(1)}%` : 'N/A'}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Synapt + BM25 Precision</span>
          </div>

          {/* LLM Judge Score */}
          <div className="glass-card" style={{ borderLeft: '4px solid #10b981' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>LLM-AS-JUDGE OVERALL</span>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#059669', marginTop: '0.2rem' }}>
              {evalResults.summary.llm_judge_overall ? `${(evalResults.summary.llm_judge_overall * 100).toFixed(1)}%` : 'N/A'}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>6-criteria rubric audit</span>
          </div>

          {/* DeepEval GEval Recommendation Quality */}
          {Object.entries(evalResults.summary.deepeval || {}).map(([metric, score]) => (
            <div key={metric} className="glass-card" style={{ borderLeft: '4px solid #8b5cf6' }}>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                {metric.replace(/([A-Z])/g, ' $1').trim()}
              </span>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#7c3aed', marginTop: '0.2rem' }}>
                {score !== null ? `${(score * 100).toFixed(0)}%` : 'Pending'}
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>DeepEval 4.x Evaluator</span>
            </div>
          ))}
        </div>
      )}

      {/* Synapt's own quality signals next to DeepEval */}
      <Section
        icon={ShieldCheck}
        iconColor="#0e7490"
        title="Synapt answer quality (alongside DeepEval)"
        subtitle={`Synapt scores every graph-RAG answer itself (knowledge, procedure and graph confidence plus a trust signal). Averages over the last ${synQuality?.n ?? 0} Synapt queries made by the app.`}
      >
        {synQuality?.n ? (
          <>
            <SynaptPassCard quality={{
              ...synQuality.summary,
              degraded: (synQuality.summary.degraded_rate ?? 0) > 0.5,
              degraded_reasons: Object.keys(synQuality.summary.degraded_reasons || {}),
              traversal_s: synQuality.summary.traversal_s,
            }} />
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.75rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
              <span>Trust degraded on <strong style={{ color: '#b45309' }}>{Math.round((synQuality.summary.degraded_rate ?? 0) * 100)}%</strong> of answers</span>
              {evalResults?.summary?.fact_check_pass_rate != null && (
                <span>· Briefing fact-check pass rate in the last eval: <strong style={{ color: '#059669' }}>{Math.round(evalResults.summary.fact_check_pass_rate * 100)}%</strong></span>
              )}
              {evalResults?.summary?.synapt?.n > 0 && (
                <span>· Eval run Synapt confidence: <strong style={{ color: '#0e7490' }}>{Math.round((evalResults.summary.synapt.confidence ?? 0) * 100)}</strong> over {evalResults.summary.synapt.n} cases</span>
              )}
            </div>
            <div className="table-wrap" style={{ marginTop: '0.9rem', maxHeight: 280, overflowY: 'auto' }}>
              <table className="table">
                <thead><tr><th>Source</th><th>Question</th><th>Overall</th><th>Knowledge</th><th>Procedure</th><th>Graph</th><th>Trust</th></tr></thead>
                <tbody>
                  {synQuality.recent.map((r) => (
                    <tr key={r.ts}>
                      <td><span className="badge badge-primary">{r.source}</span></td>
                      <td style={{ maxWidth: 420 }}>{r.question?.slice(0, 120)}</td>
                      {['confidence', 'knowledge_confidence', 'procedural_confidence', 'graph_confidence'].map((k) => (
                        <td key={k} className="num">{r[k] == null ? '—' : Math.round(r[k] * 100)}</td>
                      ))}
                      <td>{r.degraded ? <span className="badge badge-warning">degraded</span> : <span className="badge badge-success">ok</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="section-sub">No Synapt graph queries recorded yet. Run an analysis in the cockpit or a question in the Knowledge Graph tab.</p>
        )}
      </Section>

      {/* Evaluated Test Cases Table */}
      {evalResults?.rows && (
        <div className="glass-panel" style={{ padding: '1.5rem' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>
            Evaluation Benchmark Cases ({evalResults.rows.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {evalResults.rows.map((row) => (
              <div key={row.id} className="glass-card" style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span className="badge badge-primary">{row.id}</span>
                    <strong style={{ fontSize: '0.9rem', color: 'var(--text-strong)' }}>
                      {row.classification?.disruption_type} ({row.classification?.industry || 'General'})
                    </strong>
                    {row.source === 'feedback-regression' && (
                      <span className="badge badge-warning">Regression Case</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <span className="badge badge-success">
                      Similarity: {(row.avg_similarity * 100).toFixed(0)}%
                    </span>
                    {row.judge?.overall && (
                      <span className="badge badge-purple">
                        Judge: {(row.judge.overall * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                </div>

                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  "{row.input}"
                </p>

                {row.llm_used === false && (
                  <span className="badge badge-warning" style={{ fontSize: '0.72rem' }}>LLM judge unreachable · DeepEval skipped</span>
                )}
                {/* DeepEval metric chips */}
                {row.llm_used !== false && row.metrics && Object.keys(row.metrics).length > 0 && (
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.5rem' }}>
                    {Object.entries(row.metrics).map(([mName, mVal]) => (
                      <span key={mName} className={`badge ${mVal.passed ? 'badge-success' : 'badge-danger'}`} style={{ fontSize: '0.72rem' }}>
                        {mName}: {mVal.score !== null ? (mVal.score * 100).toFixed(0) + '%' : 'Err'}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Feedback Loop Telemetry & Retrain Model */}
      <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <RotateCcw size={18} color="#2563eb" />
              Continuous Learning Telemetry & Active Model Retraining
            </h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Operational user ratings generate multiplier boosts for effective response strategies. Reported actual recoveries feed into active retraining data.
            </p>
          </div>

          <button
            onClick={handleRetrain}
            disabled={retraining}
            className="btn btn-secondary"
          >
            {retraining ? (
              <div className="animate-spin" style={{ width: 14, height: 14, border: '2px solid #fff', borderTopColor: 'transparent', borderRadius: '50%' }} />
            ) : (
              <RefreshCw size={15} />
            )}
            Trigger Incremental Retraining
          </button>
        </div>

        {retrainMsg && (
          <div style={{ padding: '0.75rem', borderRadius: '6px', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', color: '#059669', fontSize: '0.85rem' }}>
            {retrainMsg}
          </div>
        )}

        {/* Feedback stats grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.85rem' }}>
          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>FEEDBACK ENTRIES</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--text-strong)' }}>
              {feedbackStats?.total || 0} Submitted
            </div>
          </div>

          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>AVERAGE USER RATING</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#b45309', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              {feedbackStats?.avg_rating || '5.0'} <Star size={16} fill="#b45309" />
            </div>
          </div>

          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>SYNAPT FORWARDED</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#0e7490' }}>
              {feedbackStats?.sent_to_synapt || 0} trident_feedback
            </div>
          </div>

          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>STRATEGY BOOSTS</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#059669' }}>
              {feedbackStats?.boosts?.length || 0} Multipliers
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

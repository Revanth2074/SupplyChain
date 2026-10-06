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
  triggerRetrain
} from '../api';

export default function TabEval() {
  const [evalStatus, setEvalStatus] = useState(null);
  const [evalResults, setEvalResults] = useState(null);
  const [feedbackStats, setFeedbackStats] = useState(null);
  const [running, setRunning] = useState(false);
  const [retraining, setRetraining] = useState(false);
  const [retrainMsg, setRetrainMsg] = useState(null);

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
      await runEvaluation({ limit: 4, use_graph: false, include_feedback: true });
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
    <div style={{ maxWidth: '1440px', margin: '0 auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
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

          <div style={{ display: 'flex', gap: '0.75rem' }}>
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

      {/* DeepEval Summary Scores */}
      {evalResults?.summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
          {/* Classification Accuracy */}
          <div className="glass-card" style={{ borderLeft: '4px solid #6366f1' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>CLASSIFICATION ACCURACY</span>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#fff', marginTop: '0.2rem' }}>
              {evalResults.summary.classification_accuracy ? `${(evalResults.summary.classification_accuracy * 100).toFixed(1)}%` : 'N/A'}
            </div>
            <span style={{ fontSize: '0.72rem', color: '#a5b4fc' }}>Golden Disruption Cases</span>
          </div>

          {/* Retrieval Precision */}
          <div className="glass-card" style={{ borderLeft: '4px solid #06b6d4' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>RETRIEVAL TYPE PRECISION</span>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#67e8f9', marginTop: '0.2rem' }}>
              {evalResults.summary.retrieval_type_precision ? `${(evalResults.summary.retrieval_type_precision * 100).toFixed(1)}%` : 'N/A'}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Synapt + BM25 Precision</span>
          </div>

          {/* LLM Judge Score */}
          <div className="glass-card" style={{ borderLeft: '4px solid #10b981' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>LLM-AS-JUDGE OVERALL</span>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#6ee7b7', marginTop: '0.2rem' }}>
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
              <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#c4b5fd', marginTop: '0.2rem' }}>
                {score !== null ? `${(score * 100).toFixed(0)}%` : 'Pending'}
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>DeepEval 4.x Evaluator</span>
            </div>
          ))}
        </div>
      )}

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
                    <strong style={{ fontSize: '0.9rem', color: '#fff' }}>
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

                {/* DeepEval metric chips */}
                {row.metrics && Object.keys(row.metrics).length > 0 && (
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
              <RotateCcw size={18} color="#6366f1" />
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
          <div style={{ padding: '0.75rem', borderRadius: '6px', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', color: '#6ee7b7', fontSize: '0.85rem' }}>
            {retrainMsg}
          </div>
        )}

        {/* Feedback stats grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.85rem' }}>
          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>FEEDBACK ENTRIES</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#fff' }}>
              {feedbackStats?.total || 0} Submitted
            </div>
          </div>

          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>AVERAGE USER RATING</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#fcd34d', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              {feedbackStats?.avg_rating || '5.0'} <Star size={16} fill="#fcd34d" />
            </div>
          </div>

          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>SYNAPT FORWARDED</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#67e8f9' }}>
              {feedbackStats?.sent_to_synapt || 0} trident_feedback
            </div>
          </div>

          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>STRATEGY BOOSTS</span>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#6ee7b7' }}>
              {feedbackStats?.boosts?.length || 0} Multipliers
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { Sliders, Activity, BarChart2 } from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { predictIncident, explainIncident } from '../api';
import WhatIfPanel from './WhatIfPanel';
import { Callout, Kpi, PageHeader } from './ui';
import { fmtUsd, fmtUsdShort } from '../format';

export default function TabPredict({ options }) {
  const [params, setParams] = useState({
    disruption_type: 'Cyber Attack',
    industry: 'Aerospace',
    supplier_tier: 2,
    supplier_region: 'Asia-Pacific',
    supplier_size: 'Medium',
    has_backup_supplier: false,
    disruption_severity: 4,
    response_type: 'Alternative Supplier',
    response_time_days: 3,
  });

  const [prediction, setPrediction] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTarget, setActiveTarget] = useState('production_impact_pct');

  const runSimulation = async () => {
    setLoading(true);
    try {
      const [predResp, explResp] = await Promise.all([
        predictIncident(params),
        explainIncident(params),
      ]);
      setPrediction(predResp.prediction);
      setExplanation(explResp.explanation);
    } catch (e) {
      console.error('Simulation error:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    runSimulation();
  }, [params]);

  // Transform local explanation data for charts
  const localContribs = explanation?.[activeTarget]?.local?.map((item) => ({
    name: item.label,
    contribution: Number(item.contribution),
    value: String(item.value),
    baseline: String(item.baseline),
  })) || [];

  const globalImportance = explanation?.[activeTarget]?.global?.slice(0, 7) || [];

  return (
    <div className="page">
      <PageHeader
        icon={Sliders}
        title="ML Simulator, Prediction Ranges & XAI"
        subtitle="HistGradientBoosting models trained on 100,000 disruptions. Change the scenario to see point predictions with 80% ranges, local feature contributions, resilience and what-if counterfactuals."
      />

      <div className="grid-auto" style={{ '--min': '340px', gap: '1.5rem' }}>
        {/* Left Column: Interactive Scenario Controls */}
        <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Activity size={18} color="var(--accent-secondary)" />
            Scenario Parameters
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Disruption Type</label>
              <select
                className="select-field"
                value={params.disruption_type}
                onChange={(e) => setParams({ ...params, disruption_type: e.target.value })}
              >
                {options?.disruption_type?.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Industry</label>
              <select
                className="select-field"
                value={params.industry}
                onChange={(e) => setParams({ ...params, industry: e.target.value })}
              >
                {options?.industry?.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Supplier Tier</label>
                <select
                  className="select-field"
                  value={params.supplier_tier}
                  onChange={(e) => setParams({ ...params, supplier_tier: Number(e.target.value) })}
                >
                  <option value="1">Tier 1 (Direct)</option>
                  <option value="2">Tier 2 (Sub-tier)</option>
                  <option value="3">Tier 3 (Raw materials)</option>
                  <option value="4">Tier 4 (Upstream)</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Supplier Size</label>
                <select
                  className="select-field"
                  value={params.supplier_size}
                  onChange={(e) => setParams({ ...params, supplier_size: e.target.value })}
                >
                  <option value="Large">Large Enterprise</option>
                  <option value="Medium">Medium</option>
                  <option value="Small">Small / Boutique</option>
                </select>
              </div>
            </div>

            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Region</label>
              <select
                className="select-field"
                value={params.supplier_region}
                onChange={(e) => setParams({ ...params, supplier_region: e.target.value })}
              >
                {options?.supplier_region?.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: '0.2rem' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Disruption Severity</span>
                <strong style={{ color: '#b45309' }}>Level {params.disruption_severity} of 5</strong>
              </div>
              <input
                type="range"
                min="1"
                max="5"
                step="1"
                value={params.disruption_severity}
                onChange={(e) => setParams({ ...params, disruption_severity: Number(e.target.value) })}
                style={{ width: '100%', accentColor: '#2563eb', cursor: 'pointer' }}
              />
            </div>

            <div>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Backup Supplier Strategy</label>
              <select
                className="select-field"
                value={String(params.has_backup_supplier)}
                onChange={(e) => setParams({ ...params, has_backup_supplier: e.target.value === 'true' })}
              >
                <option value="false">No Backup (Single Source)</option>
                <option value="true">Backup Supplier Sourced (Dual Source)</option>
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '0.75rem' }}>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Response Strategy</label>
                <select
                  className="select-field"
                  value={params.response_type}
                  onChange={(e) => setParams({ ...params, response_type: e.target.value })}
                >
                  {options?.response_type?.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Response Time</label>
                <input
                  type="number"
                  min="0"
                  max="60"
                  className="input-field"
                  value={params.response_time_days}
                  onChange={(e) => setParams({ ...params, response_time_days: Number(e.target.value) })}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Model Predictions & Resilience Score */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Output Metric Cards with 80% prediction intervals */}
          {prediction?.support?.warning && <Callout tone="warning">{prediction.support.warning}</Callout>}
          {prediction?.support && !prediction.support.warning && (
            <Callout tone="info">
              {prediction.support.matching_cases.toLocaleString()} historical cases match this exact profile ({prediction.support.level} support). Bars show the 80% range (P10–P90).
            </Callout>
          )}
          <div className="grid-auto" style={{ '--min': '220px' }}>
            <Kpi label="Production impact" tone="#f59e0b" value={`${prediction?.production_impact_pct ?? '—'}%`}
              range={prediction?.ranges && { ...prediction.ranges.production_impact_pct, value: prediction.production_impact_pct }}
              format={(v) => `${Number(v).toFixed(0)}%`} />
            <Kpi label="Revenue loss" tone="#1d4ed8" value={fmtUsd(prediction?.revenue_loss_usd)}
              range={prediction?.ranges && { ...prediction.ranges.revenue_loss_usd, value: prediction.revenue_loss_usd }}
              format={fmtUsdShort} />
            <Kpi label="Full recovery" tone="#059669" value={`${prediction?.full_recovery_days ?? '—'} days`}
              range={prediction?.ranges && { ...prediction.ranges.full_recovery_days, value: prediction.full_recovery_days }}
              format={(v) => `${Math.round(v)}d`}
              sub={prediction && `Partial ≈ ${prediction.partial_recovery_days}d (P10–P90 ${prediction.ranges?.partial_recovery_days?.p10}–${prediction.ranges?.partial_recovery_days?.p90}d)`} />
            <Kpi label="High-impact risk" tone="#dc2626" value={`${((prediction?.risk_probability || 0) * 100).toFixed(1)}%`}
              sub={<span className="badge badge-danger">Risk band: {prediction?.risk_level}</span>} />
          </div>

          {/* Resilience Score Breakdown */}
          {prediction?.resilience_score && (
            <div className="glass-panel" style={{ padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                <div>
                  <h4 style={{ fontSize: '1rem', fontWeight: 600 }}>Supply Chain Resilience Score</h4>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Structural readiness & impact absorption index (0-100)
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.4rem' }}>
                  <span style={{ fontSize: '1.6rem', fontWeight: 800, color: prediction.resilience_score.score >= 60 ? '#059669' : '#b45309' }}>
                    {prediction.resilience_score.score}
                  </span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>/ 100</span>
                  <span className={`badge ${prediction.resilience_score.score >= 60 ? 'badge-success' : 'badge-warning'}`}>
                    {prediction.resilience_score.band}
                  </span>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.6rem', marginTop: '0.5rem' }}>
                {Object.entries(prediction.resilience_score.components || {}).map(([comp, val]) => (
                  <div key={comp} className="glass-card" style={{ padding: '0.5rem', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'capitalize' }}>
                      {comp.replace('_', ' ')}
                    </div>
                    <strong style={{ fontSize: '0.95rem', color: 'var(--text-strong)' }}>+{val} pts</strong>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Explainable AI (XAI) Section */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <BarChart2 size={20} color="#2563eb" />
              Explainable AI: Feature Contributions & Global Permutation Importance
            </h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Inspect how individual attributes push predictions relative to dataset baseline median values.
            </p>
          </div>

          {/* Target selector pills */}
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            {[
              { id: 'production_impact_pct', label: 'Impact %' },
              { id: 'revenue_loss_usd', label: 'Revenue Loss $' },
              { id: 'full_recovery_days', label: 'Recovery Days' },
              { id: 'risk', label: 'Disruption Risk' },
            ].map((tgt) => (
              <button
                key={tgt.id}
                onClick={() => setActiveTarget(tgt.id)}
                className={`btn ${activeTarget === tgt.id ? 'btn-primary' : 'btn-secondary'}`}
                style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
              >
                {tgt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Feature Attribution Chart */}
        <div className="grid-auto" style={{ '--min': '420px', gap: '1.5rem' }}>
          {/* Local Waterfall / Bar */}
          <div className="glass-card" style={{ padding: '1rem', minHeight: '320px' }}>
            <h4 style={{ fontSize: '0.9rem', marginBottom: '0.75rem', color: 'var(--text-strong)' }}>
              Local Feature Contribution vs Baseline (Delta)
            </h4>
            <div style={{ height: '260px' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={localContribs} layout="vertical" margin={{ top: 5, right: 30, left: 70, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(15, 23, 42, 0.072)" />
                  <XAxis type="number" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="name" type="category" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: '#ffffff', border: '1px solid rgba(15, 23, 42, 0.12)', borderRadius: '8px' }}
                    formatter={(val, name, props) => [
                      `${val > 0 ? '+' : ''}${val} (Input: ${props.payload.value}, Baseline: ${props.payload.baseline})`,
                      'Contribution'
                    ]}
                  />
                  <Bar dataKey="contribution">
                    {localContribs.map((entry, idx) => (
                      <Cell key={idx} fill={entry.contribution >= 0 ? '#ef4444' : '#10b981'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Global Permutation Importance */}
          <div className="glass-card" style={{ padding: '1rem', minHeight: '320px' }}>
            <h4 style={{ fontSize: '0.9rem', marginBottom: '0.75rem', color: 'var(--text-strong)' }}>
              Global Permutation Feature Importance (100k Dataset)
            </h4>
            <div style={{ height: '260px' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={globalImportance} layout="vertical" margin={{ top: 5, right: 30, left: 70, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(15, 23, 42, 0.072)" />
                  <XAxis type="number" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="label" type="category" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: '#ffffff', border: '1px solid rgba(15, 23, 42, 0.12)', borderRadius: '8px' }}
                    formatter={(val) => [val, 'Importance Score']}
                  />
                  <Bar dataKey="importance" fill="#2563eb" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
      <WhatIfPanel incident={params} />
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  Clock,
  Shield,
  Plus,
  RefreshCw,
  TrendingUp,
  Layers,
  ArrowUpDown,
  CheckCircle
} from 'lucide-react';
import { prioritizeIncidents } from '../api';

const DEFAULT_INCIDENTS = [
  {
    label: 'Incident #1: Ransomware on Tier 2 Avionics Supplier',
    disruption_type: 'Cyber Attack',
    industry: 'Aerospace',
    supplier_tier: 2,
    supplier_region: 'Asia-Pacific',
    has_backup_supplier: false,
    disruption_severity: 5,
    production_impact_pct: 68.0,
    revenue_loss_usd: 12500000,
  },
  {
    label: 'Incident #2: Shanghai Port Terminal Congestion',
    disruption_type: 'Port Congestion',
    industry: 'Electronics',
    supplier_tier: 1,
    supplier_region: 'Asia-Pacific',
    has_backup_supplier: true,
    disruption_severity: 3,
    production_impact_pct: 22.0,
    revenue_loss_usd: 1800000,
  },
  {
    label: 'Incident #3: Chemical Solvent Contamination Plant Shutdown',
    disruption_type: 'Factory Incident',
    industry: 'Pharmaceuticals',
    supplier_tier: 1,
    supplier_region: 'North America',
    has_backup_supplier: false,
    disruption_severity: 4,
    production_impact_pct: 45.0,
    revenue_loss_usd: 8200000,
  },
  {
    label: 'Incident #4: Regional Rail Logistics Strike',
    disruption_type: 'Labor Strike',
    industry: 'Automotive',
    supplier_tier: 3,
    supplier_region: 'Europe',
    has_backup_supplier: true,
    disruption_severity: 2,
    production_impact_pct: 12.0,
    revenue_loss_usd: 450000,
  },
  {
    label: 'Incident #5: Export Sanction on Rare Earth Sub-Supplier',
    disruption_type: 'Geopolitical',
    industry: 'Electronics',
    supplier_tier: 2,
    supplier_region: 'Asia-Pacific',
    has_backup_supplier: false,
    disruption_severity: 4,
    production_impact_pct: 35.0,
    revenue_loss_usd: 5400000,
  }
];

export default function TabPrioritize({ options }) {
  const [incidents, setIncidents] = useState(DEFAULT_INCIDENTS);
  const [rankedList, setRankedList] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // New incident modal/form
  const [newInc, setNewInc] = useState({
    label: 'New Urgent Incident',
    disruption_type: 'Natural Disaster',
    industry: 'Electronics',
    supplier_tier: 1,
    supplier_region: 'Asia-Pacific',
    has_backup_supplier: false,
    disruption_severity: 4,
    production_impact_pct: 50,
    revenue_loss_usd: 6000000,
  });

  const runPrioritization = async (listToRun) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await prioritizeIncidents(listToRun || incidents);
      setRankedList(resp.ranked);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    runPrioritization(DEFAULT_INCIDENTS);
  }, []);

  const handleAddIncident = (e) => {
    e.preventDefault();
    const updated = [...incidents, { ...newInc, label: `${newInc.label} (#${incidents.length + 1})` }];
    setIncidents(updated);
    runPrioritization(updated);
  };

  const handleReset = () => {
    setIncidents(DEFAULT_INCIDENTS);
    runPrioritization(DEFAULT_INCIDENTS);
  };

  const getPrioBadge = (level) => {
    if (level?.includes('P1')) return 'badge-danger';
    if (level?.includes('P2')) return 'badge-warning';
    if (level?.includes('P3')) return 'badge-cyan';
    return 'badge-primary';
  };

  return (
    <div style={{ maxWidth: '1440px', margin: '0 auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h2 style={{ fontSize: '1.3rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <AlertTriangle size={22} color="#f59e0b" />
              Dynamic Disruption Prioritization Matrix
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Multi-criteria incident triage scoring severity (35%), production loss % (30%), financial impact (25%), and high-impact risk probability (10%).
            </p>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button onClick={() => runPrioritization()} disabled={loading} className="btn btn-secondary">
              <RefreshCw size={15} />
              Re-Calculate Priority
            </button>
            <button onClick={handleReset} className="btn btn-ghost">
              Reset Queue
            </button>
          </div>
        </div>
      </div>

      {/* Ranked Queue Table & Cards */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <ArrowUpDown size={18} color="#2563eb" />
          Active Incident Priority Queue ({rankedList?.length || 0} Incidents Evaluated)
        </h3>

        {error && <div style={{ color: '#dc2626', marginBottom: '1rem' }}>Error: {error}</div>}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
          {rankedList?.map((item) => {
            const inc = item.incident;
            const p = item.priority;
            const pred = item.prediction;

            return (
              <div
                key={item.index}
                className="glass-card"
                style={{
                  padding: '1.15rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.75rem',
                  borderLeft: `4px solid ${
                    p.level?.includes('P1') ? '#ef4444' : p.level?.includes('P2') ? '#f59e0b' : p.level?.includes('P3') ? '#06b6d4' : '#2563eb'
                  }`
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <span style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '50%',
                      background: 'rgba(15, 23, 42, 0.096)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontWeight: 700,
                      fontSize: '0.85rem'
                    }}>
                      #{item.rank}
                    </span>
                    <strong style={{ fontSize: '1rem', color: 'var(--text-strong)' }}>{item.label}</strong>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span className={`badge ${getPrioBadge(p.level)}`} style={{ fontSize: '0.85rem', padding: '0.25rem 0.65rem' }}>
                      {p.level} (Score: {p.score})
                    </span>
                    <span className="badge badge-purple" style={{ fontSize: '0.8rem' }}>
                      <Clock size={13} />
                      {p.action_sla}
                    </span>
                  </div>
                </div>

                {/* Sub-metrics grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', background: 'rgba(0,0,0,0.25)', padding: '0.75rem', borderRadius: '8px', fontSize: '0.8rem' }}>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Disruption Type:</span>
                    <strong style={{ display: 'block', color: 'var(--text-strong)' }}>{inc.disruption_type}</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Severity:</span>
                    <strong style={{ display: 'block', color: '#b45309' }}>Level {inc.disruption_severity} / 5</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Est. Production Impact:</span>
                    <strong style={{ display: 'block', color: '#dc2626' }}>
                      {pred.production_impact_pct}%
                    </strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Est. Revenue Loss:</span>
                    <strong style={{ display: 'block', color: 'var(--text-strong)' }}>
                      ${Number(pred.revenue_loss_usd).toLocaleString()}
                    </strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Est. Full Recovery:</span>
                    <strong style={{ display: 'block', color: '#059669' }}>
                      {pred.full_recovery_days} days
                    </strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Backup Supplier:</span>
                    <strong style={{ display: 'block', color: inc.has_backup_supplier ? '#059669' : '#dc2626' }}>
                      {inc.has_backup_supplier ? 'Yes (Dual Sourced)' : 'No (Single Sourced)'}
                    </strong>
                  </div>
                </div>

                {/* Weighted Score Breakdown */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '0.72rem', color: 'var(--text-muted)', flexWrap: 'wrap' }}>
                  <span>Formula Contribution:</span>
                  <span>Severity: <strong style={{ color: 'var(--text-strong)' }}>{p.components.severity}%</strong></span>
                  <span>Impact: <strong style={{ color: 'var(--text-strong)' }}>{p.components.production_impact}%</strong></span>
                  <span>Financial Loss: <strong style={{ color: 'var(--text-strong)' }}>{p.components.financial_loss}%</strong></span>
                  <span>Risk Prob: <strong style={{ color: 'var(--text-strong)' }}>{p.components.risk}%</strong></span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Add New Incident Form */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <h3 style={{ fontSize: '1.1rem', marginBottom: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Plus size={18} color="#10b981" />
          Add Disruption to Prioritization Queue
        </h3>

        <form onSubmit={handleAddIncident} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.85rem', alignItems: 'flex-end' }}>
          <div style={{ gridColumn: 'span 2' }}>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Incident Label</label>
            <input
              className="input-field"
              type="text"
              value={newInc.label}
              onChange={(e) => setNewInc({ ...newInc, label: e.target.value })}
            />
          </div>

          <div>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Disruption Type</label>
            <select
              className="select-field"
              value={newInc.disruption_type}
              onChange={(e) => setNewInc({ ...newInc, disruption_type: e.target.value })}
            >
              {options?.disruption_type?.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Severity (1-5)</label>
            <select
              className="select-field"
              value={newInc.disruption_severity}
              onChange={(e) => setNewInc({ ...newInc, disruption_severity: Number(e.target.value) })}
            >
              {[1, 2, 3, 4, 5].map((s) => <option key={s} value={s}>Severity {s}</option>)}
            </select>
          </div>

          <div>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Backup Supplier</label>
            <select
              className="select-field"
              value={String(newInc.has_backup_supplier)}
              onChange={(e) => setNewInc({ ...newInc, has_backup_supplier: e.target.value === 'true' })}
            >
              <option value="false">No Backup</option>
              <option value="true">Has Backup</option>
            </select>
          </div>

          <div>
            <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
              <Plus size={16} />
              Enqueue & Rank
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

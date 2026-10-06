import React, { useState, useEffect } from 'react';
import {
  BarChart3,
  TrendingUp,
  DollarSign,
  Clock,
  ShieldCheck,
  RefreshCw,
  PieChart as PieIcon,
  Layers
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Cell,
  LineChart,
  Line
} from 'recharts';
import { fetchInsights } from '../api';

export default function TabAnalytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchInsights()
      .then((res) => setData(res))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  if (loading || !data) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
        <div className="animate-spin" style={{ width: 28, height: 28, border: '3px solid #6366f1', borderTopColor: 'transparent', borderRadius: '50%', margin: '0 auto 1rem' }} />
        Aggregating macro intelligence over 100,000 disruption records...
      </div>
    );
  }

  const totals = data.totals;

  // Format type data
  const typeChart = data.by_type?.map((t) => ({
    name: t.key,
    lossM: Number((t.avg_loss / 1e6).toFixed(2)),
    recoveryDays: Math.round(t.avg_recovery),
    impactPct: Number(t.avg_impact.toFixed(1)),
    cases: t.cases,
  })) || [];

  // Format backup impact data
  const backupComparison = [
    { type: 'Cyber Attack', withBackup: 84.3, withoutBackup: 118.7 },
    { type: 'Natural Disaster', withBackup: 77.3, withoutBackup: 107.2 },
    { type: 'Geopolitical', withBackup: 68.8, withoutBackup: 96.7 },
    { type: 'Factory Incident', withBackup: 60.4, withoutBackup: 85.0 },
    { type: 'Labor Strike', withBackup: 53.0, withoutBackup: 74.7 },
    { type: 'Port Congestion', withBackup: 50.1, withoutBackup: 70.4 },
  ];

  // Strategy response data
  const strategyData = data.by_response?.map((s) => ({
    strategy: s.key,
    avgRecovery: Math.round(s.avg_recovery),
    avgLossM: Number((s.avg_loss / 1e6).toFixed(2)),
    cases: s.cases,
    changeRate: (s.change_rate * 100).toFixed(1),
  })) || [];

  return (
    <div style={{ maxWidth: '1440px', margin: '0 auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Top Banner with 100k Totals */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <h2 style={{ fontSize: '1.3rem', fontWeight: 700, marginBottom: '0.4rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <BarChart3 size={22} color="#6366f1" />
          Global Macro Intelligence (100,000 Historical Cases)
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
          Comprehensive statistical benchmark across industries, supplier tiers, regions, and strategy recovery curves.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>TOTAL CASES</span>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#fff', marginTop: '0.2rem' }}>
              {totals.cases.toLocaleString()}
            </div>
            <span style={{ fontSize: '0.75rem', color: '#a5b4fc' }}>Full Disruption Dataset</span>
          </div>

          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>TOTAL REVENUE IMPACT</span>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#fff', marginTop: '0.2rem' }}>
              ${(totals.total_loss / 1e9).toFixed(1)} Billion
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Avg ${(totals.avg_loss / 1e6).toFixed(2)}M / incident</span>
          </div>

          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>AVG FULL RECOVERY</span>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#6ee7b7', marginTop: '0.2rem' }}>
              {totals.avg_recovery} Days
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Across all response types</span>
          </div>

          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>BACKUP SUPPLIER ADOPTION</span>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#67e8f9', marginTop: '0.2rem' }}>
              {(totals.backup_rate * 100).toFixed(1)}%
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Dual-sourced suppliers</span>
          </div>

          <div className="glass-card">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>PERMANENT SUPPLIER CHANGE</span>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#fca5a5', marginTop: '0.2rem' }}>
              {(totals.change_rate * 100).toFixed(1)}%
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Post-disruption churn</span>
          </div>
        </div>
      </div>

      {/* Chart Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(460px, 1fr))', gap: '1.5rem' }}>
        {/* Chart 1: Average Financial Loss and Recovery Days by Disruption Type */}
        <div className="glass-panel" style={{ padding: '1.5rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.3rem' }}>
            Impact & Recovery by Disruption Type
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
            Average Revenue Loss ($M) and Average Full Recovery Days
          </p>
          <div style={{ height: '300px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={typeChart} margin={{ top: 10, right: 30, left: 10, bottom: 25 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="name" stroke="#94a3b8" tick={{ fontSize: 11 }} angle={-15} textAnchor="end" />
                <YAxis yAxisId="left" stroke="#6366f1" tick={{ fontSize: 11 }} label={{ value: 'Loss ($M)', angle: -90, position: 'insideLeft', fill: '#6366f1', fontSize: 11 }} />
                <YAxis yAxisId="right" orientation="right" stroke="#10b981" tick={{ fontSize: 11 }} label={{ value: 'Days', angle: 90, position: 'insideRight', fill: '#10b981', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#0f1422', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar yAxisId="left" dataKey="lossM" name="Avg Loss ($M)" fill="#6366f1" radius={[4, 4, 0, 0]} />
                <Bar yAxisId="right" dataKey="recoveryDays" name="Avg Recovery (Days)" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 2: Power of Backup Suppliers (Recovery Acceleration) */}
        <div className="glass-panel" style={{ padding: '1.5rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.3rem' }}>
            The Mitigation Power of Backup Suppliers
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
            Full recovery days: With Backup Supplier vs Single Sourced (No Backup)
          </p>
          <div style={{ height: '300px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={backupComparison} margin={{ top: 10, right: 30, left: 10, bottom: 25 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="type" stroke="#94a3b8" tick={{ fontSize: 11 }} angle={-15} textAnchor="end" />
                <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} label={{ value: 'Days to Full Recovery', angle: -90, position: 'insideLeft', fill: '#94a3b8', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#0f1422', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="withBackup" name="With Backup Supplier (Fast)" fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar dataKey="withoutBackup" name="Without Backup (Slow)" fill="#ef4444" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Strategy Performance Table */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>
          Response Strategy Effectiveness Benchmark
        </h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-muted)' }}>
                <th style={{ padding: '0.75rem 0.5rem' }}>Response Strategy</th>
                <th style={{ padding: '0.75rem 0.5rem' }}>Cases Adopted</th>
                <th style={{ padding: '0.75rem 0.5rem' }}>Avg Recovery (Days)</th>
                <th style={{ padding: '0.75rem 0.5rem' }}>Avg Revenue Loss</th>
                <th style={{ padding: '0.75rem 0.5rem' }}>Supplier Churn %</th>
              </tr>
            </thead>
            <tbody>
              {strategyData.map((s) => (
                <tr key={s.strategy} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '0.75rem 0.5rem', fontWeight: 600, color: '#fff' }}>{s.strategy}</td>
                  <td style={{ padding: '0.75rem 0.5rem', color: 'var(--text-secondary)' }}>{s.cases.toLocaleString()}</td>
                  <td style={{ padding: '0.75rem 0.5rem', color: '#6ee7b7', fontWeight: 600 }}>{s.avgRecovery} days</td>
                  <td style={{ padding: '0.75rem 0.5rem', color: '#fff' }}>${s.avgLossM}M</td>
                  <td style={{ padding: '0.75rem 0.5rem', color: Number(s.changeRate) > 25 ? '#fca5a5' : '#6ee7b7' }}>{s.changeRate}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

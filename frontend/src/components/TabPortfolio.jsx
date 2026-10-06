import React, { useEffect, useRef, useState } from 'react';
import { Briefcase, ChevronDown, ChevronRight, Grid3x3, ListOrdered, Upload } from 'lucide-react';
import { fetchPortfolioSample, scorePortfolio } from '../api';
import { Callout, Kpi, PageHeader, Section, Segmented, Spinner } from './ui';
import { fmtUsdShort } from '../format';

const BAND = { Critical: 'badge-danger', High: 'badge-warning', Medium: 'badge-primary', Low: 'badge-success' };

// sequential red ramp for risk index (40 -> 80)
const heatColor = (v) => {
  if (v == null) return 'rgba(15, 23, 42, 0.024)';
  const t = Math.max(0, Math.min(1, (v - 40) / 40));
  return `rgba(239, 68, 68, ${0.08 + t * 0.62})`;
};

function Heatmap({ heat }) {
  const cell = (r, t) => heat.cells.find((c) => c.region === r && c.tier === t);
  return (
    <div className="heat" style={{ gridTemplateColumns: `minmax(120px, 1.3fr) repeat(${heat.tiers.length}, 1fr)` }}>
      <div />
      {heat.tiers.map((t) => <div key={t} className="heat-head">Tier {t}</div>)}
      {heat.regions.map((r) => (
        <React.Fragment key={r}>
          <div className="heat-head" style={{ justifyContent: 'flex-start' }}>{r}</div>
          {heat.tiers.map((t) => {
            const c = cell(r, t);
            return (
              <div key={t} className="heat-cell" style={{ background: heatColor(c?.avg_risk_index) }} title={c?.names?.join(', ')}>
                {c?.suppliers ? (
                  <>
                    <strong style={{ color: 'var(--text-strong)', fontSize: '0.95rem' }}>{c.avg_risk_index}</strong>
                    <span style={{ color: 'rgba(15, 23, 42, 0.12)', fontSize: '0.68rem' }}>{c.suppliers} supplier{c.suppliers > 1 ? 's' : ''}</span>
                  </>
                ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
              </div>
            );
          })}
        </React.Fragment>
      ))}
    </div>
  );
}

function SupplierRow({ s }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr onClick={() => setOpen(!open)} style={{ cursor: 'pointer' }}>
        <td className="num">{open ? <ChevronDown size={13} /> : <ChevronRight size={13} />} {s.rank}</td>
        <td style={{ color: 'var(--text-strong)', fontWeight: 500 }}>{s.supplier_name}</td>
        <td>{s.industry}</td>
        <td>{s.supplier_region}</td>
        <td className="num">T{s.supplier_tier}</td>
        <td>{s.has_backup_supplier ? 'Yes' : <span className="pos">No</span>}</td>
        <td><span className={`badge ${BAND[s.band]}`}>{s.risk_index} · {s.band}</span></td>
        <td className="num">{(s.expected_risk_probability * 100).toFixed(0)}%</td>
        <td className="num">{fmtUsdShort(s.expected_revenue_loss_usd)}</td>
        <td className="num">{s.expected_full_recovery_days.toFixed(0)}d</td>
        <td className="num">{s.resilience.score}</td>
        <td style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>{s.drivers.join(' · ') || '—'}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={12} style={{ background: 'rgba(15, 23, 42, 0.024)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.4rem' }}>
              Worst case: <strong style={{ color: '#dc2626' }}>{s.worst_case.disruption_type}</strong> ({fmtUsdShort(s.worst_case.revenue_loss_usd)}, {s.worst_case.full_recovery_days} days to recover). Weight = how often that disruption type hits {s.supplier_region} suppliers.
            </div>
            <div className="grid-auto" style={{ '--min': '150px', gap: '0.4rem' }}>
              {s.by_type.map((t) => (
                <div key={t.disruption_type} className="glass-card" style={{ padding: '0.45rem 0.6rem' }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-body)', fontWeight: 600 }}>{t.disruption_type}</div>
                  <div className="num" style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                    risk {(t.risk_probability * 100).toFixed(0)}% · {fmtUsdShort(t.revenue_loss_usd)} · {t.full_recovery_days}d · w {(t.weight * 100).toFixed(0)}%
                  </div>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function TabPortfolio({ onScored }) {
  const [csv, setCsv] = useState('');
  const [severity, setSeverity] = useState(3);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const fileRef = useRef(null);
  const sample = useRef(null); // the tower scores the sample itself; only share user portfolios

  const run = async (text = csv, sev = severity) => {
    if (!text.trim()) return;
    setBusy(true); setError(null);
    try {
      const r = await scorePortfolio(text, sev);
      setRes(r);
      if (!sample.current || text !== sample.current) onScored?.(r);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  useEffect(() => {
    fetchPortfolioSample().then((t) => { sample.current = t; setCsv(t); run(t, 3); }).catch((e) => setError(e.message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    f.text().then((t) => { setCsv(t); run(t); });
    e.target.value = '';
  };

  return (
    <div className="page">
      <PageHeader
        icon={Briefcase}
        title="Supplier Portfolio Risk"
        subtitle="Upload your supplier list and every supplier is scored against all six disruption types (weighted by how often each type hits its region), giving a resilience heatmap and a ranked list of the riskiest suppliers."
      />
      <Section
        icon={Upload}
        title="Supplier list"
        subtitle="CSV columns: supplier_name, industry, supplier_region, supplier_tier, supplier_size, has_backup_supplier. A sample portfolio is loaded."
        right={(
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <span className="eyebrow">Assumed severity</span>
            <Segmented value={severity} onChange={(v) => { setSeverity(v); run(csv, v); }} options={[1, 2, 3, 4, 5].map((s) => ({ value: s, label: String(s) }))} />
          </div>
        )}
      >
        <textarea className="textarea-field" rows={5} value={csv} onChange={(e) => setCsv(e.target.value)} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }} spellCheck={false} />
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.7rem', flexWrap: 'wrap' }}>
          <button className="btn btn-primary" onClick={() => run()} disabled={busy || !csv.trim()}>{busy ? <Spinner /> : <Grid3x3 size={16} />} Score portfolio</button>
          <button className="btn btn-secondary" onClick={() => fileRef.current?.click()}><Upload size={15} /> Upload CSV</button>
          <button className="btn btn-ghost" onClick={() => fetchPortfolioSample().then((t) => { setCsv(t); run(t); })}>Reset to sample</button>
          <input ref={fileRef} type="file" accept=".csv,text/csv" onChange={onFile} hidden />
        </div>
        {error && <Callout tone="danger" style={{ marginTop: '0.8rem' }}>{error}</Callout>}
      </Section>

      {res && (
        <>
          <div className="grid-auto" style={{ '--min': '200px' }}>
            <Kpi label="Suppliers scored" value={res.count} sub={`against ${res.disruption_types.length} disruption types at severity ${res.severity_assumed}`} tone="#1d4ed8" />
            <Kpi label="Average risk index" value={res.summary.avg_risk_index} sub="0–100, higher is riskier" tone="#f59e0b" />
            <Kpi label="Critical or high" value={res.summary.critical_or_high} sub={`${res.summary.without_backup} suppliers have no backup`} tone="#ef4444" />
            <Kpi label="Expected loss if each is disrupted" value={fmtUsdShort(res.summary.expected_loss_total)} sub="sum of exposure-weighted predictions" tone="#059669" />
          </div>
          <div className="grid-auto" style={{ '--min': '420px', gap: '1.5rem', alignItems: 'start' }}>
            <Section icon={Grid3x3} iconColor="#dc2626" title="Risk heatmap" subtitle="Average risk index by supplier region and tier. Hover a cell to see the suppliers.">
              <Heatmap heat={res.heatmap} />
            </Section>
            <Section icon={ListOrdered} iconColor="#d97706" title="Where to act first" subtitle="The five riskiest suppliers and the cheapest fix.">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {res.suppliers.slice(0, 5).map((s) => (
                  <div key={s.supplier_name} className="glass-card" style={{ padding: '0.65rem 0.8rem', display: 'flex', justifyContent: 'space-between', gap: '0.6rem', alignItems: 'center' }}>
                    <div>
                      <div style={{ color: 'var(--text-strong)', fontWeight: 600, fontSize: '0.86rem' }}>{s.rank}. {s.supplier_name}</div>
                      <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                        {!s.has_backup_supplier ? 'Qualify a backup supplier' : s.supplier_tier > 1 ? 'Map sub-tier suppliers for early warning' : 'Hold buffer stock for the worst-case type'}
                        {' · '}worst case {s.worst_case.disruption_type}
                      </div>
                    </div>
                    <span className={`badge ${BAND[s.band]}`}>{s.risk_index}</span>
                  </div>
                ))}
              </div>
            </Section>
          </div>
          <Section icon={ListOrdered} title="Ranked suppliers" subtitle="Click a row for the per-disruption-type breakdown.">
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th>#</th><th>Supplier</th><th>Industry</th><th>Region</th><th>Tier</th><th>Backup</th><th>Risk index</th><th>High-impact risk</th><th>Exp. loss</th><th>Exp. recovery</th><th>Resilience</th><th>Drivers</th></tr>
                </thead>
                <tbody>{res.suppliers.map((s) => <SupplierRow key={s.supplier_name + s.rank} s={s} />)}</tbody>
              </table>
            </div>
          </Section>
        </>
      )}
    </div>
  );
}

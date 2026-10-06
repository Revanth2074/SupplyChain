import React, { useEffect, useState } from 'react';
import { GitCompare } from 'lucide-react';
import { fetchWhatIf } from '../api';
import { Callout, Section, Skeleton } from './ui';
import { fmtUsdShort } from '../format';

const delta = (v, unit, digits = 0, invert = false) => {
  if (v == null) return '—';
  const n = Number(v);
  if (Math.abs(n) < 10 ** -(digits + 1)) return <span style={{ color: 'var(--text-muted)' }}>no change</span>;
  const good = invert ? n > 0 : n < 0;
  const txt = unit === '$' ? `${n > 0 ? '+' : '−'}${fmtUsdShort(Math.abs(n))}`
    : `${n > 0 ? '+' : '−'}${Math.abs(n).toFixed(digits)}${unit}`;
  return <span className={good ? 'neg' : 'pos'}>{txt}</span>;
};

function Row({ s, strong }) {
  const d = s.delta;
  return (
    <tr style={strong ? { background: 'rgba(16,185,129,0.06)' } : undefined}>
      <td style={{ color: strong ? '#047857' : '#e2e8f0', fontWeight: strong ? 600 : 400 }}>{s.label}</td>
      <td className="num">{delta(d.full_recovery_days, 'd')}</td>
      <td className="num">{delta(d.partial_recovery_days, 'd')}</td>
      <td className="num">{delta(d.revenue_loss_usd, '$')}</td>
      <td className="num">{delta(d.production_impact_pct, ' pts', 1)}</td>
      <td className="num">{delta(d.risk_probability * 100, ' pts', 1)}</td>
      <td className="num">{delta(d.resilience, '', 1, true)}</td>
    </tr>
  );
}

/** Counterfactual "what if we had…" analysis for one incident. */
export default function WhatIfPanel({ incident, title = 'What-if: counterfactual recovery analysis' }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const key = JSON.stringify(incident || {});

  useEffect(() => {
    if (!incident?.disruption_type) return undefined;
    let live = true;
    setError(null);
    const t = setTimeout(() => {
      fetchWhatIf(incident).then((d) => live && setData(d)).catch((e) => live && setError(e.message));
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const best = data?.scenarios?.[0];
  const base = data?.base?.prediction;
  return (
    <Section
      icon={GitCompare}
      iconColor="#059669"
      title={title}
      subtitle="Each row re-runs the ML models with one lever changed and shows the difference from the current scenario. Green = better."
    >
      {error && <Callout tone="danger">{error}</Callout>}
      {!data && !error && <Skeleton height={180} />}
      {data && (
        <>
          {best && best.delta.full_recovery_days < 0 && (
            <Callout tone="success" style={{ marginBottom: '0.9rem' }}>
              <strong>{best.label}</strong> would have recovered about{' '}
              <strong>{Math.abs(best.delta.full_recovery_days).toFixed(0)} days sooner</strong>{' '}
              ({base.full_recovery_days.toFixed(0)} → {best.prediction.full_recovery_days.toFixed(0)} days).
              {data.combined && data.combined.delta.full_recovery_days < best.delta.full_recovery_days && (
                <> Combining every helpful change saves about <strong>{Math.abs(data.combined.delta.full_recovery_days).toFixed(0)} days</strong>.</>
              )}
            </Callout>
          )}
          {best && best.delta.full_recovery_days >= 0 && (
            <Callout tone="info" style={{ marginBottom: '0.9rem' }}>
              None of the single changes shortens recovery for this profile; the current set-up is already near the best historical outcome.
            </Callout>
          )}
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>If we had…</th><th>Full recovery</th><th>Partial</th><th>Revenue loss</th>
                  <th>Impact</th><th>Risk</th><th>Resilience</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ color: 'var(--text-muted)' }}>Current scenario (baseline)</td>
                  <td className="num">{base.full_recovery_days.toFixed(0)}d</td>
                  <td className="num">{base.partial_recovery_days.toFixed(0)}d</td>
                  <td className="num">{fmtUsdShort(base.revenue_loss_usd)}</td>
                  <td className="num">{base.production_impact_pct.toFixed(1)}%</td>
                  <td className="num">{(base.risk_probability * 100).toFixed(1)}%</td>
                  <td className="num">{base.resilience}</td>
                </tr>
                {data.combined && <Row s={data.combined} strong />}
                {data.scenarios.map((s) => <Row key={s.key} s={s} />)}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Section>
  );
}

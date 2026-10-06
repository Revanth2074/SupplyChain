import React from 'react';
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react';

export function Section({ icon: Icon, iconColor = 'var(--accent-primary)', title, subtitle, right, children, style }) {
  return (
    <section className="glass-panel section" style={style}>
      {(title || right) && (
        <div className="section-head">
          <div>
            <h3 className="section-title">
              {Icon && <Icon size={19} color={iconColor} />}
              {title}
            </h3>
            {subtitle && <p className="section-sub">{subtitle}</p>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ icon: Icon, title, subtitle, right }) {
  return (
    <div className="glass-panel section" style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
      <div>
        <h2 style={{ fontSize: '1.35rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          {Icon && <Icon size={22} color="#1d4ed8" />}
          {title}
        </h2>
        {subtitle && <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '0.2rem', maxWidth: 900 }}>{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

/** P10-P90 strip with the point estimate marked. */
export function RangeBar({ p10, p90, value, format = (v) => v }) {
  if (p10 == null || p90 == null || value == null) return null;
  const lo = Math.min(p10, value);
  const hi = Math.max(p90, value);
  const pad = (hi - lo) * 0.15 || 1;
  const min = Math.max(0, lo - pad);
  const max = hi + pad;
  const pos = (v) => `${((v - min) / (max - min)) * 100}%`;
  return (
    <div className="range" title="80% prediction interval (P10 to P90)">
      <div className="range-track">
        <div className="range-band" style={{ left: pos(p10), width: `calc(${pos(p90)} - ${pos(p10)})` }} />
        <div className="range-dot" style={{ left: pos(value) }} />
      </div>
      <div className="range-labels">
        <span>P10 {format(p10)}</span>
        <span>P90 {format(p90)}</span>
      </div>
    </div>
  );
}

export function Kpi({ label, value, sub, tone = '#2563eb', range, format, children }) {
  return (
    <div className="glass-card kpi" style={{ '--kpi-tone': tone }}>
      <div className="eyebrow">{label}</div>
      <div className="kpi-value" style={{ color: tone }}>{value}</div>
      {range && <RangeBar p10={range.p10} p90={range.p90} value={range.value} format={format} />}
      {sub && <div className="kpi-sub">{sub}</div>}
      {children}
    </div>
  );
}

const CALLOUT_ICON = { warning: AlertTriangle, danger: XCircle, success: CheckCircle2, info: Info };

export function Callout({ tone = 'info', children, style }) {
  const Icon = CALLOUT_ICON[tone];
  return (
    <div className={`callout callout-${tone}`} style={style}>
      <Icon size={16} style={{ flexShrink: 0, marginTop: 2 }} />
      <div>{children}</div>
    </div>
  );
}

export function Spinner({ size = 16 }) {
  return (
    <span className="animate-spin" style={{ display: 'inline-block', width: size, height: size, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%' }} />
  );
}

export function Skeleton({ height = 120 }) {
  return <div className="skeleton" style={{ height }} />;
}

export function Segmented({ options, value, onChange }) {
  return (
    <div className="segmented" role="tablist">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} className={value === o.value ? 'active' : ''} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

const scoreTone = (v) => (v == null ? 'var(--text-muted)' : v >= 0.7 ? '#059669' : v >= 0.4 ? '#b45309' : '#dc2626');

/** Synapt's own per-answer quality signals (the inputs to its Retrieval Pass Card). */
export function SynaptPassCard({ quality, compact = false }) {
  if (!quality) return null;
  const rows = [
    ['Overall', quality.confidence],
    ['Knowledge store', quality.knowledge_confidence],
    ['Procedure store', quality.procedural_confidence],
    ['Context graph', quality.graph_confidence],
  ];
  return (
    <div>
      <div className="grid-auto" style={{ '--min': compact ? '120px' : '140px', gap: '0.6rem' }}>
        {rows.map(([k, v]) => (
          <div key={k} className="glass-card" style={{ padding: '0.6rem 0.75rem' }}>
            <div className="eyebrow">{k}</div>
            <div style={{ fontSize: '1.2rem', fontWeight: 700, color: scoreTone(v), fontFamily: 'var(--font-heading)' }}>
              {v == null ? '—' : Math.round(v * 100)}
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 500 }}> /100</span>
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.6rem', alignItems: 'center' }}>
        {quality.degraded ? (
          <span className="badge badge-warning">Trust degraded: {(quality.degraded_reasons || []).join(', ').replaceAll('_', ' ') || 'yes'}</span>
        ) : (
          <span className="badge badge-success">Trust signal OK</span>
        )}
        {(quality.stores_used || []).map((s) => <span key={s} className="badge badge-cyan">{s}</span>)}
        {Object.keys(quality.stores_skipped || {}).map((s) => (
          <span key={s} className="badge" style={{ color: 'var(--text-muted)', border: '1px dashed var(--border-subtle)' }} title={quality.stores_skipped[s]}>
            {s} skipped
          </span>
        ))}
        {quality.traversal_s != null && (
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            {quality.intent && `${quality.intent} intent · `}depth {quality.avg_traversal_depth ?? '—'} · {Number(quality.traversal_s).toFixed(1)}s
          </span>
        )}
      </div>
    </div>
  );
}

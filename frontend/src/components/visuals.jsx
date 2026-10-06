import React, { useEffect, useRef, useState } from 'react';
import { animate, motion, useInView } from 'framer-motion';
import { GLOSSARY } from '../guide';

/** Underlined term with a plain-language definition on hover/focus. */
export function Term({ k, children }) {
  const [open, setOpen] = useState(false);
  const def = GLOSSARY[k];
  if (!def) return children || k;
  return (
    <span className="term" tabIndex={0} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}>
      {children || k}
      {open && (
        <motion.span className="term-tip" role="tooltip" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}>
          <b>{k}</b>{def}
        </motion.span>
      )}
    </span>
  );
}

/** Counts up to a value when it scrolls into view. */
export function AnimatedNumber({ value, format = (v) => Math.round(v).toLocaleString(), duration = 1.1 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (!inView || value == null || Number.isNaN(Number(value))) return undefined;
    const c = animate(0, Number(value), { duration, ease: 'easeOut', onUpdate: setShown });
    return () => c.stop();
  }, [inView, value, duration]);
  return <span ref={ref}>{value == null ? '—' : format(shown)}</span>;
}

/** Semi-circular animated gauge 0-100. */
export function Gauge({ value, size = 120, label, color }) {
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  const tone = color || (v >= 70 ? '#ef4444' : v >= 55 ? '#f59e0b' : v >= 40 ? '#eab308' : '#16a34a');
  const r = size / 2 - 10;
  const len = Math.PI * r;
  return (
    <div className="gauge" style={{ width: size }}>
      <svg width={size} height={size / 2 + 12} viewBox={`0 0 ${size} ${size / 2 + 12}`}>
        <path d={`M10 ${size / 2} A ${r} ${r} 0 0 1 ${size - 10} ${size / 2}`} fill="none" stroke="#e8edf5" strokeWidth="10" strokeLinecap="round" />
        <motion.path d={`M10 ${size / 2} A ${r} ${r} 0 0 1 ${size - 10} ${size / 2}`} fill="none" stroke={tone} strokeWidth="10"
          strokeLinecap="round" strokeDasharray={len} initial={{ strokeDashoffset: len }}
          animate={{ strokeDashoffset: len * (1 - v / 100) }} transition={{ duration: 1.1, ease: 'easeOut' }} />
      </svg>
      <div className="gauge-val" style={{ color: tone }}><AnimatedNumber value={v} format={(x) => x.toFixed(0)} /></div>
      {label && <div className="gauge-label">{label}</div>}
    </div>
  );
}

/** Ring countdown (e.g. SLA time left). frac 0..1 of time remaining. */
export function Ring({ frac, size = 46, color = '#2563eb', children }) {
  const r = size / 2 - 5;
  const c = 2 * Math.PI * r;
  const f = Math.max(0, Math.min(1, frac));
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e8edf5" strokeWidth="5" />
        <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="5" strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`} strokeDasharray={c} initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - f) }} transition={{ duration: 0.9, ease: 'easeOut' }} />
      </svg>
      <div className="ring-in">{children}</div>
    </div>
  );
}

/** Fades + lifts children in, staggered by index. */
export function Reveal({ i = 0, children, className, style }) {
  return (
    <motion.div className={className} style={style} initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }} transition={{ duration: 0.4, delay: Math.min(i, 10) * 0.06 }}>
      {children}
    </motion.div>
  );
}

/** Horizontal flow of steps that light up one after another (propagation chains, pipelines). */
export function FlowChain({ steps, color = '#2563eb', vertical = false }) {
  return (
    <div className={`flow ${vertical ? 'flow-v' : ''}`}>
      {steps.map((s, i) => (
        <React.Fragment key={i}>
          <motion.div className="flow-step" style={{ '--c': s.color || color }}
            initial={{ opacity: 0, scale: 0.9 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }}
            transition={{ delay: i * 0.22, duration: 0.35 }}>
            {s.kicker && <div className="flow-kicker">{s.kicker}</div>}
            <div className="flow-title">{s.title}</div>
            {s.body && <div className="flow-body">{s.body}</div>}
            {s.metric && <div className="flow-metric">{s.metric}</div>}
          </motion.div>
          {i < steps.length - 1 && (
            <div className="flow-arrow">
              <motion.span initial={{ scaleX: 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true }}
                transition={{ delay: i * 0.22 + 0.2, duration: 0.25 }} style={{ background: s.color || color }} />
            </div>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

const PRESETS = [
  { name: 'Port congestion · Electronics · APAC', inc: { disruption_type: 'Port Congestion', industry: 'Electronics', supplier_region: 'Asia-Pacific', supplier_tier: 2, supplier_size: 'Medium', has_backup_supplier: false, disruption_severity: 4 } },
  { name: 'Cyber attack · Aerospace', inc: { disruption_type: 'Cyber Attack', industry: 'Aerospace', supplier_region: 'Asia-Pacific', supplier_tier: 2, supplier_size: 'Medium', has_backup_supplier: false, disruption_severity: 4 } },
  { name: 'Strike · Automotive · Europe', inc: { disruption_type: 'Labor Strike', industry: 'Automotive', supplier_region: 'Europe', supplier_tier: 1, supplier_size: 'Large', has_backup_supplier: true, disruption_severity: 3 } },
  { name: 'Plant fire · Pharma · N. America', inc: { disruption_type: 'Factory Incident', industry: 'Pharmaceuticals', supplier_region: 'North America', supplier_tier: 1, supplier_size: 'Small', has_backup_supplier: false, disruption_severity: 5 } },
];

/** Compact incident editor: quick presets + the fields the models use. */
export function IncidentPicker({ value, onChange, options }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  const sel = (k, label, opts) => (
    <label className="ip-field">
      <span>{label}</span>
      <select className="select-field" value={value[k] ?? ''} onChange={(e) => set(k, opts.numeric ? Number(e.target.value) : e.target.value)}>
        {opts.list.map((o) => <option key={o} value={o}>{opts.fmt ? opts.fmt(o) : o}</option>)}
      </select>
    </label>
  );
  return (
    <div className="ip">
      <div className="ip-presets">
        {PRESETS.map((p) => (
          <button key={p.name} className={`chip ${JSON.stringify(p.inc) === JSON.stringify(value) ? 'on' : ''}`} onClick={() => onChange(p.inc)}>{p.name}</button>
        ))}
      </div>
      <div className="ip-grid">
        {sel('disruption_type', 'What happened', { list: options?.disruption_type || [] })}
        {sel('industry', 'Industry', { list: options?.industry || [] })}
        {sel('supplier_region', 'Supplier region', { list: options?.supplier_region || [] })}
        {sel('supplier_tier', 'Supplier tier', { list: [1, 2, 3, 4], numeric: true, fmt: (t) => `Tier ${t}${t === 1 ? ' (direct)' : ''}` })}
        {sel('supplier_size', 'Supplier size', { list: ['Small', 'Medium', 'Large'] })}
        {sel('disruption_severity', 'Severity', { list: [1, 2, 3, 4, 5], numeric: true, fmt: (s) => `${s} of 5` })}
        <label className="ip-field">
          <span>Backup supplier</span>
          <select className="select-field" value={String(!!value.has_backup_supplier)} onChange={(e) => set('has_backup_supplier', e.target.value === 'true')}>
            <option value="false">No backup (single source)</option>
            <option value="true">Qualified backup exists</option>
          </select>
        </label>
      </div>
    </div>
  );
}

export const DEFAULT_INCIDENT = PRESETS[0].inc;

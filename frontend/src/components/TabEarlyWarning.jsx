import React, { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowUpRight, BellRing, ChevronDown, CloudLightning, Globe2, Plus, Radar, Send, ShieldCheck, Target,
} from 'lucide-react';
import {
  CartesianGrid, ReferenceArea, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis, Cell,
} from 'recharts';
import { addSignal, fetchEarlyWarning, fetchLiveSignals, signalToSynapt, toggleSignal } from '../api';
import { fmtUsdShort } from '../format';
import { AnimatedNumber, Gauge, Reveal, Term } from './visuals';
import { Callout, Section, Skeleton, Spinner } from './ui';

const LEVEL = { Critical: '#dc2626', High: '#f59e0b', Elevated: '#eab308', Normal: '#16a34a' };
const SOURCE = { demo: ['Demo', 'badge-warning'], manual: ['Manual', 'badge-primary'], gdacs: ['Live · GDACS', 'badge-danger'] };
const COMP_LABEL = { signals: 'External alerts', delivery: 'Late deliveries', incidents: 'Recent incidents', buffer: 'Low stock cover', dependency: 'Dependency', regional: 'Regional history' };
const COMP_COLOR = { signals: '#ef4444', delivery: '#f59e0b', incidents: '#a855f7', buffer: '#0891b2', dependency: '#2563eb', regional: '#64748b' };

function LevelBar({ levels }) {
  const total = Object.values(levels).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="lvbar">
      <div className="lvbar-track">
        {Object.entries(levels).map(([k, v]) => v > 0 && (
          <motion.span key={k} style={{ background: LEVEL[k] }} initial={{ width: 0 }} animate={{ width: `${(v / total) * 100}%` }} transition={{ duration: 0.9 }} title={`${k}: ${v}`} />
        ))}
      </div>
      <div className="lvbar-legend">{Object.entries(levels).map(([k, v]) => <span key={k}><i style={{ background: LEVEL[k] }} />{k} {v}</span>)}</div>
    </div>
  );
}

function RiskMatrix({ suppliers }) {
  const data = suppliers.map((s) => ({ x: s.probability_90d * 100, y: s.impact_if_disrupted * 100, z: s.score, name: s.supplier_name, level: s.level }));
  return (
    <div style={{ height: 320 }}>
      <ResponsiveContainer>
        <ScatterChart margin={{ top: 10, right: 20, bottom: 30, left: 10 }}>
          <ReferenceArea x1={50} x2={100} y1={50} y2={100} fill="#fee2e2" fillOpacity={0.6} label={{ value: 'Act now', position: 'insideTopRight', fill: '#b91c1c', fontSize: 12 }} />
          <ReferenceArea x1={0} x2={50} y1={50} y2={100} fill="#fef3c7" fillOpacity={0.5} label={{ value: 'Prepare', position: 'insideTopLeft', fill: '#92400e', fontSize: 12 }} />
          <ReferenceArea x1={50} x2={100} y1={0} y2={50} fill="#fef3c7" fillOpacity={0.5} label={{ value: 'Watch', position: 'insideBottomRight', fill: '#92400e', fontSize: 12 }} />
          <ReferenceArea x1={0} x2={50} y1={0} y2={50} fill="#dcfce7" fillOpacity={0.5} label={{ value: 'Routine', position: 'insideBottomLeft', fill: '#166534', fontSize: 12 }} />
          <CartesianGrid strokeDasharray="3 3" stroke="#e6ebf2" />
          <XAxis type="number" dataKey="x" domain={[0, 100]} name="Likelihood" unit="%" label={{ value: 'How likely a disruption is (next 90 days)', position: 'insideBottom', offset: -14, fill: '#64748b', fontSize: 12 }} />
          <YAxis type="number" dataKey="y" domain={[0, 100]} name="Impact" unit="%" label={{ value: 'How bad it would be', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 12 }} />
          <ZAxis type="number" dataKey="z" range={[60, 360]} />
          <Tooltip cursor={{ strokeDasharray: '3 3' }} content={({ payload }) => payload?.[0] ? (
            <div className="chart-tip"><b>{payload[0].payload.name}</b><span>Likelihood {payload[0].payload.x.toFixed(0)}% · impact {payload[0].payload.y.toFixed(0)}%</span><span>Score {payload[0].payload.z.toFixed(0)} ({payload[0].payload.level})</span></div>
          ) : null} />
          <Scatter data={data} animationDuration={900}>
            {data.map((d) => <Cell key={d.name} fill={LEVEL[d.level]} fillOpacity={0.85} stroke="#fff" />)}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

function SignalCard({ s, onToggle, onSynapt }) {
  const [open, setOpen] = useState(false);
  const [src, cls] = SOURCE[s.source] || [s.source, 'badge-primary'];
  return (
    <motion.div layout className={`sig ${s.active ? '' : 'off'}`}>
      <button className="sig-head" onClick={() => setOpen(!open)}>
        <span className="sig-sev">{Array.from({ length: 5 }).map((_, i) => <i key={i} className={i < s.severity ? 'on' : ''} />)}</span>
        <div className="sig-main">
          <b>{s.headline}</b>
          <span>
            <span className={`badge ${cls}`}>{src}</span> {s.disruption_type} · {s.region || 'any region'}{s.industry ? ` · ${s.industry}` : ''}
          </span>
        </div>
        <div className="sig-num"><b>{s.affected?.length ?? 0}</b><span>suppliers</span></div>
        <div className="sig-num"><b>{fmtUsdShort(s.exposure_usd)}</b><span>exposure</span></div>
        <ChevronDown size={16} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div className="sig-body" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
            <div className="grid-auto" style={{ '--min': '260px', gap: '1rem' }}>
              <div>
                <div className="ct-eyebrow">Your suppliers in its path</div>
                {s.affected?.length ? s.affected.map((a) => (
                  <div key={a.supplier_name} className="sig-aff">
                    <b>{a.supplier_name}</b>
                    <span>{fmtUsdShort(a.revenue_loss_usd)} · {a.full_recovery_days}d recovery{a.has_backup_supplier ? '' : ' · no backup'}</span>
                  </div>
                )) : <p className="section-sub">None of your suppliers are in this region.</p>}
                <p className="section-sub" style={{ marginTop: 8 }}>
                  History: {s.history?.cases?.toLocaleString()} similar past disruptions, average {s.history?.avg_full_recovery} days to recover.
                </p>
              </div>
              <div>
                <div className="ct-eyebrow"><span className="badge badge-purple">Synapt</span> Playbook to follow</div>
                {s.playbook?.steps?.length ? (
                  <ol className="steps" style={{ marginTop: 6 }}>{s.playbook.steps.slice(1, 5).map((t, i) => <li key={i}>{t}</li>)}</ol>
                ) : <p className="section-sub">No playbook found.</p>}
              </div>
            </div>
            <div className="sig-actions">
              <button className="btn btn-secondary" onClick={() => onToggle(s)}>{s.active ? 'Dismiss alert' : 'Re-activate'}</button>
              <button className="btn btn-ghost" disabled={!!s.synapt_sent} onClick={() => onSynapt(s)}>
                <Send size={14} /> {s.synapt_sent ? 'Added to Synapt' : 'Add to Synapt knowledge'}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function SupplierWarning({ s, i }) {
  const [open, setOpen] = useState(i < 2);
  const total = Object.entries(s.components).reduce((a, [k, v]) => a + v, 0) || 1;
  return (
    <Reveal i={i}>
      <div className={`warn lv-${s.level.toLowerCase()}`}>
        <button className="warn-head" onClick={() => setOpen(!open)}>
          <Gauge value={s.score} size={92} />
          <div className="warn-main">
            <b>{s.supplier_name}</b>
            <span>{s.supplier_region} · {s.industry} · Tier {s.supplier_tier}{s.has_backup_supplier ? '' : ' · no backup'}</span>
            <div className="warn-tags">
              <span className="badge" style={{ background: `${LEVEL[s.level]}18`, color: LEVEL[s.level], borderColor: `${LEVEL[s.level]}44` }}>{s.level}</span>
              {s.trend > 0.5 && <span className="badge badge-danger"><ArrowUpRight size={12} /> +{s.trend.toFixed(0)} from alerts</span>}
              <span className="badge badge-primary">{Math.round(s.probability_90d * 100)}% chance of disruption (90 d)</span>
            </div>
          </div>
          <ChevronDown size={16} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }} />
        </button>
        <AnimatePresence>
          {open && (
            <motion.div className="warn-body" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
              <div className="ct-eyebrow">What is driving it</div>
              <div className="warn-stack">
                {Object.entries(s.components).filter(([, v]) => v > 0.01).map(([k, v]) => (
                  <motion.span key={k} style={{ background: COMP_COLOR[k] }} initial={{ width: 0 }} animate={{ width: `${(v / total) * 100}%` }}
                    transition={{ duration: 0.7 }} title={`${COMP_LABEL[k]}: ${(v * 100).toFixed(0)}%`} />
                ))}
              </div>
              <ul className="warn-drivers">{s.drivers.map((d) => <li key={d.key}><i style={{ background: COMP_COLOR[d.key] }} />{d.text}</li>)}</ul>
              <div className="ct-eyebrow" style={{ marginTop: 10 }}><ShieldCheck size={12} /> Preventive actions</div>
              <ul className="warn-actions">{s.actions.map((a, k) => <li key={k}>{a}</li>)}</ul>
              <p className="section-sub">If disrupted, its worst case is a {s.worst_case.disruption_type.toLowerCase()} ({fmtUsdShort(s.worst_case.revenue_loss_usd)}, {s.worst_case.full_recovery_days} days).</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </Reveal>
  );
}

export default function TabEarlyWarning({ portfolioCsv }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const [headline, setHeadline] = useState('');
  const [toSynapt, setToSynapt] = useState(false);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);
  const load = useCallback(() => fetchEarlyWarning(portfolioCsv).then(setD).catch((e) => setErr(e.message)), [portfolioCsv]);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    setBusy('add'); setMsg(null);
    try {
      const r = await addSignal(headline, '', toSynapt);
      setMsg(r.duplicate ? 'That alert is already in the feed.' : `Added: read as ${r.classification.disruption_type} in ${r.classification.supplier_region || 'an unspecified region'}.`);
      setHeadline(''); await load();
    } catch (e) { setMsg(e.message); } finally { setBusy(null); }
  };
  const live = async () => {
    setBusy('live'); setMsg(null);
    try { const r = await fetchLiveSignals(); setMsg(`Checked ${r.checked} live disaster alerts, added ${r.added} new orange/red ones.`); await load(); } catch (e) { setMsg(e.message); } finally { setBusy(null); }
  };
  const toggle = async (s) => { await toggleSignal(s.id, !s.active); load(); };
  const synapt = async (s) => { const r = await signalToSynapt(s.id); setMsg(r.sent ? 'Alert ingested into Synapt: graph answers will now take it into account.' : `Synapt: ${r.error}`); load(); };

  if (err) return <div className="page"><Callout tone="danger">{err}</Callout></div>;
  if (!d) return <div className="page"><Skeleton height={140} /><Skeleton height={320} /></div>;
  const exposure = d.signals.reduce((a, s) => a + s.exposure_usd, 0);
  return (
    <div className="page">
      <div className="grid-auto" style={{ '--min': '220px' }}>
        <div className="glass-card kpi" style={{ '--kpi-tone': '#ef4444' }}><div className="eyebrow">Active alerts</div><div className="kpi-value" style={{ color: '#ef4444' }}><AnimatedNumber value={d.signals.length} /></div><div className="kpi-sub">news, disasters, ports, geopolitics</div></div>
        <div className="glass-card kpi" style={{ '--kpi-tone': '#f59e0b' }}><div className="eyebrow">Revenue exposed to alerts</div><div className="kpi-value" style={{ color: '#b45309' }}><AnimatedNumber value={exposure} format={fmtUsdShort} /></div><div className="kpi-sub">if every alerted supplier is hit</div></div>
        <div className="glass-card kpi" style={{ '--kpi-tone': '#2563eb' }}><div className="eyebrow">Supplier warning levels</div><LevelBar levels={d.levels} /></div>
      </div>

      <div className="grid-auto" style={{ '--min': '440px', gap: '1.25rem', alignItems: 'start' }}>
        <Section icon={Target} iconColor="#dc2626" title="Risk matrix" subtitle="Each dot is one of your suppliers. Top-right = likely and severe: act first. Dot size = early-warning score.">
          <RiskMatrix suppliers={d.suppliers} />
        </Section>
        <Section icon={BellRing} iconColor="#ef4444" title="External alerts"
          subtitle="What is happening outside that could hit your suppliers. Click an alert to see who is exposed and the Synapt playbook."
          right={<button className="btn btn-secondary" onClick={live} disabled={busy === 'live'}>{busy === 'live' ? <Spinner /> : <Globe2 size={15} />} Fetch live disaster alerts</button>}>
          <div className="sig-add">
            <input className="input-field" value={headline} onChange={(e) => setHeadline(e.target.value)} placeholder="Paste a news headline, e.g. 'Floods close highways around Chennai port'"
              onKeyDown={(e) => e.key === 'Enter' && headline.length > 8 && add()} />
            <label><input type="checkbox" checked={toSynapt} onChange={(e) => setToSynapt(e.target.checked)} /> also add to Synapt</label>
            <button className="btn btn-primary" onClick={add} disabled={busy === 'add' || headline.length < 8}>{busy === 'add' ? <Spinner /> : <Plus size={15} />} Add alert</button>
          </div>
          {msg && <Callout tone="info" style={{ marginBottom: 10 }}>{msg}</Callout>}
          <div className="sig-list">
            {d.signals.map((s) => <SignalCard key={s.id} s={s} onToggle={toggle} onSynapt={synapt} />)}
            {!d.signals.length && <p className="section-sub"><CloudLightning size={14} /> No active alerts. Fetch live alerts or add a headline.</p>}
          </div>
          <p className="section-sub" style={{ marginTop: 8 }}>Demo alerts are simulated examples. Live alerts come from the public GDACS disaster feed.</p>
        </Section>
      </div>

      <Section icon={Radar} iconColor="#f59e0b" title="Supplier early warnings"
        subtitle={<>Ranked by <Term k="Early-warning score" />. Open a supplier to see what drives it and what to do before anything breaks.</>}>
        <div className="warn-legend">{Object.entries(COMP_LABEL).map(([k, v]) => <span key={k}><i style={{ background: COMP_COLOR[k] }} />{v} ({Math.round(d.weights[k] * 100)}%)</span>)}</div>
        <div className="warn-list">{d.suppliers.map((s, i) => <SupplierWarning key={s.supplier_name} s={s} i={i} />)}</div>
        <p className="section-sub" style={{ marginTop: 8 }}>{d.method}</p>
      </Section>
    </div>
  );
}

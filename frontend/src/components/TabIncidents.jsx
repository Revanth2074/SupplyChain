import React, { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, CheckCircle2, ChevronDown, ClipboardList, GraduationCap, Plus, Siren, UserRound } from 'lucide-react';
import { addIncidentAction, fetchIncidents, patchAction, patchIncident, seedIncidents } from '../api';
import { fmtUsdShort } from '../format';
import { AnimatedNumber, Reveal, Ring, Term } from './visuals';
import { Callout, Skeleton, Spinner } from './ui';

const PCOLOR = { P1: '#dc2626', P2: '#f59e0b', P3: '#2563eb', P4: '#16a34a' };
const STATUSES = ['open', 'investigating', 'mitigating', 'monitoring', 'resolved'];
const ASTATUS = { proposed: 'Proposed', accepted: 'Accepted', in_progress: 'In progress', done: 'Done', rejected: 'Rejected' };
const hrs = (h) => (Math.abs(h) >= 48 ? `${(h / 24).toFixed(1)} d` : `${h.toFixed(1)} h`);

function ActionRow({ a, onChanged }) {
  const [closing, setClosing] = useState(false);
  const [days, setDays] = useState(a.expected_recovery_days ? Math.round(a.expected_recovery_days) : '');
  const [loss, setLoss] = useState('');
  const [msg, setMsg] = useState(null);
  const overdue = a.status !== 'done' && a.status !== 'rejected' && Date.now() / 1000 > a.due_ts;
  const set = async (status) => { await patchAction(a.id, { status }); onChanged(); };
  const close = async () => {
    const r = await patchAction(a.id, { status: 'done', actual_recovery_days: Number(days), actual_loss_usd: loss ? Number(loss) : null });
    setMsg(r.learned ? 'Outcome saved: it is now training data for the prediction models.' : 'Closed.');
    setClosing(false); onChanged();
  };
  return (
    <div className={`act ${a.status}`}>
      <div className="act-row">
        <span className={`act-check ${a.status === 'done' ? 'on' : ''}`}>{a.status === 'done' ? <CheckCircle2 size={16} /> : null}</span>
        <div className="act-main">
          <b>{a.title}</b>
          <span><UserRound size={11} /> {a.owner} · due {new Date(a.due_ts * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
            {overdue && <em className="pos"> · overdue</em>}
            {a.actual_recovery_days != null && <em> · actual {a.actual_recovery_days}d vs expected {Math.round(a.expected_recovery_days)}d</em>}
          </span>
        </div>
        <select className="select-field act-sel" value={a.status} onChange={(e) => (e.target.value === 'done' ? setClosing(true) : set(e.target.value))}>
          {Object.entries(ASTATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      <AnimatePresence>
        {closing && (
          <motion.div className="act-close" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
            <span>What actually happened?</span>
            <label>Days to full recovery <input className="input-field" type="number" min="0" value={days} onChange={(e) => setDays(e.target.value)} /></label>
            <label>Revenue lost ($, optional) <input className="input-field" type="number" min="0" value={loss} onChange={(e) => setLoss(e.target.value)} /></label>
            <button className="btn btn-primary" onClick={close} disabled={days === ''}><GraduationCap size={15} /> Close & teach the model</button>
            <button className="btn btn-ghost" onClick={() => setClosing(false)}>Cancel</button>
          </motion.div>
        )}
      </AnimatePresence>
      {msg && <Callout tone="success" style={{ marginTop: 6 }}>{msg}</Callout>}
    </div>
  );
}

function Escalation({ chain }) {
  return (
    <div className="esc">
      {chain.map((c, i) => (
        <React.Fragment key={c.role}>
          <motion.div className={`esc-step ${c.notified ? 'on' : ''}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.12 }}>
            <span className="esc-dot">{c.notified ? <Siren size={12} /> : i + 1}</span>
            <b>{c.role}</b><small>{c.after_hours ? `after ${c.after_hours} h` : 'at once'}</small>
          </motion.div>
          {i < chain.length - 1 && <span className={`esc-line ${chain[i + 1].notified ? 'on' : ''}`} />}
        </React.Fragment>
      ))}
    </div>
  );
}

function IncidentCard({ inc, i, onChanged }) {
  const [open, setOpen] = useState(i === 0);
  const [title, setTitle] = useState('');
  const p = inc.priority.slice(0, 2);
  const frac = inc.status === 'resolved' ? 1 : Math.max(0, inc.remaining_hours) / inc.sla_hours;
  const ringColor = inc.breached ? '#dc2626' : frac < 0.25 ? '#f59e0b' : '#16a34a';
  const add = async () => { await addIncidentAction(inc.id, { title, owner: inc.owner, due_hours: inc.sla_hours }); setTitle(''); onChanged(); };
  return (
    <Reveal i={i}>
      <div className={`inc ${inc.breached ? 'breached' : ''} ${inc.status === 'resolved' ? 'resolved' : ''}`} style={{ '--p': PCOLOR[p] }}>
        <button className="inc-head" onClick={() => setOpen(!open)}>
          <Ring frac={frac} color={ringColor} size={54}>
            <span style={{ color: ringColor }}>{inc.status === 'resolved' ? '✓' : inc.breached ? '!' : hrs(inc.remaining_hours).split(' ')[0]}</span>
          </Ring>
          <div className="inc-main">
            <b>{inc.title}</b>
            <span>
              <span className="badge" style={{ background: `${PCOLOR[p]}18`, color: PCOLOR[p], borderColor: `${PCOLOR[p]}44` }}>{inc.priority}</span>
              {inc.breached && <span className="badge badge-danger"><AlertTriangle size={11} /> SLA missed by {hrs(-inc.remaining_hours)}</span>}
              {!inc.breached && inc.status !== 'resolved' && <span className="badge badge-success">{hrs(inc.remaining_hours)} left of {inc.sla_hours} h</span>}
              {inc.escalated && <span className="badge badge-warning"><Siren size={11} /> escalated</span>}
              <span className="inc-meta">{fmtUsdShort(inc.prediction.revenue_loss_usd)} expected · {Math.round(inc.prediction.full_recovery_days || 0)} d recovery · {inc.actions_done}/{inc.actions.length} actions done</span>
            </span>
          </div>
          <ChevronDown size={16} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }} />
        </button>
        <AnimatePresence>
          {open && (
            <motion.div className="inc-body" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
              <div className="inc-row">
                <div>
                  <div className="ct-eyebrow"><Term k="Escalation">Escalation path</Term></div>
                  <Escalation chain={inc.escalation_chain} />
                </div>
                <label className="inc-status">
                  <span className="ct-eyebrow">Status</span>
                  <select className="select-field" value={inc.status} onChange={async (e) => { await patchIncident(inc.id, { status: e.target.value }); onChanged(); }}>
                    {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </label>
              </div>
              <div className="ct-eyebrow" style={{ marginTop: 10 }}>Actions</div>
              <div className="act-list">{inc.actions.map((a) => <ActionRow key={a.id} a={a} onChanged={onChanged} />)}</div>
              <div className="act-add">
                <input className="input-field" placeholder="Add an action, e.g. 'Call backup supplier to confirm capacity'" value={title} onChange={(e) => setTitle(e.target.value)} />
                <button className="btn btn-secondary" disabled={title.length < 3} onClick={add}><Plus size={14} /> Add</button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </Reveal>
  );
}

export default function TabIncidents({ onOpen }) {
  const [list, setList] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => fetchIncidents().then(setList).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load]);
  const seed = async () => { setBusy(true); await seedIncidents(); await load(); setBusy(false); };
  if (err) return <div className="page"><Callout tone="danger">{err}</Callout></div>;
  if (!list) return <div className="page"><Skeleton height={200} /></div>;
  const open = list.filter((i) => i.status !== 'resolved');
  const stat = (label, value, color) => (
    <div className="glass-card kpi" style={{ '--kpi-tone': color }}><div className="eyebrow">{label}</div><div className="kpi-value" style={{ color }}><AnimatedNumber value={value} /></div></div>
  );
  return (
    <div className="page">
      <div className="grid-auto" style={{ '--min': '180px' }}>
        {stat('Open incidents', open.length, '#2563eb')}
        {stat('SLA deadlines missed', open.filter((i) => i.breached).length, '#dc2626')}
        {stat('Escalated', open.filter((i) => i.escalated).length, '#f59e0b')}
        {stat('Actions open', open.reduce((a, i) => a + i.actions.filter((x) => !['done', 'rejected'].includes(x.status)).length, 0), '#7c3aed')}
      </div>
      <div className="glass-panel section">
        <div className="section-head">
          <div>
            <h3 className="section-title"><ClipboardList size={18} color="#16a34a" /> Incidents</h3>
            <p className="section-sub">Sorted by urgency. Open one to see who has been alerted and to work through its actions. <Term k="SLA" /> clocks start when the incident opens.</p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary" onClick={() => onOpen('workflow')}>New from an analysis</button>
            {!list.some((i) => i.demo) && <button className="btn btn-ghost" onClick={seed} disabled={busy}>{busy ? <Spinner /> : null} Load demo incidents</button>}
          </div>
        </div>
        {!list.length && <Callout tone="info">No incidents yet. Run an analysis in the Incident Cockpit and press "Open incident", or load the demo incidents.</Callout>}
        <div className="inc-list">{list.map((inc, i) => <IncidentCard key={inc.id} inc={inc} i={i} onChanged={load} />)}</div>
      </div>
    </div>
  );
}

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  AlertTriangle, ArrowRight, Brain, ClipboardList, Cpu, Database, Radar, ShieldAlert, Sparkles, Timer, TrendingUp,
} from 'lucide-react';
import { fetchOverview } from '../api';
import { ENGINES } from '../guide';
import { AnimatedNumber, Reveal } from './visuals';
import { Callout, Skeleton } from './ui';

const LOOP = [
  { id: 'warning', step: 'Detect', text: 'Spot alerts and risky suppliers early', color: '#ef4444' },
  { id: 'workflow', step: 'Investigate', text: 'Find similar past cases and evidence', color: '#f59e0b' },
  { id: 'predict', step: 'Predict', text: 'Estimate loss, impact and recovery time', color: '#0891b2' },
  { id: 'rootcause', step: 'Explain', text: 'Show why: the cause and what made it worse', color: '#0e7490' },
  { id: 'decision', step: 'Simulate', text: 'Compare options in money and days', color: '#2563eb' },
  { id: 'workflow', step: 'Recommend', text: 'A checked action plan from the agents', color: '#4f46e5' },
  { id: 'incidents', step: 'Act', text: 'Owners, deadlines, escalation', color: '#16a34a' },
  { id: 'eval', step: 'Learn', text: 'Real outcomes retrain the models', color: '#15803d' },
];

/** The eight-step loop drawn as a ring with a travelling pulse. */
function LoopDiagram({ onOpen }) {
  const R = 150; const C = 200;
  const pos = (i) => {
    const a = -Math.PI / 2 + (i / LOOP.length) * Math.PI * 2;
    return [C + R * Math.cos(a), C + R * Math.sin(a)];
  };
  return (
    <div className="loop">
      <svg viewBox="0 0 400 400" className="loop-svg" aria-hidden="true">
        <circle cx={C} cy={C} r={R} fill="none" stroke="#e5eaf2" strokeWidth="14" />
        <motion.circle cx={C} cy={C} r={R} fill="none" stroke="url(#loopGrad)" strokeWidth="14" strokeLinecap="round"
          strokeDasharray={`${Math.PI * 2 * R * 0.12} ${Math.PI * 2 * R}`}
          animate={{ strokeDashoffset: [0, -Math.PI * 2 * R] }} transition={{ duration: 9, repeat: Infinity, ease: 'linear' }} />
        <defs>
          <linearGradient id="loopGrad" x1="0" x2="1"><stop offset="0" stopColor="#2563eb" stopOpacity="0" /><stop offset="1" stopColor="#2563eb" /></linearGradient>
        </defs>
        <text x={C} y={C - 8} textAnchor="middle" className="loop-center">Disruption</text>
        <text x={C} y={C + 14} textAnchor="middle" className="loop-center-sub">decision loop</text>
      </svg>
      {LOOP.map((s, i) => {
        const [x, y] = pos(i);
        return (
          <motion.button key={s.step} className="loop-node" style={{ left: `${(x / 400) * 100}%`, top: `${(y / 400) * 100}%`, '--c': s.color }}
            initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.1 + i * 0.08 }}
            whileHover={{ scale: 1.06 }} onClick={() => onOpen(s.id)} title={s.text}>
            <span className="loop-num">{i + 1}</span>
            <b>{s.step}</b>
            <small>{s.text}</small>
          </motion.button>
        );
      })}
    </div>
  );
}

/** Where each answer comes from: data -> Synapt + ML -> agents -> you. */
function Architecture() {
  const box = (x, y, w, h, title, sub, color, delay) => (
    <motion.g initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }}>
      <rect x={x} y={y} width={w} height={h} rx="12" fill="#fff" stroke={color} strokeWidth="1.5" />
      <rect x={x} y={y} width="5" height={h} rx="2" fill={color} />
      <text x={x + 16} y={y + 22} className="arch-t">{title}</text>
      <text x={x + 16} y={y + 40} className="arch-s">{sub}</text>
    </motion.g>
  );
  const flow = (d, delay) => (
    <g>
      <path d={d} fill="none" stroke="#dbe3ee" strokeWidth="2" />
      <motion.path d={d} fill="none" stroke="#2563eb" strokeWidth="2" strokeDasharray="6 10"
        animate={{ strokeDashoffset: [16, 0] }} transition={{ duration: 0.8, repeat: Infinity, ease: 'linear', delay }} />
    </g>
  );
  return (
    <svg viewBox="0 0 760 250" className="arch-svg" role="img" aria-label="How the assistant is put together">
      {flow('M150 72 C 210 72, 210 60, 262 60', 0)}
      {flow('M150 178 C 210 178, 210 190, 262 190', 0.2)}
      {flow('M150 72 C 200 72, 220 180, 262 190', 0.3)}
      {flow('M452 60 C 500 60, 500 125, 530 125', 0.4)}
      {flow('M452 190 C 500 190, 500 125, 530 125', 0.5)}
      {box(10, 45, 140, 54, 'External alerts', 'news · disasters · ports', '#ef4444', 0.05)}
      {box(10, 151, 140, 54, '100k past cases', 'historical dataset', ENGINES.data.color, 0.1)}
      {box(262, 30, 190, 60, 'Synapt knowledge', 'search · graph · playbooks', ENGINES.synapt.color, 0.2)}
      {box(262, 160, 190, 60, 'ML models', 'impact · loss · recovery · risk', ENGINES.ml.color, 0.3)}
      {box(530, 92, 220, 66, '7 AI agents + rules', 'plan · report · fact-check · judge', ENGINES.llm.color, 0.4)}
      <motion.text x="640" y="190" textAnchor="middle" className="arch-s" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.7 }}>
        → decisions, actions, learning
      </motion.text>
    </svg>
  );
}

function Stat({ icon: Icon, label, value, tone, onClick, hint }) {
  return (
    <motion.button className="home-stat" style={{ '--c': tone }} onClick={onClick} whileHover={{ y: -2 }}>
      <span className="home-stat-icon"><Icon size={18} /></span>
      <span className="home-stat-val"><AnimatedNumber value={value} /></span>
      <span className="home-stat-label">{label}</span>
      {hint && <span className="home-stat-hint">{hint} <ArrowRight size={12} /></span>}
    </motion.button>
  );
}

export default function TabHome({ onOpen }) {
  const [o, setO] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { fetchOverview().then(setO).catch((e) => setErr(e.message)); }, []);
  const ew = o?.early_warning || {};
  return (
    <div className="page">
      <Reveal>
        <section className="home-hero">
          <div>
            <div className="home-kicker"><Sparkles size={14} /> Supply-chain disruption assistant</div>
            <h2>From the first warning sign to a decision you can defend.</h2>
            <p>
              This assistant watches for trouble, finds what happened in similar past disruptions, predicts how bad it will be,
              explains why, compares your options in money and days, and tracks the actions until the problem is solved.
              Every page has a <b>How it works</b> button in the top-right corner.
            </p>
            <div className="home-cta">
              <button className="btn btn-primary" onClick={() => onOpen('warning')}><Radar size={16} /> See what is at risk now</button>
              <button className="btn btn-secondary" onClick={() => onOpen('workflow')}>Analyse a disruption</button>
              <button className="btn btn-ghost" onClick={() => onOpen('tower')}>Open the 3D map</button>
            </div>
          </div>
          <LoopDiagram onOpen={onOpen} />
        </section>
      </Reveal>

      {err && <Callout tone="danger">{err}</Callout>}
      {!o && !err && <Skeleton height={110} />}
      {o && (
        <div className="home-stats">
          <Stat icon={AlertTriangle} label="active external alerts" value={o.signals_active} tone="#ef4444" onClick={() => onOpen('warning')} hint="Early warning" />
          <Stat icon={TrendingUp} label="suppliers at high risk" value={(ew.Critical || 0) + (ew.High || 0)} tone="#f59e0b" onClick={() => onOpen('warning')} hint={`of ${o.suppliers}`} />
          <Stat icon={ClipboardList} label="open incidents" value={o.incidents_open} tone="#2563eb" onClick={() => onOpen('incidents')} hint={`${o.actions_open} actions open`} />
          <Stat icon={Timer} label="SLA deadlines missed" value={o.sla_breached} tone={o.sla_breached ? '#dc2626' : '#16a34a'} onClick={() => onOpen('incidents')} hint={`${o.escalated} escalated`} />
          <Stat icon={Database} label="past disruptions learnt from" value={o.cases} tone="#16a34a" onClick={() => onOpen('analytics')} hint="Analytics" />
          <Stat icon={Brain} label="real outcomes fed back" value={o.feedback.with_outcomes} tone="#7c3aed" onClick={() => onOpen('eval')} hint="Learning loop" />
        </div>
      )}

      <div className="grid-auto" style={{ '--min': '420px', gap: '1.25rem', alignItems: 'start' }}>
        <Reveal i={1}>
          <section className="glass-panel section">
            <div className="section-head"><h3 className="section-title"><Cpu size={18} color="#2563eb" /> Where the answers come from</h3></div>
            <Architecture />
            <div className="home-engines">
              {Object.values(ENGINES).map((e) => (
                <div key={e.label} style={{ '--c': e.color }}><b>{e.label}</b><span>{e.desc}</span></div>
              ))}
            </div>
          </section>
        </Reveal>
        <Reveal i={2}>
          <section className="glass-panel section">
            <div className="section-head">
              <h3 className="section-title"><ShieldAlert size={18} color="#ef4444" /> Needs attention</h3>
              <button className="btn btn-ghost" onClick={() => onOpen('warning')}>All risks <ArrowRight size={14} /></button>
            </div>
            {!o && <Skeleton height={180} />}
            {o?.top_risks?.map((r, i) => (
              <motion.div key={r.supplier_name} className="home-risk" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 + i * 0.1 }}>
                <div className={`home-risk-score lv-${r.level.toLowerCase()}`}>{r.score.toFixed(0)}</div>
                <div>
                  <b>{r.supplier_name}</b>
                  <span>{r.supplier_region} · {r.industry} · Tier {r.supplier_tier}</span>
                  <small>{r.drivers?.[0]?.text}</small>
                </div>
                <div className="home-risk-act">{r.actions?.[0]}</div>
              </motion.div>
            ))}
            {o && (
              <div className="home-synapt">
                <span className="badge badge-purple">Synapt</span>
                {o.synapt.configured ? `${o.synapt.answers} graph answers so far, average confidence ${Math.round((o.synapt.avg_confidence || 0) * 100)}/100.` : 'Not configured: local fallback search in use.'}
              </div>
            )}
          </section>
        </Reveal>
      </div>
    </div>
  );
}

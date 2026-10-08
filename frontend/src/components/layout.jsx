import React, { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Activity, AlertOctagon, BarChart3, BookOpen, Box, Briefcase, CheckCircle2, ChevronLeft, ChevronRight, ClipboardList, FlaskConical,
  GitBranch, Home, Info, Menu, Network, Radar, Scale, Search, Share2, Sliders, Workflow, X, Zap,
} from 'lucide-react';
import { ENGINES, GLOSSARY, PAGES, STAGES } from '../guide';

export const NAV = [
  { group: 'Overview', items: [{ id: 'home', icon: Home }, { id: 'tower', icon: Box }] },
  { group: 'Detect', stage: 'detect', items: [{ id: 'warning', icon: Radar }] },
  { group: 'Investigate', stage: 'investigate', items: [{ id: 'workflow', icon: Zap }, { id: 'search', icon: Search }, { id: 'knowledge', icon: Network }] },
  { group: 'Predict & explain', stage: 'predict', items: [{ id: 'predict', icon: Sliders }, { id: 'rootcause', icon: GitBranch }] },
  { group: 'Decide', stage: 'decide', items: [{ id: 'decision', icon: Scale }, { id: 'portfolio', icon: Briefcase }, { id: 'network', icon: Share2 }, { id: 'prioritize', icon: AlertOctagon }] },
  { group: 'Act & learn', stage: 'act', items: [{ id: 'incidents', icon: ClipboardList }, { id: 'eval', icon: CheckCircle2 }, { id: 'analytics', icon: BarChart3 }] },
  { group: 'System', items: [{ id: 'lab', icon: FlaskConical }] },
];
const stageColor = (id) => STAGES.find((s) => s.id === id)?.color || '#2563eb';

export function Sidebar({ active, onOpen, collapsed, setCollapsed, mobileOpen, setMobileOpen, badges = {} }) {
  return (
    <>
      <AnimatePresence>
        {mobileOpen && (
          <motion.div className="sb-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMobileOpen(false)} />
        )}
      </AnimatePresence>
      <aside className={`sidebar ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'open' : ''}`}>
        <div className="sb-brand">
          <div className="sb-logo"><Activity size={20} color="#fff" /></div>
          {!collapsed && (
            <div>
              <div className="sb-title">Disruption Assistant</div>
              <div className="sb-sub">on Synapt</div>
            </div>
          )}
          <button className="sb-close" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={18} /></button>
        </div>
        <nav className="sb-nav">
          {NAV.map((g) => (
            <div key={g.group} className="sb-group">
              {!collapsed ? (
                <div className="sb-group-label">
                  {g.stage && <i style={{ background: stageColor(g.stage) }} />}{g.group}
                </div>
              ) : <div className="sb-sep" />}
              {g.items.map(({ id, icon: Icon }) => {
                const on = active === id;
                return (
                  <button key={id} className={`sb-item ${on ? 'on' : ''}`} onClick={() => { onOpen(id); setMobileOpen(false); }}
                    title={collapsed ? PAGES[id].title : PAGES[id].plain} aria-current={on ? 'page' : undefined}
                    style={on && g.stage ? { '--stage': stageColor(g.stage) } : undefined}>
                    {on && <motion.span layoutId="sb-pill" className="sb-pill" transition={{ type: 'spring', stiffness: 500, damping: 40 }} />}
                    <Icon size={17} />
                    {!collapsed && <span className="sb-label">{PAGES[id].title}</span>}
                    {badges[id] ? <span className={`sb-badge ${collapsed ? 'dot' : ''}`}>{collapsed ? '' : badges[id]}</span> : null}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <button className="sb-collapse" onClick={() => setCollapsed(!collapsed)} aria-label="Collapse sidebar">
          {collapsed ? <ChevronRight size={16} /> : <><ChevronLeft size={16} /> Collapse</>}
        </button>
      </aside>
    </>
  );
}

function StatusDot({ ok, label, value, warn }) {
  return (
    <div className="tb-status" title={label}>
      <span className="tb-dot" style={{ background: ok ? '#16a34a' : warn ? '#f59e0b' : '#ef4444' }} />
      <span className="tb-status-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function TopBar({ page, health, onInfo, onMenu, onOpen }) {
  const info = PAGES[page];
  const stage = STAGES.find((s) => s.id === info.stage);
  const synaptOk = health?.synapt?.configured && !health?.synapt?.circuit_open;
  const sim = health?.simulated_outages || [];
  const llmOff = sim.includes('llm');
  const mlOff = health?.models?.fallback;
  return (
    <header className="topbar">
      <button className="tb-menu" onClick={onMenu} aria-label="Open menu"><Menu size={20} /></button>
      <div className="tb-title">
        <div className="tb-crumbs">
          {stage ? <span className="tb-stage" style={{ color: stage.color, background: `${stage.color}14` }}>{stage.label}</span> : <span className="tb-stage">{page === 'lab' ? 'System' : 'Overview'}</span>}
        </div>
        <AnimatePresence mode="wait">
          <motion.div key={page} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
            <h1>{info.title}</h1>
            <p>{info.plain}</p>
          </motion.div>
        </AnimatePresence>
      </div>
      <div className="tb-right">
        {sim.length > 0 && (
          <button className="tb-test" onClick={() => onOpen?.('lab')} title={`Simulated outage: ${sim.join(', ')}`}>
            <i /> Test mode · {sim.length} off
          </button>
        )}
        <StatusDot ok={synaptOk} label="Synapt" value={synaptOk ? 'Connected' : 'Fallback'} />
        <StatusDot ok={health?.models?.ready && !mlOff} warn label="Models" value={mlOff ? 'Cohort stats' : health?.models?.ready ? 'Ready' : 'Training'} />
        <StatusDot ok={health?.llm?.configured && !llmOff} warn label="Judge LLM" value={llmOff ? 'Rules' : health?.llm?.model || '—'} />
        <button className="tb-info" onClick={onInfo} aria-label="How this page works">
          <Info size={17} /> <span>How it works</span>
        </button>
      </div>
    </header>
  );
}

const GLOSS_KEYS = Object.keys(GLOSSARY);

export function InfoDrawer({ page, open, onClose }) {
  const info = PAGES[page];
  const [q, setQ] = useState('');
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  const terms = GLOSS_KEYS.filter((k) => !q || k.toLowerCase().includes(q.toLowerCase()) || GLOSSARY[k].toLowerCase().includes(q.toLowerCase()));
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="drawer-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.aside className="drawer" role="dialog" aria-label={`About ${info.title}`}
            initial={{ x: 480 }} animate={{ x: 0 }} exit={{ x: 480 }} transition={{ type: 'spring', stiffness: 320, damping: 34 }}>
            <div className="drawer-head">
              <div>
                <div className="ct-eyebrow"><BookOpen size={12} /> How this page works</div>
                <h2>{info.title}</h2>
              </div>
              <button className="ct-icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button>
            </div>
            <div className="drawer-body">
              <section className="drawer-plain">
                <strong>In plain words</strong>
                <p>{info.plain}</p>
              </section>
              <section>
                <h3>Why it matters</h3>
                <p>{info.why}</p>
              </section>
              <section>
                <h3><Workflow size={15} /> How it works</h3>
                <ol className="drawer-steps">
                  {info.how.map((h, i) => (
                    <motion.li key={i} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.08 + i * 0.07 }}>
                      <span>{i + 1}</span><p>{h}</p>
                    </motion.li>
                  ))}
                </ol>
              </section>
              <section>
                <h3>Who does the work</h3>
                <div className="drawer-engines">
                  {info.engines.map((e) => (
                    <div key={e} className="drawer-engine" style={{ '--c': ENGINES[e].color }}>
                      <b>{ENGINES[e].label}</b><span>{ENGINES[e].desc}</span>
                    </div>
                  ))}
                </div>
              </section>
              <section>
                <h3>How to read it</h3>
                <ul className="drawer-read">{info.read.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </section>
              {info.caveat && <section className="drawer-caveat"><strong>Good to know</strong><p>{info.caveat}</p></section>}
              <section>
                <h3>Glossary</h3>
                <input className="input-field" placeholder="Search terms…" value={q} onChange={(e) => setQ(e.target.value)} style={{ marginBottom: 8 }} />
                <dl className="drawer-gloss">
                  {terms.map((k) => (<React.Fragment key={k}><dt>{k}</dt><dd>{GLOSSARY[k]}</dd></React.Fragment>))}
                </dl>
              </section>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

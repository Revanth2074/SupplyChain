import React, { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  BrainCircuit, CheckCircle2, CircleSlash, Cpu, FlaskConical, Network, PlayCircle, Power, Radio, RotateCcw,
  ShieldCheck, Sparkles, XCircle,
} from 'lucide-react';
import { fetchFallbackLab, resetFallbackLab, runFallbackSelfTest, setFallbackSwitch } from '../api';
import { Callout, Section, Spinner } from './ui';
import { Reveal } from './visuals';

const ICON = { synapt: Network, synapt_graph: Network, synapt_procedures: Network, llm: Sparkles, ml: BrainCircuit, live_feed: Radio };
const ENGINE_LABEL = {
  llm: 'LLM', rules: 'Keyword rules', synapt: 'Synapt', 'local-lsa': 'Local LSA index', unavailable: 'Skipped (graceful)',
  model: 'ML models', cohort: 'Cohort statistics', template: 'Template', heuristic: 'Heuristic rubric',
  live: 'Live GDACS', blocked: 'Blocked', allowed: 'Allowed', crashed: 'Crashed',
};
const MINUTES = [5, 15, 30, 60];
const mmss = (s) => (s >= 60 ? `${Math.floor(s / 60)} min` : `${s}s`);

function Switch({ sw, busy, minutes, onToggle }) {
  const Icon = ICON[sw.id] || Cpu;
  const off = sw.active;
  return (
    <motion.div layout className={`lab-switch ${off ? 'off' : ''}`}>
      <div className="lab-sw-head">
        <span className="lab-sw-icon"><Icon size={17} /></span>
        <div className="lab-sw-title">
          <b>{sw.label}</b>
          <span>{off ? `Simulated outage · restores in ${mmss(sw.restores_in_s)}` : 'Working normally'}</span>
        </div>
        <button className={`lab-toggle ${off ? 'off' : 'on'}`} disabled={busy} onClick={() => onToggle(sw.id, !off, minutes)}
          role="switch" aria-checked={!off} aria-label={`${sw.label}: ${off ? 'off' : 'on'}`}>
          <motion.i layout transition={{ type: 'spring', stiffness: 600, damping: 35 }} />
          <em>{off ? 'OFF' : 'ON'}</em>
        </button>
      </div>
      <div className="lab-sw-body">
        <p><CircleSlash size={13} /> <b>When off:</b> {sw.outage}</p>
        <p><ShieldCheck size={13} /> <b>Fallback:</b> {sw.fallback}</p>
      </div>
    </motion.div>
  );
}

function CheckRow({ c, i }) {
  const fb = c.fallback && c.passed;
  return (
    <motion.div className={`lab-check ${c.passed ? 'pass' : 'fail'}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: i * 0.04 }}>
      <span className="lab-check-ico">{c.passed ? <CheckCircle2 size={18} /> : <XCircle size={18} />}</span>
      <div className="lab-check-main">
        <b>{c.label}</b>
        <span>{c.error ? <em className="pos">{c.error}</em> : c.detail}</span>
        {c.hint && <span className="lab-hint">{c.hint}</span>}
      </div>
      <div className="lab-check-path">
        <span className={`badge ${fb ? 'badge-warning' : c.passed ? 'badge-success' : 'badge-danger'}`}>
          {ENGINE_LABEL[c.got] || c.got}
        </span>
        {!c.passed && <small>expected {ENGINE_LABEL[c.expected] || c.expected}</small>}
        {c.passed && fb && <small>fallback used</small>}
      </div>
      <span className="lab-check-ms">{c.ms >= 1000 ? `${(c.ms / 1000).toFixed(1)} s` : `${c.ms} ms`}</span>
    </motion.div>
  );
}

export default function TabFallbackLab() {
  const [lab, setLab] = useState(null);
  const [busy, setBusy] = useState(false);
  const [minutes, setMinutes] = useState(30);
  const [full, setFull] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(() => fetchFallbackLab().then(setLab).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  const toggle = async (id, off, mins) => {
    setBusy(true); setErr(null);
    try { setLab(await setFallbackSwitch(id, off, mins)); setResult(null); } catch (e) { setErr(e.message); }
    setBusy(false);
  };
  const reset = async () => { setBusy(true); try { setLab(await resetFallbackLab()); setResult(null); } catch (e) { setErr(e.message); } setBusy(false); };
  const run = async () => {
    setRunning(true); setErr(null); setResult(null);
    try { setResult(await runFallbackSelfTest(full)); } catch (e) { setErr(e.message); }
    setRunning(false);
  };

  const offCount = lab?.switches.filter((s) => s.active).length || 0;
  const groups = result ? [
    { title: 'Feature checks', rows: result.checks.filter((c) => !c.group) },
    { title: 'Full 7-agent workflow', rows: result.checks.filter((c) => c.group) },
  ].filter((g) => g.rows.length) : [];

  return (
    <div className="page-stack">
      <Callout tone={offCount ? 'warning' : 'info'}>
        {offCount
          ? <><b>{offCount} dependenc{offCount > 1 ? 'ies are' : 'y is'} switched off for everyone using this app.</b> Every page now runs on its fallback. Switches restore themselves automatically, or use <b>Restore all</b>.</>
          : <>Switch a dependency off to simulate an outage, then <b>Run self-test</b> (or use any page) to see the fallback take over. Switches affect the whole app and restore themselves after the chosen time.</>}
      </Callout>
      {lab && !lab.enabled && <Callout tone="danger">The Fallback Lab is disabled on this deployment (<code>ENABLE_FALLBACK_LAB=0</code>).</Callout>}
      {err && <Callout tone="danger">{err}</Callout>}

      <Section icon={Power} title="Dependencies" subtitle="Each switch makes that dependency fail at its lowest level, so the real error handling and fallbacks run."
        right={(
          <div className="lab-controls">
            <label>Auto-restore after
              <select className="select-field" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
                {MINUTES.map((m) => <option key={m} value={m}>{m} min</option>)}
              </select>
            </label>
            <button className="btn btn-ghost" onClick={reset} disabled={busy || !offCount}><RotateCcw size={15} /> Restore all</button>
          </div>
        )}>
        {!lab ? <div style={{ padding: 20 }}><Spinner /></div> : (
          <div className="lab-grid">
            {lab.switches.map((sw) => <Switch key={sw.id} sw={sw} busy={busy || !lab.enabled} minutes={minutes} onToggle={toggle} />)}
          </div>
        )}
        {lab && (
          <div className="lab-status">
            <span><i className={lab.synapt.circuit_open ? 'bad' : 'ok'} /> Synapt {lab.synapt.simulated_outage?.length ? 'simulated outage' : lab.synapt.circuit_open ? `circuit open (${lab.synapt.open_tools.join(', ')})` : 'connected'}</span>
            <span><i className={lab.llm_configured ? 'ok' : 'bad'} /> LLM {lab.llm_configured ? 'configured' : 'not configured'}</span>
            <span><i className={lab.models_fallback ? 'warn' : 'ok'} /> Predictions from {lab.models_fallback ? 'cohort statistics' : 'ML models'}</span>
          </div>
        )}
      </Section>

      <Section icon={FlaskConical} title="Self-test" subtitle="Runs every feature once and checks it answered through the engine it should, given the switches above."
        right={(
          <div className="lab-controls">
            <label className="lab-check-label"><input type="checkbox" checked={full} onChange={(e) => setFull(e.target.checked)} /> Include full workflow (≈20 s, uses LLM credits when on)</label>
            <button className="btn btn-primary" onClick={run} disabled={running}>
              {running ? <><Spinner /> Running…</> : <><PlayCircle size={16} /> Run self-test</>}
            </button>
          </div>
        )}>
        <AnimatePresence mode="wait">
          {running && (
            <motion.div key="run" className="lab-running" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <Spinner size={18} /> Calling every feature with {offCount ? `${offCount} dependenc${offCount > 1 ? 'ies' : 'y'} off` : 'everything on'}…
            </motion.div>
          )}
          {result && !running && (
            <motion.div key="res" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <div className="lab-summary">
                <Reveal i={0} className={`lab-score ${result.passed === result.total ? 'pass' : 'fail'}`}>
                  <b>{result.passed}/{result.total}</b><span>checks passed</span>
                </Reveal>
                <Reveal i={1} className="lab-score"><b>{result.fallbacks_used}</b><span>answered by a fallback</span></Reveal>
                <Reveal i={2} className="lab-score"><b>{result.checks.filter((c) => c.got === 'crashed').length}</b><span>crashes</span></Reveal>
                <Reveal i={3} className="lab-score"><b>{(result.ms / 1000).toFixed(1)} s</b><span>total time</span></Reveal>
              </div>
              <p className="lab-off">Switched off during this run: {result.switched_off.length ? result.switched_off.map((s) => <span key={s} className="badge badge-warning">{s}</span>) : <span className="badge badge-success">nothing</span>}</p>
              {groups.map((g) => (
                <div key={g.title} className="lab-group">
                  <h4>{g.title}</h4>
                  {g.rows.map((c, i) => <CheckRow key={c.id} c={c} i={i} />)}
                </div>
              ))}
              <p className="lab-legend">
                <span className="badge badge-success">green</span> normal engine
                <span className="badge badge-warning">amber</span> fallback took over as designed
                <span className="badge badge-danger">red</span> unexpected path or crash
              </p>
            </motion.div>
          )}
        </AnimatePresence>
        {!result && !running && <p className="lab-empty">No run yet. Try: switch <b>Synapt (all tools)</b> off, run the self-test, then switch it back on and run again.</p>}
      </Section>
    </div>
  );
}

import React, { useEffect, useMemo, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, OrthographicCamera } from '@react-three/drei';
import {
  AlertTriangle, Anchor, Building2, Clock, DollarSign, Play, Plane, RefreshCw, ShieldCheck, Ship, Truck, X,
} from 'lucide-react';
import { fetchPortfolioSample, scorePortfolio, streamAnalyze } from '../api';
import { fmtUsdShort } from '../format';
import { DISRUPTED_AT, MODE_IMPACT, RISK, World, layoutWorld, regionStatus } from './logistics3d';

// ------------------------------------------------------------------ overlay panels
function KpiCard({ icon: Icon, label, value, tone }) {
  return (
    <div className="ct-card ct-kpi">
      <span className="ct-kpi-icon" style={{ background: `${tone}1a`, color: tone }}><Icon size={16} /></span>
      <div><div className="ct-kpi-label">{label}</div><div className="ct-kpi-value">{value}</div></div>
    </div>
  );
}

function SitePanel({ site, disruption, severity, onClose }) {
  const [steps, setSteps] = useState({});
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { setSteps({}); setResult(null); setError(null); setRunning(false); }, [site.supplier_name]);

  const type = disruption || site.worst_case.disruption_type;
  const run = () => {
    setRunning(true); setSteps({}); setResult(null); setError(null);
    const description = `${type} disruption at ${site.supplier_name}, a ${site.supplier_size.toLowerCase()} Tier ${site.supplier_tier} `
      + `${site.industry} supplier in ${site.supplier_region}. ${site.has_backup_supplier ? 'A backup supplier is qualified.' : 'There is no backup supplier.'} `
      + `Severity ${severity}/5.`;
    streamAnalyze(
      {
        description, use_graph: true, judge: true, top_k: 8,
        incident: {
          disruption_type: type, industry: site.industry, supplier_region: site.supplier_region, supplier_tier: site.supplier_tier,
          supplier_size: site.supplier_size, has_backup_supplier: site.has_backup_supplier, disruption_severity: severity,
        },
      },
      (ev) => {
        if (ev.type === 'agent_start') setSteps((p) => ({ ...p, [ev.agent]: { status: 'running', name: ev.name } }));
        if (ev.type === 'agent_done') setSteps((p) => ({ ...p, [ev.agent]: { status: 'done', name: ev.name, summary: ev.summary } }));
      },
      (e) => { setError(e.message); setRunning(false); },
      (d) => { setResult(d); setRunning(false); },
    );
  };

  return (
    <div className="ct-card ct-panel">
      <div className="ct-panel-head">
        <div>
          <div className="ct-eyebrow">{site.supplier_region} · Tier {site.supplier_tier} · {site.supplier_size}</div>
          <h3>{site.supplier_name}</h3>
          <div className="ct-sub">{site.industry} · {site.has_backup_supplier ? 'backup supplier qualified' : 'single source (no backup)'}</div>
        </div>
        <button className="ct-icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
      </div>
      <div className="ct-stats">
        <div><span>Risk index</span><strong style={{ color: RISK[site.band] }}>{site.risk_index}</strong><em>{site.band}</em></div>
        <div><span>Resilience</span><strong>{site.resilience.score}</strong><em>{site.resilience.band}</em></div>
        <div><span>Exp. recovery</span><strong>{Math.round(site.expected_full_recovery_days)}d</strong><em>weighted</em></div>
      </div>
      <div className="ct-eyebrow" style={{ marginTop: 14 }}>High-impact risk by disruption type</div>
      <div className="ct-bars">
        {site.by_type.map((t) => (
          <div key={t.disruption_type} className={`ct-bar ${t.disruption_type === disruption ? 'on' : ''}`}>
            <span>{t.disruption_type}</span>
            <div><i style={{ width: `${t.risk_probability * 100}%`, background: t.risk_probability >= DISRUPTED_AT ? '#ef4444' : '#3b82f6' }} /></div>
            <b>{Math.round(t.risk_probability * 100)}%</b>
          </div>
        ))}
      </div>
      <div className="ct-note">
        Worst case: <strong>{site.worst_case.disruption_type}</strong>, {fmtUsdShort(site.worst_case.revenue_loss_usd)} and {site.worst_case.full_recovery_days} days to recover.
        {site.drivers.length > 0 && <> Drivers: {site.drivers.join(', ')}.</>}
      </div>

      <button className="ct-btn" onClick={run} disabled={running}>
        {running ? <RefreshCw size={15} className="animate-spin" /> : <Play size={15} />}
        {running ? 'Agents working…' : `Simulate a ${type} here`}
      </button>
      {error && <div className="ct-error">{error}</div>}
      {Object.keys(steps).length > 0 && (
        <ol className="ct-steps">
          {Object.entries(steps).map(([id, s]) => (
            <li key={id} className={s.status}><b>{s.name}</b>{s.summary && <span>{s.summary}</span>}</li>
          ))}
        </ol>
      )}
      {result && (
        <div className="ct-result">
          <div className="ct-stats">
            <div><span>Priority</span><strong>{result.impact?.priority?.level?.split(' ')[0]}</strong><em>{result.impact?.priority?.action_sla}</em></div>
            <div><span>Loss</span><strong>{fmtUsdShort(result.recovery?.predicted_revenue_loss)}</strong><em>with {result.recovery?.strategy}</em></div>
            <div><span>Recovery</span><strong>{result.recovery?.predicted_full_days}d</strong><em>partial {result.recovery?.predicted_partial_days}d</em></div>
          </div>
          <div className="ct-eyebrow" style={{ marginTop: 12 }}>Response: {result.plan?.primary_strategy} → fallback {result.plan?.secondary_strategy}</div>
          {result.plan?.procedure && (
            <ol className="ct-playbook">{result.plan.procedure.steps.slice(2, 6).map((s) => <li key={s.n}>{s.text}</li>)}</ol>
          )}
          <div className="ct-sub" style={{ marginTop: 8 }}>
            <ShieldCheck size={13} /> Judge: {result.judge?.verdict} ({Math.round((result.judge?.overall_score || 0) * 100)}%) · fact-check {result.fact_check?.passed ? 'passed' : 'flagged'}
          </div>
        </div>
      )}
    </div>
  );
}

// camera presets: whole network, or close in on the hub airfield to watch ground operations
const VIEWS = {
  network: { label: 'Network', position: [60, 52, 60], zoom: 7.5, target: [0, 0, 0] },
  hub: { label: 'Hub airport', position: [14, 14, 22], zoom: 44, target: [-0.5, 0, 4.2] },
};

export default function ControlTower({ portfolio }) {
  const [data, setData] = useState(portfolio || null);
  const [asOf, setAsOf] = useState(portfolio ? new Date() : null);
  const [disruption, setDisruption] = useState(null);
  const [view, setView] = useState('network');
  const cam = VIEWS[view];
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);

  const load = () => {
    setError(null);
    fetchPortfolioSample().then((csv) => scorePortfolio(csv, 3))
      .then((d) => { setData(d); setAsOf(new Date()); }).catch((e) => setError(e.message));
  };
  useEffect(() => {
    if (portfolio) { setData(portfolio); setAsOf(new Date()); setSelected(null); } else if (!data) load();
  }, [portfolio]); // eslint-disable-line react-hooks/exhaustive-deps

  const kpis = useMemo(() => {
    if (!data) return null;
    const s = data.suppliers;
    const hit = disruption ? s.filter((x) => (x.by_type.find((t) => t.disruption_type === disruption)?.risk_probability ?? 0) >= DISRUPTED_AT) : [];
    const loss = disruption
      ? s.reduce((a, x) => a + (x.by_type.find((t) => t.disruption_type === disruption)?.revenue_loss_usd || 0), 0)
      : data.summary.expected_loss_total;
    const st = regionStatus(layoutWorld(s), disruption).byRegion;
    const halted = Object.values(st).reduce((a, r) => ({
      sea: a.sea + (r.sea ? 1 : 0), air: a.air + (r.air ? 1 : 0), cranes: a.cranes + (r.crane ? 1 : 0),
    }), { sea: 0, air: 0, cranes: 0 });
    return {
      halted, regions: Object.keys(st).length,
      sites: s.length, atRisk: disruption ? hit.length : data.summary.critical_or_high,
      loss, resilience: (s.reduce((a, x) => a + x.resilience.score, 0) / s.length).toFixed(1),
    };
  }, [data, disruption]);

  return (
    <div className="ct-root">
      <Canvas shadows dpr={[1, 2]} onPointerMissed={() => setSelected(null)}>
        <OrthographicCamera key={view} makeDefault position={cam.position} zoom={cam.zoom} near={-300} far={700} />
        <OrbitControls key={`c${view}`} target={cam.target} enableDamping minZoom={5} maxZoom={80} maxPolarAngle={Math.PI / 2.5} minPolarAngle={Math.PI / 7} />
        <ambientLight intensity={0.75} />
        <hemisphereLight args={['#ffffff', '#dbe4f0', 0.5]} />
        <directionalLight castShadow position={[25, 40, 15]} intensity={1.15}
          shadow-mapSize={[4096, 4096]} shadow-camera-left={-60} shadow-camera-right={60} shadow-camera-top={60} shadow-camera-bottom={-60} />
        {data && <World data={data} disruption={disruption} selected={selected} setSelected={setSelected} />}
      </Canvas>

      {/* top bar */}
      <div className="ct-top">
        {kpis && (
          <div className="ct-kpis">
            <KpiCard icon={Building2} label="Supplier sites" value={kpis.sites} tone="#2563eb" />
            <KpiCard icon={AlertTriangle} label={disruption ? `Hit by ${disruption}` : 'Critical / high risk'} value={kpis.atRisk} tone="#ef4444" />
            <KpiCard icon={DollarSign} label={disruption ? 'Exposure if it hits all' : 'Expected exposure'} value={fmtUsdShort(kpis.loss)} tone="#f59e0b" />
            <KpiCard icon={ShieldCheck} label="Avg resilience" value={kpis.resilience} tone="#16a34a" />
          </div>
        )}
        <div className="ct-card ct-fresh" title="Predictions come from the ML models over the 100k-case dataset, not a live feed.">
          <Clock size={14} /> Scored {asOf ? asOf.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
          {data && <> · severity {data.severity_assumed} · {portfolio ? 'your portfolio' : 'sample portfolio'}</>}
          <button className="ct-icon-btn" onClick={load} title="Re-score the sample portfolio"><RefreshCw size={13} /></button>
        </div>
      </div>

      {/* disruption selector */}
      {data && (
        <div className="ct-card ct-chips">
          <span className="ct-eyebrow">Simulate</span>
          <button className={!disruption ? 'on' : ''} onClick={() => setDisruption(null)}>Normal operations</button>
          {data.disruption_types.map((t) => (
            <button key={t} className={disruption === t ? 'on danger' : ''} onClick={() => setDisruption(t)}>{t}</button>
          ))}
          {disruption && kpis && (
            <span className="ct-halted">
              <Ship size={13} /> {kpis.halted.sea}/{kpis.regions} sea lanes
              <Plane size={13} /> {kpis.halted.air}/{kpis.regions} air routes
              <Anchor size={13} /> {kpis.halted.cranes} ports stopped
              {!Object.keys(MODE_IMPACT[disruption] || {}).length && ' · site-level only'}
            </span>
          )}
        </div>
      )}

      {/* camera views */}
      <div className="ct-card ct-views">
        <span className="ct-eyebrow">View</span>
        {Object.entries(VIEWS).map(([k, v]) => (
          <button key={k} className={view === k ? 'on' : ''} onClick={() => setView(k)}>{v.label}</button>
        ))}
      </div>

      {/* legend */}
      <div className="ct-card ct-legend">
        {Object.entries(RISK).map(([k, c]) => <span key={k}><i style={{ background: c }} />{k}</span>)}
        <span><i style={{ background: '#f97316', borderRadius: 2, width: 4 }} />no backup</span>
        <span><Truck size={13} color="#2563eb" />truck</span>
        <span><Ship size={13} color="#1e3a8a" />container ship</span>
        <span><Plane size={13} color="#0284c7" />cargo jet</span>
        <span><i style={{ background: '#ef4444', height: 3, width: 14 }} />halted lane</span>
      </div>

      {selected && <SitePanel site={selected} disruption={disruption} severity={data?.severity_assumed || 3} onClose={() => setSelected(null)} />}
      {!selected && data && <div className="ct-hint">Click a site to inspect it · drag to rotate · scroll to zoom</div>}
      {error && <div className="ct-card ct-error ct-floating-error">{error}</div>}
      {!data && !error && <div className="ct-loading">Building the supplier network…</div>}
    </div>
  );
}

import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Award, Calculator, ChevronDown, Clock, Coins, Lightbulb, Scale } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { fetchDecision } from '../api';
import { fmtUsd, fmtUsdShort } from '../format';
import { AnimatedNumber, DEFAULT_INCIDENT, IncidentPicker, Reveal, Term } from './visuals';
import { Callout, Section, Skeleton } from './ui';

const SHORT = { do_nothing: 'Absorb', backup: 'Backup', alt_supplier: 'Spot-buy', reroute: 'Reroute', buffer: 'Buffer', combined: 'Combined' };

function ScenarioCard({ s, best, base, i }) {
  const good = s.net_benefit_usd > 0;
  return (
    <Reveal i={i}>
      <div className={`scn ${best ? 'best' : ''} ${s.hypothetical ? 'hyp' : ''}`}>
        {best && <motion.div className="scn-ribbon" initial={{ y: -8, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.5 }}><Award size={13} /> Recommended</motion.div>}
        <div className="scn-tag">{s.key === 'do_nothing' ? 'Baseline' : `Option ${i}`}{s.hypothetical ? ' · needs a backup' : ''}</div>
        <h4>{s.label}</h4>
        <div className="scn-figs">
          <div><span>Loss</span><b>{fmtUsdShort(s.revenue_loss_usd)}</b></div>
          <div><span>Mitigation</span><b>{fmtUsdShort(s.mitigation_cost_usd)}</b></div>
          <div><span>Recovery</span><b>{s.full_recovery_days.toFixed(0)}d</b></div>
        </div>
        {s.key !== 'do_nothing' && (
          <div className={`scn-net ${good ? 'pos' : 'neg'}`}>
            <span>Net benefit vs absorbing</span>
            <b>{good ? '+' : '−'}{fmtUsdShort(Math.abs(s.net_benefit_usd))}</b>
            <small>
              {s.days_saved > 0 ? `${s.days_saved.toFixed(0)} days sooner · ` : ''}
              {s.extra_cost_usd <= 0 ? 'cheaper to run than absorbing' : s.roi != null ? `ROI ${s.roi > 0 ? '+' : ''}${s.roi.toFixed(1)}×` : ''}
            </small>
          </div>
        )}
        {s.key === 'do_nothing' && <div className="scn-net base"><span>Total business cost</span><b>{fmtUsdShort(base.total_cost_usd)}</b><small>the yardstick for the others</small></div>}
        <p className="scn-note">{s.cost_note}</p>
      </div>
    </Reveal>
  );
}

function CostEditor({ assumptions, onChange }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="costed">
      <button className="btn btn-ghost" onClick={() => setOpen(!open)}><Calculator size={15} /> Cost assumptions <ChevronDown size={14} style={{ transform: open ? 'rotate(180deg)' : 'none' }} /></button>
      {open && (
        <div className="table-wrap" style={{ marginTop: 8 }}>
          <table className="table">
            <thead><tr><th>Option</th><th>Set-up cost ($)</th><th>Running cost per day ($)</th><th>What it covers</th></tr></thead>
            <tbody>
              {Object.entries(assumptions).map(([k, c]) => (
                <tr key={k}>
                  <td>{SHORT[k]}</td>
                  {['fixed', 'daily'].map((f) => (
                    <td key={f}><input className="input-field" type="number" min="0" step="1000" value={c[f]} style={{ maxWidth: 140 }}
                      onChange={(e) => onChange({ ...assumptions, [k]: { ...c, [f]: Number(e.target.value) } })} /></td>
                  ))}
                  <td style={{ fontSize: '0.76rem' }}>{c.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function TabDecision({ options }) {
  const [inc, setInc] = useState(DEFAULT_INCIDENT);
  const [costs, setCosts] = useState(null);
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      fetchDecision(inc, costs).then((r) => { if (live) { setD(r); setErr(null); } }).catch((e) => live && setErr(e.message));
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [inc, costs]);

  const chart = useMemo(() => (d ? d.scenarios.map((s) => ({
    name: SHORT[s.key], loss: s.revenue_loss_usd, mitigation: s.mitigation_cost_usd, total: s.total_cost_usd,
    days: s.full_recovery_days, outage: s.outage_days, best: s.key === d.recommended,
  })) : []), [d]);
  const base = d?.scenarios[0];
  const best = d?.scenarios.find((s) => s.key === d.recommended);

  return (
    <div className="page">
      <Section icon={Scale} iconColor="#2563eb" title="1 · Describe the disruption" subtitle="Pick a quick example or set the details. Everything below updates instantly.">
        <IncidentPicker value={inc} onChange={setInc} options={options} />
      </Section>
      {err && <Callout tone="danger">{err}</Callout>}
      {!d && !err && <Skeleton height={300} />}
      {d && (
        <>
          <motion.div key={d.recommended + d.why} className="verdict" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <div className="verdict-icon"><Lightbulb size={22} /></div>
            <div>
              <div className="ct-eyebrow">The assistant recommends</div>
              <h3>{best.label}</h3>
              <p>{d.why}</p>
              {d.hint && <p className="section-sub">{d.hint}</p>}
            </div>
            <div className="verdict-figs">
              <div><span>Saves vs absorbing</span><b className="neg"><AnimatedNumber value={Math.max(0, best.net_benefit_usd)} format={fmtUsdShort} /></b></div>
              <div><span>Recovers sooner by</span><b><AnimatedNumber value={Math.max(0, best.days_saved)} format={(v) => `${Math.round(v)} days`} /></b></div>
            </div>
          </motion.div>

          <Section icon={Coins} iconColor="#b45309" title="2 · Compare the options"
            subtitle={<>Total business cost = expected loss + cost of the response. Lowest bar wins. <Term k="Outage days" /> drive the loss.</>}
            right={<CostEditor assumptions={d.assumptions} onChange={setCosts} />}>
            <div className="grid-auto" style={{ '--min': '420px', gap: '1.25rem' }}>
              <div style={{ height: 300 }}>
                <ResponsiveContainer>
                  <BarChart data={chart} margin={{ top: 20, right: 10, left: 10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis tickFormatter={fmtUsdShort} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v, n) => [fmtUsd(v), n === 'loss' ? 'Expected loss' : 'Mitigation cost']} />
                    <Legend formatter={(v) => (v === 'loss' ? 'Expected loss' : 'Mitigation cost')} />
                    <Bar dataKey="loss" stackId="a" animationDuration={900}>
                      {chart.map((c) => <Cell key={c.name} fill={c.best ? '#1d4ed8' : '#64748b'} />)}
                    </Bar>
                    <Bar dataKey="mitigation" stackId="a" radius={[6, 6, 0, 0]} animationDuration={900}>
                      {chart.map((c) => <Cell key={c.name} fill={c.best ? '#93c5fd' : '#cbd5e1'} />)}
                      <LabelList dataKey="total" position="top" formatter={fmtUsdShort} style={{ fontSize: 11, fill: '#334155' }} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div>
                <div className="ct-eyebrow" style={{ marginBottom: 8 }}><Clock size={12} /> Days until fully recovered</div>
                {chart.map((c, i) => (
                  <div key={c.name} className="daysbar">
                    <span>{c.name}</span>
                    <div><motion.i style={{ background: c.best ? '#2563eb' : '#94a3b8' }} initial={{ width: 0 }}
                      animate={{ width: `${(c.days / Math.max(...chart.map((x) => x.days))) * 100}%` }} transition={{ duration: 0.8, delay: i * 0.06 }} /></div>
                    <b>{c.days.toFixed(0)}d</b>
                  </div>
                ))}
                <p className="section-sub" style={{ marginTop: 8 }}>Predicted by the ML models for this exact profile ({d.support.matching_cases} matching past cases).</p>
              </div>
            </div>
          </Section>

          <Section icon={Scale} iconColor="#2563eb" title="3 · Option by option" subtitle={<><Term k="Net benefit" /> and <Term k="ROI" /> are measured against simply absorbing the delay.</>}>
            <div className="scn-grid">{d.scenarios.map((s, i) => <ScenarioCard key={s.key} s={s} i={i} best={s.key === d.recommended} base={base} />)}</div>
            <p className="section-sub" style={{ marginTop: 10 }}>
              Loss for each option = the ML model's do-nothing loss, scaled by how long and how badly that option leaves you short of supply.
              Mitigation costs are assumptions: edit them above to match your business.
            </p>
          </Section>
        </>
      )}
    </div>
  );
}

import React, { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { motion } from 'framer-motion';
import { Brain, GitBranch, History, Minus, Plus, Sparkles } from 'lucide-react';
import { fetchRootCause, fetchRootCauseSynapt } from '../api';
import { fmtUsdShort } from '../format';
import { AnimatedNumber, DEFAULT_INCIDENT, FlowChain, IncidentPicker, Reveal } from './visuals';
import { Callout, Section, Skeleton, Spinner, SynaptPassCard } from './ui';

const KIND_COLOR = {
  'root cause': '#dc2626', mechanism: '#ea580c', 'supply effect': '#d97706',
  'operational effect': '#0891b2', 'customer effect': '#2563eb', 'financial effect': '#7c3aed',
};

function FactorBars({ items, side }) {
  const max = Math.max(1, ...items.map((f) => Math.abs(f.effect) + 3 * Math.abs(f.impact_effect_pts || 0)));
  return (
    <div className={`fbars ${side}`}>
      {items.map((f, i) => {
        const w = (Math.abs(f.effect) + 3 * Math.abs(f.impact_effect_pts || 0)) / max;
        return (
          <motion.div key={f.text} className="fbar" initial={{ opacity: 0, x: side === 'neg' ? 12 : -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 + i * 0.08 }}>
            <div className="fbar-text"><b>{f.text}</b>{f.detail && <span>{f.detail}</span>}
              <span>{f.effect ? `${f.effect > 0 ? '+' : ''}${f.effect.toFixed(1)} days to recover` : ''}{f.impact_effect_pts ? ` · ${f.impact_effect_pts > 0 ? '+' : ''}${f.impact_effect_pts.toFixed(1)} pts impact` : ''}</span>
            </div>
            <div className="fbar-track"><motion.i initial={{ width: 0 }} animate={{ width: `${Math.max(6, w * 100)}%` }} transition={{ duration: 0.7, delay: 0.15 + i * 0.08 }} /></div>
          </motion.div>
        );
      })}
      {!items.length && <p className="section-sub">None stand out for this profile.</p>}
    </div>
  );
}

export default function TabRootCause({ options }) {
  const [inc, setInc] = useState(DEFAULT_INCIDENT);
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const [syn, setSyn] = useState(null);
  const [synBusy, setSynBusy] = useState(false);
  useEffect(() => {
    let live = true;
    setSyn(null);
    const t = setTimeout(() => fetchRootCause(inc).then((r) => live && setD(r)).catch((e) => live && setErr(e.message)), 200);
    return () => { live = false; clearTimeout(t); };
  }, [inc]);
  const askSynapt = async () => {
    setSynBusy(true);
    try { setSyn(await fetchRootCauseSynapt(inc)); } catch (e) { setSyn({ error: e.message }); } finally { setSynBusy(false); }
  };

  return (
    <div className="page">
      <Section icon={GitBranch} iconColor="#dc2626" title="Which disruption?" subtitle="Pick an example or set the details; the analysis follows instantly.">
        <IncidentPicker value={inc} onChange={setInc} options={options} />
      </Section>
      {err && <Callout tone="danger">{err}</Callout>}
      {!d && !err && <Skeleton height={260} />}
      {d && (
        <>
          <Section icon={GitBranch} iconColor="#dc2626" title={`How a ${d.root_cause.toLowerCase()} turns into lost revenue`}
            subtitle="Read left to right: each step causes the next. Sizes come from the ML predictions for this exact profile.">
            <FlowChain key={JSON.stringify(inc)} steps={d.chain.map((c) => ({
              kicker: `${c.kind} · ${c.when}`, title: c.stage, body: c.detail, color: KIND_COLOR[c.kind],
              metric: c.unit === '$' ? fmtUsdShort(c.metric) : c.unit === '%' ? `${c.metric.toFixed(0)}% capacity lost` : c.unit === 'days' ? `${c.metric.toFixed(0)} days` : null,
            }))} />
          </Section>

          <div className="grid-auto" style={{ '--min': '400px', gap: '1.25rem', alignItems: 'start' }}>
            <Section icon={Plus} iconColor="#dc2626" title="What made it worse" subtitle="Factors that lengthen recovery or deepen the impact, compared with a typical case.">
              <FactorBars items={d.contributing} side="pos" />
            </Section>
            <Section icon={Minus} iconColor="#16a34a" title="What helped" subtitle="Factors that shorten recovery or soften the impact.">
              <FactorBars items={d.mitigating} side="neg" />
            </Section>
          </div>

          <Section icon={History} iconColor="#16a34a" title="What history says" subtitle={`All ${d.incident.disruption_type.toLowerCase()} disruptions in ${d.incident.industry} in the 100,000-case history.`}>
            <div className="evid">
              <Reveal i={0} className="evid-card"><b><AnimatedNumber value={d.evidence.cases} /></b><span>similar past disruptions</span></Reveal>
              <Reveal i={1} className="evid-card"><b><AnimatedNumber value={(d.evidence.share_high_impact || 0) * 100} format={(v) => `${v.toFixed(0)}%`} /></b><span>lost over half of production</span></Reveal>
              <Reveal i={2} className="evid-card"><b><AnimatedNumber value={d.evidence.avg_full_recovery} format={(v) => `${v.toFixed(0)} d`} /></b><span>average time to full recovery</span></Reveal>
              <Reveal i={3} className="evid-card"><b><AnimatedNumber value={d.evidence.avg_loss} format={fmtUsdShort} /></b><span>average revenue loss</span></Reveal>
              <Reveal i={4} className="evid-card hl"><b><AnimatedNumber value={d.evidence.backup_effect_days} format={(v) => `${v.toFixed(0)} d`} /></b><span>faster recovery when a backup supplier existed</span></Reveal>
            </div>
            {d.support?.warning && <Callout tone="warning" style={{ marginTop: 10 }}>{d.support.warning}</Callout>}
          </Section>

          <Section icon={Brain} iconColor="#7c3aed" title="Ask Synapt to explain it"
            subtitle="Synapt walks its knowledge graph and playbooks to explain the drivers in words, and shows how confident it is."
            right={<button className="btn btn-primary" onClick={askSynapt} disabled={synBusy}>{synBusy ? <Spinner /> : <Sparkles size={15} />} Explain with Synapt</button>}>
            {synBusy && <><Skeleton height={140} /><p className="section-sub" style={{ marginTop: 6 }}>Graph reasoning usually takes 10-40 seconds.</p></>}
            {syn?.error && <Callout tone="danger">{syn.error}</Callout>}
            {syn && !syn.error && (
              <div className="grid-auto" style={{ '--min': '360px', gap: '1rem', alignItems: 'start' }}>
                <div className="markdown-body"><ReactMarkdown>{syn.answer}</ReactMarkdown></div>
                <div>
                  <div className="ct-eyebrow" style={{ marginBottom: 6 }}>How sure Synapt is</div>
                  <SynaptPassCard quality={syn.quality} compact />
                  {syn.procedures?.length > 0 && <p className="section-sub" style={{ marginTop: 8 }}>Playbooks used: {syn.procedures.join(', ')}</p>}
                </div>
              </div>
            )}
            {!syn && !synBusy && <p className="section-sub">Optional: adds Synapt's evidence-backed explanation to the analysis above.</p>}
          </Section>
        </>
      )}
    </div>
  );
}

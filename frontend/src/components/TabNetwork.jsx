import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Factory, PlugZap, Share2 } from 'lucide-react';
import { Layer, Rectangle, ResponsiveContainer, Sankey, Tooltip } from 'recharts';
import { fetchNetwork, fetchOffline } from '../api';
import { fmtUsdShort } from '../format';
import { AnimatedNumber, FlowChain, Reveal } from './visuals';
import { Callout, Section, Skeleton, Spinner } from './ui';

const KIND = { supplier: '#2563eb', product: '#0891b2', line: '#7c3aed', customer: '#16a34a' };
const BAND = { Critical: '#dc2626', High: '#f59e0b', Medium: '#2563eb', Low: '#16a34a' };

function SankeyNode({ x, y, width, height, payload, onPick, offline }) {
  const isSup = payload.kind === 'supplier';
  const color = isSup ? BAND[payload.band] || KIND.supplier : KIND[payload.kind];
  const hit = offline && (payload.name === offline.supplier || offline.affected?.some((a) => a.product === payload.name || a.line === payload.name || a.customer === payload.name));
  const label = payload.kind === 'line' ? payload.name.split(' · ')[0] : payload.name;
  return (
    <Layer>
      <Rectangle x={x} y={y} width={width} height={height} fill={color} fillOpacity={offline ? (hit ? 1 : 0.25) : 0.9}
        stroke={hit ? '#dc2626' : 'none'} strokeWidth={hit ? 2 : 0} style={{ cursor: isSup ? 'pointer' : 'default' }}
        onClick={() => isSup && onPick(payload.name)} />
      <text x={x + width + 6} y={y + height / 2} textAnchor="start" dominantBaseline="middle"
        fontSize={11} fontWeight={payload.kind === 'line' ? 600 : 400} fill={offline && !hit ? '#94a3b8' : '#1e293b'}
        style={{ cursor: isSup ? 'pointer' : 'default' }} onClick={() => isSup && onPick(payload.name)}>
        {label}<title>{payload.name}</title>
      </text>
    </Layer>
  );
}

export default function TabNetwork({ portfolioCsv }) {
  const [g, setG] = useState(null);
  const [err, setErr] = useState(null);
  const [pick, setPick] = useState('');
  const [off, setOff] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { fetchNetwork(portfolioCsv).then(setG).catch((e) => setErr(e.message)); }, [portfolioCsv]);
  const run = async (name) => {
    setPick(name); setBusy(true);
    try { setOff(await fetchOffline(name, portfolioCsv)); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const suppliers = g?.nodes.filter((n) => n.kind === 'supplier').sort((a, b) => b.risk_index - a.risk_index) || [];

  return (
    <div className="page">
      {err && <Callout tone="danger">{err}</Callout>}
      {!g && !err && <Skeleton height={420} />}
      {g && (
        <>
          <Section icon={Share2} iconColor="#0891b2" title="Who depends on whom"
            subtitle="Left to right: suppliers → products → production lines → customers. Band width = weekly revenue flowing through that link. Click a supplier to take it offline."
            right={<div className="net-legend">{Object.entries(KIND).map(([k, c]) => <span key={k}><i style={{ background: c }} />{k}</span>)}</div>}>
            <div style={{ height: 560 }}>
              <ResponsiveContainer>
                <Sankey data={{ nodes: g.nodes, links: g.links }} nodePadding={10} nodeWidth={12} margin={{ top: 10, right: 150, bottom: 10, left: 10 }}
                  link={{ stroke: '#2563eb', strokeOpacity: 0.16 }}
                  node={<SankeyNode onPick={run} offline={off} />}>
                  <Tooltip formatter={(v) => `${fmtUsdShort(v)} / week`} />
                </Sankey>
              </ResponsiveContainer>
            </div>
            <p className="section-sub">{g.note} {g.single_sourced_products.length} product(s) have only one supplier: {g.single_sourced_products.join(', ')}.</p>
          </Section>

          <Section icon={PlugZap} iconColor="#dc2626" title="What if a supplier goes offline?"
            subtitle="Pick a supplier. Recovery time comes from the ML models; stock cover, other suppliers and backups soften the hit."
            right={(
              <select className="select-field" value={pick} onChange={(e) => run(e.target.value)} style={{ maxWidth: 280 }}>
                <option value="" disabled>Choose a supplier…</option>
                {suppliers.map((s) => <option key={s.name} value={s.name}>{s.name} · risk {s.risk_index}</option>)}
              </select>
            )}>
            {busy && <Spinner />}
            {!off && !busy && <p className="section-sub">Tip: click a supplier in the diagram above.</p>}
            {off && !busy && (
              <motion.div key={off.supplier} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                <FlowChain steps={off.chain.map((c, i) => ({ title: c, color: ['#dc2626', '#d97706', '#7c3aed', '#2563eb', '#0f172a'][i] }))} />
                <div className="evid" style={{ marginTop: 14 }}>
                  <Reveal i={0} className="evid-card hl"><b><AnimatedNumber value={off.revenue_at_risk_usd} format={fmtUsdShort} /></b><span>revenue at risk</span></Reveal>
                  <Reveal i={1} className="evid-card"><b><AnimatedNumber value={off.orders_at_risk} /></b><span>customer orders delayed</span></Reveal>
                  <Reveal i={2} className="evid-card"><b><AnimatedNumber value={off.shortage_days} format={(v) => `${v.toFixed(0)} d`} /></b><span>days actually short (after {off.inventory_days.toFixed(0)} d of stock)</span></Reveal>
                  <Reveal i={3} className="evid-card"><b>{off.full_recovery_days} d</b><span>to full recovery ({off.disruption_type.toLowerCase()}, worst case)</span></Reveal>
                </div>
                <div className="table-wrap" style={{ marginTop: 14 }}>
                  <table className="table">
                    <thead><tr><th>Product</th><th>Line</th><th>Customers</th><th>Share from this supplier</th><th>Other suppliers</th><th>Orders hit</th><th>Revenue at risk</th></tr></thead>
                    <tbody>
                      {off.affected.map((a) => (
                        <tr key={a.product}>
                          <td><b>{a.product}</b></td><td>{a.line}</td><td>{a.customer}</td>
                          <td className="num">{Math.round(a.share_from_supplier * 100)}%</td>
                          <td>{a.other_suppliers.length ? a.other_suppliers.join(', ') : <span className="pos">none (single source)</span>}</td>
                          <td className="num">{a.lost_orders.toLocaleString()}</td>
                          <td className="num">{fmtUsdShort(a.revenue_at_risk_usd)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="section-sub" style={{ marginTop: 8 }}><Factory size={13} /> Lines slowed: {off.lines.map((l) => `${l.line} (${fmtUsdShort(l.revenue_at_risk_usd)})`).join(' · ')}</p>
              </motion.div>
            )}
          </Section>
        </>
      )}
    </div>
  );
}

import React, { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import TabHome from './components/TabHome';
import TabEarlyWarning from './components/TabEarlyWarning';
import TabWorkflow from './components/TabWorkflow';
import TabSearch from './components/TabSearch';
import TabKnowledge from './components/TabKnowledge';
import TabPredict from './components/TabPredict';
import TabRootCause from './components/TabRootCause';
import TabDecision from './components/TabDecision';
import TabPortfolio from './components/TabPortfolio';
import TabNetwork from './components/TabNetwork';
import TabPrioritize from './components/TabPrioritize';
import TabIncidents from './components/TabIncidents';
import TabEval from './components/TabEval';
import TabAnalytics from './components/TabAnalytics';
import TabFallbackLab from './components/TabFallbackLab';
import { InfoDrawer, Sidebar, TopBar } from './components/layout';
import { fetchHealth, fetchMeta, fetchOverview } from './api';

// three.js is heavy: load the 3D control tower on demand
const ControlTower = lazy(() => import('./components/ControlTower'));

const readHash = () => (window.location.hash || '').replace('#', '') || 'home';

export default function App() {
  const [active, setActive] = useState(readHash);
  const [health, setHealth] = useState(null);
  const [meta, setMeta] = useState(null);
  const [visited, setVisited] = useState(() => new Set([readHash()]));
  const [portfolio, setPortfolio] = useState(null);       // last user-uploaded portfolio (scored)
  const [portfolioCsv, setPortfolioCsv] = useState(null); // ...and its CSV, shared with risk pages
  const [info, setInfo] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [badges, setBadges] = useState({});

  const open = useCallback((id) => {
    setActive(id);
    setVisited((v) => (v.has(id) ? v : new Set(v).add(id)));
    if (window.location.hash !== `#${id}`) window.history.replaceState(null, '', `#${id}`);
    window.scrollTo({ top: 0 });
  }, []);

  useEffect(() => {
    Promise.all([fetchHealth(), fetchMeta()]).then(([h, m]) => { setHealth(h); setMeta(m); }).catch(() => {});
    const t = setInterval(() => fetchHealth().then(setHealth).catch(() => {}), 10000);
    const onHash = () => open(readHash());
    window.addEventListener('hashchange', onHash);
    return () => { clearInterval(t); window.removeEventListener('hashchange', onHash); };
  }, [open]);

  // attention badges in the sidebar
  useEffect(() => {
    const load = () => fetchOverview().then((o) => setBadges({
      warning: (o.early_warning.Critical || 0) + (o.early_warning.High || 0) || null,
      incidents: o.sla_breached || o.incidents_open || null,
    })).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, []);

  const opts = meta?.options;
  const onScored = (r, csv) => { setPortfolio(r); setPortfolioCsv(csv); };
  const panes = {
    home: () => <TabHome onOpen={open} />,
    tower: () => (
      <Suspense fallback={<div className="ct-root"><div className="ct-loading">Loading 3D view…</div></div>}>
        <ControlTower portfolio={portfolio} />
      </Suspense>
    ),
    warning: () => <TabEarlyWarning portfolioCsv={portfolioCsv} />,
    workflow: () => <TabWorkflow options={opts} onOpen={open} />,
    search: () => <TabSearch options={opts} />,
    knowledge: () => <TabKnowledge />,
    predict: () => <TabPredict options={opts} />,
    rootcause: () => <TabRootCause options={opts} />,
    decision: () => <TabDecision options={opts} />,
    portfolio: () => <TabPortfolio onScored={onScored} />,
    network: () => <TabNetwork portfolioCsv={portfolioCsv} />,
    prioritize: () => <TabPrioritize options={opts} />,
    incidents: () => <TabIncidents onOpen={open} />,
    eval: () => <TabEval />,
    analytics: () => <TabAnalytics />,
    lab: () => <TabFallbackLab />,
  };
  const page = panes[active] ? active : 'home';

  return (
    <div className={`shell ${collapsed ? 'sb-collapsed' : ''}`}>
      <Sidebar active={page} onOpen={open} collapsed={collapsed} setCollapsed={setCollapsed}
        mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} badges={badges} />
      <div className="shell-main">
        <TopBar page={page} health={health} onInfo={() => setInfo(true)} onMenu={() => setMobileOpen(true)} onOpen={open} />
        <main className={`shell-content ${page === 'tower' ? 'full' : ''}`}>
          {Object.entries(panes).map(([id, render]) => visited.has(id) && (
            // visited pages stay mounted so their results survive navigation
            <motion.div key={id} hidden={page !== id} initial={false}
              animate={page === id ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }} transition={{ duration: 0.25 }}>
              {render()}
            </motion.div>
          ))}
        </main>
      </div>
      <InfoDrawer page={page} open={info} onClose={() => setInfo(false)} />
    </div>
  );
}

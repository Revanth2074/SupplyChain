import React, { Suspense, lazy, useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import TabWorkflow from './components/TabWorkflow';
import TabSearch from './components/TabSearch';
import TabPrioritize from './components/TabPrioritize';
import TabPredict from './components/TabPredict';
import TabAnalytics from './components/TabAnalytics';
import TabEval from './components/TabEval';
import TabPortfolio from './components/TabPortfolio';
import TabKnowledge from './components/TabKnowledge';

// three.js is heavy: load the 3D control tower on demand
const ControlTower = lazy(() => import('./components/ControlTower'));
import { fetchHealth, fetchMeta } from './api';

export default function App() {
  const [activeTab, setActiveTab] = useState('tower');
  const [health, setHealth] = useState(null);
  const [meta, setMeta] = useState(null);
  const [visited, setVisited] = useState(() => new Set(['tower']));
  const [portfolio, setPortfolio] = useState(null);

  const openTab = (id) => {
    setActiveTab(id);
    setVisited((v) => (v.has(id) ? v : new Set(v).add(id)));
  };

  useEffect(() => {
    const loadSystem = async () => {
      try {
        const [h, m] = await Promise.all([
          fetchHealth(),
          fetchMeta(),
        ]);
        setHealth(h);
        setMeta(m);
      } catch (err) {
        console.error('Initial load error:', err);
      }
    };
    loadSystem();

    const timer = setInterval(async () => {
      try {
        const h = await fetchHealth();
        setHealth(h);
      } catch {
        // silent health poll error
      }
    }, 10000);
    return () => clearInterval(timer);
  }, []);

  const opts = meta?.options;
  const panes = {
    tower: () => (
      <Suspense fallback={<div className="ct-root"><div className="ct-loading">Loading 3D view…</div></div>}>
        <ControlTower portfolio={portfolio} />
      </Suspense>
    ),
    workflow: () => <TabWorkflow options={opts} />,
    search: () => <TabSearch options={opts} />,
    prioritize: () => <TabPrioritize options={opts} />,
    predict: () => <TabPredict options={opts} />,
    portfolio: () => <TabPortfolio onScored={setPortfolio} />,
    knowledge: () => <TabKnowledge />,
    analytics: () => <TabAnalytics />,
    eval: () => <TabEval />,
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Navigation */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={openTab}
        health={health}
      />

      {/* Main Content Area */}
      <main style={{ flex: 1, paddingBottom: activeTab === 'tower' ? 0 : '3rem' }}>
        {Object.entries(panes).map(([id, render]) => visited.has(id) && (
          // visited tabs stay mounted so their results survive tab switches
          <div key={id} hidden={activeTab !== id}>{render()}</div>
        ))}
      </main>

      {/* Modern Footer */}
      {activeTab !== 'tower' && (
      <footer style={{ borderTop: '1px solid var(--border-subtle)', background: 'rgba(255, 255, 255, 0.9)', padding: '1.25rem 1.5rem', marginTop: 'auto' }}>
        <div style={{ maxWidth: '1440px', margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ color: 'var(--text-strong)', fontWeight: 600 }}>Project 9</span>
            <span>· AI-Powered Supply Chain Disruption Assistant with Synapt MCP</span>
          </div>

          <div style={{ display: 'flex', gap: '1.25rem' }}>
            <span>Knowledge Substrate: <strong style={{ color: '#4338ca' }}>beta.synapt.ai MCP</strong></span>
            <span>Dataset: <strong style={{ color: 'var(--text-strong)' }}>100,000 Disruption Cases</strong></span>
            <span>Evaluation: <strong style={{ color: '#059669' }}>DeepEval + LLM-as-Judge + Synapt quality</strong></span>
          </div>
        </div>
      </footer>
      )}
    </div>
  );
}

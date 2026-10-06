import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import TabWorkflow from './components/TabWorkflow';
import TabSearch from './components/TabSearch';
import TabPrioritize from './components/TabPrioritize';
import TabPredict from './components/TabPredict';
import TabAnalytics from './components/TabAnalytics';
import TabEval from './components/TabEval';
import { fetchHealth, fetchMeta } from './api';

export default function App() {
  const [activeTab, setActiveTab] = useState('workflow');
  const [health, setHealth] = useState(null);
  const [meta, setMeta] = useState(null);

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
      } catch (e) {
        // silent health poll error
      }
    }, 10000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Navigation */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        health={health}
      />

      {/* Main Content Area */}
      <main style={{ flex: 1, paddingBottom: '3rem' }}>
        {activeTab === 'workflow' && <TabWorkflow options={meta?.options} />}
        {activeTab === 'search' && <TabSearch options={meta?.options} />}
        {activeTab === 'prioritize' && <TabPrioritize options={meta?.options} />}
        {activeTab === 'predict' && <TabPredict options={meta?.options} />}
        {activeTab === 'analytics' && <TabAnalytics />}
        {activeTab === 'eval' && <TabEval />}
      </main>

      {/* Modern Footer */}
      <footer style={{ borderTop: '1px solid var(--border-subtle)', background: 'rgba(7, 9, 14, 0.95)', padding: '1.25rem 1.5rem', marginTop: 'auto' }}>
        <div style={{ maxWidth: '1440px', margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ color: '#fff', fontWeight: 600 }}>Project 9</span>
            <span>· AI-Powered Supply Chain Disruption Assistant with Synapt MCP</span>
          </div>

          <div style={{ display: 'flex', gap: '1.25rem' }}>
            <span>Knowledge Substrate: <strong style={{ color: '#a5b4fc' }}>beta.synapt.ai MCP</strong></span>
            <span>Dataset: <strong style={{ color: '#fff' }}>100,000 Disruption Cases</strong></span>
            <span>Evaluation: <strong style={{ color: '#6ee7b7' }}>DeepEval 4.x + LLM-as-Judge</strong></span>
          </div>
        </div>
      </footer>
    </div>
  );
}

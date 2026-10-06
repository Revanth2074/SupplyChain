import React from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Box,
  Briefcase,
  CheckCircle2,
  Network,
  Search,
  Sliders,
  Zap,
} from 'lucide-react';

export default function Navbar({ activeTab, setActiveTab, health }) {
  const tabs = [
    { id: 'tower', label: 'Control Tower', hint: '3D supplier network', icon: Box },
    { id: 'workflow', label: 'Cockpit', hint: '7-agent disruption workflow', icon: Zap },
    { id: 'search', label: 'Search & Ask', hint: 'Hybrid RAG search and Q&A', icon: Search },
    { id: 'prioritize', label: 'Triage', hint: 'P1-P4 prioritisation queue', icon: AlertTriangle },
    { id: 'predict', label: 'Simulator', hint: 'Predictions, ranges, XAI and what-if', icon: Sliders },
    { id: 'portfolio', label: 'Portfolio Risk', hint: 'Supplier resilience heatmap', icon: Briefcase },
    { id: 'knowledge', label: 'Knowledge Graph', hint: 'Synapt graph, playbooks and memory', icon: Network },
    { id: 'analytics', label: 'Analytics', hint: 'Insights across 100k cases', icon: BarChart3 },
    { id: 'eval', label: 'Quality', hint: 'DeepEval, Synapt quality and feedback', icon: CheckCircle2 },
  ];

  const synaptOk = health?.synapt?.configured && !health?.synapt?.circuit_open;
  const modelsOk = health?.models?.ready;
  const llmOk = health?.llm?.configured;

  return (
    <header className="header-nav">
      <div style={{ maxWidth: '1440px', margin: '0 auto', padding: '0.75rem 1.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
        {/* Logo & Title */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
          <div style={{
            width: '40px',
            height: '40px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, #2563eb 0%, #06b6d4 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 0 20px rgba(37, 99, 235, 0.4)'
          }}>
            <Activity size={22} color="#fff" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-strong)', letterSpacing: '-0.02em' }}>
                Synapt Disruption Assistant
              </span>
              <span className="badge badge-purple" style={{ fontSize: '0.68rem', padding: '0.1rem 0.45rem' }}>
                MCP SUBSTRATE
              </span>
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Supply-chain disruption response on the Synapt context substrate · 100k historical cases
            </p>
          </div>
        </div>

        {/* System Status Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
          <div className="glass-card" style={{ padding: '0.3rem 0.7rem', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.75rem' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: synaptOk ? '#10b981' : '#ef4444', display: 'inline-block', boxShadow: synaptOk ? '0 0 8px #10b981' : 'none' }} />
            <span style={{ color: 'var(--text-secondary)' }}>Synapt MCP:</span>
            <strong style={{ color: synaptOk ? '#059669' : '#dc2626' }}>
              {synaptOk ? 'Active' : 'Fallback'}
            </strong>
          </div>

          <div className="glass-card" style={{ padding: '0.3rem 0.7rem', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.75rem' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: modelsOk ? '#10b981' : '#f59e0b', display: 'inline-block' }} />
            <span style={{ color: 'var(--text-secondary)' }}>ML Models:</span>
            <strong style={{ color: 'var(--text-strong)' }}>{modelsOk ? 'Ready' : 'Training…'}</strong>
          </div>

          <div className="glass-card" style={{ padding: '0.3rem 0.7rem', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.75rem' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: llmOk ? '#2563eb' : '#f59e0b', display: 'inline-block' }} />
            <span style={{ color: 'var(--text-secondary)' }}>LLM:</span>
            <strong style={{ color: '#4338ca' }}>{health?.llm?.model || 'Active'}</strong>
          </div>
        </div>
      </div>

      {/* Tabs Bar */}
      <div style={{ maxWidth: '1440px', margin: '0 auto', padding: '0 1.5rem', display: 'flex', overflowX: 'auto', borderTop: '1px solid var(--border-subtle)' }}>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`nav-tab ${isActive ? 'active' : ''}`}
              title={tab.hint}
              aria-current={isActive ? 'page' : undefined}
            >
              <Icon size={16} />
              <span className="long">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </header>
  );
}

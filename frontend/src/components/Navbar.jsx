import React from 'react';
import {
  Activity,
  Cpu,
  Database,
  Layers,
  Search,
  Sliders,
  BarChart3,
  CheckCircle2,
  AlertTriangle,
  Zap
} from 'lucide-react';

export default function Navbar({ activeTab, setActiveTab, health }) {
  const tabs = [
    { id: 'workflow', label: 'Multi-Agent Cockpit', icon: Zap },
    { id: 'search', label: 'Hybrid RAG & Copilot', icon: Search },
    { id: 'prioritize', label: 'Prioritization Queue', icon: AlertTriangle },
    { id: 'predict', label: 'ML Simulator & XAI', icon: Sliders },
    { id: 'analytics', label: 'Macro Intelligence (100k)', icon: BarChart3 },
    { id: 'eval', label: 'DeepEval & Quality', icon: CheckCircle2 },
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
            background: 'linear-gradient(135deg, #6366f1 0%, #06b6d4 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 0 20px rgba(99, 102, 241, 0.4)'
          }}>
            <Activity size={22} color="#fff" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', fontWeight: 700, color: '#fff', letterSpacing: '-0.02em' }}>
                Synapt Disruption Assistant
              </span>
              <span className="badge badge-purple" style={{ fontSize: '0.68rem', padding: '0.1rem 0.45rem' }}>
                MCP SUBSTRATE
              </span>
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              AI-Powered Supply Chain Resilience · Multi-Agent RAG · DeepEval · 100k Historical Precedents
            </p>
          </div>
        </div>

        {/* System Status Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
          <div className="glass-card" style={{ padding: '0.3rem 0.7rem', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.75rem' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: synaptOk ? '#10b981' : '#ef4444', display: 'inline-block', boxShadow: synaptOk ? '0 0 8px #10b981' : 'none' }} />
            <span style={{ color: 'var(--text-secondary)' }}>Synapt MCP:</span>
            <strong style={{ color: synaptOk ? '#6ee7b7' : '#fca5a5' }}>
              {synaptOk ? 'Active' : 'Fallback'}
            </strong>
          </div>

          <div className="glass-card" style={{ padding: '0.3rem 0.7rem', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.75rem' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: modelsOk ? '#10b981' : '#f59e0b', display: 'inline-block' }} />
            <span style={{ color: 'var(--text-secondary)' }}>ML Models:</span>
            <strong style={{ color: '#fff' }}>{modelsOk ? '100k Trained' : 'Training...'}</strong>
          </div>

          <div className="glass-card" style={{ padding: '0.3rem 0.7rem', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.75rem' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: llmOk ? '#6366f1' : '#f59e0b', display: 'inline-block' }} />
            <span style={{ color: 'var(--text-secondary)' }}>LLM:</span>
            <strong style={{ color: '#a5b4fc' }}>{health?.llm?.model || 'Active'}</strong>
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
            >
              <Icon size={16} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>
    </header>
  );
}

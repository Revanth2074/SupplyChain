import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  Search,
  Filter,
  Sliders,
  HelpCircle,
  ExternalLink,
  Sparkles,
  Zap,
  Clock,
  Layers,
  Database,
  ArrowRight
} from 'lucide-react';
import { searchDisruptions, askCopilot } from '../api';

const COPILOT_PRESETS = [
  'Which response strategies worked fastest for port congestion in electronics?',
  'What is the recovery difference for cyber attacks with vs without backup suppliers?',
  'How does Tier 2 supplier disruption in aerospace impact revenue loss?',
  'What was the most effective strategy for natural disasters in Asia-Pacific?'
];

export default function TabSearch({ options }) {
  // Search state
  const [query, setQuery] = useState('cyber attack aerospace tier 2 no backup high severity');
  const [mode, setMode] = useState('hybrid');
  const [alpha, setAlpha] = useState(0.6);
  const [loading, setLoading] = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  const [searchError, setSearchError] = useState(null);

  // Filters state
  const [filters, setFilters] = useState({
    disruption_type: '',
    industry: '',
    supplier_tier: '',
    supplier_region: '',
    severity_min: '',
    has_backup_supplier: '',
  });

  // Copilot state
  const [copilotQ, setCopilotQ] = useState(COPILOT_PRESETS[0]);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [copilotAnswer, setCopilotAnswer] = useState(null);
  const [copilotError, setCopilotError] = useState(null);

  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setSearchError(null);

    const fPayload = {};
    if (filters.disruption_type) fPayload.disruption_type = [filters.disruption_type];
    if (filters.industry) fPayload.industry = [filters.industry];
    if (filters.supplier_tier) fPayload.supplier_tier = [Number(filters.supplier_tier)];
    if (filters.supplier_region) fPayload.supplier_region = [filters.supplier_region];
    if (filters.severity_min) fPayload.severity_min = Number(filters.severity_min);
    if (filters.has_backup_supplier !== '') fPayload.has_backup_supplier = filters.has_backup_supplier === 'true';

    try {
      const data = await searchDisruptions({
        query,
        mode,
        alpha,
        top_k: 12,
        filters: Object.keys(fPayload).length ? fPayload : null,
      });
      setSearchResults(data);
    } catch (err) {
      setSearchError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleAskCopilot = async (questionToAsk) => {
    const q = questionToAsk || copilotQ;
    if (!q.trim()) return;

    setCopilotLoading(true);
    setCopilotError(null);
    try {
      const resp = await askCopilot(q);
      setCopilotAnswer(resp);
    } catch (err) {
      setCopilotError(err.message || String(err));
    } finally {
      setCopilotLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: '1440px', margin: '0 auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Top Search Bar & Filters */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <h2 style={{ fontSize: '1.3rem', fontWeight: 700, marginBottom: '0.4rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Search size={22} color="#6366f1" />
          Hybrid RAG Historical Precedent Retrieval
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
          Combines dense semantic vectors from Synapt MCP Knowledge Substrate with sparse BM25 keyword matching via Reciprocal Rank Fusion (RRF).
        </p>

        <form onSubmit={handleSearch} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: '300px', position: 'relative' }}>
              <input
                className="input-field"
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search historical disruptions (e.g., strike in Europe, port congestion electronics)..."
                style={{ fontSize: '0.95rem', paddingLeft: '2.5rem' }}
              />
              <Search size={18} color="var(--text-muted)" style={{ position: 'absolute', left: '0.85rem', top: '50%', transform: 'translateY(-50%)' }} />
            </div>

            <select
              className="select-field"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              style={{ width: 'auto', minWidth: '180px' }}
            >
              <option value="hybrid">Mode: Hybrid (Synapt + BM25)</option>
              <option value="semantic">Mode: Synapt Semantic Only</option>
              <option value="keyword">Mode: BM25 Keyword Only</option>
            </select>

            <button type="submit" disabled={loading} className="btn btn-primary" style={{ padding: '0.6rem 1.4rem' }}>
              {loading ? (
                <div className="animate-spin" style={{ width: 16, height: 16, border: '2px solid #fff', borderTopColor: 'transparent', borderRadius: '50%' }} />
              ) : (
                <Search size={16} />
              )}
              Retrieve Precedents
            </button>
          </div>

          {/* RRF Alpha slider & Metadata Filters */}
          <div className="glass-card" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem', alignItems: 'center' }}>
            {mode === 'hybrid' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  <span>Semantic Weight</span>
                  <strong>{Math.round(alpha * 100)}%</strong>
                </div>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={alpha}
                  onChange={(e) => setAlpha(Number(e.target.value))}
                  style={{ accentColor: '#6366f1', cursor: 'pointer' }}
                />
              </div>
            )}

            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Disruption Type</label>
              <select
                className="select-field"
                value={filters.disruption_type}
                onChange={(e) => setFilters({ ...filters, disruption_type: e.target.value })}
              >
                <option value="">All Types</option>
                {options?.disruption_type?.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Industry</label>
              <select
                className="select-field"
                value={filters.industry}
                onChange={(e) => setFilters({ ...filters, industry: e.target.value })}
              >
                <option value="">All Industries</option>
                {options?.industry?.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Supplier Tier</label>
              <select
                className="select-field"
                value={filters.supplier_tier}
                onChange={(e) => setFilters({ ...filters, supplier_tier: e.target.value })}
              >
                <option value="">All Tiers</option>
                <option value="1">Tier 1</option>
                <option value="2">Tier 2</option>
                <option value="3">Tier 3</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Supplier Region</label>
              <select
                className="select-field"
                value={filters.supplier_region}
                onChange={(e) => setFilters({ ...filters, supplier_region: e.target.value })}
              >
                <option value="">All Regions</option>
                {options?.supplier_region?.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Backup Supplier</label>
              <select
                className="select-field"
                value={filters.has_backup_supplier}
                onChange={(e) => setFilters({ ...filters, has_backup_supplier: e.target.value })}
              >
                <option value="">Any</option>
                <option value="true">Has Backup</option>
                <option value="false">No Backup</option>
              </select>
            </div>
          </div>
        </form>

        {searchError && (
          <div style={{ marginTop: '1rem', color: '#fca5a5', fontSize: '0.85rem' }}>
            Search Error: {searchError}
          </div>
        )}
      </div>

      {/* Search Results Display */}
      {searchResults && (
        <div className="glass-panel" style={{ padding: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.5rem' }}>
            <div>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>
                Matched Disruption Precedents ({searchResults.count})
              </h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Semantic source: <strong style={{ color: '#a5b4fc' }}>{searchResults.semantic_source || 'local'}</strong> · Latency: {searchResults.latency_ms}ms
              </p>
            </div>
            {searchResults.fallback_reason && (
              <span className="badge badge-warning">
                Fallback: {searchResults.fallback_reason}
              </span>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1rem' }}>
            {searchResults.results?.map((c) => (
              <div key={c.disruption_id} className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#a5b4fc', fontSize: '0.95rem' }}>
                    {c.disruption_id}
                  </span>
                  <div style={{ display: 'flex', gap: '0.35rem' }}>
                    {c.from_synapt && <span className="badge badge-purple">Synapt MCP</span>}
                    <span className="badge badge-primary">RRF: {c.retrieval_score}</span>
                  </div>
                </div>

                <p style={{ fontSize: '0.825rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                  {c.text}
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', background: 'rgba(0,0,0,0.2)', padding: '0.5rem', borderRadius: '6px', fontSize: '0.72rem' }}>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Impact:</span>
                    <strong style={{ color: '#fcd34d', display: 'block' }}>{c.production_impact_pct}%</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Loss:</span>
                    <strong style={{ color: '#fff', display: 'block' }}>${Number(c.revenue_loss_usd).toLocaleString()}</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Recovery:</span>
                    <strong style={{ color: '#6ee7b7', display: 'block' }}>{c.full_recovery_days} days</strong>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.5rem', marginTop: 'auto' }}>
                  <span>Strategy: <strong style={{ color: '#fff' }}>{c.response_type}</strong></span>
                  <span>Supplier kept: <strong style={{ color: c.permanent_supplier_change ? '#fca5a5' : '#6ee7b7' }}>{c.permanent_supplier_change ? 'No (Replaced)' : 'Yes'}</strong></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Ask AI Copilot Section */}
      <div className="glass-panel" style={{ padding: '1.5rem', background: 'linear-gradient(180deg, rgba(6, 182, 212, 0.05) 0%, rgba(22, 28, 46, 0.7) 100%)' }}>
        <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '0.4rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Sparkles size={20} color="#06b6d4" />
          Ask AI Disruption Copilot (Synapt Knowledge Graph QA)
        </h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '1rem' }}>
          Ask natural-language questions directly against the Synapt knowledge graph and 100,000 historical disruption precedents.
        </p>

        {/* Preset prompts chips */}
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
          {COPILOT_PRESETS.map((p, idx) => (
            <button
              key={idx}
              onClick={() => { setCopilotQ(p); handleAskCopilot(p); }}
              className="btn btn-secondary"
              style={{ fontSize: '0.75rem', padding: '0.35rem 0.7rem' }}
            >
              {p}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <input
            className="input-field"
            type="text"
            value={copilotQ}
            onChange={(e) => setCopilotQ(e.target.value)}
            placeholder="Ask a question about response strategies, recovery times, supplier resilience..."
            style={{ fontSize: '0.95rem' }}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAskCopilot(); }}
          />
          <button
            onClick={() => handleAskCopilot()}
            disabled={copilotLoading || !copilotQ.trim()}
            className="btn btn-primary"
            style={{ padding: '0.6rem 1.4rem', whiteSpace: 'nowrap' }}
          >
            {copilotLoading ? (
              <div className="animate-spin" style={{ width: 16, height: 16, border: '2px solid #fff', borderTopColor: 'transparent', borderRadius: '50%' }} />
            ) : (
              <Sparkles size={16} />
            )}
            Ask Copilot
          </button>
        </div>

        {copilotError && (
          <div style={{ marginTop: '1rem', color: '#fca5a5', fontSize: '0.85rem' }}>
            Error: {copilotError}
          </div>
        )}

        {/* Copilot Answer Display */}
        {copilotAnswer && (
          <div className="glass-card" style={{ marginTop: '1.25rem', padding: '1.25rem', borderLeft: '4px solid #06b6d4' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
              <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#67e8f9' }}>
                GROUNDED SYNTHESIS ({copilotAnswer.method})
              </span>
              <span className="badge badge-cyan">
                Sources: {copilotAnswer.sources?.length} Historical Cases
              </span>
            </div>

            <div className="markdown-body">
              <ReactMarkdown>{copilotAnswer.answer}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

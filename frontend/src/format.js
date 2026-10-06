export const fmtUsd = (v) => (v == null || Number.isNaN(Number(v)) ? '—' : `$${Math.round(Number(v)).toLocaleString()}`);
export const fmtUsdShort = (v) => {
  const n = Number(v);
  if (v == null || Number.isNaN(n)) return '—';
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
};
export const fmtPct = (v, d = 0) => (v == null ? '—' : `${(Number(v) * 100).toFixed(d)}%`);

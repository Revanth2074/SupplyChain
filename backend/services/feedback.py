"""SQLite persistence for analyses + feedback, and the continuous-improvement
signals derived from feedback (strategy boosts, eval regression set, outcomes)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager

import pandas as pd

from config import settings

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
  id TEXT PRIMARY KEY, ts REAL, input TEXT, incident TEXT, report TEXT, judge TEXT,
  synapt_query_id TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY, ts REAL, analysis_id TEXT, rating INTEGER, helpful INTEGER,
  chosen_strategy TEXT, recommended_strategy TEXT, disruption_type TEXT, industry TEXT,
  comment TEXT, actual_production_impact_pct REAL, actual_revenue_loss_usd REAL,
  actual_full_recovery_days REAL, actual_partial_recovery_days REAL, synapt_sent INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS synapt_quality (
  ts REAL, source TEXT, question TEXT, query_id TEXT, quality TEXT
);
"""


@contextmanager
def conn():
    with _lock:
        c = sqlite3.connect(settings.FEEDBACK_DB)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def save_analysis(inp: dict, incident: dict, report: dict, judge: dict | None, qid: str | None) -> str:
    aid = uuid.uuid4().hex[:12]
    with conn() as c:
        c.execute("INSERT INTO analyses VALUES (?,?,?,?,?,?,?)",
                  (aid, time.time(), json.dumps(inp), json.dumps(incident), json.dumps(report, default=str),
                   json.dumps(judge or {}, default=str), qid))
    return aid


def get_analysis(aid: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM analyses WHERE id=?", (aid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    for k in ("input", "incident", "report", "judge"):
        d[k] = json.loads(d[k] or "{}")
    return d


def recent_analyses(limit: int = 20) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT id, ts, incident, judge FROM analyses ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        inc, j = json.loads(r["incident"] or "{}"), json.loads(r["judge"] or "{}")
        out.append({"id": r["id"], "ts": r["ts"], "disruption_type": inc.get("disruption_type"),
                    "industry": inc.get("industry"), "severity": inc.get("disruption_severity"),
                    "judge_score": j.get("overall_score")})
    return out


def add_feedback(fb: dict) -> str:
    fid = uuid.uuid4().hex[:12]
    cols = ["id", "ts", "analysis_id", "rating", "helpful", "chosen_strategy", "recommended_strategy",
            "disruption_type", "industry", "comment", "actual_production_impact_pct", "actual_revenue_loss_usd",
            "actual_full_recovery_days", "actual_partial_recovery_days", "synapt_sent"]
    vals = [fid, time.time()] + [fb.get(k) for k in cols[2:-1]] + [int(bool(fb.get("synapt_sent")))]
    with conn() as c:
        c.execute(f"INSERT INTO feedback ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
    return fid


def all_feedback() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM feedback ORDER BY ts DESC").fetchall()]


def strategy_boosts() -> dict[tuple[str, str], float]:
    """(disruption_type, strategy) -> multiplicative boost in [0.85, 1.15] from user ratings."""
    rows = all_feedback()
    agg: dict[tuple[str, str], list[float]] = {}
    for r in rows:
        strat = r.get("chosen_strategy") or r.get("recommended_strategy")
        if not strat or not r.get("disruption_type") or r.get("rating") is None:
            continue
        agg.setdefault((r["disruption_type"], strat), []).append((r["rating"] - 3) / 2)  # -1..1
    return {k: round(1 + 0.15 * (sum(v) / len(v)) * min(1, len(v) / 3), 4) for k, v in agg.items()}


def outcome_rows() -> pd.DataFrame:
    """Feedback with actual outcomes -> extra precedents for the estimator pool."""
    rows = []
    for r in all_feedback():
        if r.get("actual_full_recovery_days") is None or not r.get("analysis_id"):
            continue
        a = get_analysis(r["analysis_id"])
        if not a:
            continue
        inc = a["incident"]
        pred = (a["report"].get("impact") or {}).get("prediction", {})
        rows.append({
            "disruption_id": f"FB-{r['id']}",
            "disruption_type": inc.get("disruption_type"), "industry": inc.get("industry"),
            "supplier_tier": int(inc.get("supplier_tier") or 2), "supplier_region": inc.get("supplier_region"),
            "supplier_size": inc.get("supplier_size"), "has_backup_supplier": bool(inc.get("has_backup_supplier")),
            "disruption_severity": int(inc.get("disruption_severity") or 3),
            "response_type": r.get("chosen_strategy") or inc.get("response_type"),
            "response_time_days": int(inc.get("response_time_days") or 3),
            "production_impact_pct": r.get("actual_production_impact_pct") or pred.get("production_impact_pct"),
            "revenue_loss_usd": r.get("actual_revenue_loss_usd") or pred.get("revenue_loss_usd"),
            "full_recovery_days": r["actual_full_recovery_days"],
            "partial_recovery_days": r.get("actual_partial_recovery_days") or pred.get("partial_recovery_days"),
            "permanent_supplier_change": False,
        })
    return pd.DataFrame(rows)


def low_rated_cases(max_rating: int = 2) -> list[dict]:
    out = []
    for r in all_feedback():
        if r.get("rating") is not None and r["rating"] <= max_rating and r.get("analysis_id"):
            a = get_analysis(r["analysis_id"])
            if a:
                out.append({"input": a["input"].get("description") or "", "incident": a["incident"],
                            "comment": r.get("comment")})
    return out


def log_synapt_quality(source: str, question: str, query_id: str | None, quality: dict) -> None:
    with conn() as c:
        c.execute("INSERT INTO synapt_quality VALUES (?,?,?,?,?)",
                  (time.time(), source, (question or "")[:500], query_id, json.dumps(quality, default=str)))


def synapt_quality(limit: int = 200) -> dict:
    """Synapt's own per-answer quality signals (Retrieval Pass Card inputs), aggregated."""
    with conn() as c:
        rows = c.execute("SELECT * FROM synapt_quality ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    recs = [{**dict(r), "quality": json.loads(r["quality"] or "{}")} for r in rows]

    def avg(k):
        v = [r["quality"].get(k) for r in recs if isinstance(r["quality"].get(k), (int, float))]
        return round(sum(v) / len(v), 3) if v else None

    reasons: dict[str, int] = {}
    for r in recs:
        for why in r["quality"].get("degraded_reasons") or []:
            reasons[why] = reasons.get(why, 0) + 1
    return {
        "n": len(recs),
        "summary": {k: avg(k) for k in ("confidence", "knowledge_confidence", "procedural_confidence",
                                        "graph_confidence", "traversal_s", "avg_traversal_depth")} |
                   {"degraded_rate": round(sum(r["quality"].get("degraded", False) for r in recs) / len(recs), 3)
                    if recs else None, "degraded_reasons": reasons},
        "recent": [{"ts": r["ts"], "source": r["source"], "question": r["question"], "query_id": r["query_id"],
                    **{k: r["quality"].get(k) for k in ("confidence", "knowledge_confidence", "procedural_confidence",
                                                        "graph_confidence", "degraded", "degraded_reasons",
                                                        "stores_used", "traversal_s")}} for r in recs[:30]],
    }


def stats() -> dict:
    rows = all_feedback()
    n = len(rows)
    rated = [r["rating"] for r in rows if r.get("rating") is not None]
    helpful = [r["helpful"] for r in rows if r.get("helpful") is not None]
    by_strat: dict[str, list[int]] = {}
    for r in rows:
        s = r.get("chosen_strategy") or r.get("recommended_strategy")
        if s and r.get("rating") is not None:
            by_strat.setdefault(s, []).append(r["rating"])
    return {
        "total": n, "avg_rating": round(sum(rated) / len(rated), 2) if rated else None,
        "helpful_rate": round(sum(helpful) / len(helpful), 3) if helpful else None,
        "with_outcomes": sum(1 for r in rows if r.get("actual_full_recovery_days") is not None),
        "sent_to_synapt": sum(1 for r in rows if r.get("synapt_sent")),
        "by_strategy": {k: {"n": len(v), "avg_rating": round(sum(v) / len(v), 2)} for k, v in by_strat.items()},
        "boosts": [{"disruption_type": k[0], "strategy": k[1], "boost": v} for k, v in strategy_boosts().items()],
        "recent": rows[:15],
    }

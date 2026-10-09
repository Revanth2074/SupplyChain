"""Incident desk: SLA timers, escalation chains and action tracking.

An analysed disruption becomes an incident with a priority-based SLA. Recommended actions become
tracked tasks (owner, due date, status). Closing an action with the actual recovery time / loss
writes a feedback row, so real outcomes flow into model retraining (the learning loop)."""
from __future__ import annotations

import json
import time
import uuid

from agents.impact_analysis import priority
from agents.planner import strategy_table
from services import feedback
from agents.prediction import registry

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
  id TEXT PRIMARY KEY, ts REAL, title TEXT, analysis_id TEXT, priority TEXT, priority_score REAL,
  status TEXT, owner TEXT, incident TEXT, prediction TEXT, demo INTEGER DEFAULT 0, resolved_ts REAL
);
CREATE TABLE IF NOT EXISTS actions (
  id TEXT PRIMARY KEY, incident_id TEXT, ts REAL, title TEXT, owner TEXT, due_ts REAL, status TEXT,
  expected_recovery_days REAL, actual_recovery_days REAL, expected_loss_usd REAL, actual_loss_usd REAL,
  notes TEXT, done_ts REAL
);
"""

# priority -> SLA hours and escalation chain [(role, hours after opening)]
SLA = {
    "P1": {"hours": 4, "chain": [("Operations Manager", 0), ("Head of Supply Chain", 1), ("War room (VP Operations)", 2)]},
    "P2": {"hours": 24, "chain": [("Supplier Manager", 0), ("Operations Manager", 12)]},
    "P3": {"hours": 72, "chain": [("Category Buyer", 0), ("Supplier Manager", 48)]},
    "P4": {"hours": 168, "chain": [("Category Buyer", 0)]},
}
STATUSES = ["open", "investigating", "mitigating", "monitoring", "resolved"]
ACTION_STATUSES = ["proposed", "accepted", "in_progress", "done", "rejected"]


def init() -> None:
    with feedback.conn() as c:
        c.executescript(SCHEMA)


def _sla_view(inc: dict, now: float) -> dict:
    p = (inc["priority"] or "P3")[:2]
    cfg = SLA.get(p, SLA["P3"])
    age_h = (now - inc["ts"]) / 3600
    due = inc["ts"] + cfg["hours"] * 3600
    resolved = inc["status"] == "resolved"
    reached = [r for r, h in cfg["chain"] if age_h >= h] if not resolved else [cfg["chain"][0][0]]
    return {
        "sla_hours": cfg["hours"], "due_ts": due, "age_hours": round(age_h, 2),
        "remaining_hours": round((due - now) / 3600, 2),
        "breached": (not resolved) and now > due,
        "escalation_chain": [{"role": r, "after_hours": h, "notified": r in reached} for r, h in cfg["chain"]],
        "escalation_level": len(reached) - 1,
        "escalated": (not resolved) and len(reached) > 1,
    }


def _row(r) -> dict:
    d = dict(r)
    for k in ("incident", "prediction"):
        d[k] = json.loads(d[k] or "{}")
    return d


def list_incidents() -> list[dict]:
    now = time.time()
    with feedback.conn() as c:
        incs = [_row(r) for r in c.execute("SELECT * FROM incidents ORDER BY ts DESC").fetchall()]
        acts = [dict(r) for r in c.execute("SELECT * FROM actions ORDER BY due_ts").fetchall()]
    for i in incs:
        i.update(_sla_view(i, now))
        i["actions"] = [a for a in acts if a["incident_id"] == i["id"]]
        i["actions_done"] = sum(a["status"] == "done" for a in i["actions"])
    order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    incs.sort(key=lambda i: (i["status"] == "resolved", order.get(i["priority"][:2], 9), i["due_ts"]))
    return incs


def create(title: str, incident: dict, prediction: dict, priority: dict, actions: list[dict],
           analysis_id: str | None = None, ts: float | None = None, demo: bool = False) -> str:
    iid = uuid.uuid4().hex[:10]
    ts = ts or time.time()
    p = priority["level"][:2]
    with feedback.conn() as c:
        c.execute("INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (iid, ts, title, analysis_id, priority["level"], priority["score"], "open",
                   SLA[p]["chain"][0][0], json.dumps(incident), json.dumps(prediction), int(demo), None))
        for k, a in enumerate(actions):
            due = ts + float(a.get("due_hours", SLA[p]["hours"] * (k + 1))) * 3600
            c.execute("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (uuid.uuid4().hex[:10], iid, ts, a["title"], a.get("owner", SLA[p]["chain"][0][0]), due,
                       a.get("status", "proposed"), prediction.get("full_recovery_days"), None,
                       prediction.get("revenue_loss_usd"), None, a.get("notes", ""), None))
    return iid


def _timeframe_hours(tf: str, default: float) -> float:
    tf = (tf or "").lower()
    import re
    m = re.findall(r"(\d+(?:\.\d+)?)\s*(h|hour|d|day|w|week)", tf)
    if not m:
        return default
    n, unit = m[-1]
    return float(n) * (1 if unit.startswith("h") else 24 if unit.startswith("d") else 168)


def create_from_analysis(a: dict) -> str:
    """Open an incident from a saved multi-agent analysis (its plan's actions become tasks)."""
    rep = a["report"]
    inc = a["incident"]
    prio = rep["impact"]["priority"]
    pred = {**rep["impact"]["prediction"], **{"revenue_loss_usd": rep["recovery"]["predicted_revenue_loss"],
                                               "full_recovery_days": rep["recovery"]["predicted_full_days"]}}
    plan = rep.get("plan") or {}
    sla_h = SLA[prio["level"][:2]]["hours"]
    acts = [{"title": x["action"], "owner": x.get("owner") or "Operations", "due_hours": _timeframe_hours(x.get("timeframe"), sla_h)}
            for x in plan.get("immediate_actions", [])]
    acts += [{"title": t, "owner": "Supply Chain Planning", "due_hours": sla_h * 6} for t in plan.get("short_term_actions", [])[:2]]
    title = f"{inc.get('disruption_type')} · {inc.get('industry', '')} · {inc.get('supplier_region', '')}".strip(" ·")
    return create(title, inc, pred, prio, acts, analysis_id=a["id"])


def update_incident(iid: str, status: str | None = None, owner: str | None = None) -> None:
    with feedback.conn() as c:
        if status:
            if status not in STATUSES:
                raise ValueError(f"status must be one of {STATUSES}")
            c.execute("UPDATE incidents SET status=?, resolved_ts=? WHERE id=?",
                      (status, time.time() if status == "resolved" else None, iid))
        if owner:
            c.execute("UPDATE incidents SET owner=? WHERE id=?", (owner, iid))


def add_action(iid: str, title: str, owner: str, due_hours: float) -> str:
    aid = uuid.uuid4().hex[:10]
    with feedback.conn() as c:
        inc = c.execute("SELECT prediction FROM incidents WHERE id=?", (iid,)).fetchone()
        if not inc:
            raise ValueError("incident not found")
        pred = json.loads(inc["prediction"] or "{}")
        c.execute("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (aid, iid, time.time(), title, owner, time.time() + due_hours * 3600, "proposed",
                   pred.get("full_recovery_days"), None, pred.get("revenue_loss_usd"), None, "", None))
    return aid


def update_action(aid: str, status: str | None = None, actual_recovery_days: float | None = None,
                  actual_loss_usd: float | None = None, notes: str | None = None) -> dict:
    with feedback.conn() as c:
        a = c.execute("SELECT * FROM actions WHERE id=?", (aid,)).fetchone()
        if not a:
            raise ValueError("action not found")
        a = dict(a)
        if status:
            if status not in ACTION_STATUSES:
                raise ValueError(f"status must be one of {ACTION_STATUSES}")
            c.execute("UPDATE actions SET status=?, done_ts=? WHERE id=?", (status, time.time() if status == "done" else None, aid))
        if actual_recovery_days is not None:
            c.execute("UPDATE actions SET actual_recovery_days=? WHERE id=?", (actual_recovery_days, aid))
        if actual_loss_usd is not None:
            c.execute("UPDATE actions SET actual_loss_usd=? WHERE id=?", (actual_loss_usd, aid))
        if notes is not None:
            c.execute("UPDATE actions SET notes=? WHERE id=?", (notes[:500], aid))
        inc = c.execute("SELECT * FROM incidents WHERE id=?", (a["incident_id"],)).fetchone()
    learned = False
    if status == "done" and actual_recovery_days is not None and inc:
        inc = _row(inc)
        # close the loop: the real outcome becomes a labelled training row via the feedback store
        exp = a["expected_recovery_days"] or actual_recovery_days
        aid_link = inc.get("analysis_id")
        if not aid_link:
            # incidents opened without an analysis still need one so retraining can read the incident profile
            aid_link = feedback.save_analysis({"source": "incident", "incident_id": inc["id"]}, inc["incident"],
                                              {"impact": {"prediction": inc["prediction"]}}, None, None)
            with feedback.conn() as c:
                c.execute("UPDATE incidents SET analysis_id=? WHERE id=?", (aid_link, inc["id"]))
        err = abs(actual_recovery_days - exp) / max(exp, 1)
        feedback.add_feedback({
            "analysis_id": aid_link, "rating": 5 if err < 0.2 else 4 if err < 0.4 else 3 if err < 0.7 else 2,
            "helpful": err < 0.5, "chosen_strategy": inc["incident"].get("response_type"),
            "disruption_type": inc["incident"].get("disruption_type"), "industry": inc["incident"].get("industry"),
            "comment": f"Action '{a['title'][:80]}' closed. Expected {exp:.0f}d, actual {actual_recovery_days:.0f}d.",
            "actual_full_recovery_days": actual_recovery_days, "actual_revenue_loss_usd": actual_loss_usd,
        })
        learned = True
    return {"id": aid, "learned": learned}


DEMO = [
    ({"disruption_type": "Port Congestion", "industry": "Electronics", "supplier_region": "Asia-Pacific", "supplier_tier": 2,
      "has_backup_supplier": False, "disruption_severity": 5, "supplier_size": "Medium"},
     "Port congestion delaying Shenzhen MicroParts shipments", 5.5),
    ({"disruption_type": "Labor Strike", "industry": "Automotive", "supplier_region": "Europe", "supplier_tier": 1,
      "has_backup_supplier": True, "disruption_severity": 3, "supplier_size": "Large"},
     "Strike at Bavaria Brake Systems plant", 9),
    ({"disruption_type": "Factory Incident", "industry": "Pharmaceuticals", "supplier_region": "Europe", "supplier_tier": 2,
      "has_backup_supplier": False, "disruption_severity": 2, "supplier_size": "Small"},
     "Contamination finding at Basel Biologics", 30),
]


def seed_demo() -> int:
    """Three sample incidents of different priority and age so the desk is not empty on first use."""
    with feedback.conn() as c:
        if c.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]:
            return 0
    from agents.planner import fallback_plan  # template plan, no LLM call
    n = 0
    for inc, title, hours_ago in DEMO:
        pred = registry.predict(inc)
        prio = priority(inc, pred)
        strat = strategy_table(inc)["strategies"]
        plan = fallback_plan(inc, strat, [])
        acts = [{"title": x["action"], "owner": x["owner"], "due_hours": _timeframe_hours(x["timeframe"], 24)}
                for x in plan["immediate_actions"]]
        create(f"{title} (demo)", inc, {k: pred[k] for k in ("production_impact_pct", "revenue_loss_usd", "full_recovery_days")},
               prio, acts, ts=time.time() - hours_ago * 3600, demo=True)
        n += 1
    return n

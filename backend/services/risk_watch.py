"""Proactive risk: external disruption signals + supplier early-warning scores.

Signals come from three sources:
  * demo   - a small built-in set of SIMULATED alerts (clearly labelled) so the page works offline
  * manual - headlines a user pastes in; classified by the same classification agent as incidents
  * gdacs  - live natural-disaster alerts from the public GDACS feed (Global Disaster Alert and
             Coordination System, no API key), fetched on demand
Each signal is matched to the supplier portfolio by region (and industry where stated) and can be
pushed into the Synapt knowledge base so graph-RAG answers know about current events.

The early-warning score is a transparent heuristic (weights below), not a trained model: the
historical dataset has no time dimension, so "likelihood of a disruption" cannot be learnt from it.
Impact-if-disrupted comes from the ML models."""
from __future__ import annotations

import functools
import json
import logging
import time
import uuid
import xml.etree.ElementTree as ET

import httpx

from agents.classifier import classify
from services import faults
from services import feedback
from agents import synapt_tools as syn
from services.data_store import store
from agents.guardrails import validate_text

log = logging.getLogger("risk")

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
  id TEXT PRIMARY KEY, ts REAL, source TEXT, headline TEXT, detail TEXT, disruption_type TEXT,
  region TEXT, industry TEXT, severity INTEGER, confidence REAL, active INTEGER DEFAULT 1, synapt_sent INTEGER DEFAULT 0
);
"""

DEMO_SIGNALS = [
    ("Typhoon warning for South China Sea shipping lanes; carriers expect 3-5 day delays",
     "Natural Disaster", "Asia-Pacific", None, 4),
    ("Dockworkers' union announces 72-hour strike at major west-coast ports",
     "Labor Strike", "North America", None, 3),
    ("Ransomware campaign targeting European automotive tier-2 suppliers",
     "Cyber Attack", "Europe", "Automotive", 3),
    ("New export controls on advanced electronics components announced",
     "Geopolitical", "Asia-Pacific", "Electronics", 3),
    ("Red Sea transit disruptions extend Europe-Asia voyage times",
     "Geopolitical", "Africa/Middle East", None, 4),
    ("Berth congestion reported at a major South American container port",
     "Port Congestion", "South America", None, 2),
]

# rough lat/lon boxes -> dataset regions (for GDACS alerts)
def _region_of(lat: float, lon: float) -> str | None:
    if lat is None or lon is None:
        return None
    if lon < -30:
        return "North America" if lat > 12 else "South America"
    if -30 <= lon < 60:
        if lat > 35 and lon < 45:
            return "Europe"
        return "Africa/Middle East"
    return "Asia-Pacific"


def init() -> None:
    with feedback.conn() as c:
        c.executescript(SCHEMA)
        if not c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]:
            now = time.time()
            for i, (h, t, r, ind, sev) in enumerate(DEMO_SIGNALS):
                c.execute("INSERT INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          (uuid.uuid4().hex[:10], now - i * 3600 * 5, "demo", h, "Simulated demo alert.", t, r, ind,
                           sev, 0.9, 1, 0))


def list_signals(active_only: bool = False) -> list[dict]:
    q = "SELECT * FROM signals" + (" WHERE active=1" if active_only else "") + " ORDER BY ts DESC"
    with feedback.conn() as c:
        return [dict(r) for r in c.execute(q).fetchall()]


def set_active(sid: str, active: bool) -> None:
    with feedback.conn() as c:
        c.execute("UPDATE signals SET active=? WHERE id=?", (int(active), sid))


def _insert(source, headline, detail, dtype, region, industry, severity, confidence) -> dict:
    sid = uuid.uuid4().hex[:10]
    with feedback.conn() as c:
        if c.execute("SELECT 1 FROM signals WHERE headline=?", (headline,)).fetchone():
            return {"id": None, "duplicate": True}
        c.execute("INSERT INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (sid, time.time(), source, headline, detail, dtype, region, industry, severity, confidence, 1, 0))
    return {"id": sid}


def add_manual(headline: str, detail: str = "", send_to_synapt: bool = False) -> dict:
    v = validate_text(f"{headline}. {detail}".strip(), "signal")
    cls = classify(v["text"])
    f = cls["fields"]
    if not f.get("disruption_type"):
        raise ValueError("Could not tell what kind of disruption this headline describes")
    sev = int(f.get("disruption_severity") or 3)
    conf = float(cls.get("confidence", {}).get("disruption_type", 0.6))
    res = _insert("manual", headline.strip(), detail.strip(), f["disruption_type"], f.get("supplier_region"),
                  f.get("industry"), sev, conf)
    res.update(classification=f, method=cls.get("method"))
    if send_to_synapt and res.get("id"):
        res["synapt"] = push_to_synapt(res["id"])
    return res


def push_to_synapt(sid: str) -> dict:
    """Ingest the signal into the Synapt knowledge base as a dated alert document."""
    with feedback.conn() as c:
        r = c.execute("SELECT * FROM signals WHERE id=?", (sid,)).fetchone()
    if not r:
        raise ValueError("signal not found")
    r = dict(r)
    doc = (f"# External disruption alert\n\nDate: {time.strftime('%Y-%m-%d', time.localtime(r['ts']))}\n\n"
           f"{r['headline']}. Disruption type: {r['disruption_type']}. Region: {r['region'] or 'unspecified'}. "
           f"Industry: {r['industry'] or 'all'}. Severity {r['severity']} of 5. Source: {r['source']}.\n")
    try:
        out = syn.get_synapt_connector().call_tool("trident_ingest", {
            "provider_id": syn.settings.SYNAPT_PROVIDER_ID, "connector_type": "content", "content": doc,
            "filename": f"alert_{sid}.md", "document_type": "text", "extraction_mode": "precise", "has_ttl": True,
            "ttl_days": 30})
        with feedback.conn() as c:
            c.execute("UPDATE signals SET synapt_sent=1 WHERE id=?", (sid,))
        return {"sent": True, "response": str(out)[:200]}
    except Exception as e:  # noqa: BLE001
        return {"sent": False, "error": str(e)[:200]}


GDACS_URL = "https://www.gdacs.org/xml/rss.xml"
GDACS_TYPES = {"EQ": "earthquake", "TC": "tropical cyclone", "FL": "flood", "VO": "volcano", "DR": "drought", "WF": "wildfire"}


def fetch_gdacs(limit: int = 15) -> dict:
    """Pull current orange/red natural-disaster alerts from GDACS (public RSS)."""
    faults.check("live_feed")
    r = httpx.get(GDACS_URL, timeout=20, follow_redirects=True, headers={"User-Agent": "supplychain-assistant/1.0"})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns = {"gdacs": "http://www.gdacs.org", "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#"}
    added, seen = [], 0
    for item in root.iter("item"):
        seen += 1
        level = (item.findtext("gdacs:alertlevel", default="", namespaces=ns) or "").capitalize()
        if level not in ("Orange", "Red"):
            continue
        title = (item.findtext("title") or "").strip()
        try:
            lat = float(item.findtext("geo:Point/geo:lat", namespaces=ns) or item.findtext("geo:lat", namespaces=ns))
            lon = float(item.findtext("geo:Point/geo:long", namespaces=ns) or item.findtext("geo:long", namespaces=ns))
        except (TypeError, ValueError):
            lat = lon = None
        etype = item.findtext("gdacs:eventtype", default="", namespaces=ns)
        country = item.findtext("gdacs:country", default="", namespaces=ns)
        sev = 5 if level == "Red" else 3
        res = _insert("gdacs", title, f"{GDACS_TYPES.get(etype, etype)} alert ({level}) {country}".strip(),
                      "Natural Disaster", _region_of(lat, lon), None, sev, 0.95)
        if res.get("id"):
            added.append(title)
        if len(added) >= limit:
            break
    return {"checked": seen, "added": len(added), "headlines": added}


@functools.lru_cache(maxsize=16)
def _playbook(dtype: str) -> tuple:
    try:
        p = syn.procedure_for(dtype)
        return (p["name"], tuple(s["text"] for s in p["steps"])) if p else (None, ())
    except Exception as e:  # noqa: BLE001
        log.info("playbook lookup failed: %s", e)
        return (None, ())


def _hits(sig: dict, s: dict) -> bool:
    return (not sig.get("region") or sig["region"] == s["supplier_region"]) and \
        (not sig.get("industry") or sig["industry"] == s["industry"])


def signal_impacts(scored: dict, signals: list[dict]) -> list[dict]:
    """Which of my suppliers each signal touches, the expected exposure, and the Synapt playbook to follow."""
    df = store.df
    out = []
    # fetch each disruption type's Synapt playbook once, in parallel (results are cached afterwards)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(_playbook, sorted({sig["disruption_type"] for sig in signals})))
    for sig in signals:
        hit = [s for s in scored["suppliers"] if _hits(sig, s)]
        t = sig["disruption_type"]
        rows = [next((b for b in s["by_type"] if b["disruption_type"] == t), None) for s in hit]
        exposure = sum(b["revenue_loss_usd"] for b in rows if b)
        hist = df[(df["disruption_type"] == t) & ((df["supplier_region"] == sig["region"]) if sig.get("region") else True)]
        name, steps = _playbook(t)
        out.append({
            **sig, "affected": [{"supplier_name": s["supplier_name"], "industry": s["industry"],
                                 "risk_probability": b["risk_probability"] if b else None,
                                 "revenue_loss_usd": b["revenue_loss_usd"] if b else None,
                                 "full_recovery_days": b["full_recovery_days"] if b else None,
                                 "has_backup_supplier": s["has_backup_supplier"]} for s, b in zip(hit, rows)],
            "exposure_usd": round(exposure, 0),
            "history": {"cases": int(len(hist)), "avg_full_recovery": round(float(hist["full_recovery_days"].mean()), 1) if len(hist) else None,
                        "avg_impact": round(float(hist["production_impact_pct"].mean()), 1) if len(hist) else None},
            "playbook": {"name": name, "steps": list(steps)[:7], "source": "synapt" if name else None},
        })
    return out


# ---------------------------------------------------------------- early warning
WEIGHTS = {"signals": 0.30, "delivery": 0.20, "incidents": 0.15, "buffer": 0.15, "dependency": 0.10, "regional": 0.10}


@functools.lru_cache(maxsize=1)
def _regional_rate() -> dict:
    """How over-represented each (region, industry) pair is in the disruption history (1.0 = average)."""
    df = store.df
    obs = df.groupby(["supplier_region", "industry"]).size()
    out = {}
    for (reg, ind), n in obs.items():
        e = (df["supplier_region"].eq(reg).mean() * df["industry"].eq(ind).mean()) * len(df)
        out[(reg, ind)] = round(float(n / e), 3) if e else 1.0
    return out


def early_warning(scored: dict, signals: list[dict]) -> dict:
    rate = _regional_rate()
    sev_of = lambda s: [sig for sig in signals if _hits(sig, s)]
    suppliers = []
    for s in scored["suppliers"]:
        mine = sev_of(s)
        comp = {
            "signals": min(1.0, sum(sig["severity"] / 5 * (sig.get("confidence") or 0.7) for sig in mine) / 1.5),
            "delivery": min(1.0, max(0.0, (0.98 - float(s["on_time_rate"])) / 0.15)),
            "incidents": min(1.0, float(s["recent_disruptions"]) / 4),
            "buffer": 1 - min(1.0, float(s["inventory_days"]) / 30),
            "dependency": min(1.0, float(s["dependency_pct"]) * (1.0 if not s["has_backup_supplier"] else 0.5)),
            "regional": min(1.0, max(0.0, (rate.get((s["supplier_region"], s["industry"]), 1.0) - 0.8) / 0.4)),
        }
        likelihood = sum(WEIGHTS[k] * v for k, v in comp.items())
        base_likelihood = likelihood - WEIGHTS["signals"] * comp["signals"]
        impact = float(s["expected_risk_probability"])
        score = round(100 * (0.6 * likelihood + 0.4 * impact), 1)
        base = round(100 * (0.6 * base_likelihood + 0.4 * impact), 1)
        level = "Critical" if score >= 70 else "High" if score >= 55 else "Elevated" if score >= 40 else "Normal"
        prob = round(min(0.95, 0.05 + 0.8 * likelihood), 3)
        drivers = []
        if comp["signals"] > 0:
            drivers.append({"key": "signals", "text": f"{len(mine)} active external alert(s): " + "; ".join(sig["headline"][:60] for sig in mine[:2]), "weight": comp["signals"] * WEIGHTS["signals"]})
        if comp["delivery"] > 0.2:
            drivers.append({"key": "delivery", "text": f"On-time delivery {s['on_time_rate'] * 100:.0f}% (target 98%)", "weight": comp["delivery"] * WEIGHTS["delivery"]})
        if comp["incidents"] > 0:
            drivers.append({"key": "incidents", "text": f"{int(s['recent_disruptions'])} disruption(s) in the last 12 months", "weight": comp["incidents"] * WEIGHTS["incidents"]})
        if comp["buffer"] > 0.4:
            drivers.append({"key": "buffer", "text": f"Only {s['inventory_days']:.0f} days of stock cover", "weight": comp["buffer"] * WEIGHTS["buffer"]})
        if comp["dependency"] > 0.5:
            drivers.append({"key": "dependency", "text": f"{s['dependency_pct'] * 100:.0f}% of volume from this supplier" + ("" if s["has_backup_supplier"] else ", no backup"), "weight": comp["dependency"] * WEIGHTS["dependency"]})
        if comp["regional"] > 0.3:
            drivers.append({"key": "regional", "text": f"{s['industry']} suppliers in {s['supplier_region']} are disrupted more often than average", "weight": comp["regional"] * WEIGHTS["regional"]})
        drivers.sort(key=lambda d: -d["weight"])

        # preventive actions: concrete, using the rest of the portfolio where possible
        actions = []
        if not s["has_backup_supplier"]:
            alts = sorted([o for o in scored["suppliers"] if o["supplier_name"] != s["supplier_name"]
                           and o["industry"] == s["industry"] and o["supplier_region"] != s["supplier_region"]],
                          key=lambda o: o["risk_index"])
            actions.append(f"Qualify {alts[0]['supplier_name']} ({alts[0]['supplier_region']}, risk {alts[0]['risk_index']}) as a backup"
                           if alts else f"Qualify a second {s['industry'].lower()} supplier outside {s['supplier_region']} as a backup")
        partial = next((b["full_recovery_days"] for b in s["by_type"] if b["disruption_type"] == s["worst_case"]["disruption_type"]), None)
        if s["inventory_days"] < 21:
            actions.append(f"Raise safety stock from {s['inventory_days']:.0f} to {max(21, min(45, round((partial or 40) / 3)))} days of cover")
        if mine:
            t = mine[0]["disruption_type"]
            actions.append(f"Pre-book alternative capacity now: follow the '{t}' playbook before the alert hits")
        if s["on_time_rate"] < 0.92:
            actions.append("Open a supplier performance review and agree a recovery plan")
        if s["supplier_tier"] >= 2:
            actions.append("Map this supplier's own sub-tier suppliers for early warning")
        suppliers.append({
            "supplier_name": s["supplier_name"], "industry": s["industry"], "supplier_region": s["supplier_region"],
            "supplier_tier": s["supplier_tier"], "has_backup_supplier": s["has_backup_supplier"],
            "score": score, "baseline_score": base, "trend": round(score - base, 1), "level": level,
            "probability_90d": prob, "impact_if_disrupted": round(impact, 3), "components": {k: round(v, 3) for k, v in comp.items()},
            "drivers": drivers[:5], "actions": actions[:4], "signals": [sig["id"] for sig in mine],
            "worst_case": s["worst_case"], "risk_index": s["risk_index"],
        })
    suppliers.sort(key=lambda x: -x["score"])
    levels = {lv: sum(1 for x in suppliers if x["level"] == lv) for lv in ("Critical", "High", "Elevated", "Normal")}
    return {"weights": WEIGHTS, "levels": levels, "suppliers": suppliers,
            "method": "Transparent heuristic: 60% likelihood signals (weights shown) + 40% ML impact-if-disrupted."}

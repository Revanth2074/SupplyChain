"""Domain analytics: classification agent, prioritization, strategy
recommendation (historical + counterfactual ML), and factor insights."""
from __future__ import annotations

import functools
import logging
import math
import re

import numpy as np
import pandas as pd

from . import feedback, llm
from .data_store import store
from .ml_models import registry

log = logging.getLogger("analysis")

# ---------------------------------------------------------------- classify
KEYWORDS = {
    "disruption_type": {
        "Cyber Attack": ["cyber", "ransomware", "hack", "malware", "breach", "ddos", "phishing", "it outage"],
        "Port Congestion": ["port", "congestion", "container", "vessel", "shipping", "berth", "customs", "freight"],
        "Labor Strike": ["strike", "union", "labor", "labour", "walkout", "workers", "industrial action"],
        "Natural Disaster": ["earthquake", "flood", "hurricane", "typhoon", "tsunami", "wildfire", "storm",
                             "cyclone", "drought", "natural disaster", "volcano"],
        "Geopolitical": ["sanction", "tariff", "war", "conflict", "embargo", "geopolitical", "export ban",
                         "trade restriction", "political", "border"],
        "Factory Incident": ["fire", "explosion", "factory", "plant", "equipment failure", "machine",
                             "contamination", "accident", "breakdown", "quality"],
    },
    "supplier_region": {
        "Asia-Pacific": ["asia", "china", "japan", "korea", "taiwan", "india", "vietnam", "apac", "singapore",
                         "malaysia", "thailand", "australia", "indonesia", "philippines"],
        "Europe": ["europe", "germany", "france", "italy", "uk", "spain", "poland", "netherlands", "eu "],
        "North America": ["north america", "usa", "united states", "us ", "canada", "mexico", "texas", "california"],
        "Latin America": ["latin", "brazil", "argentina", "chile", "colombia", "peru", "south america"],
        "Africa/Middle East": ["africa", "middle east", "uae", "saudi", "egypt", "nigeria", "israel", "turkey",
                               "red sea", "suez"],
    },
    "supplier_size": {"Large": ["large", "major", "big", "global supplier"], "Small": ["small", "boutique", "niche"],
                      "Medium": ["medium", "mid-size", "midsize"]},
}


def _rule_classify(text: str, opts: dict) -> dict:
    low = f" {text.lower()} "
    out, conf = {}, {}
    for field, mp in KEYWORDS.items():
        best, hits = None, 0
        for label, kws in mp.items():
            h = sum(1 for k in kws if k in low)
            if h > hits and label in opts.get(field, [label]):
                best, hits = label, h
        if best:
            out[field], conf[field] = best, min(0.9, 0.5 + 0.15 * hits)
    for ind in opts.get("industry", []):
        if ind.lower().rstrip("s") in low:
            out["industry"], conf["industry"] = ind, 0.8
            break
    m = re.search(r"tier[\s-]*([123])", low)
    if m:
        out["supplier_tier"], conf["supplier_tier"] = int(m.group(1)), 0.9
    m = re.search(r"severity[^0-9]{0,12}([1-5])", low)
    if m:
        out["disruption_severity"], conf["disruption_severity"] = int(m.group(1)), 0.9
    else:
        sev = 4 if any(w in low for w in ("severe", "critical", "major", "catastroph", "shutdown")) else \
            2 if any(w in low for w in ("minor", "small", "slight", "limited")) else 3
        out["disruption_severity"], conf["disruption_severity"] = sev, 0.5
    if "no backup" in low or "single source" in low or "sole supplier" in low or "without backup" in low:
        out["has_backup_supplier"], conf["has_backup_supplier"] = False, 0.85
    elif "backup" in low or "dual source" in low or "alternate supplier" in low:
        out["has_backup_supplier"], conf["has_backup_supplier"] = True, 0.7
    return {"fields": out, "confidence": conf, "method": "rules"}


CLASSIFY_SYS = """You are a supply-chain disruption classification agent.
Extract structured attributes from an incident description. Only use the allowed values.
If a value is not stated or cannot be reasonably inferred, use null.
Return JSON: {"disruption_type":..,"industry":..,"supplier_tier":1|2|3|null,"supplier_region":..,
"supplier_size":..,"has_backup_supplier":true|false|null,"disruption_severity":1-5,
"response_type":..|null,"response_time_days":int|null,
"confidence":{field:0..1},"rationale":"one sentence","category_summary":"short label"}"""


def classify(text: str) -> dict:
    opts = store.options()
    rules = _rule_classify(text, opts)
    if not llm.available():
        return {**rules, "rationale": "Keyword/rule-based classification (LLM unavailable)."}
    try:
        allowed = {k: v for k, v in opts.items() if k != "disruption_severity"}
        j = llm.chat_json(CLASSIFY_SYS, f"Allowed values: {allowed}\n\nIncident description:\n{text}")
        fields = {}
        for k in ("disruption_type", "industry", "supplier_region", "supplier_size", "response_type"):
            v = j.get(k)
            if v in opts.get(k, []):
                fields[k] = v
        for k in ("supplier_tier", "disruption_severity", "response_time_days"):
            if j.get(k) is not None:
                try:
                    fields[k] = int(j[k])
                except (TypeError, ValueError):
                    pass
        if isinstance(j.get("has_backup_supplier"), bool):
            fields["has_backup_supplier"] = j["has_backup_supplier"]
        for k, v in rules["fields"].items():  # fill gaps from rules
            fields.setdefault(k, v)
        conf = {**rules["confidence"], **{k: float(v) for k, v in (j.get("confidence") or {}).items()
                                          if isinstance(v, (int, float))}}
        return {"fields": fields, "confidence": conf, "method": "llm+rules",
                "rationale": j.get("rationale", ""), "category_summary": j.get("category_summary", "")}
    except Exception as e:  # noqa: BLE001
        log.warning("LLM classify failed: %s", e)
        return {**rules, "rationale": f"Rule-based fallback ({e.__class__.__name__})."}


# ---------------------------------------------------------------- prioritize
LOSS_CAP = 50_000_000


def priority(inc: dict, pred: dict | None = None) -> dict:
    """Weighted priority from severity, production impact and financial loss."""
    pred = pred or {}
    sev = int(inc.get("disruption_severity") or 3)
    impact = inc.get("production_impact_pct")
    impact = float(impact if impact is not None else pred.get("production_impact_pct", 30))
    loss = inc.get("revenue_loss_usd")
    loss = float(loss if loss is not None else pred.get("revenue_loss_usd", 1e6))
    s_sev = (sev - 1) / 4
    s_imp = min(impact, 100) / 100
    s_loss = min(1.0, math.log10(max(loss, 1e4) / 1e4) / math.log10(LOSS_CAP / 1e4))
    risk = pred.get("risk_probability")
    score = 0.35 * s_sev + 0.30 * s_imp + 0.25 * s_loss + 0.10 * (risk if risk is not None else s_sev)
    score = round(score * 100, 1)
    level = "P1 - Critical" if score >= 70 else "P2 - High" if score >= 50 else "P3 - Medium" if score >= 30 else "P4 - Low"
    sla = {"P1": "Mobilise war-room within 4h", "P2": "Response plan within 24h",
           "P3": "Review within 3 days", "P4": "Monitor weekly"}[level[:2]]
    return {"score": score, "level": level, "action_sla": sla,
            "components": {"severity": round(s_sev * 100, 1), "production_impact": round(s_imp * 100, 1),
                           "financial_loss": round(s_loss * 100, 1),
                           "risk": round((risk if risk is not None else s_sev) * 100, 1)},
            "inputs": {"severity": sev, "production_impact_pct": impact, "revenue_loss_usd": loss,
                       "estimated": {"impact": inc.get("production_impact_pct") is None,
                                     "loss": inc.get("revenue_loss_usd") is None}}}


# ---------------------------------------------------------------- recommend
def strategy_table(inc: dict) -> dict:
    """Historical effectiveness of each response strategy for comparable disruptions +
    ML counterfactual predictions for this incident under each strategy."""
    df = store.df
    scope = {"disruption_type": inc.get("disruption_type")}
    sub = df[df["disruption_type"] == inc["disruption_type"]] if inc.get("disruption_type") else df
    scope_desc = [f"type={inc.get('disruption_type')}"] if inc.get("disruption_type") else ["all"]
    if inc.get("industry"):
        s2 = sub[sub["industry"] == inc["industry"]]
        if len(s2) >= 300:
            sub, scope["industry"] = s2, inc["industry"]
            scope_desc.append(f"industry={inc['industry']}")
    if inc.get("has_backup_supplier") is not None:
        s3 = sub[sub["has_backup_supplier"] == bool(inc["has_backup_supplier"])]
        if len(s3) >= 200:
            sub = s3
            scope_desc.append(f"backup={bool(inc['has_backup_supplier'])}")
    if inc.get("disruption_severity"):
        sv = int(inc["disruption_severity"])
        s4 = sub[sub["disruption_severity"].between(sv - 1, sv + 1)]
        if len(s4) >= 150:
            sub = s4
            scope_desc.append(f"severity={sv}±1")

    g = sub.groupby("response_type").agg(
        cases=("disruption_id", "count"), avg_full_recovery=("full_recovery_days", "mean"),
        median_full_recovery=("full_recovery_days", "median"), avg_partial_recovery=("partial_recovery_days", "mean"),
        avg_revenue_loss=("revenue_loss_usd", "mean"), avg_impact=("production_impact_pct", "mean"),
        supplier_change_rate=("permanent_supplier_change", "mean"), avg_response_time=("response_time_days", "mean"),
    ).reset_index()
    boosts = feedback.strategy_boosts()
    rows = []
    for _, r in g.iterrows():
        cf_inc = {**inc, "response_type": r["response_type"]}
        p = registry.predict(cf_inc) if registry.ready else {}
        rows.append({
            "strategy": r["response_type"], "cases": int(r["cases"]),
            "avg_full_recovery": round(r["avg_full_recovery"], 1), "median_full_recovery": float(r["median_full_recovery"]),
            "avg_partial_recovery": round(r["avg_partial_recovery"], 1), "avg_revenue_loss": round(r["avg_revenue_loss"], 0),
            "avg_impact": round(r["avg_impact"], 1), "supplier_change_rate": round(r["supplier_change_rate"], 3),
            "pred_full_recovery": p.get("full_recovery_days"), "pred_partial_recovery": p.get("partial_recovery_days"),
            "pred_revenue_loss": p.get("revenue_loss_usd"),
            "feedback_boost": boosts.get((inc.get("disruption_type"), r["response_type"]), 1.0),
        })
    if not rows:
        return {"scope": scope_desc, "n": 0, "strategies": []}
    t = pd.DataFrame(rows)

    def inv_norm(s):
        s = s.astype(float)
        return 1 - (s - s.min()) / (s.max() - s.min()) if s.max() > s.min() else pd.Series(1.0, index=s.index)

    rec = t["pred_full_recovery"].fillna(t["avg_full_recovery"])
    loss = t["pred_revenue_loss"].fillna(t["avg_revenue_loss"])
    conf = np.clip(np.log10(t["cases"] + 1) / 3.5, 0.3, 1.0)
    t["effectiveness"] = ((0.35 * inv_norm(t["avg_full_recovery"]) + 0.25 * inv_norm(rec) +
                           0.25 * inv_norm(loss) + 0.15 * inv_norm(t["avg_partial_recovery"])) * conf *
                          t["feedback_boost"] * 100).round(1)
    t = t.sort_values("effectiveness", ascending=False)
    return {"scope": scope_desc, "n": int(len(sub)), "strategies": t.replace({np.nan: None}).to_dict("records")}


# ---------------------------------------------------------------- insights
@functools.lru_cache(maxsize=1)
def insights() -> dict:
    df = store.df
    metrics = {"avg_impact": ("production_impact_pct", "mean"), "avg_loss": ("revenue_loss_usd", "mean"),
               "avg_recovery": ("full_recovery_days", "mean"), "cases": ("disruption_id", "count"),
               "change_rate": ("permanent_supplier_change", "mean")}

    def grp(col):
        g = df.groupby(col).agg(**metrics).reset_index().rename(columns={col: "key"})
        g["key"] = g["key"].astype(str)
        return g.round(3).to_dict("records")

    num = df[["disruption_severity", "supplier_tier", "response_time_days", "production_impact_pct",
              "revenue_loss_usd", "partial_recovery_days", "full_recovery_days"]].copy()
    num["has_backup_supplier"] = df["has_backup_supplier"].astype(int)
    corr = num.corr().round(3)
    return {
        "totals": {"cases": int(len(df)), "avg_impact": round(float(df["production_impact_pct"].mean()), 1),
                   "avg_loss": round(float(df["revenue_loss_usd"].mean()), 0),
                   "total_loss": round(float(df["revenue_loss_usd"].sum()), 0),
                   "avg_recovery": round(float(df["full_recovery_days"].mean()), 1),
                   "backup_rate": round(float(df["has_backup_supplier"].mean()), 3),
                   "change_rate": round(float(df["permanent_supplier_change"].mean()), 3)},
        "by_type": grp("disruption_type"), "by_severity": grp("disruption_severity"),
        "by_industry": grp("industry"), "by_region": grp("supplier_region"), "by_tier": grp("supplier_tier"),
        "by_backup": grp("has_backup_supplier"), "by_response": grp("response_type"), "by_size": grp("supplier_size"),
        "correlation": {"columns": list(corr.columns), "matrix": corr.values.tolist()},
    }

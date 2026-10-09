"""
Disruption Classification Agent (Intake).
Turns a free-text incident description into structured dataset fields (type, industry,
tier, region, size, severity, backup) with per-field confidence: keyword rules constrained to the
dataset vocabulary (no LLM at runtime; the external LLM is used only as the offline judge).
"""

from __future__ import annotations

import logging
import re

from services.data_store import store

log = logging.getLogger("classifier")

KEYWORDS = {
    "disruption_type": {
        "Cyber Attack": ["cyber", "ransomware", "hack", "malware", "breach", "ddos", "phishing", "it outage"],
        "Port Congestion": [" port", "congestion", "container", "vessel", "shipping", "berth", "customs", "freight"],
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
        "South America": ["latin", "brazil", "argentina", "chile", "colombia", "peru", "south america"],
        "Africa/Middle East": ["africa", "middle east", "uae", "saudi", "egypt", "nigeria", "israel", "turkey",
                               "red sea", "suez"],
    },
    "supplier_size": {"Large": ["large", "major", "big", "global supplier"], "Small": ["small", "boutique", "niche"],
                      "Medium": ["medium", "mid-size", "midsize"]},
}


INDUSTRY_HINTS = {  # checked before the generic industry-name match
    "Aerospace": ["avionics", "aerospace", "aircraft", "titanium forging"],
    "Pharmaceuticals": ["pharma", "active pharmaceutical", "drug", "vaccine"],
    "Automotive": ["automotive", "brake", "vehicle", "car parts"],
    "Consumer Goods": ["consumer goods", "food packaging", "retail"],
    "Electronics": ["semiconductor", "circuit board", "electronic"],
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
    for ind, kws in INDUSTRY_HINTS.items():
        if ind in opts.get("industry", [ind]) and any(k in low for k in kws):
            out["industry"], conf["industry"] = ind, 0.8
            break
    m = re.search(r"tier[\s-]*([1234])", low)
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


def classify(text: str) -> dict:
    """Rule-based classification constrained to the dataset vocabulary."""
    rules = _rule_classify(text, store.options())
    found = ", ".join(sorted(rules["fields"])) or "nothing"
    return {**rules, "rationale": f"Keyword rules matched: {found}."}


def classifier_node(state: dict) -> dict:
    """LangGraph node (Intake agent): classify the description; explicit user fields override the classifier."""
    from agents.guardrails import validate_incident
    from agents.state import describe, done

    desc, given, warnings = state["description"], state["given_incident"], list(state.get("warnings") or [])
    cls = classify(desc) if desc else {"fields": {}, "confidence": {}, "method": "structured"}
    incident = {**cls["fields"], **given}
    if not incident.get("disruption_type"):
        incident["disruption_type"] = "Factory Incident"
        warnings.append("Disruption type could not be inferred; defaulted to Factory Incident")
    validate_incident(incident, store.options())
    entry = done("intake", state["intake_t0"], describe(incident),
                 {"incident": incident, "classification": cls, "warnings": warnings})
    return {"incident": incident, "classification": cls, "warnings": warnings,
            "query": desc or describe(incident), "trace": [entry]}

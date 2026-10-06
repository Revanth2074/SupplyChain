"""Input validation guardrails: length, injection, PII, off-topic and
structured-field validation against the dataset vocabulary."""
from __future__ import annotations

import re

from fastapi import HTTPException

MAX_LEN = 2000
MIN_LEN = 3

INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|prompts)",
    r"disregard (the )?(system|previous)",
    r"you are now", r"act as (an? )?(?!supply)", r"system prompt", r"jailbreak",
    r"reveal (your|the) (prompt|instructions|key)", r"<\s*script", r"\bDROP\s+TABLE\b",
    r"api[_ -]?key", r"password",
]
PII_PATTERNS = {
    "email": r"[\w.+-]+@[\w-]+\.[\w.]+",
    "card": r"\b(?:\d[ -]?){13,16}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
}
DOMAIN_TERMS = {
    "supply", "supplier", "disruption", "port", "congestion", "strike", "labor", "labour",
    "cyber", "attack", "ransomware", "factory", "fire", "incident", "geopolitical", "sanction",
    "tariff", "war", "natural", "disaster", "flood", "earthquake", "hurricane", "typhoon",
    "production", "revenue", "loss", "recovery", "logistics", "shipment", "shipping", "inventory",
    "tier", "vendor", "manufacturing", "plant", "delay", "shortage", "outage", "response",
    "backup", "reroute", "resilience", "risk", "severity", "industry", "automotive", "electronics",
    "pharmaceuticals", "aerospace", "semiconductor", "chip", "food", "retail", "textile",
    "energy", "chemicals", "region", "asia", "europe", "america", "africa", "middle", "east",
    "operations", "impact", "freight", "container", "warehouse", "procurement", "sourcing",
    "case", "cases", "similar", "historical", "strategy", "strategies", "recover", "financial",
    "dis", "lockdown", "pandemic", "covid", "quality", "recall", "bankruptcy", "insolvency",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def validate_text(text: str, field: str = "query", require_domain: bool = True) -> dict:
    """Returns {'text': sanitized, 'warnings': [...]} or raises 422."""
    if text is None:
        raise HTTPException(422, f"{field} is required")
    t = _norm(str(text))
    if len(t) < MIN_LEN:
        raise HTTPException(422, f"{field} is too short (min {MIN_LEN} chars)")
    if len(t) > MAX_LEN:
        raise HTTPException(422, f"{field} is too long (max {MAX_LEN} chars)")
    low = t.lower()
    for p in INJECTION_PATTERNS:
        if re.search(p, low, re.I):
            raise HTTPException(422, f"{field} rejected by guardrail: possible prompt-injection / unsafe content")
    warnings = []
    for name, p in PII_PATTERNS.items():
        if re.search(p, t):
            t = re.sub(p, f"[REDACTED_{name.upper()}]", t)
            warnings.append(f"Redacted {name} from input")
    if require_domain:
        toks = set(re.findall(r"[a-z]+", low))
        if not toks & DOMAIN_TERMS:
            raise HTTPException(
                422, f"{field} appears off-topic. Please describe a supply-chain disruption "
                     "(e.g. supplier, port, strike, cyber attack, production impact).")
    return {"text": t, "warnings": warnings}


def validate_incident(inc: dict, options: dict) -> list[str]:
    """Validate structured incident fields against known vocab. Returns warnings."""
    warnings = []
    for col in ("disruption_type", "industry", "supplier_region", "supplier_size", "response_type"):
        v = inc.get(col)
        if v and v not in options.get(col, []):
            raise HTTPException(422, f"Invalid {col} '{v}'. Allowed: {options.get(col)}")
    if inc.get("supplier_tier") is not None and int(inc["supplier_tier"]) not in (1, 2, 3):
        raise HTTPException(422, "supplier_tier must be 1, 2 or 3")
    if inc.get("disruption_severity") is not None and not 1 <= int(inc["disruption_severity"]) <= 5:
        raise HTTPException(422, "disruption_severity must be between 1 and 5")
    if inc.get("production_impact_pct") is not None and not 0 <= float(inc["production_impact_pct"]) <= 100:
        raise HTTPException(422, "production_impact_pct must be 0-100")
    if inc.get("revenue_loss_usd") is not None and float(inc["revenue_loss_usd"]) < 0:
        raise HTTPException(422, "revenue_loss_usd must be >= 0")
    if inc.get("response_time_days") is not None and not 0 <= int(inc["response_time_days"]) <= 365:
        raise HTTPException(422, "response_time_days must be 0-365")
    return warnings

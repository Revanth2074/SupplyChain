"""
Disruption Classification Agent (Intake).
Turns a free-text incident description into structured dataset fields (type, industry,
tier, region, size, severity, backup) with per-field confidence. A goal-driven agent: keyword rules
constrained to the dataset vocabulary first, then Synapt nearest-case labelling for any key field the
rules missed or are unsure of (no LLM; the external LLM is used only as the offline judge).
"""

from __future__ import annotations

import logging
import re

from agents.base import Action, Agent, Tool
from agents.state import describe
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


SYNAPT_FIELDS = ("disruption_type", "industry", "supplier_region")  # fields Synapt's nearest cases can label
MIN_FIELD_CONFIDENCE = 0.6
MIN_SYNAPT_LABEL_CONFIDENCE = 0.5


def _synapt_labels(text: str) -> dict:
    from agents.retrieval import synapt_label
    return synapt_label(text)


def _synapt_ready() -> bool:
    from agents import synapt_tools as syn
    return syn.configured()


class IntakeAgent(Agent):
    """Goal: a complete, valid incident with a confidence for every key field.
    Tools: vocabulary-constrained keyword rules; Synapt nearest-case labelling (trident_get_chunks) for
    fields the rules missed or are unsure of. Explicit user fields always win."""

    id, node = "intake", "classifier"
    goal = "Turn the description into a valid incident with every key field known and confident"
    max_steps = 3

    def make_tools(self) -> list[Tool]:
        return [Tool("keyword_rules", "Read the text with vocabulary-constrained keyword rules", lambda text: classify(text)),
                Tool("synapt_neighbour_labels", "Label fields from the most similar cases in Synapt (k-NN vote)",
                     lambda text: _synapt_labels(text), soft=True)]

    def started_at(self, state: dict) -> float:
        return state.get("intake_t0") or super().started_at(state)

    def perceive(self, state: dict) -> dict:
        return {"desc": state["description"], "given": state["given_incident"], "warnings": list(state.get("warnings") or []),
                "cls": None, "asked_synapt": False, "filled": [], "unsure": []}

    def _uncertain(self, obs: dict) -> list[str]:
        f, c = obs["cls"]["fields"], obs["cls"]["confidence"]
        return [k for k in SYNAPT_FIELDS if k not in obs["given"] and (k not in f or c.get(k, 0) < MIN_FIELD_CONFIDENCE)]

    def decide(self, obs: dict, steps: list[dict]) -> Action | None:
        if not obs["desc"]:
            return None  # structured input only: nothing to read
        if obs["cls"] is None:
            return Action("keyword_rules", {"text": obs["desc"]}, "Read the description with keyword rules first (fast, exact)")
        weak = self._uncertain(obs)
        if weak and not obs["asked_synapt"] and _synapt_ready():
            return Action("synapt_neighbour_labels", {"text": obs["desc"]},
                          f"{', '.join(weak)} missing or uncertain: ask Synapt how the most similar past cases are labelled")
        return None

    def observe(self, obs: dict, action: Action, result, error: str | None) -> dict:
        if action.tool == "keyword_rules":
            obs["cls"] = result
        elif action.tool == "synapt_neighbour_labels":
            obs["asked_synapt"] = True
            opts = store.options()
            for k in self._uncertain(obs) if result else []:
                top = (result["fields"].get(k) or [None])[0]
                if top and top["confidence"] < MIN_SYNAPT_LABEL_CONFIDENCE:
                    obs["unsure"].append(f"{k} ({top['value']} {top['confidence']:.0%})")
                if top and top["confidence"] >= MIN_SYNAPT_LABEL_CONFIDENCE and top["value"] in opts.get(k, []):
                    obs["cls"]["fields"][k] = top["value"]
                    obs["cls"]["confidence"][k] = round(float(top["confidence"]), 2)
                    obs["filled"].append(k)
            if obs["filled"]:
                obs["cls"]["method"] = "rules+synapt-knn"
                obs["cls"]["rationale"] += f" Synapt nearest cases filled: {', '.join(obs['filled'])}."
        return obs

    def summarise(self, action: Action, result, error: str | None) -> str:
        if error:
            return f"failed ({error}); keeping the rule result"
        if action.tool == "keyword_rules":
            return f"matched {', '.join(sorted(result['fields'])) or 'nothing'}"
        return f"{result.get('neighbours', 0)} neighbour cases; labels for {', '.join(sorted(result.get('fields', {}))) or 'none'}"

    def reflect(self, obs: dict, steps: list[dict]) -> dict:
        from agents.guardrails import validate_incident
        cls = obs["cls"] or {"fields": {}, "confidence": {}, "method": "structured", "rationale": "Structured input."}
        incident = {**cls["fields"], **obs["given"]}
        if not incident.get("disruption_type"):
            incident["disruption_type"] = "Factory Incident"
            obs["warnings"].append("Disruption type could not be inferred; defaulted to Factory Incident")
        validate_incident(incident, store.options())
        conf = {k: (1.0 if k in obs["given"] else cls["confidence"].get(k)) for k in incident}
        known = [v for v in conf.values() if v is not None]
        confidence = round(sum(known) / len(known), 2) if known else None
        obs.update(incident=incident, cls=cls)
        summary = (describe(incident) + (f" · Synapt filled {', '.join(obs['filled'])}" if obs["filled"] else "")
                   + (f" · left unknown, Synapt's neighbours disagree: {', '.join(obs['unsure'])}" if obs["unsure"] else ""))
        return {"status": "partial" if obs["warnings"] and "defaulted" in " ".join(obs["warnings"]) else "done",
                "confidence": confidence, "summary": summary, "requests": []}

    def commit(self, obs: dict, message: dict, state: dict) -> dict:
        return {"incident": obs["incident"], "classification": obs["cls"], "warnings": obs["warnings"],
                "query": obs["desc"] or describe(obs["incident"])}

    def detail(self, obs: dict):
        return {"incident": obs.get("incident"), "classification": obs.get("cls"), "warnings": obs["warnings"]}


classifier_node = IntakeAgent()

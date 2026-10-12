"""
Response Synthesis Agent & Node (Report agent).
Builds the executive briefing from the evidence package (facts, cases, strategy statistics, the plan)
and the Synapt graph-RAG answer, then runs the deterministic fact-check: unknown case IDs, placeholders,
and amounts / percentages not in the evidence are flagged. No LLM at runtime.
"""

from __future__ import annotations

import logging
import re

from agents.base import Action, Agent, Tool
from agents.state import describe

log = logging.getLogger("synthesis")

CASE_ID = re.compile(r"DIS-[0-9X]{6}", re.I)
MONEY = re.compile(r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(M|million|K|k|B|bn)?\b")
PCT = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s?%")


def report_facts(prio: dict, pred: dict, recovery: dict) -> dict:
    return {
        "priority": f"{prio['level']} (score {prio['score']}/100), SLA: {prio['action_sla']}",
        "production_impact": f"{pred['production_impact_pct']}%",
        "revenue_loss": f"${recovery['predicted_revenue_loss']:,.0f}",
        "partial_recovery": f"{recovery['predicted_partial_days']} days",
        "full_recovery": f"{recovery['predicted_full_days']} days",
        "risk_level": f"{pred['risk_level']} ({pred['risk_probability']:.0%} probability of a high-impact outcome)",
        "recommended_strategy": recovery["strategy"],
        "resilience": f"{recovery['resilience']['score']}/100 ({recovery['resilience']['band']})",
    }


def _allowed_numbers(facts: dict, cases: list[dict], strategies: list[dict], recovery: dict) -> tuple[list, list]:
    money, pct = [], []
    for v in facts.values():
        money += [_money(m) for m in MONEY.finditer(v)]
        pct += [float(m.group(1)) for m in PCT.finditer(v)]
    for c in cases:
        money.append(float(c.get("revenue_loss_usd") or 0))
        pct.append(float(c.get("production_impact_pct") or 0))
    for st in strategies:
        money += [float(st.get(k) or 0) for k in ("avg_revenue_loss", "pred_revenue_loss")]
        pct += [float(st.get("avg_impact") or 0), 100 * float(st.get("supplier_change_rate") or 0)]
    sc = recovery.get("supplier_change_probability")
    if sc is not None:
        pct.append(100 * sc)
    return money, pct


def _money(m: re.Match) -> float:
    v = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    return v * (1e6 if unit in ("m", "million") else 1e3 if unit == "k" else 1e9 if unit in ("b", "bn") else 1)


def check_report(md: str, facts: dict, cases: list[dict], strategies: list[dict], recovery: dict) -> list[str]:
    """Deterministic fact-check of the briefing against the evidence it was given."""
    issues = []
    known = {c["disruption_id"].upper() for c in cases}
    for cid in sorted({m.group(0).upper() for m in CASE_ID.finditer(md)}):
        if "X" in cid:
            issues.append(f"placeholder case ID {cid}")
        elif cid not in known:
            issues.append(f"case ID {cid} is not one of the retrieved historical cases")
    money_ok, pct_ok = _allowed_numbers(facts, cases, strategies, recovery)
    for m in MONEY.finditer(md):
        v = _money(m)
        tol = 0.051 if m.group(2) else 0.005  # "$3.37M" style is rounded
        if v >= 1000 and not any(abs(v - a) <= tol * max(a, 1) for a in money_ok):
            issues.append(f"amount {m.group(0).strip()} does not match the evidence")
    for m in PCT.finditer(md):
        v = float(m.group(1))
        if not any(abs(v - a) <= 0.55 for a in pct_ok):
            issues.append(f"percentage {m.group(0)} does not match the evidence")
    return issues


def strip_bad_ids(md: str, cases: list[dict]) -> str:
    known = {c["disruption_id"].upper() for c in cases}
    md = re.sub(r"\s*\((?:Case ID:?\s*)?(DIS-[0-9X]{6})\)",
                lambda m: m.group(0) if m.group(1).upper() in known else "", md, flags=re.I)
    return CASE_ID.sub(lambda m: m.group(0) if m.group(0).upper() in known else "a historical case", md)


SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z*])")


def strict_rewrite(md: str, issues_in) -> str:
    """Drop every sentence that the fact-check flags; headings and clean sentences are kept."""
    out = []
    for line in md.split("\n"):
        kept = [s for s in SENTENCE.split(line) if not issues_in(s)]
        if kept or not line.strip():
            out.append(" ".join(kept))
    return "\n".join(out)


def build_briefing(incident: dict, cases: list[dict], plan: dict, recovery: dict, pred: dict, prio: dict,
                   facts: dict, top3: list[dict]) -> str:
    """Executive briefing from the evidence only: every figure comes from `facts`, the cases or the
    strategy statistics, so the fact-check can verify it."""
    precedent = "; ".join(
        f"{c['disruption_id']} ({c['response_type']}, {c['full_recovery_days']} days to full recovery)"
        for c in cases[:3]) or "no close matches"
    stats = "; ".join(f"{st['strategy']} {st['avg_full_recovery']} days over {st['cases']} cases" for st in top3)
    actions = "\n".join(f"- {a['action']} ({a['timeframe']})" for a in (plan.get("immediate_actions") or [])[:4])
    return (
        f"**Situation** — {describe(incident)}. Priority **{facts['priority']}**.\n\n"
        f"**Historical Precedent** (evidence: dataset) — Closest cases: {precedent}. Average full recovery by strategy: {stats}.\n\n"
        f"**Expected Impact** (estimate: precedent statistics) — {facts['production_impact']} production impact, {facts['revenue_loss']} revenue "
        f"loss, risk level {facts['risk_level']}. Resilience {facts['resilience']}.\n\n"
        f"**Recommended Response** (recommendation: statistics + Synapt playbook) — {plan.get('primary_strategy')} (secondary: {plan.get('secondary_strategy')}). "
        f"{plan.get('rationale', '')}\n{actions}\n\n"
        f"**Recovery Outlook** (estimate: precedent statistics) — partial ≈{facts['partial_recovery']}, full ≈{facts['full_recovery']}.")


MAX_REWRITES = 2


class ReportAgent(Agent):
    """Goal: an executive briefing in which every figure and case ID is verified against the evidence.
    Tools: the evidence-built drafter, the deterministic fact-check, the strict rewrite (drops any sentence
    the check flags) and the Synapt answer attacher. The agent fact-checks its own draft and rewrites
    until it passes (at most MAX_REWRITES times) before reporting."""

    id, node = "reporter", "synthesis"
    goal = "A briefing in which every figure and case ID is verified against the evidence"
    max_steps = 2 + 2 * MAX_REWRITES + 1

    def make_tools(self) -> list[Tool]:
        return [Tool("draft_briefing", "Fill the briefing template from facts, cases, statistics and the plan",
                     lambda **kw: build_briefing(**kw)),
                Tool("fact_check", "Every amount, percentage and case ID must appear in the evidence",
                     lambda text, ev: check_report(text, ev["facts"], ev["cases"], ev["strategies"], ev["recovery"])),
                Tool("strict_rewrite", "Drop every sentence the fact-check flags",
                     lambda text, ev: strict_rewrite(text, lambda t: check_report(t, ev["facts"], ev["cases"], ev["strategies"], ev["recovery"]))),
                Tool("attach_synapt_answer", "Add Synapt's own graph-RAG answer as a separate, labelled section",
                     lambda text, answer: text + f"\n\n**Synapt Knowledge Graph** (Synapt graph-RAG answer) — {answer.strip()}")]

    def perceive(self, state: dict) -> dict:
        incident, cases, plan, recovery = state["incident"], state["cases"], state["plan"], state["recovery"]
        pred, prio = state["impact"]["prediction"], state["impact"]["priority"]
        facts = report_facts(prio, pred, recovery)
        top3 = state["strategies"]["strategies"][:3]
        proc = plan.get("procedure") or {}  # figures quoted from the Synapt playbook steps are evidence too
        ev = {"facts": {**facts, "playbook": " ".join(st["text"] for st in proc.get("steps") or [])},
              "cases": cases[:6], "strategies": top3, "recovery": recovery}
        return {"draft_args": {"incident": incident, "cases": cases[:6], "plan": plan, "recovery": recovery, "pred": pred,
                               "prio": prio, "facts": facts, "top3": top3},
                "facts": facts, "ev": ev, "text": None, "issues": None, "first": None, "rewrites": 0, "attached": False,
                "answer": (state.get("graph") or {}).get("answer"), "strict": state.get("report_mode") == "strict",
                "round": state.get("report_round", 0) + 1}

    def decide(self, obs: dict, steps: list[dict]) -> Action | None:
        if obs["text"] is None:
            return Action("draft_briefing", obs["draft_args"], "Draft the briefing from the evidence only")
        if obs["issues"] is None:
            return Action("fact_check", {"text": obs["text"], "ev": obs["ev"]}, "Fact-check every figure and case ID in the draft")
        if obs["issues"] and obs["rewrites"] < MAX_REWRITES + (1 if obs["strict"] else 0):
            return Action("strict_rewrite", {"text": obs["text"], "ev": obs["ev"]},
                          f"{len(obs['issues'])} unverified item(s): drop the sentences that carry them")
        if obs["answer"] and not obs["attached"]:
            return Action("attach_synapt_answer", {"text": obs["text"], "answer": obs["answer"]},
                          "Add Synapt's own answer as its own section (it carries Synapt's confidence, not our fact-check)")
        return None

    def observe(self, obs: dict, action: Action, result, error: str | None) -> dict:
        if action.tool in ("draft_briefing", "strict_rewrite"):
            obs["text"], obs["issues"] = result, None
            if action.tool == "strict_rewrite":
                obs["rewrites"] += 1
        elif action.tool == "fact_check":
            obs["issues"] = result
            if obs["first"] is None:
                obs["first"] = result
        else:
            obs["text"], obs["attached"] = result, True
        return obs

    def summarise(self, action: Action, result, error: str | None) -> str:
        if action.tool == "fact_check":
            return "passed" if not result else f"{len(result)} issue(s): " + "; ".join(result[:2])
        if action.tool == "attach_synapt_answer":
            return "Synapt section added"
        return f"{len(result.split())} words"

    def reflect(self, obs: dict, steps: list[dict]) -> dict:
        passed = not obs["issues"]
        rs = ("Briefing built, fact-check passed" if passed else f"Briefing built, {len(obs['issues'])} unverified figure(s) flagged")
        if obs["rewrites"]:
            rs += f" (rewritten {obs['rewrites']}x after {len(obs['first'])} issue(s))"
        return {"status": "done" if passed else "partial", "confidence": 1.0 if passed else 0.5, "summary": rs, "requests": []}

    def commit(self, obs: dict, message: dict, state: dict) -> dict:
        check = {"first_pass": obs["first"] or [], "final": obs["issues"] or [], "retried": obs["rewrites"] > 0,
                 "rewrites": obs["rewrites"], "method": "template+synapt" if obs["attached"] else "template",
                 "round": obs["round"], "passed": not obs["issues"]}
        obs["check"] = check
        return {"summary": obs["text"], "facts": obs["facts"], "fact_check": check, "report_round": obs["round"], "report_mode": ""}

    def detail(self, obs: dict):
        return {"summary": obs["text"], "facts": obs["facts"], "fact_check": obs.get("check")}


synthesis_node = ReportAgent()

"""
Response Synthesis Agent & Node (Report agent).
Builds the executive briefing from the evidence package (facts, cases, strategy statistics, the plan)
and the Synapt graph-RAG answer, then runs the deterministic fact-check: unknown case IDs, placeholders,
and amounts / percentages not in the evidence are flagged. No LLM at runtime.
"""

from __future__ import annotations

import logging
import re
import time

from agents.state import describe, done, emit

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
        f"**Expected Impact** (prediction: ML models) — {facts['production_impact']} production impact, {facts['revenue_loss']} revenue "
        f"loss, risk level {facts['risk_level']}. Resilience {facts['resilience']}.\n\n"
        f"**Recommended Response** (recommendation: statistics + Synapt playbook) — {plan.get('primary_strategy')} (secondary: {plan.get('secondary_strategy')}). "
        f"{plan.get('rationale', '')}\n{actions}\n\n"
        f"**Recovery Outlook** (prediction: ML models) — partial ≈{facts['partial_recovery']}, full ≈{facts['full_recovery']}.")


def synthesis_node(state: dict) -> dict:
    """LangGraph node (Report agent): evidence-built briefing, fact-checked, plus the Synapt graph answer.
    When the supervisor sends it back after a failed fact-check, it rewrites in strict mode: every sentence
    carrying an unverified figure or case ID is dropped, then the briefing is checked again."""
    t0 = time.time()
    emit("agent_start", "reporter")
    incident, cases, plan, recovery = state["incident"], state["cases"], state["plan"], state["recovery"]
    pred, prio = state["impact"]["prediction"], state["impact"]["priority"]
    strat, graph = state["strategies"], state.get("graph")
    facts = report_facts(prio, pred, recovery)
    report_cases = cases[:6]
    top3 = strat["strategies"][:3]
    summary_md = build_briefing(incident, report_cases, plan, recovery, pred, prio, facts, top3)
    proc = plan.get("procedure") or {}  # figures quoted from the Synapt playbook steps are evidence too
    evidence = {**facts, "playbook": " ".join(st["text"] for st in proc.get("steps") or [])}
    issues = check_report(summary_md, evidence, report_cases, top3, recovery)
    rnd = state.get("report_round", 0) + 1
    check = {"first_pass": issues, "final": issues, "retried": False, "method": "template", "round": rnd}
    if issues and rnd > 1:  # strict rewrite requested by the supervisor
        summary_md = strict_rewrite(summary_md, lambda t: check_report(t, evidence, report_cases, top3, recovery))
        check.update(final=check_report(summary_md, evidence, report_cases, top3, recovery), retried=True)
    answer = (graph or {}).get("answer")
    if answer:  # Synapt's own grounded answer, shown as its own section and not part of our fact-check
        summary_md += f"\n\n**Synapt Knowledge Graph** (Synapt graph-RAG answer) — {answer.strip()}"
        check["method"] = "template+synapt"
    check["passed"] = not check["final"]
    rs = ("Briefing built, fact-check passed" if check["passed"] else
          f"Briefing built, {len(check['final'])} unverified figure(s) flagged")
    entry = done("reporter", t0, rs, {"summary": summary_md, "facts": facts, "fact_check": check})
    return {"summary": summary_md, "facts": facts, "fact_check": check, "report_round": rnd, "trace": [entry]}

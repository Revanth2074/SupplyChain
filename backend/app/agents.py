"""Multi-agent disruption workflow:
Intake/Classifier -> Investigator -> Impact Assessor -> Response Planner ->
Recovery Analyst -> Report Writer -> Judge.  Implemented as a generator that
emits progress events (used for SSE streaming) and a final result."""
from __future__ import annotations

import concurrent.futures as cf
import json
import logging
import re
import time
from typing import Any, Iterator

import numpy as np

from . import analysis, feedback, llm
from . import synapt_service as syn
from .data_store import store
from .guardrails import validate_incident, validate_text
from .judge import judge
from .ml_models import registry
from .retrieval import hybrid_search

log = logging.getLogger("agents")
_pool = cf.ThreadPoolExecutor(max_workers=4)

AGENTS = [
    ("intake", "Intake & Classification Agent", "Validates input and classifies the disruption"),
    ("investigator", "Investigation Agent", "Retrieves similar historical cases via Synapt hybrid + graph RAG"),
    ("impact", "Impact Assessment Agent", "Predicts production, financial & recovery impact; prioritises"),
    ("planner", "Response Planning Agent", "Ranks response strategies and drafts an action plan"),
    ("recovery", "Recovery Analysis Agent", "Projects recovery timeline and resilience actions"),
    ("reporter", "Report Agent", "Synthesises an executive briefing"),
    ("judge", "Judge Agent (LLM-as-Judge)", "Audits the analysis for groundedness and quality"),
]


def _ev(kind: str, agent: str, **kw) -> dict:
    return {"type": kind, "agent": agent, "ts": time.time(), **kw}


def _describe(inc: dict) -> str:
    parts = [f"{inc.get('disruption_type', 'Unknown')} disruption"]
    if inc.get("industry"):
        parts.append(f"in {inc['industry']}")
    if inc.get("supplier_tier"):
        parts.append(f"Tier {inc['supplier_tier']} supplier")
    if inc.get("supplier_region"):
        parts.append(f"in {inc['supplier_region']}")
    if inc.get("supplier_size"):
        parts.append(f"({inc['supplier_size']})")
    if inc.get("has_backup_supplier") is not None:
        parts.append("with backup supplier" if inc["has_backup_supplier"] else "with no backup supplier")
    if inc.get("disruption_severity"):
        parts.append(f"severity {inc['disruption_severity']}/5")
    return ", ".join(parts)


PLAN_SYS = """You are the Response Planning Agent for a supply-chain operations team.
Using ONLY the evidence (similar historical cases, strategy effectiveness statistics and ML predictions),
produce a response plan. Cite historical case IDs (DIS-xxxxxx) that support your choices.
If a Synapt response playbook (synapt_procedure) is provided, follow its steps and say so in the rationale.
Return JSON: {"primary_strategy": str, "secondary_strategy": str, "rationale": str,
"immediate_actions":[{"action":str,"owner":str,"timeframe":str}],
"short_term_actions":[str], "long_term_actions":[str], "risks":[str], "cited_cases":[str]}
Strategy names must be one of the strategies in the statistics."""

REPORT_SYS = """You are the Report Agent. Write a concise executive briefing in Markdown (max ~300 words)
for supply-chain leadership with sections: **Situation**, **Historical Precedent**, **Expected Impact**,
**Recommended Response**, **Recovery Outlook**.
Rules:
- The current incident is NEW and has NO case ID. Never attach a DIS- ID (or a placeholder like DIS-XXXXXX)
  to the current incident. DIS- IDs may only name the historical cases listed in similar_cases.
- For the current incident's figures use the values in `facts` exactly as written, and use each figure once
  consistently (one revenue-loss figure, one recovery figure). Do not compute new numbers.
- Historical figures must come from similar_cases or top_strategies."""

CASE_ID = re.compile(r"DIS-[0-9X]{6}", re.I)
MONEY = re.compile(r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(M|million|K|k|B|bn)?\b")
PCT = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s?%")


def _report_facts(prio: dict, pred: dict, recovery: dict) -> dict:
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


def _strip_bad_ids(md: str, cases: list[dict]) -> str:
    known = {c["disruption_id"].upper() for c in cases}
    md = re.sub(r"\s*\((?:Case ID:?\s*)?(DIS-[0-9X]{6})\)",
                lambda m: m.group(0) if m.group(1).upper() in known else "", md, flags=re.I)
    return CASE_ID.sub(lambda m: m.group(0) if m.group(0).upper() in known else "a historical case", md)


def _fallback_plan(inc: dict, strategies: list[dict], cases: list[dict]) -> dict:
    top = strategies[0]["strategy"] if strategies else "Alternative Supplier"
    sec = strategies[1]["strategy"] if len(strategies) > 1 else "Inventory Buffer"
    cited = [c["disruption_id"] for c in cases if c.get("response_type") == top][:3]
    acts = {
        "Alternative Supplier": "Activate qualified alternative suppliers and issue expedited POs",
        "Inventory Buffer": "Release safety stock and re-allocate inventory to critical SKUs",
        "Production Reroute": "Reroute production to alternate plants/lines with available capacity",
        "Customer Delay": "Notify key customers, renegotiate delivery schedules and prioritise orders",
        "Combined Strategy": "Run combined playbook: alt sourcing + buffer release + selective rerouting",
    }
    return {
        "primary_strategy": top, "secondary_strategy": sec,
        "rationale": f"{top} shows the best historical effectiveness for comparable {inc.get('disruption_type')} cases.",
        "immediate_actions": [
            {"action": "Stand up disruption response team and confirm scope of affected parts", "owner": "Supply Chain Ops Lead", "timeframe": "0-24h"},
            {"action": acts.get(top, f"Execute {top}"), "owner": "Procurement", "timeframe": "24-72h"},
            {"action": "Quantify exposure: open orders, inventory cover days, revenue at risk", "owner": "Planning / Finance", "timeframe": "0-48h"},
        ],
        "short_term_actions": [acts.get(sec, f"Prepare {sec} as fallback"), "Daily recovery stand-up with KPI tracking"],
        "long_term_actions": ["Qualify a backup supplier for affected parts" if not inc.get("has_backup_supplier") else
                              "Review backup supplier capacity contracts", "Update risk register and BCP playbooks"],
        "risks": ["Prolonged recovery if the primary strategy capacity is insufficient"],
        "cited_cases": cited, "method": "template",
    }


def run_workflow(payload: dict) -> Iterator[dict]:
    t_all = time.time()
    trace: list[dict] = []
    state: dict[str, Any] = {}
    use_graph = payload.get("use_graph", True)

    def step(agent_id: str):
        name = next(a[1] for a in AGENTS if a[0] == agent_id)
        return name

    # ---------------- 1. Intake ----------------
    a = "intake"
    yield _ev("agent_start", a, name=step(a))
    t0 = time.time()
    store.load()
    desc = (payload.get("description") or "").strip()
    warnings: list[str] = []
    if desc:
        v = validate_text(desc, "description")
        desc, warnings = v["text"], v["warnings"]
    given = {k: v for k, v in (payload.get("incident") or {}).items() if v not in (None, "")}
    if not desc and not given.get("disruption_type"):
        raise ValueError("Provide a description or at least a disruption_type")
    validate_incident(given, store.options())
    cls = analysis.classify(desc) if desc else {"fields": {}, "confidence": {}, "method": "structured"}
    incident = {**cls["fields"], **given}  # explicit user fields override classifier
    if not incident.get("disruption_type"):
        incident["disruption_type"] = "Factory Incident"
        warnings.append("Disruption type could not be inferred; defaulted to Factory Incident")
    validate_incident(incident, store.options())
    query = desc or _describe(incident)
    state.update(incident=incident, classification=cls, query=query)
    graph_fut = proc_fut = None
    if use_graph and syn.configured():
        gq = f"{_describe(incident)}. {desc[:300]} Has a similar disruption occurred and how was it resolved, " \
             f"which response strategy recovered fastest?"
        graph_fut = _pool.submit(syn.graph_query, gq, None, None, 75, "workflow")
    proc_fut = _pool.submit(syn.procedure_for, incident["disruption_type"]) if syn.configured() else None
    out = {"incident": incident, "classification": cls, "warnings": warnings}
    trace.append({"agent": a, "ms": int((time.time() - t0) * 1000), "summary": _describe(incident)})
    yield _ev("agent_done", a, name=step(a), ms=trace[-1]["ms"], summary=trace[-1]["summary"], data=out)

    # ---------------- 2. Investigator ----------------
    a = "investigator"
    yield _ev("agent_start", a, name=step(a))
    t0 = time.time()
    search = hybrid_search(f"{query}. {_describe(incident)}", payload.get("filters"),
                           top_k=payload.get("top_k", 8), mode="hybrid", reference=incident)
    graph = None
    if graph_fut:
        try:
            graph = graph_fut.result(timeout=max(5, 80 - (time.time() - t0)))
        except Exception as e:  # noqa: BLE001
            graph = {"error": str(e)[:200]}
    cases = search["results"]
    # include graph-RAG cases not already present
    if graph and graph.get("cases"):
        have = {c["disruption_id"] for c in cases}
        for gc in graph["cases"][:4]:
            c = store.get_case(gc["id"])
            if c and c["disruption_id"] not in have:
                from .retrieval import similarity
                c.update(similarity=similarity(c, incident), legs={"graph": {"rank": 0}}, from_synapt=True,
                         retrieval_score=None)
                cases.append(c)
    state.update(cases=cases, graph=graph)
    sims = [c["similarity"] for c in cases if c.get("similarity") is not None]
    summ = (f"{len(cases)} similar cases (avg similarity {np.mean(sims):.0%}) via "
            f"{search['semantic_source']} + BM25" + (", graph-RAG answer received" if graph and graph.get("answer") else ""))
    trace.append({"agent": a, "ms": int((time.time() - t0) * 1000), "summary": summ})
    yield _ev("agent_done", a, name=step(a), ms=trace[-1]["ms"], summary=summ,
              data={"search": {k: v for k, v in search.items() if k != "results"}, "cases": cases, "graph": graph})

    # ---------------- 3. Impact ----------------
    a = "impact"
    yield _ev("agent_start", a, name=step(a))
    t0 = time.time()
    pred = registry.predict(incident)
    expl = registry.explain(incident)
    prio = analysis.priority(incident, pred)
    top_factors = {t: e["local"][:5] for t, e in expl.items()}
    impact = {"prediction": pred, "priority": prio, "explanation": expl, "top_factors": top_factors}
    state["impact"] = impact
    summ = (f"{prio['level']} (score {prio['score']}); impact ≈{pred['production_impact_pct']}%, loss ≈"
            f"${pred['revenue_loss_usd']:,.0f}, full recovery ≈{pred['full_recovery_days']:.0f}d, risk {pred['risk_level']}")
    trace.append({"agent": a, "ms": int((time.time() - t0) * 1000), "summary": summ})
    yield _ev("agent_done", a, name=step(a), ms=trace[-1]["ms"], summary=summ, data=impact)

    # ---------------- 4. Planner ----------------
    a = "planner"
    yield _ev("agent_start", a, name=step(a))
    t0 = time.time()
    strat = analysis.strategy_table(incident)
    procedure = None
    if proc_fut:
        try:
            procedure = proc_fut.result(timeout=30)
        except Exception as e:  # noqa: BLE001
            log.info("Synapt procedure unavailable: %s", e)
    evidence_cases = [{k: c.get(k) for k in ("disruption_id", "disruption_type", "industry", "supplier_tier",
                                              "has_backup_supplier", "disruption_severity", "production_impact_pct",
                                              "revenue_loss_usd", "response_type", "response_time_days",
                                              "partial_recovery_days", "full_recovery_days", "similarity")}
                      for c in cases[:10]]
    try:
        if not llm.available():
            raise RuntimeError("LLM unavailable")
        ev = {"incident": incident, "description": desc, "similar_cases": evidence_cases,
              "strategy_effectiveness": strat["strategies"][:5], "cohort": strat["scope"],
              "predictions": {k: pred[k] for k in ("production_impact_pct", "revenue_loss_usd", "full_recovery_days",
                                                  "risk_level", "risk_probability")},
              "priority": prio["level"], "synapt_graph_answer": (graph or {}).get("answer"),
              "synapt_procedure": procedure}
        plan = llm.chat_json(PLAN_SYS, json.dumps(ev, default=str), temperature=0.2, max_tokens=1400)
        plan["method"] = "llm"
        valid = {s["strategy"] for s in strat["strategies"]}
        if plan.get("primary_strategy") not in valid and strat["strategies"]:
            plan["primary_strategy"] = strat["strategies"][0]["strategy"]
    except Exception as e:  # noqa: BLE001
        log.warning("Planner fallback: %s", e)
        plan = _fallback_plan(incident, strat["strategies"], cases)
    plan["procedure"] = procedure
    state.update(strategies=strat, plan=plan)
    summ = f"Primary: {plan.get('primary_strategy')} · Secondary: {plan.get('secondary_strategy')} ({plan.get('method')})"
    if procedure:
        summ += f" · Synapt playbook: {len(procedure['steps'])} steps"
    trace.append({"agent": a, "ms": int((time.time() - t0) * 1000), "summary": summ})
    yield _ev("agent_done", a, name=step(a), ms=trace[-1]["ms"], summary=summ,
              data={"strategies": strat, "plan": plan})

    # ---------------- 5. Recovery ----------------
    a = "recovery"
    yield _ev("agent_start", a, name=step(a))
    t0 = time.time()
    primary = plan.get("primary_strategy")
    cf_pred = registry.predict({**incident, "response_type": primary})
    df = store.df
    coh = df[(df["disruption_type"] == incident["disruption_type"]) & (df["response_type"] == primary)]
    if incident.get("disruption_severity"):
        c2 = coh[coh["disruption_severity"] == int(incident["disruption_severity"])]
        coh = c2 if len(c2) > 50 else coh
    pct = {f"p{q}": float(np.percentile(coh["full_recovery_days"], q)) for q in (10, 25, 50, 75, 90)} if len(coh) else {}
    part = float(cf_pred["partial_recovery_days"])
    full = float(cf_pred["full_recovery_days"])
    rt = int(incident.get("response_time_days") or 2)
    milestones = [
        {"day": 0, "label": "Disruption detected"},
        {"day": rt, "label": f"{primary} response initiated"},
        {"day": round(part), "label": "Partial recovery (≈ production stabilised)"},
        {"day": round((part + full) / 2), "label": "Ramp-up to normal capacity"},
        {"day": round(full), "label": "Full recovery"},
    ]
    resilience_actions = []
    if not incident.get("has_backup_supplier"):
        resilience_actions.append("Qualify a backup supplier — historically reduces full recovery time by ~25-30%")
    if int(incident.get("supplier_tier") or 1) >= 2:
        resilience_actions.append("Extend visibility to Tier 2/3 suppliers (sub-tier mapping & early warning)")
    if incident.get("supplier_size") == "Small":
        resilience_actions.append("Diversify away from single small suppliers for critical parts")
    resilience_actions.append("Hold strategic inventory buffer sized to the P75 partial-recovery window")
    recovery = {"strategy": primary, "predicted_partial_days": round(part), "predicted_full_days": round(full),
                "predicted_revenue_loss": cf_pred["revenue_loss_usd"], "cohort_size": int(len(coh)),
                "ranges": cf_pred["ranges"], "support": cf_pred["support"],
                "cohort_full_recovery_percentiles": pct,
                "supplier_change_probability": round(float(coh["permanent_supplier_change"].mean()), 3) if len(coh) else None,
                "milestones": milestones, "resilience": pred["resilience_score"],
                "resilience_actions": resilience_actions}
    state["recovery"] = recovery
    summ = f"Partial ≈{round(part)}d, full ≈{round(full)}d with {primary} (cohort P50 {pct.get('p50', 0):.0f}d, n={len(coh)})"
    trace.append({"agent": a, "ms": int((time.time() - t0) * 1000), "summary": summ})
    yield _ev("agent_done", a, name=step(a), ms=trace[-1]["ms"], summary=summ, data=recovery)

    # ---------------- 6. Reporter ----------------
    a = "reporter"
    yield _ev("agent_start", a, name=step(a))
    t0 = time.time()
    facts = _report_facts(prio, pred, recovery)
    report_cases = cases[:6]
    top3 = strat["strategies"][:3]
    ev_report = {"facts": facts, "incident": incident, "description": desc,
                 "similar_cases": evidence_cases[:6],
                 "plan": {k: plan.get(k) for k in ("primary_strategy", "secondary_strategy", "rationale",
                                                    "immediate_actions", "short_term_actions", "long_term_actions",
                                                    "risks")},
                 "top_strategies": [{k: st.get(k) for k in ("strategy", "cases", "avg_full_recovery",
                                                             "avg_revenue_loss", "avg_impact")} for st in top3],
                 "synapt_graph_answer": (graph or {}).get("answer")}
    check = {"first_pass": [], "final": [], "retried": False, "method": None}
    try:
        if not llm.available():
            raise RuntimeError("LLM unavailable")
        msgs = [{"role": "system", "content": REPORT_SYS},
                {"role": "user", "content": json.dumps(ev_report, default=str)}]
        summary_md = llm.chat(msgs, temperature=0.2, max_tokens=900)
        check["first_pass"] = check_report(summary_md, facts, report_cases, top3, recovery)
        if check["first_pass"]:
            check["retried"] = True
            msgs += [{"role": "assistant", "content": summary_md},
                     {"role": "user", "content": "Fact-check failed:\n- " + "\n- ".join(check["first_pass"]) +
                      "\nRewrite the briefing fixing these issues. Use `facts` verbatim for the current incident."}]
            summary_md = llm.chat(msgs, temperature=0.1, max_tokens=900)
        summary_md = _strip_bad_ids(summary_md, report_cases)
        check["final"] = check_report(summary_md, facts, report_cases, top3, recovery)
        check["method"] = "llm"
    except Exception as e:  # noqa: BLE001
        log.warning("Reporter fallback: %s", e)
        top3 = ", ".join(c["disruption_id"] for c in cases[:3])
        summary_md = (
            f"**Situation** — {_describe(incident)}. Priority **{prio['level']}**.\n\n"
            f"**Historical Precedent** — Closest cases: {top3}.\n\n"
            f"**Expected Impact** — ≈{pred['production_impact_pct']}% production impact, "
            f"≈{facts['revenue_loss']} revenue loss, risk level {pred['risk_level']}.\n\n"
            f"**Recommended Response** — {plan.get('primary_strategy')} (fallback: {plan.get('secondary_strategy')}). "
            f"{plan.get('rationale', '')}\n\n"
            f"**Recovery Outlook** — partial ≈{recovery['predicted_partial_days']} days, full ≈"
            f"{recovery['predicted_full_days']} days.")
        check["method"] = "template"
    state["summary"] = summary_md
    check["passed"] = not check["final"]
    rs = ("Briefing drafted, fact-check passed" if check["passed"] else
          f"Briefing drafted, {len(check['final'])} unverified figure(s) flagged")
    if check["retried"]:
        rs += f" (rewritten after {len(check['first_pass'])} issue(s))"
    trace.append({"agent": a, "ms": int((time.time() - t0) * 1000), "summary": rs})
    yield _ev("agent_done", a, name=step(a), ms=trace[-1]["ms"], summary=trace[-1]["summary"],
              data={"summary": summary_md, "facts": facts, "fact_check": check})

    # ---------------- 7. Judge ----------------
    a = "judge"
    yield _ev("agent_start", a, name=step(a))
    t0 = time.time()
    report_text = summary_md + "\n\nPLAN:\n" + json.dumps(plan, default=str)
    verdict = judge(report_text, {"incident": incident, "cases": cases, "strategies": strat["strategies"],
                                  "prediction": pred, "top_strategy": plan.get("primary_strategy")}) \
        if payload.get("judge", True) else None
    summ = (f"{verdict['verdict'].upper()} · score {verdict['overall_score']:.0%} ({verdict['method']})"
            if verdict else "skipped")
    trace.append({"agent": a, "ms": int((time.time() - t0) * 1000), "summary": summ})
    yield _ev("agent_done", a, name=step(a), ms=trace[-1]["ms"], summary=summ, data=verdict)

    report = {"incident": incident, "classification": cls, "warnings": warnings, "query": query,
              "cases": cases, "search_meta": {k: v for k, v in search.items() if k != "results"},
              "graph": graph, "impact": impact, "strategies": strat, "plan": plan, "recovery": recovery,
              "summary": summary_md, "facts": facts, "fact_check": check, "judge": verdict, "trace": trace,
              "total_ms": int((time.time() - t_all) * 1000),
              "retrieval_context": [c["text"] for c in cases[:8]] +
                                   ([graph["answer"]] if graph and graph.get("answer") else [])}
    aid = feedback.save_analysis(payload, incident, {k: v for k, v in report.items() if k != "graph"},
                                 verdict, (graph or {}).get("query_id"))
    report["analysis_id"] = aid
    yield {"type": "result", "data": report}


def run_sync(payload: dict) -> dict:
    result = None
    for ev in run_workflow(payload):
        if ev["type"] == "result":
            result = ev["data"]
    return result

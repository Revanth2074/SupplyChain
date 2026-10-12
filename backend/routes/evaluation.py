"""
Evaluation API Routes.
LLM-as-Judge for any briefing, and the DeepEval suite (golden incidents + guardrail suite) run in
the background with live progress.
"""

from fastapi import APIRouter, HTTPException

from agents.judge import judge
from agents.guardrails import validate_text
from agents.planner import strategy_table
from agents.precedent import estimator
from schemas import EvalRequest, JudgeRequest, compact
from services import evaluation
from services.bootstrap import ready
from services.data_store import store

router = APIRouter(tags=["Evaluation"])


@router.post("/judge")
def judge_ep(req: JudgeRequest):
    """Score a briefing on six criteria against the evidence (cases, strategies, prediction)."""
    ready()
    validate_text(req.report, "report", require_domain=False)
    cases = [c for c in (store.get_case(i) for i in req.case_ids) if c]
    inc = compact(req.incident) or {}
    pred = estimator.predict(inc) if inc.get("disruption_type") else None
    strat = strategy_table(inc)["strategies"] if inc.get("disruption_type") else []
    return judge(req.report, {"incident": inc, "cases": cases, "strategies": strat, "prediction": pred})


@router.post("/evaluate")
def run_eval(req: EvalRequest):
    ready()
    return evaluation.start(req.limit, req.use_graph, req.include_feedback)


@router.get("/evaluate/status")
def eval_status():
    return evaluation.status()


@router.get("/evaluate/results")
def eval_results():
    r = evaluation.results()
    if not r:
        raise HTTPException(404, "No evaluation results yet")
    return r

"""DeepEval-based evaluation of disruption analysis & recommendation quality.
Uses a custom DeepEval model routed through the OpenAI-compatible gateway.
Also reports deterministic metrics (classification accuracy, retrieval precision)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import traceback

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_DISABLE_PROGRESS_BAR", "YES")
os.environ.setdefault("ERROR_REPORTING", "NO")

from . import feedback, llm  # noqa: E402
from .config import settings  # noqa: E402

log = logging.getLogger("eval")
RESULTS_PATH = settings.ARTIFACT_DIR / "eval_results.json"

GOLDEN = [
    {"id": "G1", "description": "Ransomware attack on our Tier 2 avionics electronics supplier in Asia-Pacific has halted their ERP and shipments. No backup supplier is qualified. Severity looks high (4/5).",
     "expected": {"disruption_type": "Cyber Attack", "industry": "Aerospace", "supplier_tier": 2, "has_backup_supplier": False}},
    {"id": "G2", "description": "Severe port congestion at Shanghai is delaying containers of electronic components from a large Tier 1 supplier; we do have a backup supplier in Vietnam.",
     "expected": {"disruption_type": "Port Congestion", "industry": "Electronics", "supplier_tier": 1, "has_backup_supplier": True}},
    {"id": "G3", "description": "A labor strike at a medium-sized Tier 1 automotive parts supplier in Europe has stopped production of brake assemblies. Severity 3.",
     "expected": {"disruption_type": "Labor Strike", "industry": "Automotive", "supplier_tier": 1, "disruption_severity": 3}},
    {"id": "G4", "description": "Earthquake damaged a small Tier 3 API (active pharmaceutical ingredient) supplier plant in Japan. Single source, critical severity.",
     "expected": {"disruption_type": "Natural Disaster", "industry": "Pharmaceuticals", "supplier_tier": 3, "has_backup_supplier": False}},
    {"id": "G5", "description": "New export sanctions block shipments from our Tier 2 semiconductor supplier in Africa/Middle East region; severity 4, we have an alternate supplier.",
     "expected": {"disruption_type": "Geopolitical", "supplier_tier": 2, "has_backup_supplier": True}},
    {"id": "G6", "description": "Fire at a large Tier 1 food packaging supplier's factory in North America, moderate severity 2. Backup supplier available.",
     "expected": {"disruption_type": "Factory Incident", "supplier_tier": 1, "disruption_severity": 2}},
]

_state = {"running": False, "progress": 0, "total": 0, "current": None, "error": None, "started": None}
_lock = threading.Lock()


def _make_model():
    from deepeval.models.base_model import DeepEvalBaseLLM

    class GatewayLLM(DeepEvalBaseLLM):
        def __init__(self):
            self._name = settings.JUDGE_MODEL
            super().__init__(settings.JUDGE_MODEL)

        def load_model(self, *a, **k):
            return llm.client()

        def generate(self, prompt: str, schema=None, **kw):
            if schema is not None:
                sys = "Follow the instructions exactly." + \
                      f"\nThe JSON must match this schema: {json.dumps(schema.model_json_schema())}"
                data = llm.chat_json(sys, prompt, model=settings.JUDGE_MODEL, temperature=0, max_tokens=2000)
                return schema.model_validate(data)
            return llm.chat([{"role": "user", "content": prompt}], model=settings.JUDGE_MODEL,
                            temperature=0, max_tokens=2000)

        async def a_generate(self, prompt: str, schema=None, **kw):
            return await asyncio.to_thread(self.generate, prompt, schema)

        def get_model_name(self, *a, **k):
            return f"{self._name} (gateway)"

    return GatewayLLM()


def _metrics(model):
    from deepeval.metrics import AnswerRelevancyMetric, ContextualRelevancyMetric, FaithfulnessMetric, GEval
    try:
        from deepeval.test_case import SingleTurnParams as P
    except ImportError:  # older deepeval
        from deepeval.test_case import LLMTestCaseParams as P
    return [
        AnswerRelevancyMetric(threshold=0.6, model=model, async_mode=False),
        FaithfulnessMetric(threshold=0.6, model=model, async_mode=False),
        ContextualRelevancyMetric(threshold=0.4, model=model, async_mode=False),
        GEval(name="Recommendation Quality", model=model, async_mode=False, threshold=0.6,
              evaluation_steps=[
                  "Check the output recommends a specific primary response strategy for the disruption in the input.",
                  "Check the recommendation is justified with historical cases or statistics from the retrieval context.",
                  "Check that concrete, time-bound actions are provided.",
                  "Penalise numbers or case IDs that do not appear in the retrieval context.",
              ],
              evaluation_params=[P.INPUT, P.ACTUAL_OUTPUT, P.RETRIEVAL_CONTEXT]),
        GEval(name="Impact Analysis Correctness", model=model, async_mode=False, threshold=0.6,
              evaluation_steps=[
                  "Check the output states the expected production impact, financial loss and recovery time.",
                  "Check these estimates are plausible given the severity and similar cases in the retrieval context.",
                  "Check the output identifies factors driving the impact (e.g. backup supplier, tier, severity).",
              ],
              evaluation_params=[P.INPUT, P.ACTUAL_OUTPUT, P.RETRIEVAL_CONTEXT]),
    ]


def status() -> dict:
    return {**_state, "has_results": RESULTS_PATH.exists()}


def results() -> dict | None:
    return json.loads(RESULTS_PATH.read_text()) if RESULTS_PATH.exists() else None


def start(limit: int | None = None, use_graph: bool = False, include_feedback: bool = True) -> dict:
    with _lock:
        if _state["running"]:
            return status()
        _state.update(running=True, progress=0, error=None, started=time.time(), current=None)
    threading.Thread(target=_run, args=(limit, use_graph, include_feedback), daemon=True).start()
    return status()


def _run(limit, use_graph, include_feedback):
    from deepeval.test_case import LLMTestCase

    from .agents import run_sync
    try:
        cases = list(GOLDEN)
        if include_feedback:
            for i, fb in enumerate(feedback.low_rated_cases()[:3]):
                if fb["input"]:
                    cases.append({"id": f"FB{i + 1}", "description": fb["input"], "expected": {},
                                  "source": "feedback-regression"})
        if limit:
            cases = cases[:limit]
        _state["total"] = len(cases)
        model = _make_model() if llm.available() else None
        rows = []
        for i, g in enumerate(cases):
            _state["current"] = g["id"]
            rep = run_sync({"description": g["description"], "use_graph": use_graph, "judge": True, "top_k": 8})
            inc = rep["incident"]
            exp = g.get("expected", {})
            cls_hits = {k: (inc.get(k) == v) for k, v in exp.items()}
            same_type = [c for c in rep["cases"] if c["disruption_type"] == inc.get("disruption_type")]
            row = {
                "id": g["id"], "input": g["description"], "source": g.get("source", "golden"),
                "classification": inc, "expected": exp,
                "classification_accuracy": round(sum(cls_hits.values()) / len(cls_hits), 3) if cls_hits else None,
                "classification_detail": cls_hits,
                "retrieval_type_precision": round(len(same_type) / max(1, len(rep["cases"])), 3),
                "avg_similarity": round(sum(c.get("similarity") or 0 for c in rep["cases"]) / max(1, len(rep["cases"])), 3),
                "primary_strategy": rep["plan"].get("primary_strategy"),
                "judge": {"overall": rep["judge"]["overall_score"], "verdict": rep["judge"]["verdict"],
                          "scores": rep["judge"]["scores"]} if rep.get("judge") else None,
                "metrics": {}, "latency_ms": rep["total_ms"],
                "synapt": {k: (rep.get("graph") or {}).get("quality", {}).get(k)
                           for k in ("confidence", "knowledge_confidence", "procedural_confidence",
                                     "graph_confidence", "degraded")} if (rep.get("graph") or {}).get("quality") else None,
                "fact_check_passed": (rep.get("fact_check") or {}).get("passed"),
            }
            if model:
                actual = rep["summary"] + "\n\nPlan: " + json.dumps(rep["plan"], default=str)[:2500]
                tc = LLMTestCase(input=g["description"], actual_output=actual,
                                 retrieval_context=rep["retrieval_context"][:8])
                for m in _metrics(model):
                    name = getattr(m, "name", None) or m.__class__.__name__
                    try:
                        m.measure(tc)
                        row["metrics"][name] = {"score": round(float(m.score), 3), "passed": bool(m.is_successful()),
                                                "reason": (m.reason or "")[:400]}
                    except Exception as e:  # noqa: BLE001
                        row["metrics"][name] = {"score": None, "passed": False, "reason": f"error: {e}"[:300]}
            rows.append(row)
            _state["progress"] = i + 1

        names = sorted({n for r in rows for n in r["metrics"]})
        summary = {n: round(sum(r["metrics"][n]["score"] for r in rows if r["metrics"].get(n, {}).get("score") is not None) /
                            max(1, sum(1 for r in rows if r["metrics"].get(n, {}).get("score") is not None)), 3)
                   for n in names}
        ca = [r["classification_accuracy"] for r in rows if r["classification_accuracy"] is not None]
        js = [r["judge"]["overall"] for r in rows if r.get("judge")]
        syn_rows = [r["synapt"] for r in rows if r.get("synapt")]

        def syn_avg(k):
            v = [x[k] for x in syn_rows if isinstance(x.get(k), (int, float))]
            return round(sum(v) / len(v), 3) if v else None

        fc = [r["fact_check_passed"] for r in rows if r.get("fact_check_passed") is not None]
        out = {
            "ran_at": time.strftime("%Y-%m-%d %H:%M:%S"), "n_cases": len(rows),
            "evaluator_model": settings.JUDGE_MODEL if model else None,
            "deepeval_enabled": bool(model),
            "summary": {"deepeval": summary,
                        "classification_accuracy": round(sum(ca) / len(ca), 3) if ca else None,
                        "retrieval_type_precision": round(sum(r["retrieval_type_precision"] for r in rows) / len(rows), 3),
                        "avg_similarity": round(sum(r["avg_similarity"] for r in rows) / len(rows), 3),
                        "llm_judge_overall": round(sum(js) / len(js), 3) if js else None,
                        "avg_latency_ms": int(sum(r["latency_ms"] for r in rows) / len(rows)),
                        "fact_check_pass_rate": round(sum(fc) / len(fc), 3) if fc else None,
                        "synapt": {k: syn_avg(k) for k in ("confidence", "knowledge_confidence",
                                                           "procedural_confidence", "graph_confidence")} |
                                  {"degraded_rate": round(sum(bool(x.get("degraded")) for x in syn_rows) /
                                                          len(syn_rows), 3) if syn_rows else None,
                                   "n": len(syn_rows)}},
            "rows": rows,
        }
        RESULTS_PATH.write_text(json.dumps(out, indent=1, default=str))
    except Exception as e:  # noqa: BLE001
        log.error("Eval failed: %s", traceback.format_exc())
        _state["error"] = str(e)
    finally:
        _state["running"] = False
        _state["current"] = None

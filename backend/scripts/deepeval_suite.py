#!/usr/bin/env python3
"""
Automated DeepEval Suite.
Runs the 25 golden disruption incidents through the full multi-agent workflow and scores them with
DeepEval (AnswerRelevancy, Faithfulness, ContextualRelevancy, Recommendation Quality and Impact Analysis
Correctness G-Eval rubrics) and the LLM-as-Judge — the only place the external LLM is used — plus the deterministic fact-check, classification accuracy and
the 10-case guardrail suite. Synapt's own confidence signals are recorded next to the scores.

Writes artifacts/eval_results.json (also shown on the Quality & Learning page).

Run from backend/:  python scripts/deepeval_suite.py [--limit N] [--use-graph] [--no-feedback]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.prediction import registry  # noqa: E402
from services import evaluation, feedback  # noqa: E402
from services.data_store import store  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Run the DeepEval benchmark suite")
    parser.add_argument("--limit", type=int, default=None, help="Only the first N golden cases")
    parser.add_argument("--use-graph", action="store_true", help="Include Synapt graph-RAG in each workflow run")
    parser.add_argument("--no-feedback", action="store_true", help="Skip replaying low-rated feedback inputs")
    args = parser.parse_args()

    store.load()
    feedback.init()
    registry.load_or_train()
    t0 = time.time()
    evaluation.start(args.limit, args.use_graph, not args.no_feedback)
    while evaluation.status()["running"]:
        s = evaluation.status()
        print(f"\r[*] {s['progress']}/{s['total']} cases (current: {s['current']})", end="", flush=True)
        time.sleep(5)
    print()
    if evaluation.status()["error"]:
        sys.exit(f"[FAIL] {evaluation.status()['error']}")

    r = evaluation.results()
    print(f"[OK] {r['n_cases']} cases in {int(time.time() - t0)}s "
          f"({r["n_llm_cases"]} scored by the LLM judge, {r["n_fallback_cases"]} judge unreachable) -> {evaluation.RESULTS_PATH}")
    print(json.dumps(r["summary"], indent=1))


if __name__ == "__main__":
    main()

"""
Hold-out check of the precedent estimator (no trained model to fit).

Builds the precedent pool from 80% of the case history, estimates the other 20% from their cohorts and
reports R², MAE and P10-P90 coverage per target plus the AUC of the high-impact risk share.
Writes artifacts/precedent_validation.json, which /api/precedent and the Quality page show.

Run from backend/:  python scripts/validate_precedent.py   (takes a few minutes)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.precedent import VALIDATION_PATH, validate  # noqa: E402
from services.data_store import store  # noqa: E402


def main() -> None:
    store.load()
    res = validate()
    VALIDATION_PATH.write_text(json.dumps(res, indent=1))
    for t, m in res["targets"].items():
        print(f"{t:24s} " + "  ".join(f"{k} {v}" for k, v in m.items()))
    print(f"wrote {VALIDATION_PATH}")


if __name__ == "__main__":
    main()

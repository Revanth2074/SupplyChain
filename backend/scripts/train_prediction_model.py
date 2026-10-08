#!/usr/bin/env python3
"""
Prediction Model Training Script.
Trains the HistGradientBoosting models on all 100,000 disruptions (80/20 split): production impact,
revenue loss, partial and full recovery days (each with P10/P90 quantile models) and the high-impact
risk classifier. Reported outcomes from the feedback loop are added as extra training rows.

Writes models/disruption_predictors.joblib and models/prediction_metrics.json.

Run from backend/:  python scripts/train_prediction_model.py [--no-feedback]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.prediction import META_PATH, MODEL_PATH, registry  # noqa: E402
from services import feedback  # noqa: E402
from services.data_store import store  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Train the disruption prediction models")
    parser.add_argument("--no-feedback", action="store_true", help="Ignore outcomes reported by operators")
    args = parser.parse_args()

    store.INDEX_SIZE = 1000  # search index is not needed for training
    store.load()
    feedback.init()
    extra = None if args.no_feedback else feedback.outcome_rows()
    print(f"[*] Training on {len(store.df):,} cases"
          + (f" + {len(extra)} operator-reported outcomes" if extra is not None and len(extra) else ""))
    meta = registry.train(extra)

    print(f"[OK] Trained in {meta['train_seconds']}s -> {MODEL_PATH.name}, {META_PATH.name}")
    for tgt, m in meta["targets"].items():
        if "r2" in m:
            print(f"    {m['label']:<28} R2 {m['r2']:.3f}  MAE {m['mae']:,.2f}  P10-P90 coverage {m.get('interval_coverage', 0):.1%}")
        else:
            print(f"    {m['label']:<28} AUC {m['auc']:.3f}  positive rate {m['positive_rate']:.1%}")
    top = sorted(meta["targets"]["full_recovery_days"]["importance"].items(), key=lambda kv: -kv[1])[:4]
    print("[*] Top drivers of full recovery:", json.dumps({k: round(v, 3) for k, v in top}))


if __name__ == "__main__":
    main()

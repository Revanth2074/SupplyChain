"""Prediction models: production impact, revenue loss, recovery time, and
disruption-risk (high-impact probability) + resilience score + explainability."""
from __future__ import annotations

import json
import logging
import threading
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from . import faults
from .config import settings
from .data_store import store

log = logging.getLogger("ml")

CAT = ["disruption_type", "industry", "supplier_region", "supplier_size", "response_type"]
NUM = ["supplier_tier", "has_backup_supplier", "disruption_severity", "response_time_days"]
FEATURES = CAT + NUM
FEATURE_LABELS = {
    "disruption_type": "Disruption type", "industry": "Industry", "supplier_region": "Supplier region",
    "supplier_size": "Supplier size", "response_type": "Response strategy",
    "supplier_tier": "Supplier tier", "has_backup_supplier": "Backup supplier",
    "disruption_severity": "Severity", "response_time_days": "Response time (days)",
}
TARGETS = {
    "production_impact_pct": {"label": "Production impact (%)", "log": False},
    "revenue_loss_usd": {"label": "Revenue loss (USD)", "log": True},
    "full_recovery_days": {"label": "Full recovery (days)", "log": False},
    "partial_recovery_days": {"label": "Partial recovery (days)", "log": False},
}
QUANTILES = (0.1, 0.9)
# Fallback when the models are unavailable: statistics of the most similar historical cohort.
# Keys are dropped from the end (least important first) until the cohort has MIN_COHORT cases.
COHORT_KEYS = ("disruption_severity", "supplier_tier", "has_backup_supplier", "supplier_size",
               "response_type", "industry", "disruption_type", "supplier_region")
MIN_COHORT = 30
MODEL_PATH = settings.ARTIFACT_DIR / "models.joblib"
META_PATH = settings.ARTIFACT_DIR / "models_meta.json"


def _pipe(est) -> Pipeline:
    pre = ColumnTransformer([
        ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), CAT),
        ("num", "passthrough", NUM),
    ])
    return Pipeline([("pre", pre), ("est", est)])


def _cat_mask() -> list[bool]:
    return [True] * len(CAT) + [False] * len(NUM)


class ModelRegistry:
    def __init__(self) -> None:
        self.models: dict[str, Pipeline] = {}
        self.meta: dict = {}
        self.baseline: dict = {}
        self.risk_threshold: dict = {}
        self.ready = False
        self.training = False
        self._lock = threading.Lock()

    def _frame(self, df: pd.DataFrame) -> pd.DataFrame:
        X = df[FEATURES].copy()
        X["has_backup_supplier"] = X["has_backup_supplier"].astype(int)
        return X

    def load_or_train(self) -> None:
        if MODEL_PATH.exists() and META_PATH.exists():
            try:
                blob = joblib.load(MODEL_PATH)
                if all(f"{t}@q{int(q * 100)}" in blob["models"] for t in TARGETS for q in QUANTILES):
                    self.models, self.baseline, self.risk_threshold = blob["models"], blob["baseline"], blob["risk_threshold"]
                    self.meta = json.loads(META_PATH.read_text())
                    self.ready = True
                    log.info("Loaded models from disk")
                    return
                log.info("Saved models predate quantile ranges, retraining")
            except Exception as e:  # noqa: BLE001
                log.warning("Model load failed, retraining: %s", e)
        self.train()

    def train(self, extra: pd.DataFrame | None = None) -> dict:
        with self._lock:
            self.training = True
            t0 = time.time()
            df = store.df.reset_index(drop=True)
            if extra is not None and not extra.empty:
                df = pd.concat([df, extra], ignore_index=True)
            X = self._frame(df)
            Xtr, Xte, idx_tr, idx_te = train_test_split(X, df.index, test_size=0.2, random_state=42)
            models, meta = {}, {"trained_at": time.strftime("%Y-%m-%d %H:%M:%S"), "n_rows": len(df), "targets": {}}

            for tgt, cfg in TARGETS.items():
                y = df[tgt].astype(float)
                ytr, yte = y.loc[idx_tr], y.loc[idx_te]
                fit_y = np.log1p(ytr) if cfg["log"] else ytr
                m = _pipe(HistGradientBoostingRegressor(max_iter=300, learning_rate=0.08, max_leaf_nodes=48,
                                                        categorical_features=_cat_mask(), random_state=42))
                m.fit(Xtr, fit_y)
                pred = m.predict(Xte)
                pred = np.expm1(pred) if cfg["log"] else pred
                sample = Xte.sample(n=min(4000, len(Xte)), random_state=1)
                ys = np.log1p(y.loc[sample.index]) if cfg["log"] else y.loc[sample.index]
                pi = permutation_importance(m, sample, ys, n_repeats=3, random_state=0, n_jobs=1)
                imp = {f: round(float(v), 5) for f, v in zip(FEATURES, pi.importances_mean)}
                meta["targets"][tgt] = {
                    "label": cfg["label"], "mae": round(float(mean_absolute_error(yte, pred)), 3),
                    "r2": round(float(r2_score(yte, pred)), 4), "importance": imp,
                }
                models[tgt] = m

                # P10 / P90 quantile models -> prediction ranges
                qp = {}
                for q in QUANTILES:
                    mq = _pipe(HistGradientBoostingRegressor(loss="quantile", quantile=q, max_iter=200,
                                                             learning_rate=0.08, max_leaf_nodes=48,
                                                             categorical_features=_cat_mask(), random_state=42))
                    mq.fit(Xtr, fit_y)
                    pq = mq.predict(Xte)
                    qp[q] = np.expm1(pq) if cfg["log"] else pq
                    models[f"{tgt}@q{int(q * 100)}"] = mq
                lo, hi = np.minimum(qp[QUANTILES[0]], qp[QUANTILES[1]]), np.maximum(qp[QUANTILES[0]], qp[QUANTILES[1]])
                meta["targets"][tgt]["interval_coverage"] = round(float(((yte >= lo) & (yte <= hi)).mean()), 3)

            # --- disruption risk: high-impact event (top-quartile loss OR slow recovery OR severe impact)
            thr = {
                "revenue_loss_usd": float(df["revenue_loss_usd"].quantile(0.75)),
                "full_recovery_days": float(df["full_recovery_days"].quantile(0.75)),
                "production_impact_pct": 50.0,
            }
            yrisk = ((df["revenue_loss_usd"] >= thr["revenue_loss_usd"]) |
                     (df["full_recovery_days"] >= thr["full_recovery_days"]) |
                     (df["production_impact_pct"] >= thr["production_impact_pct"])).astype(int)
            clf = _pipe(HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=48,
                                                       categorical_features=_cat_mask(), random_state=42))
            clf.fit(Xtr, yrisk.loc[idx_tr])
            proba = clf.predict_proba(Xte)[:, 1]
            sample = Xte.sample(n=min(4000, len(Xte)), random_state=1)
            pi = permutation_importance(clf, sample, yrisk.loc[sample.index], n_repeats=3, random_state=0,
                                        scoring="roc_auc", n_jobs=1)
            meta["targets"]["risk"] = {
                "label": "High-impact disruption risk",
                "auc": round(float(roc_auc_score(yrisk.loc[idx_te], proba)), 4),
                "positive_rate": round(float(yrisk.mean()), 4), "thresholds": thr,
                "importance": {f: round(float(v), 5) for f, v in zip(FEATURES, pi.importances_mean)},
            }
            models["risk"] = clf

            base = {c: df[c].mode().iloc[0] for c in CAT}
            base.update({"supplier_tier": int(df["supplier_tier"].median()), "has_backup_supplier": 1,
                         "disruption_severity": int(df["disruption_severity"].median()),
                         "response_time_days": int(df["response_time_days"].median())})
            meta["train_seconds"] = round(time.time() - t0, 1)
            self.models, self.meta, self.baseline, self.risk_threshold = models, meta, base, thr
            joblib.dump({"models": models, "baseline": base, "risk_threshold": thr}, MODEL_PATH)
            META_PATH.write_text(json.dumps(meta, indent=1))
            self.ready, self.training = True, False
            log.info("Models trained in %.1fs", meta["train_seconds"])
            return meta

    # ---------------- inference ----------------
    def _row(self, inc: dict) -> pd.DataFrame:
        r = {}
        for f in FEATURES:
            v = inc.get(f)
            if v is None or v == "":
                v = self.baseline[f]
            r[f] = v
        r["has_backup_supplier"] = int(bool(r["has_backup_supplier"]))
        r["supplier_tier"] = int(r["supplier_tier"])
        r["disruption_severity"] = int(r["disruption_severity"])
        r["response_time_days"] = int(r["response_time_days"])
        return pd.DataFrame([r])[FEATURES]

    # ---------------- cohort-statistics fallback ----------------
    def fallback(self) -> bool:
        return faults.active("ml") or not self.models

    def _cohort(self, row: tuple) -> dict:
        """Median, P10/P90 and high-impact share of the closest historical cohort for one feature row."""
        cache = self.__dict__.setdefault("_cohort_cache", {})
        if row in cache:
            return cache[row]
        df = store.df
        cols = self.__dict__.setdefault("_cohort_cols", {})
        vals = dict(zip(FEATURES, row))
        keys = list(COHORT_KEYS)
        while True:
            m = np.ones(len(df), dtype=bool)
            for k in keys:
                if k not in cols:
                    cols[k] = df[k].astype(int).to_numpy() if k == "has_backup_supplier" else df[k].to_numpy()
                m &= cols[k] == vals[k]
            if m.sum() >= MIN_COHORT or not keys:
                break
            keys.pop()
        sub = df[m]
        out = {"_n": int(len(sub)), "_matched_on": keys}
        for t in TARGETS:
            col = sub[t].astype(float)
            out[t] = float(col.median())
            for q in QUANTILES:
                out[f"{t}@q{int(q * 100)}"] = float(col.quantile(q))
        thr = self.risk_threshold or {"revenue_loss_usd": float(df["revenue_loss_usd"].quantile(.75)),
                                      "full_recovery_days": float(df["full_recovery_days"].quantile(.75)),
                                      "production_impact_pct": 50.0}
        out["risk"] = float(((sub["revenue_loss_usd"] >= thr["revenue_loss_usd"]) |
                             (sub["full_recovery_days"] >= thr["full_recovery_days"]) |
                             (sub["production_impact_pct"] >= thr["production_impact_pct"])).mean())
        if len(cache) > 5000:
            cache.clear()
        cache[row] = out
        return out

    def _cohort_rows(self, X: pd.DataFrame, key: str) -> np.ndarray:
        return np.array([self._cohort(tuple(_py(v) for v in r))[key] for r in X[FEATURES].itertuples(index=False)])

    def _pred(self, tgt: str, X: pd.DataFrame) -> np.ndarray:
        if self.fallback():
            return self._cohort_rows(X, tgt)
        m = self.models[tgt]
        if tgt == "risk":
            return m.predict_proba(X)[:, 1]
        p = m.predict(X)
        return np.expm1(p) if TARGETS[tgt]["log"] else p

    def _quantile(self, tgt: str, q: float, X: pd.DataFrame) -> np.ndarray:
        if self.fallback():
            return self._cohort_rows(X, f"{tgt}@q{int(q * 100)}")
        p = self.models[f"{tgt}@q{int(q * 100)}"].predict(X)
        return np.expm1(p) if TARGETS[tgt]["log"] else p

    def support(self, inc: dict) -> dict:
        """How many historical cases share this incident's profile -> trust in the prediction."""
        df = store.df
        keys = [k for k in ("disruption_type", "industry", "supplier_region", "supplier_tier",
                            "has_backup_supplier", "disruption_severity") if inc.get(k) not in (None, "")]
        m = np.ones(len(df), dtype=bool)
        for k in keys:
            if k == "has_backup_supplier":
                v = bool(inc[k])
            elif k in ("supplier_tier", "disruption_severity"):
                v = int(inc[k])
            else:
                v = inc[k]
            m &= (df[k] == v).to_numpy()
        n = int(m.sum())
        level = "high" if n >= 100 else "medium" if n >= 30 else "low"
        warning = None
        if level == "low":
            warning = (f"Insufficient history: only {n} past case(s) match this exact profile "
                       f"({', '.join(keys)}). Treat the predictions as indicative and rely on the wider ranges.")
        return {"matching_cases": n, "level": level, "matched_on": keys, "warning": warning}

    def predict(self, inc: dict) -> dict:
        X = self._row(inc)
        out = {t: float(self._pred(t, X)[0]) for t in TARGETS}
        ranges = {}
        for t in TARGETS:
            a, b = (float(self._quantile(t, q, X)[0]) for q in QUANTILES)
            lo, hi = min(a, b, out[t]), max(a, b, out[t])
            if t == "production_impact_pct":
                lo, hi = max(lo, 0), min(hi, 100)
            nd = 1 if t == "production_impact_pct" else 0
            ranges[t] = {"p10": round(max(lo, 0), nd), "p90": round(hi, nd)}
        risk = float(self._pred("risk", X)[0])
        out["production_impact_pct"] = round(min(max(out["production_impact_pct"], 0), 100), 1)
        out["revenue_loss_usd"] = round(max(out["revenue_loss_usd"], 0), 0)
        out["full_recovery_days"] = round(max(out["full_recovery_days"], 1), 0)
        out["partial_recovery_days"] = round(max(out["partial_recovery_days"], 1), 0)
        out["risk_probability"] = round(risk, 3)
        out["risk_level"] = "Critical" if risk >= .75 else "High" if risk >= .5 else "Medium" if risk >= .25 else "Low"
        out["ranges"] = ranges
        out["support"] = self.support(inc)
        out["resilience_score"] = self.resilience(inc, out)
        out["inputs_used"] = {k: (v.item() if hasattr(v, "item") else v) for k, v in X.iloc[0].to_dict().items()}
        if self.fallback():
            c = self._cohort(tuple(_py(v) for v in X.iloc[0][FEATURES]))
            out["method"] = "cohort-statistics"
            out["cohort"] = {"cases": c["_n"], "matched_on": c["_matched_on"],
                             "note": "Prediction models unavailable: median and P10/P90 of the most similar "
                                     "historical cases."}
        else:
            out["method"] = "model"
        return out

    def predict_batch(self, rows: list[dict]) -> pd.DataFrame:
        """Vectorised point predictions + risk for many incidents (portfolio scoring)."""
        X = pd.concat([self._row(r) for r in rows], ignore_index=True)
        out = pd.DataFrame({t: self._pred(t, X) for t in TARGETS})
        out["risk_probability"] = self._pred("risk", X)
        out["production_impact_pct"] = out["production_impact_pct"].clip(0, 100)
        out["revenue_loss_usd"] = out["revenue_loss_usd"].clip(lower=0)
        return out

    def whatif(self, inc: dict) -> dict:
        """Counterfactuals: re-predict with one lever changed and report the deltas vs the base case."""
        base = self.predict(inc)
        used = base["inputs_used"]
        rt = int(used["response_time_days"])
        cur = used["response_type"]
        scen = []
        if not used["has_backup_supplier"]:
            scen.append(("backup", "Had a qualified backup supplier", {"has_backup_supplier": True}))
        if rt > 0:
            d = min(5, rt)
            scen.append(("faster", f"Responded {d} day{'s' if d > 1 else ''} sooner", {"response_time_days": rt - d}))
            if rt > d:
                scen.append(("same_day", "Responded the same day", {"response_time_days": 0}))
        if int(used["supplier_tier"]) > 1:
            scen.append(("tier1", "Sourced directly from a Tier 1 supplier", {"supplier_tier": 1}))
        for st in sorted(store.df["response_type"].unique()):
            if st != cur:
                scen.append((f"strategy:{st}", f"Used {st} instead of {cur}", {"response_type": st}))

        def summarise(p):
            return {"production_impact_pct": p["production_impact_pct"], "revenue_loss_usd": p["revenue_loss_usd"],
                    "partial_recovery_days": p["partial_recovery_days"], "full_recovery_days": p["full_recovery_days"],
                    "risk_probability": p["risk_probability"], "resilience": p["resilience_score"]["score"]}

        b = summarise(base)

        def run(key, label, change):
            p = summarise(self.predict({**inc, **change}))
            return {"key": key, "label": label, "change": change, "prediction": p,
                    "delta": {k: round(p[k] - b[k], 3) for k in b}}

        rows = sorted((run(*sc) for sc in scen), key=lambda r: r["delta"]["full_recovery_days"])

        def helps(r):
            d = r["delta"]
            return d["full_recovery_days"] < 0 or (d["full_recovery_days"] == 0 and d["revenue_loss_usd"] < 0)

        combo_change, levers = {}, set()
        for r in rows:  # sorted best-first, so the first helpful lever of each kind wins
            lever = ("strategy" if r["key"].startswith("strategy:")
                     else "response" if r["key"] in ("faster", "same_day") else r["key"])
            if helps(r) and lever not in levers:
                combo_change.update(r["change"])
                levers.add(lever)
        combo = run("combined", "All improvements together", combo_change) if len(combo_change) > 1 else None
        return {"base": {"inputs": used, "prediction": b, "ranges": base["ranges"], "support": base["support"]},
                "scenarios": rows, "combined": combo}

    def resilience(self, inc: dict, pred: dict) -> dict:
        """0-100 resilience score combining structural and predicted outcome factors."""
        tier = int(inc.get("supplier_tier") or self.baseline["supplier_tier"])
        backup = bool(inc.get("has_backup_supplier")) if inc.get("has_backup_supplier") is not None else True
        size = inc.get("supplier_size") or "Medium"
        comp = {
            "backup_supplier": 25 if backup else 0,
            "supplier_tier": {1: 10, 2: 15, 3: 20, 4: 20}.get(tier, 15) * 0.75,
            "supplier_size": {"Large": 15, "Medium": 10, "Small": 5}.get(size, 10),
            "recovery_speed": max(0.0, 25 * (1 - pred["full_recovery_days"] / 200)),
            "impact_absorption": max(0.0, 20 * (1 - pred["production_impact_pct"] / 100)),
        }
        score = round(sum(comp.values()), 1)
        band = "Strong" if score >= 70 else "Moderate" if score >= 50 else "Weak"
        return {"score": score, "band": band, "components": {k: round(v, 1) for k, v in comp.items()}}

    def explain(self, inc: dict) -> dict:
        """Local explanation: contribution of each feature = pred(actual) - pred(feature set to baseline).
        Plus global permutation importance from training."""
        X = self._row(inc)
        res = {}
        for tgt in list(TARGETS) + ["risk"]:
            base_pred = float(self._pred(tgt, X)[0])
            contribs = []
            for f in FEATURES:
                Xb = X.copy()
                Xb[f] = self.baseline[f] if f != "has_backup_supplier" else int(self.baseline[f])
                alt = float(self._pred(tgt, Xb)[0])
                contribs.append({"feature": f, "label": FEATURE_LABELS[f], "value": _py(X.iloc[0][f]),
                                 "baseline": _py(self.baseline[f]), "contribution": round(base_pred - alt, 4)})
            contribs.sort(key=lambda c: -abs(c["contribution"]))
            gi = self.meta["targets"][tgt]["importance"]
            res[tgt] = {
                "label": self.meta["targets"][tgt]["label"], "prediction": round(base_pred, 4),
                "local": contribs,
                "global": sorted([{"feature": f, "label": FEATURE_LABELS[f], "importance": v} for f, v in gi.items()],
                                 key=lambda d: -d["importance"]),
            }
        return res


def _py(v):
    return v.item() if hasattr(v, "item") else v


registry = ModelRegistry()

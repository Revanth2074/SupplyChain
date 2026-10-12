"""Precedent estimator: production impact, revenue loss, recovery time and high-impact risk from what
happened to comparable past disruptions. No trained model.

Two sources of precedent:
  * Synapt (trident_get_chunks): the nearest past cases to this incident, found semantically in the
    knowledge base. They are the evidence shown with every estimate and a cross-check on the numbers.
  * The cohort: every case in the history (the same cases Synapt was built from) that shares this
    incident's profile. Keys are dropped from the end of COHORT_KEYS (least telling first) until at
    least MIN_COHORT cases match. The estimate is the cohort median with its P10 / P90, and the risk is
    the cohort's share of high-impact outcomes.

Counterfactuals (what-if, strategy comparison) and explanations re-read the cohort with one attribute
changed, so every number traces back to a set of real cases."""
from __future__ import annotations

import json
import logging
import threading
import time

import numpy as np
import pandas as pd

from config import settings
from services.data_store import store

log = logging.getLogger("precedent")

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
    "production_impact_pct": {"label": "Production impact (%)"},
    "revenue_loss_usd": {"label": "Revenue loss (USD)"},
    "full_recovery_days": {"label": "Full recovery (days)"},
    "partial_recovery_days": {"label": "Partial recovery (days)"},
}
QUANTILES = (0.1, 0.9)
# Most telling first (chosen on a 20% hold-out). Response time is matched in bands.
COHORT_KEYS = ("disruption_severity", "supplier_size", "supplier_tier", "industry", "has_backup_supplier",
               "rt_band", "response_type", "disruption_type", "supplier_region")
RT_BANDS = (-1, 2, 7, 14, 10_000)
RT_BAND_LABELS = ("0-2 d", "3-7 d", "8-14 d", "15+ d")
MIN_COHORT = 30
MIN_COMPARE = 100   # each side of a comparison (what-if, drivers) needs this many cases, so deltas are not noise
SYNAPT_TOP_K = 20
VALIDATION_PATH = settings.ARTIFACT_DIR / "precedent_validation.json"


def rt_band(days) -> int:
    return int(np.searchsorted(RT_BANDS, float(days), side="left") - 1)


def _py(v):
    return v.item() if hasattr(v, "item") else v


def _risk_flags(df: pd.DataFrame, thr: dict) -> np.ndarray:
    return ((df["revenue_loss_usd"] >= thr["revenue_loss_usd"]) |
            (df["full_recovery_days"] >= thr["full_recovery_days"]) |
            (df["production_impact_pct"] >= thr["production_impact_pct"])).to_numpy()


def _wmedian(values, weights) -> float:
    o = np.argsort(values)
    v, w = np.asarray(values, float)[o], np.asarray(weights, float)[o]
    c = np.cumsum(w)
    return float(v[np.searchsorted(c, c[-1] / 2)])


class PrecedentEstimator:
    def __init__(self) -> None:
        self.df: pd.DataFrame | None = None
        self.meta: dict = {}
        self.baseline: dict = {}
        self.risk_threshold: dict = {}
        self.ready = False
        self.refreshing = False
        self._cols: dict = {}
        self._cache: dict = {}
        self._synapt_cache: dict = {}
        self._lock = threading.Lock()

    # ---------------- precedent pool ----------------
    def load(self, extra: pd.DataFrame | None = None) -> dict:
        """Build the precedent pool from the case history (+ outcomes operators reported)."""
        with self._lock:
            self.refreshing = True
            t0 = time.time()
            df = store.df.reset_index(drop=True)
            if extra is not None and not extra.empty:
                # only complete operator outcomes join the pool
                extra = extra.dropna(subset=[*FEATURES, "full_recovery_days"])
                df = pd.concat([df, extra], ignore_index=True)
            df = df.copy()
            df["has_backup_supplier"] = df["has_backup_supplier"].astype(int)
            df["rt_band"] = np.searchsorted(RT_BANDS, df["response_time_days"].astype(float).to_numpy(), side="left") - 1
            thr = {"revenue_loss_usd": float(df["revenue_loss_usd"].quantile(0.75)),
                   "full_recovery_days": float(df["full_recovery_days"].quantile(0.75)),
                   "production_impact_pct": 50.0}
            df["_risk"] = _risk_flags(df, thr).astype(float)
            base = {c: df[c].mode().iloc[0] for c in CAT}
            base.update({"supplier_tier": int(df["supplier_tier"].median()), "has_backup_supplier": 1,
                         "disruption_severity": int(df["disruption_severity"].median()),
                         "response_time_days": int(df["response_time_days"].median())})
            self.df, self.risk_threshold, self.baseline = df, thr, base
            self._cols = {k: df[k].to_numpy() for k in COHORT_KEYS}
            self._cache.clear()
            meta = {"method": "precedent statistics", "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "n_cases": int(len(df)), "feedback_rows": int(len(extra)) if extra is not None else 0,
                    "min_cohort": MIN_COHORT, "cohort_keys": list(COHORT_KEYS), "synapt_top_k": SYNAPT_TOP_K,
                    "targets": {t: {"label": c["label"], "spread": self._spread(t)} for t, c in TARGETS.items()}}
            meta["targets"]["risk"] = {"label": "High-impact disruption risk", "thresholds": thr,
                                       "positive_rate": round(float(df["_risk"].mean()), 4), "spread": self._spread("_risk")}
            if VALIDATION_PATH.exists():
                meta["validation"] = json.loads(VALIDATION_PATH.read_text())
            meta["build_seconds"] = round(time.time() - t0, 1)
            self.meta, self.ready, self.refreshing = meta, True, False
            log.info("Precedent pool ready: %d cases in %.1fs", len(df), meta["build_seconds"])
            return meta

    def _spread(self, tgt: str) -> list[dict]:
        """How much each attribute separates outcomes in the history: the share of the variance of the
        target explained by grouping on that attribute alone (eta squared). Descriptive, not a model."""
        df = self.df
        y = df[tgt].astype(float)
        tot = float(((y - y.mean()) ** 2).sum()) or 1.0
        out = []
        for f in FEATURES:
            key = "rt_band" if f == "response_time_days" else f
            g = df.groupby(key)[tgt].agg(["mean", "count"])
            between = float((g["count"] * (g["mean"] - y.mean()) ** 2).sum())
            out.append({"feature": f, "label": FEATURE_LABELS[f], "importance": round(between / tot, 5)})
        return sorted(out, key=lambda d: -d["importance"])

    def _row(self, inc: dict) -> dict:
        r = {}
        for f in FEATURES:
            v = inc.get(f)
            r[f] = self.baseline[f] if v is None or v == "" else v
        r["has_backup_supplier"] = int(bool(r["has_backup_supplier"]))
        for k in ("supplier_tier", "disruption_severity", "response_time_days"):
            r[k] = int(r[k])
        r["rt_band"] = rt_band(r["response_time_days"])
        return r

    def cohort(self, inc: dict, keep: tuple = (), pair: dict | None = None) -> dict:
        """Median, P10/P90 and high-impact share of the closest cohort of past cases.
        For a comparison (what-if, drivers): attributes in `keep` (the lever being changed) are never
        dropped, and `pair` is the other side of the comparison; both sides are matched on the same
        attributes, so the difference comes from the lever and not from a different cohort."""
        r = self._row(inc)
        o = self._row(pair) if pair else None
        keep = tuple("rt_band" if k == "response_time_days" else k for k in keep if k in FEATURES)
        key = (tuple(_py(r[k]) for k in COHORT_KEYS), keep, tuple(_py(o[k]) for k in COHORT_KEYS) if o else None)
        if key in self._cache:
            return self._cache[key]
        df, cols = self.df, self._cols
        need = MIN_COMPARE if (keep or o) else MIN_COHORT
        keys = list(COHORT_KEYS)
        while True:
            m = np.ones(len(df), dtype=bool)
            mo = np.ones(len(df), dtype=bool)
            for k in keys:
                m &= cols[k] == r[k]
                if o:
                    mo &= cols[k] == o[k]
            droppable = [k for k in keys if k not in keep]
            if (m.sum() >= need and (not o or mo.sum() >= need)) or not droppable:
                break
            keys.remove(droppable[-1])
        if not m.any() and (keep or o):  # a value no past case has (e.g. a new strategy): plain cohort
            return self.cohort(inc)
        sub = df[m]
        out = {"n": int(len(sub)), "matched_on": [k if k != "rt_band" else "response_time_days" for k in keys],
               "risk": float(sub["_risk"].mean()),
               "example_ids": sub["disruption_id"].head(5).tolist()}
        for t in TARGETS:
            col = sub[t].astype(float)
            out[t] = float(col.median())
            for q in QUANTILES:
                out[f"{t}@q{int(q * 100)}"] = float(col.quantile(q))
        if len(self._cache) > 20000:
            self._cache.clear()
        self._cache[key] = out
        return out

    # ---------------- Synapt precedents ----------------
    @staticmethod
    def query_text(inc: dict) -> str:
        parts = [inc.get("description") or ""]
        for k, fmt in (("disruption_type", "Disruption type: {}."), ("industry", "Industry: {}."),
                       ("supplier_tier", "Supplier tier: Tier {}."), ("supplier_region", "Supplier region: {}."),
                       ("supplier_size", "Supplier size: {}."), ("disruption_severity", "Severity was {} out of 5."),
                       ("response_type", "Response strategy: {}.")):
            if inc.get(k) not in (None, ""):
                parts.append(fmt.format(inc[k]))
        if inc.get("has_backup_supplier") is not None:
            parts.append("The supplier had a backup supplier." if inc["has_backup_supplier"]
                         else "The supplier had no backup supplier.")
        return " ".join(p for p in parts if p).strip()

    def synapt_precedents(self, inc: dict, top_k: int = SYNAPT_TOP_K) -> dict:
        """Ask Synapt (trident_get_chunks) for the nearest past cases and summarise what happened to them:
        similarity-weighted median outcomes over the closest matches."""
        from agents import synapt_tools as syn
        from agents.retrieval import similarity
        q = self.query_text(inc)
        if q in self._synapt_cache:
            return self._synapt_cache[q]
        t0 = time.time()
        seen, cases = set(), []
        for h in syn.get_chunks(q, top_k=top_k):
            cid = h.get("id")
            if cid and cid not in seen and (c := store.get_case(cid)):
                seen.add(cid)
                cases.append({**c, "similarity": similarity(c, inc) or 0.0})
        cases.sort(key=lambda c: -c["similarity"])
        close = [c for c in cases if c["similarity"] >= 0.75] or cases[:10]
        out = {"source": "synapt", "query": q, "found": len(cases), "used": len(close),
               "avg_similarity": round(float(np.mean([c["similarity"] for c in close])), 3) if close else None,
               "case_ids": [c["disruption_id"] for c in close[:10]],
               "latency_ms": int((time.time() - t0) * 1000)}
        if close:
            w = [max(c["similarity"], 0.05) ** 4 for c in close]
            for t in TARGETS:
                out[t] = round(_wmedian([c[t] for c in close], w), 1)
            out["risk"] = round(float(np.average(_risk_flags(pd.DataFrame(close), self.risk_threshold), weights=w)), 3)
        if len(self._synapt_cache) > 500:
            self._synapt_cache.clear()
        self._synapt_cache[q] = out
        return out

    # ---------------- estimates ----------------
    def support(self, inc: dict) -> dict:
        """How many past cases share this incident's profile -> trust in the estimate."""
        df = self.df
        keys = [k for k in ("disruption_type", "industry", "supplier_region", "supplier_tier",
                            "has_backup_supplier", "disruption_severity") if inc.get(k) not in (None, "")]
        m = np.ones(len(df), dtype=bool)
        for k in keys:
            v = int(bool(inc[k])) if k == "has_backup_supplier" else int(inc[k]) if k in ("supplier_tier", "disruption_severity") else inc[k]
            m &= (df[k] == v).to_numpy()
        n = int(m.sum())
        level = "high" if n >= 100 else "medium" if n >= 30 else "low"
        warning = None
        if level == "low":
            warning = (f"Insufficient history: only {n} past case(s) match this exact profile "
                       f"({', '.join(keys)}). Treat the estimates as indicative and rely on the wider ranges.")
        return {"matching_cases": n, "level": level, "matched_on": keys, "warning": warning}

    def predict(self, inc: dict, synapt: bool = False, keep: tuple = (), pair: dict | None = None) -> dict:
        """Cohort estimate with P10-P90 ranges. With synapt=True the nearest Synapt precedents are
        attached as evidence and cross-check. keep / pair: see cohort()."""
        c = self.cohort(inc, keep, pair)
        out = {t: c[t] for t in TARGETS}
        ranges = {}
        for t in TARGETS:
            lo, hi = c[f"{t}@q10"], c[f"{t}@q90"]
            nd = 1 if t == "production_impact_pct" else 0
            ranges[t] = {"p10": round(max(lo, 0), nd), "p90": round(hi, nd)}
        risk = c["risk"]
        out["production_impact_pct"] = round(min(max(out["production_impact_pct"], 0), 100), 1)
        out["revenue_loss_usd"] = round(max(out["revenue_loss_usd"], 0), 0)
        out["full_recovery_days"] = round(max(out["full_recovery_days"], 1), 0)
        out["partial_recovery_days"] = round(max(out["partial_recovery_days"], 1), 0)
        out["risk_probability"] = round(risk, 3)
        out["risk_level"] = "Critical" if risk >= .75 else "High" if risk >= .5 else "Medium" if risk >= .25 else "Low"
        out["ranges"] = ranges
        out["support"] = self.support(inc)
        out["resilience_score"] = self.resilience(inc, out)
        r = self._row(inc)
        out["inputs_used"] = {f: _py(r[f]) for f in FEATURES}
        out["method"] = "precedent statistics"
        out["cohort"] = {"cases": c["n"], "matched_on": c["matched_on"], "example_ids": c["example_ids"],
                         "note": "Median and P10-P90 of the most similar past cases."}
        if synapt:
            out["synapt_precedents"] = self.synapt_precedents(inc)
        return out

    def predict_batch(self, rows: list[dict]) -> pd.DataFrame:
        """Cohort estimates + risk for many incidents (portfolio scoring)."""
        cs = [self.cohort(r) for r in rows]
        out = pd.DataFrame({t: [c[t] for c in cs] for t in TARGETS})
        out["risk_probability"] = [c["risk"] for c in cs]
        return out

    def whatif(self, inc: dict) -> dict:
        """Counterfactuals: re-read the cohort with one lever changed and report the deltas vs the base case."""
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
        for st in sorted(self.df["response_type"].dropna().unique()):
            if st != cur:
                scen.append((f"strategy:{st}", f"Used {st} instead of {cur}", {"response_type": st}))

        def summarise(p):
            return {"production_impact_pct": p["production_impact_pct"], "revenue_loss_usd": p["revenue_loss_usd"],
                    "partial_recovery_days": p["partial_recovery_days"], "full_recovery_days": p["full_recovery_days"],
                    "risk_probability": p["risk_probability"], "resilience": p["resilience_score"]["score"]}

        b = summarise(base)

        def run(key, label, change):
            # compare like for like: both sides keep the changed attributes in their cohorts
            keep, new = tuple(change), {**inc, **change}
            p = self.predict(new, keep=keep, pair=inc)
            s = summarise(p)
            ref = summarise(self.predict(inc, keep=keep, pair=new)) if keep else b
            return {"key": key, "label": label, "change": change, "prediction": s, "cohort_cases": p["cohort"]["cases"],
                    "delta": {k: round(s[k] - ref[k], 3) for k in b}}

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
        return {"base": {"inputs": used, "prediction": b, "ranges": base["ranges"], "support": base["support"],
                         "cohort": base["cohort"]},
                "scenarios": rows, "combined": combo, "method": "precedent statistics"}

    def resilience(self, inc: dict, pred: dict) -> dict:
        """0-100 resilience score combining structural and estimated outcome factors."""
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
        """Local drivers: for each attribute, how the cohort outcome changes when that attribute is set to
        the most common value (cohort(actual) - cohort(attribute at baseline)). Global: how much each
        attribute separates outcomes across the whole history."""
        r = self._row(inc)
        res = {}
        base_c = self.cohort(inc)
        for tgt in list(TARGETS) + ["risk"]:
            key = "risk" if tgt == "risk" else tgt
            contribs = []
            for f in FEATURES:
                alt_inc = {**inc, f: self.baseline[f]}
                ref = self.cohort(inc, (f,), alt_inc)[key]
                alt = self.cohort(alt_inc, (f,), inc)[key]
                contribs.append({"feature": f, "label": FEATURE_LABELS[f], "value": _py(r[f]),
                                 "baseline": _py(self.baseline[f]), "contribution": round(ref - alt, 4)})
            contribs.sort(key=lambda c: -abs(c["contribution"]))
            res[tgt] = {"label": self.meta["targets"][tgt]["label"], "prediction": round(base_c[key], 4),
                        "local": contribs, "global": self.meta["targets"][tgt]["spread"],
                        "cohort_cases": base_c["n"]}
        return res


def _r2(y, p) -> float:
    return 1 - float(((y - p) ** 2).sum()) / float(((y - y.mean()) ** 2).sum())


def _auc(y, score) -> float:
    """Probability that a random high-impact case scores above a random other case (ties count half)."""
    r = pd.Series(score).rank().to_numpy()
    pos = y.astype(bool)
    n1, n0 = pos.sum(), (~pos).sum()
    return float((r[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def validate(test_share: float = 0.2, seed: int = 42) -> dict:
    """Hold-out check: build cohorts from 80% of the history and estimate the other 20%."""
    est = PrecedentEstimator()
    df = store.df.reset_index(drop=True)
    te = np.random.default_rng(seed).random(len(df)) < test_share
    est_df, test = df[~te], df[te]
    store_df, store.df = store.df, est_df
    try:
        est.load()
    finally:
        store.df = store_df
    preds = [est.cohort(r) for r in test[FEATURES].to_dict("records")]
    out = {"method": "hold-out", "test_cases": int(len(test)), "train_cases": int(len(est_df)), "targets": {}}
    for t in TARGETS:
        p = np.array([c[t] for c in preds])
        lo = np.array([c[f"{t}@q10"] for c in preds])
        hi = np.array([c[f"{t}@q90"] for c in preds])
        y = test[t].to_numpy(float)
        out["targets"][t] = {"r2": round(_r2(y, p), 4), "mae": round(float(np.abs(y - p).mean()), 3),
                             "interval_coverage": round(float(((y >= lo) & (y <= hi)).mean()), 3)}
    yr = _risk_flags(test, est.risk_threshold)
    out["targets"]["risk"] = {"auc": round(_auc(yr, [c["risk"] for c in preds]), 4)}
    out["validated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return out


estimator = PrecedentEstimator()

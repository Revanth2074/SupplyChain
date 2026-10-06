"""Local dataset store: CSV loading, case text rendering, BM25 keyword index and
LSA semantic index (used for hybrid search + fallback when Synapt is down)."""
from __future__ import annotations

import logging
import re
import threading
from typing import Any

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from .config import settings

log = logging.getLogger("data")

CATEGORICAL = ["disruption_type", "industry", "supplier_tier", "supplier_region",
               "supplier_size", "has_backup_supplier", "response_type"]
TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def impact_band(p: float) -> str:
    return "Severe" if p >= 50 else "High" if p >= 35 else "Moderate" if p >= 20 else "Low"


def loss_band(v: float) -> str:
    if v < 1e6:
        return "Under 1M"
    if v < 5e6:
        return "1M to 5M"
    if v < 25e6:
        return "5M to 25M"
    return "Over 25M"


def recovery_band(d: float) -> str:
    return "Fast" if d <= 30 else "Normal" if d <= 60 else "Slow" if d <= 120 else "Very Slow"


def case_text(r: dict) -> str:
    backup = "had a backup supplier" if r["has_backup_supplier"] else "had no backup supplier"
    change = "was permanently replaced" if r["permanent_supplier_change"] else "relationship was kept"
    return (
        f"Disruption type: {r['disruption_type']}. Industry: {r['industry']}. "
        f"Supplier tier: Tier {r['supplier_tier']}. Supplier region: {r['supplier_region']}. "
        f"Supplier size: {r['supplier_size']}. The supplier {backup}. "
        f"Severity was {r['disruption_severity']} out of 5. Production impact was "
        f"{r['production_impact_pct']}% ({impact_band(r['production_impact_pct'])}). Revenue loss was "
        f"${r['revenue_loss_usd']:,.0f} ({loss_band(r['revenue_loss_usd'])}). Response strategy: "
        f"{r['response_type']}, started after {r['response_time_days']} days. Partial recovery took "
        f"{r['partial_recovery_days']} days and full recovery took {r['full_recovery_days']} days "
        f"({recovery_band(r['full_recovery_days'])}). The supplier {change}."
    )


class DataStore:
    """Loads the full dataset; builds indexes over a stratified index sample to
    keep startup fast while the full frame is used for stats & ML."""

    INDEX_SIZE = 100000  # index every historical case for keyword + local semantic search

    def __init__(self) -> None:
        self.df: pd.DataFrame | None = None
        self.idx_df: pd.DataFrame | None = None
        self.bm25: BM25Okapi | None = None
        self.tfidf: TfidfVectorizer | None = None
        self.svd: TruncatedSVD | None = None
        self.lsa: np.ndarray | None = None
        self.ready = False
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            if self.ready:
                return
            log.info("Loading dataset %s", settings.DATA_CSV)
            df = pd.read_csv(settings.DATA_CSV)
            for b in ("has_backup_supplier", "permanent_supplier_change"):
                df[b] = df[b].astype(str).str.lower().eq("true")
            self.df = df.set_index("disruption_id", drop=False)

            idx = df.sample(n=min(self.INDEX_SIZE, len(df)), random_state=42).reset_index(drop=True)
            idx["text"] = [case_text(r) for r in idx.to_dict("records")]
            self.idx_df = idx
            self.bm25 = BM25Okapi([tokenize(t) for t in idx["text"]])
            self.tfidf = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
            X = self.tfidf.fit_transform(idx["text"])
            self.svd = TruncatedSVD(n_components=96, random_state=42)
            self.lsa = normalize(self.svd.fit_transform(X))
            self.ready = True
            log.info("DataStore ready: %d rows, %d indexed", len(df), len(idx))

    # -------------- filtering --------------
    @staticmethod
    def apply_filters(df: pd.DataFrame, f: dict | None) -> pd.DataFrame:
        if not f:
            return df
        m = pd.Series(True, index=df.index)
        for col in ("disruption_type", "industry", "supplier_region", "supplier_size", "response_type"):
            vals = f.get(col)
            if vals:
                vals = vals if isinstance(vals, list) else [vals]
                m &= df[col].isin(vals)
        if f.get("supplier_tier"):
            tiers = f["supplier_tier"] if isinstance(f["supplier_tier"], list) else [f["supplier_tier"]]
            m &= df["supplier_tier"].isin([int(t) for t in tiers])
        if f.get("severity_min") is not None:
            m &= df["disruption_severity"] >= int(f["severity_min"])
        if f.get("severity_max") is not None:
            m &= df["disruption_severity"] <= int(f["severity_max"])
        if f.get("disruption_severity"):
            sv = f["disruption_severity"] if isinstance(f["disruption_severity"], list) else [f["disruption_severity"]]
            m &= df["disruption_severity"].isin([int(s) for s in sv])
        if f.get("has_backup_supplier") is not None:
            m &= df["has_backup_supplier"] == bool(f["has_backup_supplier"])
        return df[m]

    # -------------- search --------------
    def keyword_search(self, query: str, filters: dict | None, k: int) -> list[tuple[str, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        return self._rank(scores, filters, k)

    def semantic_search(self, query: str, filters: dict | None, k: int) -> list[tuple[str, float]]:
        q = normalize(self.svd.transform(self.tfidf.transform([query])))
        scores = (self.lsa @ q.T).ravel()
        return self._rank(scores, filters, k)

    def _rank(self, scores: np.ndarray, filters: dict | None, k: int) -> list[tuple[str, float]]:
        cand = self.apply_filters(self.idx_df, filters)
        if cand.empty:
            return []
        s = scores[cand.index.values]
        top = np.argsort(-s)[:k]
        return [(cand.iloc[i]["disruption_id"], float(s[i])) for i in top]

    def get_case(self, cid: str) -> dict | None:
        if self.df is None or cid not in self.df.index:
            return None
        r = self.df.loc[cid].to_dict()
        r["text"] = case_text(r)
        return _clean(r)

    def options(self) -> dict[str, Any]:
        df = self.df
        return {
            "disruption_type": sorted(df["disruption_type"].unique().tolist()),
            "industry": sorted(df["industry"].unique().tolist()),
            "supplier_tier": sorted(int(x) for x in df["supplier_tier"].unique()),
            "supplier_region": sorted(df["supplier_region"].unique().tolist()),
            "supplier_size": sorted(df["supplier_size"].unique().tolist()),
            "response_type": sorted(df["response_type"].unique().tolist()),
            "disruption_severity": [1, 2, 3, 4, 5],
        }


def _clean(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, (np.integer,)):
            v = int(v)
        elif isinstance(v, (np.floating,)):
            v = float(v)
        elif isinstance(v, np.bool_):
            v = bool(v)
        out[k] = v
    return out


store = DataStore()

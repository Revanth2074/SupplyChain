"""
Historical Analytics Service.
Factor insights across all 100,000 disruptions (by type, severity, industry, region, tier,
backup, strategy, size) and the correlation matrix used by the Analytics page.
"""

from __future__ import annotations

import functools

from services.data_store import store

@functools.lru_cache(maxsize=1)
def insights() -> dict:
    df = store.df
    metrics = {"avg_impact": ("production_impact_pct", "mean"), "avg_loss": ("revenue_loss_usd", "mean"),
               "avg_recovery": ("full_recovery_days", "mean"), "cases": ("disruption_id", "count"),
               "change_rate": ("permanent_supplier_change", "mean")}

    def grp(col):
        g = df.groupby(col).agg(**metrics).reset_index().rename(columns={col: "key"})
        g["key"] = g["key"].astype(str)
        return g.round(3).to_dict("records")

    num = df[["disruption_severity", "supplier_tier", "response_time_days", "production_impact_pct",
              "revenue_loss_usd", "partial_recovery_days", "full_recovery_days"]].copy()
    num["has_backup_supplier"] = df["has_backup_supplier"].astype(int)
    corr = num.corr().round(3)
    return {
        "totals": {"cases": int(len(df)), "avg_impact": round(float(df["production_impact_pct"].mean()), 1),
                   "avg_loss": round(float(df["revenue_loss_usd"].mean()), 0),
                   "total_loss": round(float(df["revenue_loss_usd"].sum()), 0),
                   "avg_recovery": round(float(df["full_recovery_days"].mean()), 1),
                   "backup_rate": round(float(df["has_backup_supplier"].mean()), 3),
                   "change_rate": round(float(df["permanent_supplier_change"].mean()), 3)},
        "by_type": grp("disruption_type"), "by_severity": grp("disruption_severity"),
        "by_industry": grp("industry"), "by_region": grp("supplier_region"), "by_tier": grp("supplier_tier"),
        "by_backup": grp("has_backup_supplier"), "by_response": grp("response_type"), "by_size": grp("supplier_size"),
        "correlation": {"columns": list(corr.columns), "matrix": corr.values.tolist()},
    }

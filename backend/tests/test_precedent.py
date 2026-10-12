"""Precedent estimator (no trained model) and the Impact agent's Synapt cross-check, on a small synthetic history."""
import numpy as np
import pandas as pd

from agents import precedent as prec
from agents.precedent import PrecedentEstimator, rt_band


def _history(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "disruption_id": [f"DIS-{i:06d}" for i in range(n)],
        "disruption_type": rng.choice(["Cyber Attack", "Port Congestion"], n),
        "industry": rng.choice(["Aerospace", "Automotive"], n),
        "supplier_region": rng.choice(["Europe", "Asia-Pacific"], n),
        "supplier_size": rng.choice(["Small", "Large"], n),
        "response_type": rng.choice(["Alternative Supplier", "Customer Delay"], n),
        "supplier_tier": rng.choice([1, 2], n),
        "has_backup_supplier": rng.choice([True, False], n),
        "disruption_severity": rng.choice([2, 4], n),
        "response_time_days": rng.choice([1, 5, 20], n),
    })
    # outcomes: backup and the Alternative Supplier strategy shorten recovery, severity lengthens it
    df["full_recovery_days"] = (40 + 20 * df["disruption_severity"] - 30 * df["has_backup_supplier"]
                                - 15 * (df["response_type"] == "Alternative Supplier") + rng.normal(0, 3, n)).round()
    df["partial_recovery_days"] = (df["full_recovery_days"] * 0.4).round()
    df["production_impact_pct"] = 10 * df["disruption_severity"] + rng.normal(0, 2, n)
    df["revenue_loss_usd"] = 1e5 * df["disruption_severity"] + rng.normal(0, 1e4, n)
    return df


def _estimator(monkeypatch):
    monkeypatch.setattr(prec.store, "df", _history())
    monkeypatch.setattr(prec, "VALIDATION_PATH", prec.settings.ARTIFACT_DIR / "_missing_validation.json")
    e = PrecedentEstimator()
    e.load()
    return e


INC = {"disruption_type": "Cyber Attack", "industry": "Aerospace", "supplier_region": "Europe", "supplier_size": "Small",
       "response_type": "Customer Delay", "supplier_tier": 2, "has_backup_supplier": False, "disruption_severity": 4,
       "response_time_days": 5}


def test_response_time_bands():
    assert [rt_band(d) for d in (0, 2, 3, 7, 8, 14, 15, 60)] == [0, 0, 1, 1, 2, 2, 3, 3]


def test_estimate_is_the_median_of_a_real_cohort(monkeypatch):
    e = _estimator(monkeypatch)
    p = e.predict(INC)
    assert p["method"] == "precedent statistics"
    assert p["cohort"]["cases"] >= prec.MIN_COHORT
    assert p["ranges"]["full_recovery_days"]["p10"] <= p["full_recovery_days"] <= p["ranges"]["full_recovery_days"]["p90"]
    assert 0 <= p["risk_probability"] <= 1
    assert "synapt_precedents" not in p  # Synapt is only asked when requested


def test_cohort_backs_off_until_enough_cases(monkeypatch):
    e = _estimator(monkeypatch)
    c = e.cohort(INC)
    assert c["n"] >= prec.MIN_COHORT
    assert len(c["matched_on"]) < len(prec.COHORT_KEYS)  # 3000 cases cannot match all nine keys


def test_kept_lever_stays_in_the_cohort(monkeypatch):
    e = _estimator(monkeypatch)
    c = e.cohort({**INC, "response_type": "Alternative Supplier"}, keep=("response_type",))
    assert "response_type" in c["matched_on"]


def test_whatif_finds_the_levers_that_help(monkeypatch):
    e = _estimator(monkeypatch)
    w = e.whatif(INC)
    by = {s["key"]: s for s in w["scenarios"]}
    assert by["backup"]["delta"]["full_recovery_days"] < 0
    assert by["strategy:Alternative Supplier"]["delta"]["full_recovery_days"] < 0
    assert w["method"] == "precedent statistics"


def test_explain_names_real_drivers(monkeypatch):
    e = _estimator(monkeypatch)
    ex = e.explain(INC)["full_recovery_days"]
    top = {d["feature"] for d in ex["local"][:3]}
    assert top & {"has_backup_supplier", "disruption_severity"}
    assert ex["global"][0]["feature"] in ("disruption_severity", "has_backup_supplier")


def test_impact_agent_asks_synapt_then_flags_disagreement(monkeypatch):
    from agents.impact_analysis import ImpactAgent
    e = _estimator(monkeypatch)
    monkeypatch.setattr(prec, "estimator", e)
    far = {"source": "synapt", "used": 8, "avg_similarity": 0.8, "case_ids": ["DIS-000001"],
           "full_recovery_days": 400.0, "production_impact_pct": 40.0}
    monkeypatch.setattr(e, "synapt_precedents", lambda inc, top_k=20: far)
    agent = ImpactAgent()
    out = agent({"incident": INC})
    steps = out["messages"][0]["steps"]
    assert [s["tool"] for s in steps] == ["synapt_precedents", "precedent_estimate", "priority"]
    impact = out["impact"]
    assert impact["precedent"] is far and impact["checks"]
    assert out["messages"][0]["status"] == "partial"

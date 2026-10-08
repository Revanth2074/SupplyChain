"""Reciprocal Rank Fusion and the P1-P4 priority formula."""
import pytest

from agents.impact_analysis import priority
from agents.retrieval import reciprocal_rank_fusion


def test_rrf_rewards_agreement_between_legs():
    fused = reciprocal_rank_fusion({
        "synapt": (0.6, [("A", 0.9), ("B", 0.8)]),
        "bm25": (0.4, [("B", 12.0), ("C", 9.0)]),
    }, k=60)
    # B is ranked by both legs, so it beats A (top of one leg only)
    assert fused["B"]["score"] > fused["A"]["score"] > fused["C"]["score"]
    assert fused["B"]["score"] == pytest.approx(0.6 / 62 + 0.4 / 61)
    assert fused["B"]["legs"]["bm25"]["rank"] == 1


def test_rrf_weight_changes_order():
    legs = {"x": (1.0, [("A", 1.0)]), "y": (0.1, [("B", 1.0)])}
    fused = reciprocal_rank_fusion(legs)
    assert fused["A"]["score"] > fused["B"]["score"]


@pytest.mark.parametrize("inc,level", [
    ({"disruption_severity": 5, "production_impact_pct": 90, "revenue_loss_usd": 50e6}, "P1"),
    ({"disruption_severity": 1, "production_impact_pct": 2, "revenue_loss_usd": 1e4}, "P4"),
])
def test_priority_levels(inc, level):
    p = priority(inc, {"risk_probability": 1.0 if level == "P1" else 0.0})
    assert p["level"].startswith(level)


def test_priority_formula_weights():
    p = priority({"disruption_severity": 3, "production_impact_pct": 50, "revenue_loss_usd": 1e4},
                 {"risk_probability": 0.5})
    # 0.35*0.5 + 0.30*0.5 + 0.25*0 + 0.10*0.5 = 0.375
    assert p["score"] == pytest.approx(37.5)
    assert p["level"].startswith("P3")
    assert p["inputs"]["estimated"] == {"impact": False, "loss": False}

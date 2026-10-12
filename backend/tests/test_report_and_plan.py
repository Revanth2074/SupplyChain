"""Report fact-check, plan rationale and Synapt playbook steps (all deterministic, no LLM)."""
from agents.planner import _rationale, apply_playbook, statistics_plan
from agents.synthesis import check_report, strip_bad_ids

CASES = [{"disruption_id": "DIS-000123", "revenue_loss_usd": 2_000_000, "production_impact_pct": 40.0,
          "response_type": "Inventory Buffer"}]
STRATS = [
    {"strategy": "Inventory Buffer", "cases": 50, "avg_full_recovery": 90.0, "effectiveness": 60.0,
     "avg_revenue_loss": 1_000_000, "avg_impact": 30.0, "supplier_change_rate": 0.3},
    {"strategy": "Alternative Supplier", "cases": 20, "avg_full_recovery": 70.0, "effectiveness": 50.0,
     "avg_revenue_loss": 1_500_000, "avg_impact": 35.0, "supplier_change_rate": 0.1},
]
FACTS = {"revenue_loss": "$3,000,000", "production_impact": "45.0%"}


def test_fact_check_passes_grounded_report():
    md = "Closest case DIS-000123 lost $2,000,000 at 40.0% impact; expect $3,000,000 and 45.0%."
    assert check_report(md, FACTS, CASES, STRATS, {}) == []


def test_fact_check_flags_unknown_ids_placeholders_and_numbers():
    md = "Like DIS-999999 and DIS-XXXXXX, loss will be $7,777,777 with 88% impact."
    issues = check_report(md, FACTS, CASES, STRATS, {})
    assert any("DIS-999999" in i for i in issues)
    assert any("placeholder" in i for i in issues)
    assert any("7,777,777" in i for i in issues)
    assert any("88%" in i for i in issues)


def test_playbook_figures_count_as_evidence():
    md = "Historically $3,365,434 loss."
    assert check_report(md, FACTS, CASES, STRATS, {})
    assert check_report(md, {**FACTS, "playbook": "averaged $3,365,434 revenue loss"}, CASES, STRATS, {}) == []


def test_strip_bad_ids_keeps_known_cases():
    out = strip_bad_ids("See DIS-000123 and DIS-555555.", CASES)
    assert "DIS-000123" in out and "DIS-555555" not in out


def test_rationale_explains_ranking_and_names_fastest():
    txt = _rationale({"disruption_type": "Cyber Attack"}, STRATS)
    assert "highest effectiveness score" in txt
    assert "Alternative Supplier recovered fastest" in txt


def test_plan_uses_synapt_playbook_steps():
    plan = statistics_plan({"disruption_type": "Cyber Attack", "has_backup_supplier": False}, STRATS, CASES)
    assert plan["method"] == "statistics"
    assert plan["cited_cases"] == ["DIS-000123"]
    assert any("backup" in r.lower() for r in plan["risks"])
    proc = {"name": "Respond to a Cyber Attack disruption",
            "steps": [{"n": i, "text": f"step {i}"} for i in range(1, 6)]}
    plan = apply_playbook(plan, proc)
    assert plan["method"] == "statistics+synapt-playbook"
    assert [a["action"] for a in plan["immediate_actions"][:3]] == ["step 1", "step 2", "step 3"]
    assert plan["short_term_actions"][:2] == ["step 4", "step 5"]
    assert apply_playbook({"method": "statistics"}, None) == {"method": "statistics"}

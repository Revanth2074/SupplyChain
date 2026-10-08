"""Rule classifier (the Intake agent runs without an LLM)."""
from agents.classifier import _rule_classify

OPTS = {
    "disruption_type": ["Cyber Attack", "Factory Incident", "Geopolitical", "Labor Strike", "Natural Disaster",
                        "Port Congestion"],
    "industry": ["Aerospace", "Automotive", "Consumer Goods", "Electronics", "Pharmaceuticals"],
    "supplier_region": ["Africa/Middle East", "Asia-Pacific", "Europe", "North America", "South America"],
    "supplier_size": ["Large", "Medium", "Small"],
}


def fields(text):
    return _rule_classify(text, OPTS)["fields"]


def test_cyber_attack_avionics_is_aerospace():
    f = fields("Ransomware attack on our Tier 2 avionics electronics supplier in Asia-Pacific. "
               "No backup supplier is qualified. Severity 4.")
    assert f["disruption_type"] == "Cyber Attack"
    assert f["industry"] == "Aerospace"
    assert f["supplier_tier"] == 2
    assert f["disruption_severity"] == 4
    assert f["has_backup_supplier"] is False
    assert f["supplier_region"] == "Asia-Pacific"


def test_export_is_not_port_congestion():
    # "export" contains "port"; it must not be classified as Port Congestion
    f = fields("New export sanctions block shipments from our Tier 2 semiconductor supplier; we have an alternate supplier.")
    assert f["disruption_type"] == "Geopolitical"
    assert f["industry"] == "Electronics"
    assert f["has_backup_supplier"] is True


def test_port_congestion_and_backup():
    f = fields("Severe port congestion at Shanghai is delaying containers from a large Tier 1 supplier; "
               "we do have a backup supplier.")
    assert f["disruption_type"] == "Port Congestion"
    assert f["supplier_size"] == "Large"
    assert f["has_backup_supplier"] is True


def test_values_stay_inside_vocabulary():
    f = fields("Something happened at a supplier somewhere with a strike and a fire and a flood")
    for k in ("disruption_type", "industry", "supplier_region", "supplier_size"):
        if k in f:
            assert f[k] in OPTS[k]

"""Incremental-ingest manifest logic and the dataset data contract."""
import pandas as pd

from scripts.build_knowledge_base import REQUIRED_COLUMNS, validate_dataset
from synapt import ingest_to_synapt as ing


def test_content_hash_ignores_line_endings():
    assert ing.content_hash("a\r\nb\r\n") == ing.content_hash("a\nb\n")
    assert ing.content_hash("a\nb") != ing.content_hash("a\nc")


def test_manifest_status_new_changed_unchanged():
    items = [{"path": "cases/a.md", "sha256": ing.content_hash("same")},
             {"path": "cases/b.md", "sha256": ing.content_hash("new text")},
             {"path": "cases/c.md", "sha256": ing.content_hash("x")}]
    manifest = {ing.P: {"cases/a.md": {"sha256": ing.content_hash("same")},
                        "cases/b.md": {"sha256": ing.content_hash("old text")}}}
    status = {it["path"]: it["status"] for it in ing.with_status(items, manifest)}
    assert status == {"cases/a.md": "unchanged", "cases/b.md": "changed", "cases/c.md": "new"}


def _row(**kw):
    row = {"disruption_id": "DIS-000001", "disruption_type": "Cyber Attack", "industry": "Electronics",
           "supplier_tier": 2, "supplier_region": "Europe", "supplier_size": "Large", "has_backup_supplier": True,
           "disruption_severity": 3, "production_impact_pct": 30.0, "revenue_loss_usd": 1e6,
           "response_type": "Inventory Buffer", "response_time_days": 3, "partial_recovery_days": 10,
           "full_recovery_days": 40, "permanent_supplier_change": False}
    return {**row, **kw}


def test_data_contract_passes_clean_rows():
    df = pd.DataFrame([_row(), _row(disruption_id="DIS-000002")])
    assert set(REQUIRED_COLUMNS) <= set(df.columns)
    assert validate_dataset(df) == []


def test_data_contract_catches_violations():
    df = pd.DataFrame([_row(), _row(disruption_type="Alien Invasion", supplier_tier=9,
                                    partial_recovery_days=50, full_recovery_days=40)])
    errors = " ".join(validate_dataset(df)).lower()
    assert "disruption_type" in errors and "supplier_tier" in errors and "partial" in errors
    dup = pd.DataFrame([_row(), _row()])
    assert validate_dataset(dup)

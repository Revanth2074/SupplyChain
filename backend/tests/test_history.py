"""Activity history store (artifacts/history.json): record, list, filter, get, delete, clear, size cap."""
import pytest

from services import history


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "HISTORY_PATH", tmp_path / "history.json")


def test_record_list_newest_first_with_counts():
    history.record("analysis", "Cyber attack at Kansas", "P2 · Inventory Buffer", {"x": 1}, ref="abc123")
    history.record("ask", "Fastest strategy for port congestion?", "Alternative Supplier")
    r = history.list_entries()
    assert r["total"] == 2 and r["counts"] == {"analysis": 1, "ask": 1}
    assert [e["kind"] for e in r["entries"]] == ["ask", "analysis"]
    assert "data" not in r["entries"][0]  # list view omits snapshots


def test_filter_search_get_delete_clear():
    a = history.record("analysis", "Cyber attack at Kansas", "P2")
    history.record("search", "port congestion tier 1", "10 results")
    assert [e["id"] for e in history.list_entries(kind="analysis")["entries"]] == [a["id"]]
    assert len(history.list_entries(q="KANSAS")["entries"]) == 1
    assert history.get(a["id"])["title"] == "Cyber attack at Kansas"
    assert history.delete(a["id"]) and not history.delete(a["id"])
    assert history.clear() == 1 and history.list_entries()["total"] == 0


def test_oversized_snapshot_is_replaced():
    e = history.record("portfolio", "Big", data={"blob": "x" * (history.MAX_DATA_CHARS + 10)})
    assert history.get(e["id"])["data"]["note"].startswith("snapshot too large")

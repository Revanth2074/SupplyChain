"""Activity history: every action taken in the console (analyses, questions, searches, simulations,
decisions, incidents, feedback, evaluations) kept in one JSON file on the server,
artifacts/history.json, so the History tab shows the same list on any device that opens the app."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

from config import settings

HISTORY_PATH = settings.ARTIFACT_DIR / "history.json"
MAX_ENTRIES = 2000           # oldest entries are dropped beyond this
MAX_DATA_CHARS = 60_000      # cap on the stored snapshot of one entry

_lock = threading.Lock()


def _read() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write(entries: list[dict]) -> None:
    tmp = HISTORY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, HISTORY_PATH)  # atomic: a crash never leaves a half-written file


def record(kind: str, title: str, summary: str = "", data: dict | None = None, ref: str | None = None) -> dict:
    """Append one entry (newest first) and return it."""
    snap = data or {}
    if len(json.dumps(snap, default=str)) > MAX_DATA_CHARS:
        snap = {"note": "snapshot too large to store", "keys": sorted(snap)[:40]}
    entry = {"id": uuid.uuid4().hex[:12], "ts": time.time(), "kind": kind, "title": title[:200],
             "summary": summary[:600], "ref": ref, "data": snap}
    with _lock:
        entries = _read()
        entries.insert(0, entry)
        _write(entries[:MAX_ENTRIES])
    return entry


def list_entries(kind: str | None = None, q: str | None = None, limit: int = 200) -> dict:
    entries = _read()
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    if kind:
        entries = [e for e in entries if e["kind"] == kind]
    if q:
        ql = q.lower()
        entries = [e for e in entries if ql in (e["title"] + " " + e["summary"]).lower()]
    # the list view does not need the snapshots; GET /history/{id} returns one in full
    return {"total": sum(counts.values()), "counts": counts,
            "entries": [{k: v for k, v in e.items() if k != "data"} for e in entries[:limit]]}


def get(entry_id: str) -> dict | None:
    return next((e for e in _read() if e["id"] == entry_id), None)


def delete(entry_id: str) -> bool:
    with _lock:
        entries = _read()
        keep = [e for e in entries if e["id"] != entry_id]
        if len(keep) == len(entries):
            return False
        _write(keep)
    return True


def clear() -> int:
    with _lock:
        n = len(_read())
        _write([])
    return n

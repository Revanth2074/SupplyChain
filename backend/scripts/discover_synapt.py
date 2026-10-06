"""Run: python -m scripts.discover_synapt  (from backend/)"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.synapt_client import get_client  # noqa: E402

c = get_client()
tools = c.list_tools()
print(f"Found {len(tools)} tools\n")
for t in tools:
    print("=" * 80)
    print(t["name"])
    print((t.get("description") or "")[:600])
    print(json.dumps(t.get("inputSchema", {}), indent=1)[:1500])

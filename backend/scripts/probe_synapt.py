import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings  # noqa: E402
from app.synapt_client import get_client  # noqa: E402

c = get_client()
P = settings.SYNAPT_PROVIDER_ID
q = "cyber attack aerospace tier 2 supplier no backup high severity, how was it resolved"


def show(name, args, n=2500):
    print("\n" + "#" * 30, name)
    try:
        r = c.call_tool(name, args)
        s = json.dumps(r, indent=1, default=str) if not isinstance(r, str) else r
        print(type(r).__name__, len(s))
        print(s[:n])
    except Exception as e:  # noqa: BLE001
        print("ERR", e)


which = sys.argv[1:] or ["stats", "chunks", "search", "query"]
if "stats" in which:
    show("trident_get_stats", {"provider_id": P})
if "chunks" in which:
    show("trident_get_chunks", {"provider_id": P, "query": q, "top_k": 3})
if "search" in which:
    show("trident_search", {"provider_id": P, "query": q, "top_k": 3})
if "query" in which:
    show("trident_query", {"provider_id": P, "question": q, "top_k": 5, "graph_hops": 2}, 5000)
if "schema" in which:
    show("trident_get_schema", {"provider_id": P})
if "episodes" in which:
    show("trident_episodes", {"provider_id": P, "query": q, "top_k": 3})

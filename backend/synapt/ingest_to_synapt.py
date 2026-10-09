#!/usr/bin/env python3
"""
Synapt / Trident MCP Ingestion Client.
Loads the knowledge assets in knowledge_base/ into the active Synapt Context Provider with
`trident_ingest` via `SynaptMCPConnector`:

  - Historical case narratives   knowledge_base/cases/*.md       (Context Graph, 4,000 cases)
  - Response playbooks (SOPs)    knowledge_base/sops/*.md        (Procedure Store)
  - Reference statistics         knowledge_base/reference/*.md   (profiles of all 100k cases, aggregate stats)

Optional steps:
  --ontology        ingest knowledge_base/reference/ontology.md with typed entity/relation hints
  --graph           create typed entities, concepts and stat-backed edges (trident_create_*; currently rejected
                    server-side with "index_node() missing 'neo4j_id'", so the script stops cleanly)
  --learn-regions   record Synapt's masked [LOCATION_x] tokens -> region names for the app

Run from backend/ (generate the assets first with scripts/build_knowledge_base.py):
    python synapt/ingest_to_synapt.py --dry-run          # status of every file: new / changed / unchanged
    python synapt/ingest_to_synapt.py                    # send new + changed files only (asks first)
    python synapt/ingest_to_synapt.py --only sops --force
    python synapt/ingest_to_synapt.py --mark-ingested    # adopt files already in the provider, send nothing
    python synapt/ingest_to_synapt.py --only none --learn-regions

Every successful ingest is recorded in artifacts/synapt_ingest_manifest.json (content hash, job id, time), so
re-runs skip unchanged files. Synapt has no delete tool, so a changed file sent again adds a second version.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Dict, List

import pandas as pd

# Ensure the service root (backend/) and this directory are importable
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
sys.path.insert(0, os.path.dirname(_here))
from synapt_connector import SynaptConfig, SynaptError, SynaptMCPConnector  # noqa: E402

from config import get_knowledge_base_dir, settings  # noqa: E402

_connector: SynaptMCPConnector = None  # set in main()
P = settings.SYNAPT_PROVIDER_ID


# graph-building helpers share the dataset statistics with the knowledge-base builder
sys.path.insert(0, os.path.join(os.path.dirname(_here), "scripts"))
from build_knowledge_base import CONCEPTS, agg, fmt, strategy_ranking  # noqa: E402


def call(tool: str, args: dict, retries: int = 2, rate_limit_waits: int = 8) -> Any:
    """Call a Trident tool and parse its JSON text; retries transient failures and waits out
    Synapt's ingest rate limit ({"error": "rate_limited", "retry_after_seconds": N} comes back as a result)."""
    i = 0
    while True:
        try:
            r = _connector.call_tool(tool, {"provider_id": P, **args})
            if isinstance(r, str):
                try:
                    r = json.loads(r)
                except json.JSONDecodeError:
                    return r
            if isinstance(r, dict) and r.get("error") == "rate_limited" and rate_limit_waits > 0:
                rate_limit_waits -= 1
                wait = int(r.get("retry_after_seconds") or 30) + 3
                print(f"rate-limited, waiting {wait}s...", end=" ", flush=True)
                time.sleep(wait)
                continue
            if isinstance(r, dict) and set(r) == {"result"} and isinstance(r["result"], str):
                try:
                    return json.loads(r["result"])
                except json.JSONDecodeError:
                    return r["result"]
            return r
        except SynaptError as e:
            if i >= retries:
                raise
            i += 1
            print(f"  retry {tool}: {e}")
            time.sleep(2 * i)


def load_dataset() -> pd.DataFrame:
    df = pd.read_csv(settings.DATA_CSV)
    for b in ("has_backup_supplier", "permanent_supplier_change"):
        df[b] = df[b].astype(str).str.lower().eq("true")
    return df


# ---------------------------------------------------------------- ingest manifest (incremental, idempotent)
# Synapt has no delete tool: every trident_ingest adds a document. The manifest records what this provider
# already holds (file -> content hash, job id, time) so re-runs skip unchanged files instead of duplicating them.
MANIFEST_PATH = settings.ARTIFACT_DIR / "synapt_ingest_manifest.json"


def content_hash(text: str) -> str:
    """SHA-256 of the content with line endings normalised (CRLF vs LF is not a content change)."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def load_manifest() -> Dict[str, Any]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: Dict[str, Any]) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8", newline="\n")


def record(manifest: Dict[str, Any], item: Dict[str, Any], job_id: str, extraction_mode: str) -> None:
    manifest.setdefault(P, {})[item["path"]] = {
        "sha256": item["sha256"], "job_id": job_id, "ingested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "document_type": item["document_type"], "extraction_mode": extraction_mode}
    save_manifest(manifest)  # after every file, so an interrupted run never re-sends what already succeeded


def with_status(items: List[Dict[str, Any]], manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """status: new (never ingested), changed (ingested, content differs since), unchanged."""
    done = manifest.get(P, {})
    for it in items:
        prev = done.get(it["path"])
        it["status"] = "new" if not prev else "unchanged" if prev["sha256"] == it["sha256"] else "changed"
    return items


def load_local_knowledge_assets(only: str = "all") -> List[Dict[str, Any]]:
    """Loads the markdown files from knowledge_base/cases, sops and reference."""
    kb = get_knowledge_base_dir()
    groups = [
        ("cases", "text", "Historical Disruption Case Narratives"),
        ("sops", "sop", "Disruption Response Playbook (SOP)"),
        ("reference", "text", "Reference Statistics (all 100,000 cases)"),
    ]
    items = []
    for folder, doc_type, category in groups:
        if only not in ("all", folder):
            continue
        d = kb / folder
        if not d.exists():
            continue
        for fname in sorted(os.listdir(d)):
            # the ontology has its own typed ingest (--ontology); the combined playbook duplicates sops/
            if not fname.endswith(".md") or fname in ("ontology.md", "response_playbooks_combined.md"):
                continue
            content = (d / fname).read_text(encoding="utf-8")
            items.append({"filename": fname, "path": f"{folder}/{fname}", "document_type": doc_type,
                          "category": category, "content": content, "sha256": content_hash(content)})
    return items


ENTITY_TYPES = json.dumps([
    {"name": "DisruptionType", "description": "Category of supply chain disruption, e.g. Cyber Attack, Port Congestion"},
    {"name": "Industry", "description": "Industry of the affected company, e.g. Automotive, Electronics"},
    {"name": "SupplierRegion", "description": "Region of the affected supplier, e.g. Europe, Asia-Pacific"},
    {"name": "ResponseStrategy", "description": "Response used to recover, e.g. Alternative Supplier, Inventory Buffer"},
    {"name": "SupplierTier", "description": "Tier 1, Tier 2 or Tier 3 supplier"},
    {"name": "SeverityLevel", "description": "Disruption severity 1 to 5"},
    {"name": "Metric", "description": "Outcome measure such as production impact, revenue loss or recovery time"},
])
# names must come from Synapt's edge vocabulary
REL_TYPES = json.dumps([
    {"name": "USES", "description": "Disruption type, industry or region was recovered using a response strategy"},
    {"name": "RELATED_TO", "description": "Industry or region experienced a disruption type"},
    {"name": "MEASURES", "description": "Metric measures the outcome of a disruption or strategy"},
])


ONTO_ENTITY_TYPES = json.dumps([
    {"name": "DisruptionType", "description": "A category of supply chain disruption"},
    {"name": "Industry", "description": "An industry sector whose suppliers are disrupted"},
    {"name": "SupplierRegion", "description": "A geographic region where suppliers are located"},
    {"name": "ResponseStrategy", "description": "A strategy used to respond to and recover from a disruption"},
    {"name": "SupplierTier", "description": "A supplier tier (Tier 1 direct to Tier 4 upstream)"},
    {"name": "OutcomeMetric", "description": "A measure of disruption impact or recovery"},
])
ONTO_REL_TYPES = json.dumps([
    {"name": "RECOVERED_WITH", "description": "A disruption type is best recovered with a response strategy"},
    {"name": "EXPOSED_TO", "description": "An industry or region is exposed to a disruption type"},
    {"name": "MEASURED_BY", "description": "An outcome is measured by a metric"},
])


def ingest_assets(items: List[Dict[str, Any]], extraction_mode: str, manifest: Dict[str, Any]) -> None:
    success = failed = 0
    for idx, item in enumerate(items, 1):
        print(f"[{idx}/{len(items)}] Ingesting [{item['category']}]: {item['filename']}...", end=" ", flush=True)
        tool_args = {
            "connector_type": "content",
            "document_type": item["document_type"],
            "extraction_mode": extraction_mode,
            "filename": item["filename"],
            "content": item["content"],
            "has_ttl": False,
            "entity_types": ENTITY_TYPES,
            "relationship_types": REL_TYPES,
        }
        try:
            res_obj = call("trident_ingest", tool_args)
            if isinstance(res_obj, dict) and res_obj.get("error"):  # never record a rejected file as ingested
                raise SynaptError(f"{res_obj['error']}: {res_obj.get('message', '')}")
            resp_list = res_obj.get("response", []) if isinstance(res_obj, dict) else []
            job_id = resp_list[0].get("job_id", "ACCEPTED") if resp_list else "QUEUED"
            print(f"[OK] (Job: {job_id})")
            record(manifest, item, str(job_id), extraction_mode)
            success += 1
            time.sleep(0.5)  # Spacing requests gently
        except Exception as e:  # noqa: BLE001
            print(f"[FAILED]: {e}")
            failed += 1
    print(f"\n[*] Ingestion Complete: {success} accepted, {failed} failed.")


def ingest_ontology() -> None:
    path = get_knowledge_base_dir() / "reference" / "ontology.md"
    r = call("trident_ingest", {
        "connector_type": "content", "content": path.read_text(encoding="utf-8"), "filename": path.name,
        "document_type": "text", "extraction_mode": "comprehensive", "has_ttl": False,
        "entity_types": ONTO_ENTITY_TYPES, "relationship_types": ONTO_REL_TYPES,
    })
    print(path.name, "->", json.dumps(r, default=str)[:300])


def exists(name: str) -> bool:
    try:
        r = call("trident_find_exact", {"name": name})
    except SynaptError:
        return False
    s = json.dumps(r, default=str).lower()
    return bool(r) and "not found" not in s and "no node" not in s and '"nodes": []' not in s


def build_graph(df: pd.DataFrame) -> None:
    ents: list[tuple[str, str, str]] = []
    for t, g in df.groupby("disruption_type"):
        best = strategy_ranking(df, "disruption_type", t)[0]
        ents.append((t, "DisruptionType", f"Supply chain disruption type. {fmt(agg(g))}. "
                                          f"Fastest historical response: {best[0]} ({best[1]['full']:.1f} days)."))
    for i, g in df.groupby("industry"):
        ents.append((i, "Industry", f"Industry affected by supply chain disruptions. {fmt(agg(g))}."))
    for r, g in df.groupby("supplier_region"):
        ents.append((r, "SupplierRegion", f"Supplier region {r}. {fmt(agg(g))}."))
    for rt, g in df.groupby("response_type"):
        ents.append((rt, "ResponseStrategy", f"Disruption response strategy. {fmt(agg(g))}."))
    for t, g in df.groupby("supplier_tier"):
        ents.append((f"Tier {t}", "SupplierTier", f"Tier {t} supplier. {fmt(agg(g))}."))
    for s, g in df.groupby("disruption_severity"):
        ents.append((f"Severity {s}", "SeverityLevel", f"Disruption severity {s} of 5. {fmt(agg(g))}."))

    print(f"creating {len(ents)} entities + {len(CONCEPTS)} concepts")
    try:
        for name, typ, desc in ents:
            if exists(name):
                print("  exists:", name)
                continue
            call("trident_create_entity", {"label": name, "entity_type": typ, "description": desc}, retries=0)
            print("  entity:", name)
        for name, definition in CONCEPTS.items():
            if exists(name):
                print("  exists:", name)
                continue
            call("trident_create_concept", {"name": name, "definition": definition, "aliases": ""}, retries=0)
            print("  concept:", name)
    except SynaptError as e:
        # As of 2026-10-06 the Synapt server fails every create with
        # "GraphNodeIndex.index_node() missing ... 'neo4j_id'"; the ingested profile
        # and playbook docs carry the same knowledge until that is fixed.
        sys.exit(f"Synapt rejected node creation, graph not written: {e}")

    edges: list[tuple[str, str, str, str, float]] = []
    for col, label in (("disruption_type", str), ("industry", str), ("supplier_region", str)):
        for v in sorted(df[col].unique()):
            rank = strategy_ranking(df, col, v)
            worst = rank[-1][1]["full"]
            for i, (rt, s) in enumerate(rank):
                conf = round(0.5 + 0.5 * (worst - s["full"]) / max(worst - rank[0][1]["full"], 1e-9), 3)
                edges.append((label(v), "USES", rt,
                              f"Rank {i + 1} of {len(rank)} by recovery speed for {label(v)}: {fmt(s)}.", conf))
    for i in sorted(df.industry.unique()):
        for t, g in df[df.industry == i].groupby("disruption_type"):
            edges.append((i, "RELATED_TO", t, f"{i} exposure to {t}: {fmt(agg(g))}.", 1.0))
    for r in sorted(df.supplier_region.unique()):
        for t, g in df[df.supplier_region == r].groupby("disruption_type"):
            edges.append((r, "RELATED_TO", t, f"{t} at {r} suppliers: {fmt(agg(g))}.", 1.0))
    for s in sorted(df.disruption_severity.unique()):
        edges.append((f"Severity {s}", "RELATED_TO", "Disruption Priority",
                      f"Severity {s}: {fmt(agg(df[df.disruption_severity == s]))}.", 1.0))
    for t in sorted(df.supplier_tier.unique()):
        edges.append((f"Tier {t}", "RELATED_TO", "Supply Chain Resilience",
                      f"Tier {t}: {fmt(agg(df[df.supplier_tier == t]))}.", 1.0))
    for rt in sorted(df.response_type.unique()):
        edges.append((rt, "RELATED_TO", "Full Recovery Time",
                      f"{rt}: {fmt(agg(df[df.response_type == rt]))}.", 1.0))

    print(f"creating {len(edges)} relationships")
    ok = 0
    for src, et, tgt, desc, conf in edges:
        try:
            call("trident_create_relationship", {"source_label": src, "edge_type": et, "target_label": tgt,
                                                 "description": desc, "confidence": conf})
            ok += 1
        except SynaptError as e:
            print(f"  FAILED {src} -{et}-> {tgt}: {e}")
    print(f"  {ok}/{len(edges)} relationships created")


def learn_regions(df: pd.DataFrame) -> None:
    from agents.synapt_tools import regions
    reg = df.set_index("disruption_id").supplier_region
    for r in sorted(df.supplier_region.unique()):
        for q in (f"{r} supplier disruption", f"Supplier region: {r}. Supplier size: Large"):
            for h in call("trident_get_chunks", {"query": q, "top_k": 10}):
                for cid, txt in re.findall(r"(DIS-\d{6})\s+(.*?)(?=#{2,3}\s*DIS-|$)", h.get("text", ""), re.S):
                    m = regions.IN_CASE.search(txt)
                    if m and cid in reg.index:
                        regions.learn(m.group(1), reg[cid])
    print(json.dumps(regions.tokens, indent=1))


def main():
    global _connector
    parser = argparse.ArgumentParser(description="Ingest the Supply-Chain Knowledge Base into Synapt via MCP")
    parser.add_argument("--dry-run", action="store_true", help="Print manifest without ingesting")
    parser.add_argument("--only", choices=["all", "cases", "sops", "reference", "none"], default="all",
                        help="Which knowledge assets to ingest (none = run only the optional steps)")
    parser.add_argument("--extraction-mode", choices=["comprehensive", "balanced", "precise"], default="comprehensive")
    parser.add_argument("--ontology", action="store_true", help="Also ingest reference/ontology.md with typed hints")
    parser.add_argument("--graph", action="store_true", help="Create typed entities, concepts and edges")
    parser.add_argument("--learn-regions", action="store_true", help="Learn masked region tokens for the app")
    parser.add_argument("--force", action="store_true", help="Also re-send files whose content is unchanged")
    parser.add_argument("--mark-ingested", action="store_true",
                        help="Record the selected files as already ingested (adopt content already in the provider) "
                             "without sending anything")
    parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation")
    args = parser.parse_args()

    config = SynaptConfig()
    print(f"[*] Target Provider: {config.provider_id}")
    print(f"[*] MCP Endpoint:    {config.mcp_url}")
    print(f"[*] Authenticating as: {config.username}")

    manifest = load_manifest()
    items = with_status(load_local_knowledge_assets(args.only) if args.only != "none" else [], manifest)
    to_send = [x for x in items if args.force or x["status"] != "unchanged"]

    print("\n========================================================")
    print(f"   SYNAPT MCP INGESTION MANIFEST -> [{config.provider_id}]")
    print("========================================================")
    print(f"[*] Total Knowledge Assets: {len(items)}   (manifest: {MANIFEST_PATH.name})")
    by_cat: Dict[str, Dict[str, int]] = {}
    for x in items:
        c = by_cat.setdefault(x["category"], {"new": 0, "changed": 0, "unchanged": 0})
        c[x["status"]] += 1
    for cat, c in by_cat.items():
        print(f"    - {cat}: {sum(c.values())}  (new {c['new']}, changed {c['changed']}, unchanged {c['unchanged']})")
    print(f"[*] To send: {len(to_send)}{' (forced)' if args.force else ' (new + changed; unchanged files are skipped)'}")
    print(f"[*] Extraction Mode: '{args.extraction_mode}'")
    print(f"[*] Optional steps: ontology={args.ontology} graph={args.graph} learn-regions={args.learn_regions}")
    print("========================================================")
    changed = [x for x in to_send if x["status"] == "changed"]
    if changed:
        print(f"[!] {len(changed)} changed file(s): Synapt has no delete tool, so each re-ingest ADDS a new version next to "
              "the old one. Use a fresh provider (SYNAPT_PROVIDER_ID) for a clean rebuild.")
    done = manifest.get(P, {})
    if any(x["path"].startswith("sops/") and x["status"] == "new" for x in to_send) and \
            "reference/response_playbooks_combined.md" in done:
        print("[!] The playbooks are already in the provider via the combined document "
              f"('{done['reference/response_playbooks_combined.md'].get('ingested_as', 'response_playbooks_combined.md')}'); "
              "sending the SOP files adds a second copy of each procedure.")
    print()

    if args.mark_ingested:
        for x in items:
            record(manifest, x, "adopted", args.extraction_mode)
        print(f"[*] Recorded {len(items)} file(s) as already ingested. Nothing was sent.")
        return
    if args.dry_run:
        for x in to_send[:60]:
            print(f"    {x['status']:<9} {x['path']}")
        if len(to_send) > 60:
            print(f"    ... and {len(to_send) - 60} more")
        print("[*] Dry run complete. Nothing was sent.")
        return
    if to_send and not args.yes and input(f"Send {len(to_send)} file(s) to '{config.provider_id}'? [y/N] ").strip().lower() != "y":
        sys.exit("Cancelled.")

    _connector = SynaptMCPConnector(config)
    _connector.authenticate()
    _connector.initialize_mcp()

    if to_send:
        ingest_assets(to_send, args.extraction_mode, manifest)
    elif items:
        print("[*] Everything selected is already ingested and unchanged.")
    if args.ontology:
        ingest_ontology()
    if args.graph or args.learn_regions:
        df = load_dataset()
        if args.graph:
            build_graph(df)
        if args.learn_regions:
            learn_regions(df)


if __name__ == "__main__":
    main()

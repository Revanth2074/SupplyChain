"""Build and load the Synapt knowledge layer for the supply-chain provider.

Run from backend/:
    python -m scripts.synapt_knowledge docs      # write profile + playbook docs to ../synapt_ingest/
    python -m scripts.synapt_knowledge ingest    # upload those docs via trident_ingest (no TTL)
    python -m scripts.synapt_knowledge graph     # create typed entities, concepts and stat-backed edges
    python -m scripts.synapt_knowledge learn-regions  # map Synapt's masked region tokens -> regions
    python -m scripts.synapt_knowledge ontology  # ingest an explicit ontology doc so Synapt's extractor builds
                                                 # typed entities + relations (workaround while trident_create_entity
                                                 # fails server-side with "index_node() missing 'neo4j_id'")
    python -m scripts.synapt_knowledge tickets   # write ../synapt_ingest/disruption_tickets.xlsx for the
                                                 # console's Data Ingestion > Ticketing source (ticket store +
                                                 # mined episodes; MCP trident_ingest cannot create one)
    python -m scripts.synapt_knowledge check     # graph stats + region-masking check

All statistics are computed from the full 100k-row CSV, so the graph covers the
whole dataset even though only a 4,000-case sample is ingested as raw text.
Synapt's PII masking rewrites supplier regions in ingested chunks to stable
[LOCATION_x] tokens; `learn-regions` records that mapping for the app
(app.synapt_service.regions), which also keeps learning it at query time.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings  # noqa: E402
from app.synapt_client import SynaptError, get_client  # noqa: E402

OUT = Path(settings.DATA_CSV).parent / "synapt_ingest"
P = settings.SYNAPT_PROVIDER_ID

CONCEPTS = {
    "Production Impact": "Percentage of production capacity lost because of a supply chain disruption "
                         "(production_impact_pct). Bands: Low <20%, Moderate 20-35%, High 35-50%, Severe >=50%.",
    "Revenue Loss": "Financial loss in USD caused by the disruption (revenue_loss_usd).",
    "Partial Recovery Time": "Days until operations were partially restored (partial_recovery_days).",
    "Full Recovery Time": "Days until operations were fully restored (full_recovery_days). "
                          "Bands: Fast <=30, Normal <=60, Slow <=120, Very Slow >120.",
    "Response Time": "Days between the disruption and the start of the response strategy (response_time_days).",
    "Backup Supplier": "Whether the affected supplier had a qualified backup supplier (has_backup_supplier).",
    "Permanent Supplier Change": "Whether the affected supplier was permanently replaced after the disruption.",
    "Disruption Severity": "Severity of the disruption on a 1 (minor) to 5 (critical) scale.",
    "Disruption Priority": "Triage level P1-P4 from a weighted score: severity 35%, production impact 30%, "
                           "financial loss 25%, risk 10%.",
    "Supply Chain Resilience": "0-100 score of how well a supplier set-up absorbs and recovers from disruption, "
                               "driven by backup supplier, tier, response speed and predicted recovery time.",
}


def load() -> pd.DataFrame:
    df = pd.read_csv(settings.DATA_CSV)
    for b in ("has_backup_supplier", "permanent_supplier_change"):
        df[b] = df[b].astype(str).str.lower().eq("true")
    return df


def agg(g: pd.DataFrame) -> dict:
    return {
        "n": len(g), "impact": g.production_impact_pct.mean(), "loss": g.revenue_loss_usd.mean(),
        "partial": g.partial_recovery_days.mean(), "full": g.full_recovery_days.mean(),
        "resp": g.response_time_days.mean(), "change": g.permanent_supplier_change.mean() * 100,
    }


def fmt(s: dict) -> str:
    return (f"{s['n']} cases, average production impact {s['impact']:.1f}%, average revenue loss "
            f"${s['loss']:,.0f}, average partial recovery {s['partial']:.1f} days, average full recovery "
            f"{s['full']:.1f} days, permanent supplier change in {s['change']:.0f}% of cases")


def strategy_ranking(df: pd.DataFrame, by: str, value) -> list[tuple[str, dict]]:
    sub = df[df[by] == value]
    rows = [(rt, agg(g)) for rt, g in sub.groupby("response_type") if len(g) >= 30]
    return sorted(rows, key=lambda x: x[1]["full"])


# ---------------------------------------------------------------- documents
def build_docs(df: pd.DataFrame) -> list[Path]:
    OUT.mkdir(exist_ok=True)
    prof = ["# Supply Chain Disruption Profiles (full dataset of 100000 cases)", ""]
    for col, title, name in (
        ("disruption_type", "Disruption type profile", str),
        ("industry", "Industry profile", str),
        ("supplier_region", "Supplier region profile", str),
        ("supplier_tier", "Supplier tier profile", lambda t: f"Tier {t}"),
        ("supplier_size", "Supplier size profile", lambda s: f"{s} supplier"),
        ("disruption_severity", "Severity profile", lambda s: f"Severity {s} of 5"),
    ):
        for v, g in df.groupby(col):
            prof += [f"## {title}: {name(v)}", "", f"{name(v)}: {fmt(agg(g))}."]
            for b, gb in g.groupby("has_backup_supplier"):
                s = agg(gb)
                prof.append(f"{'With' if b else 'Without'} a backup supplier: {s['n']} cases, average "
                            f"production impact {s['impact']:.1f}%, average full recovery {s['full']:.1f} days.")
            if col in ("disruption_type", "industry", "supplier_region"):
                rank = strategy_ranking(df, col, v)
                prof.append("Response strategies ranked by average full recovery: " + "; ".join(
                    f"{i + 1}. {rt} ({s['full']:.1f} days, ${s['loss']:,.0f} loss, {s['n']} cases)"
                    for i, (rt, s) in enumerate(rank)) + ".")
            prof.append("")
    # cross-tab: disruption type x region
    prof += ["## Disruption type by supplier region", ""]
    for (t, r), g in df.groupby(["disruption_type", "supplier_region"]):
        s = agg(g)
        prof.append(f"{t} disruptions at {r} suppliers: {s['n']} cases, average production "
                    f"impact {s['impact']:.1f}%, average full recovery {s['full']:.1f} days, average revenue "
                    f"loss ${s['loss']:,.0f}.")
    prof.append("")
    p1 = OUT / "profiles.md"
    p1.write_text("\n".join(prof), encoding="utf-8")

    # SOP playbooks -> Synapt procedures
    sop = ["# Disruption Response Playbooks", "",
           "Standard operating procedures derived from the outcomes of 100000 historical supply chain "
           "disruptions. Each playbook lists the response strategies in order of fastest average full recovery.", ""]
    for t, g in df.groupby("disruption_type"):
        rank = strategy_ranking(df, "disruption_type", t)
        nb, wb = agg(g[~g.has_backup_supplier]), agg(g[g.has_backup_supplier])
        fast = agg(g[g.response_time_days <= 3])
        slow = agg(g[g.response_time_days > 7])
        sop += [f"## Procedure: Respond to a {t} disruption", "",
                f"Intent: restore production after a {t} disruption with the lowest recovery time and loss.", "",
                f"1. Classify the incident: confirm it is a {t} disruption and record industry, supplier tier, "
                f"supplier region, supplier size, backup supplier status and severity (1-5).",
                f"2. Assess impact: historical {t} disruptions averaged {agg(g)['impact']:.1f}% production impact "
                f"and ${agg(g)['loss']:,.0f} revenue loss; severity 4-5 cases should be triaged as P1 or P2.",
                f"3. Check backup supplier: cases with a backup recovered fully in {wb['full']:.1f} days on average "
                f"versus {nb['full']:.1f} days without one. Activate the backup supplier if one exists.",
                f"4. Start the response within 3 days: responses started within 3 days averaged {fast['full']:.1f} "
                f"days to full recovery versus {slow['full']:.1f} days when started after 7 days.",
                f"5. Select the response strategy, preferring the fastest historical option: {rank[0][0]} "
                f"({rank[0][1]['full']:.1f} days average full recovery), then {rank[1][0]} "
                f"({rank[1][1]['full']:.1f} days). Avoid {rank[-1][0]} unless constrained "
                f"({rank[-1][1]['full']:.1f} days).",
                f"6. Track recovery: expect partial recovery in about {agg(g)['partial']:.0f} days; escalate if "
                f"full recovery exceeds {agg(g)['full'] * 1.5:.0f} days.",
                f"7. Review the supplier: {agg(g)['change']:.0f}% of {t} disruptions ended in a permanent "
                f"supplier change; record the outcome and feedback for continuous improvement.", ""]
    p2 = OUT / "response_playbooks.md"
    p2.write_text("\n".join(sop), encoding="utf-8")
    print(f"wrote {p1} ({p1.stat().st_size // 1024} KB) and {p2} ({p2.stat().st_size // 1024} KB)")
    return [p1, p2]


# ---------------------------------------------------------------- synapt calls
def call(tool: str, args: dict, retries: int = 2):
    for i in range(retries + 1):
        try:
            r = get_client().call_tool(tool, {"provider_id": P, **args})
            if isinstance(r, dict) and set(r) == {"result"} and isinstance(r["result"], str):
                try:
                    return json.loads(r["result"])
                except json.JSONDecodeError:
                    return r["result"]
            return r
        except SynaptError as e:
            if i == retries:
                raise
            print(f"  retry {tool}: {e}")
            time.sleep(2 * (i + 1))


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


def ingest(paths: list[Path]) -> None:
    for p in paths:
        r = call("trident_ingest", {
            "connector_type": "content", "content": p.read_text(encoding="utf-8"), "filename": p.name,
            "document_type": "sop" if "playbook" in p.name else "text",
            "extraction_mode": "comprehensive", "has_ttl": False,
            "entity_types": ENTITY_TYPES, "relationship_types": REL_TYPES,
        })
        print(p.name, "->", json.dumps(r, default=str)[:300])


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
    from app.synapt_service import regions
    reg = df.set_index("disruption_id").supplier_region
    for r in sorted(df.supplier_region.unique()):
        for q in (f"{r} supplier disruption", f"Supplier region: {r}. Supplier size: Large"):
            for h in call("trident_get_chunks", {"query": q, "top_k": 10}):
                for cid, txt in re.findall(r"(DIS-\d{6})\s+(.*?)(?=#{2,3}\s*DIS-|$)", h.get("text", ""), re.S):
                    m = regions.IN_CASE.search(txt)
                    if m and cid in reg.index:
                        regions.learn(m.group(1), reg[cid])
    print(json.dumps(regions.tokens, indent=1))


def build_tickets(df: pd.DataFrame, n: int = 5000) -> Path:
    def band(d):
        return "Fast" if d <= 30 else "Normal" if d <= 60 else "Slow" if d <= 120 else "Very Slow"

    t = df.sample(n, random_state=11)
    out = pd.DataFrame({
        "ticket_id": t.disruption_id,
        "title": t.disruption_type + " at " + t.industry + " Tier " + t.supplier_tier.astype(str) + " supplier",
        "description": t.apply(lambda r: (
            f"{r.disruption_type} disruption at a {r.supplier_size.lower()} Tier {r.supplier_tier} {r.industry} "
            f"supplier in {r.supplier_region}. Severity {r.disruption_severity}/5, "
            f"{'a backup supplier is available' if r.has_backup_supplier else 'no backup supplier'}. "
            f"Production impact {r.production_impact_pct}%, revenue loss ${r.revenue_loss_usd:,.0f}."), axis=1),
        "resolution": t.apply(lambda r: (
            f"Responded with {r.response_type} after {r.response_time_days} days; partial recovery in "
            f"{r.partial_recovery_days} days, full recovery in {r.full_recovery_days} days; supplier "
            f"{'replaced' if r.permanent_supplier_change else 'kept'}."), axis=1),
        "disruption_type": t.disruption_type, "industry": t.industry, "supplier_region": t.supplier_region,
        "response_type": t.response_type, "recovery_outcome": t.full_recovery_days.map(band),
    })
    path = OUT / "disruption_tickets.xlsx"
    out.to_excel(path, index=False, sheet_name="tickets")  # the ticket gateway accepts .xlsx only
    print(f"wrote {path} ({len(out)} tickets). Upload it in the Synapt console: Data Ingestion > Ticketing,")
    print("with label fields disruption_type, industry, supplier_region, response_type, recovery_outcome.")
    return path


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


def build_ontology(df: pd.DataFrame) -> Path:
    """Short declarative sentences, one fact each: the form LLM extractors turn into clean entities + edges."""
    lines = ["# Supply Chain Disruption Ontology", "",
             "This document defines the entities of the supply chain disruption domain and how they relate.", ""]
    lines += ["## Disruption types", ""]
    for t, g in df.groupby("disruption_type"):
        rank = strategy_ranking(df, "disruption_type", t)
        lines.append(f"{t} is a DisruptionType. {t} disruptions recover fastest with {rank[0][0]} "
                     f"({rank[0][1]['full']:.0f} days on average) and slowest with {rank[-1][0]} ({rank[-1][1]['full']:.0f} days). "
                     f"{t} RECOVERED_WITH {rank[0][0]}. {t} disruptions cause {agg(g)['impact']:.0f}% average production impact.")
    lines += ["", "## Response strategies", ""]
    for rt, g in df.groupby("response_type"):
        lines.append(f"{rt} is a ResponseStrategy. {rt} reaches full recovery in {agg(g)['full']:.0f} days on average across all disruption types.")
    lines += ["", "## Industries", ""]
    for i, g in df.groupby("industry"):
        worst = g.groupby("disruption_type").production_impact_pct.mean().idxmax()
        lines.append(f"{i} is an Industry. {i} is most EXPOSED_TO {worst}, which causes the highest production impact for {i} suppliers.")
    lines += ["", "## Supplier regions", ""]
    for r, g in df.groupby("supplier_region"):
        common = g.disruption_type.value_counts().idxmax()
        lines.append(f"{r} is a SupplierRegion. {r} is most often EXPOSED_TO {common}.")
    lines += ["", "## Supplier tiers", ""]
    for t, g in df.groupby("supplier_tier"):
        lines.append(f"Tier {t} is a SupplierTier. Tier {t} suppliers recover fully in {agg(g)['full']:.0f} days on average.")
    lines += ["", "## Outcome metrics", "",
              "Production Impact is an OutcomeMetric. Production Impact measures the share of production capacity lost.",
              "Revenue Loss is an OutcomeMetric. Revenue Loss measures the money lost because of a disruption.",
              "Full Recovery Time is an OutcomeMetric. Full Recovery Time measures days until operations are fully restored.",
              "Backup Supplier is a ResponseStrategy enabler. Having a Backup Supplier shortens Full Recovery Time.", ""]
    path = OUT / "ontology.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {path}")
    return path


def ingest_ontology(path: Path) -> None:
    r = call("trident_ingest", {
        "connector_type": "content", "content": path.read_text(encoding="utf-8"), "filename": path.name,
        "document_type": "text", "extraction_mode": "comprehensive", "has_ttl": False,
        "entity_types": ONTO_ENTITY_TYPES, "relationship_types": ONTO_REL_TYPES,
    })
    print(path.name, "->", json.dumps(r, default=str)[:300])


def check() -> None:
    print(json.dumps(call("trident_get_stats", {}), indent=1))
    hits = call("trident_get_chunks", {"query": "Supplier region profile Europe", "top_k": 3})
    for h in (hits if isinstance(hits, list) else []):
        t = h.get("text", "")
        print("--", h.get("source_file"), "| masked" if "[LOCATION_" in t else "| clear", "|", t[:160].replace("\n", " "))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "docs":
        build_docs(load())
    elif cmd == "ingest":
        ingest(build_docs(load()))
    elif cmd == "graph":
        build_graph(load())
    elif cmd == "ontology":
        ingest_ontology(build_ontology(load()))
    elif cmd == "tickets":
        build_tickets(load())
    elif cmd == "learn-regions":
        learn_regions(load())
    elif cmd == "check":
        check()
    else:
        sys.exit(__doc__)

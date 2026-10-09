#!/usr/bin/env python3
"""
Knowledge Base Builder.
Generates the Markdown knowledge assets ingested into Synapt from the full 100,000-case dataset.
All statistics use every row, so the knowledge covers the whole dataset even though only a
4,000-case narrative sample (knowledge_base/cases/) is ingested as raw text.

Run from backend/:
    python scripts/build_knowledge_base.py validate  # data-quality contract on the CSV (runs before every build)
    python scripts/build_knowledge_base.py cases     # cases/cases_0xx.md: 4,000 enriched case cards
    python scripts/build_knowledge_base.py sops      # sops/SOP_00x_*.md runbooks (+ reference/response_playbooks_combined.md)
    python scripts/build_knowledge_base.py docs      # reference/profiles.md
    python scripts/build_knowledge_base.py tickets   # tickets/disruption_tickets.xlsx (Synapt ticket store;
                                                     # the ticket gateway accepts .xlsx only)
    python scripts/build_knowledge_base.py ontology  # reference/ontology.md (typed-entity workaround)
    python scripts/build_knowledge_base.py all

Then load them with: python synapt/ingest_to_synapt.py --dry-run
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import get_knowledge_base_dir, settings  # noqa: E402

KB = get_knowledge_base_dir()
REFERENCE, SOPS, TICKETS, CASES = KB / "reference", KB / "sops", KB / "tickets", KB / "cases"

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
    for d in (REFERENCE, SOPS):
        d.mkdir(parents=True, exist_ok=True)
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
    p1 = REFERENCE / "profiles.md"
    p1.write_text("\n".join(prof), encoding="utf-8", newline="\n")

    print(f"wrote {p1} ({p1.stat().st_size // 1024} KB)")
    return [p1]


# ---------------------------------------------------------------- data-quality contract
REQUIRED_COLUMNS = [
    "disruption_id", "disruption_type", "industry", "supplier_tier", "supplier_region", "supplier_size",
    "has_backup_supplier", "disruption_severity", "production_impact_pct", "revenue_loss_usd", "response_type",
    "response_time_days", "partial_recovery_days", "full_recovery_days", "permanent_supplier_change",
]
VOCAB = {
    "disruption_type": {"Cyber Attack", "Factory Incident", "Geopolitical", "Labor Strike", "Natural Disaster",
                        "Port Congestion"},
    "industry": {"Aerospace", "Automotive", "Consumer Goods", "Electronics", "Pharmaceuticals"},
    "supplier_region": {"Africa/Middle East", "Asia-Pacific", "Europe", "North America", "South America"},
    "supplier_size": {"Large", "Medium", "Small"},
    "response_type": {"Alternative Supplier", "Combined Strategy", "Customer Delay", "Inventory Buffer",
                      "Production Reroute"},
}
RANGES = {"supplier_tier": (1, 4), "disruption_severity": (1, 5), "production_impact_pct": (0, 100),
          "revenue_loss_usd": (0, None), "response_time_days": (0, 365), "partial_recovery_days": (0, None),
          "full_recovery_days": (0, None)}


def validate_dataset(df: pd.DataFrame) -> list[str]:
    """Data contract checked before anything is generated. Returns the violations (empty list = pass)."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return [f"missing columns: {missing}"]
    errors = []
    nulls = {c: int(n) for c, n in df[REQUIRED_COLUMNS].isna().sum().items() if n}
    if nulls:
        errors.append(f"null values: {nulls}")
    if not df["disruption_id"].is_unique:
        errors.append(f"{int(df['disruption_id'].duplicated().sum())} duplicate disruption_id values")
    bad_ids = int((~df["disruption_id"].astype(str).str.fullmatch(r"DIS-\d{6}")).sum())
    if bad_ids:
        errors.append(f"{bad_ids} disruption_id values not in DIS-000000 format")
    for col, allowed in VOCAB.items():
        extra = sorted(set(df[col].dropna().unique()) - allowed)
        if extra:
            errors.append(f"{col}: unexpected values {extra}")
    for col, (lo, hi) in RANGES.items():
        bad = (df[col] < lo) | (df[col] > hi) if hi is not None else (df[col] < lo)
        if bad.any():
            errors.append(f"{col}: {int(bad.sum())} values outside [{lo}, {hi if hi is not None else 'inf'}]")
    n = int((df["partial_recovery_days"] > df["full_recovery_days"]).sum())
    if n:
        errors.append(f"{n} rows where partial recovery is longer than full recovery")
    return errors


def check_dataset(df: pd.DataFrame) -> None:
    errors = validate_dataset(df)
    if errors:
        sys.exit("[FAIL] data contract:\n  - " + "\n  - ".join(errors))
    print(f"[OK] data contract: {len(df):,} rows, {len(REQUIRED_COLUMNS)} columns, no nulls, unique DIS- ids, "
          f"vocabularies and ranges valid")


# ---------------------------------------------------------------- playbook ids
def sop_ids(df: pd.DataFrame) -> dict[str, str]:
    """Disruption type -> SOP id (alphabetical, so the ids are stable)."""
    return {t: f"SOP-{i:03d}" for i, t in enumerate(sorted(df.disruption_type.unique()), 1)}


def _ranking(sub: pd.DataFrame) -> list[tuple[str, dict]]:
    rows = [(rt, agg(g)) for rt, g in sub.groupby("response_type") if len(g) >= 30]
    return sorted(rows, key=lambda x: x[1]["full"])


# ---------------------------------------------------------------- SOP runbooks
def build_sops(df: pd.DataFrame) -> list[Path]:
    """One runbook per disruption type: metadata, trigger, prerequisites, ordered steps (action, owner, expected
    outcome, validation), escalation. Every number is computed from all 100,000 cases. The '## Procedure:'
    heading and the 7 numbered steps are what Synapt's Procedure Store extracts."""
    from services.ops import SLA

    SOPS.mkdir(parents=True, exist_ok=True)
    REFERENCE.mkdir(parents=True, exist_ok=True)
    ids = sop_ids(df)
    intro = ("Standard operating procedures derived from the outcomes of 100000 historical supply chain "
             "disruptions. Each playbook gives the trigger, prerequisites, ordered steps with an owner, expected "
             "outcome and validation, and the escalation path.")
    escalation = ["### Escalation", ""]
    for p, cfg in SLA.items():
        chain = " -> ".join(f"{role} ({'at once' if h == 0 else f'after {h}h'})" for role, h in cfg["chain"])
        escalation.append(f"* {p}: respond within {cfg['hours']} hours. Escalation chain: {chain}.")
    escalation.append("")
    combined = ["# Disruption Response Playbooks", "", intro, ""]
    paths = []
    for t, sid in ids.items():
        g = df[df.disruption_type == t]
        a, wb, nb = agg(g), agg(g[g.has_backup_supplier]), agg(g[~g.has_backup_supplier])
        fast, slow = agg(g[g.response_time_days <= 3]), agg(g[g.response_time_days > 7])
        rank_b, rank_n, rank_all = _ranking(g[g.has_backup_supplier]), _ranking(g[~g.has_backup_supplier]), _ranking(g)
        p90_loss = g.revenue_loss_usd.quantile(0.9)
        p50_part, p75_full = g.partial_recovery_days.median(), g.full_recovery_days.quantile(0.75)
        high_share = (g.disruption_severity >= 4).mean()
        title = f"Respond to a {t} disruption"
        body = [
            f"## Procedure: {title}", "",
            f"Intent: restore production after a {t} disruption with the lowest recovery time and loss.", "",
            "### Metadata", "",
            f"* Procedure ID: {sid}",
            f"* Target disruption type: {t}",
            f"* Trigger: any {t} disruption. Severity 4-5 or production impact of 35% or more is P1 or P2: "
            f"open a war-room within 4 hours.",
            f"* Evidence base: {len(g):,} historical {t} disruptions ({high_share:.0%} at severity 4-5).",
            "", "### Prerequisites", "",
            "1. The incident is logged with disruption type, industry, supplier tier, region, size, backup status "
            "and severity.",
            "2. The affected parts, open orders and inventory cover are known or being collected.",
            "3. An incident owner is assigned in the Incident Desk.",
            "", "### Ordered Steps", "",
            f"1. Classify and triage. Action: confirm it is a {t} disruption, record its attributes and compute the "
            f"priority (35% severity, 30% production impact, 25% revenue loss, 10% risk). Owner: Supply Chain Ops "
            f"Lead. Expected outcome: priority P1-P4 and SLA set within 1 hour. Validation: the incident shows a "
            f"priority and an owner.",
            f"2. Assess impact. Action: estimate production impact and revenue at risk; historical {t} disruptions "
            f"averaged {a['impact']:.1f}% production impact and ${a['loss']:,.0f} revenue loss (90th percentile "
            f"${p90_loss:,.0f}). Owner: Planning and Finance. Expected outcome: exposure quantified within 24 hours. "
            f"Validation: predicted impact, loss and recovery ranges recorded on the incident.",
            f"3. Secure supply. Action: if a backup supplier exists, activate it now; if not, start qualifying an "
            f"alternative supplier immediately. {t} cases with a backup recovered fully in {wb['full']:.1f} days on "
            f"average versus {nb['full']:.1f} days without one. Owner: Procurement. Expected outcome: a confirmed "
            f"alternative source. Validation: purchase order or capacity confirmation from the backup or "
            f"alternative supplier.",
            f"4. Start the response within 3 days. Action: launch the selected strategy without waiting for complete "
            f"information; responses started within 3 days averaged {fast['full']:.1f} days to full recovery versus "
            f"{slow['full']:.1f} days when started after 7 days. Owner: Supply Chain Ops Lead. Expected outcome: "
            f"response started by day 3. Validation: response start date logged.",
            f"5. Select the response strategy. Action: with a backup supplier, prefer {rank_b[0][0]} "
            f"({rank_b[0][1]['full']:.1f} days average full recovery), then {rank_b[1][0]} "
            f"({rank_b[1][1]['full']:.1f} days); without a backup supplier, prefer {rank_n[0][0]} "
            f"({rank_n[0][1]['full']:.1f} days), then {rank_n[1][0]} ({rank_n[1][1]['full']:.1f} days). Avoid "
            f"{rank_all[-1][0]} unless constrained ({rank_all[-1][1]['full']:.1f} days). Owner: Supply Chain Ops Lead "
            f"with Procurement. Expected outcome: one primary and one fallback strategy approved. Validation: both "
            f"strategies recorded on the incident.",
            f"6. Track recovery. Action: hold a daily recovery stand-up; expect partial recovery in about "
            f"{p50_part:.0f} days. Escalate one level if full recovery is projected beyond {p75_full:.0f} days (the "
            f"75th percentile for {t}). Owner: Incident owner. Expected outcome: partial recovery near day "
            f"{p50_part:.0f}. Validation: recovery milestones updated at least weekly.",
            f"7. Close and learn. Action: record the actual recovery days and loss, decide on the supplier "
            f"({a['change']:.0f}% of {t} disruptions ended in a permanent supplier change) and rate the "
            f"recommendation. Owner: Incident owner. Expected outcome: the outcome is captured for model retraining "
            f"and Synapt feedback. Validation: incident closed with the actual outcome recorded.",
            "", *escalation,
        ]
        path = SOPS / f"SOP_{sid[-3:]}_{t.replace(' ', '_')}_Response.md"
        path.write_text("\n".join([f"# {sid}: {title}", "", intro, "", *body]), encoding="utf-8", newline="\n")
        paths.append(path)
        combined += body
    comb = REFERENCE / "response_playbooks_combined.md"
    comb.write_text("\n".join(combined), encoding="utf-8", newline="\n")
    print(f"wrote {len(paths)} SOP runbooks in {SOPS} and {comb}")
    return paths


# ---------------------------------------------------------------- enriched case cards
SAMPLE_FILE = CASES / "case_sample_ids.csv"
CASES_PER_FILE = 100


def _case_sample(df: pd.DataFrame) -> list[tuple[str, str]]:
    """(file, disruption_id) pairs. Reuses the recorded sample so regenerated files hold the same 4,000 cases
    that are already in Synapt; otherwise draws a type-stratified 4% sample."""
    if SAMPLE_FILE.exists():
        s = pd.read_csv(SAMPLE_FILE)
        return list(zip(s.file, s.disruption_id))
    s = df.groupby("disruption_type", group_keys=False).sample(frac=0.04, random_state=7)
    s = s.sort_values(["disruption_type", "disruption_severity", "disruption_id"])
    pairs = [(f"cases_{i // CASES_PER_FILE + 1:03d}.md", cid) for i, cid in enumerate(s.disruption_id)]
    pd.DataFrame(pairs, columns=["file", "disruption_id"]).to_csv(SAMPLE_FILE, index=False)
    return pairs


def _drivers(r, backup_gap: float) -> list[str]:
    sev = int(r.disruption_severity)
    d = [f"high severity ({sev} of 5)" if sev >= 4 else f"low severity ({sev} of 5)" if sev <= 2
         else "medium severity (3 of 5)"]
    d.append("a backup supplier was available" if r.has_backup_supplier else
             f"no backup supplier (recoveries without one take about {backup_gap:.0f} days longer on average)")
    if r.response_time_days > 7:
        d.append(f"a slow response start ({r.response_time_days} days)")
    elif r.response_time_days <= 2:
        d.append(f"a fast response start ({r.response_time_days} days)")
    if r.supplier_tier >= 3:
        d.append(f"a deep-tier supplier (Tier {r.supplier_tier}) with less visibility")
    if r.supplier_size == "Large":
        d.append("a large supplier, which carries the highest revenue exposure")
    return d[:4]


def case_card(r, cohort: dict, backup_gap: float, sop: tuple[str, str], enrich: bool = True) -> str:
    """One case: the three factual paragraphs, then (enrich) priority, drivers, outcome verdict and playbook link."""
    from agents.impact_analysis import priority
    from services.data_store import impact_band, loss_band, recovery_band

    backup = "had a backup supplier" if r.has_backup_supplier else "had no backup supplier"
    change = "was permanently replaced" if r.permanent_supplier_change else "relationship was kept"
    parts = [
        f"## {r.disruption_id}", "",
        f"Disruption type: {r.disruption_type}. Industry: {r.industry}. Supplier tier: Tier {r.supplier_tier}. "
        f"Supplier region: {r.supplier_region}. Supplier size: {r.supplier_size}. The supplier {backup}.", "",
        f"Severity was {r.disruption_severity} out of 5. Production impact was {r.production_impact_pct}% "
        f"({impact_band(r.production_impact_pct)}). Revenue loss was ${r.revenue_loss_usd:,.0f} "
        f"({loss_band(r.revenue_loss_usd)}).", "",
        f"Response strategy: {r.response_type}, started after {r.response_time_days} days. Partial recovery took "
        f"{r.partial_recovery_days} days and full recovery took {r.full_recovery_days} days "
        f"({recovery_band(r.full_recovery_days)}). The supplier {change}.", "",
    ]
    if enrich:
        inc = {"disruption_severity": int(r.disruption_severity), "production_impact_pct": float(r.production_impact_pct),
               "revenue_loss_usd": float(r.revenue_loss_usd)}
        p = priority(inc)
        med, n = cohort[(r.disruption_type, int(r.disruption_severity), bool(r.has_backup_supplier))]
        diff = r.full_recovery_days - med
        if r.full_recovery_days <= 0.85 * med:
            verdict = f"{abs(diff):.0f} days faster than typical, so the {r.response_type} response was effective"
        elif r.full_recovery_days >= 1.15 * med:
            verdict = f"{diff:.0f} days slower than typical, so the {r.response_type} response under-performed"
        else:
            verdict = "in line with similar cases"
        parts += [
            f"Assessment: priority {p['level']} (score {p['score']}/100; action SLA: {p['action_sla']}). "
            f"Main drivers: {'; '.join(_drivers(r, backup_gap))}.", "",
            f"Outcome: full recovery took {r.full_recovery_days} days versus a median of {med:.0f} days for {n:,} "
            f"similar {r.disruption_type} disruptions (severity {r.disruption_severity}, "
            f"{'with' if r.has_backup_supplier else 'without'} a backup supplier): {verdict}.", "",
            f"Recommended playbook: {sop[0]} ({sop[1]}).", "",
        ]
    return "\n".join(parts)


def build_cases(df: pd.DataFrame, enrich: bool = True) -> list[Path]:
    CASES.mkdir(parents=True, exist_ok=True)
    pairs = _case_sample(df)
    idx = df.set_index("disruption_id")
    # cohort = same type, severity and backup status over all 100k cases (median full recovery, size)
    g = df.groupby(["disruption_type", "disruption_severity", "has_backup_supplier"]).full_recovery_days
    cohort = {(t, int(s), bool(b)): (float(m), int(n)) for (t, s, b), m, n in zip(g.median().index, g.median(), g.size())}
    backup_gap = df[~df.has_backup_supplier].full_recovery_days.mean() - df[df.has_backup_supplier].full_recovery_days.mean()
    ids = sop_ids(df)
    files: dict[str, list[str]] = {}
    for fname, cid in pairs:
        r = idx.loc[cid]
        r = r.copy()
        r["disruption_id"] = cid
        t = r.disruption_type
        files.setdefault(fname, []).append(
            case_card(r, cohort, backup_gap, (ids[t], f"Respond to a {t} disruption"), enrich))
    paths = []
    for n, (fname, cards) in enumerate(files.items(), 1):
        path = CASES / fname
        path.write_text(f"# Historical Supply Chain Disruption Cases, Batch {n}\n\n" + "".join(c + "\n" for c in cards)
                        .rstrip("\n") + "\n", encoding="utf-8", newline="\n")
        paths.append(path)
    print(f"wrote {len(paths)} case files ({len(pairs):,} {'enriched ' if enrich else ''}cases) in {CASES}")
    return paths


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
    TICKETS.mkdir(parents=True, exist_ok=True)
    path = TICKETS / "disruption_tickets.xlsx"
    out.to_excel(path, index=False, sheet_name="tickets")  # the ticket gateway accepts .xlsx only
    print(f"wrote {path} ({len(out)} tickets). Upload it in the Synapt console: Data Ingestion > Ticketing,")
    print("with label fields disruption_type, industry, supplier_region, response_type, recovery_outcome.")
    return path


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
    path = REFERENCE / "ontology.md"
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {path}")
    return path


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    commands = ("validate", "cases", "sops", "docs", "tickets", "ontology", "all")
    if cmd not in commands:
        sys.exit(__doc__)
    data = load()
    check_dataset(data)
    if cmd in ("cases", "all"):
        build_cases(data, enrich="--plain" not in sys.argv)
    if cmd in ("sops", "all"):
        build_sops(data)
    if cmd in ("docs", "all"):
        build_docs(data)
    if cmd in ("tickets", "all"):
        build_tickets(data)
    if cmd in ("ontology", "all"):
        build_ontology(data)

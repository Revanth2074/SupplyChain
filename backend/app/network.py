"""Supplier dependency network: supplier -> product -> production line -> customer segment,
and "what happens if this supplier goes offline?" propagation.

Products, lines, order volumes and prices are a SAMPLE bill of materials (demo data) because the
historical dataset has no product structure. Recovery time and production impact for the outage come
from the ML models; inventory cover and sourcing shares come from the supplier portfolio."""
from __future__ import annotations

# product -> (production line, weekly orders, revenue per order USD, customer segment)
PRODUCTS = {
    "Control Unit": ("Line A · Electronics assembly", 4200, 310, "Automotive OEMs"),
    "Sensor Pack": ("Line A · Electronics assembly", 2600, 140, "Automotive OEMs"),
    "Display Panel": ("Line A · Electronics assembly", 3300, 210, "Consumer electronics"),
    "Battery Cell": ("Line A · Electronics assembly", 6000, 55, "Consumer electronics"),
    "Brake Module": ("Line B · Vehicle systems", 3100, 420, "Automotive OEMs"),
    "Housing": ("Line B · Vehicle systems", 3800, 95, "Industrial customers"),
    "Wiring Harness": ("Line B · Vehicle systems", 2900, 180, "Automotive OEMs"),
    "Seat Fabric": ("Line B · Vehicle systems", 1800, 60, "Automotive OEMs"),
    "API Batch": ("Line C · Pharma fill & finish", 650, 2400, "Hospitals & distributors"),
    "Packaging Kit": ("Line C · Pharma fill & finish", 5200, 35, "Retail & pharmacies"),
    "Avionics Suite": ("Line D · Aerospace", 140, 26000, "Airlines & MRO"),
    "Airframe Panel": ("Line D · Aerospace", 220, 9800, "Airlines & MRO"),
}


def _products_of(s: dict) -> list[str]:
    return [p.strip() for p in str(s.get("products") or "").split(";") if p.strip() in PRODUCTS]


def build(scored: dict) -> dict:
    """Sankey-ready graph; link values are weekly revenue (USD) flowing through each dependency."""
    sups = scored["suppliers"]
    feeders = {p: [s for s in sups if p in _products_of(s)] for p in PRODUCTS}
    nodes, index, links = [], {}, []

    def node(name, kind, **extra):
        if name not in index:
            index[name] = len(nodes)
            nodes.append({"name": name, "kind": kind, **extra})
        return index[name]

    for p, fs in feeders.items():
        if not fs:
            continue
        line, orders, price, cust = PRODUCTS[p]
        weekly = orders * price
        total_share = sum(float(s["dependency_pct"]) for s in fs) or 1
        pi = node(p, "product", weekly_revenue=weekly, weekly_orders=orders)
        for s in fs:
            si = node(s["supplier_name"], "supplier", band=s["band"], risk_index=s["risk_index"], region=s["supplier_region"])
            links.append({"source": si, "target": pi, "value": round(weekly * float(s["dependency_pct"]) / total_share, 0)})
        li = node(line, "line")
        links.append({"source": pi, "target": li, "value": weekly})
        ci = node(cust, "customer")
        links.append({"source": li, "target": ci, "value": weekly, "product": p})
    # merge duplicate line->customer links
    merged = {}
    for l in links:
        k = (l["source"], l["target"])
        merged[k] = {**l, "value": merged.get(k, {}).get("value", 0) + l["value"]}
    single = [p for p, fs in feeders.items() if len(fs) == 1]
    return {"nodes": nodes, "links": list(merged.values()),
            "single_sourced_products": single, "products": len([p for p in feeders if feeders[p]]),
            "note": "Products, lines, order volumes and prices are sample data (demo bill of materials)."}


def offline(scored: dict, supplier_name: str, disruption_type: str | None = None) -> dict:
    """Supplier goes offline: which products, lines, customers and orders are hit, and the revenue at risk."""
    sups = {s["supplier_name"]: s for s in scored["suppliers"]}
    s = sups.get(supplier_name)
    if not s:
        raise ValueError(f"unknown supplier '{supplier_name}'")
    t = disruption_type or s["worst_case"]["disruption_type"]
    bt = next(b for b in s["by_type"] if b["disruption_type"] == t)
    full = float(bt["full_recovery_days"])
    impact = float(s["expected_production_impact_pct"]) / 100
    partial = full * 0.35  # historical median partial/full recovery ratio is ~0.35
    inv = float(s["inventory_days"])
    # days of real shortage: full outage until partial recovery, half outage until full recovery, minus stock cover
    lost_days = max(0.0, partial - inv) + 0.5 * max(0.0, full - max(partial, inv))
    affected, lines, customers = [], {}, {}
    total_orders = total_rev = 0.0
    for p in _products_of(s):
        line, orders, price, cust = PRODUCTS[p]
        others = [o for o in scored["suppliers"] if o["supplier_name"] != supplier_name and p in _products_of(o)]
        share = float(s["dependency_pct"])
        cover = min(0.6, 0.3 * len(others)) + (0.25 if s["has_backup_supplier"] else 0)  # others / backup absorb part of the gap
        exposed = share * (1 - min(0.85, cover))
        lost_orders = orders / 7 * lost_days * exposed * min(1.0, impact * 1.6)
        rev = lost_orders * price
        total_orders += lost_orders
        total_rev += rev
        lines[line] = lines.get(line, 0) + rev
        customers[cust] = customers.get(cust, 0) + lost_orders
        affected.append({"product": p, "line": line, "customer": cust, "share_from_supplier": round(share, 2),
                         "other_suppliers": [o["supplier_name"] for o in others], "exposed_share": round(exposed, 3),
                         "lost_orders": round(lost_orders), "revenue_at_risk_usd": round(rev, 0)})
    chain = [
        f"{supplier_name} offline ({t.lower()})",
        f"{len(affected)} product(s) short: " + ", ".join(a["product"] for a in affected) if affected else "No mapped products",
        f"{len(lines)} production line(s) slowed",
        f"{round(total_orders):,} customer orders delayed",
        f"${total_rev:,.0f} revenue at risk",
    ]
    return {"supplier": supplier_name, "disruption_type": t, "full_recovery_days": round(full), "partial_recovery_days": round(partial),
            "inventory_days": inv, "shortage_days": round(lost_days, 1), "affected": affected,
            "lines": [{"line": k, "revenue_at_risk_usd": round(v, 0)} for k, v in lines.items()],
            "customers": [{"segment": k, "orders": round(v)} for k, v in customers.items()],
            "orders_at_risk": round(total_orders), "revenue_at_risk_usd": round(total_rev, 0), "chain": chain}

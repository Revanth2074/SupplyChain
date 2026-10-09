# Supply Chain Disruption Data Dictionary & Audit Specification

## 1. Executive Dataset Profile

| Property | Value |
|---|---|
| Dataset | Supply Chain Disruption and Recovery Dataset (Kaggle) |
| File | `supply_chain_disruption_recovery.csv` (11 MB) |
| Rows | 100,000 historical disruptions (one row per event) |
| Columns | 15 (9 known at incident time, 5 outcomes, 1 identifier) |
| Primary key | `disruption_id` (`DIS-000001` … `DIS-100000`, unique) |
| Missing values | 0 in every column |
| Time dimension | None (no event date), so "likelihood of a disruption" cannot be learnt; early warning uses current signals |

## 2. Data Quality Audit

- **Completeness:** no nulls, no duplicate IDs.
- **Ranges:** all values are inside their domains (impact 1–100 %, tier 1–4, severity 1–5, recovery ≥ 3 days).
- **Skew:** revenue loss is heavily right-skewed (median $875k, mean $2.52M, max $373M), so the loss model is trained on `log1p(revenue_loss_usd)` and priority uses a log scale capped at $50M.
- **Synthetic signature:** disruption type and region add almost no information once severity, tier, size and backup are known (near-zero permutation importance), so the data is likely synthetic. Findings are reported honestly rather than over-fitted.
- **Class balance:** 55.6 % of cases had a backup supplier; 23.9 % ended in a permanent supplier change; Tier 4 is 10 % of rows.

## 3. Comprehensive Column Data Dictionary

### 3.1 Identity

| Column | Type | Description |
|---|---|---|
| `disruption_id` | string | Unique case ID. Synapt chunks are joined back to the CSV by this ID. |

### 3.2 Incident attributes (known at incident time → model inputs, filters)

| Column | Type | Values / range | Distribution |
|---|---|---|---|
| `disruption_type` | category | Cyber Attack, Factory Incident, Geopolitical, Labor Strike, Natural Disaster, Port Congestion | Port Congestion 25.1k … Factory Incident 11.9k |
| `industry` | category | Aerospace, Automotive, Consumer Goods, Electronics, Pharmaceuticals | Electronics 29.8k … Aerospace 10.0k |
| `supplier_tier` | int | 1–4 (1 = direct supplier) | 34.9k / 30.0k / 25.0k / 10.0k |
| `supplier_region` | category | Africa/Middle East, Asia-Pacific, Europe, North America, South America | Asia-Pacific 40.3k … Africa/Middle East 8.0k |
| `supplier_size` | category | Large, Medium, Small | Medium 45.2k, Small 29.9k, Large 25.0k |
| `has_backup_supplier` | bool | true / false | 55.6 % true |
| `disruption_severity` | int | 1 (minor) – 5 (critical) | mean 2.5, median 2 |
| `response_type` | category | Alternative Supplier, Combined Strategy, Customer Delay, Inventory Buffer, Production Reroute | Alternative Supplier 44.4k … Combined 11.7k |
| `response_time_days` | int | 1–64 days to start the response | median 2, mean 4.1 |

### 3.3 Outcomes (prediction targets, evidence)

| Column | Type | Range | Mean / median | Model |
|---|---|---|---|---|
| `production_impact_pct` | float | 1–100 % | 31.4 / 30.1 | Regressor + P10/P90 (R² 0.70) |
| `revenue_loss_usd` | float | $10k – $373M | $2.52M / $0.88M | Regressor on log scale + P10/P90 (R² 0.33) |
| `partial_recovery_days` | int | 3–337 | 27.5 / 20 | Regressor + P10/P90 (R² 0.27) |
| `full_recovery_days` | int | 8–798 | 75.8 / 61 | Regressor + P10/P90 (R² 0.40) |
| `permanent_supplier_change` | bool | true / false | 23.9 % true | Reported per cohort (supplier-change probability) |

### 3.4 Derived fields

| Field | Definition | Used by |
|---|---|---|
| High-impact risk (label) | top-quartile loss (≥ $2.49M) OR top-quartile full recovery (≥ 100 days) OR ≥ 50 % production impact; 46.7 % positive | Risk classifier (AUC 0.87) |
| Impact band | Low < 20 %, Moderate 20–35 %, High 35–50 %, Severe ≥ 50 % | Case text for search |
| Recovery band / `recovery_outcome` | Fast ≤ 30 d, Normal ≤ 60, Slow ≤ 120, Very Slow > 120 | Case text, Synapt ticket store label |
| Priority score | 35 % severity + 30 % impact + 25 % log-loss + 10 % risk → P1 ≥ 70, P2 ≥ 50, P3 ≥ 30, P4 | Triage, SLA |
| Resilience score | backup 25 + tier ≤ 15 + size ≤ 15 + recovery speed ≤ 25 + impact absorption ≤ 20 | Impact agent, portfolio |

## 4. Knowledge-Base Derivatives (`knowledge_base/`)

| Asset | Built from | Ingested into Synapt as |
|---|---|---|
| `cases/cases_001…040.md` | 4,000-case sample (`case_sample_ids.csv`, type-stratified 4 %) | Knowledge chunks (semantic retrieval, graph extraction) |
| `sops/SOP_001…006_*_Response.md` | Strategy outcomes per disruption type (all 100k rows) | Procedure Store (`trident_get_procedures`) |
| `reference/profiles.md`, `aggregate_stats.md` | Group statistics over all 100k rows | Knowledge chunks |
| `reference/ontology.md` | One-fact-per-sentence ontology | Typed-entity extraction hint |
| `tickets/disruption_tickets.xlsx` | 5,000 labelled tickets | Ticket store (console upload; `.xlsx` only) |

Regenerate with `python scripts/build_knowledge_base.py all` (deterministic: same CSV → identical files).

### 4.1 Data contract (checked before every build)

`scripts/build_knowledge_base.py` refuses to build if any rule fails: all 15 columns present, no nulls, unique
IDs in `DIS-000000` format, categorical values inside the vocabularies above, numeric ranges (tier 1–4,
severity 1–5, impact 0–100 %, loss ≥ 0, response time 0–365 days, recovery ≥ 0) and partial recovery never
longer than full recovery. The current dataset passes every rule.

### 4.2 Case card format

Each case keeps the three factual paragraphs (attributes; severity, impact and loss with bands; response and
recovery with band and supplier outcome) and adds:

| Line | Content | Source |
|---|---|---|
| `Assessment:` | Priority P1–P4, score and action SLA; up to four main drivers (severity, backup supplier, response start, deep tier, large supplier) | `agents/impact_analysis.priority` on the case's actual impact and loss |
| `Outcome:` | Full recovery vs the median of similar cases (same type, severity and backup status over all 100k rows); verdict *effective* (≤ 85 % of median), *in line* or *under-performed* (≥ 115 %) | Cohort medians |
| `Recommended playbook:` | `SOP-00x (Respond to a <type> disruption)` | Disruption type |

Bands follow the definitions in §3.4 (the first ingested version used older thresholds, e.g. 36.9 % impact was
labelled Moderate; 2,490 case paragraphs are corrected in the regenerated files).

Verdicts across the 4,000 cases: 1,555 effective, 892 in line, 1,553 under-performed. Priorities: 222 P1, 933 P2,
1,539 P3, 1,306 P4.

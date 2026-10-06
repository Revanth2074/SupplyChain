# System Design Specification
## AI-Powered Supply Chain Disruption Assistant with Synapt MCP

---

## 1. Executive Overview & Problem Context
Modern supply chains operate under extreme volatility. Unanticipated events—ranging from cyberattacks and port strikes to natural disasters and plant explosions—propagate downstream, leading to millions of dollars in idle capacity and delayed shipments. Operations teams often have access to historical post-mortems, but this data is siloed across unstructured incident reports and structured enterprise logs.

The **AI-Powered Supply Chain Disruption Assistant** unites:
1. **Synapt Knowledge Substrate (MCP Connector)**: Dense semantic vectors, entity resolution, and tri-store graph-RAG reasoning (`beta.synapt.ai`).
2. **Hybrid RAG Engine**: Reciprocal Rank Fusion (RRF) combining Synapt semantic retrieval with sparse BM25 keyword matching and strict metadata filtering across 100,000 historical disruption records.
3. **Machine Learning Predictive Engine**: Multi-target `HistGradientBoosting` regressors predicting Production Impact %, Financial Loss $, and Recovery Days, alongside high-impact risk probability and a composite Supply Chain Resilience Score (0–100).
4. **Autonomous 7-Agent Disruption Workflow**: Coordinated investigation, impact quantification, tactical action planning, executive synthesis, and LLM-as-Judge verification streamed via Server-Sent Events (SSE).
5. **DeepEval & Continuous Learning Loop**: Automated evaluation across Faithfulness, Answer Relevancy, and GEval rubrics, coupled with operational feedback multipliers and automated model retraining.

---

## 2. Core Design Principles

### 2.1 Hybrid Knowledge Substrate (Synapt + Local Store)
- **Primary Retrieval**: Dense semantic similarity search and Neo4j graph traversal via Synapt's Streamable HTTP MCP tools (`trident_get_chunks`, `trident_query`, `trident_search`).
- **Local Fallback & Enrichment**: Local TF-IDF/TruncatedSVD LSA semantic indexing and BM25Okapi inverted index over the 100,000 cases CSV (`supply_chain_disruption_recovery.csv`). If Synapt experiences connectivity or latency spikes, a resilient circuit breaker switches transparently to local search.
- **Entity & Metadata Hydration**: Case IDs matched via Synapt (e.g. `DIS-079895`) are immediately re-hydrated against the dataset master store to restore de-anonymized metadata and enable exact faceted filtering.

### 2.2 Explainable & Auditable Intelligence
- **No Black Boxes**: Predictions are accompanied by local feature attribution waterfalls ($\Delta_f$ contribution vs dataset median baseline) and global permutation feature importances.
- **LLM-as-Judge**: Every executive briefing is audited by an independent evaluation agent against a 6-dimension rubric (Groundedness, Relevance, Actionability, Completeness, Consistency, Safety) with citation verification.

### 2.3 Continuous Learning & Feedback
- User actions (accepting/modifying a strategy or rating recommendations 1–5 stars) compute dynamic multiplier boosts $w \in [0.85, 1.15]$ applied to strategy effectiveness ranking.
- Post-disruption actual recovery days and financial outcomes are persisted in SQLite (`feedback.db`) to enable on-demand incremental retraining of ML models.
- Operational feedback is forwarded back to Synapt MCP via `trident_feedback` with task/query tracking.

---

## 3. Data Schema & Feature Engineering

### 3.1 Disruption Dataset Vocabulary (100,000 Historical Records)
| Field | Type | Description / Cardinality |
| :--- | :--- | :--- |
| `disruption_id` | String | Unique case identifier (`DIS-000001` to `DIS-100000`) |
| `disruption_type` | Categorical (6) | Cyber Attack, Factory Incident, Geopolitical, Labor Strike, Natural Disaster, Port Congestion |
| `industry` | Categorical (10) | Aerospace, Automotive, Chemicals, Consumer Goods, Electronics, Energy, Food & Beverage, Healthcare, Industrial Machinery, Pharmaceuticals |
| `supplier_tier` | Ordinal (1–3) | Tier 1 (Direct OEM), Tier 2 (Component sub-tier), Tier 3 (Raw materials) |
| `supplier_region` | Categorical (5) | Africa/Middle East, Asia-Pacific, Europe, Latin America, North America |
| `supplier_size` | Categorical (3) | Small, Medium, Large |
| `has_backup_supplier` | Boolean | True / False (Dual-sourced vs Single-sourced) |
| `disruption_severity` | Ordinal (1–5) | 1 (Minor) to 5 (Catastrophic shutdown) |
| `production_impact_pct`| Float (0–100%) | Loss of manufacturing capacity |
| `revenue_loss_usd` | Float | Financial impact in USD (Under 1M to >50M) |
| `response_type` | Categorical (5) | Alternative Supplier, Combined Strategy, Customer Delay, Inventory Buffer, Production Reroute |
| `response_time_days` | Integer (0–365) | Days between disruption onset and response initiation |
| `partial_recovery_days`| Integer (0–365) | Days to achieve partial production stabilization |
| `full_recovery_days` | Integer (0–1000)| Days to return to 100% operational baseline |
| `permanent_supplier_change`| Boolean | Whether supplier was terminated/replaced |

---

## 4. Algorithmic Formulations

### 4.1 Hybrid Retrieval: Reciprocal Rank Fusion (RRF)
Given a query $q$ and metadata filter constraint $F$, candidate rankings from the semantic leg $R_{\text{sem}}$ and keyword leg $R_{\text{kw}}$ are fused:

$$\text{RRF}(c) = \frac{\alpha}{k + \text{rank}_{\text{sem}}(c)} + \frac{1 - \alpha}{k + \text{rank}_{\text{kw}}(c)}$$

Where $k = 60$, $\alpha \in [0, 1]$ (default 0.60).
When a reference incident profile $I$ is available, candidate cases are re-ranked using attribute similarity:

$$\text{Similarity}(c, I) = \frac{\sum_j w_j \cdot \mathbb{I}(c_j = I_j)}{\sum_j w_j}$$

Where disruption type carries weight 3.0, industry 2.0, severity 2.0, backup 1.5, tier 1.0, region 1.0, and size 1.0.

### 4.2 Disruption Prioritization Scoring
For an incident $I$ with predicted impact $\hat{P}$, estimated financial loss $\hat{L}$, and risk probability $\hat{R}$:

$$\text{Score}(I) = 35 \cdot \left(\frac{\text{Severity} - 1}{4}\right) + 30 \cdot \left(\frac{\min(\hat{P}, 100)}{100}\right) + 25 \cdot \left(\frac{\log_{10}(\hat{L} / 10^4)}{\log_{10}(5 \cdot 10^7 / 10^4)}\right) + 10 \cdot \hat{R}$$

- **P1 - Critical** ($\ge 70$ pts): SLA 4h (War-room mobilization).
- **P2 - High** ($50–69$ pts): SLA 24h (Response plan formulation).
- **P3 - Medium** ($30–49$ pts): SLA 72h (Operational review).
- **P4 - Low** ($< 30$ pts): Weekly monitoring.

### 4.3 Supply Chain Resilience Score
A holistic $0–100$ index evaluating structural defense and recovery agility:

$$\text{Resilience} = S_{\text{backup}} + S_{\text{tier}} + S_{\text{size}} + S_{\text{velocity}} + S_{\text{absorption}}$$

- $S_{\text{backup}} \in \{0, 25\}$: $+25$ if dual-sourced with qualified backup.
- $S_{\text{tier}} \in [7.5, 15]$: Tier 1 direct visibility.
- $S_{\text{size}} \in \{5, 10, 15\}$: Large supplier financial solvency buffer.
- $S_{\text{velocity}} = 25 \cdot \max(0, 1 - \hat{D}_{\text{full}} / 200)$.
- $S_{\text{absorption}} = 20 \cdot \max(0, 1 - \hat{P}_{\text{impact}} / 100)$.

---

## 5. Security & Input Guardrails
- **Prompt Injection Defense**: Regex scanning against delimiter exploits, instruction overrides (`ignore previous instructions`, `you are now`, `system prompt`), and SQL injection patterns.
- **PII Scrubbing**: Automatic token masking for email addresses (`[REDACTED_EMAIL]`), credit cards, and social identification numbers before prompt ingestion.
- **Domain Relevance Barrier**: Token intersection gate requiring at least one domain keyword (supplier, tier, disruption, port, cyber, logistics, strike, factory, etc.) to prevent off-topic LLM abuse.
- **Range & Vocabulary Validation**: Strict Pydantic enforcement of severity ($1–5$), impact percentages ($0–100\%$), positive revenue values, and allowed categorical options.

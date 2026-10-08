# SOP-001: Respond to a Cyber Attack disruption

Standard operating procedures derived from the outcomes of 100000 historical supply chain disruptions. Each playbook gives the trigger, prerequisites, ordered steps with an owner, expected outcome and validation, and the escalation path.

## Procedure: Respond to a Cyber Attack disruption

Intent: restore production after a Cyber Attack disruption with the lowest recovery time and loss.

### Metadata

* Procedure ID: SOP-001
* Target disruption type: Cyber Attack
* Trigger: any Cyber Attack disruption. Severity 4-5 or production impact of 35% or more is P1 or P2: open a war-room within 4 hours.
* Evidence base: 14,887 historical Cyber Attack disruptions (43% at severity 4-5).

### Prerequisites

1. The incident is logged with disruption type, industry, supplier tier, region, size, backup status and severity.
2. The affected parts, open orders and inventory cover are known or being collected.
3. An incident owner is assigned in the Incident Desk.

### Ordered Steps

1. Classify and triage. Action: confirm it is a Cyber Attack disruption, record its attributes and compute the priority (35% severity, 30% production impact, 25% revenue loss, 10% risk). Owner: Supply Chain Ops Lead. Expected outcome: priority P1-P4 and SLA set within 1 hour. Validation: the incident shows a priority and an owner.
2. Assess impact. Action: estimate production impact and revenue at risk; historical Cyber Attack disruptions averaged 41.3% production impact and $3,365,434 revenue loss (90th percentile $8,092,893). Owner: Planning and Finance. Expected outcome: exposure quantified within 24 hours. Validation: predicted impact, loss and recovery ranges recorded on the incident.
3. Secure supply. Action: if a backup supplier exists, activate it now; if not, start qualifying an alternative supplier immediately. Cyber Attack cases with a backup recovered fully in 84.3 days on average versus 118.7 days without one. Owner: Procurement. Expected outcome: a confirmed alternative source. Validation: purchase order or capacity confirmation from the backup or alternative supplier.
4. Start the response within 3 days. Action: launch the selected strategy without waiting for complete information; responses started within 3 days averaged 93.9 days to full recovery versus 113.5 days when started after 7 days. Owner: Supply Chain Ops Lead. Expected outcome: response started by day 3. Validation: response start date logged.
5. Select the response strategy. Action: with a backup supplier, prefer Inventory Buffer (65.2 days average full recovery), then Customer Delay (80.0 days); without a backup supplier, prefer Alternative Supplier (86.2 days), then Inventory Buffer (86.7 days). Avoid Combined Strategy unless constrained (125.2 days). Owner: Supply Chain Ops Lead with Procurement. Expected outcome: one primary and one fallback strategy approved. Validation: both strategies recorded on the incident.
6. Track recovery. Action: hold a daily recovery stand-up; expect partial recovery in about 28 days. Escalate one level if full recovery is projected beyond 130 days (the 75th percentile for Cyber Attack). Owner: Incident owner. Expected outcome: partial recovery near day 28. Validation: recovery milestones updated at least weekly.
7. Close and learn. Action: record the actual recovery days and loss, decide on the supplier (29% of Cyber Attack disruptions ended in a permanent supplier change) and rate the recommendation. Owner: Incident owner. Expected outcome: the outcome is captured for model retraining and Synapt feedback. Validation: incident closed with the actual outcome recorded.

### Escalation

* P1: respond within 4 hours. Escalation chain: Operations Manager (at once) -> Head of Supply Chain (after 1h) -> War room (VP Operations) (after 2h).
* P2: respond within 24 hours. Escalation chain: Supplier Manager (at once) -> Operations Manager (after 12h).
* P3: respond within 72 hours. Escalation chain: Category Buyer (at once) -> Supplier Manager (after 48h).
* P4: respond within 168 hours. Escalation chain: Category Buyer (at once).

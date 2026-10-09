# Disruption Response Playbooks

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

## Procedure: Respond to a Factory Incident disruption

Intent: restore production after a Factory Incident disruption with the lowest recovery time and loss.

### Metadata

* Procedure ID: SOP-002
* Target disruption type: Factory Incident
* Trigger: any Factory Incident disruption. Severity 4-5 or production impact of 35% or more is P1 or P2: open a war-room within 4 hours.
* Evidence base: 11,878 historical Factory Incident disruptions (11% at severity 4-5).

### Prerequisites

1. The incident is logged with disruption type, industry, supplier tier, region, size, backup status and severity.
2. The affected parts, open orders and inventory cover are known or being collected.
3. An incident owner is assigned in the Incident Desk.

### Ordered Steps

1. Classify and triage. Action: confirm it is a Factory Incident disruption, record its attributes and compute the priority (35% severity, 30% production impact, 25% revenue loss, 10% risk). Owner: Supply Chain Ops Lead. Expected outcome: priority P1-P4 and SLA set within 1 hour. Validation: the incident shows a priority and an owner.
2. Assess impact. Action: estimate production impact and revenue at risk; historical Factory Incident disruptions averaged 29.6% production impact and $2,359,573 revenue loss (90th percentile $5,598,840). Owner: Planning and Finance. Expected outcome: exposure quantified within 24 hours. Validation: predicted impact, loss and recovery ranges recorded on the incident.
3. Secure supply. Action: if a backup supplier exists, activate it now; if not, start qualifying an alternative supplier immediately. Factory Incident cases with a backup recovered fully in 60.4 days on average versus 85.0 days without one. Owner: Procurement. Expected outcome: a confirmed alternative source. Validation: purchase order or capacity confirmation from the backup or alternative supplier.
4. Start the response within 3 days. Action: launch the selected strategy without waiting for complete information; responses started within 3 days averaged 67.0 days to full recovery versus 87.7 days when started after 7 days. Owner: Supply Chain Ops Lead. Expected outcome: response started by day 3. Validation: response start date logged.
5. Select the response strategy. Action: with a backup supplier, prefer Inventory Buffer (52.6 days average full recovery), then Alternative Supplier (57.9 days); without a backup supplier, prefer Alternative Supplier (66.2 days), then Inventory Buffer (74.9 days). Avoid Combined Strategy unless constrained (92.8 days). Owner: Supply Chain Ops Lead with Procurement. Expected outcome: one primary and one fallback strategy approved. Validation: both strategies recorded on the incident.
6. Track recovery. Action: hold a daily recovery stand-up; expect partial recovery in about 18 days. Escalate one level if full recovery is projected beyond 94 days (the 75th percentile for Factory Incident). Owner: Incident owner. Expected outcome: partial recovery near day 18. Validation: recovery milestones updated at least weekly.
7. Close and learn. Action: record the actual recovery days and loss, decide on the supplier (22% of Factory Incident disruptions ended in a permanent supplier change) and rate the recommendation. Owner: Incident owner. Expected outcome: the outcome is captured for model retraining and Synapt feedback. Validation: incident closed with the actual outcome recorded.

### Escalation

* P1: respond within 4 hours. Escalation chain: Operations Manager (at once) -> Head of Supply Chain (after 1h) -> War room (VP Operations) (after 2h).
* P2: respond within 24 hours. Escalation chain: Supplier Manager (at once) -> Operations Manager (after 12h).
* P3: respond within 72 hours. Escalation chain: Category Buyer (at once) -> Supplier Manager (after 48h).
* P4: respond within 168 hours. Escalation chain: Category Buyer (at once).

## Procedure: Respond to a Geopolitical disruption

Intent: restore production after a Geopolitical disruption with the lowest recovery time and loss.

### Metadata

* Procedure ID: SOP-003
* Target disruption type: Geopolitical
* Trigger: any Geopolitical disruption. Severity 4-5 or production impact of 35% or more is P1 or P2: open a war-room within 4 hours.
* Evidence base: 18,084 historical Geopolitical disruptions (21% at severity 4-5).

### Prerequisites

1. The incident is logged with disruption type, industry, supplier tier, region, size, backup status and severity.
2. The affected parts, open orders and inventory cover are known or being collected.
3. An incident owner is assigned in the Incident Desk.

### Ordered Steps

1. Classify and triage. Action: confirm it is a Geopolitical disruption, record its attributes and compute the priority (35% severity, 30% production impact, 25% revenue loss, 10% risk). Owner: Supply Chain Ops Lead. Expected outcome: priority P1-P4 and SLA set within 1 hour. Validation: the incident shows a priority and an owner.
2. Assess impact. Action: estimate production impact and revenue at risk; historical Geopolitical disruptions averaged 33.9% production impact and $2,691,691 revenue loss (90th percentile $6,386,810). Owner: Planning and Finance. Expected outcome: exposure quantified within 24 hours. Validation: predicted impact, loss and recovery ranges recorded on the incident.
3. Secure supply. Action: if a backup supplier exists, activate it now; if not, start qualifying an alternative supplier immediately. Geopolitical cases with a backup recovered fully in 68.8 days on average versus 96.7 days without one. Owner: Procurement. Expected outcome: a confirmed alternative source. Validation: purchase order or capacity confirmation from the backup or alternative supplier.
4. Start the response within 3 days. Action: launch the selected strategy without waiting for complete information; responses started within 3 days averaged 76.1 days to full recovery versus 96.7 days when started after 7 days. Owner: Supply Chain Ops Lead. Expected outcome: response started by day 3. Validation: response start date logged.
5. Select the response strategy. Action: with a backup supplier, prefer Inventory Buffer (57.3 days average full recovery), then Alternative Supplier (66.1 days); without a backup supplier, prefer Alternative Supplier (74.9 days), then Inventory Buffer (78.7 days). Avoid Combined Strategy unless constrained (105.8 days). Owner: Supply Chain Ops Lead with Procurement. Expected outcome: one primary and one fallback strategy approved. Validation: both strategies recorded on the incident.
6. Track recovery. Action: hold a daily recovery stand-up; expect partial recovery in about 22 days. Escalate one level if full recovery is projected beyond 106 days (the 75th percentile for Geopolitical). Owner: Incident owner. Expected outcome: partial recovery near day 22. Validation: recovery milestones updated at least weekly.
7. Close and learn. Action: record the actual recovery days and loss, decide on the supplier (25% of Geopolitical disruptions ended in a permanent supplier change) and rate the recommendation. Owner: Incident owner. Expected outcome: the outcome is captured for model retraining and Synapt feedback. Validation: incident closed with the actual outcome recorded.

### Escalation

* P1: respond within 4 hours. Escalation chain: Operations Manager (at once) -> Head of Supply Chain (after 1h) -> War room (VP Operations) (after 2h).
* P2: respond within 24 hours. Escalation chain: Supplier Manager (at once) -> Operations Manager (after 12h).
* P3: respond within 72 hours. Escalation chain: Category Buyer (at once) -> Supplier Manager (after 48h).
* P4: respond within 168 hours. Escalation chain: Category Buyer (at once).

## Procedure: Respond to a Labor Strike disruption

Intent: restore production after a Labor Strike disruption with the lowest recovery time and loss.

### Metadata

* Procedure ID: SOP-004
* Target disruption type: Labor Strike
* Trigger: any Labor Strike disruption. Severity 4-5 or production impact of 35% or more is P1 or P2: open a war-room within 4 hours.
* Evidence base: 15,017 historical Labor Strike disruptions (7% at severity 4-5).

### Prerequisites

1. The incident is logged with disruption type, industry, supplier tier, region, size, backup status and severity.
2. The affected parts, open orders and inventory cover are known or being collected.
3. An incident owner is assigned in the Incident Desk.

### Ordered Steps

1. Classify and triage. Action: confirm it is a Labor Strike disruption, record its attributes and compute the priority (35% severity, 30% production impact, 25% revenue loss, 10% risk). Owner: Supply Chain Ops Lead. Expected outcome: priority P1-P4 and SLA set within 1 hour. Validation: the incident shows a priority and an owner.
2. Assess impact. Action: estimate production impact and revenue at risk; historical Labor Strike disruptions averaged 26.0% production impact and $2,033,352 revenue loss (90th percentile $4,968,332). Owner: Planning and Finance. Expected outcome: exposure quantified within 24 hours. Validation: predicted impact, loss and recovery ranges recorded on the incident.
3. Secure supply. Action: if a backup supplier exists, activate it now; if not, start qualifying an alternative supplier immediately. Labor Strike cases with a backup recovered fully in 53.0 days on average versus 74.7 days without one. Owner: Procurement. Expected outcome: a confirmed alternative source. Validation: purchase order or capacity confirmation from the backup or alternative supplier.
4. Start the response within 3 days. Action: launch the selected strategy without waiting for complete information; responses started within 3 days averaged 58.9 days to full recovery versus 75.3 days when started after 7 days. Owner: Supply Chain Ops Lead. Expected outcome: response started by day 3. Validation: response start date logged.
5. Select the response strategy. Action: with a backup supplier, prefer Inventory Buffer (49.0 days average full recovery), then Alternative Supplier (51.0 days); without a backup supplier, prefer Inventory Buffer (64.4 days), then Alternative Supplier (65.0 days). Avoid Combined Strategy unless constrained (77.8 days). Owner: Supply Chain Ops Lead with Procurement. Expected outcome: one primary and one fallback strategy approved. Validation: both strategies recorded on the incident.
6. Track recovery. Action: hold a daily recovery stand-up; expect partial recovery in about 16 days. Escalate one level if full recovery is projected beyond 83 days (the 75th percentile for Labor Strike). Owner: Incident owner. Expected outcome: partial recovery near day 16. Validation: recovery milestones updated at least weekly.
7. Close and learn. Action: record the actual recovery days and loss, decide on the supplier (21% of Labor Strike disruptions ended in a permanent supplier change) and rate the recommendation. Owner: Incident owner. Expected outcome: the outcome is captured for model retraining and Synapt feedback. Validation: incident closed with the actual outcome recorded.

### Escalation

* P1: respond within 4 hours. Escalation chain: Operations Manager (at once) -> Head of Supply Chain (after 1h) -> War room (VP Operations) (after 2h).
* P2: respond within 24 hours. Escalation chain: Supplier Manager (at once) -> Operations Manager (after 12h).
* P3: respond within 72 hours. Escalation chain: Category Buyer (at once) -> Supplier Manager (after 48h).
* P4: respond within 168 hours. Escalation chain: Category Buyer (at once).

## Procedure: Respond to a Natural Disaster disruption

Intent: restore production after a Natural Disaster disruption with the lowest recovery time and loss.

### Metadata

* Procedure ID: SOP-005
* Target disruption type: Natural Disaster
* Trigger: any Natural Disaster disruption. Severity 4-5 or production impact of 35% or more is P1 or P2: open a war-room within 4 hours.
* Evidence base: 15,016 historical Natural Disaster disruptions (31% at severity 4-5).

### Prerequisites

1. The incident is logged with disruption type, industry, supplier tier, region, size, backup status and severity.
2. The affected parts, open orders and inventory cover are known or being collected.
3. An incident owner is assigned in the Incident Desk.

### Ordered Steps

1. Classify and triage. Action: confirm it is a Natural Disaster disruption, record its attributes and compute the priority (35% severity, 30% production impact, 25% revenue loss, 10% risk). Owner: Supply Chain Ops Lead. Expected outcome: priority P1-P4 and SLA set within 1 hour. Validation: the incident shows a priority and an owner.
2. Assess impact. Action: estimate production impact and revenue at risk; historical Natural Disaster disruptions averaged 37.3% production impact and $3,039,002 revenue loss (90th percentile $7,271,992). Owner: Planning and Finance. Expected outcome: exposure quantified within 24 hours. Validation: predicted impact, loss and recovery ranges recorded on the incident.
3. Secure supply. Action: if a backup supplier exists, activate it now; if not, start qualifying an alternative supplier immediately. Natural Disaster cases with a backup recovered fully in 77.3 days on average versus 107.2 days without one. Owner: Procurement. Expected outcome: a confirmed alternative source. Validation: purchase order or capacity confirmation from the backup or alternative supplier.
4. Start the response within 3 days. Action: launch the selected strategy without waiting for complete information; responses started within 3 days averaged 84.8 days to full recovery versus 107.4 days when started after 7 days. Owner: Supply Chain Ops Lead. Expected outcome: response started by day 3. Validation: response start date logged.
5. Select the response strategy. Action: with a backup supplier, prefer Inventory Buffer (62.1 days average full recovery), then Alternative Supplier (74.1 days); without a backup supplier, prefer Alternative Supplier (80.2 days), then Inventory Buffer (85.1 days). Avoid Combined Strategy unless constrained (117.9 days). Owner: Supply Chain Ops Lead with Procurement. Expected outcome: one primary and one fallback strategy approved. Validation: both strategies recorded on the incident.
6. Track recovery. Action: hold a daily recovery stand-up; expect partial recovery in about 25 days. Escalate one level if full recovery is projected beyond 120 days (the 75th percentile for Natural Disaster). Owner: Incident owner. Expected outcome: partial recovery near day 25. Validation: recovery milestones updated at least weekly.
7. Close and learn. Action: record the actual recovery days and loss, decide on the supplier (27% of Natural Disaster disruptions ended in a permanent supplier change) and rate the recommendation. Owner: Incident owner. Expected outcome: the outcome is captured for model retraining and Synapt feedback. Validation: incident closed with the actual outcome recorded.

### Escalation

* P1: respond within 4 hours. Escalation chain: Operations Manager (at once) -> Head of Supply Chain (after 1h) -> War room (VP Operations) (after 2h).
* P2: respond within 24 hours. Escalation chain: Supplier Manager (at once) -> Operations Manager (after 12h).
* P3: respond within 72 hours. Escalation chain: Category Buyer (at once) -> Supplier Manager (after 48h).
* P4: respond within 168 hours. Escalation chain: Category Buyer (at once).

## Procedure: Respond to a Port Congestion disruption

Intent: restore production after a Port Congestion disruption with the lowest recovery time and loss.

### Metadata

* Procedure ID: SOP-006
* Target disruption type: Port Congestion
* Trigger: any Port Congestion disruption. Severity 4-5 or production impact of 35% or more is P1 or P2: open a war-room within 4 hours.
* Evidence base: 25,118 historical Port Congestion disruptions (4% at severity 4-5).

### Prerequisites

1. The incident is logged with disruption type, industry, supplier tier, region, size, backup status and severity.
2. The affected parts, open orders and inventory cover are known or being collected.
3. An incident owner is assigned in the Incident Desk.

### Ordered Steps

1. Classify and triage. Action: confirm it is a Port Congestion disruption, record its attributes and compute the priority (35% severity, 30% production impact, 25% revenue loss, 10% risk). Owner: Supply Chain Ops Lead. Expected outcome: priority P1-P4 and SLA set within 1 hour. Validation: the incident shows a priority and an owner.
2. Assess impact. Action: estimate production impact and revenue at risk; historical Port Congestion disruptions averaged 24.3% production impact and $1,963,051 revenue loss (90th percentile $4,722,564). Owner: Planning and Finance. Expected outcome: exposure quantified within 24 hours. Validation: predicted impact, loss and recovery ranges recorded on the incident.
3. Secure supply. Action: if a backup supplier exists, activate it now; if not, start qualifying an alternative supplier immediately. Port Congestion cases with a backup recovered fully in 50.1 days on average versus 70.4 days without one. Owner: Procurement. Expected outcome: a confirmed alternative source. Validation: purchase order or capacity confirmation from the backup or alternative supplier.
4. Start the response within 3 days. Action: launch the selected strategy without waiting for complete information; responses started within 3 days averaged 55.8 days to full recovery versus 71.7 days when started after 7 days. Owner: Supply Chain Ops Lead. Expected outcome: response started by day 3. Validation: response start date logged.
5. Select the response strategy. Action: with a backup supplier, prefer Alternative Supplier (47.7 days average full recovery), then Inventory Buffer (50.1 days); without a backup supplier, prefer Inventory Buffer (63.8 days), then Production Reroute (69.2 days). Avoid Customer Delay unless constrained (72.5 days). Owner: Supply Chain Ops Lead with Procurement. Expected outcome: one primary and one fallback strategy approved. Validation: both strategies recorded on the incident.
6. Track recovery. Action: hold a daily recovery stand-up; expect partial recovery in about 16 days. Escalate one level if full recovery is projected beyond 77 days (the 75th percentile for Port Congestion). Owner: Incident owner. Expected outcome: partial recovery near day 16. Validation: recovery milestones updated at least weekly.
7. Close and learn. Action: record the actual recovery days and loss, decide on the supplier (20% of Port Congestion disruptions ended in a permanent supplier change) and rate the recommendation. Owner: Incident owner. Expected outcome: the outcome is captured for model retraining and Synapt feedback. Validation: incident closed with the actual outcome recorded.

### Escalation

* P1: respond within 4 hours. Escalation chain: Operations Manager (at once) -> Head of Supply Chain (after 1h) -> War room (VP Operations) (after 2h).
* P2: respond within 24 hours. Escalation chain: Supplier Manager (at once) -> Operations Manager (after 12h).
* P3: respond within 72 hours. Escalation chain: Category Buyer (at once) -> Supplier Manager (after 48h).
* P4: respond within 168 hours. Escalation chain: Category Buyer (at once).

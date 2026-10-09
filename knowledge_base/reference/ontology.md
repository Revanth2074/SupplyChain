# Supply Chain Disruption Ontology

This document defines the entities of the supply chain disruption domain and how they relate.

## Disruption types

Cyber Attack is a DisruptionType. Cyber Attack disruptions recover fastest with Inventory Buffer (81 days on average) and slowest with Combined Strategy (125 days). Cyber Attack RECOVERED_WITH Inventory Buffer. Cyber Attack disruptions cause 41% average production impact.
Factory Incident is a DisruptionType. Factory Incident disruptions recover fastest with Alternative Supplier (59 days on average) and slowest with Combined Strategy (93 days). Factory Incident RECOVERED_WITH Alternative Supplier. Factory Incident disruptions cause 30% average production impact.
Geopolitical is a DisruptionType. Geopolitical disruptions recover fastest with Alternative Supplier (67 days on average) and slowest with Combined Strategy (106 days). Geopolitical RECOVERED_WITH Alternative Supplier. Geopolitical disruptions cause 34% average production impact.
Labor Strike is a DisruptionType. Labor Strike disruptions recover fastest with Alternative Supplier (53 days on average) and slowest with Combined Strategy (78 days). Labor Strike RECOVERED_WITH Alternative Supplier. Labor Strike disruptions cause 26% average production impact.
Natural Disaster is a DisruptionType. Natural Disaster disruptions recover fastest with Alternative Supplier (75 days on average) and slowest with Combined Strategy (118 days). Natural Disaster RECOVERED_WITH Alternative Supplier. Natural Disaster disruptions cause 37% average production impact.
Port Congestion is a DisruptionType. Port Congestion disruptions recover fastest with Alternative Supplier (48 days on average) and slowest with Customer Delay (72 days). Port Congestion RECOVERED_WITH Alternative Supplier. Port Congestion disruptions cause 24% average production impact.

## Response strategies

Alternative Supplier is a ResponseStrategy. Alternative Supplier reaches full recovery in 63 days on average across all disruption types.
Combined Strategy is a ResponseStrategy. Combined Strategy reaches full recovery in 108 days on average across all disruption types.
Customer Delay is a ResponseStrategy. Customer Delay reaches full recovery in 80 days on average across all disruption types.
Inventory Buffer is a ResponseStrategy. Inventory Buffer reaches full recovery in 68 days on average across all disruption types.
Production Reroute is a ResponseStrategy. Production Reroute reaches full recovery in 89 days on average across all disruption types.

## Industries

Aerospace is an Industry. Aerospace is most EXPOSED_TO Cyber Attack, which causes the highest production impact for Aerospace suppliers.
Automotive is an Industry. Automotive is most EXPOSED_TO Cyber Attack, which causes the highest production impact for Automotive suppliers.
Consumer Goods is an Industry. Consumer Goods is most EXPOSED_TO Cyber Attack, which causes the highest production impact for Consumer Goods suppliers.
Electronics is an Industry. Electronics is most EXPOSED_TO Cyber Attack, which causes the highest production impact for Electronics suppliers.
Pharmaceuticals is an Industry. Pharmaceuticals is most EXPOSED_TO Cyber Attack, which causes the highest production impact for Pharmaceuticals suppliers.

## Supplier regions

Africa/Middle East is a SupplierRegion. Africa/Middle East is most often EXPOSED_TO Port Congestion.
Asia-Pacific is a SupplierRegion. Asia-Pacific is most often EXPOSED_TO Port Congestion.
Europe is a SupplierRegion. Europe is most often EXPOSED_TO Port Congestion.
North America is a SupplierRegion. North America is most often EXPOSED_TO Port Congestion.
South America is a SupplierRegion. South America is most often EXPOSED_TO Port Congestion.

## Supplier tiers

Tier 1 is a SupplierTier. Tier 1 suppliers recover fully in 72 days on average.
Tier 2 is a SupplierTier. Tier 2 suppliers recover fully in 75 days on average.
Tier 3 is a SupplierTier. Tier 3 suppliers recover fully in 79 days on average.
Tier 4 is a SupplierTier. Tier 4 suppliers recover fully in 81 days on average.

## Outcome metrics

Production Impact is an OutcomeMetric. Production Impact measures the share of production capacity lost.
Revenue Loss is an OutcomeMetric. Revenue Loss measures the money lost because of a disruption.
Full Recovery Time is an OutcomeMetric. Full Recovery Time measures days until operations are fully restored.
Backup Supplier is a ResponseStrategy enabler. Having a Backup Supplier shortens Full Recovery Time.

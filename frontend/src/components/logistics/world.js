/* World layout for the Control Tower (pure data, no rendering): island placement, sites,
 * ports, home-island piers, airports, sea routes and the disruption -> transport-mode rules. */
import {
  add, buildShipTimeline, dist, makeAirport, mul, norm, scheduleFleet, STAND_OFF,
} from './paths.js';

export const RISK = { Low: '#22c55e', Medium: '#3b82f6', High: '#f59e0b', Critical: '#ef4444' };
export const DISRUPTED_AT = 0.6; // high-impact probability at which a site "flares"

// which transport modes each disruption type stops in an affected region
export const MODE_IMPACT = {
  'Port Congestion': { sea: true, crane: true },
  'Labor Strike': { sea: true, crane: true, truck: true },
  Geopolitical: { sea: true, air: true },
  'Natural Disaster': { sea: true, air: true },
  'Cyber Attack': { air: true },
  'Factory Incident': {},
};

const REGION_POS = {
  'North America': [-38, -12.6],
  'South America': [-24, 26.5],
  Europe: [5.7, -36.8],
  'Africa/Middle East': [28.8, 20.7],
  'Asia-Pacific': [40.2, -11.5],
};
export const SPACING = 3.4;
export const HUB_R = 10.5;
export const HUB_SEED = 9.1;
export const HUB_POS = [0, -2];
export const SEA_Y = -0.5;
export const HUB_AIRPORT = makeAirport([-5.2, 6.9], [5.2, 6.9], [0, -1], 3);

/** Deterministic irregular coastline: radius multiplier in about [0.95, 1.19]. */
export const coast = (a, seed) => 1.07 + 0.07 * Math.sin(3 * a + seed) + 0.04 * Math.sin(5 * a + seed * 2.1)
  + 0.02 * Math.sin(11 * a + seed * 3.7);

export function layoutWorld(suppliers) {
  const byRegion = {};
  suppliers.forEach((s) => { (byRegion[s.supplier_region] = byRegion[s.supplier_region] || []).push(s); });
  const sites = [];
  const regions = Object.entries(byRegion).map(([region, list], ri) => {
    const C = REGION_POS[region] || [0, 40 + ri * 8];
    const u = norm([-C[0], -C[1]]); // region -> hub
    const p = [-u[1], u[0]];        // perpendicular
    const cols = Math.min(3, list.length);
    const rows = Math.ceil(list.length / cols);
    const gridR = Math.hypot(cols * SPACING, rows * SPACING) / 2;
    const R = gridR + 9; // room for the far-side airport and its apron
    const seed = ri * 1.7 + 0.6;
    const mySites = list.map((s, i) => ({
      ...s,
      pos: [C[0] + ((i % cols) - (cols - 1) / 2) * SPACING, C[1] + (Math.floor(i / cols) - (rows - 1) / 2) * SPACING],
    }));
    sites.push(...mySites);
    const port = add(C, mul(u, R * coast(Math.atan2(u[1], u[0]), seed) - 1.0));
    const hubAng = Math.atan2(-u[1], -u[0]);
    const pier = mul([-u[0], -u[1]], HUB_R * coast(hubAng, HUB_SEED) - 0.6);
    // runway on the far side of the island, perpendicular to the hub direction; apron faces inland (+u)
    const rwc = add(C, mul(u, -(R - 1.8)));
    const L = 8;
    const airport = makeAirport(add(rwc, mul(p, -L / 2)), add(rwc, mul(p, L / 2)), u, 1);
    return { region, C, u, p, R, seed, count: list.length, sites: mySites, port, pier, airport };
  });
  return { sites, regions };
}

/** Ship + aircraft timelines for the whole world (aircraft sequenced through the hub). */
export function buildTraffic(world) {
  const ships = world.regions.map((r) => buildShipTimeline(r));
  const air = scheduleFleet(world.regions.map((r) => r.airport), HUB_AIRPORT);
  return { ships, air };
}

export function regionStatus(world, disruption) {
  const hit = (s) => !!disruption && (s.by_type.find((t) => t.disruption_type === disruption)?.risk_probability ?? 0) >= DISRUPTED_AT;
  const modes = MODE_IMPACT[disruption] || {};
  const out = {};
  world.regions.forEach((r) => {
    const sitesHit = world.sites.filter((s) => s.supplier_region === r.region && hit(s)).length;
    const affected = sitesHit > 0;
    out[r.region] = {
      sitesHit,
      sea: affected && !!modes.sea, air: affected && !!modes.air,
      crane: affected && !!modes.crane, truck: affected && !!modes.truck,
    };
  });
  return { hit, byRegion: out };
}

/** Is point p inside an airport's paved / operational area (runway, taxiway, apron)? */
export function inAirport(ap, p, margin = 0) {
  const rel = [p[0] - ap.a[0], p[1] - ap.a[1]];
  const s = rel[0] * ap.d[0] + rel[1] * ap.d[1];
  const off = rel[0] * ap.n[0] + rel[1] * ap.n[1];
  return s > -2.2 - margin && s < ap.L + 2.2 + margin && off > -1.6 - margin && off < STAND_OFF + 2.6 + margin;
}

export const distToSeg = (p, a, b) => {
  const ab = [b[0] - a[0], b[1] - a[1]];
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / ((ab[0] ** 2 + ab[1] ** 2) || 1)));
  return dist(p, [a[0] + ab[0] * t, a[1] + ab[1] * t]);
};

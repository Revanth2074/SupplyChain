// Numerical checks for Control Tower traffic: no teleports, closed loops, sane speeds/attitudes,
// aircraft never below ground, and no overlapping hub runway/taxiway use. Run: npm run check:traffic
import { layoutWorld, buildTraffic, HUB_AIRPORT } from '../src/components/logistics/world.js';
import { sampleAt, PLANE } from '../src/components/logistics/paths.js';

const counts = { 'North America': 4, 'South America': 2, Europe: 5, 'Africa/Middle East': 2, 'Asia-Pacific': 5 };
const suppliers = [];
for (const [region, n] of Object.entries(counts)) for (let i = 0; i < n; i++) suppliers.push({ supplier_name: `${region}-${i}`, supplier_region: region, by_type: [] });
const world = layoutWorld(suppliers);
const { ships, air } = buildTraffic(world);
let fail = 0;
const check = (cond, msg) => { if (!cond) { fail++; console.log('FAIL', msg); } };

console.log(`slot ${air.slot.toFixed(1)}s  period ${air.period.toFixed(1)}s`);
air.fleet.forEach(({ timeline: tl, offset, dwellHub, dwellRegion }, i) => {
  const r = world.regions[i];
  check(Math.abs(tl.duration - air.period) < 0.6, `${r.region} duration ${tl.duration} vs period ${air.period}`);
  let nan = 0; let maxJump = 0; let minAirY = 99; let maxY = 0; let maxGroundYawRate = 0; let maxBank = 0; let maxPitch = -9; let minPitch = 9;
  for (let k = 0; k < tl.n; k++) {
    for (const a of [tl.x, tl.y, tl.z, tl.yaw, tl.pitch, tl.bank, tl.t]) if (!Number.isFinite(a[k])) nan++;
    maxY = Math.max(maxY, tl.y[k]);
    if (tl.y[k] > PLANE.gY + 0.01) minAirY = Math.min(minAirY, tl.y[k]);
    check(tl.y[k] >= PLANE.gY - 1e-3, `${r.region} below ground at ${k}`);
    maxBank = Math.max(maxBank, Math.abs(tl.bank[k])); maxPitch = Math.max(maxPitch, tl.pitch[k]); minPitch = Math.min(minPitch, tl.pitch[k]);
    if (k) {
      const dt = tl.t[k] - tl.t[k - 1];
      const d = Math.hypot(tl.x[k] - tl.x[k - 1], tl.z[k] - tl.z[k - 1]);
      if (dt > 1e-4) {
        maxJump = Math.max(maxJump, d / dt);
        if (tl.y[k] <= PLANE.gY + 0.01 && d > 1e-4) maxGroundYawRate = Math.max(maxGroundYawRate, Math.abs(tl.yaw[k] - tl.yaw[k - 1]) / dt);
      } else if (d > 1e-3) check(false, `${r.region} teleport ${d.toFixed(3)} at ${k}`);
    }
  }
  check(nan === 0, `${r.region} NaN x${nan}`);
  const first = [tl.x[0], tl.z[0], tl.yaw[0]]; const last = [tl.x[tl.n - 1], tl.z[tl.n - 1], tl.yaw[tl.n - 1]];
  check(Math.hypot(first[0] - last[0], first[1] - last[1]) < 1e-3, `${r.region} loop not closed`);
  check(Math.abs(Math.sin((first[2] - last[2]) / 2)) < 1e-3, `${r.region} heading not closed ${first[2]} ${last[2]}`);
  const e = tl.events;
  console.log(`${r.region.padEnd(19)} dwell hub ${dwellHub.toFixed(1)}s home ${dwellRegion.toFixed(1)}s | out flight ${(e.outTD - e.outAirStart).toFixed(1)}s ret ${(e.retTD - e.retAirStart).toFixed(1)}s | max speed ${maxJump.toFixed(2)} | cruise top ${maxY.toFixed(2)} | ground yaw rate ${maxGroundYawRate.toFixed(2)} rad/s | bank ${maxBank.toFixed(2)} pitch ${minPitch.toFixed(2)}..${maxPitch.toFixed(2)}`);
  check(dwellHub > 3 && dwellRegion > 3.5, `${r.region} dwell too short`);
  check(maxJump < PLANE.cruise * 1.15, `${r.region} speed spike ${maxJump}`);
  check(maxGroundYawRate < 2.5, `${r.region} spins on the ground ${maxGroundYawRate}`);
});

// hub ground/runway occupancy must never overlap between aircraft
const P = air.period;
const ivs = [];
air.fleet.forEach(({ timeline: tl, offset }, i) => {
  const e = tl.events;
  const abs = (t) => (((t - offset) % P) + P) % P;
  ivs.push({ i, kind: 'arr', a: abs(e.outTD - 2.5), b: abs(e.hubStand) });
  ivs.push({ i, kind: 'dep', a: abs(e.hubPush), b: abs(e.hubLO + 1) });
});
const overlaps = (x, y) => {
  const segs = (v) => (v.a <= v.b ? [[v.a, v.b]] : [[v.a, P], [0, v.b]]);
  return segs(x).some(([a1, b1]) => segs(y).some(([a2, b2]) => a1 < b2 && a2 < b1));
};
for (let a = 0; a < ivs.length; a++) for (let b = a + 1; b < ivs.length; b++) {
  if (overlaps(ivs[a], ivs[b])) check(false, `hub conflict ${ivs[a].kind}${ivs[a].i} vs ${ivs[b].kind}${ivs[b].i}`);
}
console.log('hub windows:', ivs.sort((x, y) => x.a - y.a).map((v) => `${v.kind}${v.i} ${v.a.toFixed(0)}-${v.b.toFixed(0)}`).join(' | '));

// planes parked at the hub at the same time must use different stands
// ships
ships.forEach((tl, i) => {
  let nan = 0; let maxV = 0;
  for (let k = 1; k < tl.n; k++) {
    if (!Number.isFinite(tl.x[k] + tl.z[k] + tl.yaw[k])) nan++;
    const dt = tl.t[k] - tl.t[k - 1];
    const d = Math.hypot(tl.x[k] - tl.x[k - 1], tl.z[k] - tl.z[k - 1]);
    if (dt > 1e-4) maxV = Math.max(maxV, d / dt); else if (d > 1e-3) check(false, `ship ${i} teleport`);
  }
  check(nan === 0, `ship ${i} NaN`);
  check(Math.hypot(tl.x[0] - tl.x[tl.n - 1], tl.z[0] - tl.z[tl.n - 1]) < 1e-3, `ship ${i} loop not closed`);
  console.log(`ship ${world.regions[i].region.padEnd(19)} cycle ${tl.duration.toFixed(1)}s max speed ${maxV.toFixed(2)}`);
});
console.log(fail ? `${fail} FAILURES` : 'ALL CHECKS PASSED');
process.exit(fail ? 1 : 0);

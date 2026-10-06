/* Pure geometry + timeline maths for the Control Tower (no React / three.js, unit-testable).
 *
 * Aircraft fly a full operation: pushback, taxi, line-up, takeoff roll, rotation, climb,
 * turn, cruise, stabilised approach on the runway centreline, flare, rollout, runway exit,
 * taxi-in, turnaround at the stand. The hub runway is sequenced so only one aircraft uses
 * the hub runway / taxiway at a time. Ships berth alongside quays and are turned by tugs.
 */

// ------------------------------------------------------------------ 2D vectors
export const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
export const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
export const mul = (a, k) => [a[0] * k, a[1] * k];
export const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
export const len = (a) => Math.hypot(a[0], a[1]);
export const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
export const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
export const norm = (a) => { const l = len(a) || 1; return [a[0] / l, a[1] / l]; };
export const ease = (t) => t * t * (3 - 2 * t);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const headingOf = (d) => Math.atan2(d[1], d[0]);

// ------------------------------------------------------------------ dense path primitives
export function lineSamples(p, q, step) {
  const n = Math.max(1, Math.ceil(dist(p, q) / step));
  return Array.from({ length: n + 1 }, (_, i) => lerp(p, q, i / n));
}

function quadSamples(p0, c, p1, step) {
  const n = Math.max(2, Math.ceil((dist(p0, c) + dist(c, p1)) / step));
  return Array.from({ length: n + 1 }, (_, i) => {
    const t = i / n; const u = 1 - t;
    return [u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0], u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]];
  });
}

export function cubicSamples(p0, p1, p2, p3, step) {
  const n = Math.max(4, Math.ceil((dist(p0, p1) + dist(p1, p2) + dist(p2, p3)) / step));
  return Array.from({ length: n + 1 }, (_, i) => {
    const t = i / n; const u = 1 - t;
    const a = u * u * u; const b = 3 * u * u * t; const c = 3 * u * t * t; const d = t * t * t;
    return [a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]];
  });
}

/** Polyline with every interior corner replaced by a smooth turn of radius r. */
export function roundedPath(pts, r = 0.7, step = 0.06) {
  const out = [pts[0]];
  let cur = pts[0];
  for (let i = 1; i < pts.length; i++) {
    const p = pts[i];
    if (i < pts.length - 1) {
      const din = norm(sub(p, pts[i - 1])); const dout = norm(sub(pts[i + 1], p));
      const rr = Math.min(r, dist(pts[i - 1], p) / 2, dist(p, pts[i + 1]) / 2);
      const pin = sub(p, mul(din, rr)); const pout = add(p, mul(dout, rr));
      out.push(...lineSamples(cur, pin, step).slice(1), ...quadSamples(pin, p, pout, step).slice(1));
      cur = pout;
    } else {
      out.push(...lineSamples(cur, p, step).slice(1));
    }
  }
  return out;
}

const smin = (a, b, k = 0.6) => -k * Math.log(Math.exp(-a / k) + Math.exp(-b / k));

// speed profiles: (s, S) -> speed
export const trapezoid = (v0, vm, v1, ramp) => (s, S) => Math.max(Math.min(v0, v1, vm),
  Math.min(vm, v0 + (vm - v0) * (s / ramp), v1 + (vm - v1) * ((S - s) / ramp)));
const kinematic = (v0, v1) => (s, S) => Math.sqrt(Math.max(0, v0 * v0 + (v1 * v1 - v0 * v0) * (S ? s / S : 1)));

// ------------------------------------------------------------------ track builder
/** A track is a list of samples {x, z, y, v, rev, gear, air, bias, yaw?, dt?}; finalize() turns it into a timeline. */
export function addMove(track, pts, { v, y = 0, rev = false, gear = true, air = false, bias = 0, maxYawRate = air ? Infinity : 1.2 }) {
  const cum = [0];
  for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + dist(pts[i - 1], pts[i]));
  const S = cum[cum.length - 1];
  const at = (f, s) => (typeof f === 'function' ? f(s, S) : f);
  // slow down for turns: speed <= max yaw rate * local turn radius
  const limit = pts.map((p, i) => {
    if (!Number.isFinite(maxYawRate) || i === 0 || i === pts.length - 1) return Infinity;
    const a = sub(p, pts[i - 1]); const b = sub(pts[i + 1], p);
    const turn = Math.abs(wrap(headingOf(b) - headingOf(a)));
    const ds = (len(a) + len(b)) / 2;
    return turn > 1e-4 ? maxYawRate * (ds / turn) : Infinity;
  });
  // spread each limit over its neighbours so the aircraft brakes into the turn instead of snapping
  const lim = limit.map((_, i) => Math.min(...limit.slice(Math.max(0, i - 6), i + 7)));
  const last = track[track.length - 1];
  pts.forEach((p, i) => {
    if (i === 0 && last && dist([last.x, last.z], p) < 1e-6) return;
    const vv = Math.max(0.04, Math.min(at(v, cum[i]), lim[i]));
    track.push({ x: p[0], z: p[1], y: at(y, cum[i]), v: vv, rev, gear: at(gear, cum[i]), air, bias: at(bias, cum[i]) });
  });
  return S;
}

export function addHold(track, dt, extra = {}) {
  const last = track[track.length - 1];
  track.push({ ...last, v: 0, dt, hold: true, ...extra });
}

/** Rotate (and optionally drift) in place over `dt` seconds - tugs turning a ship. */
export function addTurn(track, fromYaw, toYaw, dt, to = null, steps = 40) {
  const last = track[track.length - 1];
  const start = [last.x, last.z];
  const dy = wrap(toYaw - fromYaw);
  for (let i = 1; i <= steps; i++) {
    const k = ease(i / steps);
    const p = to ? lerp(start, to, k) : start;
    track.push({ ...last, x: p[0], z: p[1], v: 0, dt: dt / steps, hold: true, yaw: fromYaw + dy * k });
  }
}

const GLIDE_WINDOW = 4;

export function finalize(track) {
  const n = track.length;
  const t = new Float32Array(n); const x = new Float32Array(n); const y = new Float32Array(n); const z = new Float32Array(n);
  const yaw = new Float32Array(n); const pitch = new Float32Array(n); const bank = new Float32Array(n);
  const gear = new Uint8Array(n); const spd = new Float32Array(n);
  // heading
  for (let i = 0; i < n; i++) {
    const s = track[i];
    if (s.yaw !== undefined) { yaw[i] = s.yaw; continue; }
    if (s.hold && i > 0) { yaw[i] = yaw[i - 1]; continue; }
    let d = null;
    for (let j = i + 1; j < Math.min(n, i + 6); j++) {
      if (track[j].hold) break;
      if (dist([track[j].x, track[j].z], [s.x, s.z]) > 1e-5) { d = [track[j].x - s.x, track[j].z - s.z]; break; }
    }
    if (!d && i > 0) d = [s.x - track[i - 1].x, s.z - track[i - 1].z];
    yaw[i] = d && len(d) > 1e-6 ? headingOf(d) + (s.rev ? Math.PI : 0) : (i ? yaw[i - 1] : 0);
  }
  // unwrap so interpolation never spins the long way round
  for (let i = 1; i < n; i++) yaw[i] = yaw[i - 1] + wrap(yaw[i] - yaw[i - 1]);
  // time
  for (let i = 0; i < n; i++) {
    const s = track[i];
    x[i] = s.x; y[i] = s.y; z[i] = s.z; gear[i] = s.gear ? 1 : 0; spd[i] = s.v;
    if (i === 0) { t[i] = 0; continue; }
    if (s.dt !== undefined) { t[i] = t[i - 1] + s.dt; continue; }
    const p = track[i - 1];
    const ds = Math.hypot(s.x - p.x, s.z - p.z, s.y - p.y);
    t[i] = t[i - 1] + ds / Math.max(0.04, (s.v + p.v) / 2);
  }
  // attitude: pitch = flight-path angle + body bias, bank = coordinated-turn bank angle
  for (let i = 0; i < n; i++) {
    const s = track[i];
    let fpa = 0; let bk = 0;
    if (s.air && i > 0 && i < n - 1) {
      const a = track[i - 1]; const b = track[i + 1];
      const h = Math.hypot(b.x - a.x, b.z - a.z) || 1e-6;
      fpa = Math.atan2(b.y - a.y, h);
      const kappa = wrap(yaw[i + 1] - yaw[i - 1]) / h;
      bk = clamp(Math.atan((s.v * s.v * kappa) / 6), -0.5, 0.5);
    }
    pitch[i] = fpa + (s.bias || 0);
    bank[i] = bk;
  }
  const smooth = (arr, w) => {
    const src = Float32Array.from(arr);
    for (let i = 0; i < n; i++) {
      let acc = 0; let c = 0;
      for (let j = Math.max(0, i - w); j <= Math.min(n - 1, i + w); j++) { acc += src[j]; c++; }
      arr[i] = acc / c;
    }
  };
  smooth(pitch, GLIDE_WINDOW); smooth(bank, 8);
  return { t, x, y, z, yaw, pitch, bank, gear, spd, duration: t[n - 1], n };
}

/** Interpolated state of a timeline at time tau (seconds, wrapped). */
export function sampleAt(tl, tau, out = {}) {
  const T = tl.duration;
  let q = ((tau % T) + T) % T;
  let lo = 0; let hi = tl.n - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (tl.t[mid] <= q) lo = mid; else hi = mid; }
  const span = tl.t[hi] - tl.t[lo];
  const f = span > 0 ? Math.min(1, (q - tl.t[lo]) / span) : 0;
  const L = (arr) => arr[lo] + (arr[hi] - arr[lo]) * f;
  out.x = L(tl.x); out.y = L(tl.y); out.z = L(tl.z);
  out.yaw = L(tl.yaw); out.pitch = L(tl.pitch); out.bank = L(tl.bank);
  out.gear = tl.gear[f < 0.5 ? lo : hi] === 1; out.v = L(tl.spd);
  return out;
}

// ------------------------------------------------------------------ airports
export const TAXI_OFF = 1.6;   // runway centreline -> parallel taxiway
export const STAND_OFF = 4.0;  // runway centreline -> stand (aircraft centre, nose toward terminal)
export const STAND_GAP = 2.6;  // stand spacing along the apron (> wingspan)

/** a -> b is the runway in use (takeoff and landing direction); n points from the runway to the apron. */
export function makeAirport(a, b, n, standCount = 1) {
  const d = norm(sub(b, a)); const L = dist(a, b);
  const at = (s, off) => add(add(a, mul(d, s)), mul(n, off));
  const stands = Array.from({ length: standCount }, (_, k) => {
    const s = L / 2 + (k - (standCount - 1) / 2) * STAND_GAP;
    return { s, pos: at(s, STAND_OFF) };
  });
  return { a, b, d, n, L, at, stands, connA: -0.8, exitS: 0.9 * L, tdS: 0.15 * L, lineupS: 0.5, rollFrac: 0.55 };
}

// ------------------------------------------------------------------ aircraft operations
export const PLANE = { push: 0.8, taxi: 1.8, rot: 3.6, climb: 4.6, cruise: 5.4, app: 3.6, alt: 8.5, climbGrad: 0.28, glideGrad: 0.16, gY: 0.25 };
const FINAL = 9; // final approach fix distance before touchdown

function parkedSample(ap, k) {
  const st = ap.stands[k];
  return { x: st.pos[0], z: st.pos[1], y: PLANE.gY, v: 0, rev: false, gear: true, air: false, bias: 0, yaw: headingOf(ap.n) };
}

/** Pushback, taxi to the threshold, line up, hold, takeoff roll. Returns the liftoff point. */
function departure(tr, ap, k, ev, tag) {
  const st = ap.stands[k];
  const K = ap.at(st.s, TAXI_OFF);
  ev[`${tag}Push`] = tr.length - 1;
  // tug pushes the aircraft straight back, then swings the tail so the nose ends up facing the threshold
  addMove(tr, roundedPath([st.pos, K, ap.at(st.s + 1.3, TAXI_OFF)], 1.2), { v: trapezoid(0.05, PLANE.push, 0.05, 0.5), y: PLANE.gY, rev: true });
  addHold(tr, 1.2); // tug disconnect, engine start
  addMove(tr, roundedPath([ap.at(st.s + 1.3, TAXI_OFF), ap.at(ap.connA, TAXI_OFF), ap.at(ap.connA, 0), ap.at(ap.lineupS, 0)], 0.65),
    { v: trapezoid(0.05, PLANE.taxi, 0.05, 1.0), y: PLANE.gY });
  addHold(tr, 1.5); // lined up, waiting for takeoff clearance
  const roll = ap.L * ap.rollFrac;
  const lo = ap.at(ap.lineupS + roll, 0);
  addMove(tr, lineSamples(ap.at(ap.lineupS, 0), lo, 0.08), {
    v: kinematic(0.15, PLANE.rot), y: PLANE.gY,
    bias: (s, S) => 0.17 * clamp((s / S - 0.75) / 0.25, 0, 1), // rotation in the last quarter of the roll
  });
  ev[`${tag}LO`] = tr.length - 1;
  return lo;
}

/** Initial climb on runway heading, turn, cruise, stabilised approach on the destination centreline. */
function flight(tr, from, lo, to, ev, tag) {
  const td = to.at(to.tdS, 0);
  const c1 = add(lo, mul(from.d, 4));
  const fix = sub(td, mul(to.d, FINAL));
  const k = clamp(dist(c1, fix) * 0.4, 3, 16);
  const pts = [
    ...lineSamples(lo, c1, 0.15),
    ...cubicSamples(c1, add(c1, mul(from.d, k)), sub(fix, mul(to.d, k)), fix, 0.15).slice(1),
    ...lineSamples(fix, td, 0.15).slice(1),
  ];
  ev[`${tag}AirStart`] = tr.length - 1;
  addMove(tr, pts, {
    air: true,
    y: (s, S) => PLANE.gY + Math.max(0, smin(smin(PLANE.climbGrad * s, PLANE.alt), PLANE.glideGrad * (S - s))),
    v: (s, S) => (s < 6 ? PLANE.rot + (PLANE.cruise - PLANE.rot) * (s / 6)
      : S - s < FINAL ? PLANE.app + (PLANE.cruise - PLANE.app) * ((S - s) / FINAL) : PLANE.cruise),
    gear: (s, S) => s < 2.5 || S - s < FINAL + 1, // retract after climb-out, extend before the final fix
    bias: (s, S) => (S - s < FINAL ? 0.2 + 0.06 * clamp(1 - (S - s), 0, 1) : 0.06), // approach attitude + flare
  });
  ev[`${tag}TD`] = tr.length - 1;
  return td;
}

/** Rollout, runway exit, taxi to the stand (nose in). */
function arrival(tr, ap, k, ev, tag) {
  const st = ap.stands[k];
  const r1 = ap.at(ap.exitS - 0.6, 0);
  addMove(tr, lineSamples(ap.at(ap.tdS, 0), r1, 0.08), {
    v: kinematic(PLANE.app, 1.4), y: PLANE.gY,
    bias: (s) => Math.max(0, 0.12 * (1 - s / 0.8)), // nose-wheel lowering after touchdown
  });
  addMove(tr, roundedPath([r1, ap.at(ap.exitS + 0.3, 0), ap.at(ap.exitS + 0.3, TAXI_OFF), ap.at(st.s, TAXI_OFF), st.pos], 0.75),
    { v: trapezoid(1.4, PLANE.taxi, 0.05, 1.0), y: PLANE.gY });
  ev[`${tag}Stand`] = tr.length - 1;
}

/** Complete round trip region -> hub -> region, starting and ending parked at the region stand. */
export function buildPlaneTimeline(region, hub, hubStand, dwellRegion, dwellHub) {
  const tr = [parkedSample(region, 0)];
  const ev = {};
  addHold(tr, Math.max(0.1, dwellRegion));
  const lo1 = departure(tr, region, 0, ev, 'reg');
  flight(tr, region, lo1, hub, ev, 'out');
  arrival(tr, hub, hubStand, ev, 'hub');
  addHold(tr, Math.max(0.1, dwellHub));
  const lo2 = departure(tr, hub, hubStand, ev, 'hub');
  flight(tr, hub, lo2, region, ev, 'ret');
  arrival(tr, region, 0, ev, 'reg2');
  // make sure the loop closes exactly on the parked heading
  tr.push({ ...parkedSample(region, 0), dt: 0.5, hold: true });
  const tl = finalize(tr);
  tl.events = Object.fromEntries(Object.entries(ev).map(([key, i]) => [key, tl.t[i]]));
  return tl;
}

/**
 * Sequence all aircraft through the hub so ground operations never overlap:
 * slot j = [arrival of plane j: short final -> stand][departure of plane j-1: pushback -> liftoff].
 * Returns per-plane {timeline, offset}; state at clock c = sampleAt(timeline, c + offset).
 */
export function scheduleFleet(regionAirports, hub) {
  const n = regionAirports.length;
  const stand = (i) => i % hub.stands.length;
  const probe = regionAirports.map((ap, i) => buildPlaneTimeline(ap, hub, stand(i), 0, 0));
  const arrBlock = probe.map((tl) => tl.events.hubStand - tl.events.outTD + 2.5);
  const depBlock = probe.map((tl) => tl.events.hubLO - tl.events.hubPush + 1.0);
  const maxArr = Math.max(...arrBlock); const maxDep = Math.max(...depBlock);
  const minSlot = maxArr + maxDep + 3;
  const base = probe.map((tl) => tl.duration);       // duration with zero dwell
  const taxiIn = probe.map((tl) => tl.events.hubStand - tl.events.outTD);
  if (n === 1) {
    const tl = buildPlaneTimeline(regionAirports[0], hub, 0, 4, 8);
    return { slot: tl.duration, period: tl.duration, fleet: [{ timeline: tl, offset: 0 }] };
  }
  // each plane must fit its whole round trip (plus >= 4 s parked at home) into n slots
  const slot = Math.max(minSlot, ...base.map((b, i) => (b + maxArr + 2.5 - taxiIn[i] + 4) / (n - 1)));
  const period = n * slot;
  const fleet = regionAirports.map((ap, i) => {
    const dwellHub = slot + maxArr - 1.5 - taxiIn[i];   // push back right after the next arrival clears
    const dwellRegion = period - base[i] - dwellHub;
    const tl = buildPlaneTimeline(ap, hub, stand(i), dwellRegion, dwellHub);
    // touchdown of plane i at the hub happens at clock i*slot + 2.5
    return { timeline: tl, offset: tl.events.outTD - (i * slot + 2.5), dwellHub, dwellRegion };
  });
  return { slot, period, fleet };
}

// ------------------------------------------------------------------ ships
export const SHIP = { sea: 1.5, berth: 0.12, dwell: 6, turn: 7 };

/**
 * Container ship shuttle between a regional quay (berth alongside, heading +-p) and a home jetty
 * (berth alongside, heading u). Tugs pull it off the berth and turn it at each end.
 */
export function buildShipTimeline({ port, pier, u, p }) {
  const A = add(port, mul(u, 2.8));                       // alongside the regional quay
  const Aoff = add(A, mul(u, 2.0));                       // swung clear of the quay
  const B = add(add(pier, mul(u, -1.7)), mul(p, 1.35));   // alongside the home jetty
  const Boff = add(B, mul(p, 1.6));
  const hA = p; const hB = u;
  const tr = [{ x: A[0], z: A[1], y: 0, v: 0, rev: false, gear: false, air: false, bias: 0, yaw: headingOf(mul(hA, -1)) }];
  const voyage = (from, hFrom, to, hTo) => {
    const k = clamp(dist(from, to) * 0.35, 3, 14);
    addMove(tr, cubicSamples(from, add(from, mul(hFrom, k)), sub(to, mul(hTo, k)), to, 0.12),
      { v: trapezoid(SHIP.berth, SHIP.sea, SHIP.berth, 2.5) });
  };
  addHold(tr, SHIP.dwell);                                               // cargo ops at the regional quay
  addTurn(tr, headingOf(mul(hA, -1)), headingOf(hA), SHIP.turn, Aoff);  // tugs swing her round
  voyage(Aoff, hA, B, hB);
  addHold(tr, SHIP.dwell);                                               // discharge at the home jetty
  addTurn(tr, headingOf(hB), headingOf(mul(hB, -1)), SHIP.turn, Boff);
  voyage(Boff, mul(hB, -1), A, mul(hA, -1));
  const tl = finalize(tr);
  tl.outbound = cubicSamples(Aoff, add(Aoff, mul(hA, clamp(dist(Aoff, B) * 0.35, 3, 14))), sub(B, mul(hB, clamp(dist(Aoff, B) * 0.35, 3, 14))), B, 0.5);
  tl.anchor = add(add(A, mul(u, 5.5)), mul(p, 2.5));
  tl.anchorYaw = headingOf(u);
  return tl;
}

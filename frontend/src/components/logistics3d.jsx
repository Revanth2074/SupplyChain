/* Multi-modal 3D logistics world for the Control Tower.
 * Regions are islands around a home island (your plant). Trucks run on land, container ships
 * berth alongside quays and sail curved sea routes, B747 freighters fly full airport-to-airport
 * operations sequenced through the hub (see logistics/paths.js). A selected disruption type
 * halts the transport modes it would realistically hit. */
import React, { useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { Html, Line, RoundedBox } from '@react-three/drei';
import { add, mul, norm, lerp, ease, sampleAt } from './logistics/paths.js';
import {
  HUB_AIRPORT, HUB_POS, HUB_R, HUB_SEED, RISK, SEA_Y, buildTraffic, coast, distToSeg, inAirport, layoutWorld, regionStatus,
} from './logistics/world.js';
import { Airport, B747 } from './logistics/aircraft.jsx';

export { DISRUPTED_AT, MODE_IMPACT, RISK, layoutWorld, regionStatus } from './logistics/world.js';

const SIZE = { Large: [2.5, 1.7, 2.1], Medium: [2.0, 1.3, 1.7], Small: [1.5, 1.0, 1.3] };
const CONTAINER_COLORS = ['#c2410c', '#1d4ed8', '#15803d', '#b45309', '#0e7490', '#6d28d9', '#be123c', '#475569'];

/** Ocean swell height at (x, z, t); ships sample the same function so they ride the waves. */
const wave = (x, z, t) => 0.045 * Math.sin(0.33 * x + t * 0.9) + 0.035 * Math.sin(0.41 * z - t * 0.7)
  + 0.02 * Math.sin(0.8 * (x + z) + t * 1.3);

function rng(seed) {
  let s = Math.abs(Math.floor(seed * 9301 + 49297)) % 233280;
  return () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
}

// ------------------------------------------------------------------ terrain
function Ocean() {
  const ref = useRef();
  const geo = useMemo(() => new THREE.PlaneGeometry(260, 260, 96, 96), []);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = clock.elapsedTime;
    const g = ref.current.geometry;
    const pos = g.attributes.position;
    for (let i = 0; i < pos.count; i++) pos.setZ(i, wave(pos.getX(i), -pos.getY(i), t)); // local y = -world z
    pos.needsUpdate = true;
    g.computeVertexNormals();
  });
  return (
    <mesh ref={ref} geometry={geo} rotation={[-Math.PI / 2, 0, 0]} position={[0, SEA_Y, 0]} receiveShadow>
      <meshStandardMaterial color="#4aa6e3" roughness={0.32} metalness={0.02} />
    </mesh>
  );
}

function coastShape(R, seed, scale = 1) {
  const shape = new THREE.Shape();
  const n = 80;
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * Math.PI * 2;
    const r = R * coast(a, seed) * scale;
    const x = Math.cos(a) * r; const z = Math.sin(a) * r;
    if (i === 0) shape.moveTo(x, -z); else shape.lineTo(x, -z); // shape y = -world z
  }
  return shape;
}

function Island({ c, R, seed, tint = '#9cc97a', alert = false }) {
  const geos = useMemo(() => ({
    shelf: new THREE.ShapeGeometry(coastShape(R, seed, 1.3)),
    beach: new THREE.ExtrudeGeometry(coastShape(R, seed, 1.07), { depth: 0.32, bevelEnabled: true, bevelThickness: 0.05, bevelSize: 0.25, bevelSegments: 2, curveSegments: 4 }),
    land: new THREE.ExtrudeGeometry(coastShape(R, seed, 1.0), { depth: 0.42, bevelEnabled: true, bevelThickness: 0.06, bevelSize: 0.18, bevelSegments: 2, curveSegments: 4 }),
  }), [R, seed]);
  return (
    <group position={[c[0], 0, c[1]]}>
      <mesh geometry={geos.shelf} rotation={[-Math.PI / 2, 0, 0]} position={[0, SEA_Y + 0.07, 0]}>
        <meshStandardMaterial color="#5ec8d8" transparent opacity={0.55} roughness={0.3} />
      </mesh>
      <mesh geometry={geos.beach} rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.62, 0]} receiveShadow>
        <meshStandardMaterial color="#e9d8a6" roughness={0.95} />
      </mesh>
      <mesh geometry={geos.land} rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.48, 0]} receiveShadow>
        <meshStandardMaterial color={alert ? '#c9b48f' : tint} roughness={0.95} />
      </mesh>
    </group>
  );
}

function Pad({ center, w, d, color = '#d5d9df' }) {
  return (
    <mesh position={[center[0], 0.015, center[1]]} receiveShadow>
      <boxGeometry args={[w, 0.03, d]} />
      <meshStandardMaterial color={color} roughness={0.9} />
    </mesh>
  );
}

function Road({ from, to, active }) {
  const len = Math.hypot(to[0] - from[0], to[1] - from[1]);
  const ang = Math.atan2(to[1] - from[1], to[0] - from[0]);
  const dashes = Math.max(0, Math.floor(len / 0.8) - 1);
  return (
    <group position={[(from[0] + to[0]) / 2, 0.03, (from[1] + to[1]) / 2]} rotation={[0, -ang, 0]}>
      <mesh receiveShadow><boxGeometry args={[len, 0.03, 0.6]} /><meshStandardMaterial color={active ? '#7f1d1d' : '#3f4752'} roughness={0.85} /></mesh>
      {[-0.27, 0.27].map((z) => (
        <mesh key={z} position={[0, 0.018, z]}><boxGeometry args={[len, 0.005, 0.03]} /><meshStandardMaterial color="#d6d3d1" /></mesh>
      ))}
      {Array.from({ length: dashes }).map((_, i) => (
        <mesh key={i} position={[-len / 2 + 0.8 * (i + 1), 0.018, 0]}><boxGeometry args={[0.34, 0.005, 0.04]} /><meshStandardMaterial color={active ? '#fca5a5' : '#facc15'} /></mesh>
      ))}
    </group>
  );
}

function Pine({ p, s, c }) {
  return (
    <group position={[p[0], 0, p[1]]} scale={s}>
      <mesh position={[0, 0.2, 0]} castShadow><cylinderGeometry args={[0.06, 0.08, 0.4, 6]} /><meshStandardMaterial color="#6b4423" /></mesh>
      <mesh position={[0, 0.65, 0]} castShadow><coneGeometry args={[0.42, 0.8, 7]} /><meshStandardMaterial color={c} flatShading /></mesh>
      <mesh position={[0, 1.05, 0]} castShadow><coneGeometry args={[0.3, 0.6, 7]} /><meshStandardMaterial color={c} flatShading /></mesh>
    </group>
  );
}

function Broadleaf({ p, s, c }) {
  return (
    <group position={[p[0], 0, p[1]]} scale={s}>
      <mesh position={[0, 0.25, 0]} castShadow><cylinderGeometry args={[0.06, 0.09, 0.5, 6]} /><meshStandardMaterial color="#6b4423" /></mesh>
      <mesh position={[0, 0.75, 0]} castShadow><icosahedronGeometry args={[0.45, 0]} /><meshStandardMaterial color={c} flatShading /></mesh>
      <mesh position={[0.2, 0.62, 0.12]} castShadow><icosahedronGeometry args={[0.3, 0]} /><meshStandardMaterial color={c} flatShading /></mesh>
    </group>
  );
}

function Hill({ p, s }) {
  return (
    <mesh position={[p[0], -0.05, p[1]]} scale={[s * 1.6, s * 0.55, s * 1.3]} castShadow receiveShadow>
      <icosahedronGeometry args={[1, 1]} />
      <meshStandardMaterial color="#7fb35f" flatShading roughness={1} />
    </mesh>
  );
}

const TREE_GREENS = ['#2f7d32', '#3f8f3a', '#4b9b3f', '#2e6b30', '#5aa64a'];

/** Vegetation on free land, avoiding sites, roads, ports and airports. */
function Scenery({ c, R, seed, blocked, count = 44 }) {
  const { trees, hills } = useMemo(() => {
    const r = rng(seed * 100 + 7);
    const t = []; const h = [];
    for (let i = 0; i < 260 && t.length < count; i++) {
      const a = r() * Math.PI * 2;
      const rad = Math.sqrt(r()) * R * coast(a, seed) * 0.9;
      const p = [c[0] + Math.cos(a) * rad, c[1] + Math.sin(a) * rad];
      const s = 0.6 + r() * 0.6; const col = TREE_GREENS[Math.floor(r() * TREE_GREENS.length)]; const kind = r() > 0.45;
      if (!blocked(p, 0.9)) t.push({ p, s, c: col, kind });
    }
    for (let i = 0; i < 40 && h.length < 3; i++) {
      const a = r() * Math.PI * 2;
      const rad = (0.55 + r() * 0.3) * R;
      const p = [c[0] + Math.cos(a) * rad, c[1] + Math.sin(a) * rad];
      const s = 0.9 + r() * 0.8;
      if (!blocked(p, 2.2)) h.push({ p, s });
    }
    return { trees: t, hills: h };
  }, [c, R, seed, blocked, count]);
  return (
    <>
      {hills.map((h, i) => <Hill key={`h${i}`} p={h.p} s={h.s} />)}
      {trees.map((t, i) => (t.kind ? <Pine key={i} p={t.p} s={t.s} c={t.c} /> : <Broadleaf key={i} p={t.p} s={t.s} c={t.c} />))}
    </>
  );
}

function Clouds() {
  const group = useRef();
  const clouds = useMemo(() => {
    const r = rng(42);
    return Array.from({ length: 5 }).map(() => ({
      x: -70 + r() * 140, z: -50 + r() * 100, y: 17 + r() * 4, s: 0.55 + r() * 0.45, v: 0.5 + r() * 0.5,
      puffs: Array.from({ length: 5 }).map(() => [r() * 3 - 1.5, r() * 0.6, r() * 1.6 - 0.8, 0.9 + r() * 0.8]),
    }));
  }, []);
  useFrame((_, dt) => {
    group.current?.children.forEach((g, i) => {
      g.position.x += clouds[i].v * dt;
      if (g.position.x > 80) g.position.x = -80;
    });
  });
  return (
    <group ref={group}>
      {clouds.map((c, i) => (
        <group key={i} position={[c.x, c.y, c.z]} scale={c.s}>
          {c.puffs.map((p, k) => (
            <mesh key={k} position={[p[0], p[1], p[2]]} castShadow>
              <icosahedronGeometry args={[p[3], 1]} />
              <meshStandardMaterial color="#ffffff" transparent opacity={0.72} roughness={1} flatShading depthWrite={false} />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  );
}

// ------------------------------------------------------------------ containers, port, crane
function ContainerBox({ position, color, size = [0.9, 0.42, 0.4] }) {
  return (
    <mesh position={position} castShadow receiveShadow>
      <boxGeometry args={size} />
      <meshStandardMaterial color={color} roughness={0.75} />
    </mesh>
  );
}

function ContainerYard({ cols = 3, rows = 2, layers = 2, seed = 0 }) {
  const boxes = [];
  for (let l = 0; l < layers; l++) {
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        if ((c + r + l + seed) % 5 === 4 && l > 0) continue; // ragged top like a real yard
        const k = (c * 7 + r * 13 + l * 5 + seed) % CONTAINER_COLORS.length;
        boxes.push(<ContainerBox key={`${l}${r}${c}`} position={[c * 0.95, 0.21 + l * 0.43, r * 0.45]} color={CONTAINER_COLORS[k]} />);
      }
    }
  }
  return <group>{boxes}</group>;
}

/** Ship-to-shore gantry crane. Local +x points out to sea. Lifts containers ship -> yard. */
function GantryCrane({ frozen }) {
  const trolley = useRef();
  const load = useRef();
  const cable = useRef();
  useFrame(({ clock }) => {
    if (frozen || !trolley.current) return;
    const cyc = (clock.elapsedTime % 9) / 9;
    // .00-.30 run out empty, .30-.45 lower + pick up, .45-.75 run back loaded, .75-1 lower to the yard
    let x; let drop; let loaded;
    if (cyc < 0.3) { x = THREE.MathUtils.lerp(-0.6, 2.6, ease(cyc / 0.3)); drop = 0.3; loaded = false; } else if (cyc < 0.45) { x = 2.6; drop = 0.3 + Math.sin(((cyc - 0.3) / 0.15) * Math.PI) * 1.6; loaded = cyc > 0.375; } else if (cyc < 0.75) { x = THREE.MathUtils.lerp(2.6, -0.6, ease((cyc - 0.45) / 0.3)); drop = 0.3; loaded = true; } else { x = -0.6; drop = 0.3 + Math.sin(((cyc - 0.75) / 0.25) * Math.PI) * 1.4; loaded = cyc < 0.875; }
    trolley.current.position.x = x;
    cable.current.scale.y = drop;
    cable.current.position.y = -drop / 2;
    load.current.position.y = -drop - 0.22;
    load.current.visible = loaded;
  });
  const steel = frozen ? '#9ca3af' : '#e0a21b';
  return (
    <group>
      {[-0.75, 0.75].map((z) => [-0.9, 0.9].map((x) => (
        <mesh key={`${x}${z}`} position={[x, 1.6, z]} castShadow><boxGeometry args={[0.13, 3.2, 0.13]} /><meshStandardMaterial color={steel} /></mesh>
      )))}
      {[-0.75, 0.75].map((z) => (
        <mesh key={`b${z}`} position={[0, 0.5, z]} castShadow><boxGeometry args={[1.9, 0.12, 0.12]} /><meshStandardMaterial color={steel} /></mesh>
      ))}
      <mesh position={[0.9, 3.25, 0]} castShadow><boxGeometry args={[4.6, 0.22, 1.7]} /><meshStandardMaterial color={steel} /></mesh>
      <mesh position={[-0.9, 3.55, 0]} castShadow><boxGeometry args={[0.6, 0.45, 0.8]} /><meshStandardMaterial color="#f1f5f9" /></mesh>
      <group ref={trolley} position={[-0.6, 3.05, 0]}>
        <mesh castShadow><boxGeometry args={[0.45, 0.22, 0.6]} /><meshStandardMaterial color="#334155" /></mesh>
        <mesh ref={cable} position={[0, -0.15, 0]}><boxGeometry args={[0.025, 1, 0.025]} /><meshStandardMaterial color="#111827" /></mesh>
        <group ref={load} position={[0, -0.5, 0]}>
          <ContainerBox position={[0, 0, 0]} color="#c2410c" />
        </group>
      </group>
    </group>
  );
}

/** Regional port: quay apron, crane, container yard, bollards. Local +x = sea. */
function Port({ at, u, frozen, label, seed }) {
  const ang = Math.atan2(u[1], u[0]);
  return (
    <group position={[at[0], 0, at[1]]} rotation={[0, -ang, 0]}>
      <mesh position={[-0.6, 0.0, 0]} receiveShadow><boxGeometry args={[5.4, 0.06, 4.6]} /><meshStandardMaterial color="#c9ced6" /></mesh>
      <mesh position={[1.75, -0.22, 0]} receiveShadow castShadow><boxGeometry args={[1.0, 0.5, 4.6]} /><meshStandardMaterial color="#a8afb9" /></mesh>
      {[-1.7, -0.6, 0.6, 1.7].map((z) => (
        <mesh key={z} position={[2.1, 0.12, z]}><cylinderGeometry args={[0.07, 0.09, 0.2, 8]} /><meshStandardMaterial color="#1f2937" /></mesh>
      ))}
      <group position={[0.8, 0, 0]}><GantryCrane frozen={frozen} /></group>
      <group position={[-2.9, 0, -1.9]}><ContainerYard cols={2} rows={4} layers={3} seed={seed} /></group>
      <group position={[-2.9, 0, 0.6]}><ContainerYard cols={2} rows={3} layers={2} seed={seed + 3} /></group>
      {label && (
        <Html zIndexRange={[10, 0]} position={[0, 4.4, 0]} center style={{ pointerEvents: 'none' }}>
          <div className={`ct-tag ${frozen ? 'ct-tag-red' : ''}`}>{label}</div>
        </Html>
      )}
    </group>
  );
}

function Pier({ at, u }) {
  const ang = Math.atan2(u[1], u[0]); // jetty runs along -u, out to sea toward the region
  return (
    <group position={[at[0], 0, at[1]]} rotation={[0, -ang, 0]}>
      <mesh position={[-1.2, -0.2, 0]} receiveShadow castShadow><boxGeometry args={[2.8, 0.45, 1.5]} /><meshStandardMaterial color="#a8afb9" /></mesh>
      {[-2.3, -1.3, -0.3].map((x) => (
        <mesh key={x} position={[x, 0.08, 0.62]}><cylinderGeometry args={[0.07, 0.09, 0.2, 8]} /><meshStandardMaterial color="#1f2937" /></mesh>
      ))}
      <mesh position={[-0.6, 0.55, -0.5]} castShadow><boxGeometry args={[0.1, 1.1, 0.1]} /><meshStandardMaterial color="#e5e7eb" /></mesh>
      <mesh position={[-0.6, 1.12, -0.5]}><sphereGeometry args={[0.08, 8, 8]} /><meshBasicMaterial color="#f59e0b" /></mesh>
    </group>
  );
}

// ------------------------------------------------------------------ ship
const HULL = (() => {
  const s = new THREE.Shape();
  s.moveTo(-1.9, -0.5); s.lineTo(1.2, -0.5); s.quadraticCurveTo(1.85, -0.45, 2.15, 0);
  s.quadraticCurveTo(1.85, 0.45, 1.2, 0.5); s.lineTo(-1.9, 0.5); s.quadraticCurveTo(-2.05, 0, -1.9, -0.5);
  return s;
})();
const HULL_LOW = new THREE.ExtrudeGeometry(HULL, { depth: 0.22, bevelEnabled: true, bevelThickness: 0.03, bevelSize: 0.03, bevelSegments: 1 });
const HULL_HIGH = new THREE.ExtrudeGeometry(HULL, { depth: 0.32, bevelEnabled: true, bevelThickness: 0.03, bevelSize: 0.03, bevelSegments: 1 });

function ShipModel({ halted, seed }) {
  const stacks = [];
  for (let b = 0; b < 6; b++) {
    const tiers = 2 + ((b + seed) % 2);
    for (let l = 0; l < tiers; l++) {
      for (let r = 0; r < 3; r++) {
        stacks.push(<ContainerBox key={`${b}${l}${r}`} size={[0.5, 0.25, 0.27]}
          position={[-0.95 + b * 0.52, 0.71 + l * 0.255, -0.29 + r * 0.29]}
          color={CONTAINER_COLORS[(b * 3 + l + r * 5 + seed) % CONTAINER_COLORS.length]} />);
      }
    }
  }
  return (
    <group>
      <mesh geometry={HULL_LOW} rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]} castShadow><meshStandardMaterial color="#9f1d1d" roughness={0.6} /></mesh>
      <mesh geometry={HULL_HIGH} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.2, 0]} castShadow><meshStandardMaterial color={halted ? '#7f1d1d' : '#1f2f4a'} roughness={0.5} /></mesh>
      <mesh position={[0.1, 0.55, 0]}><boxGeometry args={[3.7, 0.03, 0.95]} /><meshStandardMaterial color="#8b9199" /></mesh>
      {stacks}
      <mesh position={[-1.55, 0.98, 0]} castShadow><boxGeometry args={[0.42, 0.85, 0.85]} /><meshStandardMaterial color="#f8fafc" /></mesh>
      <mesh position={[-1.55, 1.45, 0]} castShadow><boxGeometry args={[0.46, 0.1, 1.15]} /><meshStandardMaterial color="#f8fafc" /></mesh>
      <mesh position={[-1.33, 1.3, 0]}><boxGeometry args={[0.02, 0.1, 0.8]} /><meshStandardMaterial color="#0f172a" /></mesh>
      <mesh position={[-1.8, 1.55, 0]} castShadow><boxGeometry args={[0.22, 0.4, 0.3]} /><meshStandardMaterial color="#1e3a8a" /></mesh>
      <mesh position={[-1.8, 1.78, 0]}><boxGeometry args={[0.23, 0.07, 0.31]} /><meshStandardMaterial color="#111827" /></mesh>
      <mesh position={[1.75, 0.82, 0]}><cylinderGeometry args={[0.02, 0.02, 0.5, 6]} /><meshStandardMaterial color="#e5e7eb" /></mesh>
    </group>
  );
}

const WAKE = (() => {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, -3.4, 0, 1.0, -3.4, 0, -1.0], 3));
  g.computeVertexNormals();
  return g;
})();

/** Plays back a ship timeline (berth, tug turn, voyage) and rides the swell; anchors offshore when halted. */
function Ship({ tl, halted, phase, seed }) {
  const ref = useRef();
  const wake = useRef();
  const st = useMemo(() => ({}), []);
  useFrame(({ clock }) => {
    const g = ref.current;
    if (!g) return;
    const t = clock.elapsedTime;
    let x; let z; let yaw; let v;
    if (halted) {
      [x, z] = tl.anchor; yaw = tl.anchorYaw + Math.sin(t * 0.15) * 0.3; v = 0; // swinging at anchor
    } else {
      sampleAt(tl, t + phase, st);
      ({ x, z, yaw, v } = st);
    }
    const fx = Math.cos(yaw); const fz = Math.sin(yaw);
    const pitch = (wave(x + fx * 0.9, z + fz * 0.9, t) - wave(x - fx * 0.9, z - fz * 0.9, t)) * 0.55;
    const roll = Math.sin(t * 0.9 + phase) * 0.03;
    g.position.set(x, SEA_Y + wave(x, z, t) - 0.08, z);
    g.rotation.set(roll, -yaw, pitch, 'YZX');
    if (wake.current) {
      wake.current.visible = v > 0.35;
      wake.current.scale.set(Math.min(1, v / 1.5), 1, 1);
    }
  });
  return (
    <group ref={ref}>
      <ShipModel halted={halted} seed={seed} />
      <mesh ref={wake} geometry={WAKE} position={[-1.9, 0.06, 0]}>
        <meshBasicMaterial color="#ffffff" transparent opacity={0.4} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
    </group>
  );
}

// ------------------------------------------------------------------ aircraft
/** Plays back a scheduled 747 timeline: attitude (pitch / coordinated bank), gear up/down. */
function Aircraft({ timeline, offset, grounded }) {
  const ref = useRef();
  const gear = useRef();
  const st = useMemo(() => ({}), []);
  useFrame(({ clock }) => {
    const g = ref.current;
    if (!g) return;
    if (grounded) { // held at its home stand
      g.position.set(timeline.x[0], timeline.y[0], timeline.z[0]);
      g.rotation.set(0, -timeline.yaw[0], 0, 'YZX');
      if (gear.current) gear.current.visible = true;
      return;
    }
    sampleAt(timeline, clock.elapsedTime + offset, st);
    g.position.set(st.x, st.y, st.z);
    g.rotation.set(st.bank, -st.yaw, st.pitch, 'YZX');
    if (gear.current) gear.current.visible = st.gear;
  });
  return <group ref={ref}><B747 grounded={grounded} gearRef={gear} /></group>;
}

// ------------------------------------------------------------------ road vehicles
function TruckModel({ halted, container }) {
  return (
    <group>
      <mesh position={[-0.25, 0.14, 0]} castShadow><boxGeometry args={[1.0, 0.08, 0.38]} /><meshStandardMaterial color="#1f2937" /></mesh>
      <ContainerBox position={[-0.25, 0.4, 0]} size={[0.92, 0.42, 0.38]} color={halted ? '#9ca3af' : container} />
      <mesh position={[0.42, 0.29, 0]} castShadow><boxGeometry args={[0.34, 0.44, 0.4]} /><meshStandardMaterial color={halted ? '#dc2626' : '#f1f5f9'} /></mesh>
      <mesh position={[0.6, 0.36, 0]}><boxGeometry args={[0.02, 0.17, 0.34]} /><meshStandardMaterial color="#0f172a" metalness={0.5} roughness={0.2} /></mesh>
      {[-0.6, -0.15, 0.42].map((x) => [-0.2, 0.2].map((z) => (
        <mesh key={`${x}${z}`} position={[x, 0.08, z]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[0.08, 0.08, 0.06, 10]} /><meshStandardMaterial color="#111827" /></mesh>
      )))}
      {[0.13, -0.13].map((z) => (
        <mesh key={z} position={[0.6, 0.18, z]}><boxGeometry args={[0.02, 0.05, 0.07]} /><meshBasicMaterial color="#fef9c3" /></mesh>
      ))}
    </group>
  );
}

/** Drives from -> to in the right-hand lane, pauses to load, U-turns, drives back. */
function Truck({ from, to, halted, phase, period = 22, container }) {
  const ref = useRef();
  const dir = norm([to[0] - from[0], to[1] - from[1]]);
  const lane = mul([-dir[1], dir[0]], 0.14);
  useFrame(({ clock }) => {
    const g = ref.current;
    if (!g) return;
    const base = -Math.atan2(dir[1], dir[0]);
    if (halted) {
      const p = add(lerp(from, to, 0.12), lane);
      g.position.set(p[0], 0.05, p[1]); g.rotation.y = base;
      return;
    }
    const cyc = ((clock.elapsedTime + phase * period) % period) / period;
    let t; let yaw;
    if (cyc < 0.42) { t = ease(cyc / 0.42); yaw = base; } else if (cyc < 0.5) { t = 1; yaw = base + Math.PI * ease((cyc - 0.42) / 0.08); } else if (cyc < 0.92) { t = 1 - ease((cyc - 0.5) / 0.42); yaw = base + Math.PI; } else { t = 0; yaw = base + Math.PI + Math.PI * ease((cyc - 0.92) / 0.08); }
    const side = cyc >= 0.5 && cyc < 0.92 ? -1 : 1;
    const p = add(lerp(from, to, t), mul(lane, side));
    g.position.set(p[0], 0.05, p[1]);
    g.rotation.y = yaw;
  });
  return <group ref={ref}><TruckModel halted={halted} container={container} /></group>;
}

function Forklift({ a, b, phase }) {
  const ref = useRef();
  const fork = useRef();
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const s = Math.sin(clock.elapsedTime * 0.6 + phase);
    const p = lerp(a, b, (s + 1) / 2);
    ref.current.position.set(p[0], 0.03, p[1]);
    ref.current.rotation.y = -Math.atan2(b[1] - a[1], b[0] - a[0]) + (Math.cos(clock.elapsedTime * 0.6 + phase) < 0 ? Math.PI : 0);
    if (fork.current) fork.current.position.y = 0.12 + Math.max(0, s) * 0.4;
  });
  return (
    <group ref={ref}>
      <mesh position={[0, 0.2, 0]} castShadow><boxGeometry args={[0.5, 0.26, 0.36]} /><meshStandardMaterial color="#facc15" /></mesh>
      <mesh position={[-0.12, 0.42, 0]} castShadow><boxGeometry args={[0.24, 0.18, 0.32]} /><meshStandardMaterial color="#1f2937" /></mesh>
      <mesh position={[-0.02, 0.62, 0]}><boxGeometry args={[0.36, 0.03, 0.34]} /><meshStandardMaterial color="#111827" /></mesh>
      <mesh position={[0.27, 0.45, 0]}><boxGeometry args={[0.05, 0.8, 0.3]} /><meshStandardMaterial color="#475569" /></mesh>
      <group ref={fork} position={[0.42, 0.12, 0]}>
        <mesh><boxGeometry args={[0.3, 0.03, 0.26]} /><meshStandardMaterial color="#475569" /></mesh>
        <mesh position={[0.02, 0.1, 0]} castShadow><boxGeometry args={[0.3, 0.16, 0.28]} /><meshStandardMaterial color="#b45309" /></mesh>
      </group>
    </group>
  );
}

function Smoke({ at }) {
  const ref = useRef();
  useFrame(({ clock }) => {
    ref.current?.children.forEach((m, i) => {
      const k = (clock.elapsedTime * 0.25 + i / 6) % 1;
      m.position.set(k * 0.5, k * 2.6, -k * 1.4); // prevailing wind carries it north, away from the airfield
      m.scale.setScalar(0.2 + k * 0.45);
      m.material.opacity = 0.55 * (1 - k);
    });
  });
  return (
    <group ref={ref} position={at}>
      {Array.from({ length: 6 }).map((_, i) => (
        <mesh key={i}><icosahedronGeometry args={[0.5, 1]} /><meshStandardMaterial color="#e5e7eb" transparent opacity={0.4} depthWrite={false} /></mesh>
      ))}
    </group>
  );
}

// ------------------------------------------------------------------ sites + hub
function Pin({ color = '#2563eb' }) {
  const ref = useRef();
  useFrame(({ clock }) => { if (ref.current) ref.current.position.y = 3.1 + Math.sin(clock.elapsedTime * 3) * 0.15; });
  return (
    <group ref={ref}>
      <mesh rotation={[Math.PI, 0, 0]} castShadow><coneGeometry args={[0.28, 0.6, 16]} /><meshStandardMaterial color={color} /></mesh>
      <mesh position={[0, 0.42, 0]}><sphereGeometry args={[0.3, 20, 20]} /><meshStandardMaterial color={color} /></mesh>
    </group>
  );
}

function Flare() {
  const ring = useRef();
  useFrame(({ clock }) => {
    const t = (clock.elapsedTime * 0.8) % 1;
    if (ring.current) { ring.current.scale.setScalar(1 + t * 1.6); ring.current.material.opacity = 0.55 * (1 - t); }
  });
  return (
    <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.06, 0]}>
      <ringGeometry args={[1.3, 1.55, 40]} />
      <meshBasicMaterial color="#ef4444" transparent opacity={0.5} />
    </mesh>
  );
}

function Site({ site, selected, hovered, disrupted, onSelect, onHover }) {
  const [w, h, d] = SIZE[site.supplier_size] || SIZE.Medium;
  const roof = useRef();
  useFrame(({ clock }) => {
    if (roof.current) roof.current.emissiveIntensity = disrupted ? 0.35 + Math.sin(clock.elapsedTime * 5) * 0.25 : 0;
  });
  const tone = RISK[site.band] || RISK.Medium;
  return (
    <group
      position={[site.pos[0], 0, site.pos[1]]}
      onClick={(e) => { e.stopPropagation(); onSelect(site); }}
      onPointerOver={(e) => { e.stopPropagation(); onHover(site.supplier_name); document.body.style.cursor = 'pointer'; }}
      onPointerOut={() => { onHover(null); document.body.style.cursor = 'auto'; }}
    >
      <Pad center={[0.2, 0.2]} w={w + 1.5} d={d + 1.3} />
      <RoundedBox args={[w, h, d]} radius={0.06} position={[0, h / 2 + 0.03, 0]} castShadow receiveShadow>
        <meshStandardMaterial color={selected ? '#ffffff' : '#eef1f5'} roughness={0.7} />
      </RoundedBox>
      <mesh position={[0, h + 0.07, 0]}><boxGeometry args={[w + 0.1, 0.08, d + 0.1]} /><meshStandardMaterial ref={roof} color={tone} emissive="#ef4444" emissiveIntensity={0} /></mesh>
      {[-1, 0, 1].map((k) => (
        <mesh key={k} position={[k * w / 3, h + 0.2, 0]} rotation={[0, 0, 0.35]} castShadow>
          <boxGeometry args={[w / 3 + 0.05, 0.05, d + 0.1]} />
          <meshStandardMaterial color={tone} />
        </mesh>
      ))}
      {[-0.3, 0.3].map((x) => (
        <mesh key={x} position={[x * w, 0.42, d / 2 + 0.01]}><boxGeometry args={[w * 0.25, 0.7, 0.03]} /><meshStandardMaterial color="#64748b" /></mesh>
      ))}
      <mesh position={[0, h * 0.78, d / 2 + 0.01]}><boxGeometry args={[w * 0.85, 0.12, 0.02]} /><meshStandardMaterial color="#1e3a5f" metalness={0.4} roughness={0.2} /></mesh>
      {Array.from({ length: site.supplier_tier }).map((_, i) => (
        <mesh key={i} position={[-w / 2 - 0.01, h - 0.25 - i * 0.18, 0]}><boxGeometry args={[0.03, 0.1, d * 0.6]} /><meshStandardMaterial color={tone} /></mesh>
      ))}
      <mesh position={[w / 2 - 0.3, h + 0.6, -d / 2 + 0.3]} castShadow><cylinderGeometry args={[0.1, 0.13, 1.1, 10]} /><meshStandardMaterial color="#9ca3af" /></mesh>
      <group position={[w / 2 + 0.25, 0.03, -d / 2 + 0.1]}><ContainerYard cols={1} rows={2} layers={site.supplier_size === 'Large' ? 2 : 1} seed={site.supplier_tier} /></group>
      {!site.has_backup_supplier && (
        <mesh position={[-w / 2 + 0.25, h + 0.5, -d / 2 + 0.25]}><boxGeometry args={[0.12, 0.6, 0.12]} /><meshStandardMaterial color="#f97316" /></mesh>
      )}
      {disrupted && <Flare />}
      {selected && <Pin color="#2563eb" />}
      {!selected && disrupted && <Pin color="#ef4444" />}
      {(hovered || selected) && (
        <Html zIndexRange={[10, 0]} position={[0, h + 1.0, 0]} center style={{ pointerEvents: 'none' }}>
          <div className="ct-label"><strong>{site.supplier_name}</strong><span>{site.risk_index} · {site.band}</span></div>
        </Html>
      )}
    </group>
  );
}


function Hub() {
  const [x, z] = HUB_POS;
  return (
    <group position={[x, 0, z]}>
      <Pad center={[0, 0.3]} w={13} d={6.6} color="#cfd4db" />
      <RoundedBox args={[5, 2.4, 3.6]} radius={0.1} position={[0, 1.23, 0]} castShadow receiveShadow>
        <meshStandardMaterial color="#2f6fed" roughness={0.6} />
      </RoundedBox>
      <mesh position={[0, 2.5, 0]} castShadow><boxGeometry args={[5.2, 0.2, 3.8]} /><meshStandardMaterial color="#e5e7eb" /></mesh>
      {[-1.6, 1.6].map((dx) => [-0.9, 0.9].map((dz) => (
        <mesh key={`${dx}${dz}`} position={[dx, 2.7, dz]}><boxGeometry args={[0.5, 0.2, 0.5]} /><meshStandardMaterial color="#9ca3af" /></mesh>
      )))}
      {[-1.5, -0.5, 0.5, 1.5].map((dx) => (
        <mesh key={dx} position={[dx, 0.6, 1.81]}><boxGeometry args={[0.8, 1.1, 0.04]} /><meshStandardMaterial color="#1e3a8a" /></mesh>
      ))}
      <mesh position={[-2.0, 2.9, -1.2]} castShadow><cylinderGeometry args={[0.22, 0.3, 3.2, 12]} /><meshStandardMaterial color="#b91c1c" /></mesh>
      <mesh position={[-2.0, 3.6, -1.2]}><cylinderGeometry args={[0.24, 0.24, 0.25, 12]} /><meshStandardMaterial color="#f8fafc" /></mesh>
      <Smoke at={[-2.0, 4.6, -1.2]} />
      <group position={[3.2, 0.03, -0.9]}><ContainerYard cols={2} rows={4} layers={2} seed={3} /></group>
      <group position={[-5.6, 0.03, -0.9]}><ContainerYard cols={2} rows={4} layers={3} seed={5} /></group>
      <Html zIndexRange={[10, 0]} position={[0, 3.6, 0]} center style={{ pointerEvents: 'none' }}>
        <div className="ct-tag ct-tag-blue">Your plant</div>
      </Html>
    </group>
  );
}

function RegionLabel({ r, atRisk }) {
  return (
    <Html zIndexRange={[10, 0]} position={[r.C[0], 0.1, r.C[1] + r.R * 1.2 + 1.2]} center style={{ pointerEvents: 'none' }}>
      <div className="ct-region">{r.region}<span>{r.count} site{r.count > 1 ? 's' : ''}{atRisk ? ` · ${atRisk} at risk` : ''}</span></div>
    </Html>
  );
}

// ------------------------------------------------------------------ world
function RegionIsland({ r, ri, st, hover, setHover, selected, setSelected, hit }) {
  const blocked = useMemo(() => (p, m) => (
    r.sites.some((s) => Math.hypot(p[0] - s.pos[0], p[1] - s.pos[1]) < 2.3 + m)
    || r.sites.some((s) => distToSeg(p, s.pos, r.port) < 0.7 + m)
    || Math.hypot(p[0] - r.port[0], p[1] - r.port[1]) < 4.2 + m
    || inAirport(r.airport, p, m * 0.6)
  ), [r]);
  return (
    <group>
      <Island c={r.C} R={r.R} seed={r.seed} alert={st.sitesHit > 0} />
      <Scenery c={r.C} R={r.R} seed={r.seed} blocked={blocked} />
      <RegionLabel r={r} atRisk={st.sitesHit} />
      <Airport ap={r.airport} />
      <Port at={r.port} u={r.u} frozen={st.crane} seed={ri * 3} label={st.crane ? 'Port halted' : st.sea ? 'Berth closed' : null} />
      {r.sites.map((s, i) => {
        const halted = hit(s) || st.truck;
        const toPort = norm([r.port[0] - s.pos[0], r.port[1] - s.pos[1]]);
        return (
          <group key={s.supplier_name}>
            <Road from={s.pos} to={r.port} active={halted} />
            <Site site={s} selected={selected?.supplier_name === s.supplier_name} hovered={hover === s.supplier_name}
              disrupted={hit(s)} onSelect={setSelected} onHover={setHover} />
            <Truck from={add(s.pos, mul(toPort, 1.6))} to={add(r.port, mul(r.u, -2.6))}
              halted={halted} phase={(i * 0.31 + ri * 0.17) % 1} period={18 + (i % 3) * 3}
              container={CONTAINER_COLORS[(i + ri) % CONTAINER_COLORS.length]} />
          </group>
        );
      })}
    </group>
  );
}

/** Road from a home-island pier to the plant's container yard on the same side (keeps clear of the airfield). */
const pierRoadEnd = (pier) => add(HUB_POS, [Math.sign(pier[0] || 1) * 6.6, 0.4]);

export function World({ data, disruption, selected, setSelected }) {
  const [hover, setHover] = useState(null);
  const world = useMemo(() => layoutWorld(data.suppliers), [data]);
  const traffic = useMemo(() => buildTraffic(world), [world]);
  const { hit, byRegion } = regionStatus(world, disruption);
  const hubBlocked = useMemo(() => (p, m) => (
    (Math.abs(p[0] - HUB_POS[0]) < 7.0 + m && Math.abs(p[1] - HUB_POS[1] - 0.3) < 3.5 + m)
    || inAirport(HUB_AIRPORT, p, m * 0.6)
    || world.regions.some((r) => distToSeg(p, r.pier, pierRoadEnd(r.pier)) < 0.7 + m
      || Math.hypot(p[0] - r.pier[0], p[1] - r.pier[1]) < 2.2 + m)
  ), [world]);
  const lanes = useMemo(() => world.regions.map((r, i) => {
    const tl = traffic.air.fleet[i].timeline;
    const t0 = tl.events.outAirStart; const t1 = tl.events.outTD;
    const s = {};
    const air = Array.from({ length: 70 }, (_, k) => { sampleAt(tl, t0 + ((t1 - t0) * k) / 69, s); return [s.x, s.y, s.z]; });
    const sea = traffic.ships[i].outbound.map(([x, z]) => [x, SEA_Y + 0.12, z]);
    return { air, sea };
  }), [world, traffic]);
  return (
    <>
      <Ocean />
      <Clouds />
      <Island c={[0, 0]} R={HUB_R} seed={HUB_SEED} tint="#a3cf81" />
      <Scenery c={[0, 0]} R={HUB_R} seed={HUB_SEED} blocked={hubBlocked} count={36} />

      {/* home island: plant, airport, piers, forklifts */}
      <Hub />
      <Airport ap={HUB_AIRPORT} terminal={false} />
      <Html zIndexRange={[10, 0]} position={[0, 0.1, HUB_AIRPORT.a[1] + 2.0]} center style={{ pointerEvents: 'none' }}>
        <div className="ct-tag">Air cargo hub · runway 09</div>
      </Html>
      <Forklift a={[2.4, -0.2]} b={[4.9, -0.2]} phase={0} />
      <Forklift a={[-2.6, 0.0]} b={[-5.0, 0.0]} phase={1.7} />

      {world.regions.map((r, ri) => {
        const st = byRegion[r.region];
        const flight = traffic.air.fleet[ri];
        return (
          <group key={r.region}>
            <RegionIsland r={r} ri={ri} st={st} hover={hover} setHover={setHover} selected={selected} setSelected={setSelected} hit={hit} />
            <Pier at={r.pier} u={r.u} />
            <Road from={r.pier} to={pierRoadEnd(r.pier)} active={st.sea} />
            <Truck from={add(r.pier, mul(r.u, -0.4))} to={pierRoadEnd(r.pier)}
              halted={st.sea} phase={ri * 0.27} period={20} container={CONTAINER_COLORS[(ri * 2) % CONTAINER_COLORS.length]} />
            {/* sea lane + container ship */}
            <Line points={lanes[ri].sea} color={st.sea ? '#ef4444' : '#e0f2fe'} lineWidth={1.4} dashed dashSize={0.7} gapSize={0.5}
              transparent opacity={st.sea ? 0.9 : 0.55} />
            <Ship tl={traffic.ships[ri]} halted={st.sea} phase={ri * 9.7} seed={ri} />
            {/* air route (outbound track) + freighter */}
            <Line points={lanes[ri].air} color={st.air ? '#ef4444' : '#7dd3fc'} lineWidth={1} dashed dashSize={0.45} gapSize={0.55}
              transparent opacity={st.air ? 0.85 : 0.35} />
            <Aircraft timeline={flight.timeline} offset={flight.offset} grounded={st.air} />
          </group>
        );
      })}
    </>
  );
}

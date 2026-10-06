/* Boeing 747-400F-proportioned freighter (generic livery) + airport rendering.
 * Model units: 1 unit ~= 17.6 m, so length 4.0 (70.6 m), span 3.66 (64.4 m), height 1.1 (19.4 m).
 * Nose = +x, right wing = +z, up = +y. Fuselage centre sits at the origin. */
import React, { useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { STAND_OFF, TAXI_OFF } from './paths.js';

export const PLANE_SCALE = 0.6;
const FUS_R = 0.185;

const FUSELAGE = new THREE.LatheGeometry([
  [0, -2.0], [0.035, -1.98], [0.07, -1.9], [0.11, -1.72], [0.15, -1.45], [0.175, -1.15], [FUS_R, -0.85],
  [FUS_R, 1.4], [0.18, 1.6], [0.165, 1.74], [0.14, 1.85], [0.105, 1.93], [0.06, 1.98], [0, 2.0],
].map(([r, y]) => new THREE.Vector2(r, y)), 24);

/** Flat surface from a planform given as [x, z] points (shape y = -z so it lies flat after rotating -90 deg about x). */
function planform(pts, depth) {
  const s = new THREE.Shape();
  pts.forEach(([x, z], i) => (i ? s.lineTo(x, -z) : s.moveTo(x, -z)));
  return new THREE.ExtrudeGeometry(s, { depth, bevelEnabled: false });
}
const mirror = (pts) => pts.map(([x, z]) => [x, -z]);
/** Vertical surface from [x, y] profile points. */
function profile(pts, depth) {
  const s = new THREE.Shape();
  pts.forEach(([x, y], i) => (i ? s.lineTo(x, y) : s.moveTo(x, y)));
  return new THREE.ExtrudeGeometry(s, { depth, bevelEnabled: false });
}

// 37.5 deg swept wing with trailing-edge kink, root chord ~1.0, tip chord ~0.2
const WING_PTS = [[0.62, 0.16], [-0.82, 1.83], [-1.02, 1.83], [-0.6, 0.62], [-0.38, 0.16]];
const WING_R = planform(WING_PTS, 0.035);
const WING_L = planform(mirror(WING_PTS), 0.035);
const STAB_PTS = [[-1.42, 0.05], [-1.86, 0.66], [-1.98, 0.66], [-1.86, 0.05]];
const STAB_R = planform(STAB_PTS, 0.022);
const STAB_L = planform(mirror(STAB_PTS), 0.022);
const FIN = profile([[-1.18, 0.16], [-1.78, 0.98], [-1.96, 0.98], [-1.97, 0.12]], 0.035);
const WINGLET = profile([[-0.82, 0], [-0.97, 0.17], [-1.05, 0.17], [-1.02, 0]], 0.014);

const DIHEDRAL = 0.12; // ~7 deg
const WING_Y = -0.09;  // low wing
const xLE = (z) => 0.62 - ((z - 0.16) / 1.67) * 1.44;
const wingY = (z) => WING_Y + Math.abs(z) * Math.tan(DIHEDRAL);
const ENGINES = [0.66, 1.14, -0.66, -1.14].map((z) => ({ z, x: xLE(Math.abs(z)) + 0.07, y: wingY(z) - 0.11 }));

const WHITE = '#f8fafc';
const GREY = '#dfe4ea';

function Blink({ position, color, rate = 1.2, offset = 0, size = 0.035 }) {
  const ref = useRef();
  useFrame(({ clock }) => { if (ref.current) ref.current.visible = ((clock.elapsedTime + offset) * rate) % 1 < 0.14; });
  return <mesh ref={ref} position={position}><sphereGeometry args={[size, 6, 6]} /><meshBasicMaterial color={color} /></mesh>;
}

function Bogie({ x, z, wheels = 4 }) {
  const pts = wheels === 2 ? [[0, -0.035], [0, 0.035]] : [[-0.05, -0.04], [-0.05, 0.04], [0.05, -0.04], [0.05, 0.04]];
  return (
    <group position={[x, 0, z]}>
      <mesh position={[0, -0.23, 0]}><boxGeometry args={[0.02, 0.13, 0.02]} /><meshStandardMaterial color="#94a3b8" /></mesh>
      {pts.map(([dx, dz]) => (
        <mesh key={`${dx}${dz}`} position={[dx, -0.297, dz]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.045, 0.045, 0.03, 10]} /><meshStandardMaterial color="#111827" />
        </mesh>
      ))}
    </group>
  );
}

/** Generic 747-400F silhouette: upper-deck hump, 4 underwing engines, winglets, 18-wheel gear. */
export function B747({ grounded, gearRef, accent = '#1d4ed8' }) {
  const tail = grounded ? '#dc2626' : accent;
  return (
    <group scale={PLANE_SCALE}>
      <mesh geometry={FUSELAGE} rotation={[0, 0, -Math.PI / 2]} castShadow><meshStandardMaterial color={WHITE} roughness={0.35} /></mesh>
      {/* upper deck hump, flight-deck windows, cheatline, grey belly */}
      <mesh position={[1.3, 0.1, 0]} scale={[0.68, 0.16, 0.15]} castShadow><sphereGeometry args={[1, 24, 14]} /><meshStandardMaterial color={WHITE} roughness={0.35} /></mesh>
      <mesh position={[1.87, 0.165, 0]} rotation={[0, 0, -0.55]}><boxGeometry args={[0.07, 0.03, 0.17]} /><meshStandardMaterial color="#0f172a" roughness={0.2} /></mesh>
      {[1, -1].map((s) => (
        <mesh key={s} position={[0.25, 0.04, s * (FUS_R - 0.002)]}><boxGeometry args={[3.0, 0.03, 0.01]} /><meshStandardMaterial color={accent} /></mesh>
      ))}
      <mesh position={[0.2, -0.1, 0]} scale={[1.65, 0.1, 0.16]}><sphereGeometry args={[1, 18, 10]} /><meshStandardMaterial color="#cbd5e1" /></mesh>
      {/* wings with dihedral + winglets */}
      <group position={[0, WING_Y, 0]} rotation={[-DIHEDRAL, 0, 0]}>
        <mesh geometry={WING_R} rotation={[-Math.PI / 2, 0, 0]} castShadow><meshStandardMaterial color={GREY} roughness={0.5} /></mesh>
        <mesh geometry={WINGLET} position={[0, 0.03, 1.83]} rotation={[-0.35, 0, 0]} castShadow><meshStandardMaterial color={tail} /></mesh>
      </group>
      <group position={[0, WING_Y, 0]} rotation={[DIHEDRAL, 0, 0]}>
        <mesh geometry={WING_L} rotation={[-Math.PI / 2, 0, 0]} castShadow><meshStandardMaterial color={GREY} roughness={0.5} /></mesh>
        <mesh geometry={WINGLET} position={[0, 0.03, -1.83 - 0.014]} rotation={[0.35, 0, 0]} castShadow><meshStandardMaterial color={tail} /></mesh>
      </group>
      {/* tailplane + fin */}
      <group position={[0, 0.04, 0]} rotation={[-DIHEDRAL, 0, 0]}>
        <mesh geometry={STAB_R} rotation={[-Math.PI / 2, 0, 0]} castShadow><meshStandardMaterial color={GREY} /></mesh>
      </group>
      <group position={[0, 0.04, 0]} rotation={[DIHEDRAL, 0, 0]}>
        <mesh geometry={STAB_L} rotation={[-Math.PI / 2, 0, 0]} castShadow><meshStandardMaterial color={GREY} /></mesh>
      </group>
      <mesh geometry={FIN} position={[0, 0, -0.0175]} castShadow><meshStandardMaterial color={tail} /></mesh>
      {/* four high-bypass engines on pylons */}
      {ENGINES.map((e) => (
        <group key={e.z} position={[e.x, e.y, e.z]}>
          <mesh rotation={[0, 0, Math.PI / 2]} castShadow><cylinderGeometry args={[0.072, 0.06, 0.32, 18]} /><meshStandardMaterial color="#e5e7eb" metalness={0.25} roughness={0.35} /></mesh>
          <mesh position={[0.161, 0, 0]} rotation={[0, 0, Math.PI / 2]}><cylinderGeometry args={[0.062, 0.062, 0.006, 18]} /><meshStandardMaterial color="#1f2937" /></mesh>
          <mesh position={[-0.2, 0, 0]} rotation={[0, 0, Math.PI / 2]}><coneGeometry args={[0.045, 0.09, 12]} /><meshStandardMaterial color="#64748b" /></mesh>
          <mesh position={[-0.06, 0.08, 0]}><boxGeometry args={[0.26, 0.07, 0.016]} /><meshStandardMaterial color={GREY} /></mesh>
        </group>
      ))}
      {/* landing gear: nose + 2 body + 2 wing bogies */}
      <group ref={gearRef}>
        <Bogie x={1.55} z={0} wheels={2} />
        <Bogie x={-0.3} z={0.13} /><Bogie x={-0.3} z={-0.13} />
        <Bogie x={-0.05} z={0.37} /><Bogie x={-0.05} z={-0.37} />
      </group>
      {/* navigation lights: red left, green right, white tail; red beacons; white strobes */}
      <mesh position={[-0.9, wingY(1.83) + 0.01, 1.84]}><sphereGeometry args={[0.025, 6, 6]} /><meshBasicMaterial color="#22c55e" /></mesh>
      <mesh position={[-0.9, wingY(1.83) + 0.01, -1.84]}><sphereGeometry args={[0.025, 6, 6]} /><meshBasicMaterial color="#ef4444" /></mesh>
      <Blink position={[0.1, 0.27, 0]} color="#ef4444" rate={1.1} />
      <Blink position={[0.1, -0.2, 0]} color="#ef4444" rate={1.1} offset={0.5} />
      <Blink position={[-1.0, wingY(1.83), 1.86]} color="#ffffff" rate={0.9} offset={0.2} />
      <Blink position={[-1.0, wingY(1.83), -1.86]} color="#ffffff" rate={0.9} offset={0.2} />
      <Blink position={[-2.0, 0.05, 0]} color="#ffffff" rate={0.9} offset={0.6} />
    </group>
  );
}

// ------------------------------------------------------------------ airport
const strip = (x0, x1, z, w, y, color, key) => (
  <mesh key={key} position={[(x0 + x1) / 2, y, z]} receiveShadow>
    <boxGeometry args={[Math.abs(x1 - x0), 0.02, w]} /><meshStandardMaterial color={color} roughness={0.9} />
  </mesh>
);

/** Runway (in-use direction a -> b), parallel taxiway, connectors, apron with stands, terminal, tower. */
export function Airport({ ap, terminal = true, label }) {
  const ang = Math.atan2(ap.d[1], ap.d[0]);
  const side = Math.sign(ap.n[0] * -ap.d[1] + ap.n[1] * ap.d[0]) || 1; // local +z is n * side
  const Z = (off) => off * side;
  const L = ap.L;
  const W = 1.2;
  const standXs = ap.stands.map((s) => s.s);
  const apronX0 = Math.min(...standXs) - 1.6; const apronX1 = Math.max(...standXs) + 1.6;
  const exitX = ap.exitS + 0.3;
  return (
    <group position={[ap.a[0], 0.03, ap.a[1]]} rotation={[0, -ang, 0]}>
      {/* grass strip, runway, markings */}
      {strip(-1.6, L + 1.6, 0, W + 1.0, -0.012, '#c3d5b0', 'shoulder')}
      {strip(-1.2, L + 1.2, 0, W, 0, '#2f343b', 'rwy')}
      {Array.from({ length: Math.floor((L - 1.4) / 0.7) }).map((_, i) => strip(0.9 + i * 0.7, 1.2 + i * 0.7, 0, 0.05, 0.012, '#f8fafc', `cl${i}`))}
      {[-0.42, -0.28, -0.14, 0.14, 0.28, 0.42].map((z) => strip(0.05, 0.55, z * W * 1.4, 0.06, 0.012, '#f8fafc', `th${z}`))}
      {[-0.42, -0.28, -0.14, 0.14, 0.28, 0.42].map((z) => strip(L - 0.55, L - 0.05, z * W * 1.4, 0.06, 0.012, '#f8fafc', `tb${z}`))}
      {[-0.3, 0.3].map((z) => strip(ap.tdS - 0.2, ap.tdS + 0.35, z * W, 0.12, 0.012, '#f8fafc', `tdz${z}`))}
      {/* taxiway system */}
      {strip(ap.connA - 0.3, exitX + 0.3, Z(TAXI_OFF), 0.6, 0.002, '#4b5563', 'twy')}
      {strip(ap.connA - 0.3, exitX + 0.3, Z(TAXI_OFF), 0.035, 0.014, '#facc15', 'twycl')}
      {[ap.connA, exitX].map((x) => (
        <mesh key={`c${x}`} position={[x, 0.002, Z(TAXI_OFF / 2)]} receiveShadow>
          <boxGeometry args={[0.6, 0.02, TAXI_OFF]} /><meshStandardMaterial color="#4b5563" />
        </mesh>
      ))}
      {/* apron + stands with lead-in lines and stop bars */}
      <mesh position={[(apronX0 + apronX1) / 2, -0.001, Z((TAXI_OFF + 0.3 + STAND_OFF + 1.6) / 2)]} receiveShadow>
        <boxGeometry args={[apronX1 - apronX0, 0.02, STAND_OFF + 1.6 - TAXI_OFF - 0.3]} /><meshStandardMaterial color="#c8cdd4" />
      </mesh>
      {standXs.map((x) => (
        <group key={`st${x}`}>
          <mesh position={[x, 0.014, Z((TAXI_OFF + STAND_OFF + 0.9) / 2)]}><boxGeometry args={[0.035, 0.01, STAND_OFF + 0.9 - TAXI_OFF]} /><meshStandardMaterial color="#facc15" /></mesh>
          <mesh position={[x, 0.014, Z(STAND_OFF + 1.25)]}><boxGeometry args={[0.5, 0.01, 0.05]} /><meshStandardMaterial color="#facc15" /></mesh>
        </group>
      ))}
      {/* approach lighting beyond the in-use threshold */}
      {[1.5, 1.85, 2.2].map((dx) => [-0.25, 0, 0.25].map((z) => (
        <mesh key={`al${dx}${z}`} position={[-dx, 0.03, z]}><sphereGeometry args={[0.035, 6, 6]} /><meshBasicMaterial color="#fde68a" /></mesh>
      )))}
      {/* control tower */}
      <group position={[apronX1 + 0.9, 0, Z(STAND_OFF + 1.2)]}>
        <mesh position={[0, 0.9, 0]} castShadow><cylinderGeometry args={[0.16, 0.22, 1.8, 10]} /><meshStandardMaterial color="#e5e7eb" /></mesh>
        <mesh position={[0, 1.95, 0]} castShadow><cylinderGeometry args={[0.36, 0.28, 0.3, 10]} /><meshStandardMaterial color="#1e3a5f" metalness={0.4} roughness={0.2} /></mesh>
        <mesh position={[0, 2.18, 0]}><cylinderGeometry args={[0.38, 0.38, 0.05, 10]} /><meshStandardMaterial color="#f1f5f9" /></mesh>
      </group>
      {/* cargo terminal */}
      {terminal && (
        <group position={[(apronX0 + apronX1) / 2, 0, Z(STAND_OFF + 2.2)]}>
          <mesh position={[0, 0.4, 0]} castShadow receiveShadow><boxGeometry args={[apronX1 - apronX0 - 0.4, 0.8, 0.9]} /><meshStandardMaterial color="#e2e8f0" /></mesh>
          <mesh position={[0, 0.82, 0]}><boxGeometry args={[apronX1 - apronX0 - 0.3, 0.06, 1.0]} /><meshStandardMaterial color="#1d4ed8" /></mesh>
        </group>
      )}
      {/* windsock */}
      <group position={[L + 1.4, 0, Z(-1.3)]}>
        <mesh position={[0, 0.35, 0]}><cylinderGeometry args={[0.015, 0.015, 0.7, 6]} /><meshStandardMaterial color="#94a3b8" /></mesh>
        <mesh position={[-0.14, 0.68, 0]} rotation={[0, 0, Math.PI / 2]}><coneGeometry args={[0.05, 0.25, 8]} /><meshStandardMaterial color="#f97316" /></mesh>
      </group>
      {label}
    </group>
  );
}

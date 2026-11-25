// The surgical drape: one sheet of cloth laid over the patient's shape on the OR table,
// tented between the body and the table's edges, falling over both long sides in
// folds. A height field over the table top, bent down past the edges. Since 2026-11-22
// (the owner: the face uncovered, the legs apart) the sheet runs from the shoulders,
// under the anaesthesia screen, to the hips; the legs have their own leggings.

import * as THREE from 'three';

const smooth = (a, b, x) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

// the body's height under the sheet at (x, z) from the table's centre line and centre:
// the torso, the shoulders and the two thighs where they leave the hips, soft-edged
// (exported: the ports sit on it)
export const HIP_X = 0.5, THIGH_Z = 0.115;
export function body(x, z) {
  const lobe = (cx, cz, len, w, h) => {
    const u = (x - cx) / len, v = (z - cz) / w;
    const d = u * u * u * u + v * v;
    return d < 1 ? h * Math.sqrt(1 - d) : 0;
  };
  return Math.max(lobe(0.05, 0, 0.52, 0.25, 0.22), lobe(-0.49, 0, 0.17, 0.23, 0.15),
    lobe(HIP_X + 0.06, THIGH_Z, 0.16, 0.085, 0.15), lobe(HIP_X + 0.06, -THIGH_Z, 0.16, 0.085, 0.15));
}

// The sheet spans x0 to x0 + length along the table (table coordinates); place it at the
// table's centre plus `centre` (returned on the mesh's userData). Past `tableEnd` the
// table gives way at the head end, and the sheet rests on it before that.
export function drape({ x0 = -1.15, length = 2.3, width = 1.5, edge = 0.27, hang = 0.62, material }) {
  const cx = x0 + length / 2;
  const g = new THREE.PlaneGeometry(length, width, 180, 120);
  // creases: ridged sines at a few seeded angles and lengths (10 to 25 cm), a few
  // millimetres high on the table and deeper where the sheet hangs
  let seed = 97;
  const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
  const ridges = Array.from({ length: 9 }, () => ({ a: rnd() * Math.PI, f: 25 + rnd() * 35, ph: rnd() * 6.28, amp: 0.4 + rnd() * 0.6 }));
  const crease = (x, z) => ridges.reduce((w, r) => w + r.amp * (1 - Math.abs(Math.sin((Math.cos(r.a) * x + Math.sin(r.a) * z) * r.f + r.ph))) ** 3, 0) / ridges.length - 0.08;
  g.rotateX(-Math.PI / 2);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i) + cx;
    const z = p.getZ(i);
    const az = Math.abs(z);
    const folds = Math.sin(x * 9.5 + Math.sin(x * 3.1) * 1.4) * 0.5 + Math.sin(x * 23 + z * 4) * 0.2;
    if (az <= edge) {
      // on the table: the body, and the sheet tented down toward the edges
      const h = body(x, z);
      const tent = 0.035 * (1 - smooth(edge * 0.55, edge, az));
      p.setY(i, Math.max(h, tent) + 0.012 + folds * 0.003 + crease(x, z) * 0.012);
    } else {
      // past the edge: the sheet falls, swinging out a little, folding as it goes
      const t = Math.min(1, (az - edge) / (width / 2 - edge));
      const drop = t * hang;
      const out = Math.sin(t * Math.PI * 0.5) * 0.05 + folds * 0.022 * t + crease(x, z) * 0.03 * t;
      p.setZ(i, Math.sign(z) * (edge + 0.015 + out));
      p.setY(i, 0.012 - drop + folds * 0.01 * t);
    }
    // the sheet ends at the shoulders, resting on the table, and past the hips, falling
    // between the legs
    const head = x0 + 0.05 - x, foot = x - (x0 + length - 0.12);
    if (head > 0) p.setY(i, Math.max(p.getY(i) - head * 1.4, az <= edge ? 0.006 : -Infinity));
    if (foot > 0) p.setY(i, p.getY(i) - foot * 2.2);
  }
  g.computeVertexNormals();
  const mesh = new THREE.Mesh(g, material);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.userData.centre = cx;
  return mesh;
}

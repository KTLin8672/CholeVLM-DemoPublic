// The anaesthesia screen's curtain (the owner, 2026-11-22: "the divider should be a
// linen-like curtain"): a linen cloth hung from the arched bar over the patient's upper
// chest, falling onto the patient and past the table's sides, in soft gathered folds.
// The folds come from a tangent angle integrated across
// the cloth's width, so arc length equals the rest coordinate and the weave never
// stretches across; uv is the cloth's own metres, so the weave keeps its scale.
//
// Local frame: the arch's centre at the origin, the cloth in the y-z plane (z across the
// table), the folds swinging along x. `top(z)` is the bar's height over z, `bottom(z)`
// where the hem comes to rest.

import * as THREE from 'three';

const smooth = (a, b, x) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

export function curtain({ span, top, bottom, material, wave = 0.11, amp = 0.95, seed = 3 }) {
  // the fold curve: z and x along the rest coordinate s, from the integrated angle
  const curve = (S, n) => {
    const pts = [[0, 0]];
    let z = 0, x = 0;
    const ds = S / n;
    for (let i = 1; i <= n; i++) {
      const s = (i - 0.5) * ds;
      const th = (2 * Math.PI * s) / wave + seed;
      // gathers fade to the hanging edges, so the sides fall flatter
      const env = 0.55 + 0.45 * Math.sin(Math.PI * (s / S));
      const a = Math.max(-1.4, Math.min(1.4, amp * env * (Math.sin(th) + 0.16 * Math.sin(2 * th + 0.8) + 0.22 * Math.sin(0.37 * th + 1.1))));
      z += ds * Math.cos(a);
      x += ds * Math.sin(a);
      pts.push([z, x]);
    }
    return pts;
  };
  // the cloth's rest width chosen so its folded span is the bar's
  const NS = 220, NV = 44;
  let S = span * 1.3, pts = curve(S, NS);
  for (let k = 0; k < 3; k++) {
    S *= span / pts[NS][0];
    pts = curve(S, NS);
  }
  const z0 = span / 2, x0 = pts.reduce((m, p) => m + p[1], 0) / pts.length;
  const pos = new Float32Array((NS + 1) * (NV + 1) * 3);
  const uv = new Float32Array((NS + 1) * (NV + 1) * 2);
  for (let i = 0; i <= NS; i++) {
    const z = pts[i][0] - z0, xf = pts[i][1] - x0;
    const yt = top(z), yb = Math.min(bottom(z), yt - 0.02);
    for (let j = 0; j <= NV; j++) {
      const t = j / NV, v = t * (yt - yb);
      // pinched at the bar, opening as the cloth falls
      const open = 0.3 + 0.7 * smooth(0, 0.12, v);
      const k = i * (NV + 1) + j;
      pos[k * 3] = xf * open;
      pos[k * 3 + 1] = yt - v;
      pos[k * 3 + 2] = z;
      uv[k * 2] = (i / NS) * S;
      uv[k * 2 + 1] = v;
    }
  }
  const index = [];
  for (let i = 0; i < NS; i++) {
    for (let j = 0; j < NV; j++) {
      const a = i * (NV + 1) + j, b = a + NV + 1;
      index.push(a, b, a + 1, b, b + 1, a + 1);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  g.setIndex(index);
  g.computeVertexNormals();
  const mesh = new THREE.Mesh(g, material);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

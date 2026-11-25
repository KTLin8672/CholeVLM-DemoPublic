// Realistic surfaces for the virtual OR (the owner, 2026-11-06: "turn it from
// cartoonish to realistic").
// What made the room read as a toy was one flat colour and one roughness per surface,
// and nothing bright to reflect. Here every surface gets a finish that varies across it,
// drawn once into canvases (no image files, nothing fetched, a seeded generator so every
// render is the same):
// - steel: a true conductor (metalness 1, its F0 as the colour), brushed streaks and
//   smudges in the roughness, a little anisotropy along the grain;
// - painted equipment: an off-white enamel with orange peel in the normal, mottled
//   roughness and a thin clear coat;
// - moulded plastic (the units, the bezels): fine grain, satin;
// - the drapes: nonwoven polypropylene, short random fibres and the embossed dot grid
//   of SMS fabric in the normal, near-matte with a soft sheen;
// - linen: the anaesthesia screen's curtain, a plain weave of spun threads;
// - glass: the dark screens are black glass that mirrors the room.

import * as THREE from 'three';

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

function canvas(size) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  return [c, c.getContext('2d', { willReadFrequently: true })];
}

function texture(c, repeat, srgb = false) {
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(repeat[0], repeat[1]);
  t.anisotropy = 8;
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// a height field (canvas, grey = height) to a tangent-space normal map
function normalsFrom(heightCanvas, strength) {
  const n = heightCanvas.width;
  const src = heightCanvas.getContext('2d').getImageData(0, 0, n, n).data;
  const [c, g] = canvas(n);
  const out = g.createImageData(n, n);
  const h = (x, y) => src[(((y + n) % n) * n + ((x + n) % n)) * 4] / 255;
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const dx = (h(x + 1, y) - h(x - 1, y)) * strength;
      const dy = (h(x, y + 1) - h(x, y - 1)) * strength;
      const len = Math.hypot(dx, dy, 1);
      const i = (y * n + x) * 4;
      out.data[i] = (-dx / len * 0.5 + 0.5) * 255;
      out.data[i + 1] = (dy / len * 0.5 + 0.5) * 255;
      out.data[i + 2] = (1 / len * 0.5 + 0.5) * 255;
      out.data[i + 3] = 255;
    }
  }
  g.putImageData(out, 0, 0);
  return c;
}

// soft blobs at random: smudges, mottling, orange peel
function blobs(g, n, r, count, alpha, light = 0.5) {
  for (let i = 0; i < count; i++) {
    const x = r() * n, y = r() * n, s = 2 + r() * (n / 18);
    const v = r() < light ? 255 : 0;
    const grd = g.createRadialGradient(x, y, 0, x, y, s);
    grd.addColorStop(0, `rgba(${v},${v},${v},${alpha})`);
    grd.addColorStop(1, `rgba(${v},${v},${v},0)`);
    g.fillStyle = grd;
    g.fillRect(x - s, y - s, s * 2, s * 2);
  }
}

// brushed steel: fine streaks along u at two scales, a few wiped smudges
function brushedRoughness() {
  const n = 512, [c, g] = canvas(n), r = rng(41);
  g.fillStyle = 'rgb(170,170,170)';
  g.fillRect(0, 0, n, n);
  for (let i = 0; i < 2200; i++) {
    const v = 120 + r() * 120;
    g.fillStyle = `rgba(${v},${v},${v},${0.25 + r() * 0.35})`;
    g.fillRect(r() * n - 100, r() * n, 60 + r() * 400, r() < 0.8 ? 1 : 2);
  }
  blobs(g, n, r, 40, 0.18, 0.3);
  return texture(c, [1, 1]);
}

// enamel paint: orange peel in the normal, mottled sheen in the roughness
function paintMaps() {
  const n = 256, r = rng(53);
  const [h, gh] = canvas(n);
  gh.fillStyle = '#808080'; gh.fillRect(0, 0, n, n);
  blobs(gh, n, r, 900, 0.22);
  const [ro, gr] = canvas(n);
  gr.fillStyle = 'rgb(200,200,200)'; gr.fillRect(0, 0, n, n);
  blobs(gr, n, r, 120, 0.2);
  return { normalMap: texture(normalsFrom(h, 2.2), [3, 3]), roughnessMap: texture(ro, [2, 2]) };
}

// moulded plastic: a fine spark-eroded grain
function grainMaps() {
  const n = 256, r = rng(61);
  const [h, g] = canvas(n);
  g.fillStyle = '#808080'; g.fillRect(0, 0, n, n);
  for (let i = 0; i < 9000; i++) {
    const v = r() < 0.5 ? 255 : 0;
    g.fillStyle = `rgba(${v},${v},${v},0.18)`;
    g.fillRect(r() * n, r() * n, 1 + r() * 1.5, 1 + r() * 1.5);
  }
  return { normalMap: texture(normalsFrom(h, 1.6), [6, 6]) };
}

// SMS nonwoven: random short fibres over an embossed dot grid (the drape's bonding points)
function nonwovenNormal() {
  const n = 512, [c, g] = canvas(n), r = rng(73);
  g.fillStyle = '#808080'; g.fillRect(0, 0, n, n);
  g.lineCap = 'round';
  for (let i = 0; i < 5200; i++) {
    const x = r() * n, y = r() * n, a = r() * Math.PI, len = 6 + r() * 22;
    const v = r() < 0.6 ? 255 : 0;
    g.strokeStyle = `rgba(${v},${v},${v},${0.08 + r() * 0.1})`;
    g.lineWidth = 0.6 + r() * 0.9;
    g.beginPath();
    g.moveTo(x, y);
    g.quadraticCurveTo(x + Math.cos(a + 0.4) * len * 0.5, y + Math.sin(a + 0.4) * len * 0.5, x + Math.cos(a) * len, y + Math.sin(a) * len);
    g.stroke();
  }
  // the bonding points: a diamond grid of small pressed dots
  const step = 16;
  for (let y = 0; y < n; y += step) {
    for (let x = (y / step) % 2 ? step / 2 : 0; x < n; x += step) {
      const grd = g.createRadialGradient(x, y, 0, x, y, 3.2);
      grd.addColorStop(0, 'rgba(0,0,0,0.45)');
      grd.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = grd;
      g.fillRect(x - 4, y - 4, 8, 8);
    }
  }
  return texture(normalsFrom(c, 3.0), [14, 9]);
}

// linen, a plain weave: 32 threads a tile, each
// its own width, tone and an occasional slub; over and under blended across the cell
// borders, a twist along each spun thread; a tone map from the thread on top, darker in
// the gaps. One tile is 32 threads of 2.4 mm, so a uv in metres repeats it 13 times a metre.
export const LINEN_TILE_M = 32 * 0.0024;
function linenMaps() {
  const n = 512, NT = 32, cell = n / NT, r = rng(89);
  const thread = () => ({ w: 0.8 + r() * 0.17, tone: r(), at: r(), slub: r() < 0.3 ? r() * 0.34 : 0, ph: r() * 6.28 });
  const warp = Array.from({ length: NT }, thread), weft = Array.from({ length: NT }, thread);
  const ss = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  const wrap = (d) => d - Math.round(d);
  const [hc, hg] = canvas(n), [cc, cg] = canvas(n);
  const H = hg.createImageData(n, n), C = cg.createImageData(n, n);
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const A = Math.floor(x / cell), B = Math.floor(y / cell);
      const fx = (x / cell) % 1 - 0.5, fy = (y / cell) % 1 - 0.5;
      const wa = warp[A], we = weft[B];
      const over = (A + B) & 1;
      // each thread's half-width, thickened along its length at its slub
      const hwA = 0.5 * wa.w + 0.5 * wa.slub * Math.exp(-(wrap(y / n - wa.at) ** 2) / 0.002);
      const hwB = 0.5 * we.w + 0.5 * we.slub * Math.exp(-(wrap(x / n - we.at) ** 2) / 0.002);
      const pa = Math.max(0, 1 - (fx / hwA) ** 2), pb = Math.max(0, 1 - (fy / hwB) ** 2);
      const sa = ss(0.05, 0.5, Math.abs(fy)), sb = ss(0.05, 0.5, Math.abs(fx));
      const twA = 0.22 * 0.12 * Math.sin(2 * Math.PI * (5 * (y / cell) + 1.3 * fx) + wa.ph);
      const twB = 0.22 * 0.12 * Math.sin(2 * Math.PI * (5 * (x / cell) + 1.3 * fy) + we.ph);
      const hA = Math.sqrt(pa) * (over ? 1 - 0.5 * sa : 0.5 * sa) + (pa > 0 ? twA : 0);
      const hB = Math.sqrt(pb) * (over ? 0.5 * sb : 1 - 0.5 * sb) + (pb > 0 ? twB : 0);
      const top = hA >= hB ? wa : we;
      const h = Math.max(0, hA, hB);
      const i = (y * n + x) * 4;
      const hv = Math.min(255, h * 230);
      H.data[i] = H.data[i + 1] = H.data[i + 2] = hv; H.data[i + 3] = 255;
      const tone = (0.86 + 0.28 * top.tone) * (0.55 + 0.45 * ss(0.05, 0.85, h));
      const cv = Math.min(255, tone * 0.88 * 255);
      C.data[i] = C.data[i + 1] = C.data[i + 2] = cv; C.data[i + 3] = 255;
    }
  }
  hg.putImageData(H, 0, 0);
  cg.putImageData(C, 0, 0);
  const rep = [1 / LINEN_TILE_M, 1 / LINEN_TILE_M];
  return { normalMap: texture(normalsFrom(hc, 2.6), rep), map: texture(cc, rep, true) };
}

// the patient drape's printed zones, as a colour map over its whole sheet (u along the
// table, v across it): the reinforced, absorbent panel around the fenestration, a
// little darker, its stitched border, and the tape line of the adhesive incise film.
// `at` is the fenestration's centre in uv; sizes in uv.
export function drapeZones(at, size) {
  const n = 1024, [c, g] = canvas(n);
  g.fillStyle = '#ffffff';
  g.fillRect(0, 0, n, n);
  const cx = at[0] * n, cy = (1 - at[1]) * n, w = size[0] * n, h = size[1] * n;
  g.fillStyle = '#d4dad8';
  g.beginPath(); g.roundRect(cx - w / 2, cy - h / 2, w, h, 18); g.fill();
  g.setLineDash([5, 4]);
  g.strokeStyle = 'rgba(255,255,255,0.55)';
  g.lineWidth = 2;
  g.beginPath(); g.roundRect(cx - w / 2 + 7, cy - h / 2 + 7, w - 14, h - 14, 14); g.stroke();
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

// steel's F0, linear
const STEEL_F0 = new THREE.Color().setRGB(0.56, 0.57, 0.58, THREE.LinearSRGBColorSpace);

export function surfaces(colors) {
  const brushed = brushedRoughness();
  const paint = paintMaps();
  const grain = grainMaps();
  const nonwoven = nonwovenNormal();
  const linen = linenMaps();
  // the sheen from the dye itself (a lightened sheen colour turns the cloth milky)
  const drapeSheen = (hex) => new THREE.Color(hex).multiplyScalar(0.62);

  return {
    steel: new THREE.MeshPhysicalMaterial({
      color: STEEL_F0, metalness: 1, roughness: 0.42, roughnessMap: brushed, anisotropy: 0.55,
    }),
    // painted equipment: enamel with orange peel and a thin clear coat
    paint: (color) => new THREE.MeshPhysicalMaterial({
      color, roughness: 0.5, roughnessMap: paint.roughnessMap, normalMap: paint.normalMap,
      normalScale: new THREE.Vector2(0.12, 0.12), clearcoat: 0.45, clearcoatRoughness: 0.32,
    }),
    // moulded plastic housings, satin
    plastic: (color, roughness = 0.42) => new THREE.MeshPhysicalMaterial({
      color, roughness, metalness: 0, normalMap: grain.normalMap, normalScale: new THREE.Vector2(0.18, 0.18),
      clearcoat: 0.12, clearcoatRoughness: 0.5,
    }),
    // the drapes: near-matte nonwoven, a soft sheen at grazing angles
    drape: (color, extra = {}) => new THREE.MeshPhysicalMaterial({
      color, roughness: 0.92, normalMap: nonwoven, normalScale: new THREE.Vector2(0.6, 0.6),
      sheen: 0.45, sheenRoughness: 0.75, sheenColor: drapeSheen(color), ...extra,
    }),
    // linen (the anaesthesia screen's curtain): a plain weave, matte, a soft sheen
    linen: (color, extra = {}) => new THREE.MeshPhysicalMaterial({
      color, map: linen.map, roughness: 0.9, normalMap: linen.normalMap, normalScale: new THREE.Vector2(1.15, 1.15),
      sheen: 0.55, sheenRoughness: 0.55, sheenColor: drapeSheen(color), side: THREE.DoubleSide, ...extra,
    }),
    // a dark screen: black glass that mirrors the room
    glass: () => new THREE.MeshPhysicalMaterial({
      color: '#030807', roughness: 0.05, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.04, ior: 1.52,
    }),
    // the sheet-vinyl floor: polished, with the room's lights in it
    floor: (map) => new THREE.MeshPhysicalMaterial({
      color: '#ffffff', map, roughness: 0.34, roughnessMap: paint.roughnessMap, clearcoat: 0.55, clearcoatRoughness: 0.18,
    }),
    // painted wall panels: matte, the paint's own texture
    // semi-gloss wall paint: the canopy's light grades across it
    wall: (map) => new THREE.MeshStandardMaterial({
      color: '#ffffff', map, roughness: 0.6, normalMap: paint.normalMap, normalScale: new THREE.Vector2(0.06, 0.06),
    }),
    colors,
  };
}

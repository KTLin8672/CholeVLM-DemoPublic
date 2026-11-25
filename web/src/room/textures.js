// Procedural surfaces for the virtual OR, drawn once into canvases: no image files,
// nothing fetched. A vinyl floor with seams and flecks, wall panels with their joints,
// and a woven bump for the drapes. A seeded generator keeps every render the same.

import * as THREE from 'three';

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

function canvas(size) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  return [c, c.getContext('2d')];
}

const tex = (c, repeat, color = true) => {
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(repeat[0], repeat[1]);
  t.anisotropy = 4;
  if (color) t.colorSpace = THREE.SRGBColorSpace;
  return t;
};

// sheet vinyl: a mottled base with fine flecks and a welded seam every sheet width
export function floorTexture(base = '#33433f') {
  const [c, g] = canvas(1024);
  const r = rng(7);
  g.fillStyle = base;
  g.fillRect(0, 0, 1024, 1024);
  for (let i = 0; i < 9000; i++) {
    const v = r();
    g.fillStyle = v < 0.5 ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.07)';
    g.fillRect(r() * 1024, r() * 1024, 1 + r() * 2.5, 1 + r() * 2.5);
  }
  g.fillStyle = 'rgba(0,0,0,0.28)';
  g.fillRect(0, 0, 1024, 3);
  g.fillRect(0, 0, 3, 1024);
  return tex(c, [8, 6]);
}

// wall panels: a joint every panel, a little unevenness in the paint
export function wallTexture(base = '#8a9995') {
  const [c, g] = canvas(512);
  const r = rng(11);
  g.fillStyle = base;
  g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 3000; i++) {
    g.fillStyle = r() < 0.5 ? 'rgba(255,255,255,0.025)' : 'rgba(0,0,0,0.03)';
    g.fillRect(r() * 512, r() * 512, 2 + r() * 6, 2 + r() * 6);
  }
  g.fillStyle = 'rgba(0,0,0,0.22)';
  g.fillRect(0, 0, 2, 512);
  g.fillStyle = 'rgba(255,255,255,0.06)';
  g.fillRect(2, 0, 1, 512);
  return tex(c, [13, 1]);
}

// a woven bump for the drapes: warp and weft with a little irregularity
export function fabricBump() {
  const [c, g] = canvas(256);
  const r = rng(23);
  g.fillStyle = '#808080';
  g.fillRect(0, 0, 256, 256);
  for (let y = 0; y < 256; y += 4) {
    g.fillStyle = `rgba(255,255,255,${0.18 + r() * 0.1})`;
    g.fillRect(0, y, 256, 2);
  }
  for (let x = 0; x < 256; x += 4) {
    g.fillStyle = `rgba(0,0,0,${0.12 + r() * 0.08})`;
    g.fillRect(x, 0, 2, 256);
  }
  for (let i = 0; i < 1500; i++) {
    g.fillStyle = r() < 0.5 ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)';
    g.fillRect(r() * 256, r() * 256, 1 + r() * 3, 1);
  }
  return tex(c, [18, 10], false);
}

// a soft dark disc for the floor under a base or a wheel: contact shadow
let contact;
export function contactShadow() {
  if (!contact) {
    const [c, g] = canvas(128);
    const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    grd.addColorStop(0, 'rgba(0,0,0,0.55)');
    grd.addColorStop(0.5, 'rgba(0,0,0,0.25)');
    grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd;
    g.fillRect(0, 0, 128, 128);
    contact = new THREE.CanvasTexture(c);
  }
  return contact;
}

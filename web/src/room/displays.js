// The background equipment's own screens, each realistic, not a generic black display,
// drawn into canvases
// as each device shows itself in a laparoscopic cholecystectomy: the camera control
// unit, the light source, the insufflator, the electrosurgical generator, the two
// infusion pumps and the anaesthesia machine's ventilator page.
//
// Each shows its settings and its status, never a measurement of the patient: no
// heart rate, no saturation, no pressure curve, no end-tidal CO2. The demo has none of
// those, and the screen invents nothing that could be read as the patient's. The values are the usual defaults for the operation
// (12 mmHg pneumoperitoneum, a 30 W hook, 100 mL/h of saline), the same in every run.
// Colours are the devices' own white, cyan and green; never the screen's red or amber.

import * as THREE from 'three';

const FONT = '"Atkinson Hyperlegible Next", "DejaVu Sans", Arial, sans-serif';
const MONO = '"Atkinson Hyperlegible Mono", "DejaVu Sans Mono", monospace';
const INK = '#eaf4f6', CYAN = '#7fd6e8', GREEN = '#8fe0a8', DIM = '#7d9298', BLUE = '#79b4f2';

function panel(w, h, draw) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const g = c.getContext('2d');
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  const paint = (now = 0) => { draw(g, w, h, now); tex.needsUpdate = true; };
  paint();
  // the faces are self-hosted: draw again once they are in
  document.fonts?.ready.then(() => paint());
  return { tex, paint };
}

const text = (g, s, x, y, size, color, { font = FONT, weight = 600, align = 'left' } = {}) => {
  g.font = `${weight} ${size}px ${font}`;
  g.fillStyle = color;
  g.textAlign = align;
  g.textBaseline = 'alphabetic';
  g.fillText(s, x, y);
};
const bg = (g, w, h, color = '#06121a') => {
  g.fillStyle = color; g.fillRect(0, 0, w, h);
  const grd = g.createLinearGradient(0, 0, 0, h);
  grd.addColorStop(0, 'rgba(255,255,255,0.05)'); grd.addColorStop(1, 'rgba(0,0,0,0.15)');
  g.fillStyle = grd; g.fillRect(0, 0, w, h);
};

// the tower's three units, bottom to top: camera control, light source, insufflator
export const towerScreens = [
  () => panel(512, 196, (g, w, h) => {
    bg(g, w, h);
    text(g, 'CAMERA 1', 24, 46, 30, CYAN);
    text(g, 'PROFILE  LAPAROSCOPY', 24, 92, 26, DIM);
    text(g, '1080p', 24, 166, 64, INK, { font: MONO });
    text(g, 'WB OK', w - 24, 46, 30, GREEN, { align: 'right' });
    text(g, 'ENH 2  ·  AUTO', w - 24, 166, 28, INK, { align: 'right' });
  }),
  () => panel(512, 196, (g, w, h) => {
    bg(g, w, h);
    text(g, 'LED LIGHT', 24, 46, 30, CYAN);
    text(g, 'ON', w - 24, 46, 30, GREEN, { align: 'right' });
    text(g, '80', 24, 160, 86, INK, { font: MONO });
    text(g, '%', 132, 160, 40, DIM);
    for (let i = 0; i < 10; i++) {
      g.fillStyle = i < 8 ? '#cfeef5' : '#203238';
      g.fillRect(200 + i * 29, 104, 22, 56);
    }
  }),
  () => panel(512, 196, (g, w, h) => {
    bg(g, w, h);
    text(g, 'PRESSURE  mmHg', 24, 40, 24, CYAN);
    text(g, 'SET', 24, 160, 26, DIM);
    text(g, '12', 80, 162, 82, INK, { font: MONO });
    g.fillStyle = '#203238'; g.fillRect(256, 20, 2, 156);
    text(g, 'FLOW  L/min', 280, 40, 24, CYAN);
    text(g, 'SET', 280, 160, 26, DIM);
    text(g, '20', 336, 162, 82, INK, { font: MONO });
    text(g, 'INSUFFLATING', w - 18, 190, 18, GREEN, { align: 'right' });
  }),
];

// the electrosurgical generator: the monopolar outputs set, the hook's port lit
export const esuScreen = () => panel(480, 160, (g, w, h) => {
  bg(g, w, h, '#05101a');
  text(g, 'CUT', 22, 38, 24, DIM);
  text(g, 'PURE', 22, 66, 18, DIM);
  text(g, '30', 22, 140, 70, INK, { font: MONO });
  text(g, 'W', 112, 140, 26, DIM);
  g.fillStyle = '#1b2b33'; g.fillRect(238, 14, 2, 132);
  text(g, 'COAG', 258, 38, 24, BLUE);
  text(g, 'SOFT', 258, 66, 18, DIM);
  text(g, '30', 258, 140, 70, INK, { font: MONO });
  text(g, 'W', 348, 140, 26, DIM);
  text(g, 'READY', w - 16, 150, 16, GREEN, { align: 'right' });
});

// the infusion pumps: the solution, the rate, the volume to be infused, and the flow
// arrows that a running pump shows (they step; `paint(now)` moves them)
export const pumpScreen = (solution, rate, vtbi) => panel(400, 200, (g, w, h, now) => {
  bg(g, w, h, '#071318');
  text(g, solution, 18, 38, 26, CYAN);
  text(g, 'RATE', 18, 82, 20, DIM);
  text(g, String(rate), 18, 150, 66, INK, { font: MONO });
  text(g, 'mL/h', 18 + String(rate).length * 40 + 8, 150, 24, DIM);
  text(g, `VTBI ${vtbi} mL`, w - 18, 82, 20, DIM, { align: 'right' });
  const k = Math.floor(now / 600) % 4;
  text(g, ['›  ', '›› ', '›››', '   '][k], w - 18, 150, 44, GREEN, { font: MONO, align: 'right' });
  text(g, 'INFUSING', w - 18, 188, 18, GREEN, { align: 'right' });
});

// the anaesthesia machine: its ventilator's settings page (settings only, no curves)
export const ventilatorScreen = () => panel(720, 520, (g, w, h) => {
  bg(g, w, h, '#0a1014');
  g.fillStyle = '#16232a'; g.fillRect(0, 0, w, 64);
  text(g, 'VCV', 24, 44, 32, INK);
  text(g, 'Adult', 112, 44, 26, DIM);
  text(g, 'Ventilation settings', w - 24, 44, 24, DIM, { align: 'right' });
  const tiles = [['VT', '450', 'mL'], ['RR', '12', '/min'], ['PEEP', '5', 'cmH₂O'], ['FiO₂', '50', '%'], ['I:E', '1:2', ''], ['Sevo', '2.0', '%']];
  tiles.forEach(([k, v, unit], i) => {
    const x = 24 + (i % 3) * 228, y = 92 + Math.floor(i / 3) * 196;
    g.fillStyle = '#111c22'; g.fillRect(x, y, 212, 176);
    g.strokeStyle = '#25363e'; g.lineWidth = 2; g.strokeRect(x + 1, y + 1, 210, 174);
    text(g, k, x + 16, y + 38, 26, CYAN);
    text(g, v, x + 16, y + 124, 72, INK, { font: MONO });
    text(g, unit, x + 196, y + 160, 22, DIM, { align: 'right' });
  });
});

// a screen plane with its picture, lit from within
export function screenMesh(w, h, screen, brightness = 0.85) {
  const m = new THREE.MeshBasicMaterial({ map: screen.tex, color: new THREE.Color(brightness, brightness, brightness) });
  return new THREE.Mesh(new THREE.PlaneGeometry(w, h), m);
}

// The reading's stand-in on phones. There the model's reading is a dashboard of its own under
// the room (style.css), and the reading's monitor shows a generic page in its place:
// the reading's layout as empty placeholders, with no phase, tool, criterion or figure
// on it, since the screen invents nothing. An alert the model raises is real, so the
// page takes the alert's red frame as the reading does. The reading
// is on monitor C, landscape, so this page is too: the rail
// and the stamp across the top, the phase and the tools on the left, safety and the
// next step on the right.
export function standInScreen() {
  let alerting = false;
  const p = panel(880, 550, (g, w, h) => {
    g.fillStyle = '#071a17';
    g.fillRect(0, 0, w, h);
    const bar = (x, y, bw, bh) => { g.fillStyle = '#16312c'; g.fillRect(x, y, bw, bh); };
    const box = (x, y, bw, bh) => { g.lineWidth = 2; g.strokeStyle = '#2f5a52'; g.strokeRect(x + 1, y + 1, bw - 2, bh - 2); };
    const col = (w - 48 - 28) / 2; // two columns, 24 in from each side, 28 apart
    const L = 24, R = 24 + col + 28;
    const rule = (x, y) => { g.fillStyle = '#1d3a35'; g.fillRect(x, y, col, 2); };
    // the phase rail, seven empty steps, and the late stamp's place
    for (let i = 0; i < 7; i++) box(L + i * 39, 16, 36, 38);
    bar(w - 174, 20, 150, 18); bar(w - 134, 46, 110, 12);
    // left: the phase (its name, the confidence track, three rows), then tools in view
    rule(L, 66);
    bar(L, 82, 330, 34); bar(L, 124, 210, 34);
    bar(L, 176, col, 12);
    for (let i = 0; i < 3; i++) { bar(L, 204 + i * 28, 104, 14); bar(L + 124, 204 + i * 28, 170 - i * 30, 14); }
    rule(L, 304);
    bar(L, 320, 140, 16); box(L, 348, 124, 36); box(L + 134, 348, 98, 36); bar(L, 398, 280, 14);
    // right: safety (three empty boxes), then the next step and its rationale
    rule(R, 66);
    bar(R, 82, 96, 16);
    for (let i = 0; i < 3; i++) { box(R, 112 + i * 34, 24, 24); bar(R + 36, 117 + i * 34, 230 - i * 40, 14); }
    bar(R, 224, 180, 30);
    rule(R, 304);
    bar(R, 320, 120, 16); bar(R, 350, 320, 30); bar(R, 398, col - 30, 14); bar(R, 422, 300, 14); bar(R, 446, 240, 14);
    if (alerting) { g.lineWidth = 14; g.strokeStyle = '#ff4b55'; g.strokeRect(7, 7, w - 14, h - 14); }
  });
  return { tex: p.tex, setAlert(on) { if (on !== alerting) { alerting = on; p.paint(); } } };
}

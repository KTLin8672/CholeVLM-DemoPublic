// The instruments the model names, built in 3D and drawn once into pictures for the
// tools page (monitor B in the presenter view; the owner, 2026-11-09: "show visual of
// the next tool ... 3d model (but present 2d on the monitor) and the name underneath
// it"). Each is the working end of a laparoscopic instrument as used in a
// cholecystectomy, its shaft running out of the picture at the lower left, in the
// room's own finishes: an insulated black shaft, steel jaws as a true conductor, a
// titanium clip, a white ceramic insulator on the bipolar forceps.
//
// They are drawn once, ahead of time, not in the visitor's browser: `python -m
// chole_demo bake-instruments` opens `bake.html` on Vite's dev server (loopback), which
// draws each in a small WebGL context of its own under a studio environment, and
// writes the pictures to `web/public/instruments/<name>.webp` (clear background, laid
// on the page's own black-green), which the build ships with the page. On the CPU
// renderer drawing them took 19 s at boot, and nobody's phone should spend its GPU on
// them for every visit (the Frugal Frame Rule).
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const W = 540, H = 720; // px, portrait 3:4: up to 250 page px wide on monitor B, ~400 device px on a phone
const lin = (r, g, b) => new THREE.Color().setRGB(r, g, b, THREE.LinearSRGBColorSpace);

function materials() {
  return {
    // steel as a conductor: its colour is its reflectance, the rest is reflection
    steel: new THREE.MeshPhysicalMaterial({ color: lin(0.56, 0.57, 0.58), metalness: 1, roughness: 0.26 }),
    blade: new THREE.MeshPhysicalMaterial({ color: lin(0.6, 0.61, 0.62), metalness: 1, roughness: 0.16 }),
    titanium: new THREE.MeshPhysicalMaterial({ color: lin(0.62, 0.58, 0.53), metalness: 1, roughness: 0.22 }),
    // the shafts' black insulation, a satin plastic with a thin clear coat
    sheath: new THREE.MeshPhysicalMaterial({ color: '#16191a', roughness: 0.42, clearcoat: 0.5, clearcoatRoughness: 0.35 }),
    ceramic: new THREE.MeshPhysicalMaterial({ color: '#e7e3da', roughness: 0.35, clearcoat: 0.3 }),
    cartridge: new THREE.MeshPhysicalMaterial({ color: '#5d6468', roughness: 0.55 }),
    slot: new THREE.MeshStandardMaterial({ color: '#0b0d0e', roughness: 0.8 }),
    bore: new THREE.MeshStandardMaterial({ color: '#050606', roughness: 0.9, side: THREE.BackSide }),
    bag: new THREE.MeshPhysicalMaterial({ color: '#e9efed', roughness: 0.5, sheen: 0.6, sheenRoughness: 0.5, sheenColor: '#ffffff', transparent: true, opacity: 0.9, side: THREE.DoubleSide }),
    mark: new THREE.MeshStandardMaterial({ color: '#d9dcd8', roughness: 0.5 }),
  };
}

// a rod along +x from x0 to x1 (a cylinder's axis is y: turned onto x)
function rod(r, x0, x1, mat, segs = 32, r1 = r) {
  const g = new THREE.CylinderGeometry(r1, r, x1 - x0, segs, 1);
  g.rotateZ(-Math.PI / 2);
  g.translate((x0 + x1) / 2, 0, 0);
  return new THREE.Mesh(g, mat);
}

// a short pin across the jaws (along z) at x: the hinge's pin or the scissors' screw
function pin(r, len, x, mat) {
  const g = new THREE.CylinderGeometry(r, r, len, 24);
  g.rotateX(Math.PI / 2);
  g.translate(x, 0, 0);
  return new THREE.Mesh(g, mat);
}

// a plan outline (x along the instrument, z across) given as its two edges, extruded
// to `h` and laid so the extrusion is +y (the plate's thickness), from y 0 to h
function plate(left, right, h, mat, holes = []) {
  const s = new THREE.Shape();
  left.forEach(([x, z], i) => (i ? s.lineTo(x, -z) : s.moveTo(x, -z)));
  for (const [x, z] of right.slice().reverse()) s.lineTo(x, -z);
  s.closePath();
  for (const hole of holes) {
    const p = new THREE.Path();
    hole.forEach(([x, z], i) => (i ? p.lineTo(x, -z) : p.moveTo(x, -z)));
    p.closePath();
    s.holes.push(p);
  }
  const bevel = Math.min(0.00025, h * 0.2);
  const g = new THREE.ExtrudeGeometry(s, { depth: h - 2 * bevel, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 3, curveSegments: 12 });
  g.rotateX(-Math.PI / 2); // extrusion → +y, the outline's y → -z (given as -z above: back to +z)
  g.translate(0, bevel, 0);
  g.computeVertexNormals();
  return new THREE.Mesh(g, mat);
}

// an outline from a centre line z = c(x) and a width w(x), x from 0 to L, n steps,
// closed at the tip by a round end of the last width
function outline(L, c, w, n = 28) {
  const left = [], right = [];
  for (let i = 0; i <= n; i++) {
    const x = (L * i) / n;
    left.push([x, c(x) - w(x) / 2]);
    right.push([x, c(x) + w(x) / 2]);
  }
  // a round tip: a half circle from the right edge to the left, round the end
  const r = w(L) / 2;
  const tip = [];
  for (let k = 1; k < 8; k++) {
    const a = Math.PI / 2 - (Math.PI * k) / 8;
    tip.push([L + r * Math.cos(a), c(L) + r * Math.sin(a)]);
  }
  return { left, right: [...right, ...tip] };
}

// a slot, rounded at both ends, from x0 to x1 on centre line c, half-width hw
function slotPath(x0, x1, c, hw, n = 10) {
  const pts = [];
  for (let k = 0; k <= n; k++) { const a = -Math.PI / 2 + (Math.PI * k) / n; pts.push([x1 + hw * Math.cos(a), c + hw * Math.sin(a)]); }
  for (let k = 0; k <= n; k++) { const a = Math.PI / 2 + (Math.PI * k) / n; pts.push([x0 + hw * Math.cos(a), c + hw * Math.sin(a)]); }
  return pts;
}

// a pair of jaws hinged at x = hinge: the upper opened by +open about z, the lower by
// -open, each a plate of thickness h from the given outline; `bend` curves both the
// same way along their length (y += bend·x², curved scissors and Maryland forceps)
function jaws(group, { left, right }, h, open, mat, hinge, holes = [], bend = 0) {
  for (const side of [1, -1]) {
    const pivot = new THREE.Group();
    pivot.position.x = hinge;
    const j = plate(left, right, h, mat, holes);
    if (bend) {
      const pos = j.geometry.attributes.position;
      for (let i = 0; i < pos.count; i++) pos.setY(i, pos.getY(i) + bend * pos.getX(i) ** 2);
      j.geometry.computeVertexNormals();
    }
    j.position.y = side > 0 ? 0.00012 : -h - 0.00012;
    pivot.add(j);
    pivot.rotation.z = side * open;
    group.add(pivot);
  }
}

// a steel tube along +x from x0 to x1 with a hollow, open end (the bore dark)
function tube(r, wall, x0, x1, M) {
  const g = new THREE.Group();
  const outer = new THREE.CylinderGeometry(r, r, x1 - x0, 40, 1, true);
  outer.rotateZ(-Math.PI / 2);
  outer.translate((x0 + x1) / 2, 0, 0);
  g.add(new THREE.Mesh(outer, M.steel));
  const inner = new THREE.CylinderGeometry(r - wall, r - wall, x1 - x0, 40, 1, true);
  inner.rotateZ(-Math.PI / 2);
  inner.translate((x0 + x1) / 2, 0, 0);
  g.add(new THREE.Mesh(inner, M.bore));
  const lip = new THREE.RingGeometry(r - wall, r, 40);
  lip.rotateY(Math.PI / 2);
  lip.translate(x1, 0, 0);
  g.add(new THREE.Mesh(lip, M.steel));
  return g;
}

const SHAFT0 = -0.4; // m: every shaft starts far out of the picture

const BUILD = {
  // an atraumatic fenestrated grasper: two straight jaws, each with a window
  grasper(M) {
    const g = new THREE.Group();
    g.add(rod(0.0026, SHAFT0, -0.0025, M.sheath));
    g.add(rod(0.0026, -0.0025, 0.0022, M.steel));
    const L = 0.019;
    const shape = outline(L, () => 0, (x) => 0.0044 - 0.0008 * (x / L));
    jaws(g, shape, 0.0022, 0.21, M.steel, 0.0016, [slotPath(0.004, L - 0.0035, 0, 0.0009)]);
    g.add(pin(0.0007, 0.0049, 0.0016, M.steel)); // the hinge pin, its heads either side
    g.userData.span = { x: [-0.012, 0.0225], r: 0.0065 };
    return g;
  },
  // a 10 mm clip applier, a titanium clip held open in its jaws
  clipper(M) {
    const g = new THREE.Group();
    g.add(rod(0.005, SHAFT0, -0.004, M.sheath));
    g.add(rod(0.005, -0.004, 0.0015, M.steel, 40, 0.0042));
    const L = 0.021, open = 0.16, hinge = 0.0015;
    jaws(g, outline(L, () => 0, (x) => 0.0048 - 0.0014 * (x / L)), 0.0026, open, M.steel, hinge);
    // the clip: its crown by the hinge, its legs in the jaws' inner faces
    // (in the gap, just inside each jaw's inner face, so it shows between them)
    const y = (x) => Math.max(0.00025, (x - hinge) * Math.tan(open) + 0.00012 - 0.0005);
    const pts = [[0.0195, y(0.0195)], [0.012, y(0.012)], [0.0055, y(0.0055)], [0.0036, 0.0005], [0.0032, 0], [0.0036, -0.0005], [0.0055, -y(0.0055)], [0.012, -y(0.012)], [0.0195, -y(0.0195)]];
    const curve = new THREE.CatmullRomCurve3(pts.map(([x, yy]) => new THREE.Vector3(x, yy, 0)), false, 'centripetal');
    const clip = new THREE.Mesh(new THREE.TubeGeometry(curve, 96, 0.00055, 10), M.titanium);
    clip.scale.z = 2.2; // a clip is a flat wire, wider than it is thick
    g.add(clip);
    g.userData.span = { x: [-0.012, 0.025], r: 0.0075 };
    return g;
  },
  // curved scissors (Metzenbaum): two blades curving to one side, the pivot screw
  scissors(M) {
    const g = new THREE.Group();
    g.add(rod(0.0026, SHAFT0, -0.002, M.sheath));
    g.add(rod(0.0026, -0.002, 0.0026, M.steel));
    const L = 0.017;
    const shape = outline(L, (x) => 0.0036 * (x / L) ** 2, (x) => 0.0042 * (1 - x / L) ** 0.85 + 0.0003, 32);
    jaws(g, shape, 0.0014, 0.15, M.blade, 0.0026, [], 9);
    g.add(pin(0.001, 0.0044, 0.0026, M.steel)); // the pivot screw
    g.userData.span = { x: [-0.012, 0.0206], y: [-0.0045, 0.0075], z: [-0.0058, 0.0058] };
    return g;
  },
  // the monopolar L-hook: the insulation tapers to a bare wire that turns down at its end
  hook(M) {
    const g = new THREE.Group();
    g.add(rod(0.0026, SHAFT0, 0.0, M.sheath));
    g.add(rod(0.0026, 0.0, 0.0045, M.sheath, 32, 0.0011));
    const path = new THREE.CurvePath();
    path.add(new THREE.LineCurve3(new THREE.Vector3(0.004, 0, 0), new THREE.Vector3(0.0135, 0, 0)));
    path.add(new THREE.QuadraticBezierCurve3(new THREE.Vector3(0.0135, 0, 0), new THREE.Vector3(0.0152, 0, 0), new THREE.Vector3(0.0152, -0.0017, 0)));
    path.add(new THREE.LineCurve3(new THREE.Vector3(0.0152, -0.0017, 0), new THREE.Vector3(0.0152, -0.0048, 0)));
    g.add(new THREE.Mesh(new THREE.TubeGeometry(path, 80, 0.00072, 14), M.blade));
    const end = new THREE.Mesh(new THREE.SphereGeometry(0.00072, 14, 10), M.blade);
    end.position.set(0.0152, -0.0048, 0);
    g.add(end);
    g.userData.span = { x: [-0.012, 0.016], r: 0.0055 };
    return g;
  },
  // Maryland bipolar forceps: slender jaws curving to one side, blunt, behind a white
  // ceramic insulator
  bipolar(M) {
    const g = new THREE.Group();
    g.add(rod(0.0026, SHAFT0, -0.003, M.sheath));
    g.add(rod(0.0026, -0.003, 0.0004, M.ceramic));
    g.add(rod(0.0024, 0.0004, 0.0022, M.steel));
    const L = 0.016;
    jaws(g, outline(L, (x) => 0.0042 * (x / L) ** 1.6, (x) => 0.0034 - 0.0016 * (x / L), 32), 0.0018, 0.13, M.steel, 0.0019, [], 12);
    g.userData.span = { x: [-0.012, 0.0196], y: [-0.0045, 0.0078], z: [-0.0058, 0.0058] };
    return g;
  },
  // the suction-irrigation cannula: a steel tube, open at its end, side holes near it
  suction_irrigation(M) {
    const g = new THREE.Group();
    g.add(tube(0.0025, 0.0005, SHAFT0, 0.004, M));
    g.userData.span = { x: [-0.022, 0.0045], r: 0.0042 };
    for (let i = 0; i < 4; i++) {
      for (const a of [0.55, -0.55]) {
        const hole = new THREE.Mesh(new THREE.CircleGeometry(0.00062, 18), M.slot);
        hole.scale.x = 1.35;
        const x = -0.002 - i * 0.0042 - (a > 0 ? 0 : 0.0021);
        hole.position.set(x, 0.00251 * Math.cos(a), 0.00251 * Math.sin(a));
        hole.lookAt(new THREE.Vector3(x, 0.01 * Math.cos(a), 0.01 * Math.sin(a)));
        g.add(hole);
      }
    }
    return g;
  },
  // a specimen retrieval bag: its introducer, a sprung ring, the open pouch on it
  specimen_bag(M) {
    const g = new THREE.Group();
    g.add(rod(0.005, SHAFT0, 0.0, M.ceramic));
    const t = tube(0.005, 0.0006, -0.002, 0.0002, M);
    g.add(t);
    const a = 0.019, b = 0.013, cx = 0.004 + a;
    const rim = (u) => new THREE.Vector3(cx - a * Math.cos(u), 0, b * Math.sin(u));
    // the ring, closed, and the two arms from the introducer to its near end
    const ringCurve = new THREE.CatmullRomCurve3(Array.from({ length: 48 }, (_, i) => rim((2 * Math.PI * i) / 48)), true);
    g.add(new THREE.Mesh(new THREE.TubeGeometry(ringCurve, 160, 0.0006, 10, true), M.steel));
    for (const s of [1, -1]) {
      const arm = new THREE.CatmullRomCurve3([new THREE.Vector3(0, 0, s * 0.0016), new THREE.Vector3(0.0028, 0, s * 0.0028), rim(s * 0.5)]);
      g.add(new THREE.Mesh(new THREE.TubeGeometry(arm, 24, 0.00055, 8), M.steel));
    }
    // the pouch: hung from the ring, narrowing to a rounded bottom, softly creased
    const U = 64, V = 24, depth = 0.034;
    const pos = [];
    const idx = [];
    for (let j = 0; j <= V; j++) {
      const v = j / V;
      const shrink = 1 - 0.78 * v ** 1.6;
      for (let i = 0; i <= U; i++) {
        const u = (2 * Math.PI * i) / U;
        const crease = 1 + 0.05 * v * Math.sin(9 * u + 1.3) + 0.03 * v * Math.sin(17 * u);
        const p = rim(u);
        const x = cx + (p.x - cx) * shrink * crease;
        const z = p.z * shrink * crease;
        pos.push(x, -depth * (Math.sin((v * Math.PI) / 2) ** 0.9), z);
      }
    }
    for (let j = 0; j < V; j++) for (let i = 0; i < U; i++) {
      const k = j * (U + 1) + i;
      idx.push(k, k + U + 1, k + 1, k + 1, k + U + 1, k + U + 2);
    }
    const pg = new THREE.BufferGeometry();
    pg.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    pg.setIndex(idx);
    pg.computeVertexNormals();
    g.add(new THREE.Mesh(pg, M.bag));
    g.userData.span = { x: [-0.01, 0.0435], y: [-0.035, 0.0055], z: [-0.0145, 0.0145] };
    return g;
  },
  // a linear stapler: the steel anvil over the staple cartridge, slightly open
  stapler(M) {
    const g = new THREE.Group();
    g.add(rod(0.006, SHAFT0, -0.004, M.sheath));
    g.add(rod(0.006, -0.004, 0.003, M.steel, 40, 0.0052));
    const L = 0.042, open = 0.17, hinge = 0.003;
    const anvil = new THREE.Group();
    anvil.position.x = hinge;
    const a = plate(...Object.values(outline(L, () => 0, (x) => 0.0085 - 0.002 * (x / L) ** 3)), 0.0032, M.steel);
    a.position.y = 0.0002;
    anvil.add(a);
    anvil.rotation.z = open;
    g.add(anvil);
    const cart = plate(...Object.values(outline(L - 0.004, () => 0, () => 0.0088)), 0.0048, M.cartridge);
    cart.position.set(hinge, -0.0048 - 0.0002, 0);
    g.add(cart);
    // the staple rows either side of the knife's channel, on the cartridge's face
    const face = new THREE.Group();
    face.position.set(hinge, -0.0002 + 0.00003, 0);
    face.add(new THREE.Mesh(new THREE.BoxGeometry(L - 0.008, 0.00006, 0.0005).translate((L - 0.008) / 2 + 0.002, 0, 0), M.slot));
    for (const z of [-0.0034, -0.0024, -0.0014, 0.0014, 0.0024, 0.0034]) {
      for (let k = 0; k < 13; k++) {
        const x = 0.003 + k * 0.0027 + (Math.abs(z) > 0.002 ? 0.0013 : 0);
        if (x > L - 0.007) continue;
        face.add(new THREE.Mesh(new THREE.BoxGeometry(0.0017, 0.00006, 0.00036).translate(x, 0, z), M.slot));
      }
    }
    g.add(face);
    g.userData.span = { x: [-0.014, 0.049], y: [-0.0065, 0.0118], z: [-0.0062, 0.0062] };
    return g;
  },
  // any other instrument: a blunt probe, its centimetre marks on the shaft
  other(M) {
    const g = new THREE.Group();
    g.add(rod(0.0026, SHAFT0, 0.0, M.sheath));
    g.add(rod(0.0016, 0.0, 0.011, M.steel));
    const end = new THREE.Mesh(new THREE.SphereGeometry(0.0016, 20, 12), M.steel);
    end.position.x = 0.011;
    g.add(end);
    for (let k = 1; k <= 3; k++) g.add(rod(0.00262, -0.01 * k - 0.0006, -0.01 * k + 0.0006, M.mark));
    g.userData.span = { x: [-0.033, 0.0128], r: 0.0042 };
    return g;
  },
};
// how each lies in its picture: the tip up and to the right, turned three-quarters to
// the viewer; the bag nearer level, so its pouch hangs
const POSE = {
  default: { pitch: 0.86, yaw: -0.5, roll: 0.55 },
  grasper: { pitch: 0.86, yaw: -0.5, roll: 0.95 }, // more of a jaw's face, so its window shows
  specimen_bag: { pitch: 0.3, yaw: -0.35, roll: 0.25 },
  stapler: { pitch: 0.8, yaw: -0.55, roll: 0.5 },
};

// one instrument's model, by its picture's name (for a check without a GPU)
export const buildInstrument = (name) => BUILD[name]?.(materials()) ?? null;
export const INSTRUMENTS = Object.keys(BUILD);

// Draw every instrument once; resolves to { name: data URL of a WebP } (null where
// WebGL is missing).
export async function instrumentPictures() {
  let renderer;
  try {
    const canvas = document.createElement('canvas');
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, preserveDrawingBuffer: true });
  } catch {
    return null;
  }
  try {
    renderer.setPixelRatio(1);
    renderer.setSize(W, H, false);
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    const pmrem = new THREE.PMREMGenerator(renderer);
    const studio = new RoomEnvironment();
    const env = pmrem.fromScene(studio, 0.03).texture;
    studio.dispose?.();
    const M = materials();
    const out = {};
    for (const [name, build] of Object.entries(BUILD)) {
      const scene = new THREE.Scene();
      scene.environment = env;
      scene.environmentIntensity = 0.85;
      // a warm key from the upper left (the room's surgical light), a cool rim behind
      const key = new THREE.DirectionalLight('#fff3df', 2.4);
      key.position.set(-0.6, 1, 0.8);
      const rim = new THREE.DirectionalLight('#cfe6ff', 1.3);
      rim.position.set(0.8, 0.3, -1);
      scene.add(key, rim);
      const tool = build(M);
      const pose = POSE[name] ?? POSE.default;
      tool.rotation.x = pose.roll;
      const holder = new THREE.Group();
      holder.add(tool);
      holder.rotation.set(0, pose.yaw, pose.pitch, 'YZX');
      scene.add(holder);
      scene.updateMatrixWorld(true);
      // the frame: the working end and a little of the shaft behind it (its span, a box
      // in the instrument's own axes), wherever the pose has turned it
      const sp = tool.userData.span;
      const ys = sp.y ?? [-sp.r, sp.r], zs = sp.z ?? [-sp.r, sp.r];
      const box = new THREE.Box3();
      for (const x of sp.x) for (const y of ys) for (const z of zs) box.expandByPoint(tool.localToWorld(new THREE.Vector3(x, y, z)));
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const camera = new THREE.PerspectiveCamera(24, W / H, 0.001, 2);
      const half = Math.max(size.y / 2, size.x / 2 / (W / H)) * 1.14;
      const dist = half / Math.tan(THREE.MathUtils.degToRad(12)) + size.z / 2;
      camera.position.set(center.x, center.y, center.z + dist);
      camera.lookAt(center);
      renderer.render(scene, camera);
      out[name] = renderer.domElement.toDataURL('image/webp', 0.9);
      tool.traverse((o) => { if (o.isMesh) o.geometry.dispose(); });
    }
    for (const m of Object.values(M)) m.dispose();
    env.dispose();
    pmrem.dispose();
    return out;
  } catch {
    return null;
  } finally {
    renderer.dispose();
    renderer.forceContextLoss();
  }
}

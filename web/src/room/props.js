// The virtual operating room's pieces: the video on the endoscope's screen, the bed and
// the other equipment shaded as real. Physically based materials
// (matte drapes, brushed steel, painted equipment, a vinyl floor) lit by the room's
// lights and soft shadows. World units are metres, y up; the back wall is at
// z = -3.2, the boom monitors near z = -1.2, the OR table across the frame at z = 0.35
// (the patient's head to the left, where the anaesthesia machine stands), and the
// camera on the surgeons' side, looking over the table at the monitors.

import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { body as bodyHeight, drape } from './drape.js';
import { curtain } from './curtain.js';
import { addPatient } from './patient.js';
import { contactShadow, floorTexture, wallTexture } from './textures.js';
import { addEquipment, plugAt } from './equipment.js';
import { screenMesh, towerScreens, ventilatorScreen } from './displays.js';
import { drapeZones, surfaces } from './surfaces.js';

export const ROOM_COLORS = {
  wall: '#8a9995', rail: '#1f6f61', floor: '#2f403d', ceiling: '#1a2422',
  drape: '#1a4f52', drapeDeep: '#143f42', steel: '#c3cacc', white: '#dfe5e3',
  grey: '#9aa5a6', dark: '#262d30', bezel: '#141a1b', unit: '#2a3134',
  led: '#6ff0b0', ledBlue: '#7cc8ff', lamp: '#f3efe3', beaconIdle: '#7b8987', alert: '#ff4b55',
};

// physically based: roughness 1 is chalk, 0 a mirror; metalness for steel
export const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.6, metalness: 0, ...extra });
export const unlit = (color, extra = {}) => new THREE.MeshBasicMaterial({ color, toneMapped: false, ...extra });

export const rbox = (w, h, d, r, m) => new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, r), m);
export const box = (w, h, d, m) => new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
export const cyl = (rt, rb, h, m, seg = 24) => new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), m);
export const at = (mesh, x, y, z) => { mesh.position.set(x, y, z); return mesh; };
// shadows: what stands in the surgical light casts one; what is lit receives them
export const solid = (mesh, cast = true, receive = true) => {
  mesh.traverse((o) => { if (o.isMesh) { o.castShadow = cast; o.receiveShadow = receive; } });
  return mesh;
};

// A hanging monitor: a black bezel and a screen plane (the plane carries the
// video texture, or sits behind a CSS3D page).
function monitor(w, h, screenMat, M) {
  const g = new THREE.Group();
  g.add(solid(rbox(w + 0.07, h + 0.07, 0.055, 0.018, M.bezel)));
  g.add(solid(at(rbox(w * 0.3, h * 0.3, 0.06, 0.02, M.dark), 0, 0, -0.05)));
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(w, h), screenMat);
  screen.position.z = 0.0285;
  g.add(screen);
  return { group: g, screen };
}

export function buildRoom(scene) {
  // the surfaces' finishes (surfaces.js): brushed steel, enamel, satin plastic,
  // nonwoven drapes, black glass, a polished vinyl floor
  const S = surfaces();
  const M = {
    wall: S.wall(wallTexture(ROOM_COLORS.wall)),
    rail: S.plastic(ROOM_COLORS.rail, 0.4),
    floor: S.floor(floorTexture(ROOM_COLORS.floor)),
    drape: S.drape(ROOM_COLORS.drape, { side: THREE.DoubleSide }),
    drapeDeep: S.drape(ROOM_COLORS.drapeDeep),
    steel: S.steel,
    white: S.paint(ROOM_COLORS.white),
    grey: S.paint(ROOM_COLORS.grey),
    dark: S.plastic(ROOM_COLORS.dark, 0.5),
    bezel: S.plastic(ROOM_COLORS.bezel, 0.36),
    unit: S.plastic(ROOM_COLORS.unit, 0.4),
    rubber: mat('#15191a', { roughness: 0.9 }),
    glass: S.glass(),
  };
  const room = new THREE.Group();
  scene.add(room);
  const add = (m) => { room.add(m); return m; };

  // the shell: floor (with the lighter anti-static field under the table), walls, ceiling
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(16, 12), M.floor);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  add(at(floor, 0, 0, -1));
  const field = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 2.6), mat('#3a4d49', { roughness: 0.38 }));
  field.rotation.x = -Math.PI / 2;
  field.receiveShadow = true;
  add(at(field, 0, 0.002, 0.2));
  add(solid(at(new THREE.Mesh(new THREE.PlaneGeometry(16, 4.4), M.wall), 0, 2.2, -3.2), false));
  add(at(box(16, 0.16, 0.05, M.rail), 0, 0.95, -3.17));
  add(at(box(16, 0.1, 0.04, M.drapeDeep), 0, 0.05, -3.18));
  for (const side of [-1, 1]) {
    const w = new THREE.Mesh(new THREE.PlaneGeometry(9, 4.4), M.wall);
    w.rotation.y = -side * Math.PI / 2;
    w.receiveShadow = true;
    add(at(w, side * 4.2, 2.2, 1));
  }
  const ceiling = new THREE.Mesh(new THREE.PlaneGeometry(16, 12), mat(ROOM_COLORS.ceiling, { roughness: 1 }));
  ceiling.rotation.x = Math.PI / 2;
  add(at(ceiling, 0, 3.05, -1));
  // wall cabinets and a door, low on the back wall
  for (const x of [-2.9, -2.15]) {
    add(at(rbox(0.72, 0.8, 0.3, 0.025, M.white), x, 1.35, -3.04));
    add(at(box(0.012, 0.78, 0.005, mat('#a9b8b5')), x, 1.35, -2.888));
    add(at(box(0.014, 0.16, 0.03, M.steel), x - 0.05, 1.42, -2.875));
    add(at(box(0.014, 0.16, 0.03, M.steel), x + 0.05, 1.42, -2.875));
  }
  add(at(rbox(1.05, 2.15, 0.08, 0.02, M.white), 2.75, 1.075, -3.13));
  add(at(box(0.14, 0.7, 0.01, mat('#5f7772', { roughness: 0.2 })), 2.95, 1.45, -3.085));
  add(at(box(1.0, 0.25, 0.01, M.steel), 2.75, 0.14, -3.085));
  // medical gas outlets on the wall
  // (a steel face, the gas's colour ring, the socket: oxygen green, air black, vacuum white)
  ['#2f8f5b', '#1b1f21', '#e8ece9'].forEach((ring, i) => {
    const x = -2.3 + i * 0.13;
    add(at(rbox(0.09, 0.09, 0.016, 0.006, M.steel), x, 1.85, -3.19));
    add(at(new THREE.Mesh(new THREE.TorusGeometry(0.022, 0.0055, 10, 28), mat(ring, { roughness: 0.4 })), x, 1.85, -3.18));
    add(at(new THREE.Mesh(new THREE.CircleGeometry(0.013, 20), M.dark), x, 1.85, -3.181));
  });

  // the ceiling boom: one pole, an arm and two monitors (the alarm beacon is on monitor C)
  add(solid(at(cyl(0.05, 0.05, 0.8, M.steel), -0.05, 2.95, -1.3)));
  add(solid(at(box(1.9, 0.07, 0.09, M.white), -0.12, 2.55, -1.3)));
  const screens = {};
  const a = monitor(1.12, 0.63, unlit('#000000'), M);
  a.group.position.set(-0.6, 1.7, -1.22);
  a.group.rotation.y = 0.1;
  add(a.group);
  // the drop tubes run from the boom arm (y 2.55) into each monitor's back mount,
  // unbroken (they once stopped short of monitor B's top)
  add(at(cyl(0.02, 0.02, 0.76, M.steel), -0.6, 2.18, -1.28));
  screens.A = a.screen;
  const b = monitor(0.6, 0.8, unlit('#071a17'), M);
  b.group.position.set(0.42, 1.74, -1.16);
  b.group.rotation.y = -0.1;
  add(b.group);
  add(at(cyl(0.02, 0.02, 0.7, M.steel), 0.42, 2.21, -1.24));
  screens.B = b.screen;

  // the laparoscopy tower under monitor A: a white cart with three dark units
  add(solid(at(rbox(0.62, 1.2, 0.56, 0.03, M.white), -1.15, 0.6, -1.7)));
  for (const [dx, dz] of [[-0.25, -0.22], [0.25, -0.22], [-0.25, 0.22], [0.25, 0.22]]) add(at(cyl(0.035, 0.035, 0.05, M.rubber), -1.15 + dx, 0.025, -1.7 + dz));
  const leds = [];
  const towerPlugs = []; // camera, light guide, gas: where the scope's three lines end
  add(at(box(0.5, 0.02, 0.03, M.steel), -1.15, 1.23, -1.39)); // the cart's push handle
  for (let i = 0; i < 3; i++) {
    add(at(rbox(0.54, 0.15, 0.03, 0.01, M.unit), -1.15, 0.78 + i * 0.17, -1.405));
    add(at(box(0.004, 0.11, 0.004, mat('#3d474b')), -1.0, 0.78 + i * 0.17, -1.388)); // a panel joint
    const y = 0.78 + i * 0.17;
    // its screen (displays.js): camera control, light source, insufflator, bottom to top
    const show = towerScreens[i]();
    add(at(box(0.136, 0.056, 0.002, M.glass), -1.19, y + 0.015, -1.3895));
    add(at(screenMesh(0.13, 0.05, show), -1.19, y + 0.015, -1.388));
    // its socket for the scope's line, plugged (the line itself is routed below)
    towerPlugs.push(plugAt(add, M, -0.95, y - 0.005, -1.39, { r: [0.009, 0.008, 0.006][i], body: [M.dark, M.steel, M.white][i] }));
    add(at(box(0.08, 0.007, 0.001, mat('#8d9799', { roughness: 0.4 })), -1.33, y - 0.045, -1.389)); // its label plate
    for (let k = 0; k < 4; k++) add(at(rbox(0.018, 0.012, 0.005, 0.002, M.grey), -1.2 + k * 0.026, y - 0.035, -1.389)); // keys
    for (let j = 0; j < 3; j++) {
      const led = new THREE.Mesh(new THREE.CircleGeometry(0.0055, 12), unlit(j === 2 ? ROOM_COLORS.ledBlue : ROOM_COLORS.led));
      leds.push(led);
      add(at(led, -1.36 + j * 0.035, 0.8 + i * 0.17, -1.388));
    }
  }

  // monitor C on a rolling stand, right of monitor B: the model's reading in both views
  // (A the video, B the tools, C the reading
  // and the siren); its page covers the screen, dark green under it like B's
  const c = monitor(0.88, 0.55, unlit('#071a17'), M);
  c.group.position.set(1.33, 1.76, -1.08);
  c.group.rotation.y = -0.22;
  add(c.group);
  // the beacon sits on monitor C's bezel, by its right corner, with the reading it
  // alarms for (on monitor B until 2026-11-09): grey at rest, red while an alert holds
  c.group.updateMatrixWorld(true);
  const beaconMat = mat(ROOM_COLORS.beaconIdle, { roughness: 0.3, emissive: new THREE.Color(ROOM_COLORS.alert), emissiveIntensity: 0 });
  const beacon = new THREE.Group();
  beacon.add(cyl(0.05, 0.055, 0.03, M.bezel));
  beacon.add(at(new THREE.Mesh(new THREE.SphereGeometry(0.045, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2), beaconMat), 0, 0.015, 0));
  const cTop = 0.55 / 2 + 0.035; // the bezel's top edge, in the monitor's own frame
  beacon.position.copy(c.group.localToWorld(new THREE.Vector3(0.3, cTop + 0.025, 0)));
  beacon.rotation.y = -0.22;
  add(beacon);
  // its mounting foot, seated on the bezel's top edge, so the beacon stands on the
  // monitor instead of floating a centimetre above it
  const foot = solid(rbox(0.1, 0.012, 0.05, 0.004, M.bezel));
  foot.rotation.y = -0.22;
  foot.position.copy(c.group.localToWorld(new THREE.Vector3(0.3, cTop + 0.005, 0)));
  add(foot);
  add(solid(at(cyl(0.022, 0.022, 1.45, M.steel), 1.36, 0.76, -1.13)));
  add(solid(at(cyl(0.26, 0.28, 0.04, M.dark), 1.36, 0.04, -1.13)));
  add(solid(at(rbox(0.42, 0.04, 0.3, 0.01, M.white), 1.36, 0.95, -1.0)));
  screens.C = c.screen;

  // the OR table, across the frame: base, column, the top to the hips (a split-leg table:
  // the leg boards are patient.js's), mattress
  const T = { x: 0, z: -0.42, top: 0.9 };
  const mattress = mat('#1e2a33', { roughness: 0.8 });
  add(solid(at(rbox(0.7, 0.06, 0.45, 0.02, M.dark), T.x + 0.2, 0.03, T.z)));
  add(solid(at(rbox(0.32, 0.8, 0.24, 0.04, M.white), T.x + 0.2, 0.46, T.z)));
  add(solid(at(rbox(1.55, 0.06, 0.56, 0.02, M.dark), T.x - 0.25, T.top - 0.06, T.z)));
  add(solid(at(rbox(1.5, 0.06, 0.52, 0.02, mattress), T.x - 0.25, T.top, T.z)));
  // the patient under one drape sheet from the shoulders to the hips, the head end left,
  // the head uncovered behind the anaesthesia screen; the sheet tents to the table's edges
  // and falls over both long sides in folds; its fenestration at (T.x - 0.01, T.z + 0.07):
  // the reinforced panel around it printed on the sheet (u = (x - x0) / length,
  // v = 0.5 - z / 1.5 on the 1.5 m wide sheet)
  const SH = { x0: -0.62, length: 1.3 };
  const sheet = S.drape(ROOM_COLORS.drape, { side: THREE.DoubleSide, map: drapeZones([(-0.01 - SH.x0) / SH.length, 0.5 - 0.07 / 1.5], [0.56 / SH.length, 0.4 / 1.5]) });
  const sheetMesh = drape({ ...SH, material: sheet });
  add(at(sheetMesh, T.x + sheetMesh.userData.centre, T.top + 0.03, T.z));
  // the legs on their boards, the head and its airway (patient.js)
  const patient = addPatient(add, M, S, { T, mattress });
  // the anaesthesia screen: a bar arched over the patient's upper chest, a linen curtain
  // hung from it, resting on the patient and falling past the
  // table's sides
  const AR = 0.33, AY = T.top + 0.05;
  const arch = solid(new THREE.Mesh(new THREE.TorusGeometry(AR, 0.012, 8, 28, Math.PI), M.steel));
  arch.rotation.y = Math.PI / 2;
  add(at(arch, T.x - 0.5, AY, T.z));
  const onSheet = (z) => T.top + 0.03 + 0.012 + Math.max(bodyHeight(-0.5, z), 0.035 * (1 - Math.min(1, Math.abs(z) / 0.27)));
  const fall = (z) => { const t = Math.min(1, Math.max(0, (Math.abs(z) - 0.22) / 0.11)); return t * t * (3 - 2 * t); };
  add(at(curtain({
    span: 2 * AR,
    top: (z) => Math.sqrt(Math.max(0, AR * AR - z * z)),
    bottom: (z) => onSheet(z) + (T.top - 0.3 - onSheet(z)) * fall(z) - AY,
    material: S.linen('#3a7570'),
  }), T.x - 0.5, AY, T.z));
  // the operative field: skin under a clear incise film, an oval opening in the drape
  const skin = (x, z) => T.top + 0.03 + 0.012 + bodyHeight(x - T.x, z - T.z);
  // the skin in the fenestration under the adhesive incise film: iodine-tinted, and the
  // film glossy, so the lamp shows in it
  const film = new THREE.MeshPhysicalMaterial({ color: '#5e3a28', roughness: 0.55, clearcoat: 0.25, clearcoatRoughness: 0.35 });
  const opening = new THREE.Mesh(new THREE.CircleGeometry(0.1, 40), film);
  opening.rotation.x = -Math.PI / 2;
  opening.scale.set(1.25, 0.9, 1);
  add(at(opening, T.x - 0.01, skin(T.x - 0.01, T.z + 0.07) + 0.004, T.z + 0.07));

  // laparoscopic instruments, as in a cholecystectomy: four trocars in the abdominal
  // wall, each instrument through one, all converging on the gallbladder under the right
  // costal margin; outside, the handles and the camera head lean toward the surgeons'
  // side (the camera's), low, clear of monitor B
  const target = new THREE.Vector3(T.x - 0.2, T.top + 0.12, T.z - 0.12);
  const Y = new THREE.Vector3(0, 1, 0);
  const plastic = mat('#c9d3d6', { roughness: 0.3, transparent: true, opacity: 0.88 });
  const black = mat('#15191b', { roughness: 0.3, metalness: 0.1 });
  const grip = mat('#2b3337', { roughness: 0.5 });
  const accent = mat('#4f7ea8', { roughness: 0.45 }); // brand-neutral blue, never a severity colour
  const trocar = (x, z, r) => {
    const base = new THREE.Vector3(x, skin(x, z) - 0.004, z);
    const dir = base.clone().sub(target).normalize();
    const q = new THREE.Quaternion().setFromUnitVectors(Y, dir);
    const g = new THREE.Group();
    g.add(at(cyl(r + 0.0022, r + 0.0022, 0.035, plastic, 16), 0, 0.014, 0)); // the cannula above the skin
    g.add(at(cyl(0.0175, 0.0145, 0.032, plastic, 20), 0, 0.046, 0)); // the housing
    g.add(at(cyl(0.0135, 0.0135, 0.007, grip, 20), 0, 0.065, 0)); // the seal cap
    g.add(at(box(0.024, 0.005, 0.005, grip), 0.02, 0.04, 0)); // the stopcock's lever
    g.add(at(cyl(0.0035, 0.0035, 0.014, plastic, 8), 0.019, 0.04, 0)); // and its luer
    g.children[4].rotation.z = Math.PI / 2;
    g.position.copy(base);
    g.quaternion.copy(q);
    add(solid(g));
    return { base, dir, q, cock: g.localToWorld(new THREE.Vector3(0.03, 0.04, 0)) };
  };
  // a shaft from inside the port outward, the handle on its end (built along +y)
  const instrument = (port, out, r, shaftMat, handle) => {
    const g = new THREE.Group();
    g.add(at(cyl(r, r, out + 0.05, shaftMat, 12), 0, (out + 0.05) / 2 - 0.05, 0));
    const h = handle();
    h.position.y = out;
    g.add(h);
    g.position.copy(port.base);
    g.quaternion.copy(port.q);
    add(solid(g));
    g.updateMatrixWorld(true);
    return g;
  };
  const pistol = () => {
    const h = new THREE.Group();
    h.add(at(cyl(0.012, 0.012, 0.014, accent, 16), 0, 0.006, 0)); // the rotation knob
    h.add(at(rbox(0.022, 0.065, 0.03, 0.008, grip), 0, 0.048, -0.004)); // the body
    const lever = at(rbox(0.012, 0.055, 0.013, 0.005, grip), 0, 0.045, -0.034);
    lever.rotation.x = 0.35;
    h.add(lever);
    for (const [y, z] of [[0.082, -0.022], [0.03, -0.058]]) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.0145, 0.0042, 8, 22), grip);
      ring.position.set(0, y, z);
      ring.rotation.y = Math.PI / 2;
      h.add(ring);
    }
    return h;
  };
  const pencil = () => {
    const h = new THREE.Group();
    h.add(at(cyl(0.0075, 0.0085, 0.11, grip, 16), 0, 0.055, 0));
    for (const y of [0.03, 0.05]) h.add(at(rbox(0.008, 0.012, 0.006, 0.002, accent), 0, y, 0.008));
    h.add(at(cyl(0.004, 0.006, 0.02, black, 10), 0, 0.12, 0)); // the strain relief
    return h;
  };
  const camera = () => {
    const h = new THREE.Group();
    h.add(at(cyl(0.011, 0.009, 0.026, M.steel, 18), 0, 0.013, 0)); // the scope's eyepiece
    h.add(at(cyl(0.0035, 0.0035, 0.03, M.steel, 10), 0.016, 0.006, 0)); // the light post
    h.children[1].rotation.z = Math.PI / 2;
    h.add(at(cyl(0.016, 0.016, 0.012, M.steel, 20), 0, 0.032, 0)); // the coupler
    h.add(at(rbox(0.036, 0.075, 0.034, 0.012, M.dark), 0, 0.075, 0)); // the camera head
    for (const y of [0.06, 0.08]) h.add(at(cyl(0.004, 0.004, 0.004, accent, 10), 0, y, 0.018));
    h.children.at(-1).rotation.x = Math.PI / 2;
    h.children.at(-2).rotation.x = Math.PI / 2;
    return h;
  };
  const umbilical = trocar(T.x + 0.16, T.z + 0.02, 0.0055);
  const epigastric = trocar(T.x - 0.24, T.z + 0.08, 0.003);
  const subcostal1 = trocar(T.x - 0.08, T.z + 0.12, 0.003);
  const subcostal2 = trocar(T.x + 0.05, T.z + 0.14, 0.003);
  const scope = instrument(umbilical, 0.15, 0.005, M.steel, camera);
  instrument(epigastric, 0.17, 0.0028, black, pistol);
  const hook = instrument(subcostal1, 0.16, 0.0028, black, pencil);
  instrument(subcostal2, 0.17, 0.0028, black, pistol);
  const camEnd = scope.localToWorld(new THREE.Vector3(0, 0.15 + 0.115, 0));
  const lightPost = scope.localToWorld(new THREE.Vector3(0.032, 0.15 + 0.006, 0));
  const hookEnd = hook.localToWorld(new THREE.Vector3(0, 0.16 + 0.13, 0));

  // cables and tubing: the laparoscope's camera and light cables and the insufflation
  // tube to the tower, the breathing circuit to the patient's head, the IV line
  const tube = (pts, r, m, seg = 96) => {
    const curve = new THREE.CatmullRomCurve3(pts.map(([x, y, z]) => new THREE.Vector3(x, y, z)), false, 'centripetal');
    return add(solid(new THREE.Mesh(new THREE.TubeGeometry(curve, seg, r, 8, false), m)));
  };
  const cable = mat('#1b1f21', { roughness: 0.45 });
  const lightCable = mat('#5d6a70', { roughness: 0.4 });
  const clear = mat('#d8e6ea', { roughness: 0.15, transparent: true, opacity: 0.55 });
  const circuit = mat('#8fb0c4', { roughness: 0.35, transparent: true, opacity: 0.8 });
  const v = (p) => [p.x, p.y, p.z];
  // the camera cable from the camera head, the light cable from the scope's light post,
  // the insufflation tube from the umbilical trocar's stopcock: over the drape's far edge
  // and down to the tower; the hook's energy cable over the near edge to the floor
  // the scope's three lines to the tower (camera to the camera control unit, light guide
  // to the light source, gas to the insufflator): off the scope toward the head end, over
  // the drape's far strip, off its far edge, in a loop near the floor, up into the plugs
  const toTower = (start, lane, r, m) => {
    const end = towerPlugs[lane];
    const restX = -0.18 - lane * 0.035, restZ = T.z - 0.235 - lane * 0.012;
    tube([v(start), [start.x - 0.05, start.y + 0.015, start.z - 0.07], [restX + 0.12, skin(restX + 0.12, restZ) + 0.03, restZ + 0.02],
      [restX, skin(restX, restZ) + 0.02, restZ], [restX - 0.14, T.top + 0.045, T.z - 0.29], [-0.56 + lane * 0.02, 0.55, T.z - 0.43],
      [-0.82, 0.3 + lane * 0.04, -1.12], [end[0] + 0.01, end[1] - 0.12, end[2] + 0.13], [end[0], end[1] - 0.02, end[2] + 0.03], end], r, m);
  };
  toTower(camEnd, 0, 0.0055, cable);
  toTower(lightPost, 1, 0.0045, lightCable);
  toTower(umbilical.cock, 2, 0.004, clear);
  // the hook's monopolar cable over the far edge, along the floor, into the generator
  const kit = addEquipment(add, M, { T });
  const sock = kit.esuSocket;
  tube([v(hookEnd), [hookEnd.x + 0.02, hookEnd.y - 0.03, hookEnd.z - 0.1], [T.x - 0.05, T.top + 0.06, T.z - 0.31], [T.x - 0.15, 0.45, T.z - 0.4], [-0.25, 0.04, -1.5], [sock.x, 0.05, sock.z + 0.25], [sock.x, sock.y - 0.12, sock.z + 0.08], v(sock)], 0.004, cable);
  const AN0 = { x: -1.62, z: -0.6 };
  // the breathing circuit's two hoses, inspiratory and expiratory, to the Y-piece at the
  // patient's head (patient.js)
  const [yx, yy, yz] = patient.yPiece;
  tube([[AN0.x + 0.25, 0.98, AN0.z + 0.25], [AN0.x + 0.45, 1.08, AN0.z + 0.24], [yx - 0.16, yy - 0.01, yz - 0.03], [yx - 0.03, yy, yz - 0.006], [yx, yy, yz - 0.004]], 0.01, circuit);
  tube([[AN0.x + 0.25, 0.94, AN0.z + 0.32], [AN0.x + 0.45, 1.04, AN0.z + 0.33], [yx - 0.16, yy - 0.02, yz + 0.035], [yx - 0.03, yy, yz + 0.006], [yx, yy, yz + 0.004]], 0.01, circuit);

  // the anaesthesia machine at the head of the table (its own screen dark: the demo
  // shows no vital signs, it has none)
  const AN = { x: -1.62, z: -0.6 };
  add(solid(at(rbox(0.62, 1.05, 0.55, 0.03, M.white), AN.x, 0.6, AN.z)));
  add(solid(at(rbox(0.66, 0.05, 0.6, 0.015, M.grey), AN.x, 1.15, AN.z)));
  for (let i = 0; i < 3; i++) add(at(box(0.5, 0.005, 0.01, M.grey), AN.x, 0.35 + i * 0.18, AN.z + 0.28));
  add(solid(at(cyl(0.012, 0.012, 0.45, M.steel), AN.x + 0.18, 1.38, AN.z - 0.12)));
  const anScreen = new THREE.Group();
  anScreen.add(solid(rbox(0.4, 0.3, 0.04, 0.012, M.bezel)));
  anScreen.add(at(screenMesh(0.36, 0.26, ventilatorScreen(), 0.8), 0, 0, 0.021)); // its ventilator's settings
  anScreen.position.set(AN.x + 0.18, 1.62, AN.z - 0.1);
  anScreen.rotation.y = 0.5;
  add(anScreen);
  for (const dx of [-0.2, 0.2]) add(solid(at(cyl(0.05, 0.05, 0.42, mat('#cfd8d6', { roughness: 0.35, metalness: 0.5 })), AN.x + dx, 0.42, AN.z - 0.33)));
  // the ventilator's bellows in a clear canister, two vaporisers, the flowmeter tubes
  add(at(cyl(0.075, 0.075, 0.24, mat('#cfe0ea', { transparent: true, opacity: 0.35, roughness: 0.05 })), AN.x - 0.16, 1.3, AN.z + 0.12));
  for (let i = 0; i < 5; i++) add(at(cyl(0.06, 0.06, 0.022, mat('#3c5566', { roughness: 0.6 })), AN.x - 0.16, 1.22 + i * 0.035, AN.z + 0.12));
  for (const [dx, band] of [[0.06, '#5b7fae'], [0.18, '#7e6aa8']]) {
    add(solid(at(rbox(0.09, 0.16, 0.1, 0.01, M.grey), AN.x + dx, 1.26, AN.z + 0.18)));
    add(at(box(0.092, 0.025, 0.102, mat(band, { roughness: 0.5 })), AN.x + dx, 1.3, AN.z + 0.18));
  }
  for (let i = 0; i < 3; i++) add(at(cyl(0.008, 0.008, 0.16, mat('#d5e4ea', { transparent: true, opacity: 0.5, roughness: 0.05 })), AN.x - 0.22 + i * 0.03, 0.95, AN.z + 0.29));
  for (let i = 0; i < 3; i++) add(at(box(0.18, 0.012, 0.02, M.steel), AN.x + 0.12, 0.42 + i * 0.18, AN.z + 0.29));

  // the back table at the right, draped, with instrument trays
  const BT = { x: 1.95, z: -0.3 };
  add(solid(at(rbox(1.0, 0.04, 0.55, 0.01, M.drape), BT.x, 0.92, BT.z)));
  add(solid(at(box(1.0, 0.3, 0.01, M.drapeDeep), BT.x, 0.76, BT.z + 0.275)));
  for (const [dx, dz] of [[-0.45, -0.24], [0.45, -0.24], [-0.45, 0.24], [0.45, 0.24]]) add(solid(at(cyl(0.015, 0.015, 0.9, M.steel), BT.x + dx, 0.45, BT.z + dz)));
  for (const [dx, w] of [[-0.25, 0.36], [0.2, 0.42]]) add(solid(at(rbox(w, 0.04, 0.26, 0.008, M.steel), BT.x + dx, 0.96, BT.z - 0.05)));
  // the Mayo tray over the patient's legs
  add(solid(at(cyl(0.018, 0.018, 1.1, M.steel), 1.35, 0.55, 0.1)));
  add(solid(at(cyl(0.2, 0.22, 0.03, M.dark), 1.35, 0.02, 0.1)));
  add(solid(at(rbox(0.56, 0.03, 0.36, 0.008, M.drape), 1.15, 1.12, 0.1)));
  for (let i = 0; i < 4; i++) add(solid(at(box(0.012, 0.008, 0.22, M.steel), 1.1 + i * 0.04, 1.14, 0.1)));
  // a kick bucket and a step stool by the table
  add(solid(at(cyl(0.17, 0.15, 0.32, M.steel), 0.85, 0.16, 0.25)));
  add(solid(at(rbox(0.45, 0.22, 0.32, 0.02, M.grey), -0.75, 0.11, 0.2)));

  // two surgical lights above the table (their heads and arms; the one at the left
  // casts the room's shadows, see room.js)
  const lampFace = unlit(ROOM_COLORS.lamp);
  const lamps = [];
  for (const [x, y, z, rx, rz] of [[-0.55, 2.78, -0.05, 0.75, 0.2], [0.8, 2.84, -0.2, 0.7, -0.2]]) {
    const head = new THREE.Group();
    head.add(solid(cyl(0.34, 0.3, 0.1, M.white, 32), true, false));
    const face = new THREE.Mesh(new THREE.CircleGeometry(0.27, 32), lampFace);
    face.rotation.x = Math.PI / 2;
    head.add(at(face, 0, -0.051, 0));
    const rim = new THREE.Mesh(new THREE.TorusGeometry(0.335, 0.02, 8, 36), M.steel);
    rim.rotation.x = Math.PI / 2;
    head.add(rim);
    head.position.set(x, y, z);
    head.rotation.set(rx, 0, rz);
    add(head);
    add(at(cyl(0.025, 0.025, 0.5, M.steel), x, y + 0.36, z - 0.05));
    lamps.push(head);
  }

  // an IV pole with a bag, at the head of the table
  add(solid(at(cyl(0.012, 0.012, 2.1, M.steel), -1.25, 1.05, -0.05)));
  // (its bags, pumps and lines: equipment.js)
  // the anaesthesia machine's gas hoses from the wall outlets (oxygen and air, the
  // colours of their rings), sagging down to its back; the vacuum outlet stays free
  [['#2f8f5b', -2.3], ['#1b1f21', -2.17]].forEach(([color, x], k) => {
    tube([[x, 1.85, -3.16], [x, 1.78, -3.08], [x + 0.12, 1.05, -2.5 + k * 0.05], [-1.95 + k * 0.04, 0.55, -1.5], [AN.x - 0.12 + k * 0.05, 0.75, AN.z - 0.33], [AN.x - 0.12 + k * 0.05, 0.85, AN.z - 0.28]], 0.007, mat(color, { roughness: 0.5 }), 64);
  });
  add(solid(at(cyl(0.22, 0.24, 0.03, M.dark), -1.25, 0.015, -0.05)));

  // soft shade on the wall behind what is mounted on it or stands against it, where the
  // room's light cannot reach (no ambient occlusion otherwise)
  const wallShade = new THREE.MeshBasicMaterial({ map: contactShadow(), transparent: true, opacity: 0.7, depthWrite: false, toneMapped: false, polygonOffset: true, polygonOffsetFactor: -1 });
  for (const [x, y, w, h] of [[-2.9, 1.3, 1.0, 1.1], [-2.15, 1.3, 1.0, 1.1], [0.18, 0.62, 0.3, 0.62], [0.46, 0.62, 0.3, 0.62], [1.95, 0.8, 1.05, 0.36], [2.45, 0.98, 0.22, 0.34]]) {
    add(at(new THREE.Mesh(new THREE.PlaneGeometry(w, h), wallShade), x, y, -3.198));
  }

  // contact shadows: where a base or a wheel meets the floor
  const shade = new THREE.MeshBasicMaterial({ map: contactShadow(), transparent: true, depthWrite: false, toneMapped: false });
  for (const [x, z, w, d] of [
    [T.x + 0.2, T.z, 1.0, 0.75], [-1.15, -1.7, 0.95, 0.85], [AN.x, AN.z, 0.95, 0.85], [BT.x, BT.z, 1.3, 0.8],
    [1.36, -1.13, 0.7, 0.7], [-1.25, -0.05, 0.6, 0.6], [1.35, 0.1, 0.55, 0.55], [0.85, 0.25, 0.5, 0.5], [-0.75, 0.2, 0.7, 0.55],
    [-0.42, -2.35, 0.75, 0.65], [1.9, -2.6, 0.7, 0.7],
  ]) {
    const s = new THREE.Mesh(new THREE.PlaneGeometry(w, d), shade);
    s.rotation.x = -Math.PI / 2;
    add(at(s, x, 0.004, z));
  }

  // the screens' glow on the wall behind the boom: in laparoscopy light the monitors
  // are what lights the room
  const glowCanvas = document.createElement('canvas');
  glowCanvas.width = glowCanvas.height = 256;
  {
    const g = glowCanvas.getContext('2d');
    const r = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    r.addColorStop(0, 'rgba(170, 225, 215, 0.42)');
    r.addColorStop(0.55, 'rgba(120, 190, 180, 0.14)');
    r.addColorStop(1, 'rgba(120, 190, 180, 0)');
    g.fillStyle = r; g.fillRect(0, 0, 256, 256);
  }
  const glowMat = unlit('#ffffff', { map: new THREE.CanvasTexture(glowCanvas), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false });
  add(at(new THREE.Mesh(new THREE.PlaneGeometry(4.2, 2.4), glowMat), -0.1, 1.75, -3.19));
  const glowBase = glowMat.color.clone();

  // the wall clock shows the video time, drawn into a canvas texture
  const clockCanvas = document.createElement('canvas');
  clockCanvas.width = 512; clockCanvas.height = 192;
  const clockTex = new THREE.CanvasTexture(clockCanvas);
  clockTex.colorSpace = THREE.SRGBColorSpace;
  add(at(rbox(0.56, 0.23, 0.05, 0.02, M.white), -1.95, 2.18, -3.17));
  add(at(new THREE.Mesh(new THREE.PlaneGeometry(0.5, 0.1875), unlit('#ffffff', { map: clockTex })), -1.95, 2.18, -3.14));
  // the colon ticks while the video plays (dim for the second half of each second)
  // and holds lit when it is paused, as a wall clock's does
  const setClock = (text, colon = true) => {
    const g = clockCanvas.getContext('2d');
    g.fillStyle = '#050b0a'; g.fillRect(0, 0, 512, 192);
    g.font = '600 132px "Atkinson Hyperlegible Mono", monospace';
    g.textBaseline = 'middle'; g.textAlign = 'left';
    let x = 256 - g.measureText(text).width / 2;
    for (const ch of text) {
      g.fillStyle = ch === ':' && !colon ? '#173d2f' : '#7dffc4';
      g.fillText(ch, x, 100);
      x += g.measureText(ch).width;
    }
    clockTex.needsUpdate = true;
  };
  setClock('00:00');

  // the blob's perch: on top of monitor A's bezel, near its right corner
  a.group.updateMatrixWorld(true);
  const perch = a.group.localToWorld(new THREE.Vector3(0.38, 0.315 + 0.035, 0));
  const spots = {
    perch,
    mayo: new THREE.Vector3(1.15, 1.14, 0.1),
    clock: new THREE.Vector3(-1.95, 2.18, -3.14),
    beaconTop: beacon.position.clone().add(new THREE.Vector3(0, 0.07, 0)),
    abdomen: new THREE.Vector3(T.x + 0.08, T.top + 0.22, T.z),
    lampLeft: lamps[0].position.clone(),
  };
  // the patient's draped top line, for framing the presenter view (the near drapes
  // and the floor are cropped: the owner asked to zoom out only a little)
  const table = [[-0.75, T.top + 0.2, T.z + 0.1], [1.2, T.top + 0.15, T.z + 0.1]].map(([x, y, z]) => new THREE.Vector3(x, y, z)); // the patient's draped top
  return { room, screens, beacon: { group: beacon, material: beaconMat }, leds, spots, table, setClock, wallGlow: { material: glowMat, base: glowBase }, liveScreens: kit.screens };
}

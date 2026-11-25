// The theatre's fuller kit, so the room reads as a real one:
// the things a laparoscopic cholecystectomy room holds besides the tower, placed where
// the presenter camera sees them, all behind monitor B or below it, none in front of it:
// - the electrosurgical generator on its cart, behind the anaesthesia screen, the hook's
//   cable plugged into it (props.js routes the cable);
// - two wall suction units on the rail under monitor B, their canisters part-filled with
//   irrigation, one tube running to the field;
// - a glove-box dispenser and a hand-rub dispenser on the wall under monitor C, and a
//   linen hamper beside them;
// - two infusion pumps on the IV pole;
// - the monitors' cables down the boom's drop tubes.
// The devices' screens show their own settings and status (displays.js), never a
// measurement of the patient: the demo has no vital signs and shows none.

import * as THREE from 'three';
import { at, box, cyl, mat, rbox, solid, unlit } from './props.js';
import { esuScreen, pumpScreen, screenMesh } from './displays.js';

// a plug in a device's socket on a face looking along +z: the socket's steel ring, the
// plug's body and its strain relief; the cable leaves from the returned point
export function plugAt(add, M, x, y, z, { r = 0.009, body = M.dark } = {}) {
  const ring = cyl(r + 0.006, r + 0.006, 0.006, M.steel, 20);
  ring.rotation.x = Math.PI / 2;
  add(at(ring, x, y, z + 0.003));
  const plug = cyl(r, r, 0.04, body, 16);
  plug.rotation.x = Math.PI / 2;
  add(solid(at(plug, x, y, z + 0.026)));
  const relief = cyl(r * 0.62, r * 0.75, 0.022, M.dark, 12);
  relief.rotation.x = Math.PI / 2;
  add(at(relief, x, y, z + 0.056));
  return [x, y, z + 0.066];
}

// a wall socket on the back wall, where a power cord ends
function wallSocket(add, M, x, y) {
  add(at(rbox(0.08, 0.08, 0.012, 0.004, M.white), x, y, -3.19));
  for (const dx of [-0.012, 0.012]) add(at(box(0.004, 0.012, 0.002, M.dark), x + dx, y, -3.183));
}

export function addEquipment(add, M, { T, cockAt } = {}) {
  const glass = M.glass;
  const screens = [];
  const led = (color) => new THREE.Mesh(new THREE.CircleGeometry(0.006, 10), unlit(color));
  const tube = (pts, r, m, seg = 64) => {
    const curve = new THREE.CatmullRomCurve3(pts.map(([x, y, z]) => new THREE.Vector3(x, y, z)), false, 'centripetal');
    return add(solid(new THREE.Mesh(new THREE.TubeGeometry(curve, seg, r, 8, false), m)));
  };
  const accent = mat('#4f7ea8', { roughness: 0.45 }); // the instruments' brand-neutral blue

  // ---- the electrosurgical generator on its cart -------------------------------------
  const E = { x: -0.42, z: -2.35 };
  for (const [dx, dz] of [[-0.2, -0.17], [0.2, -0.17], [-0.2, 0.17], [0.2, 0.17]]) {
    add(at(cyl(0.025, 0.025, 0.04, M.rubber, 12), E.x + dx, 0.02, E.z + dz));
    add(solid(at(cyl(0.012, 0.012, 0.76, M.steel, 10), E.x + dx, 0.42, E.z + dz)));
  }
  add(solid(at(rbox(0.48, 0.03, 0.4, 0.008, M.grey), E.x, 0.06, E.z)));
  add(solid(at(rbox(0.48, 0.03, 0.4, 0.008, M.grey), E.x, 0.38, E.z)));
  add(solid(at(rbox(0.48, 0.03, 0.4, 0.008, M.grey), E.x, 0.8, E.z)));
  // the smoke evacuator on the lower shelf
  add(solid(at(rbox(0.4, 0.2, 0.32, 0.015, M.white), E.x, 0.5, E.z)));
  // its port capped: idle in this operation (a tube to a trocar would cross the field)
  add(at(cyl(0.02, 0.02, 0.012, M.steel, 16), E.x + 0.1, 0.5, E.z + 0.164)).rotation.x = Math.PI / 2;
  add(at(cyl(0.016, 0.016, 0.016, M.white, 16), E.x + 0.1, 0.5, E.z + 0.176)).rotation.x = Math.PI / 2;
  add(at(box(0.09, 0.03, 0.002, glass), E.x - 0.08, 0.53, E.z + 0.161)); // its small display, off
  // the generator: a white case, a dark glass front with its sockets and keys
  const esu = new THREE.Group();
  esu.add(solid(rbox(0.42, 0.15, 0.38, 0.015, M.white)));
  esu.add(at(box(0.4, 0.13, 0.004, glass), 0, 0, 0.191));
  const esuShow = esuScreen();
  esu.add(at(screenMesh(0.12, 0.04, esuShow), -0.1, 0.03, 0.1945)); // its outputs as set
  esu.add(at(led('#6ff0b0'), -0.175, 0.03, 0.195)); // ready
  for (const [x, y, r] of [[0.03, -0.03, 0.014], [0.09, -0.03, 0.011], [0.15, -0.03, 0.011]]) {
    const socket = cyl(r, r, 0.01, M.dark, 16);
    socket.rotation.x = Math.PI / 2;
    esu.add(at(socket, x, y, 0.195));
  }
  for (const [x, m] of [[0.06, accent], [0.12, M.white]]) esu.add(at(rbox(0.035, 0.018, 0.006, 0.003, m), x, 0.035, 0.195));
  esu.position.set(E.x, 0.895, E.z);
  add(esu);
  const esuSocket = new THREE.Vector3(E.x + 0.03, 0.865, E.z + 0.2);
  // its power cord, from the back to the wall
  const cord = mat('#202426', { roughness: 0.5 });
  wallSocket(add, M, -0.35, 0.3);
  tube([[E.x - 0.12, 0.86, E.z - 0.19], [E.x - 0.12, 0.74, E.z - 0.26], [E.x - 0.08, 0.05, E.z - 0.42], [-0.38, 0.015, -2.95], [-0.35, 0.12, -3.13], [-0.35, 0.3, -3.175]], 0.004, cord, 64);

  // ---- two wall suction units on the rail, under monitor B ---------------------------
  const W = -3.145; // the back wall's face
  const canister = mat('#dfe9ec', { roughness: 0.08, transparent: true, opacity: 0.42 });
  const fluid = mat('#cfae9e', { roughness: 0.2, transparent: true, opacity: 0.75 });
  const lid = mat('#3f6f8f', { roughness: 0.4 });
  const tops = [];
  for (const [x, fill] of [[0.18, 0.11], [0.46, 0.05]]) {
    // the regulator on the rail, its gauge facing the room
    add(solid(at(rbox(0.09, 0.11, 0.06, 0.01, M.white), x, 0.8, W + 0.03)));
    const gauge = new THREE.Mesh(new THREE.CircleGeometry(0.03, 24), mat('#f2f5f4', { roughness: 0.3 }));
    add(at(gauge, x, 0.815, W + 0.061));
    const needle = box(0.002, 0.024, 0.001, M.dark);
    needle.rotation.z = -0.6;
    add(at(needle, x + 0.006, 0.82, W + 0.063));
    // its bracket, the clear canister with its fluid, the lid
    add(at(box(0.02, 0.2, 0.05, M.steel), x, 0.64, W + 0.025));
    add(solid(at(cyl(0.065, 0.065, 0.24, canister, 24), x, 0.53, W + 0.1)));
    add(at(cyl(0.06, 0.06, fill, fluid, 24), x, 0.41 + fill / 2 + 0.005, W + 0.1));
    add(solid(at(cyl(0.07, 0.07, 0.025, lid, 24), x, 0.66, W + 0.1)));
    add(at(cyl(0.008, 0.008, 0.04, lid, 10), x + 0.03, 0.69, W + 0.1));
    tops.push(new THREE.Vector3(x + 0.03, 0.71, W + 0.1));
  }
  // the first unit's patient tube: down from its lid, along the floor, up to the field
  const clear = mat('#d8e6ea', { roughness: 0.15, transparent: true, opacity: 0.5 });
  const t = tops[0];
  // ... into the suction-irrigation handpiece lying on the drape's far strip, its shaft
  // toward the field
  const hz = T.z - 0.26, hy = T.top + 0.03 + 0.012 + 0.024;
  add(solid(at(rbox(0.13, 0.026, 0.03, 0.008, M.grey), 0.33, hy, hz)));
  for (const [x, m] of [[0.355, M.white], [0.385, accent]]) add(solid(at(cyl(0.0065, 0.0065, 0.022, m, 14), x, hy + 0.02, hz)));
  const shaft = cyl(0.0025, 0.0025, 0.16, M.steel, 10);
  shaft.rotation.z = Math.PI / 2;
  add(solid(at(shaft, 0.185, hy, hz)));
  tube([[t.x, t.y, t.z], [t.x + 0.02, t.y + 0.06, t.z + 0.08], [t.x + 0.05, 0.5, t.z + 0.3], [0.25, 0.05, -2.2], [0.3, 0.04, -1.3], [0.36, 0.45, -0.86], [0.43, 0.9, -0.745], [0.42, hy, hz - 0.01], [0.395, hy, hz]], 0.004, clear, 96);

  // ---- under monitor C: gloves, hand rub, a linen hamper -----------------------------
  add(solid(at(box(0.78, 0.15, 0.11, M.white), 1.95, 0.8, W + 0.055)));
  [['#7aa6cf', 1.7], ['#9a8bc9', 1.95], ['#f2f5f4', 2.2]].forEach(([color, x]) => {
    add(at(box(0.23, 0.12, 0.095, mat(color, { roughness: 0.75 })), x, 0.8, W + 0.06));
    add(at(box(0.2, 0.035, 0.002, mat('#f4f6f5', { roughness: 0.6 })), x, 0.775, W + 0.109)); // the label
    add(at(box(0.08, 0.014, 0.002, M.dark), x, 0.83, W + 0.109)); // the slot
  });
  add(solid(at(rbox(0.1, 0.2, 0.09, 0.015, M.white), 2.45, 1.0, W + 0.045)));
  add(at(rbox(0.06, 0.03, 0.02, 0.006, M.grey), 2.45, 0.94, W + 0.095)); // its lever
  // the linen hamper: four legs under its rim ring (once they stood outside it), a foot
  // ring, and the bag hung in the ring with its cuff turned over it
  const H = { x: 1.9, z: -2.6 }, R = 0.205, leg = R * Math.SQRT1_2;
  for (const [dx, dz] of [[-leg, -leg], [leg, -leg], [-leg, leg], [leg, leg]]) add(solid(at(cyl(0.01, 0.01, 0.82, M.steel, 8), H.x + dx, 0.41, H.z + dz)));
  for (const y of [0.82, 0.08]) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(R, 0.01, 8, 32), M.steel);
    ring.rotation.x = Math.PI / 2;
    add(solid(at(ring, H.x, y, H.z)));
  }
  const bag = mat('#a9c1cf', { roughness: 0.95, side: THREE.DoubleSide });
  add(solid(at(cyl(R - 0.012, 0.17, 0.52, bag, 28), H.x, 0.56, H.z)));
  const cuff = new THREE.Mesh(new THREE.TorusGeometry(R, 0.016, 8, 32), bag);
  cuff.rotation.x = Math.PI / 2;
  add(solid(at(cuff, H.x, 0.815, H.z)));

  // ---- the IV pole: two bags, each line through its own pump to the patient's arm -----
  const P0 = { x: -1.25, z: -0.05 };
  add(at(box(0.26, 0.012, 0.012, M.steel), P0.x, 2.08, P0.z)); // the hook bar
  const bagMat = mat('#cfe6f2', { transparent: true, opacity: 0.45, roughness: 0.15 });
  const line = mat('#e2eef2', { roughness: 0.2, transparent: true, opacity: 0.6 });
  const pumps = [
    { side: 1, y: 1.48, bagX: -1.17, solution: 'NaCl 0.9 %', rate: 100, vtbi: 500 },
    { side: -1, y: 1.28, bagX: -1.33, solution: 'Ringer', rate: 125, vtbi: 1000 },
  ];
  pumps.forEach((p, k) => {
    // the bag on its hook, the spike, the drip chamber
    add(at(cyl(0.002, 0.002, 0.06, M.steel, 6), p.bagX, 2.05, P0.z));
    add(at(rbox(0.09, 0.14, 0.03, 0.02, bagMat), p.bagX, 1.95, P0.z));
    add(at(cyl(0.004, 0.004, 0.02, M.white, 8), p.bagX, 1.87, P0.z));
    add(at(cyl(0.009, 0.009, 0.05, clear, 14), p.bagX, 1.835, P0.z));
    // the pump, clamped to the pole on its side, its screen
    const px = P0.x + p.side * 0.1, pz = P0.z + 0.02;
    const pump = new THREE.Group();
    pump.add(solid(rbox(0.14, 0.16, 0.1, 0.015, M.white)));
    const show = pumpScreen(p.solution, p.rate, p.vtbi);
    screens.push(show);
    pump.add(at(screenMesh(0.09, 0.045, show), -0.01, 0.035, 0.0505));
    pump.add(at(led('#6ff0b0'), 0.05, 0.04, 0.052));
    for (let i = 0; i < 3; i++) pump.add(at(rbox(0.022, 0.014, 0.005, 0.003, M.grey), -0.035 + i * 0.03, -0.03, 0.051));
    pump.add(at(box(0.03, 0.05, 0.05, M.steel), -p.side * 0.085, 0, 0)); // the pole clamp
    pump.position.set(px, p.y, pz);
    add(pump);
    // the line: down from the drip chamber into the pump's top, out of its bottom, and
    // to the patient's arm, where it goes under the drape at the table's near edge
    const inlet = [px + 0.03, p.y + 0.08, pz + 0.035], outlet = [px + 0.03, p.y - 0.08, pz + 0.035];
    tube([[p.bagX, 1.81, P0.z], [p.bagX + 0.01, 1.7, P0.z + 0.01], [inlet[0], inlet[1] + 0.06, inlet[2]], inlet], 0.0022, line, 32);
    const end = [T.x - 0.56 - k * 0.025, T.top + 0.05, T.z + 0.275];
    tube([outlet, [outlet[0], outlet[1] - 0.08, outlet[2] + 0.02], [outlet[0] + 0.12, 1.08, outlet[2] + 0.02], [-0.95, 1.0, -0.05], [end[0] - 0.08, end[1] + 0.03, end[2] + 0.04], end], 0.0022, line, 48);
    // its power cord, to the pole and down it
    tube([[px - p.side * 0.03, p.y - 0.05, pz - 0.05], [P0.x + p.side * 0.016, p.y - 0.1, P0.z - 0.012], [P0.x + p.side * 0.016, 0.3, P0.z - 0.012], [P0.x + p.side * 0.03, 0.04, P0.z - 0.02]], 0.0025, cord, 32);
  });

  // ---- the monitors' cables down the boom's drop tubes -------------------------------
  const cable = mat('#1b1f21', { roughness: 0.45 });
  tube([[-0.53, 2.56, -1.3], [-0.55, 2.35, -1.31], [-0.56, 2.12, -1.3], [-0.5, 1.98, -1.27]], 0.006, cable, 24);
  tube([[0.48, 2.56, -1.27], [0.47, 2.4, -1.27], [0.46, 2.24, -1.25], [0.5, 2.1, -1.22]], 0.006, cable, 24);
  // monitor C's cable: from its back, down its stand's pole, along the floor to the wall
  wallSocket(add, M, 1.75, 0.3);
  tube([[1.35, 1.62, -1.17], [1.385, 1.4, -1.155], [1.39, 0.5, -1.155], [1.42, 0.06, -1.18], [1.6, 0.015, -1.7], [1.74, 0.015, -2.9], [1.75, 0.12, -3.13], [1.75, 0.3, -3.175]], 0.005, cable, 64);

  return { esuSocket, screens };
}

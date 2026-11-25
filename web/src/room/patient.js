// The patient's legs and head (the owner, 2026-11-22: "your patient bed should have 2
// leg stick out ... you cover the patient face like a dead person, you should add a
// breather to the patient mouth"). The table is a split-leg table, as in the French
// position the Strasbourg videos were filmed in (the surgeon between the legs): each leg
// in its legging on its own leg board, apart from the hips. The head is uncovered on a gel
// head ring, in a surgical cap, the eyes taped shut, and intubated: the tracheal tube
// taped at the mouth, its filter and the catheter mount up to the breathing circuit's
// Y-piece, whose two hoses run to the anaesthesia machine (props.js). Everything here
// stands still: no breathing motion, nothing that would draw a frame (the room is drawn
// only as often as it changes).

import * as THREE from 'three';
import { at, cyl, mat, rbox, solid } from './props.js';
import { HIP_X, THIGH_Z } from './drape.js';

export const LEG_SPREAD = 0.24; // rad, each leg board from the table's line
const LEG_LEN = 0.86;

// a leg lying on its board along +x, flattened a little where it rests: a lathe of the
// thigh, knee, calf and ankle, its underside lifted to y = 0
function legGeometry() {
  const profile = [[0, -0.02], [0.06, -0.015], [0.085, 0.02], [0.088, 0.12], [0.08, 0.26], [0.066, 0.4],
    [0.06, 0.46], [0.062, 0.52], [0.058, 0.6], [0.046, 0.72], [0.04, 0.79], [0.034, 0.83], [0, 0.845]];
  const g = new THREE.LatheGeometry(profile.map(([r, y]) => new THREE.Vector2(r, y)), 28);
  g.rotateZ(-Math.PI / 2); // the lathe's axis along +x
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const y = p.getY(i), r = Math.hypot(y, p.getZ(i));
    p.setY(i, (y + r) * 0.82);
  }
  g.computeVertexNormals();
  return g;
}

// a head lying face up, from a unit sphere (x toward the chin, y the face, z the ears):
// the jaw narrows and recedes toward the chin, the chin and the brow stand out, the eye
// sockets sink, the face is a little flatter than the back of the head
function headGeometry() {
  const g = new THREE.SphereGeometry(1, 64, 44);
  const p = g.attributes.position;
  const sm = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  const bump = (dx, dz, sx, sz) => Math.exp(-(dx * dx) / sx - (dz * dz) / sz);
  for (let i = 0; i < p.count; i++) {
    let x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const jaw = sm(0.1, 1, x);
    z *= 1 - 0.36 * jaw;
    if (y < 0) y *= 1 - 0.6 * sm(0.2, 1, x); // under the jaw, toward the neck
    if (y < 0 && x < 0.2) { y *= 1.04; z *= 1.03; } // the back of the skull
    if (y > 0) {
      y *= 1 - 0.07 * y; // a flatter face
      y += 0.09 * bump(x - 0.86, z, 0.012, 0.05); // the chin
      y += 0.035 * bump(x + 0.3, z, 0.006, 0.18) * sm(0.2, 0.6, y); // the brow
      y -= 0.045 * bump(x + 0.18, Math.abs(z) - 0.36, 0.008, 0.016); // the eye sockets
      y += 0.02 * bump(x - 0.2, Math.abs(z) - 0.55, 0.03, 0.02); // the cheekbones
    }
    p.setXYZ(i, x, y, z);
  }
  g.computeVertexNormals();
  return g;
}

export function addPatient(add, M, S, { T, mattress }) {
  const top = T.top + 0.03; // the mattress's surface

  // ---- the legs: two leg boards hinged at the hips, each leg in its legging ----------
  const legGeo = legGeometry();
  for (const side of [1, -1]) {
    const g = new THREE.Group();
    g.position.set(T.x + HIP_X, 0, T.z + side * THIGH_Z);
    g.rotation.y = -side * LEG_SPREAD;
    g.add(solid(at(rbox(LEG_LEN + 0.02, 0.05, 0.22, 0.015, M.dark), LEG_LEN / 2, T.top - 0.055, 0)));
    g.add(solid(at(rbox(LEG_LEN, 0.06, 0.2, 0.02, mattress), LEG_LEN / 2, T.top, 0)));
    // the board's hinge plate under it, at the hip
    g.add(solid(at(rbox(0.12, 0.04, 0.18, 0.01, M.steel), 0.04, T.top - 0.1, 0)));
    const leg = solid(new THREE.Mesh(legGeo, M.drape));
    g.add(at(leg, -0.02, top + 0.002, 0));
    // the foot in the legging, toes up, leaning a little toward the foot end
    const foot = solid(new THREE.Mesh(new THREE.SphereGeometry(1, 24, 16), M.drape));
    foot.scale.set(0.05, 0.095, 0.045);
    foot.rotation.z = -0.3;
    g.add(at(foot, 0.79, top + 0.085, 0));
    add(g);
  }

  // ---- the head ----------------------------------------------------------------------
  const C = new THREE.Vector3(T.x - 0.76, top + 0.12, T.z); // the head's centre
  const RX = 0.105, RY = 0.09, RZ = 0.078; // crown to chin along x, the face up, ear to ear
  const skin = new THREE.MeshPhysicalMaterial({ color: '#c49c86', roughness: 0.55, sheen: 0.3, sheenRoughness: 0.6, sheenColor: new THREE.Color('#e3b49a') });
  // the gel head ring under it
  const ring = solid(new THREE.Mesh(new THREE.TorusGeometry(0.066, 0.026, 12, 36), mat('#6f8ea3', { roughness: 0.3 })));
  ring.rotation.x = -Math.PI / 2;
  add(at(ring, C.x - 0.01, top + 0.026, C.z));
  const head = solid(new THREE.Mesh(headGeometry(), skin));
  head.scale.set(RX, RY, RZ);
  add(at(head, C.x, C.y, C.z));
  head.updateMatrixWorld(true);
  // the face's height over (dx toward the chin, dz across), found on the head itself
  const ray = new THREE.Raycaster();
  const down = new THREE.Vector3(0, -1, 0);
  const face = (dx, dz) => {
    ray.set(new THREE.Vector3(C.x + dx, C.y + 1, C.z + dz), down);
    return ray.intersectObject(head)[0]?.point.y ?? C.y;
  };
  // the neck, from under the jaw to the shoulders under the sheet
  const neck = solid(cyl(0.044, 0.047, 0.12, skin, 20));
  neck.rotation.z = Math.PI / 2;
  add(at(neck, C.x + 0.13, C.y - 0.04, C.z));
  // the nose and the ears
  const nose = solid(new THREE.Mesh(new THREE.SphereGeometry(1, 20, 14), skin));
  nose.scale.set(0.022, 0.012, 0.0095);
  add(at(nose, C.x + 0.016, face(0.016, 0) + 0.002, C.z));
  for (const s of [1, -1]) {
    const ear = solid(new THREE.Mesh(new THREE.SphereGeometry(1, 16, 10), skin));
    ear.scale.set(0.022, 0.015, 0.0065);
    add(at(ear, C.x - 0.012, C.y - 0.012, C.z + s * (RZ - 0.005)));
  }
  // the surgical cap over the crown, down to the brows
  const capGeo = new THREE.SphereGeometry(1, 40, 18, 0, Math.PI * 2, 0, 0.4 * Math.PI);
  capGeo.rotateZ(Math.PI / 2); // its pole toward the crown (-x)
  const cap = solid(new THREE.Mesh(capGeo, S.drape('#86a9c2', { side: THREE.DoubleSide })));
  cap.scale.set(RX + 0.01, RY + 0.012, RZ + 0.012);
  add(at(cap, C.x - 0.004, C.y - 0.004, C.z));
  // tape: a strip laid on the face, its corners on the skin
  const tapeMat = mat('#eef1ec', { roughness: 0.75 });
  const tape = (dx0, dx1, dz0, dz1) => {
    const g = new THREE.PlaneGeometry(1, 1, 16, 4);
    g.rotateX(-Math.PI / 2);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const dx = dx0 + (p.getX(i) + 0.5) * (dx1 - dx0), dz = dz0 + (p.getZ(i) + 0.5) * (dz1 - dz0);
      p.setXYZ(i, C.x + dx, face(dx, dz) + 0.0022, C.z + dz);
    }
    g.computeVertexNormals();
    add(new THREE.Mesh(g, tapeMat));
  };
  // the eyes taped shut, as under anaesthesia
  tape(-0.024, -0.011, 0.011, 0.04);
  tape(-0.024, -0.011, -0.04, -0.011);
  // the tube's tape across the upper lip and the cheeks
  tape(0.042, 0.054, -0.036, 0.04);

  // ---- the airway: tracheal tube, filter, catheter mount, Y-piece --------------------
  const mouth = new THREE.Vector3(C.x + 0.06, face(0.06, 0.014) - 0.003, C.z + 0.014);
  const tube = (pts, r, m, seg = 48) => {
    const curve = new THREE.CatmullRomCurve3(pts.map((p) => new THREE.Vector3(...p)), false, 'centripetal');
    return add(solid(new THREE.Mesh(new THREE.TubeGeometry(curve, seg, r, 10, false), m)));
  };
  const clearPlastic = mat('#e2ecee', { roughness: 0.2, transparent: true, opacity: 0.75 });
  const conn = new THREE.Vector3(C.x + 0.005, mouth.y + 0.075, C.z + 0.02); // the 15 mm connector
  tube([[mouth.x, mouth.y - 0.02, mouth.z], [mouth.x, mouth.y + 0.008, mouth.z], [mouth.x - 0.008, mouth.y + 0.045, mouth.z + 0.003],
    [mouth.x - 0.03, mouth.y + 0.068, mouth.z + 0.005], [conn.x, conn.y, conn.z]], 0.0055, clearPlastic);
  const fitting = solid(cyl(0.0085, 0.0085, 0.022, mat('#dfe5e3', { roughness: 0.4 }), 16));
  fitting.rotation.z = Math.PI / 2;
  add(at(fitting, conn.x - 0.008, conn.y, conn.z));
  // the heat-and-moisture filter: a flat clear disc with its white rim
  const filter = new THREE.Group();
  filter.add(solid(cyl(0.03, 0.03, 0.034, mat('#f1f3f1', { roughness: 0.35, transparent: true, opacity: 0.85 }), 28)));
  filter.add(solid(cyl(0.0305, 0.0305, 0.008, mat('#d9dfdd', { roughness: 0.45 }), 28)));
  filter.rotation.z = Math.PI / 2;
  add(at(filter, conn.x - 0.038, conn.y, conn.z));
  // the catheter mount, a short corrugated hose up to the Y-piece
  const Y = new THREE.Vector3(C.x - 0.19, conn.y + 0.035, C.z + 0.02);
  tube([[conn.x - 0.055, conn.y, conn.z], [conn.x - 0.1, conn.y + 0.01, conn.z], [Y.x + 0.04, Y.y - 0.005, Y.z], [Y.x + 0.012, Y.y, Y.z]], 0.0095, mat('#9db7c9', { roughness: 0.35, transparent: true, opacity: 0.85 }), 32);
  const yPiece = solid(cyl(0.013, 0.013, 0.04, mat('#c9d1d3', { roughness: 0.35 }), 16));
  yPiece.rotation.z = Math.PI / 2;
  add(at(yPiece, Y.x, Y.y, Y.z));
  // where the circuit's two hoses join it
  return { yPiece: [Y.x - 0.018, Y.y, Y.z] };
}

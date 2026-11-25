// The room's reflections. Steel and gloss look like metal and paint only when a dark environment holds
// a few bright, hard-edged things to mirror. So the environment is the OR's own light,
// built as a small scene of emitters at their places in the room and baked once with
// PMREM: the laminar-flow ceiling panels above the table (turned down for laparoscopy,
// still the brightest area), the two surgical lamp faces, the endoscope monitor's warm
// glow and the reading monitor's dim one, the door's window, and dim walls and floor
// for the bounce. Radiance is linear and above 1 where a real emitter is, so the
// reflections carry structure instead of one grey mean.

import * as THREE from 'three';

const card = (w, h, rgb, pos, look) => {
  const m = new THREE.Mesh(
    new THREE.PlaneGeometry(w, h),
    new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(...rgb, THREE.LinearSRGBColorSpace), side: THREE.DoubleSide, toneMapped: false }),
  );
  m.position.set(...pos);
  m.lookAt(new THREE.Vector3(...look));
  return m;
};

export function roomEnvironment(renderer, at) {
  const env = new THREE.Scene();
  env.background = new THREE.Color().setRGB(0.012, 0.016, 0.015, THREE.LinearSRGBColorSpace);

  // the shell, dim: walls a little lighter than the floor and ceiling
  const wall = [0.05, 0.066, 0.062];
  env.add(card(16, 4.4, wall, [0, 2.2, -3.2], [0, 2.2, 0]));
  env.add(card(9, 4.4, wall, [-4.2, 2.2, 1], [0, 2.2, 1]));
  env.add(card(9, 4.4, wall, [4.2, 2.2, 1], [0, 2.2, 1]));
  env.add(card(16, 4.4, [0.03, 0.038, 0.036], [0, 2.2, 5], [0, 2.2, 0]));
  env.add(card(16, 12, [0.022, 0.03, 0.028], [0, 0, -1], [0, 1, -1]));
  env.add(card(16, 12, [0.015, 0.018, 0.018], [0, 3.05, -1], [0, 0, -1]));

  // the laminar-flow canopy: a grid of diffuser panels over the table, the bars between
  // them wide enough to survive the bake's blur
  for (let i = 0; i < 4; i++) {
    for (let j = 0; j < 3; j++) {
      const x = -1.2 + i * 0.8, z = -1.0 + j * 0.62;
      env.add(card(0.66, 0.48, [0.95, 1.0, 1.05], [x, 3.02, z], [x, 0, z]));
    }
  }
  // the surgical lamps' faces, warm and the hottest things in the room
  for (const [x, y, z] of [[-0.55, 2.73, -0.05], [0.8, 2.79, -0.2]]) {
    const face = new THREE.Mesh(
      new THREE.CircleGeometry(0.27, 40),
      new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(4.2, 3.9, 3.4, THREE.LinearSRGBColorSpace), side: THREE.DoubleSide, toneMapped: false }),
    );
    face.position.set(x, y, z);
    face.lookAt(x * 0.3, 0.9, -0.42);
    env.add(face);
  }
  // the monitors: A warm with tissue, B the reading's dark green, C off
  env.add(card(1.12, 0.63, [0.62, 0.42, 0.36], [-0.6, 1.7, -1.22], [-0.6, 1.7, 3]));
  env.add(card(0.6, 0.8, [0.05, 0.12, 0.1], [0.42, 1.74, -1.16], [0.42, 1.74, 3]));
  // the door's window, the corridor's cool light
  env.add(card(0.14, 0.7, [0.35, 0.42, 0.5], [2.95, 1.45, -3.08], [2.95, 1.45, 0]));

  const pmrem = new THREE.PMREMGenerator(renderer);
  const target = pmrem.fromScene(env, 0.008, 0.05, 30, { size: 256, position: at });
  pmrem.dispose();
  env.traverse((o) => { o.geometry?.dispose(); o.material?.dispose(); });
  return target.texture;
}

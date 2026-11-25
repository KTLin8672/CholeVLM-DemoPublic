// The alert's moment in the room (the surface's memorable moment: the beacon on the
// boom turning red as the model raises an alert). When an alert is newly raised, the
// beacon throws a rotating red beam across the walls, the ceiling and the boom for
// four seconds, as a real rotating beacon does, then leaves the slow throb that holds
// while the alert holds (room.js). Red, because it is an alert and only then; nothing
// on a seek (onEvent is not called on a jump); under "reduce motion" no sweep at all,
// the beacon's own glow says it. The monitors' screens are unlit, so the beam never
// tints the video or a page. See README.md in this folder.
import * as THREE from 'three';

const SWEEP_MS = 4000;
const TURN_MS = 1500; // one turn of the beacon's mirror

export function setup(scene, ctx) {
  const top = ctx.room.spot('beaconTop');
  if (!top) return {};
  // built once, dark at rest: a light added later would recompile every material
  const beam = new THREE.SpotLight(ctx.palette.alert, 0, 8, 0.6, 0.65, 1.1);
  beam.position.copy(top).add(new THREE.Vector3(0, -0.04, 0));
  ctx.room.scene.add(beam, beam.target);
  let at = -1e9;

  return {
    onEvent(e) {
      if (e.severity === 'alert' && !ctx.reducedMotion) { at = performance.now(); ctx.wake(SWEEP_MS); }
    },
    tick(now) {
      const k = (now - at) / SWEEP_MS;
      if (k < 0 || k >= 1) { beam.intensity = 0; return; }
      // in quickly, out over the last fifth
      const env = Math.min(1, k / 0.04) * Math.min(1, (1 - k) / 0.2);
      const a = ((now - at) / TURN_MS) * Math.PI * 2;
      beam.target.position.set(top.x + Math.sin(a) * 3, top.y - 0.45, top.z - Math.cos(a) * 3);
      beam.intensity = 18 * env;
    },
  };
}

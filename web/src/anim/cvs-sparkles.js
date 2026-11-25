// Dormant: "CVS reached" is not a capability of v1, and the served
// CVS is a screening signal, never drawn as achieved; `cvsNew` is always empty,
// so this never fires. Kept in the owner's folder.
// When a CVS criterion is newly achieved, its box on the reading (monitor C) pulses: a ring grows
// out of the box and a few sparks fan out to its left, away from the label on its
// right, so nothing on the lane is covered. Sizes follow the box as the camera
// frames it. Nothing on a seek (the achievement did not just
// happen), nothing when the dot is off screen, and nothing under "reduce motion".
import * as THREE from 'three';

const LIFE = 0.9; // s
const SPARKS = 6;

export function setup(scene, ctx) {
  const ringGeo = new THREE.RingGeometry(0.78, 1, 40);
  const sparkGeo = new THREE.CircleGeometry(1.8, 8);
  const colors = [ctx.palette.mint, ctx.palette.lavender, ctx.palette.pink];
  const live = [];

  const pulse = (key) => {
    const a = ctx.anchor(`cvs-${key}`);
    if (!a || a.w === 0 || a.bottom < 0 || a.top > ctx.size.h) return;
    const ring = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({ color: ctx.palette.mint, transparent: true }));
    ring.position.set(a.x, a.y, 40);
    scene.add(ring);
    const sparks = Array.from({ length: SPARKS }, (_, i) => {
      const m = new THREE.Mesh(sparkGeo, new THREE.MeshBasicMaterial({ color: colors[i % colors.length], transparent: true }));
      scene.add(m);
      // a fan from 135° to 225°: up-left, left, down-left
      return { m, ang: ((135 + (90 * i) / (SPARKS - 1)) * Math.PI) / 180 };
    });
    live.push({ ring, sparks, x: a.x, y: a.y, r0: Math.max(4, a.w / 2), born: performance.now() });
    ctx.wake(LIFE * 1000);
  };

  const drop = (p) => {
    for (const m of [p.ring, ...p.sparks.map((s) => s.m)]) {
      scene.remove(m);
      m.material.dispose();
    }
  };

  return {
    onDecision(d) {
      if (d.jumped || ctx.reducedMotion) return;
      for (const key of d.cvsNew) pulse(key);
    },
    tick(now) {
      for (let i = live.length - 1; i >= 0; i--) {
        const p = live[i];
        const k = (now - p.born) / 1000 / LIFE;
        if (k >= 1) { drop(p); live.splice(i, 1); continue; }
        const ease = 1 - (1 - k) ** 3;
        p.ring.scale.setScalar(p.r0 + 6 * ease); // from the box's half-width outward
        p.ring.material.opacity = 0.9 * (1 - k);
        for (const s of p.sparks) {
          const r = p.r0 + 3 + 5 * ease;
          s.m.position.set(p.x + Math.cos(s.ang) * r, p.y + Math.sin(s.ang) * r, 41);
          s.m.material.opacity = 1 - k;
        }
      }
    },
  };
}

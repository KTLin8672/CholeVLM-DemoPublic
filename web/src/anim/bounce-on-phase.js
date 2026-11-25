// A pastel blob perched on top of the endoscope monitor in the virtual OR, breathes,
// hops when the procedure moves on to a later phase (taking the new phase's colour),
// and shivers red on an alert. It glances at the reading on monitor C when the reading
// changes in substance (a phase, a tool, a criterion, an event), and between times
// looks about: down at the video under it, back at the room. A phase going backward is an anomaly, not progress:
// the blob only takes the colour, it does not hop. Nothing hops on a seek, and under
// "reduce motion" it keeps still. It lives in the room (ctx.room.scene, metres), so
// the monitors' pages are always drawn over it. See README.md in this folder.
import * as THREE from 'three';

export function setup(scene, ctx) {
  const R = 0.075; // metres
  const buddy = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.SphereGeometry(R, 32, 16),
    new THREE.MeshToonMaterial({ color: ctx.palette.pink }),
  );
  body.scale.y = 0.9;
  buddy.add(body);
  const eyeGeo = new THREE.SphereGeometry(R * 0.13, 12, 8);
  const eyeMat = new THREE.MeshBasicMaterial({ color: 0x152523 });
  const eyes = [-1, 1].map((side) => {
    const eye = new THREE.Mesh(eyeGeo, eyeMat);
    eye.position.set(side * R * 0.32, R * 0.16, R * 0.9);
    buddy.add(eye);
    return eye;
  });
  const cheekMat = new THREE.MeshBasicMaterial({ color: 0xff8fab, transparent: true, opacity: 0.75 });
  for (const side of [-1, 1]) {
    const cheek = new THREE.Mesh(new THREE.CircleGeometry(R * 0.15, 16), cheekMat);
    cheek.position.set(side * R * 0.55, -R * 0.08, R * 0.84);
    cheek.rotation.y = side * 0.5;
    buddy.add(cheek);
  }
  ctx.room.scene.add(buddy);
  const seat = ctx.room.spot('perch') ?? new THREE.Vector3();

  const color = new THREE.Color(ctx.palette.pink);
  const target = new THREE.Color(ctx.palette.pink);
  const alertColor = new THREE.Color(ctx.palette.alert);
  let hopAt = -1e9;
  let shiverAt = -1e9;
  let blinkAt = 0;
  // where it looks: yaw (toward +x turns right) and pitch (down is positive)
  // the reading (on monitor C since 2026-11-09) is far to its right and a little
  // below: a three-quarter turn, so the eyes stay in view
  const reading = { yaw: 0.85, pitch: 0.18 };
  buddy.rotation.order = 'YXZ'; // turn, then nod
  const LOOKS = [{ yaw: 0, pitch: 0 }, { yaw: -0.35, pitch: 0.55 }, { yaw: 0.25, pitch: -0.1 }, { yaw: -0.15, pitch: 0.05 }];
  const gaze = { yaw: 0, pitch: 0 };
  let look = LOOKS[0];
  let lookUntil = 0;
  let nextIdle = performance.now() + 6000;
  let last = performance.now();

  return {
    onDecision(d) {
      const news = d.phaseChanged || d.toolsNew?.length || d.cvsNew?.length || d.eventsNew?.length;
      if (news && !d.jumped && !ctx.reducedMotion) {
        look = reading;
        lookUntil = performance.now() + 1800;
        ctx.wake(600); // the turn of its head
      }
      if (!d.phaseChanged) return;
      target.set(ctx.phaseColor(d.state.phase));
      if (!d.phaseBackward && !d.jumped && !ctx.reducedMotion) { hopAt = performance.now(); ctx.wake(700); }
    },
    onEvent(e) {
      if (e.severity === 'alert' && !ctx.reducedMotion) { shiverAt = performance.now(); ctx.wake(900); }
    },
    tick(now) {
      const k = (now - hopAt) / 700;
      const hop = k >= 0 && k < 1 ? Math.sin(k * Math.PI) : 0;
      const breathe = ctx.reducedMotion ? 1 : 1 + 0.04 * Math.sin(now / 420);
      const s = (now - shiverAt) / 900;
      const shiver = s >= 0 && s < 1 ? Math.sin(now / 18) * 0.012 * (1 - s) : 0;
      buddy.position.set(seat.x + shiver, seat.y + R * 0.88 + hop * 0.14, seat.z);
      buddy.scale.set(1 + 0.12 * hop, breathe * (1 - 0.1 * hop) + 0.2 * hop, 1);
      buddy.rotation.z = hop * 0.25 * Math.sin(k * Math.PI * 2);
      // the gaze: held on the reading for a moment, else an idle look every few seconds
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (ctx.reducedMotion) look = LOOKS[0];
      else if (now > lookUntil && now > nextIdle) {
        look = LOOKS[Math.floor(Math.random() * LOOKS.length)];
        lookUntil = now + 1400 + Math.random() * 1600;
        nextIdle = lookUntil + 4000 + Math.random() * 5000;
      } else if (now > lookUntil) look = LOOKS[0];
      const e = 1 - Math.exp(-dt * 7);
      gaze.yaw += (look.yaw - gaze.yaw) * e;
      gaze.pitch += (look.pitch - gaze.pitch) * e;
      buddy.rotation.y = gaze.yaw;
      buddy.rotation.x = gaze.pitch;
      color.lerp(target, 0.06);
      body.material.color.copy(color);
      if (s >= 0 && s < 1) body.material.color.lerp(alertColor, 0.6 * (1 - s));
      // a blink every few seconds
      if (now > blinkAt + 3800) blinkAt = now;
      const blink = now - blinkAt < 120 ? 0.15 : 1;
      for (const eye of eyes) eye.scale.y = blink;
    },
  };
}

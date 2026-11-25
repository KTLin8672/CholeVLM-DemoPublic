// The room's own life, apart from the animations of anim/, so the OR looks live. Two things, both decoration, neither a value:
//
// - Monitor A lights the room with the video's own colour. The video (or the 1 fps
//   frame) is sampled a few times a second into a tiny canvas; its average colour,
//   washed toward white so it never reads as the alarm's red, tints monitor A's spill
//   light and the glow on the wall, and its brightness sets how much they give. A dark
//   scene darkens the room, a bright one lifts it, as a real endoscope monitor does.
// - The laparoscopy tower's status lights: power and the light source steady, each
//   unit's activity light flickering at its own pace. Under "reduce motion" they hold.
// Both move only when the room is drawn (room.js): a few times a second while the video
// plays, and not at all while it is paused.

import * as THREE from 'three';

const SAMPLE_MS = 250;
const SPILL_DEFAULT = new THREE.Color('#e6f4ff');

export function roomLife({ parts, spillA, screenA, reducedMotion }) {
  const probe = document.createElement('canvas');
  probe.width = 16; probe.height = 9;
  const g = probe.getContext('2d', { willReadFrequently: true });
  let sampledAt = -1e9;
  let usable = true;
  const target = SPILL_DEFAULT.clone();
  let targetPower = 1;
  const basePower = spillA.intensity;
  const hsl = { h: 0, s: 0, l: 0 };

  const sample = () => {
    const src = screenA.map?.image;
    const ready = src instanceof HTMLVideoElement ? src.readyState >= 2 : src?.complete && src.naturalWidth;
    if (!ready) { target.copy(SPILL_DEFAULT); targetPower = 0.7; return; }
    try {
      g.drawImage(src, 0, 0, probe.width, probe.height);
      const px = g.getImageData(0, 0, probe.width, probe.height).data;
      let r = 0, gr = 0, b = 0;
      for (let i = 0; i < px.length; i += 4) { r += px[i]; gr += px[i + 1]; b += px[i + 2]; }
      const n = px.length / 4;
      const c = new THREE.Color().setRGB(r / n / 255, gr / n / 255, b / n / 255, THREE.SRGBColorSpace);
      const lum = 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b; // linear
      // washed toward white: tissue's pink tints the room, it never paints it red
      c.getHSL(hsl);
      target.setHSL(hsl.h, Math.min(hsl.s, 0.45) * 0.55, 0.8);
      targetPower = 0.45 + 1.6 * Math.min(1, Math.sqrt(lum) * 1.4);
    } catch {
      usable = false; // a source the canvas may not read: keep the steady spill
    }
  };

  const glow = parts.wallGlow;
  const tint = new THREE.Color();
  // per unit: [activity period in ms, share of the period lit]
  const pace = [[1300, 0.55], [430, 0.4], [2100, 0.75]];
  const ledColor = parts.leds.map((m) => m.material.color.clone());
  const hash = (n) => { const x = Math.sin(n * 127.1) * 43758.5453; return x - Math.floor(x); };

  let last = performance.now();
  let painted = 0;
  return function tick(now) {
    // the infusion pumps' running arrows (displays.js), a step every 600 ms
    if (!reducedMotion() && now - painted > 600) { painted = now; for (const s of parts.liveScreens ?? []) s.paint(now); }
    // (up to a frame of the few a second the room is drawn while the video plays)
    const dt = Math.min(0.3, (now - last) / 1000);
    last = now;
    if (usable && now - sampledAt > SAMPLE_MS) { sampledAt = now; sample(); }
    // eased: a cut in the video brightens or dims the room over about a second
    const k = 1 - Math.exp(-dt * (reducedMotion() ? 1 : 3));
    spillA.color.lerp(target, k);
    spillA.intensity += (basePower * targetPower - spillA.intensity) * k;
    tint.copy(glow.base).lerp(spillA.color, 0.7).multiplyScalar(0.35 + 0.7 * Math.min(1.5, spillA.intensity / basePower));
    glow.material.color.copy(tint);

    parts.leds.forEach((led, i) => {
      const unit = Math.floor(i / 3), j = i % 3;
      let on = 1;
      if (j === 1 && !reducedMotion()) {
        const [period, share] = pace[unit];
        const step = Math.floor(now / period);
        on = hash(step + unit * 31) < share ? 1 : 0.16;
      }
      led.material.color.copy(ledColor[i]).multiplyScalar(on);
    });
  };
}

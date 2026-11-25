// The animation layer. Every module in ./anim/ is loaded on its own (see
// anim/README.md) and may draw in two places: the overlay, one transparent canvas
// over the whole window in screen pixels (never in the way of a click), and the
// virtual operating room itself (ctx.room), in metres.

import * as THREE from 'three';
import { PALETTE, phaseColor, phaseIndex } from './panels.js';

const modules = import.meta.glob('./anim/*.js', { eager: true });

export function startLayer(canvas, room) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  const scene = new THREE.Scene();
  // Pixel units, origin at the bottom-left of the window, y up.
  const camera = new THREE.OrthographicCamera(0, 1, 1, 0, -1000, 1000);
  scene.add(new THREE.AmbientLight(0xffffff, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 2.2);
  sun.position.set(-300, 500, 800);
  scene.add(sun);

  const size = { w: 1, h: 1 };
  const resize = () => {
    size.w = window.innerWidth;
    size.h = window.innerHeight;
    renderer.setSize(size.w, size.h, false);
    camera.right = size.w;
    camera.top = size.h;
    camera.updateProjectionMatrix();
  };
  resize();
  window.addEventListener('resize', resize);

  // A panel's box in overlay coordinates (pixels, y up): 'video' (the endoscope
  // monitor), 'readings' (the reading, monitor C), 'engineer' (monitor B in the engineer
  // view), 'tools-page' (monitor B in the presenter view), 'controls', 'timeline', 'phase',
  // 'tools', 'cvs' (the critical view; no criterion's box),
  // 'flags', 'step', 'reply', 'events',
  // 'ask', 'delay', 'room'. A hidden panel has a zero box.
  const SCREENS = { video: 'A' };
  const anchor = (name) => {
    let r;
    if (SCREENS[name]) r = room.screenRect(SCREENS[name]);
    else {
      const el = document.querySelector(`[data-anchor="${name}"]`);
      if (!el) return null;
      r = el.getBoundingClientRect();
    }
    return {
      x: r.left + r.width / 2, y: size.h - (r.top + r.height / 2),
      w: r.width, h: r.height,
      left: r.left, right: r.right, top: size.h - r.top, bottom: size.h - r.bottom,
    };
  };

  // The viewer's "reduce motion" setting, read live: an animation then keeps still.
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const ctx = {
    THREE, camera, size, anchor, palette: PALETTE, phaseColor, phaseIndex,
    get reducedMotion() { return motion.matches; },
    // The room is drawn only as often as it changes, a few times a second while the
    // video plays (room.js): a short animation asks for every frame while it runs.
    wake: (ms) => room.wake(ms),
    // The room: add meshes to room.scene (metres, y up). Spots: room.spot('perch')
    // on top of the endoscope monitor, 'mayo' the instrument tray, 'clock' the wall
    // clock, 'beaconTop' the alarm beacon; room.toOverlay(v) maps a world point into
    // overlay pixels.
    room: {
      scene: room.scene, camera: room.camera, spot: room.spot,
      toOverlay(v) { const p = room.project(v); return { x: p.x, y: size.h - p.y }; },
    },
  };
  const anims = [];
  for (const [path, mod] of Object.entries(modules)) {
    if (typeof mod.setup !== 'function') continue;
    try {
      anims.push({ path, hooks: mod.setup(scene, ctx) ?? {} });
    } catch (err) {
      console.error(`animation ${path} failed in setup`, err);
    }
  }
  // One broken animation never stops the screen or the others.
  const call = (name, ...args) => {
    for (const a of anims) {
      try {
        a.hooks[name]?.(...args);
      } catch (err) {
        console.error(`animation ${a.path} failed in ${name}`, err);
      }
    }
  };

  // ticks run just before the room renders, so the room's meshes move with it
  let last = performance.now();
  room.onFrame((now) => {
    call('tick', now, (now - last) / 1000);
    last = now;
    renderer.render(scene, camera);
  });

  return {
    count: anims.length,
    decision: (d, prev) => call('onDecision', d, prev),
    event: (e) => call('onEvent', e),
  };
}

// The virtual operating room (the owner's pick, 2026-11-05). The video plays on the
// endoscope monitor (A) as a texture. Since the owner's arrangement of 2026-11-09, the
// boom monitor beside it (B) shows the tools (in view now, and the model's next one)
// in the presenter view and the engineer's figures in the engineer view, and the
// monitor on its stand (C) the model's reading in both, with the alarm beacon on it:
// DOM pages placed in the room with CSS3D so their text stays crisp. Both views frame
// all three, the engineer view as close as they fit; a drag turns the room round the
// vertical axis through the view's centre. It is drawn only as often as something on
// it changes (`tick`).

import * as THREE from 'three';
import { CSS3DRenderer, CSS3DObject } from 'three/addons/renderers/CSS3DRenderer.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { buildRoom, ROOM_COLORS } from './props.js';
import { roomLife } from './life.js';
import { roomEnvironment } from './environment.js';
import { standInScreen } from './displays.js';

const VIEW_DIR = {
  presenter: new THREE.Vector3(0.02, -0.16, -1).normalize(),
  engineer: new THREE.Vector3(0.03, -0.05, -1).normalize(),
  // phones (the owner, 2026-11-07: the camera may change, the room may not): square-on
  // to the endoscope monitor, which faces 0.1 rad to the right, so the footage is not
  // foreshortened; a landscape phone's wide band faces the boom to take in both
  // monitors and the beacon
  compact: new THREE.Vector3(-Math.sin(0.1), -0.05, -Math.cos(0.1)).normalize(),
  compactWide: new THREE.Vector3(0, -0.07, -1).normalize(),
};
// the owner, 2026-11-09: "presenter: monitor left to right, A: video B: tool C: board and
// siren. Engineer zoom in so A and B and C are in view only as big as possible"
const VIEW_SCREENS = { presenter: ['A', 'B', 'C'], engineer: ['A', 'B', 'C'], compact: ['A'], compactWide: ['A', 'B', 'C'] };
// a stage at least this much wider than tall frames the boom whole (a landscape phone)
const WIDE = 1.9;
const easeOutExpo = (k) => (k >= 1 ? 1 : 1 - 2 ** (-10 * k));

export function createRoom({ stage, canvas, cssRoot, pages, flat, insets, reducedMotion, playing = () => false }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  // film-like tone and soft shadows: the realism the owner asked for
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  const css = new CSS3DRenderer({ element: cssRoot });

  // Drawing frugally. On 2026-11-06 a browser on
  // the Spark's own desktop drew this room sixty times a second and took a fifth of the
  // GPU from training. The video is 1 fps, and the room's own life (the status lights,
  // the pumps' arrows, the clock's colon) steps no faster than a few times a second, so
  // the room is drawn:
  // - at full rate only while something moves for the viewer: the turn under the hand
  //   and as it eases after, the camera between views, a short animation that asks
  //   for it (`wake`: the blob's hop, the beacon's sweep, a criterion's sparks);
  // - every PLAY_MS while the video plays;
  // - while it is paused, only when something changes (`invalidate`: a seek, a decision,
  //   a view, a resize, a picture loaded), then for SETTLE_MS while the eased lights
  //   catch up; still otherwise;
  // - never while the page is hidden.
  // The same in every view. A recording draws every frame (`frugal = false`).
  const PLAY_MS = 250, SETTLE_MS = 1200;
  let frugal = true, dirty = true, fullUntil = 0, settleUntil = performance.now() + 3000;
  let lastDraw = -1e9, pendingFrame = 0, timer = 0;
  const beforeHooks = [], frameHooks = [];
  const moving = (now) => yaw !== yawTo || from !== null || now < fullUntil;
  function ask() {
    if (!pendingFrame && !document.hidden) pendingFrame = requestAnimationFrame(tick);
  }
  function invalidate() {
    dirty = true;
    settleUntil = Math.max(settleUntil, performance.now() + SETTLE_MS);
    ask();
  }
  const wake = (ms) => { fullUntil = Math.max(fullUntil, performance.now() + ms); ask(); };
  function tick(now) {
    pendingFrame = 0;
    clearTimeout(timer);
    timer = 0;
    if (document.hidden) return;
    const paced = playing() || now < settleUntil;
    if (!frugal || dirty || moving(now) || (paced && now - lastDraw >= PLAY_MS - 8)) draw(now);
    if (!frugal || moving(now)) ask();
    else if (playing() || now < settleUntil) timer = setTimeout(ask, Math.max(0, PLAY_MS - (now - lastDraw)));
  }
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) invalidate();
    else { clearTimeout(timer); timer = 0; }
  });
  // the faces of the kit's screens arrive after the first frame (displays.js)
  document.fonts?.ready.then(invalidate);

  // ambient occlusion (GTAO): the darkening where surfaces meet, under and between
  // things, that the lights alone do not give, and whose absence reads as a toy. The
  // room renders linear into a multisampled half-float target, takes the occlusion,
  // and is tone-mapped once at the end. The endoscope's video is not part of that: it
  // is drawn after, straight to the screen, untouched (see `draw`), so the footage
  // keeps its own colours. A viewer whose machine cannot keep up loses the occlusion,
  // not the frame rate.
  const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 }));
  const scene0 = new THREE.Scene(); // replaced below, once the scene exists
  const renderPass = new RenderPass(scene0, null);
  composer.addPass(renderPass);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#0a1413');
  // the reflections: the OR's own lights baked into an environment (environment.js),
  // so steel, enamel, glass and the floor have the room's bright things to mirror
  scene.environment = roomEnvironment(renderer, new THREE.Vector3(0, 1.5, -0.6));
  scene.environmentIntensity = 1.0;
  // laparoscopy light: the room lights are down, the monitors and one surgical light
  // carry the scene; a faint fill keeps the shapes readable
  scene.add(new THREE.HemisphereLight('#9fbdb5', '#0b1211', 0.12));
  const glow = new THREE.PointLight(ROOM_COLORS.alert, 0, 1.6, 2);
  scene.add(glow);

  const camera = new THREE.PerspectiveCamera(26, 1, 0.05, 60);
  renderPass.scene = scene;
  renderPass.camera = camera;
  const ao = new GTAOPass(scene, camera, 1, 1);
  ao.updateGtaoMaterial({ radius: 0.45, distanceExponent: 1.4, thickness: 1.2, scale: 1.0, samples: 12 });
  ao.blendIntensity = 1.0;
  composer.addPass(ao);
  composer.addPass(new OutputPass());
  const VIDEO_LAYER = 1;
  const parts = buildRoom(scene);
  scene.updateMatrixWorld(true);
  // the left surgical light, turned down, on the operative field: the one shadow caster
  const surgical = new THREE.SpotLight('#fff3df', 30, 6, 0.2, 0.55, 1.5);
  surgical.position.copy(parts.spots.lampLeft).add(new THREE.Vector3(0, -0.08, 0));
  surgical.target.position.copy(parts.spots.abdomen);
  surgical.castShadow = true;
  surgical.shadow.mapSize.set(1024, 1024);
  surgical.shadow.camera.near = 0.4;
  surgical.shadow.camera.far = 5;
  surgical.shadow.bias = -0.0004;
  surgical.shadow.normalBias = 0.02;
  surgical.shadow.radius = 4;
  scene.add(surgical, surgical.target);
  // the dimmed ceiling panels: one soft light from above that grounds everything
  // standing on the floor in its own shadow
  const ceilingLight = new THREE.DirectionalLight('#e3efec', 0.5);
  ceilingLight.position.set(0.6, 3.0, 0.9);
  ceilingLight.target.position.set(0, 0, -0.6);
  ceilingLight.castShadow = true;
  ceilingLight.shadow.mapSize.set(2048, 2048);
  Object.assign(ceilingLight.shadow.camera, { left: -3.2, right: 3.2, top: 2.6, bottom: -2.6, near: 0.5, far: 6 });
  ceilingLight.shadow.bias = -0.0006;
  ceilingLight.shadow.normalBias = 0.03;
  ceilingLight.shadow.radius = 3;
  scene.add(ceilingLight, ceilingLight.target);
  // the screens' spill: a soft light in front of each lit screen
  // (aimed low, below the screens' centres, so the blob perched on monitor A keeps
  // its own colour)
  const spills = {};
  for (const [k, color, power] of [['A', '#e6f4ff', 0.9], ['B', '#cdeee5', 0.6], ['C', '#cdeee5', 0.6]]) {
    const m = parts.screens[k];
    const spill = new THREE.PointLight(color, power, 2.6, 1.8);
    spill.position.copy(m.localToWorld(new THREE.Vector3(0, -0.3, 0.5)));
    scene.add(spill);
    spills[k] = spill;
  }
  glow.position.copy(parts.beacon.group.position).add(new THREE.Vector3(0, 0.1, 0.3));

  // A DOM page laid on a screen plane: authored at its own pixel size, scaled to
  // the plane's width, a hair in front of it.
  const pageOn = (mesh, el, authoredWidth) => {
    const o = new CSS3DObject(el);
    el.style.pointerEvents = 'none';
    const s = mesh.geometry.parameters.width / authoredWidth;
    o.scale.set(s, s, s);
    mesh.updateMatrixWorld(true);
    mesh.getWorldPosition(o.position);
    mesh.getWorldQuaternion(o.quaternion);
    o.position.add(new THREE.Vector3(0, 0, 0.002).applyQuaternion(o.quaternion));
    scene.add(o);
    return o;
  };
  // monitor B: the tools page (presenter) or the engineer's page (engineer), one shown
  const objTools = pageOn(parts.screens.B, pages.tools, 600);
  const objEng = pageOn(parts.screens.B, pages.engineer, 600);
  // monitor C: the model's reading; on a phone its generic page instead (setCompact)
  const objBoard = pageOn(parts.screens.C, pages.board, 880);
  const standIn = standInScreen();
  const showPages = () => {
    objTools.visible = compact || view !== 'engineer';
    objEng.visible = !compact && view === 'engineer';
  };
  // the 1 fps inset sits on monitor A's lower-left corner
  const inset = new CSS3DObject(pages.inset);
  {
    const A = parts.screens.A;
    const s = 0.24 / 300;
    inset.scale.set(s, s, s);
    A.getWorldQuaternion(inset.quaternion);
    const local = new THREE.Vector3(-0.56 + 0.135, -0.315 + 0.105, 0.003);
    inset.position.copy(A.localToWorld(local));
    scene.add(inset);
  }

  // the video on monitor A, or the 1 fps frames when the source serves no video
  const screenA = parts.screens.A.material;
  // the video on its own layer, drawn after the room's passes, over them: facing the
  // room nothing stands in front of monitor A; turned, the room's depth is laid down for
  // it first (`depthUnderVideo`), so what stands in front hides it
  parts.screens.A.layers.set(VIDEO_LAYER);
  let texture = null;
  // monitor A lights the room with the video's colour; the tower's lights blink (life.js)
  const life = roomLife({ parts, spillA: spills.A, screenA, reducedMotion });
  const setSource = (el) => {
    texture?.dispose();
    texture = el instanceof HTMLVideoElement ? new THREE.VideoTexture(el) : new THREE.Texture(el);
    texture.colorSpace = THREE.SRGBColorSpace;
    if (!(el instanceof HTMLVideoElement)) {
      const update = () => { texture.needsUpdate = true; invalidate(); };
      el.addEventListener('load', update);
      if (el.complete && el.naturalWidth) update();
    }
    screenA.map = texture;
    screenA.color.set('#ffffff');
    screenA.needsUpdate = true;
    invalidate();
  };

  // framing: fit the view's screens into the band between the top bar and the HUD
  let size = { w: 1, h: 1 };
  let view = 'presenter';
  let compact = false;
  showPages();
  // a screen's corners, or its bezel's with `pad` (m) all round
  const corners = (mesh, pad = 0) => {
    const { width, height } = mesh.geometry.parameters;
    return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([x, y]) => mesh.localToWorld(new THREE.Vector3((x * (width + 2 * pad)) / 2, (y * (height + 2 * pad)) / 2, 0)));
  };
  const poseFor = (v) => {
    const phone = v === 'compact' || v === 'compactWide';
    // on a phone the monitors are framed with their bezels and the blob on its perch
    const pts = VIEW_SCREENS[v].flatMap((k) => corners(parts.screens[k], phone ? 0.04 : 0));
    if (v === 'presenter') pts.push(parts.spots.perch.clone().add(new THREE.Vector3(0, 0.14, 0)), parts.spots.beaconTop.clone(), ...parts.table);
    if (v === 'engineer') pts.push(parts.spots.beaconTop.clone());
    if (phone) pts.push(parts.spots.perch.clone().add(new THREE.Vector3(0, 0.17, 0)));
    if (v === 'compactWide') pts.push(parts.spots.beaconTop.clone().add(new THREE.Vector3(0, 0.03, 0)));
    const center = new THREE.Box3().setFromPoints(pts).getCenter(new THREE.Vector3());
    const dir = VIEW_DIR[v];
    const { top, bottom } = insets();
    const availW = size.w * 0.94;
    const availH = Math.max(80, (size.h - top - bottom) * 0.95);
    const cam = camera.clone();
    cam.aspect = size.w / size.h;
    cam.updateProjectionMatrix();
    const measure = (d) => {
      cam.position.copy(center).addScaledVector(dir, -d);
      cam.lookAt(center);
      cam.updateMatrixWorld(true);
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      for (const p of pts) {
        const q = p.clone().project(cam);
        const x = ((q.x + 1) / 2) * size.w, y = ((1 - q.y) / 2) * size.h;
        x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
      }
      return { bw: x1 - x0, bh: y1 - y0, cy: (y0 + y1) / 2 };
    };
    let lo = 0.4, hi = 30;
    for (let i = 0; i < 32; i++) {
      const mid = (lo + hi) / 2;
      const m = measure(mid);
      if (m.bw <= availW && m.bh <= availH) hi = mid; else lo = mid;
    }
    const m = measure(hi);
    const want = top + (size.h - top - bottom) / 2;
    const perPx = (2 * hi * Math.tan(THREE.MathUtils.degToRad(cam.fov / 2))) / size.h;
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion);
    const shift = up.multiplyScalar(-(m.cy - want) * perPx);
    return { pos: cam.position.clone().add(shift), target: center.clone().add(shift) };
  };

  // Turning the room (the owner, 2026-11-06): a drag across the stage swings the camera
  // round the vertical axis through the point the view is framed on, and nothing else
  // (no tilt, no zoom, no pan). It is held within YAW_MAX either way, so the camera
  // stays inside the room and the screens stay readable; past the limit the drag gives
  // a little and springs back when let go. A double click faces the room again, and so
  // does a change of view (the view buttons frame their screens head-on).
  const YAW_MAX = THREE.MathUtils.degToRad(40);
  const GIVE = THREE.MathUtils.degToRad(6);
  const UP = new THREE.Vector3(0, 1, 0);
  const limit = (y) => THREE.MathUtils.clamp(y, -YAW_MAX, YAW_MAX);
  const give = (y) => {
    const over = Math.abs(y) - YAW_MAX;
    return over <= 0 ? y : Math.sign(y) * (YAW_MAX + GIVE * (1 - Math.exp(-over / GIVE)));
  };
  let yaw = 0, yawTo = 0, drag = null, travelled = 0;
  stage.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || !e.isPrimary) return;
    drag = { id: e.pointerId, x: e.clientX, from: yawTo, far: 0 };
    stage.setPointerCapture(e.pointerId);
    stage.classList.add('turning');
    e.preventDefault();
  });
  stage.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    drag.far = Math.max(drag.far, Math.abs(e.clientX - drag.x));
    // half the stage's width swings the whole range; the room follows the hand
    yawTo = give(drag.from - ((e.clientX - drag.x) * 4 * YAW_MAX) / Math.max(320, size.w));
    ask();
  });
  const release = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    travelled = drag.far;
    drag = null;
    yawTo = limit(yawTo);
    stage.classList.remove('turning');
    ask();
  };
  stage.addEventListener('pointerup', release);
  stage.addEventListener('pointercancel', release);
  // (two quick drags are not a double click)
  stage.addEventListener('dblclick', () => { if (travelled < 6) { yawTo = 0; ask(); } });

  // Turned, things in the room come between the camera and the screens (to the left, the
  // IV pole and its bags pass in front of monitor A from about 15°). The video is drawn
  // after the room's passes and over them, so first the room's depth is laid down, only
  // inside monitor A's box on the screen, and the video then hides where something
  // stands in front of it; facing the room nothing does, and that pass is skipped. The
  // "model saw" inset is a page laid in the room (CSS3D), drawn over the whole room
  // whatever stands before it, so it steps out of sight while any ray from the camera to
  // it meets something on the way, and comes back once the way is clear.
  const depthOnly = new THREE.MeshBasicMaterial({ colorWrite: false });
  const monitorA = parts.screens.A.parent;
  scene.traverse((o) => { if (o.isMesh && !o.geometry.boundingBox) o.geometry.computeBoundingBox(); });
  const shown = (o) => { for (; o; o = o.parent) if (!o.visible) return false; return true; };
  const ray = new THREE.Raycaster();
  const blocked = (obj, w, h) => {
    obj.updateMatrixWorld();
    const p = new THREE.Vector3(), dir = new THREE.Vector3();
    for (let i = 0; i < 7; i++) {
      for (let j = 0; j < 5; j++) {
        p.set((i / 6 - 0.5) * w * 0.96, (j / 4 - 0.5) * h * 0.96, 0).applyMatrix4(obj.matrixWorld);
        dir.copy(p).sub(camera.position);
        const far = dir.length() - 0.012;
        ray.set(camera.position, dir.normalize());
        ray.far = far;
        const hit = ray.intersectObject(scene, true).find((x) => shown(x.object) && (x.object.material?.opacity ?? 1) > 0.05);
        if (hit) return true;
      }
    }
    return false;
  };
  let insetHidden = false;
  const hideInset = (on) => { if (on !== insetHidden) { insetHidden = on; pages.inset.style.opacity = on ? '0' : ''; } };
  const depthUnderVideo = () => {
    const r = screenRect('A'), s = stage.getBoundingClientRect();
    const x0 = Math.max(0, Math.floor(r.left - s.left) - 2), x1 = Math.min(size.w, Math.ceil(r.right - s.left) + 2);
    const y0 = Math.max(0, Math.floor(size.h - (r.bottom - s.top)) - 2), y1 = Math.min(size.h, Math.ceil(size.h - (r.top - s.top)) + 2);
    if (x1 <= x0 || y1 <= y0) return;
    const shadows = renderer.shadowMap.autoUpdate;
    renderer.shadowMap.autoUpdate = false; // the shadows are the room pass's, not redone here
    renderer.setScissor(x0, y0, x1 - x0, y1 - y0);
    renderer.setScissorTest(true);
    // monitor A's own body is never in front of its screen, and its face lies 1 mm
    // behind it, inside a coarse depth buffer's step (a software renderer's): left out
    monitorA.visible = false;
    scene.overrideMaterial = depthOnly;
    renderer.render(scene, camera);
    scene.overrideMaterial = null;
    monitorA.visible = true;
    renderer.setScissorTest(false);
    renderer.shadowMap.autoUpdate = shadows;
  };

  let from = null, to = null, startedAt = 0;
  const current = { pos: new THREE.Vector3(0, 1.6, 4), target: new THREE.Vector3(0, 1.7, -1) };
  const goTo = (animate) => {
    to = poseFor(compact ? (size.w / size.h >= WIDE ? 'compactWide' : 'compact') : view);
    if (!animate || reducedMotion()) {
      current.pos.copy(to.pos); current.target.copy(to.target); from = null;
    } else {
      from = { pos: current.pos.clone(), target: current.target.clone() };
      startedAt = performance.now();
    }
    invalidate();
  };

  const resize = () => {
    const r = stage.getBoundingClientRect();
    size = { w: Math.max(1, r.width), h: Math.max(1, r.height) };
    renderer.setSize(size.w, size.h, false);
    composer.setPixelRatio(renderer.getPixelRatio());
    composer.setSize(size.w, size.h);
    css.setSize(size.w, size.h);
    camera.aspect = size.w / size.h;
    camera.updateProjectionMatrix();
    goTo(false);
  };
  new ResizeObserver(resize).observe(stage);
  resize();

  // the alarm: the beacon glows red while an alert holds, and throbs slowly while the
  // video plays (slow enough to read the same drawn a few times a second)
  let alerting = false;
  let slow = 16;
  let bornAt = performance.now();
  const draw = (now) => {
    for (const f of beforeHooks) f(now);
    if (from) {
      const k = easeOutExpo((now - startedAt) / 1100);
      current.pos.lerpVectors(from.pos, to.pos, k);
      current.target.lerpVectors(from.target, to.target, k);
      if (k >= 1) from = null;
    }
    // the turn eases after the hand (about 90 ms), at once under "reduce motion"
    const ease = reducedMotion() ? 1 : 1 - Math.exp(-Math.min(200, now - lastDraw) / 90);
    yaw += (yawTo - yaw) * ease;
    if (Math.abs(yawTo - yaw) < 1e-4) yaw = yawTo;
    camera.position.copy(current.pos).sub(current.target).applyAxisAngle(UP, yaw).add(current.target);
    camera.lookAt(current.target);
    const pulse = alerting ? (reducedMotion() || !playing() ? 1 : 0.7 + 0.3 * Math.sin(now / 320)) : 0;
    parts.beacon.material.emissiveIntensity = 1.4 * pulse;
    parts.beacon.material.color.set(alerting ? ROOM_COLORS.alert : ROOM_COLORS.beaconIdle);
    glow.intensity = 1.2 * pulse;
    life(now);
    for (const f of frameHooks) f(now);
    composer.render();
    // (a colour background forces a clear, which would wipe the room: none for this draw)
    const bg = scene.background;
    scene.background = null;
    renderer.autoClear = false;
    // (the last pass's full-screen quad leaves its own depth everywhere)
    renderer.clearDepth();
    if (yaw !== 0) depthUnderVideo();
    camera.layers.set(VIDEO_LAYER);
    renderer.render(scene, camera);
    camera.layers.set(0);
    renderer.autoClear = true;
    scene.background = bg;
    if (yaw !== 0 && !pages.inset.hidden) hideInset(blocked(inset, pages.inset.offsetWidth, pages.inset.offsetHeight));
    else hideInset(false);
    css.render(scene, camera);
    // too slow for the occlusion (a weak GPU): drop it, keep the turn smooth (timed over
    // frames drawn back to back, the only time the rate shows)
    if (now - lastDraw < 100) {
      slow = slow * 0.97 + (now - lastDraw) * 0.03;
      if (ao.enabled && slow > 48 && now - bornAt > 4000) ao.enabled = false;
    }
    lastDraw = now;
    dirty = false; // (what the hooks above changed is in this frame)
  };

  // a screen's box on the page, in CSS pixels (y down), from its projected corners
  const screenRect = (k) => {
    const mesh = parts.screens[k];
    if (!mesh) return null;
    const r = stage.getBoundingClientRect();
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const p of corners(mesh)) {
      const q = p.clone().project(camera);
      const x = r.left + ((q.x + 1) / 2) * size.w, y = r.top + ((1 - q.y) / 2) * size.h;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
    return { left: x0, right: x1, top: y0, bottom: y1, width: x1 - x0, height: y1 - y0 };
  };

  return {
    scene, camera, THREE,
    spot: (name) => parts.spots[name]?.clone() ?? null,
    // a world point's position on the page, in CSS pixels (y down)
    project(v) {
      const r = stage.getBoundingClientRect();
      const q = v.clone().project(camera);
      return { x: r.left + ((q.x + 1) / 2) * size.w, y: r.top + ((1 - q.y) / 2) * size.h };
    },
    screenRect,
    setSource,
    setClock: (text, colon) => parts.setClock(text, colon),
    // monitor B shows the tools in the presenter view and the engineer's page in the
    // engineer view
    setView(v) { view = v; showPages(); if (!drag) yawTo = 0; goTo(true); },
    // Narrow windows: the room frames monitor A (on a landscape phone all three), and
    // the reading and the engineer's page leave the room for flat panels under it
    // (removing a CSS3D object takes its element out of the 3D layer; adding it back
    // returns it); the tools stay on monitor B, and the dashboard has its own card of
    // them (main.js). On a phone (the owner, 2026-11-07) the reading's monitor shows a
    // generic page instead (its stand-in, displays.js).
    setCompact(c) {
      if (c === compact) return;
      compact = c;
      const screen = parts.screens.C.material;
      screen.map = c ? standIn.tex : null;
      screen.color.set(c ? '#ffffff' : '#071a17');
      screen.needsUpdate = true;
      standIn.setAlert(c && alerting);
      showPages();
      for (const [o, el] of [[objBoard, pages.board], [objEng, pages.engineer]]) {
        if (c) {
          scene.remove(o);
          el.style.transform = '';
          el.style.display = ''; // (the 3D layer hides a page it does not show)
          el.style.position = 'relative';
          flat.appendChild(el);
        } else {
          el.style.position = 'absolute';
          scene.add(o);
        }
      }
      goTo(false);
    },
    setAlert(on) { if (on !== alerting) { alerting = on; standIn.setAlert(compact && on); invalidate(); } },
    get alerting() { return alerting; },
    get view() { return view; },
    // a phone's layout: the reading under the room, its stand-in on monitor C
    get compact() { return compact; },
    // the turn, in radians (+ the camera to the right), within ±YAW_MAX
    get yaw() { return yaw; },
    set yaw(y) { yaw = yawTo = limit(y); invalidate(); },
    yawMax: YAW_MAX,
    // the turn or the camera still easing toward where it is going
    get moving() { return yaw !== yawTo || from !== null; },
    // just before each frame is drawn: the screen's own update (main.js), then the
    // animations (layer.js)
    beforeFrame(f) { beforeHooks.push(f); },
    onFrame(f) { frameHooks.push(f); },
    // something on the page changed: draw it (and let the eased lights settle)
    invalidate,
    // a short animation: full rate for `ms`
    wake,
    // false for a recording: every animation frame drawn
    get frugal() { return frugal; },
    set frugal(on) { frugal = on; invalidate(); },
    reframe: () => goTo(false),
    // the occlusion pass, on or off (it drops itself on a machine that cannot keep up)
    get occlusion() { return ao.enabled; },
    set occlusion(on) { ao.enabled = on; bornAt = performance.now(); slow = 16; invalidate(); },
  };
}

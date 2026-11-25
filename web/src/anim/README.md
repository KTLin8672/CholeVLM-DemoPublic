# Animations

Every `*.js` file in this folder is loaded on its own; drop a file in and it runs
(with `npm run dev`, it hot-reloads). A file exports one function:

```js
import * as THREE from 'three';

export function setup(scene, ctx) {
  // build meshes, add them to `scene`
  return {
    onDecision(d, prev) {}, // each new decision on screen
    onEvent(e) {},          // each newly raised non-standard event
    tick(now, dt) {},       // every frame drawn: now in ms, dt in s (see ctx.wake)
  };
}
```

**Two places to draw.** *The overlay*: one transparent canvas over the whole window (clicks pass
through it, and it sits beneath the HUD and the labels). Its camera is orthographic in pixels:
origin at the window's bottom-left, y up, z toward you (keep z between -1000 and 1000). An
ambient and a directional light are in it. *The room*: the virtual operating room itself,
`ctx.room.scene`, in metres, y up, lit dimly for laparoscopy (the monitors are the light).
Anything you add there sits in the room, and the monitors' pages are always drawn over it, so
it can never cover a value. `setup(scene, …)` receives the overlay's scene.

**`ctx`**
- `ctx.anchor(name)` gives a box in overlay pixels: `{x, y, w, h, left, right, top, bottom}`
  (x, y the centre). Names:
  - `video` (the endoscope monitor, A), `tools-page` (monitor B in the presenter view),
    `engineer` (monitor B in the engineer view), `readings` (the reading, monitor C), `room`;
  - on monitor C, the reading: `phase`, `tools`, `cvs` (the critical view's rows; no
    criterion has a box), `flags`, `hint` (engineer view), `why`
    (presenter view) on the left, `ahead` on the right;
  - in the HUD: `controls`, `timeline`, `events`, `ask`;
  - on monitor B in the engineer view: `model`, `reply`, `delay`, `step`, `calls`,
    `cvs-served`.

  A hidden panel has a zero box. Call it in `tick`, since the camera and the window move.
- `ctx.room`: `scene`, `camera`, `spot(name)` (a world point: `perch` on top of the endoscope
  monitor, `mayo` the instrument tray, `clock` the wall clock, `beaconTop` the alarm beacon),
  `toOverlay(v)` (a world point in overlay pixels).
- `ctx.palette`: `lavender pink sky mint orchid lime periwinkle peach` (decoration only),
  `butter` (warnings) and `alert` (red), which mean severity and nothing else, `drape`, `slate`, `text`.
- `ctx.phaseColor(phase)`: the phase's pastel (for decoration); `ctx.phaseIndex(phase)`: its
  place in the usual order (0–6, -1 unknown).
- `ctx.reducedMotion`: true when the viewer asked the system to reduce motion; keep still then.
- `ctx.wake(ms)`: the room is drawn frugally: every 250 ms while the video
  plays, only on a change while it is paused, never while the page is hidden; so `tick` runs
  only that often. An animation that needs smooth motion calls `ctx.wake(ms)` when it starts,
  for its length, and gets every frame for that long (the hop, the sweep, the sparks do).
- `ctx.size`: `{w, h}` of the window; `ctx.camera` (the overlay's), `ctx.THREE`.

**`d`, a decision**: one decision line of the API of the [evaluation and serving repository](https://github.com/KTLin8672/CholeVLM-EvalTool) (`docs/api.md` there, pinned in
`configs/api.yaml`, today 1.13; the mock speaks the same shape):
- `d.state`: the decision's JSON as the server completes it: `phase`, `phase_conf`,
  `phase_remaining`, `tools_now`, `tools_now_conf`, `next_tool` (`{tool: 'none'}` when none),
  `risk_flags` (a value may be `null`: unknown), `risk_flags_shown`, `blood`,
  `next_step` (`{verb: 'continue'}` carries no target), `rationale`. The model's own CVS is
  not passed to the page.
- `d.cvs_served`, in a run that has it: per criterion (`two_structures`, `triangle_cleared`,
  `cystic_plate`) its `value` (0, 1 or `null`) and `source`; a screening signal, never a
  criterion met.
- What changed since the last decision on screen: `d.phaseChanged`, `d.phaseBackward` (the
  new phase comes earlier in the usual order: an anomaly, not progress), `d.cvsNew` (always empty:
  no criterion is marked as met), `d.toolsNew` (tools just in view), `d.eventsNew` (events just raised).
- `d.jumped`: the clock was moved (a seek, a run switch), so these changes did not just
  happen; celebrate nothing then. `onEvent` is not called on a jump.
- `d.events` (each `visible`), `d.memory` (the running memory, cut to what the screen
  draws: `current_phase`, `phase_timeline`, `flags`),
  `d.outlook` (`next_phase`, `tools_300s` from the priors), `d.delay`, `d.t_frame`,
  `d.compute_s`, `d.fallback`.

**`e`, an event**: `id`, `kind`, `severity` (`alert`, `warn`, `info`), `field`, `value`,
`wording`, `t_raised`, `t_cleared`.

**Rules.** An animation only decorates: it never hides or covers a lane's value, the
event box or the synthetic-footage label, and it never invents data. Red is for alerts,
butter for warnings. Nothing fires on a jump, and nothing moves under `ctx.reducedMotion`.
An error in one file is logged to the console and the others keep running.

Examples: `bounce-on-phase.js` (a blob in the room, perched on the endoscope monitor, that hops
when the procedure moves on, takes the phase's colour, shivers on an alert, and glances at
monitor B when the reading changes), `cvs-sparkles.js` (an overlay ring pulse with a few
sparks on the box of a criterion just achieved, fanning away from its label; dormant) and
`alarm-sweep.js` (the beacon's red beam turning across the room for four seconds when an
alert is raised; a light in the room, built once at setup and dark at rest, since adding
a light later recompiles every material).

The room's own life (monitor A's spill in the video's colour, the tower's status lights)
is `room/life.js`, not an animation here: it is part of the room.

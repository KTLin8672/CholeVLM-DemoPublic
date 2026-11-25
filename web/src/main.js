// The screen: a virtual operating room (the owner's pick, 2026-11-05). The video plays
// on the endoscope monitor and the decision log follows it by video time (the video
// by byte ranges). Monitor B shows the
// reading, the HUD the run, monitor C the engineer's figures. Data comes only from
// the demo server's /api: today the mock, later chole-eval.

import '@fontsource/atkinson-hyperlegible-next/400.css';
import '@fontsource/atkinson-hyperlegible-next/600.css';
import '@fontsource/atkinson-hyperlegible-next/700.css';
import '@fontsource/atkinson-hyperlegible-next/800.css';
import '@fontsource/atkinson-hyperlegible-next/400-italic.css';
import '@fontsource/atkinson-hyperlegible-mono/400.css';
import '@fontsource/atkinson-hyperlegible-mono/600.css';
import './style.css';
import { startLayer } from './layer.js';
import * as P from './panels.js';
import { createRoom } from './room/room.js';

const $ = (id) => document.getElementById(id);
const ENDED = -3; // the shown index past the rollout's last decision
const LEAD_S = 3; // a stretch run opens this long before its first decision
// step 2, reconnects: the pause before each new try, growing, in seconds
const BACKOFF_S = [1, 2, 4, 8, 15, 30];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
// phones, and narrow or short windows: one column, the reading a dashboard under the
// room (style.css; the same query there)
const narrow = window.matchMedia('(max-width: 900px), (max-height: 500px)');

// Video time in seconds. With a <video> attached the video is the clock; without
// one (a source with no video) the clock runs on its own over the 1 fps frames.
// `changed` is called on a play, a pause, a seek or a new speed (the room draws then).
class Clock {
  constructor() {
    this.t = 0; this.speed = 1; this.running = false; this.duration = 0;
    this.last = performance.now(); this.video = null;
    this.offset = 0; // the video second the file's time 0 stands for (the header's video.t0)
    this.changed = () => {};
  }
  attach(video) { this.video = video; if (video) video.playbackRate = this.speed; }
  get playing() { return this.video ? !this.video.paused && !this.video.ended : this.running; }
  now() {
    const n = performance.now();
    if (this.video) {
      this.t = Math.min(this.duration, this.video.currentTime + this.offset);
    } else if (this.running) {
      this.t = Math.min(this.duration, this.t + ((n - this.last) / 1000) * this.speed);
      if (this.t >= this.duration) this.running = false;
    }
    this.last = n;
    return this.t;
  }
  play() {
    if (this.t >= this.duration) this.seek(0);
    if (this.video) this.video.play().catch((err) => console.warn('video play refused', err));
    else { this.last = performance.now(); this.running = true; }
    this.changed();
  }
  pause() { this.now(); if (this.video) this.video.pause(); else this.running = false; this.changed(); }
  seek(t) {
    this.t = Math.max(0, Math.min(this.duration, t));
    if (this.video) this.video.currentTime = Math.max(0, this.t - this.offset);
    this.last = performance.now();
    this.changed();
  }
  setSpeed(s) { this.speed = s; if (this.video) this.video.playbackRate = s; this.changed(); }
}

function framePlayer(img) {
  let video = null, shown = -1;
  const cache = new Map();
  const url = (f) => `/api/frames/${encodeURIComponent(video)}/${f}.jpg?variant=current`;
  return {
    reset(v) { video = v; shown = -1; cache.clear(); },
    show(t, duration) {
      const f = Math.max(0, Math.min(duration - 1, Math.floor(t)));
      if (f === shown) return;
      shown = f;
      img.src = url(f);
      for (let k = 1; k <= 4; k++) {
        if (f + k < duration && !cache.has(f + k)) { const im = new Image(); im.src = url(f + k); cache.set(f + k, im); }
      }
      if (cache.size > 64) for (const key of [...cache.keys()].slice(0, 32)) cache.delete(key);
    },
  };
}

// When each decision is on screen. An offline run shows a
// decision at its frame time (the waiting gone) or, simulating live, when live
// would have it: after encode and compute, with the ticks live would drop skipped.
// A live run is shown as it happened: after encode and compute; its drops are in the log.
function schedule(decisions, mode, simulateLive) {
  const done = (d) => d.t_frame + d.encode_s + d.compute_s;
  if (mode === 'live') return decisions.map((d, i) => ({ at: done(d), i }));
  if (!simulateLive) return decisions.map((d, i) => ({ at: d.t_frame, i }));
  const out = [];
  let busyUntil = -Infinity;
  decisions.forEach((d, i) => {
    if (d.t_frame < busyUntil) return;
    busyUntil = done(d);
    out.push({ at: busyUntil, i });
  });
  return out;
}

function lastAtOrBefore(sched, t) {
  let lo = 0, hi = sched.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (sched[mid].at <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans < 0 ? -1 : sched[ans].i;
}

// What changed since the decision shown before. `jumped`: the clock was moved (a
// seek, a run switch), so the change is not something that just happened.
function enrich(d, prev, jumped) {
  const visible = d.events.filter((e) => e.visible && e.t_cleared == null);
  const backward = (a, b) => P.phaseIndex(a) >= 0 && P.phaseIndex(b) >= 0 && P.phaseIndex(b) < P.phaseIndex(a);
  if (!prev) return { ...d, jumped, phaseChanged: true, phaseBackward: false, cvsNew: [], toolsNew: d.state.tools_now ?? [], eventsNew: visible };
  const seen = new Set(prev.events.map((e) => e.id));
  const was = prev.state.tools_now ?? [];
  return {
    ...d,
    jumped,
    phaseChanged: d.state.phase !== prev.state.phase,
    phaseBackward: backward(prev.state.phase, d.state.phase),
    cvsNew: [], // no CVS criterion is marked as met
    toolsNew: (d.state.tools_now ?? []).filter((t) => !was.includes(t)),
    eventsNew: visible.filter((e) => !seen.has(e.id)),
  };
}

async function boot() {
  const clock = new Clock();
  const video = $('video');
  const frame = $('frame');
  const player = framePlayer(frame);

  const room = createRoom({
    stage: $('stage'),
    canvas: $('room'),
    cssRoot: $('css3d'),
    // monitor B: the tools (presenter) or the engineer's page; monitor C: the reading
    pages: { tools: $('screen-tools'), engineer: $('screen-c'), board: $('screen-b'), inset: $('model-frame') },
    flat: $('flat'),
    insets: () => (narrow.matches ? { top: 0, bottom: 0 } : { top: $('topbar').offsetHeight, bottom: $('hud').offsetHeight }),
    reducedMotion: () => motion.matches,
    playing: () => clock.playing,
  });
  // the room is drawn when something changes (room.js): the clock's
  // moves and the video's own events are such changes
  clock.changed = room.invalidate;
  for (const ev of ['playing', 'pause', 'seeked', 'ended', 'loadeddata', 'ratechange']) video.addEventListener(ev, room.invalidate);
  // On a phone, play, the clock and the timeline sit in a bar at the screen's foot, in
  // thumb reach (the owner, 2026-11-07); on a wider window they go back to the HUD.
  const transport = ['play', 'clock', 'timeline'].map((id) => {
    const el = $(id);
    const mark = document.createComment(id);
    el.before(mark);
    return [el, mark];
  });
  const dock = (on) => { for (const [el, mark] of transport) if (on) $('bar').append(el); else mark.after(el); };
  const fit = () => { room.setCompact(narrow.matches); dock(narrow.matches); };
  narrow.addEventListener('change', fit);
  fit();
  new ResizeObserver(() => room.reframe()).observe($('hud'));
  const layer = startLayer($('fx'), room);

  // Presenter (A the video, B the tools, C the reading) or engineer (B the engineer's
  // page): the camera moves.
  const setView = (v) => {
    document.body.classList.toggle('view-engineer', v === 'engineer');
    document.body.classList.toggle('view-presenter', v !== 'engineer');
    for (const b of document.querySelectorAll('#view-switch button')) b.setAttribute('aria-pressed', String(b.dataset.view === v));
    room.setView(v);
    const url = new URL(location.href);
    if (v === 'engineer') url.searchParams.set('view', 'engineer'); else url.searchParams.delete('view');
    history.replaceState(null, '', url);
  };
  for (const b of document.querySelectorAll('#view-switch button')) b.addEventListener('click', () => setView(b.dataset.view));
  setView(new URLSearchParams(location.search).get('view') === 'engineer' ? 'engineer' : 'presenter');

  // The owner's sign-in (the owner, 2026-11-07): an Owner tab beside the views asks for
  // his password (no user name, no other address); signed in, Ask and the videos not
  // shown publicly are on, and the tab signs him out again. Asking the model is his
  // alone, so a visitor sees no Ask box.
  const me = await fetch('/api/me').then((r) => r.json()).catch(() => ({ owner: false }));
  let owner = !!me.owner;
  let held = null; // a question waiting for the sign-in (the cookie ran out meanwhile)
  const askForm = $('ask-form');
  const askInput = $('ask-input');
  const tab = $('owner-tab');
  const panel = $('owner-panel');
  const pwInput = $('owner-input');
  const pwButton = $('owner-submit');
  const say = (text) => { $('owner-msg').textContent = text; };
  const showOwner = () => {
    tab.classList.toggle('on', owner);
    tab.title = owner ? 'signed in as the owner' : 'the owner’s sign-in';
    tab.setAttribute('aria-label', owner ? 'Owner, signed in' : 'Owner');
    askForm.hidden = !owner;
    $('owner-title').textContent = owner ? 'Signed in as the owner' : 'Owner sign-in';
    $('owner-note').textContent = owner
      ? 'Ask and the videos not shown publicly are on in this browser, for 30 days.'
      : 'Signing in turns on Ask and the videos not shown publicly.';
    $('owner-form').hidden = owner;
    $('owner-out').hidden = !owner;
  };
  const openPanel = (open, note = '') => {
    panel.hidden = !open;
    tab.setAttribute('aria-expanded', String(open));
    if (!open) return;
    say(note);
    pwInput.removeAttribute('aria-invalid');
    (owner ? $('owner-out') : pwInput).focus();
  };
  const putAway = () => {
    pwInput.value = '';
    held = null;
    openPanel(false);
  };
  const closePanel = () => { putAway(); tab.focus(); };
  showOwner();
  // the connection to the model's server, said in the top bar (step 2): nothing while all
  // is well and the run is finished; "following" while a run is written; amber when not
  const conn = (kind, text) => {
    const el = $('conn');
    el.hidden = !kind;
    el.className = kind ?? '';
    el.textContent = text ?? '';
  };
  // a request that tries again with a growing pause when the server does not answer
  const patient = async (url, say) => {
    for (let k = 0; ; k++) {
      try {
        const res = await fetch(url);
        if (res.status < 500 && res.status !== 429) return res;
      } catch { /* no answer: try again */ }
      const wait = BACKOFF_S[Math.min(k, BACKOFF_S.length - 1)];
      say(`No answer from the model server. Trying again in ${wait} s`);
      await sleep(wait * 1000);
    }
  };

  const runs = await (await patient('/api/videos', (m) => conn('warn', m))).json();
  conn(null);
  const sel = $('run');
  // two runs of one video (a stretch and the whole) are told apart by the run's stamp
  const twins = (r) => runs.filter((x) => x.video_id === r.video_id && x.mode === r.mode).length > 1;
  const stamp = (r) => (r.from_t != null ? `from ${P.mmss(r.from_t)}` : r.run.match(/(\d{8}T\d{4})\d*$/)?.[1] ?? 'whole');
  // a run still being written is followed, and says so
  const writing = (r) => (r.writing ? ` · ${r.mode === 'live' ? 'live now' : 'in progress'}` : '');
  const ood = (r) => (r.held_out ? ' · out of distribution' : '');
  const fillRuns = () => {
    sel.innerHTML = runs.map((r, i) => `<option value="${i}">${P.esc(r.video_id)} · ${P.esc(r.mode)}${twins(r) ? ` · ${P.esc(stamp(r))}` : ''}${ood(r)}${writing(r)}</option>`).join('');
  };
  fillRuns();
  // the owner's sign-in shows runs a visitor does not see (a held-out video), added at
  // the end; signing out takes them away again, and the first run plays if one was on
  const key = (r) => `${r.run}\n${r.video_id}`;
  const syncRuns = async () => {
    let all;
    try { all = await (await fetch('/api/videos')).json(); } catch { return; } // the list stays
    const on = runs[Number(sel.value)];
    const now = new Set(all.map(key));
    const had = new Set(runs.map(key));
    const kept = runs.filter((r) => now.has(key(r)));
    const added = all.filter((r) => !had.has(key(r)));
    if (kept.length === runs.length && !added.length) return;
    runs.splice(0, runs.length, ...kept, ...added);
    fillRuns();
    const i = on ? runs.findIndex((r) => key(r) === key(on)) : -1;
    if (i >= 0) sel.value = String(i);
    else if (runs.length) await load(0);
  };

  let R = null; // the loaded rollout, or the one being followed (R.following)
  let gen = 0; // the run on screen: an answer for one left behind is dropped
  let sock = null; // the follow socket
  let sched = [];
  let shown = -1;
  let lastClock = -1;
  let lastLoopT = 0;
  let lastSecond = -1;
  let useVideo = true;

  const reschedule = () => {
    sched = schedule(R.decisions, R.meta.mode, $('live-sim').checked);
    shown = -2; // redraw
    room.invalidate();
  };

  // The video when the source serves one; the 1 fps frames otherwise.
  const usePlayer = (withVideo) => {
    useVideo = withVideo;
    clock.attach(withVideo ? video : null);
    room.setSource(withVideo ? video : frame);
  };
  video.addEventListener('error', () => {
    if (!useVideo) return;
    console.warn('no video from the source: the 1 fps frames play instead');
    const t = clock.now();
    usePlayer(false);
    clock.seek(t);
  });

  // the player and the panels for a run's meta (a stored rollout's, or a followed one's)
  const setUp = (meta) => {
    clock.pause();
    clock.duration = meta.duration_s;
    clock.offset = meta.video?.t0 ?? 0;
    player.reset(meta.video_id);
    usePlayer(true);
    const src = `/api/video/${encodeURIComponent(meta.video_id)}`;
    if (!video.src.endsWith(src)) video.src = src;
    P.renderHeader(meta);
    $('live-sim-label').hidden = meta.mode === 'live' || R.following;
    $('ask-log').innerHTML = '';
    $('ask-panel').hidden = true;
  };

  const stopFollow = () => {
    if (!sock) return;
    const s = sock;
    sock = null;
    s.close();
  };

  const load = async (i) => {
    const r = runs[i];
    sel.value = String(i);
    const my = ++gen;
    stopFollow();
    conn(null);
    if (r.writing) return follow(r, my);
    const res = await patient(`/api/rollout/${encodeURIComponent(r.run)}/${encodeURIComponent(r.video_id)}`,
      (m) => my === gen && conn('warn', m));
    if (my !== gen) return;
    if (res.status === 409) { r.writing = true; return follow(r, my); } // it is being written after all
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail ?? body.error);
    conn(null);
    R = body;
    setUp(R.meta);
    // a run of a stretch (from_t) opens a few seconds before its first decision
    clock.seek(Math.max(0, (R.meta.first_decision_t ?? 0) - LEAD_S));
    reschedule();
  };

  // Step 2: a run still being written, followed through the demo server's socket
  // (follow.py): its lines so far, then each one as it is written. The socket comes
  // back on its own after a drop, from the last line held; the top bar says how it is.
  const FOLLOW_SAY = {
    connecting: ['warn', 'Connecting to the model server…'],
    reconnecting: ['warn', 'The model server is not answering. Reconnecting…'],
    unreadable: ['warn', 'This run speaks a newer API than this screen reads'],
  };
  const follow = (r, my) => {
    R = { meta: null, decisions: [], dropped: [], end: null, following: true, upstream: 'connecting', received: 0, placed: false, lastLineAt: 0 };
    sched = [];
    shown = -2;
    const say = () => {
      if (R.end) { conn(null); return; }
      const [kind, text] = FOLLOW_SAY[R.upstream] ?? ['live', R.meta?.mode === 'live' ? 'Following live' : 'Following as it is written'];
      conn(kind, text);
    };
    say();
    let tries = 0;
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${proto}//${location.host}/api/follow/${encodeURIComponent(r.run)}/${encodeURIComponent(r.video_id)}?after=${R.received}`);
      sock = ws;
      ws.onmessage = (ev) => {
        if (my !== gen) return;
        const m = JSON.parse(ev.data);
        if (m.type === 'meta' && !R.meta) {
          R.meta = m.meta;
          setUp(R.meta);
        } else if (m.type === 'line' && m.i === R.received) {
          tries = 0;
          R.received += 1;
          R.lastLineAt = performance.now();
          if (m.line.kind === 'decision') {
            R.decisions.push(m.line);
            R.meta.first_decision_t = Math.min(R.meta.first_decision_t ?? Infinity, m.line.t_frame);
            R.meta.last_decision_t = Math.max(R.meta.last_decision_t ?? -Infinity, m.line.t_frame);
            reschedule();
            if (R.held && clock.now() < R.meta.last_decision_t + R.meta.D) { R.held = false; clock.play(); }
          } else R.dropped.push(m.line);
        } else if (m.type === 'status') {
          R.upstream = m.upstream;
        } else if (m.type === 'end') {
          R.end = m.end;
          R.following = false;
        }
        say();
        room.invalidate();
      };
      ws.onclose = (ev) => {
        if (my !== gen || sock !== ws) return;
        sock = null;
        if (R.end || R.upstream === 'unreadable') return;
        // not being written any more (it finished meanwhile): it is a stored run now
        if (ev.code === 4404) { r.writing = false; load(runs.indexOf(r)); return; }
        const wait = BACKOFF_S[Math.min(tries++, BACKOFF_S.length - 1)];
        conn('warn', ev.code === 4429 ? `Too many open views from here. Trying again in ${wait} s` : `Connection lost. Reconnecting in ${wait} s`);
        setTimeout(() => { if (my === gen) connect(); }, wait * 1000);
      };
    };
    connect();
  };

  // a followed run takes its place once its stored lines are in: a live run at the
  // live edge (where its latest decision was shown), one in progress at its start
  let placeLater = 0;
  const place = () => {
    if (!R.following || R.placed || !R.decisions.length) return;
    // the stored lines still coming in: look again once they have paused (the room is
    // drawn only on a change, so the look is asked for, not left to the next frame)
    const quiet = 300 - (performance.now() - R.lastLineAt);
    if (quiet > 0) { clearTimeout(placeLater); placeLater = setTimeout(room.invalidate, quiet + 20); return; }
    R.placed = true;
    const last = R.decisions[R.decisions.length - 1];
    clock.seek(R.meta.mode === 'live'
      ? last.t_frame + last.encode_s + last.compute_s
      : Math.max(0, R.meta.first_decision_t - LEAD_S));
    clock.play();
  };

  const show = (i, jumped) => {
    if (i === shown) return;
    const prev = shown >= 0 ? R.decisions[shown] : null;
    shown = i;
    if (i === ENDED) {
      // past the rollout's last decision: say so, never hold a stale reading
      P.renderEnded(R.meta);
      P.renderToolsEnded(R.meta);
      $('model-frame').hidden = true;
      room.setAlert(false);
      $('screen-b').classList.remove('alerting');
      return;
    }
    if (i < 0) {
      P.renderWaiting(R.meta); P.renderToolsWaiting(); P.renderEvents(null); P.renderReplies([]); P.renderDelay(null, [], R.meta); P.renderStep(null); P.renderCalls(null); P.renderCvsServed(null, R.meta);
      $('model-frame').hidden = true;
      room.setAlert(false);
      $('screen-b').classList.remove('alerting');
      return;
    }
    const d = R.decisions[i];
    const upto = R.decisions.slice(0, i + 1);
    P.renderLanes(d, R.meta);
    P.renderTools(d, upto);
    P.renderEvents(d);
    P.renderReplies(upto.slice(-2));
    P.renderDelay(d, upto, R.meta);
    P.renderStep(d);
    P.renderCalls(d, upto);
    P.renderCvsServed(d, R.meta);
    // a reply that failed: every lane holds the previous state, and the reading says so
    $('screen-b').classList.toggle('fell-back', !!d.fallback);
    const alerting = P.alertActive(d);
    room.setAlert(alerting);
    $('screen-b').classList.toggle('alerting', alerting);
    $('model-frame-img').src = `/api/frames/${encodeURIComponent(R.meta.video_id)}/${Math.floor(d.t_frame)}.jpg?variant=video`;
    $('model-frame-note').innerHTML = `model saw <b>${P.mmss(d.t_frame)}</b>`;
    $('model-frame').hidden = false;
    const rich = enrich(d, prev, jumped);
    layer.decision(rich, prev);
    if (!jumped) for (const e of rich.eventsNew) layer.event(e);
  };

  // the screen's update, run just before each frame of the room (room.beforeFrame),
  // so the panels change as often as the room is drawn and no more
  const loop = () => {
    if (R?.following && !R.meta) return;
    if (R?.following) place();
    // a run in progress (not live) runs slower than its video: the video waits at the
    // last decision the model has made, and the screen says it is waiting
    if (R?.following && R.meta.mode !== 'live' && R.decisions.length) {
      const frontier = R.meta.last_decision_t + R.meta.D;
      if (clock.now() >= frontier && clock.playing) { clock.pause(); clock.seek(frontier); R.held = true; }
    }
    if (R) {
      const t = clock.now();
      const jumped = Math.abs(t - lastLoopT) > 1 || shown === -2;
      lastLoopT = t;
      if (!useVideo) player.show(t, R.meta.duration_s);
      let i = lastAtOrBefore(sched, t);
      const lastT = R.meta.last_decision_t;
      if (R.end && !R.following && lastT != null && i === R.decisions.length - 1 && t > lastT + R.meta.D) i = ENDED;
      show(i, jumped);
      // the times ahead count down with the video between decisions
      P.tickEta(t);
      const held = R.following && R.held && !clock.playing;
      if (shown === ENDED) P.renderEndedStamp(R.meta);
      else if (held) P.renderComputingStamp(R.meta);
      else P.renderStamp(shown >= 0 ? R.decisions[shown] : null, t, R.meta);
      if (shown >= 0) P.renderFrozen(R.decisions[shown], t, R.meta, held);
      if (Math.abs(t - lastClock) > 0.1 || jumped) {
        lastClock = t;
        $('clock').textContent = `${P.mmss(t)} / ${P.mmss(R.meta.duration_s)}`;
        const last = shown === ENDED ? R.decisions.length - 1 : shown;
        P.renderTimeline(last >= 0 ? R.decisions[last] : null, R.meta, t);
        P.renderRecent(R, last, t);
      }
      // the wall clock: its colon ticks while the video plays and holds when paused
      const playing = clock.playing;
      const half = Math.floor(t * 2) * 2 + (playing && !motion.matches ? 0 : 1);
      if (half !== lastSecond) { lastSecond = half; room.setClock(P.mmss(t), !playing || motion.matches || half % 4 === 0); }
      $('play').classList.toggle('playing', playing);
      $('play').setAttribute('aria-label', playing ? 'pause' : 'play');
    }
  };

  const toggle = () => (clock.playing ? clock.pause() : clock.play());
  $('play').addEventListener('click', toggle);
  document.addEventListener('keydown', (e) => {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return;
    if (e.code === 'Space' && document.activeElement?.tagName !== 'BUTTON') {
      e.preventDefault();
      toggle();
    } else if (e.key === 'e' || e.key === 'E') {
      setView(room.view === 'engineer' ? 'presenter' : 'engineer');
    }
  });
  $('speed').addEventListener('change', (e) => clock.setSpeed(Number(e.target.value)));
  $('live-sim').addEventListener('change', reschedule);
  sel.addEventListener('change', () => load(Number(sel.value)));
  $('timeline').addEventListener('click', (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    clock.seek(((e.clientX - r.left) / r.width) * clock.duration);
  });
  // keyboard: a decision interval per arrow, ten with shift, Home and End
  $('timeline').addEventListener('keydown', (e) => {
    if (!R) return;
    const step = R.meta.D * (e.shiftKey ? 10 : 1);
    const to = { ArrowLeft: clock.now() - step, ArrowRight: clock.now() + step, Home: 0, End: clock.duration }[e.key];
    if (to == null) return;
    e.preventDefault();
    clock.seek(to);
  });

  $('ask-close').addEventListener('click', () => { $('ask-panel').hidden = true; });
  const signIn = async () => {
    const password = pwInput.value;
    if (!password) { say('Type the owner password.'); pwInput.focus(); return; }
    pwInput.value = '';
    pwButton.disabled = true;
    say('Checking…');
    let res = null;
    try {
      res = await fetch('/api/owner', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ password }),
      });
    } catch { /* no answer: said below */ }
    pwButton.disabled = false;
    if (res?.ok) {
      owner = true;
      showOwner();
      const q = held;
      held = null;
      openPanel(false);
      tab.focus();
      $('owner-status').textContent = 'Signed in as the owner. Ask is on.';
      await syncRuns();
      if (q) await ask(q);
      return;
    }
    pwInput.setAttribute('aria-invalid', 'true');
    say(!res ? 'No answer from the server. Try again.'
      : res.status === 429 ? 'Too many tries. Wait a few minutes, then try again.'
      : 'Wrong password. Try again.');
    pwInput.focus();
  };
  const signOut = async () => {
    const res = await fetch('/api/owner', { method: 'DELETE' }).catch(() => null);
    if (!res?.ok) { say(res ? 'The server did not sign this browser out. Try again in a minute.' : 'No answer from the server. Try again.'); return; }
    owner = false;
    showOwner();
    $('ask-log').innerHTML = '';
    $('ask-panel').hidden = true;
    closePanel();
    $('owner-status').textContent = 'Signed out.';
    await syncRuns();
  };
  tab.addEventListener('click', () => (panel.hidden ? openPanel(true) : closePanel()));
  $('owner-close').addEventListener('click', closePanel);
  $('owner-out').addEventListener('click', signOut);
  $('owner-form').addEventListener('submit', (e) => { e.preventDefault(); signIn(); });
  panel.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    e.preventDefault();
    closePanel();
  });
  // a tap anywhere else puts the panel away
  document.addEventListener('pointerdown', (e) => {
    if (!panel.hidden && !panel.contains(e.target) && !tab.contains(e.target)) putAway();
  });

  const ask = async (question) => {
    const t = clock.now();
    const div = document.createElement('div');
    div.className = 'qa';
    div.innerHTML = `<div class="q">${P.esc(question)} <span class="muted">at ${P.mmss(t)}</span></div><div class="muted">asking the model…</div>`;
    $('ask-log').prepend(div);
    $('ask-panel').hidden = false;
    let text;
    try {
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ run: R.meta.run, video_id: R.meta.video_id, t, question }),
      });
      const reply = await res.json();
      if (res.status === 403 && reply.error === 'owner_only') {
        // signed out meanwhile (a new password, or the cookie's 30 days): the question
        // waits for the sign-in
        div.remove();
        if (!$('ask-log').children.length) $('ask-panel').hidden = true;
        owner = false;
        showOwner();
        openPanel(true, 'This browser was signed out (a new password, or the 30 days ran out). Sign in and the question goes to the model.');
        held = question;
        return;
      }
      text = res.ok ? reply.answer : `The server refused the question: ${reply.detail ?? reply.error ?? res.status}.`;
    } catch (err) {
      text = `The question did not reach the server (${err.message}). Ask again.`;
    }
    div.lastElementChild.className = '';
    div.lastElementChild.textContent = text;
  };

  askForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const question = askInput.value.trim();
    if (!question || !R) return;
    askInput.value = '';
    await ask(question);
  });

  await load(0);
  room.beforeFrame(loop);
  room.invalidate();
  // Hooks for scripted checks and the recording.
  window.__demo = { clock, layer, load, room, setView, get rollout() { return R; }, get runs() { return runs; }, dropSocket: () => sock?.close(), ready: true };
}

boot().catch((err) => {
  $('feed-info').textContent = `failed to load: ${err}`;
  console.error(err);
});

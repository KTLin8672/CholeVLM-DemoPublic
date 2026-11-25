// The screen's pages, rendered from decision lines in api.md v0.1's shape. Since the
// owner's arrangement of 2026-11-09, monitor C carries the model's reading; monitor B the
// tools in the presenter view (in view now and those the model called for the next three
// minutes, pictured) and the raw
// replies and every delay figure in the engineer view; the HUD carries the timeline, the
// last minute of decisions and the events. Every value comes from the log; a field the
// model left null is shown as unknown, never filled.
//
// The reading is a navigation aid (the owner's direction): what is
// coming in the next minutes leads (the next phase and its time to go, the next
// instrument, the instruments likely within five minutes), each counting down as the
// video plays and naming its source, the model's estimate or the training videos'
// statistics; where the procedure is now follows, smaller; warnings stay as they were.
// The 30-second next step, which v1 does not claim, is the engineer's.
//
// Colour has two jobs: drape green is the room and the screens; amber means a
// warning and red an alert, nothing else (the owner's picks, 2026-11-05).


export const PHASES = [
  'Preparation', 'CalotTriangleDissection', 'ClippingCutting', 'GallbladderDissection',
  'GallbladderPackaging', 'CleaningCoagulation', 'GallbladderRetraction',
];
export const PHASE_NAMES = {
  Preparation: 'Preparation',
  CalotTriangleDissection: 'Calot triangle dissection',
  ClippingCutting: 'Clipping & cutting',
  GallbladderDissection: 'Gallbladder dissection',
  GallbladderPackaging: 'Gallbladder packaging',
  CleaningCoagulation: 'Cleaning & coagulation',
  GallbladderRetraction: 'Gallbladder retraction',
};
const PHASE_SHORT = ['Prep', 'Calot', 'Clipping', 'GB dissection', 'Packaging', 'Cleaning', 'Retraction'];
// The phase's place in the usual order, -1 when unknown.
export const phaseIndex = (p) => PHASES.indexOf(p);

// For the animations only (decoration, never data): the blob's colour per phase.
export const PALETTE = {
  pink: '#ffb3c6', mint: '#b8f2e6', lavender: '#cdb4f6', sky: '#a0d8ff',
  orchid: '#ecb8f5', lime: '#caffbf', periwinkle: '#b3c0ff', peach: '#ffd6a5',
  drape: '#1f7a69', butter: '#ffc94d', alert: '#ff4b55', // severity: warning, alert
  slate: '#152523', text: '#f2fbf8',
};
const PHASE_COLOR = [PALETTE.lavender, PALETTE.pink, PALETTE.sky, PALETTE.mint, PALETTE.orchid, PALETTE.lime, PALETTE.periwinkle];
export const phaseColor = (p) => PHASE_COLOR[phaseIndex(p)] ?? PALETTE.mint;

const toolBase = (t) => t.split(':')[0];
const toolLabel = (t) => {
  const [base, sub] = t.split(':');
  const name = { suction_irrigation: 'suction / irrigation', specimen_bag: 'specimen bag' }[base] ?? base;
  return sub ? `${name} · ${sub}` : name;
};
// A raised flag's look: 'alert' (red, the beacon) and 'warn' (butter) are severities;
// 'unscored' is not one. The bleeding flag was trained on labels a model wrote and never
// scored, and the paper says not to rely on it, so the owner
// chose, 2026-11-22, that it is no longer drawn as an alert: an outline in the ink of every
// value with the word "unscored", no red, no beacon, whatever severity its event carries.
const FLAG_LABEL = {
  bleeding: ['active bleeding', 'unscored'],
  clipping_before_cvs: ['clipping before CVS', 'alert'],
  poor_visibility: ['poor visibility', 'warn'],
};
const UNSCORED_EVENTS = new Set(['active_bleeding']);
const evSeverity = (e) => (UNSCORED_EVENTS.has(e.kind) ? 'unscored' : e.severity);
const UNSCORED_TAG = '<span class="unscored-tag" title="trained on labels a model wrote and never scored: not to be relied on">unscored</span>';
const CVS_LABEL = { two_structures: 'two structures', triangle_cleared: 'triangle cleared', cystic_plate: 'cystic plate' };
const SEVERITY_RANK = { alert: 0, warn: 1, unscored: 1.5, info: 2 };

const $ = (id) => document.getElementById(id);
export const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
export const mmss = (t) => {
  const s = Math.max(0, Math.floor(t));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};
const pct = (x) => (x == null ? '–' : `${Math.round(x * 100)}%`);
const num = (x, d = 2) => (x == null ? '–' : Number(x).toFixed(d));
const UNKNOWN = '<span class="unknown">unknown</span>';

export function renderHeader(meta) {
  $('feed-info').textContent = `${meta.video_id} · ${meta.mode} run · a decision every ${meta.D} s · API ${meta.api_version}`;
  const banner = $('mock-banner');
  banner.hidden = !meta.banner;
  banner.textContent = meta.banner ?? '';
  $('synthetic-label').hidden = meta.feed !== 'synthetic';
  const credit = $('attribution');
  credit.hidden = !meta.attribution;
  credit.textContent = meta.attribution ?? '';
  // a video from outside the training distribution says so on every frame
  const ood = $('held-out');
  ood.hidden = !meta.held_out;
  ood.textContent = meta.held_out ?? '';
  renderModel(meta.model, meta.decision_form);
}

// The engineer's monitor names the model on the page: the checkpoint and its gate's
// result, then the gate's own line as training wrote it (api.md v1.6).
// A log before v1.6 does not record the gate, and says so.
function renderModel(m, form) {
  const el = $('c-model');
  if (!m?.checkpoint) { el.innerHTML = ''; return; }
  // api.md v1.12: a stateless run's decisions had no previous state and no prior block;
  // the checkpoint's gate was read in the form it was trained in
  const stateless = form === 'stateless';
  const gate = {
    met: 'gate met',
    'not met': 'gate not met',
    none: 'no gate',
  }[m.gate] ?? 'its gate is not in this run\'s log';
  el.innerHTML = `<b>${esc(m.checkpoint)}</b>${stateless ? ' · stateless' : ''} · <span class="gate">${gate}${stateless && (m.gate === 'met' || m.gate === 'not met') ? ' (in the trained form)' : ''}</span>${m.gate_line ? `<span class="gate-line">${esc(m.gate_line)}</span>` : ''}`;
}

const LANE_TITLES = { 'lane-ahead': 'Ahead', 'lane-cvs': 'Safety', 'lane-why': 'In the model’s words' };

export function renderWaiting(meta) {
  renderRail(null);
  for (const [id, title] of Object.entries(LANE_TITLES)) $(id).innerHTML = `<h3><span>${title}</span></h3><div class="waiting">–</div>`;
  $('lane-ahead').innerHTML = `<h3><span>Ahead</span></h3><div class="a-name">Waiting for the first decision</div><div class="waiting">The model reads a frame every ${meta.D} s.</div>`;
  $('lane-phase').innerHTML = '<h3><span>Now</span></h3><div class="waiting">–</div>';
  $('lane-tools').innerHTML = '';
  $('lane-flags').innerHTML = '';
}

// Past the rollout's last decision (an offline run that covers part of the video):
// the lanes say there is no decision, rather than hold the last one.
export function renderEnded(meta) {
  renderRail(null);
  const at = mmss(meta.last_decision_t ?? 0);
  for (const [id, title] of Object.entries(LANE_TITLES)) $(id).innerHTML = `<h3><span>${title}</span></h3><div class="waiting">no decision</div>`;
  $('lane-ahead').innerHTML = `<h3><span>Ahead</span></h3><div class="a-name">No decision after ${at}</div><div class="waiting">This run's rollout of the video ends there; the video plays on without the model.</div>`;
  $('lane-phase').innerHTML = '<h3><span>Now</span></h3><div class="waiting">no decision</div>';
  $('lane-tools').innerHTML = '';
  $('lane-flags').innerHTML = '';
}

export function renderEndedStamp(meta) {
  const el = $('b-stamp');
  el.className = 'late';
  el.innerHTML = `<span class="v">no decision</span><span class="k">the rollout ends at <b>${mmss(meta.last_decision_t ?? 0)}</b></span>`;
}

// The seven phases in their usual order: done, now, still to come, and the one the
// training videos say comes next outlined, the route ahead.
export function renderRail(d) {
  const idx = d ? phaseIndex(d.state.phase) : -1;
  const next = d ? phaseIndex(d.outlook?.next_phase?.[0]?.phase) : -1;
  $('b-rail').innerHTML = PHASES.map((p, i) =>
    `<i class="${i < idx ? 'past' : i === idx ? 'now' : i === next ? 'next' : ''}" title="${esc(PHASE_NAMES[p])}">${i + 1}</i>`).join('');
}

// A time ahead as it counts down with the video: in minutes from a minute up, in seconds
// under it. Each is written once with the moment it is due (`data-due`, video seconds)
// and redrawn by tickEta, so it moves between decisions.
const etaHtml = (s) => (s <= 0 ? 'due now'
  : s < 60 ? `in <b>${Math.ceil(s)}</b> s` : `in <b>${Math.round(s / 60)}</b> min`);
const etaSpan = (due, cls = '') => `<span class="eta ${cls}" data-due="${due}"></span>`;
export function tickEta(t) {
  for (const el of document.querySelectorAll('.eta[data-due]')) {
    const html = etaHtml(Number(el.dataset.due) - t);
    if (el.dataset.shown !== html) { el.dataset.shown = html; el.innerHTML = html; }
  }
}
// where a look-ahead item comes from: the model's own estimate, or
// the procedure statistics of the training videos; nothing from a table is the model's
const SRC = {
  model: '<span class="src model" title="the model’s own estimate">model</span>',
  stats: '<span class="src stats" title="the procedure statistics of the training videos (the serving addendum), not the model">training videos</span>',
};

// Ahead: what is coming in the next minutes, early enough to act on.
// The next phase is the training videos' likeliest after the model's current one; its
// time to go is the model's estimate. The next instrument is the model's call; the
// instruments likely within five minutes are the training videos' (`tools_300s`, the
// types not already in view).
function aheadLane(d) {
  const s = d.state;
  const o = d.outlook;
  const np = o?.next_phase?.[0];
  const name = !np ? UNKNOWN
    : np.phase === 'end' ? 'the end of the procedure'
      : `${phaseIndex(np.phase) + 1} ${esc(PHASE_NAMES[np.phase] ?? np.phase)}`;
  const rem = s.phase_remaining;
  const time = rem?.estimate_s != null
    ? `<div class="a-time">${etaSpan(d.t_frame + rem.estimate_s, 'a-eta')}${SRC.model}</div>`
    : `<div class="a-time"><span class="muted">time to go ${UNKNOWN}</span></div>`;
  const others = (o?.next_phase ?? []).slice(1, 3).map((x) => `${esc(PHASE_SHORT[phaseIndex(x.phase)] ?? x.phase)} ${num(x.p)}`).join(', ');
  const cur = d.memory.current_phase;
  const eng = `<div class="a-eng engineer-only">${rem ? `${esc(String(rem.bucket).replace('-', '–'))} · ${num(rem.estimate_s, 0)} s` : ''}${np ? ` · P ${num(np.p)}${others ? `, else ${others}` : ''}` : ''}${cur.phase === s.phase
    ? `<br>pace ${num(cur.pace)}× median${cur.prior_p90_s != null ? ` · p90 ${mmss(cur.prior_p90_s)}` : ''}` : ''}</div>`;
  const nt = s.next_tool;
  const tool = !nt ? UNKNOWN
    : nt.tool === 'none' ? '<span class="muted">none in the next 30 s</span>'
      : `<b>${esc(toolLabel(nt.tool))}</b> ${nt.within_s != null ? etaSpan(d.t_frame + nt.within_s) : '<span class="eta">within 30 s</span>'}<span class="muted engineer-only"> · conf ${num(nt.conf)}</span>`;
  const soon = (o?.tools_300s ?? []).filter((x) => !x.in_view && x.p >= 0.05).slice(0, 3);
  const rows = !o ? `<div class="waiting">${UNKNOWN}</div>`
    : soon.length ? `<div class="tools5">${soon.map((x) => `<span>${esc(toolLabel(x.tool))}</span>
        <div class="bar"><i style="width:${pct(x.p)}"></i></div><b>${pct(x.p)}</b>`).join('')}</div>`
      : '<div class="muted">no new instrument likely</div>';
  return `
    <h3><span>Ahead · next phase</span>${SRC.stats}</h3>
    <div class="a-name">${name}</div>
    ${time}${eng}
    <div class="a-k"><span>Next instrument</span>${SRC.model}</div>
    <div class="a-tool">${tool}</div>
    <div class="a-k"><span${o ? ` title="the table's bin: ${mmss(o.elapsed_bin_s)} or more into the phase"` : ''}>Chance within 5 min</span>${SRC.stats}</div>
    ${rows}`;
}

// Now: where the procedure is, as context; on monitor C the left column, what is ahead
// on the right (the owner, 2026-11-23).
function phaseLane(d, meta) {
  const s = d.state;
  const cur = d.memory.current_phase;
  const low = s.phase_conf != null && s.phase_conf < meta.thresholds.low_phase_conf;
  const fell = d.fallback ? ' <span class="badge warn" title="this reply did not parse; the previous state is kept">fell back</span>' : '';
  const same = cur.phase === s.phase;
  const where = same ? `<b>${mmss(cur.elapsed_s)}</b> into it`
    : `<span title="the running memory counts a change once it holds ${meta.flicker_s ?? 10} s">memory: ${esc(PHASE_SHORT[phaseIndex(cur.phase)] ?? cur.phase)}</span>`;
  return `
    <h3><span>Now</span><span class="now-where">${where}</span></h3>
    <div class="now-name">${s.phase ? `${phaseIndex(s.phase) + 1} ${esc(PHASE_NAMES[s.phase] ?? s.phase)}` : UNKNOWN}${fell}</div>
    ${d.fallback ? '<div class="fell">This reply did not parse. Every lane shows the previous state.</div>' : ''}
    <div class="row"><span class="muted">confidence</span>
      <div class="bar"><i class="${low ? 'low' : ''}" style="width:${pct(s.phase_conf ?? 0)}"></i></div>
      <span class="big-val">${pct(s.phase_conf)}</span>${low ? '<span class="badge warn">low</span>' : ''}</div>`;
}

function toolsLane(d) {
  const s = d.state;
  const conf = s.tools_now_conf ?? {};
  const now = s.tools_now == null
    ? UNKNOWN
    : s.tools_now.length
      ? s.tools_now.map((t) => `<span class="chip" title="confidence ${pct(conf[toolBase(t)])}">${esc(toolLabel(t))}</span>`).join('')
      : '<span class="muted">none in view</span>';
  return `<div class="row"><span class="muted">in view</span>${now}</div>`;
}

// Where a served CVS value comes from (api.md v1.11): the reply's
// own value, the reply's own probability over a threshold fixed on val, or the CVS
// specialist, which is not the language model
const CVS_SRC = {
  reply: '<span class="src model" title="the model’s own reading in its reply">model</span>',
  p1: '<span class="src model" title="the model’s own probability of yes in its reply, over a threshold fixed on the validation videos">model p</span>',
  specialist: '<span class="src spec" title="the CVS specialist: a separate small model reading the vision probe’s numbers up to this second, not the language model">specialist</span>',
};
// A served criterion as a screening signal: two states named by
// what they mean, never drawn as achieved, checked or in a colour of success; null is unknown
const CVS_STATE = (v) => (v == null ? UNKNOWN : `<span class="st">${v ? 'possibly seen' : 'not seen'}</span>`);
const CVS_NOTE = 'screening signal, not a confirmation'; // one line, under the lane's "critical view" heading

// The critical view: in a run with the served CVS each
// criterion is "not seen" or "possibly seen" with its source, under one line saying it
// is a screening signal; nothing is drawn from the three together (no count, no
// combined state, no time) and nothing holds or smooths a value. A run without the
// served CVS shows no CVS reading, never the reply's own in its place. On the engineer's
// view, in a run served with the hint, the probe's three numbers beside each criterion's
// name, labelled the probe's and never the model's (api.md v1.5).
function cvsLane(d, meta) {
  const h = meta.hint ? d.hint : null;
  const served = meta.cvs_served ? d.cvs_served : null;
  const probe = (k) => (h ? `<span class="probe engineer-only" title="the vision hint's reading of this frame, not the model's">probe ${h.shown && h[k] != null ? num(h[k]) : '–'}</span>` : '');
  let body;
  if (served) {
    body = `<div class="cvs-note">${CVS_NOTE}</div><div class="cvs">${Object.entries(CVS_LABEL).map(([k, label]) =>
      `<div class="item"><span>${label}</span>${CVS_STATE(served[k].value)}${CVS_SRC[served[k].source]}${probe(k)}</div>`).join('')}</div>`;
  } else {
    body = `<div class="cvs-none">no CVS reading in this run</div>${h ? `<div class="cvs probes engineer-only">${Object.keys(CVS_LABEL).map((k) =>
      `<div class="item"><span>${CVS_LABEL[k]}</span>${probe(k)}</div>`).join('')}</div>` : ''}`;
  }
  const why = !h ? ''
    : h.shown ? 'probe: the vision hint, a linear probe on this frame; not the model\'s reading'
      : h.unfamiliar ? 'probe: the vision hint is off, an unfamiliar scene'
        : 'probe: the vision hint is off, no prior block on this decision';
  const note = h ? `<div class="hint-note engineer-only" data-anchor="hint">${why}</div>` : '';
  return `<h3><span>Safety</span><span>critical view, risk flags</span></h3>${body}${note}`;
}

// The engineer's page: the served CVS as it came, per criterion
// the value and its source; beside them, once the API carries them (api.md v1.13), val's figures under the word "val": precision (of its 1s,
// the share whose label is met), NPV (of its 0s, the share whose label is not met) and the
// share of labelled points met, with the points and videos they are read on. A criterion
// served by p1 had its threshold fixed on val, so its figures are the out-of-fold ones,
// marked †. A run without them shows none.
const fig = (x) => x.value.toFixed(2);
const count = (n) => n.toLocaleString('en-US');
function valFoot(val) {
  const ks = Object.keys(CVS_LABEL);
  const same = ks.every((k) => val[k].points === val[ks[0]].points && val[k].videos === val[ks[0]].videos);
  const on = same
    ? `on ${count(val[ks[0]].points)} labelled points of ${val[ks[0]].videos} videos`
    : `on ${ks.map((k) => `${count(val[k].points)} (${k})`).join(', ')} labelled points of ${Math.max(...ks.map((k) => val[k].videos))} videos at most`;
  const oof = ks.some((k) => val[k].out_of_fold) ? ' · † out of fold' : '';
  return `<div class="c-cvs-val" title="† a criterion served by p1 had its threshold fixed on val, so its figures are read out of fold">val, ${on}${oof}</div>`;
}

export function renderCvsServed(d, meta) {
  const el = $('c-cvs');
  if (!d || !meta?.cvs_served) { el.innerHTML = ''; return; }
  const val = meta.cvs_val ?? null;
  const head = !val ? ''
    : '<span></span><span class="h">served</span><span class="h">source</span>'
      + '<span class="h" title="of the criterion\'s 1s on val, the share whose label is met">val precision</span>'
      + '<span class="h" title="of the criterion\'s 0s on val, the share whose label is not met">val NPV</span>'
      + '<span class="h" title="the share of val\'s labelled points whose label is met">val met</span>';
  const rows = Object.keys(CVS_LABEL).map((k) => {
    const c = d.cvs_served[k];
    const v = val?.[k];
    const mark = v?.out_of_fold ? '†' : '';
    const figs = !v ? ''
      : `<span class="f" title="of ${count(v.precision.n)} 1s on val, ${fig(v.precision)} had the label met">${fig(v.precision)}${mark}</span>`
        + `<span class="f" title="of ${count(v.npv.n)} 0s on val, ${fig(v.npv)} had the label not met">${fig(v.npv)}${mark}</span>`
        + `<span class="f" title="of ${count(v.met_share.n)} labelled points on val, ${fig(v.met_share)} met">${fig(v.met_share)}</span>`;
    return `<span>${k}</span><b>${c.value == null ? 'null' : c.value}</b><span>${c.source}</span>${figs}`;
  }).join('');
  el.innerHTML = `<h3><span>CVS served · ${CVS_NOTE}</span></h3>`
    + `<div class="c-cvs-rows${val ? ' with-val' : ''}">${head}${rows}</div>${val ? valFoot(val) : ''}`;
}

// The tools page (monitor B in the presenter view, and a card in a phone's dashboard;
// the owner, 2026-11-09: "show visual of the next tool ... and the name underneath it,
// if there is two tool estimate divide it by a center divider", then "Now | next"): on
// the left the tools the model sees in the frame now, on the right the tools it has called
// for the next minutes, parted by a centre rule. Each is a picture of the instrument, drawn
// ahead of time from its 3D model (room/instruments.js, web/public/instruments/), with
// its name under it, in the reading's words. Every value is the model's: a null is
// unknown (dashed), never filled.
// The right half (the owner, 2026-11-22: "aggregate the model result and see what is the
// next most possible (top 2) tool for next 3 minute", in place of the next tool within
// 30 s) counts the model's own next-tool calls, each for 30 s, over the last
// three minutes, a call left out once the model has seen its tool since, and shows the two
// most called that are not in view, each with its count: a count of the model's calls, not
// a trained three-minute forecast, and tagged so. The 30-s call stays on the reading.
const TOOL_PAGES = ['screen-tools', 'tool-card'];
// the picture for a tool as the model writes it (`energy:hook`, `clipper`, …): the
// energy device named without a sub-type is drawn as the hook, the one a
// cholecystectomy uses most, and says "hook or bipolar" under its name
const PICTURE = {
  grasper: 'grasper', clipper: 'clipper', scissors: 'scissors', energy: 'hook', 'energy:hook': 'hook',
  'energy:bipolar': 'bipolar', suction_irrigation: 'suction_irrigation', specimen_bag: 'specimen_bag',
  stapler: 'stapler', other: 'other',
};
const pictureOf = (t) => PICTURE[t] ?? PICTURE[String(t).split(':')[0]] ?? null;

function putTools(html, fell = false) {
  for (const id of TOOL_PAGES) {
    const el = $(id);
    if (!el) continue;
    el.innerHTML = html;
    el.classList.toggle('fell-back', fell);
  }
}

const toolFigure = (tool, sub = '') => {
  const pic = pictureOf(tool);
  return `<figure class="t-tool">${pic ? `<img src="/instruments/${pic}.webp" alt="" decoding="async">` : '<div class="t-nopic"></div>'}<figcaption><b>${esc(toolLabel(tool))}</b>${sub}</figcaption></figure>`;
};
const CALLS_S = 180;
const CALLS_TAG = `<span class="src model" title="the two tools the model called most (each call for 30 s) over the last 3 minutes; a call left out once the model saw its tool; the counts on the engineer’s page; not a trained 3-minute forecast">model’s calls</span>`;
const toolCols = (now, next, n, m = 1) => `
  <div class="t-col"><h3><span>Tools in view</span></h3><div class="t-items n${n}">${now}</div></div>
  <div class="t-rule" aria-hidden="true"></div>
  <div class="t-col"><h3><span>Next 3 min</span>${CALLS_TAG}</h3><div class="t-items n${m}">${next}</div></div>`;
const typeOf = (t) => String(t).split(':')[0];
// the two tool types the model called most over the last three minutes, not in view now;
// newest first, so a call is dropped when a later decision saw its tool, and a tie goes
// to the type called last; a reply that fell back repeats the previous state and is not
// counted again
function calledTools(d, upto) {
  const counts = new Map();
  const seen = new Set();
  for (let j = upto.length - 1; j >= 0 && upto[j].t_frame >= d.t_frame - CALLS_S; j--) {
    const e = upto[j];
    const call = e.state?.next_tool?.tool;
    if (!e.fallback && call && call !== 'none' && !seen.has(typeOf(call))) counts.set(typeOf(call), (counts.get(typeOf(call)) ?? 0) + 1);
    for (const x of e.state?.tools_now ?? []) seen.add(typeOf(x));
  }
  const now = new Set((d.state.tools_now ?? []).map(typeOf));
  return [...counts].filter(([t]) => !now.has(t)).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([tool, calls]) => ({ tool, calls }));
}
const toolNote = (text) => `<div class="t-empty">${text}</div>`;

export function renderTools(d, upto = [d]) {
  const s = d.state;
  const now = s.tools_now == null ? toolNote(UNKNOWN)
    : s.tools_now.length ? s.tools_now.map((t) => toolFigure(t)).join('')
      : toolNote('none in view');
  const energy = (t) => (t === 'energy' ? '<span class="t-sub">hook or bipolar</span>' : '');
  const called = calledTools(d, upto);
  const next = called.length
    ? called.map((x) => toolFigure(x.tool, energy(x.tool))).join('') // the counts: the engineer's page (renderCalls)
    : toolNote('no new tool called');
  const fell = d.fallback ? '<div class="t-fell">This reply did not parse: the previous state is shown.</div>' : '';
  putTools(toolCols(now, next, Math.max(1, s.tools_now?.length ?? 1), Math.max(1, called.length)) + fell, !!d.fallback);
}

// The counts behind monitor B's right half, on the engineer's page alone (the owner,
// 2026-11-23: "remove the count of calls, that should be in engineering view only").
export function renderCalls(d, upto = [d]) {
  const el = $('c-calls');
  if (!d) { el.innerHTML = ''; return; }
  const called = calledTools(d, upto);
  const rows = called.length
    ? `<div class="c-calls-rows">${called.map((x) => `<span>${esc(toolLabel(x.tool))}</span><b>${x.calls} call${x.calls === 1 ? '' : 's'}</b>`).join('')}</div>`
    : '<div class="muted">no new tool called</div>';
  el.innerHTML = `<h3><span>Next 3 min · the model’s calls</span><span>last ${CALLS_S} s</span></h3>${rows}`;
}

export function renderToolsWaiting() {
  putTools(toolCols(toolNote('waiting for the first decision'), toolNote('–'), 1));
}

export function renderToolsEnded(meta) {
  const at = mmss(meta.last_decision_t ?? 0);
  putTools(toolCols(toolNote(`no decision after ${at}`), toolNote('no decision'), 1));
}

// Only what is raised (or unknown) is shown: an off flag is not a label on screen.
function flagsLane(d) {
  const s = d.state;
  const pills = [];
  for (const [k, [label, sev]] of Object.entries(FLAG_LABEL)) {
    const v = s.risk_flags?.[k];
    if (v == null) pills.push(`<span class="pill" title="the model left this flag unknown">${label}?</span>`);
    else if (v) {
      const spans = d.memory.flags?.[k] ?? [];
      const open = spans.length && spans[spans.length - 1][1] == null ? spans[spans.length - 1][0] : null;
      // an unscored flag's pill gives its word in place of the time, which the event box and
      // the timeline's mark carry: the pill holds one line in the board's flags column
      const since = open != null && sev !== 'unscored' ? ` · since ${mmss(open)}` : '';
      pills.push(`<span class="pill on ${sev}">${label}${since}${sev === 'unscored' ? UNSCORED_TAG : ''}</span>`);
    }
  }
  if (s.blood == null) pills.push('<span class="pill" title="the model left blood unknown">blood?</span>');
  else if (s.blood !== 'none') pills.push(`<span class="pill on ${s.blood === 'significant' ? 'warn' : 'info'}">blood: ${esc(s.blood)}</span>`);
  return `<div class="row">${pills.length ? pills.join('') : '<span class="muted">no risk flags raised</span>'}</div>`;
}

// The 30-second next step, on the engineer's page beside the raw replies: v1 does not claim it, and its horizon is not one a person can act on.
// The model's rationale goes with it there; on the presenter's view it has a lane of its own.
const whyText = (d) => `<div class="rationale">${d.state.rationale == null ? UNKNOWN : `“${esc(d.state.rationale)}”`}</div>`;
export function renderStep(d) {
  const el = $('c-step');
  if (!d) { el.innerHTML = ''; return; }
  const ns = d.state.next_step;
  let step;
  if (!ns) step = UNKNOWN;
  else if (ns.verb === 'continue' || ns.verb === 'other') {
    step = `<span class="step">${esc(ns.verb)}</span> <span class="muted">${ns.verb === 'continue' ? 'no new step within 30 s' : 'a step outside the verb list'}</span>`;
  } else {
    step = `<span class="step">${esc(ns.verb)} → ${esc(String(ns.target).replace(/_/g, ' '))}</span> <span class="muted">in about ${ns.within_s ?? '?'} s</span>`;
  }
  el.innerHTML = `<h3><span>Next step · 30 s · not a claimed capability</span><span>${ns ? `conf ${num(ns.conf)}` : ''}</span></h3><div class="row">${step}</div>${whyText(d)}`;
}

function whyLane(d) {
  return `<h3><span>In the model’s words</span></h3>${whyText(d)}`;
}

export function renderLanes(d, meta) {
  renderRail(d);
  $('lane-ahead').innerHTML = aheadLane(d);
  $('lane-phase').innerHTML = phaseLane(d, meta);
  $('lane-tools').innerHTML = toolsLane(d);
  $('lane-cvs').innerHTML = cvsLane(d, meta);
  $('lane-flags').innerHTML = flagsLane(d);
  $('lane-why').innerHTML = whyLane(d);
}

// A late decision is shown as such. Monitor B leads with how far
// its reading trails the video, at value size: amber once it is more than one
// decision interval behind, and "stale" past two.
export function renderStamp(d, t, meta) {
  const el = $('b-stamp');
  if (!d) { el.innerHTML = ''; el.className = 'late'; return; }
  const behind = Math.max(0, t - d.t_frame);
  const late = behind > meta.D;
  const stale = behind > 2 * meta.D;
  el.className = `late${late ? ' warn' : ''}`;
  el.innerHTML = `<span class="v">${behind.toFixed(1)} s behind</span><span class="k">${stale ? 'stale · ' : ''}reading from <b>${mmss(d.t_frame)}</b></span>`;
}

// A run in progress (step 2): the video waits at the model's last decision while it
// computes the next one, and the reading says so instead of a lag that is not one.
export function renderComputingStamp(meta) {
  const el = $('b-stamp');
  el.className = 'late warn';
  el.innerHTML = `<span class="v">model computing</span><span class="k">the decision for <b>${mmss(meta.last_decision_t + meta.D)}</b></span>`;
}

// The frozen-frame indicator (step 2): once the reading trails the video by more than
// two decision intervals, the "model saw" inset says the model's view is frozen, and
// for how long (a late decision is shown as such).
let frozenNote = '';
export function renderFrozen(d, t, meta, held) {
  const behind = t - d.t_frame;
  const frozen = !held && behind > 2 * meta.D;
  $('model-frame').classList.toggle('frozen', frozen);
  const note = `model saw <b>${mmss(d.t_frame)}</b>${frozen ? ` · frozen <b>${Math.floor(behind)} s</b>` : ''}`;
  if (note !== frozenNote) { frozenNote = note; $('model-frame-note').innerHTML = note; }
}

// An alert is on screen: a raised alert flag or an uncleared alert event.
export function alertActive(d) {
  if (!d) return false;
  const flags = Object.entries(FLAG_LABEL).some(([k, [, sev]]) => sev === 'alert' && d.state.risk_flags?.[k] === 1);
  return flags || d.events.some((e) => e.visible && e.t_cleared == null && evSeverity(e) === 'alert');
}

// The whole run: the phases from the model's running memory, numbered, with the flags
// marked (no CVS mark); the playhead at the video time.
const MARK_INK = { alert: 'var(--alert)', warn: 'var(--warn)', unscored: 'var(--ink)' };
export function renderTimeline(d, meta, t) {
  const dur = meta.duration_s;
  const x = (v) => `${(100 * Math.max(0, Math.min(dur, v))) / dur}%`;
  let segs = '', marks = '';
  if (d) {
    segs = d.memory.phase_timeline.map((p) => {
      const i = phaseIndex(p.phase);
      const end = p.end_t ?? d.t_frame;
      return `<div class="seg" title="${esc(PHASE_NAMES[p.phase] ?? p.phase)} · ${mmss(p.elapsed_s)}" style="left:${x(p.start_t)};width:${x(end - p.start_t)};background:${i % 2 ? 'var(--drape-deep)' : 'var(--drape)'}">${i + 1} ${PHASE_SHORT[i] ?? ''}</div>`;
    }).join('');
    marks = Object.entries(d.memory.flags).flatMap(([f, spans]) => spans.map(([on]) =>
      `<div class="mark" style="left:${x(on)};background:${MARK_INK[FLAG_LABEL[f]?.[1]] ?? 'var(--warn)'}" title="${esc(FLAG_LABEL[f]?.[0] ?? f)} at ${mmss(on)}"></div>`)).join('');
  }
  const tl = $('timeline');
  tl.setAttribute('aria-valuemax', String(Math.round(dur)));
  tl.setAttribute('aria-valuenow', String(Math.round(t)));
  tl.setAttribute('aria-valuetext', mmss(t));
  tl.innerHTML = `<div class="track">${segs}<div class="head" style="left:${x(t)}"></div></div><div class="marks">${marks}</div>`;
}

// The last minute of decisions at their true length, from the frame to the answer
// (encode + compute); a fallback dashed, a dropped tick hollow. Then the presenter's figures.
export function renderRecent(R, i, t) {
  const W = 60;
  const x = (v) => (100 * (v - (t - W))) / W;
  const blocks = [];
  for (let k = i; k >= 0; k--) {
    const d = R.decisions[k];
    if (d.t_frame < t - W) break;
    const end = Math.min(t, d.t_frame + d.encode_s + d.compute_s);
    blocks.push(`<i class="${d.fallback ? 'fb' : ''}" style="left:${x(d.t_frame)}%;width:${Math.max(0.3, x(end) - x(d.t_frame))}%"></i>`);
  }
  for (const dr of R.dropped) {
    if (dr.t_frame > t - W && dr.t_frame <= t) blocks.push(`<i class="drop" style="left:${x(dr.t_frame)}%;width:${(100 * 0.5) / W}%"></i>`);
  }
  const d = i >= 0 ? R.decisions[i] : null;
  const dl = d?.delay;
  const s = (v) => (v == null ? '–' : `${Number(v).toFixed(2)} s`);
  const r = (v) => (v == null ? '–' : `${(100 * v).toFixed(1)}%`);
  const fallbacks = i >= 0 ? R.decisions.slice(0, i + 1).filter((z) => z.fallback).length : 0;
  const figs = !d ? `a decision every <b>${R.meta.D} s</b>`
    : [`model time <b>${s(dl.compute_p50_s)}</b> median`,
      // api.md v1.3: dropped_rate_est is the share of ticks a live loop at D would skip (the adapter reads older lines so)
      R.meta.mode === 'live' ? `dropped <b>${r(dl.dropped_rate_observed)}</b>` : `live would skip <b>${r(dl.dropped_rate_est)}</b>`,
      `fallbacks <b>${fallbacks}</b>`].join(' · ');
  $('recent').innerHTML = `<span>last minute, frame to answer</span><div class="strip">${blocks.join('')}<span class="now"></span></div><span class="figs">${figs}</span>`;
}

// the adapter's REPLY_WITHHELD: an unparsed reply whose own "cvs" could not be cut whole
const WITHHELD = 'unparsed, withheld';

export function renderReplies(recent) {
  const items = recent.slice().reverse().map((d) => {
    let body = d.reply;
    let how = '';
    try {
      body = JSON.stringify(JSON.parse(d.reply), null, 1);
    } catch {
      // an unparsed reply is shown as it came, less its own "cvs", or withheld
      if (d.reply !== WITHHELD) how = ' · as it came, less any <code>"cvs"</code>';
    }
    const bad = d.fallback ? ` <span class="badge warn">invalid</span> ${d.parse_error ? esc(d.parse_error) : ''} · previous state kept${how}` : how;
    const lines = String(body).split('\n');
    const shown = lines.length > 9 ? `${lines.slice(0, 9).join('\n')}\n…` : body;
    return `<div class="reply"><div><b>${mmss(d.t_frame)}</b> · #${d.seq} · ${num(d.compute_s)} s${bad}</div><pre>${esc(shown)}</pre></div>`;
  });
  // the reply's own CVS is cut by the server, so what is shown is
  // not the model's bytes, and the pane says so once
  const cut = '<div class="reply-note">each reply re-serialised with its own <code>"cvs"</code> field removed, so not the model’s bytes: the CVS shown is the served one, below</div>';
  $('reply').innerHTML = items.length ? cut + items.join('') : '<div class="waiting">no reply yet</div>';
}

// Raised and holding events first, alerts on top; cleared ones after, newest first.
export function renderEvents(d) {
  const evs = (d ? d.events.filter((e) => e.visible) : []).slice().sort((a, b) =>
    (a.t_cleared != null) - (b.t_cleared != null)
    || SEVERITY_RANK[evSeverity(a)] - SEVERITY_RANK[evSeverity(b)]
    || b.t_raised - a.t_raised);
  $('events').innerHTML = evs.length
    ? evs.map((e) => {
      const cleared = e.t_cleared != null;
      const sev = evSeverity(e);
      return `<div class="event ${cleared ? 'cleared' : sev}"><b>${mmss(e.t_raised)}</b>
        <span>${esc(e.wording)}${sev === 'unscored' ? UNSCORED_TAG : ''}${cleared ? ` · cleared ${mmss(e.t_cleared)}` : ''}<span class="field">${esc(e.kind)} · ${esc(e.field)}</span></span></div>`;
    }).join('')
    : '<div class="calm">No events raised</div>';
}

// Plan §9 item 7, as the server computes it (the Delay object), on the engineer's laptop.
export function renderDelay(d, upto, meta) {
  if (!d) { $('delay').innerHTML = `<span>a decision every</span><b>${meta.D} s</b>`; return; }
  const dl = d.delay;
  const s = (v) => (v == null ? '–' : `${Number(v).toFixed(2)} s`);
  const r = (v) => (v == null ? '–' : `${(100 * v).toFixed(1)}%`);
  const rows = [
    ['a decision every (D)', `${meta.D} s`], ['compute p50', s(dl.compute_p50_s)], ['compute p95', s(dl.compute_p95_s)],
    ['staleness now', s(dl.staleness_s)], ['live would skip', r(dl.dropped_rate_est)],
    [`replies over D (${meta.D} s)`, r(dl.over_d_rate)],
  ];
  if (meta.mode === 'live') rows.push(['dropped, observed', `${r(dl.dropped_rate_observed)} (${d.tick - d.seq} ticks)`]);
  rows.push(['encode', s(d.encode_s)], ['fallbacks', String(upto.filter((x) => x.fallback).length)], ['decisions', String(dl.n)]);
  $('delay').innerHTML = rows.map(([k, v]) => `<span>${k}</span><b>${esc(v)}</b>`).join('');
}

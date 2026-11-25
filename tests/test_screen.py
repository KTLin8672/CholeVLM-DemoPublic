"""The built screen in headless Chromium (Playwright, the venv's browsers): the
virtual OR. At recording sizes the monitors' pages
fit their screens and stay in view, an alert is on monitor C, in the event box and
on the beacon, the bleeding flag is raised as unscored and never as an alert, off flags are not shown, low confidence is a word, the
video plays, and on a phone the reading is a dashboard under the room, without
sideways scroll.

Skipped when the page is not built (`npm run build` in web/), when the mock's video
is not built (`python -m chole_demo mock`), or when Playwright or its browser is missing.
`CHOLE_DEMO_TEST_DIST` names another build to test (a trial build, before it goes into
web/dist, which the server serves live); for a trial build each of these fails instead,
since a run of skips exits 0 and the swap that follows the tests would go ahead untested.
"""

import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from chole_demo.feeds import mock
from chole_demo.owner import Owner
from chole_demo.server import RUNS, WEB_DIST, create_app

TRIAL = os.environ.get("CHOLE_DEMO_TEST_DIST")


def _missing(why: str) -> None:
    """Skip, or fail when a trial build is to be swapped in only if these tests pass."""
    if TRIAL:
        pytest.fail(f"{why}: the trial build is not tested", pytrace=False)
    pytest.skip(why, allow_module_level=True)


try:
    from playwright import sync_api as pw
except ImportError:
    _missing("Playwright is not installed")

VENV = Path(os.environ.get("VIRTUAL_ENV", Path.home() / ".virtualenvs" / "CholeVLMDemo"))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(VENV / "ms-playwright"))

DIST = Path(TRIAL or WEB_DIST)
if not (DIST / "index.html").exists():
    _missing(f"the page is not built ({DIST / 'index.html'} is missing)")
if not (RUNS / "mock" / "video" / f"{mock.VIDEO_ID}.mp4").exists():
    _missing("the mock is not built (python -m chole_demo mock)")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PASSWORD = "a test password, not the owner's"


def _serve(tmp_path_factory, pace=1.0, source=mock.MockSource):
    owner = Owner(tmp_path_factory.mktemp("owner") / "owner.local.yaml")
    owner.set_password(PASSWORD)
    app = create_app(
        source(RUNS, pace=pace),
        web_dist=DIST,
        access_log=tmp_path_factory.mktemp("log") / "access.log",
        owner=owner,
        sessions_dir=tmp_path_factory.mktemp("sessions"),
    )
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def url(tmp_path_factory):
    yield from _serve(tmp_path_factory)


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except pw.Error as e:
            _missing(f"no Playwright browser: {e}")
        yield b
        b.close()


SEEK = """t => new Promise(res => {
  const v = document.getElementById('video');
  window.__demo.clock.pause();
  window.__demo.clock.seek(t);
  const done = () => setTimeout(res, 400);
  if (v.seeking) v.addEventListener('seeked', done, {once: true}); else done();
})"""

STATE = """() => {
  const inView = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.top >= 0 && r.bottom <= window.innerHeight
      && r.left >= 0 && r.right <= window.innerWidth;
  };
  const fits = (el) => el.scrollHeight <= el.clientHeight + 1;
  const shown = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).display !== 'none';
  return {
    readingsFit: fits(document.getElementById('screen-b')),
    engineerFits: fits(document.getElementById('screen-c')),
    toolsFit: fits(document.getElementById('screen-tools')),
    readingsInView: inView(document.getElementById('screen-b')),
    engineerInView: inView(document.getElementById('screen-c')),
    toolsInView: inView(document.getElementById('screen-tools')),
    engineerShown: shown(document.getElementById('screen-c')),
    toolsShown: shown(document.getElementById('screen-tools')),
    monitors: ['A', 'B', 'C'].map((k) => { const r = window.__demo.room.screenRect(k);
      return r.left >= 0 && r.right <= window.innerWidth && r.top >= 0 && r.bottom <= window.innerHeight; }),
    pillInView: inView(document.querySelector('#lane-flags .pill.on.alert')),
    alertCardInView: inView(document.querySelector('#events .event.alert')),
    pillAlert: !!document.querySelector('#lane-flags .pill.on.alert'),
    alertCard: !!document.querySelector('#events .event.alert'),
    unscoredInView: inView(document.querySelector('#lane-flags .pill.on.unscored')),
    unscoredCard: !!document.querySelector('#events .event.unscored'),
    beacon: window.__demo.room.alerting,
    flags: document.getElementById('lane-flags').innerText,
    phase: document.getElementById('lane-phase').innerText,
    videoReady: document.getElementById('video').readyState,
  };
}"""


def _open(browser, url, w, h, view):
    errors = []
    page = browser.new_page(viewport={"width": w, "height": h})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(url + ("?view=engineer" if view == "engineer" else ""))
    page.wait_for_function("window.__demo && window.__demo.ready", timeout=20000)
    page.wait_for_timeout(1300)  # the camera's move into the view
    # the video's first frame: on the CPU renderer a frame of the room takes a few hundred
    # ms since the realism pass, so its load events come later than a fixed wait allows
    page.wait_for_function("document.getElementById('video').readyState >= 2", timeout=20000)
    return page, errors


def test_the_built_page_carries_no_html_comment():
    """index.html's comments are notes for whoever edits it; a visitor's view-source shows
    none of them."""
    assert "<!--" not in (DIST / "index.html").read_text()


@pytest.mark.parametrize("view", ["presenter", "engineer"])
@pytest.mark.parametrize(("w", "h"), [(1280, 720), (1600, 900)])
def test_the_alert_is_on_screen_and_the_pages_fit(browser, url, w, h, view):
    page, errors = _open(browser, url, w, h, view)
    page.evaluate(SEEK, 209)  # clipping before CVS from 203 s in the mock: an alert
    alert = page.evaluate(STATE)
    page.evaluate(SEEK, 320)  # bleeding from 317 s in the mock: never an alert
    s = page.evaluate(STATE)
    page.close()
    for seen in (alert, s):
        assert seen["readingsFit"] and seen["engineerFits"] and seen["toolsFit"], (
            f"a monitor's page overflows at {w}x{h} ({view})"
        )
    # A the video, B the tools (the engineer's page in the engineer
    # view), C the reading with the beacon; both views frame all three
    assert s["monitors"] == [True, True, True], f"a monitor is cut at {w}x{h} ({view})"
    assert s["readingsInView"], f"the reading (monitor C) is cut at {w}x{h} ({view})"
    if view == "engineer":
        assert s["engineerInView"] and not s["toolsShown"], f"monitor B at {w}x{h}"
    else:
        assert s["toolsInView"] and not s["engineerShown"], f"monitor B at {w}x{h}"
    assert alert["pillInView"] and alert["alertCardInView"] and alert["beacon"]
    # the bleeding flag, trained on labels a model wrote and never scored: raised in the ink of every value with "unscored", no red, no beacon
    assert s["unscoredInView"] and "unscored" in s["flags"] and s["unscoredCard"]
    assert not s["pillAlert"] and not s["alertCard"] and not s["beacon"]
    assert "poor visibility" not in s["flags"]  # an off flag is not shown
    assert s["videoReady"] >= 2
    assert errors == []


def test_off_flags_and_low_confidence(browser, url):
    page, errors = _open(browser, url, 1600, 900, "presenter")
    page.evaluate(SEEK, 470)
    quiet = page.evaluate(STATE)
    page.evaluate(SEEK, 292)  # the scripted backward call: confidence under the threshold
    low = page.evaluate(STATE)
    page.close()
    assert "no risk flags raised" in quiet["flags"] and not quiet["beacon"]
    assert "low" in low["phase"].split()
    assert errors == []


AHEAD = """() => {
  const shown = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).display !== 'none';
  const now = window.__demo.clock.now();
  const want = (s) => (s <= 0 ? 'due now' : s < 60 ? `in ${Math.ceil(s)} s` : `in ${Math.round(s / 60)} min`);
  const ahead = document.getElementById('lane-ahead'), nowLane = document.getElementById('lane-now');
  return {
    nowLeft: nowLane.getBoundingClientRect().right <= ahead.getBoundingClientRect().left,
    aheadText: ahead.innerText,
    sources: [...ahead.querySelectorAll('.src')].map((e) => e.textContent),
    phaseSources: [ahead.querySelector('h3 .src'), ahead.querySelector('.a-time .src')].map((e) => e && e.textContent),
    etas: [...document.querySelectorAll('.eta[data-due]')].filter(shown)
      .map((e) => [e.textContent.replace(/\\s+/g, ' ').trim(), want(Number(e.dataset.due) - now)]),
    stepShown: shown(document.getElementById('c-step')),
    step: document.getElementById('c-step').innerText,
    whyShown: shown(document.getElementById('lane-why')),
    nextOnRail: document.querySelectorAll('#b-rail i.next').length,
  };
}"""


@pytest.mark.parametrize("view", ["presenter", "engineer"])
def test_the_reading_leads_with_what_is_ahead(browser, url, view):
    """The screen is a navigation aid. The
    reading carries what is coming (the next phase with its time to go, the next
    instrument, the instruments' chance within five minutes), in the right column beside
    where it is now, each time counting down
    with the video and each item naming its source; the 30-second next step, which v1
    does not claim, is on the engineer's page alone."""
    page, errors = _open(browser, url, 1600, 900, view)
    page.evaluate(SEEK, 200)
    s = page.evaluate(AHEAD)
    page.close()
    # now on the left, what is ahead on the right, as the tools page
    assert s["nowLeft"], "where it is now sits left of what is ahead"
    assert "next phase" in s["aheadText"] and "Next instrument" in s["aheadText"]
    assert "Chance within 5 min" in s["aheadText"]
    assert "model" in s["sources"] and "training videos" in s["sources"]
    # the next phase is the table's and its time the model's: both names on the item
    assert s["phaseSources"] == ["training videos", "model"], s["phaseSources"]
    assert s["etas"] and all(got == want for got, want in s["etas"]), s["etas"]
    assert s["nextOnRail"] <= 1
    if view == "engineer":
        assert s["stepShown"] and "not a claimed capability" in s["step"] and not s["whyShown"]
    else:
        assert not s["stepShown"] and s["whyShown"]
    assert errors == []


POSE = """() => { const r = window.__demo.room, c = r.camera, f = c.getWorldDirection(new r.THREE.Vector3());
  return { yaw: r.yaw, max: r.yawMax, y: c.position.y, tilt: f.y, fov: c.fov,
           inset: document.getElementById('model-frame').style.opacity }; }"""

# the turn eases after the hand, a step a frame: wait until it has come to rest and a frame
# has been drawn since (the CPU renderer under `tenant` draws about one a second here)
SETTLE = """() => new Promise(done => { const room = window.__demo.room; let n = 0;
  room.onFrame(() => n++); const until = performance.now() + 20000;
  (function look() { if ((!room.moving && n > 0) || performance.now() > until) done();
    else setTimeout(look, 50); })(); })"""


def test_a_drag_turns_the_room_round_its_vertical_axis(browser, url):
    """A drag turns the room round the vertical axis through the
    view's centre, and nothing else; it holds within its limit, a double click faces the
    room again; turned, what stands in front of a screen hides it."""
    page, errors = _open(browser, url, 1280, 720, "presenter")
    page.evaluate(SEEK, 320)
    settle = lambda: page.evaluate(SETTLE)
    front = page.evaluate(POSE)
    page.mouse.move(640, 300)
    page.mouse.down()
    page.mouse.move(840, 300, steps=4)
    page.mouse.up()
    settle()
    turned = page.evaluate(POSE)
    page.mouse.move(200, 300)
    page.mouse.down()
    page.mouse.move(1250, 300, steps=6)  # far past the limit
    page.mouse.up()
    settle()
    held = page.evaluate(POSE)
    page.evaluate("() => { window.__demo.room.yaw = -0.45; }")  # the IV kit before monitor A
    settle()
    behind = page.evaluate(POSE)
    page.mouse.dblclick(640, 300)
    settle()
    again = page.evaluate(POSE)
    page.close()
    assert front["yaw"] == 0 and front["inset"] == ""
    # a drag to the right swings the camera to the left, round the view's centre
    assert -front["max"] < turned["yaw"] < -0.2
    for p in (turned, held, behind):
        assert p["y"] == pytest.approx(front["y"], abs=1e-6)  # no lift
        assert p["tilt"] == pytest.approx(front["tilt"], abs=1e-6)  # no tilt
        assert p["fov"] == front["fov"]  # no zoom
    assert held["yaw"] == pytest.approx(-held["max"], abs=1e-3)
    assert behind["inset"] == "0"
    assert again["yaw"] == 0 and again["inset"] == ""
    assert errors == []


COUNT = (
    "ms => new Promise(r => { const n0 = window.__n; setTimeout(() => r(window.__n - n0), ms); })"
)
HIDE = """on => { if (on) Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
  else delete document.hidden; document.dispatchEvent(new Event('visibilitychange')); }"""


def test_the_room_is_drawn_only_as_often_as_it_changes(browser, url):
    """A browser on the Spark's desktop drew the room
    every frame and took a fifth of the GPU from training. Paused, the room is drawn on a
    change and then not at all; playing, a few times a second; hidden, never; a
    recording (`frugal = false`) gets every frame."""
    page, errors = _open(browser, url, 1280, 720, "presenter")
    page.evaluate("() => { window.__n = 0; window.__demo.room.onFrame(() => window.__n++); }")
    page.evaluate(SEEK, 320)
    page.wait_for_timeout(1500)  # the eased lights settle
    still = page.evaluate(COUNT, 3000)
    page.evaluate("() => window.__demo.clock.seek(330)")
    seek = page.evaluate(COUNT, 3000)
    page.evaluate("() => window.__demo.clock.play()")
    page.wait_for_timeout(500)
    playing = page.evaluate(COUNT, 4000)
    page.evaluate(HIDE, True)
    page.wait_for_timeout(500)
    hidden = page.evaluate(COUNT, 3000)
    page.evaluate(HIDE, False)
    back = page.evaluate(COUNT, 3000)
    page.evaluate("() => window.__demo.clock.pause()")
    page.wait_for_timeout(2000)
    page.evaluate("() => { window.__demo.room.frugal = false; }")
    recording = page.evaluate(COUNT, 3000)
    page.close()
    assert still == 0
    assert 1 <= seek <= 10  # the change, then the lights settling
    assert 2 <= playing <= 18  # 4 a second at most (fewer on a CPU renderer)
    assert hidden == 0
    assert back >= 1
    assert recording >= 2
    assert errors == []


def test_the_owner_tab_signs_in_and_turns_ask_on(browser, url):
    """An Owner tab beside Presenter and Engineer asks for his
    password (no user name, no other address); signed in, Ask is on, and the tab signs
    him out again. A visitor sees no Ask box."""
    page, errors = _open(browser, url, 1600, 900, "presenter")
    tab, panel, pw = (
        page.locator("#owner-tab"),
        page.locator("#owner-panel"),
        page.locator("#owner-input"),
    )
    ask = page.locator("#ask-form")
    assert ask.is_hidden() and panel.is_hidden() and tab.get_attribute("aria-expanded") == "false"
    tabs = page.evaluate(
        "[...document.querySelectorAll('#tabs button')].map(b => b.textContent.trim())"
    )
    assert tabs == ["Presenter", "Engineer", "Owner"]
    tab.click()
    assert panel.is_visible() and tab.get_attribute("aria-expanded") == "true"
    assert pw.evaluate("e => e === document.activeElement")
    pw.press("Escape")  # put away, focus back on the tab
    assert panel.is_hidden() and tab.evaluate("e => e === document.activeElement")
    tab.click()
    pw.fill("wrong")
    pw.press("Enter")
    page.wait_for_function(
        "document.getElementById('owner-msg').textContent.includes('Wrong password')"
    )
    assert pw.get_attribute("aria-invalid") == "true" and pw.input_value() == "" and ask.is_hidden()
    pw.fill(PASSWORD)
    page.locator("#owner-submit").click()
    page.wait_for_function("!document.getElementById('ask-form').hidden")
    assert panel.is_hidden() and "on" in tab.get_attribute("class")
    assert page.evaluate("fetch('/api/me').then(r => r.json())") == {"owner": True}
    page.locator("#ask-input").fill("describe the scene")
    page.locator("#ask-form button").click()
    page.wait_for_function(
        "document.querySelector('#ask-log .qa div:last-child')?.textContent.includes('MOCK')"
    )
    tab.click()  # signed in: the panel says so and signs out
    assert page.locator("#owner-out").is_visible() and page.locator("#owner-form").is_hidden()
    page.locator("#owner-out").click()
    page.wait_for_function("document.getElementById('ask-form').hidden")
    assert panel.is_hidden() and "on" not in tab.get_attribute("class")
    assert page.locator("#ask-panel").is_hidden()
    assert page.evaluate("fetch('/api/me').then(r => r.json())") == {"owner": False}
    page.close()
    assert [e for e in errors if "status of 403" not in e] == []  # the wrong password's answer


TOOLS = """() => {
  const page = document.getElementById('screen-tools');
  const cols = [...page.querySelectorAll('.t-col')];
  const figs = (c) => [...c.querySelectorAll('.t-tool')].map((f) => ({
    name: f.querySelector('figcaption b').textContent,
    caption: f.querySelector('figcaption').textContent,
    pic: !!f.querySelector('img') && f.querySelector('img').naturalWidth > 0,
  }));
  const R = window.__demo.rollout, t = window.__demo.clock.now();
  const upto = R.decisions.filter((x) => x.t_frame <= t).map((x) => ({
    t: x.t_frame, now: x.state.tools_now, next: x.state.next_tool, fallback: !!x.fallback }));
  const d = upto[upto.length - 1];
  return { now: figs(cols[0]), next: figs(cols[1]), notes: cols.map((c) => c.querySelector('.t-empty')?.textContent ?? null),
           head: [...cols[1].querySelectorAll('h3 > span')].map((e) => e.textContent),
           rule: page.querySelector('.t-rule').getBoundingClientRect().height, height: page.getBoundingClientRect().height,
           callsShown: document.getElementById('c-calls').getClientRects().length > 0,
           state: { now: d.now }, upto };
}"""

CALLS = """() => {
  const el = document.getElementById('c-calls');
  const R = window.__demo.rollout, t = window.__demo.clock.now();
  const upto = R.decisions.filter((x) => x.t_frame <= t).map((x) => ({
    t: x.t_frame, now: x.state.tools_now, next: x.state.next_tool, fallback: !!x.fallback }));
  return { shown: el.getClientRects().length > 0, head: el.querySelector('h3 > span')?.textContent ?? null,
           cells: [...el.querySelectorAll('.c-calls-rows > *')].map((e) => e.textContent),
           note: el.querySelector('.muted')?.textContent ?? null, upto };
}"""


def _called(upto, window=180):
    """The model's own next-tool calls over the last three minutes,
    counted by type, a call left out once a later decision saw its tool; the two most
    called not in view, newest first on a tie; a reply that fell back not counted."""
    d = upto[-1]
    counts, seen = {}, set()
    for e in reversed(upto):
        if e["t"] < d["t"] - window:
            break
        call = (e["next"] or {}).get("tool")
        kind = call.split(":")[0] if call else None
        if not e["fallback"] and call and call != "none" and kind not in seen:
            counts[kind] = counts.get(kind, 0) + 1
        seen |= {x.split(":")[0] for x in e["now"] or []}
    now = {x.split(":")[0] for x in d["now"] or []}
    return sorted([kv for kv in counts.items() if kv[0] not in now], key=lambda kv: -kv[1])[:2]


def test_monitor_b_shows_the_tools_in_view_and_the_next_one(browser, url):
    """In the presenter view monitor B shows, left of a centre
    rule, the tools the model sees now and, right of it, the tools to come, each a
    picture of the instrument (drawn ahead of time from its 3D model) with its name under
    it; since 2026-11-22 the tools to come are the two the model called most over the last
    three minutes, tagged as the model's calls; since 2026-11-23 their counts are on the
    engineer's page alone."""
    page, errors = _open(browser, url, 1600, 900, "presenter")
    loaded = "[...document.querySelectorAll('#screen-tools img')].every((i) => i.complete)"
    seen = []
    for t in (40, 150, 260, 320, 420):
        page.evaluate(SEEK, t)
        page.wait_for_function(loaded, timeout=20000)
        seen.append(page.evaluate(TOOLS))
    page.close()
    for s in seen:
        now = s["state"]["now"]
        assert len(s["now"]) == len(now or []) and all(f["pic"] for f in s["now"] + s["next"])
        if not now:
            assert s["notes"][0] == ("none in view" if now == [] else "unknown")
        for f, tool in zip(s["now"], now or [], strict=True):  # in the reading's words
            assert f["name"].startswith(tool.split(":")[0].split("_")[0])
        want = _called(s["upto"])
        assert s["head"] == ["Next 3 min", "model’s calls"]
        assert len(s["next"]) == len(want)
        for f, (kind, _n) in zip(s["next"], want, strict=True):
            assert f["name"].startswith(kind.split("_")[0]) and "call" not in f["caption"]
        assert not s["callsShown"]  # the counts: the engineer's page alone
        if not want:
            assert s["notes"][1] == "no new tool called"
        assert s["rule"] > 0.8 * s["height"]  # the centre rule, top to bottom
    assert any(s["next"] for s in seen) and any(len(s["now"]) == 2 for s in seen)
    assert errors == []


def test_the_calls_are_counted_on_the_engineer_page(browser, url):
    """The call counts are on the engineer's view alone. The engineer's page gives monitor B's two called tools with their counts,
    by the same rule."""
    page, errors = _open(browser, url, 1600, 900, "engineer")
    seen = []
    for t in (150, 260, 420):
        page.evaluate(SEEK, t)
        seen.append(page.evaluate(CALLS))
    page.close()
    for s in seen:
        want = _called(s["upto"])
        assert s["shown"] and s["head"] == "Next 3 min · the model’s calls"
        names, counts = s["cells"][0::2], s["cells"][1::2]
        assert len(names) == len(want), (s["cells"], want)
        for name, count, (kind, n) in zip(names, counts, want, strict=True):
            assert (
                name.startswith(kind.split("_")[0]) and count == f"{n} call{'' if n == 1 else 's'}"
            )
        if not want:
            assert s["note"] == "no new tool called"
    assert any(s["cells"] for s in seen)
    assert errors == []


# api.md v1.5-v1.7: a run served with the self-probe hint, its checkpoint's gate in the header
UNFAMILIAR = range(301, 341)  # the mock decides at odd seconds: raised at 311


class HintedMock(mock.MockSource):
    """The mock's log as a run served with the hint would carry it."""

    def load(self, run, video_id):
        lines = [dict(x, api_version="1.7") for x in super().load(run, video_id)]
        lines[0] = dict(
            lines[0],
            hint={"probe": "probe-cvs-v1", "manifest_sha256": "b22c8d10", "threshold": 74.6455},
            checkpoint={
                "name": "stage2c-best", "manifest_sha256": "0f0f", "form": "gate",
                "gate": {"met": False, "line": "stage 2 gate NOT MET (the owner's written decision to proceed): triangle_cleared 0.74 vs 0.78 NOT met"},
            },
        )  # fmt: skip
        for i, x in enumerate(lines):
            if x["kind"] == "decision":
                far = x["t_frame"] in UNFAMILIAR
                h = {"familiarity": 120.0 if far else 26.4, "hint_shown": not far and x["seq"] > 0}
                if h["hint_shown"]:
                    h.update(two_structures=0.62, triangle_cleared=0.31, cystic_plate=0.12)
                lines[i] = dict(x, hint=h)
        return lines


@pytest.fixture(scope="module")
def hinted_url(tmp_path_factory):
    yield from _serve(tmp_path_factory, source=HintedMock)


HINT = """() => ({
  cvs: document.getElementById('lane-cvs').innerText,
  probes: [...document.querySelectorAll('#lane-cvs .probe')].filter(e => e.offsetParent !== null).map(e => e.textContent),
  model: document.getElementById('c-model').innerText,
  events: document.getElementById('events').innerText,
  readingsFit: document.getElementById('screen-b').scrollHeight <= document.getElementById('screen-b').clientHeight + 1,
  engineerFits: document.getElementById('screen-c').scrollHeight <= document.getElementById('screen-c').clientHeight + 1,
})"""


@pytest.mark.parametrize("view", ["presenter", "engineer"])
def test_the_vision_hint_and_the_model_on_the_engineers_view(browser, hinted_url, view):
    """The engineer view shows the probe's three numbers
    beside each criterion's name, labelled the probe's (a run without the served CVS shows
    no CVS reading), and names the checkpoint and its gate; the "unfamiliar scene" event is raised
    once the scene has been unfamiliar for 10 s; the presenter view shows no probe."""
    page, errors = _open(browser, hinted_url, 1600, 900, view)
    page.evaluate(SEEK, 200)
    seen = page.evaluate(HINT)
    page.evaluate(SEEK, 309)  # unfamiliar since 301: not yet 10 s
    early = page.evaluate(HINT)
    page.evaluate(SEEK, 320)
    far = page.evaluate(HINT)
    page.close()
    assert seen["readingsFit"] and seen["engineerFits"] and far["readingsFit"]
    if view == "engineer":
        assert seen["probes"] == ["probe 0.62", "probe 0.31", "probe 0.12"]
        assert "a linear probe on this frame; not the model's reading" in seen["cvs"]
        assert far["probes"] == ["probe –"] * 3 and "an unfamiliar scene" in far["cvs"]
        assert seen["model"].startswith("stage2c-best · gate not met")
        assert "triangle_cleared 0.74 vs 0.78 not met" in seen["model"]
        assert "(" not in seen["model"] and "owner" not in seen["model"]
    else:
        assert seen["probes"] == [] and "probe" not in seen["cvs"] and "probe" not in far["cvs"]
    assert "Unfamiliar scene" not in early["events"]
    assert "Unfamiliar scene: the footage is unlike the training videos" in far["events"]
    assert errors == []


class ServedMock(mock.MockSource):
    """The mock's log as a stateless run with the served CVS carries it (api.md v1.11,
    v1.12, v1.13): no hint; two_structures the reply's probability from 100 s,
    triangle_cleared the specialist's, the reverse of the reply's, cystic_plate the
    reply's own, unknown; the header with val's (made-up) reading of the choice."""

    def load(self, run, video_id):
        lines = [dict(x, api_version="1.13") for x in super().load(run, video_id)]
        lines[0] = dict(
            lines[0],
            decision_form={"name": "stateless", "reading": "each decision alone", "rows": "gate-blank/",
                           "served": True, "by": "the evaluation's ruling"},
            cvs_served={"choice": {"rows": "gate-blank"}, "criteria": {}, "val_reading": mock.VAL_READING},
            checkpoint={
                "name": "stage3-final", "manifest_sha256": "3b9e", "form": "gate",
                "gate": {"met": False, "line": "stage 3 gate NOT MET: next_step_top3_10_above_transition 0.6741 vs 0.7275 not met"},
            },
        )  # fmt: skip
        for i, x in enumerate(lines):
            if x["kind"] == "decision":
                reply = x["state"]["cvs"]
                lines[i] = dict(x, cvs_served={
                    "two_structures": {"value": int(x["t_frame"] >= 100), "source": "p1"},
                    "triangle_cleared": {"value": 1 - reply["triangle_cleared"], "source": "specialist"},
                    "cystic_plate": {"value": None, "source": "reply"},
                })  # fmt: skip
        return lines


@pytest.fixture(scope="module")
def served_url(tmp_path_factory):
    yield from _serve(tmp_path_factory, source=ServedMock)


SERVED = """() => {
  const st = [...document.querySelectorAll('#lane-cvs .cvs .item')];
  const colour = (e) => e && getComputedStyle(e).color;
  return {
    states: st.map(e => e.children[1].textContent),
    tags: [...document.querySelectorAll('#lane-cvs .src')].map(e => e.textContent),
    stColour: colour(document.querySelector('#lane-cvs .st')),
    ink: colour(st[0]?.children[0]),
    note: (document.getElementById('lane-cvs').innerText.match(/screening signal, not a confirmation/g) ?? []).length,
    noteLines: (() => { const n = document.querySelector('#lane-cvs .cvs-note'); if (!n) return 0;
      const r = document.createRange(); r.selectNodeContents(n); return r.getClientRects().length; })(),
    none: document.getElementById('lane-cvs').innerText.includes('no CVS reading in this run'),
    marked: document.querySelectorAll('#lane-cvs .box, #lane-cvs .when, [data-anchor^="cvs-"]:not([data-anchor="cvs-served"])').length,
    counted: /\\d\\s*(of|\\/)\\s*3/.test(document.getElementById('screen-b').innerText),
    engineer: [...document.querySelectorAll('#c-cvs .c-cvs-rows > *')].filter(e => e.offsetParent !== null).map(e => e.textContent),
    cvsFoot: [...document.querySelectorAll('#c-cvs .c-cvs-val')].filter(e => e.offsetParent !== null).map(e => e.textContent),
    cvsFits: (() => { const c = document.getElementById('c-cvs'); return c.scrollWidth <= c.clientWidth + 1; })(),
    marks: document.querySelectorAll('#timeline .marks .mark').length,
    flagMarks: [...document.querySelectorAll('#timeline .marks .mark')].filter(e => /at \\d/.test(e.title) && !/two structures|triangle cleared|cystic plate/.test(e.title)).length,
    model: document.getElementById('c-model').innerText,
    replies: document.querySelectorAll('#reply pre').length,
    replyCvs: [...document.querySelectorAll('#reply pre')].some(e => e.textContent.includes('"cvs"')),
    replyNote: [...document.querySelectorAll('#reply .reply-note')].filter(e => e.offsetParent !== null).map(e => e.textContent),
    readingsFit: document.getElementById('screen-b').scrollHeight <= document.getElementById('screen-b').clientHeight + 1
      && document.getElementById('screen-b').scrollWidth <= document.getElementById('screen-b').clientWidth + 1,
    engineerFits: document.getElementById('screen-c').scrollHeight <= document.getElementById('screen-c').clientHeight + 1,
  };
}"""

# every criterion at its widest ("possibly seen", "specialist"): each row stays one line and
# the board fits, the page put back as it was
WIDEST = """() => {
  const b = document.getElementById('screen-b');
  const items = [...document.querySelectorAll('#lane-cvs .cvs .item')];
  const keep = items.map(it => it.innerHTML);
  items.forEach(it => { it.children[1].outerHTML = '<span class="st">possibly seen</span>';
                        it.querySelector('.src').textContent = 'specialist'; });
  const h = items.map(it => it.offsetHeight), one = items[0].querySelector('.st').offsetHeight;
  const fits = b.scrollHeight <= b.clientHeight + 1;
  items.forEach((it, i) => { it.innerHTML = keep[i]; });
  return {oneLine: h.every(x => x < 1.6 * one), fits};
}"""


@pytest.mark.parametrize("view", ["presenter", "engineer"])
def test_the_served_cvs_is_a_screening_signal(browser, served_url, view):
    """Each served criterion is "not seen" or "possibly seen" (null
    unknown), in the ink of every value, with its source; one line says it is a screening
    signal, not a confirmation; no box, count, combined state, time or timeline mark; the
    engineer's page gives each criterion's served value and source, and val's figures; the
    engineer's view names the stateless form and that the gate was read in the trained
    form."""
    page, errors = _open(browser, served_url, 1600, 900, view)
    page.evaluate(SEEK, 80)
    early = page.evaluate(SERVED)
    page.evaluate(SEEK, 320)  # the reply has triangle_cleared from 167 s; bleeding from 317 s
    late = page.evaluate(SERVED)
    widest = page.evaluate(WIDEST)  # with the bleeding flag raised
    page.close()
    assert early["states"] == ["not seen", "possibly seen", "unknown"]
    assert late["states"] == ["possibly seen", "not seen", "unknown"]
    assert early["tags"] == late["tags"] == ["model p", "specialist", "model"]
    for seen in (early, late):
        assert seen["note"] == 1 and seen["noteLines"] == 1 and not seen["none"]
        assert seen["marked"] == 0 and not seen["counted"]
        assert seen["stColour"] == seen["ink"]  # the criterion's own ink: no colour of success
    assert late["marks"] == late["flagMarks"] and late["marks"] > 0  # the flags' marks stay
    assert early["readingsFit"] and late["readingsFit"] and late["engineerFits"]
    assert widest == {"oneLine": True, "fits": True}
    # the reply's own CVS is cut from the raw replies, and the pane says so: re-serialised,
    # so not the model's bytes
    assert late["replies"] > 0 and not late["replyCvs"]
    if view == "engineer":
        note = (
            'each reply re-serialised with its own "cvs" field removed, so not the model’s bytes: '
            "the CVS shown is the served one, below"
        )
        assert late["replyNote"] == [note]
        # val's figures beside the served values under the word "val" (api.md v1.13), two_structures' out of fold and marked so
        assert late["engineer"] == [
            "", "served", "source", "val precision", "val NPV", "val met",
            "two_structures", "1", "p1", "0.39†", "0.92†", "0.18",
            "triangle_cleared", "0", "specialist", "0.36", "0.95", "0.12",
            "cystic_plate", "null", "reply", "0.33", "0.96", "0.09",
        ]  # fmt: skip
        assert late["cvsFoot"] == ["val, on 1,200 labelled points of 12 videos · † out of fold"]
        assert late["cvsFits"]
        assert late["model"].startswith(
            "stage3-final · stateless · gate not met (in the trained form)"
        )
    else:
        assert late["engineer"] == [] and late["cvsFoot"] == []
    assert errors == []


@pytest.mark.parametrize("view", ["presenter", "engineer"])
def test_a_run_without_the_served_cvs_shows_no_cvs_reading(browser, url, view):
    """A run without `cvs_served` shows no CVS reading, as a
    missing field, never the reply's own CVS in its place; no CVS mark on the timeline."""
    page, errors = _open(browser, url, 1600, 900, view)
    page.evaluate(SEEK, 320)
    seen = page.evaluate(SERVED)
    page.close()
    assert seen["none"] and seen["states"] == [] and seen["tags"] == [] and seen["note"] == 0
    assert seen["marked"] == 0 and seen["engineer"] == []
    assert seen["marks"] == seen["flagMarks"] and seen["marks"] > 0
    assert errors == []


# step 2: a run still being written, followed through the socket
FOLLOW = """async (run) => {
  const d = window.__demo;
  await d.load(d.runs.findIndex((r) => r.run === run));
}"""

FOLLOWED = """() => {
  const R = window.__demo.rollout, conn = document.getElementById('conn');
  const ticks = R.decisions.map((d) => d.tick);
  return { following: R.following, ended: !!R.end, n: R.decisions.length, unique: new Set(ticks).size,
           ordered: ticks.every((t, i) => i === 0 || t > ticks[i - 1]), held: !!R.held,
           conn: conn.hidden ? null : conn.textContent, stamp: document.getElementById('b-stamp').innerText,
           playing: window.__demo.clock.playing, t: window.__demo.clock.now(),
           last: R.meta?.last_decision_t, label: document.getElementById('run').selectedOptions[0].text };
}"""


@pytest.fixture(scope="module")
def fast_url(tmp_path_factory):
    yield from _serve(tmp_path_factory, pace=0.03)  # the whole live run written in about 15 s


@pytest.fixture(scope="module")
def slow_url(tmp_path_factory):
    yield from _serve(tmp_path_factory, pace=3.0)  # the model three times slower than the video


def test_a_live_run_is_followed_through_a_dropped_socket_to_its_end(browser, fast_url):
    page, errors = _open(browser, fast_url, 1280, 720, "presenter")
    page.evaluate(FOLLOW, mock.WRITING)
    page.wait_for_function("window.__demo.rollout.decisions.length > 20", timeout=20000)
    first = page.evaluate(FOLLOWED)
    # every text the connection line shows, as it changes: the lost state lasts about a
    # second, and on the CPU renderer a frame-paced poll can step over it
    page.evaluate(
        """() => { const el = document.getElementById('conn'); window.__conn = [];
        new MutationObserver(() => window.__conn.push(el.textContent))
          .observe(el, { childList: true, characterData: true, subtree: true }); }"""
    )
    page.evaluate("window.__demo.dropSocket()")
    page.wait_for_function(
        "window.__conn.some((t) => t.startsWith('Connection lost'))", timeout=10000
    )
    page.wait_for_function("window.__demo.rollout.end !== null", timeout=40000)
    last = page.evaluate(FOLLOWED)
    page.close()
    n = sum(x["kind"] == "decision" for x in mock.generate("live"))
    assert first["following"] and first["conn"] == "Following live" and "live now" in first["label"]
    assert last["ended"] and not last["following"] and last["conn"] is None
    assert last["n"] == last["unique"] == n and last["ordered"]
    assert errors == []


def test_a_run_in_progress_waits_for_the_model_and_says_so(browser, slow_url):
    page, errors = _open(browser, slow_url, 1280, 720, "presenter")
    page.evaluate(FOLLOW, mock.WRITING_OFFLINE)
    page.wait_for_function("window.__demo.rollout.held === true", timeout=30000)
    held = page.evaluate(FOLLOWED)
    page.wait_for_function(
        f"window.__demo.rollout.meta.last_decision_t > {held['last']}", timeout=30000
    )
    page.wait_for_function(f"window.__demo.clock.now() > {held['t'] + 0.5}", timeout=10000)
    page.close()
    assert held["following"] and held["conn"] == "Following as it is written"
    assert "model computing" in held["stamp"] and not held["playing"]
    assert held["t"] == pytest.approx(held["last"] + mock.D)  # waiting at the last decision + D
    assert errors == []


PHONE = """() => {
  const r = id => document.getElementById(id).getBoundingClientRect();
  const room = window.__demo.room, stage = r('stage'), a = room.screenRect('A'), b = room.screenRect('B'), c = room.screenRect('C');
  const inside = q => q.left >= stage.left - 1 && q.right <= stage.right + 1 && q.top >= stage.top - 1 && q.bottom <= stage.bottom + 1;
  const bar = r('bar');
  const small = [...document.querySelectorAll('#topbar button, #hud button, #hud select, #ask-form input, #bar button, #bar #timeline, #owner-panel button, #owner-form input')]
    .filter(e => e.getClientRects().length && e.getBoundingClientRect().height < 44).map(e => e.id || e.textContent.trim());
  return {
    compact: room.compact, reading: document.getElementById('screen-b').parentElement.id,
    order: [stage.bottom <= r('flat').top + 1, r('flat').bottom <= r('hud').top + 1],
    sideways: document.documentElement.scrollWidth > innerWidth,
    bar: [...document.getElementById('bar').children].map(e => e.id),
    barInView: bar.top >= 0 && bar.bottom <= innerHeight + 1,
    aShare: a.width / stage.width, aIn: inside(a), bIn: inside(b), cIn: inside(c),
    nowFirst: r('lane-now').bottom <= r('lane-ahead').top + 1,
    card: [...document.querySelectorAll('#tool-card .t-col h3 span:first-child')].map(e => e.textContent),
    cardAboveRoom: r('tool-card').bottom <= stage.top + 1 && r('tool-card').top >= r('topbar').bottom - 1,
    cardPics: [...document.querySelectorAll('#tool-card img')].every(i => i.complete && i.naturalWidth > 0),
    pill: !!document.querySelector('#flat #lane-flags .pill.on.alert'),
    unscored: !!document.querySelector('#flat #lane-flags .pill.on.unscored'),
    alertFrame: document.getElementById('screen-b').classList.contains('alerting'),
    beacon: room.alerting, small,
  };
}"""


@pytest.mark.parametrize(("w", "h"), [(390, 844), (844, 390), (932, 430)])
def test_on_a_phone_the_reading_is_a_dashboard_under_the_room(browser, url, w, h):
    """On a phone the room's monitor B shows a generic page and
    the model's reading is a dashboard of its own under the room; play, the clock and
    the timeline sit at the screen's foot; every control takes a finger. Upright, the
    camera is on the endoscope monitor; a landscape phone (a large one included, past
    the 900 px width) frames the three monitors and the beacon. An alert lands on the
    dashboard and the beacon, the unscored bleeding flag on the dashboard alone (2026-11-22);
    the tools are a card above the room (2026-11-09); the dashboard reads now before what is
    ahead, as monitor C (2026-11-24)."""
    ctx = browser.new_context(viewport={"width": w, "height": h}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(url)
    page.wait_for_function("window.__demo && window.__demo.ready", timeout=20000)
    page.wait_for_function("document.getElementById('video').readyState >= 2", timeout=20000)
    page.evaluate(SEEK, 209)  # clipping before CVS from 203 s in the mock: an alert
    page.evaluate(SETTLE)
    s = page.evaluate(PHONE)
    page.evaluate(SEEK, 320)  # bleeding from 317 s in the mock: never an alert
    page.evaluate(SETTLE)
    bleed = page.evaluate(PHONE)
    ctx.close()
    assert s["compact"] and s["reading"] == "flat" and s["order"] == [True, True]
    assert s["nowFirst"]  # now, then what is ahead
    assert not s["sideways"] and s["bar"] == ["play", "clock", "timeline"] and s["barInView"]
    assert s["small"] == []
    assert s["pill"] and s["alertFrame"] and s["beacon"]
    assert (
        bleed["unscored"] and not bleed["pill"] and not bleed["alertFrame"] and not bleed["beacon"]
    )
    if w < h:
        assert s["aIn"] and s["aShare"] > 0.8  # the footage across the phone
    else:
        assert s["aIn"] and s["bIn"] and s["cIn"]  # the three monitors, the beacon on C
    # the tools above the room, then the rest
    assert s["card"] == ["Tools in view", "Next 3 min"] and s["cardAboveRoom"] and s["cardPics"]
    assert errors == []

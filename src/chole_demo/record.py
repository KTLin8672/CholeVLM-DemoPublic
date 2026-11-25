"""Record the screen to an H.264 file, rendered frame by frame.

python -m chole_demo record [--run RUN --video VIDEO] [--from T] [--seconds 120]

Headless Chromium draws the room with SwiftShader on the CPU, at a few frames a second
(about 3 at 1080p since the realism pass), too slow to capture in real time. So the page's clock is
Playwright's: time stands still between frames and jumps by 1/fps for each one (one
animation frame each), and the room's camera, beacon and animations keep their real
pace in the file. The video
is paused and seeked to each frame's time; the screen reads its time from the video,
as in playback.

Four things are set for the recording only, nothing else on the page:
- the video's frame callback is hidden, so three.js uploads the seeked frame on every
  render instead of waiting for a frame that a paused video never presents;
- the play button shows playing, as it does in the playback the file stands for;
- the room draws every animation frame (`room.frugal = false`): on a viewer's page it
  draws only a few frames a second while the video plays, and the
  file has thirty;
- the run is chosen through the page's own hook (`window.__demo.load`).

It reads the screen on loopback (the `chole-demo-screen` service) and writes
`recordings/` (gitignored) with a JSON sidecar: what was recorded, the commit, the hash.
A recording is a deliverable, so one of the same name is never recorded over without
`--replace`.

Beside a running training job it runs only through `python -m chole_demo tenant -- python
-m chole_demo record ...` (the CPU scope and the step canary).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from chole_demo.server import DEFAULT_PORT, REPO

RECORDINGS = REPO / "recordings"
VENV = Path(os.environ.get("VIRTUAL_ENV", Path.home() / ".virtualenvs" / "CholeVLMDemo"))

HIDE_FRAME_CALLBACK = "delete HTMLVideoElement.prototype.requestVideoFrameCallback;"

CHOOSE = """async ([run, video]) => {
  const runs = await (await fetch('/api/videos')).json();
  const i = runs.findIndex((r) => (!run || r.run === run) && (!video || r.video_id === video));
  if (i < 0) throw new Error('not listed: ' + run + ' ' + video);
  const d = window.__demo;
  await d.load(i);
  d.clock.pause();
  Object.defineProperty(d.clock, 'playing', { get: () => true });
  d.room.frugal = false;
  return { run: runs[i].run, video: runs[i].video_id, at: d.clock.t,
           duration: d.rollout.meta.duration_s };
}"""

SEEK = """async (t) => {
  const v = document.getElementById('video');
  window.__demo.clock.seek(t);
  if (v.seeking) await new Promise((r) => v.addEventListener('seeked', r, { once: true }));
}"""

SETTLE = """async () => {
  const waiting = [...document.images].filter((i) => i.src && !i.complete);
  await Promise.all(waiting.map((i) => new Promise((r) => {
    i.addEventListener('load', r, { once: true });
    i.addEventListener('error', r, { once: true });
  })));
  await document.fonts.ready;
}"""


def _commit() -> str:
    git = ["git", "-C", str(REPO)]
    out = subprocess.run([*git, "rev-parse", "--short", "HEAD"], check=True, capture_output=True)
    dirty = subprocess.run([*git, "diff", "--quiet", "HEAD"], check=False).returncode
    return out.stdout.decode().strip() + ("-dirty" if dirty else "")


def refuse_existing(out: Path, replace: bool) -> None:
    """Stop before a single frame is drawn when `out` exists and `--replace` was not given."""
    if out.exists() and not replace:
        raise SystemExit(f"{out} exists: pass --replace to record over it and its JSON file")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def record(
    run: str | None = None,
    video: str | None = None,
    start: float | None = None,
    seconds: float = 120.0,
    fps: int = 30,
    size: tuple[int, int] = (1920, 1080),
    view: str = "presenter",
    port: int = DEFAULT_PORT,
    out: Path | None = None,
    replace: bool = False,
) -> Path:
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(VENV / "ms-playwright"))
    from playwright.sync_api import sync_playwright

    url = f"http://127.0.0.1:{port}/" + ("?view=engineer" if view == "engineer" else "")
    w, h = size
    n = round(seconds * fps)
    RECORDINGS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h})
        page.add_init_script(HIDE_FRAME_CALLBACK)
        page.clock.install()
        page.goto(url)
        page.wait_for_function("window.__demo && window.__demo.ready", timeout=60_000)
        got = page.evaluate(CHOOSE, [run, video])
        t0 = got["at"] if start is None else start
        if t0 + seconds > got["duration"]:
            raise SystemExit(
                f"the video is {got['duration']} s long; {t0} + {seconds} runs past it"
            )
        name = f"{got['video'].replace(':', '_')}-{got['run']}-{t0:g}s-{seconds:g}s-{view}.mp4"
        out = out or RECORDINGS / name
        refuse_existing(out, replace)
        page.clock.pause_at(page.evaluate("Date.now()") + 1000)
        ffmpeg = subprocess.Popen(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                "-threads", "4", "-movflags", "+faststart", str(out),
            ],
            stdin=subprocess.PIPE,
        )  # fmt: skip
        began, ms = time.time(), 0
        for k in range(n):
            page.evaluate(SEEK, t0 + k / fps)
            target = round((k + 1) * 1000 / fps)
            page.clock.fast_forward(target - ms)  # one animation frame per file frame
            ms = target
            page.evaluate(SETTLE)
            ffmpeg.stdin.write(page.screenshot(type="jpeg", quality=95))
            if (k + 1) % (fps * 10) == 0:
                rate = (k + 1) / (time.time() - began)
                print(f"{(k + 1) / fps:.0f} s of {seconds:g} ({rate:.1f} frames/s)", flush=True)
        ffmpeg.stdin.close()
        if ffmpeg.wait() != 0:
            raise SystemExit("ffmpeg failed")
        browser.close()
    meta = {
        "file": out.name,
        "sha256": _sha256(out),
        "bytes": out.stat().st_size,
        "run": got["run"],
        "video_id": got["video"],
        "from_s": t0,
        "seconds": seconds,
        "fps": fps,
        "size": f"{w}x{h}",
        "view": view,
        "chole_demo": _commit(),
        "rendered": "frame by frame, headless Chromium (SwiftShader), page clock by Playwright",
        "render_s": round(time.time() - began, 1),
    }
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
    return out

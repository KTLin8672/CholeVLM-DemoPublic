"""Stored model outputs, replayed: the page with no model and no model server behind it.

    python -m chole_demo.feeds.replay VIDEO_ID PATH   # once a video: its picture, from your copy
    python -m chole_demo serve --source replay        # http://127.0.0.1:8781

What it reads, and the format of each (VIDEO is the video id with ':' as '_'):

- `replay/VIDEO.json`, in the repository: one video's model outputs, in the form the page
  reads from `GET /api/rollout`: `meta` (the run, the video, its duration and attribution),
  `decisions` (one a decision, each with its second `t_frame`), `dropped` and `end`. The two
  files there are the model's outputs on two validation videos; another video's outputs in
  the same form, in the same folder, are listed beside them.
- `runs/replay/video/VIDEO.mp4`, which you make: H.264, one frame a second, frame t being
  second t of the operation (the outputs' `t_frame`), 644x392.
- `runs/replay/frames/{current,video}/VIDEO/TTTTT.jpg`, which you make: second T as a JPEG,
  644x392 and 336x196 (the page's still frames and its "model saw" inset).

The repository carries no frame: the datasets' licence lets the demo show their frames, not
hand them out. So the picture is made from your own copy of the dataset, by the command
above. PATH is either a folder of the video's 1 fps frames (PNG or JPEG, each named with its
number; the smallest number is second 0, and a missing second repeats the one before it), or
the video file itself (sampled once a second from its start). The frame is the whole frame,
scaled and letterboxed; the model saw it cropped to the endoscope's view (its non-black part).

Asking the model needs a model: here a question is answered that no model is connected.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUTPUTS = REPO / "replay"
SIZES = {"current": (644, 392), "video": (336, 196)}
IMAGES = {".png", ".jpg", ".jpeg"}


def file_name(video_id: str) -> str:
    return video_id.replace(":", "_")


class ReplaySource:
    """The outputs in `replay/`, already in the page's form, with the picture made from the
    user's own copy of each video under `runs/replay/`."""

    screen_ready = True  # the server sends a stored rollout as it is

    def __init__(self, runs_dir: Path, outputs: Path = OUTPUTS) -> None:
        self.dir = runs_dir / "replay"
        self.outputs = outputs
        self._rollouts: dict[str, dict] | None = None

    def _all(self) -> dict[str, dict]:
        if self._rollouts is None:
            self._rollouts = {}
            for path in sorted(self.outputs.glob("*.json")):
                rollout = json.loads(path.read_text())
                self._rollouts[rollout["meta"]["video_id"]] = rollout
        return self._rollouts

    def missing(self) -> list[str]:
        """The listed videos whose picture is not made yet."""
        return [v for v in self._all() if not self._video(v).is_file()]

    def runs(self) -> list[dict]:
        out: dict[str, dict] = {}
        for video_id, rollout in self._all().items():
            meta = rollout["meta"]
            run = out.setdefault(
                meta["run"],
                {"run": meta["run"], "video_ids": [], "mode": meta["mode"],
                 "source": "replay", "status": "done", "sizes": {}},
            )  # fmt: skip
            run["video_ids"].append(video_id)
            run["sizes"][video_id] = len(rollout["decisions"])
        return list(out.values())

    def load(self, run: str, video_id: str) -> dict:
        rollout = self._all().get(video_id)
        if rollout is None or rollout["meta"]["run"] != run:
            raise KeyError(f"no stored outputs for {run}/{video_id}")
        return rollout

    def _video(self, video_id: str) -> Path:
        return self.dir / "video" / f"{file_name(video_id)}.mp4"

    def frame_path(self, video_id: str, t: int, variant: str) -> Path:
        if video_id not in self._all() or variant not in SIZES:
            raise KeyError(f"no frame {video_id}/{t} ({variant})")
        path = self.dir / "frames" / variant / file_name(video_id) / f"{t:05d}.jpg"
        if not path.is_file():
            raise KeyError(f"no frame {video_id}/{t} ({variant})")
        return path

    def video_path(self, video_id: str) -> Path:
        path = self._video(video_id)
        if video_id not in self._all() or not path.is_file():
            raise KeyError(f"no video {video_id}")
        return path

    def ask(self, run: str, video_id: str, t: float, question: str) -> dict:
        return {"error": "no_model", "detail": "stored outputs only: no model is connected"}


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        sys.exit("ffmpeg is needed to make the video: install it first")
    return path


def _number(path: Path) -> int | None:
    found = re.findall(r"\d+", path.stem)
    return int(found[-1]) if found else None


def _sequence(folder: Path, into: Path) -> tuple[str, int]:
    """The folder's frames as one image a second, 0 up, linked into `into`; a missing
    second repeats the one before it. Returns the ffmpeg input pattern and the count."""
    frames = {}
    for p in folder.iterdir():
        if p.suffix.lower() in IMAGES and (n := _number(p)) is not None:
            frames[n] = p
    if not frames:
        sys.exit(f"no numbered PNG or JPEG frame in {folder}")
    suffixes = {p.suffix.lower() for p in frames.values()}
    if len(suffixes) > 1:
        sys.exit(f"frames of more than one kind in {folder}: {', '.join(sorted(suffixes))}")
    ext = suffixes.pop()
    first, last = min(frames), max(frames)
    previous = frames[first]
    for t in range(last - first + 1):
        previous = frames.get(first + t, previous)
        (into / f"{t:05d}{ext}").symlink_to(previous.resolve())
    return str(into / f"%05d{ext}"), last - first + 1


def _fit(size: tuple[int, int]) -> str:
    w, h = size
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )


def make(video_id: str, source: Path, runs_dir: Path, outputs: Path = OUTPUTS) -> dict:
    """Make one video's picture under `runs_dir/replay/` from the user's own copy."""
    ffmpeg = _ffmpeg()
    out = runs_dir / "replay"
    name = file_name(video_id)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if source.is_dir():
            (tmp / "seq").mkdir()
            pattern, count = _sequence(source, tmp / "seq")
            given = ["-framerate", "1", "-start_number", "0", "-i", pattern]
            sample = ""
        elif source.is_file():
            given, sample, count = ["-i", str(source)], "fps=1,", None
        else:
            sys.exit(f"{source}: no such file or folder")

        def run(args: list[str]) -> None:
            subprocess.run([ffmpeg, "-loglevel", "error", "-y", *given, *args], check=True)

        run(
            ["-vf", sample + _fit(SIZES["current"]), "-an", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-r", "1", "-movflags", "+faststart", str(tmp / "v.mp4")]
        )  # fmt: skip
        for variant, size in SIZES.items():
            (tmp / variant).mkdir()
            run(["-vf", sample + _fit(size), "-q:v", "3", "-start_number", "0",
                 str(tmp / variant / "%05d.jpg")])  # fmt: skip
        made = len(list((tmp / "current").glob("*.jpg")))
        count = count or made
        (out / "video").mkdir(parents=True, exist_ok=True)
        shutil.move(tmp / "v.mp4", out / "video" / f"{name}.mp4")
        for variant in SIZES:
            target = out / "frames" / variant / name
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(tmp / variant, target)
    expected = None
    stored = outputs / f"{name}.json"
    if stored.is_file():
        expected = json.loads(stored.read_text())["meta"].get("duration_s")
    return {"video": video_id, "seconds": count, "outputs_seconds": expected}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m chole_demo.feeds.replay",
        description="make a video's picture for the replay from your own copy of it",
    )
    p.add_argument("video_id", help="as in replay/, e.g. cholec80:46")
    p.add_argument("path", type=Path, help="the video file, or a folder of its 1 fps frames")
    args = p.parse_args(argv)
    from chole_demo.server import RUNS

    done = make(args.video_id, args.path, RUNS)
    print(f"{done['video']}: {done['seconds']} s made under runs/replay/")
    if done["outputs_seconds"] is None:
        print("no stored outputs for this video in replay/: the page will not list it")
    elif abs(done["seconds"] - done["outputs_seconds"]) > 2:
        print(
            f"WARNING: the outputs cover {done['outputs_seconds']} s and the picture "
            f"{done['seconds']} s: is it the same video, from its start?"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

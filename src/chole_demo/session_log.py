"""JSON lines of every decision, kept for scoring the generated feed.

One file per run and video followed, `runs/sessions/<run>/<video>.jsonl` (gitignored):
each line is `{"received": <wall time>, "line": <the API line as it came>}`, the
header first and the end last. A line is written once: a server restarted midway
reads the file back and goes on after it. Lines read from the store when a follow
starts carry the time they were read, so a consumer measures latency from the
lines' own `t_response` and `t_frame_arrival` and reads `received` only for lines
that arrived live. The evaluation later receives the generated feed's file for its
scoring; nothing here is ever served.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".") or "_"


class SessionLog:
    def __init__(self, sessions_dir: Path, run: str, video_id: str) -> None:
        self.path = sessions_dir / _safe(run) / f"{_safe(video_id)}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[tuple] = set()
        if self.path.exists():
            for raw in self.path.read_text().splitlines():
                try:
                    self._seen.add(self._key(json.loads(raw)["line"]))
                except (ValueError, KeyError, TypeError):
                    continue

    @staticmethod
    def _key(line: dict) -> tuple:
        return line.get("kind"), line.get("tick")

    def write(self, line: dict) -> None:
        key = self._key(line)
        if key in self._seen:
            return
        self._seen.add(key)
        with self.path.open("a") as f:
            f.write(json.dumps({"received": round(time.time(), 3), "line": line}) + "\n")

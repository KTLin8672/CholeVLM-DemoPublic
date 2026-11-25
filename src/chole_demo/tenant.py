"""Heavy CPU work beside training, bounded.

python -m chole_demo tenant -- CMD ...

The GB10's memory bandwidth is shared by its CPU and its GPU, so the demo's CPU
rendering (headless Chromium on SwiftShader: the screen tests, the room's renders, a
recording) slows a training step as a GPU job does: on the evening of 2026-11-06
`stage2b`'s median step went from 120 s to 178 s while the room was being built. So
every such job runs through this, the way the rule says:

- in its own scope, `CPUQuota=400%`, `MemoryMax=8G`, no swap, at `nice 19` and OOM
  score 1000;
- training's step is read from its status file before and after and printed, for the
  log's row;
- it does not start while training runs a dev evaluation or a gate, and stops if one
  begins;
- the canary: the status file is read every 30 s, and once a new step has taken more
  than 1.25 times the median, the job is stopped (exit 75).

A light test (no browser) needs none of this. With no training job running, the job
runs in the same scope without the canary. The status file's path comes from
`ARTIFACT_ROOT` or from `configs/tenant.local.yaml` (`training_status:`, gitignored),
never from the code.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SCOPE = [
    "systemd-run", "--user", "--scope", "-q",
    "-p", "CPUQuota=400%", "-p", "MemoryMax=8G", "-p", "MemorySwapMax=0",
]  # fmt: skip
LOW = ["nice", "-n", "19", "choom", "-n", "1000", "--"]
LIMIT = 1.25
STOPPED = 75  # EX_TEMPFAIL: run it again later


def status_path() -> Path | None:
    root = os.environ.get("ARTIFACT_ROOT")
    if root:
        return Path(root).expanduser() / "status" / "train-spark.json"
    cfg = REPO / "configs" / "tenant.local.yaml"
    if cfg.exists():
        p = (yaml.safe_load(cfg.read_text()) or {}).get("training_status")
        if p:
            return Path(p).expanduser()
    return None


def read(path: Path | None) -> dict | None:
    try:
        return json.loads(path.read_text()) if path else None
    except (OSError, ValueError):
        return None


def training(s: dict | None) -> bool:
    return bool(s and s.get("busy"))


def held(s: dict | None) -> bool:
    """A dev evaluation or a gate: training's own memory peaks, never shared."""
    return training(s) and s.get("phase") not in (None, "training")


def say(s: dict | None, when: str) -> str:
    if not training(s):
        return f"training {when}: no job running"
    return (
        f"training {when}: {s.get('run')} step {s.get('step')}, last {s.get('last_step_s')} s,"
        f" median {s.get('step_s_median')} s ({s.get('updated')})"
    )


def run(
    cmd: list[str], path: Path | None = None, *, scoped: bool = True, poll: float = 30.0
) -> int:
    path = path if path is not None else status_path()
    if path is None:
        print("tenant: no status file (set ARTIFACT_ROOT or configs/tenant.local.yaml)")
        return 2
    before = read(path)
    print(say(before, "before"), flush=True)
    if held(before):
        print(f"tenant: training is in its {before.get('phase')}; not starting")
        return STOPPED
    unit = f"chole-demo-tenant-{os.getpid()}"
    prefix = (SCOPE + ["--unit", unit] + LOW) if scoped else []
    proc = subprocess.Popen(prefix + cmd, start_new_session=True)
    seen = before.get("step") if before else None
    why = None
    while proc.poll() is None:
        try:
            proc.wait(timeout=poll)
            break
        except subprocess.TimeoutExpired:
            pass
        s = read(path)
        if held(s):
            why = f"training began its {s.get('phase')}"
        elif training(s) and s.get("step") != seen:
            seen = s.get("step")
            last, median = s.get("last_step_s"), s.get("step_s_median")
            if last and median and last > LIMIT * median:
                why = f"step {seen} took {last} s, over {LIMIT} x the median {median} s"
        if why:
            print(f"tenant: stopping: {why}", flush=True)
            if scoped:
                subprocess.run(["systemctl", "--user", "stop", f"{unit}.scope"], check=False)
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            break
    print(say(read(path), "after"), flush=True)
    return STOPPED if why else proc.returncode

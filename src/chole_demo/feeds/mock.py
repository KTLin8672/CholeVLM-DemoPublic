"""The mock feed: made-up decision logs in chole-eval's API v0.1 shapes.

The screen is built against this until chole-eval serves its
API. The lines follow `chole-eval/docs/api.md` v0.1 (the header, decision,
dropped and end lines; the State, Delay, Outlook, Event and Memory objects).
Every value is invented: no label table, prior file, frame shard or video of
the project is read, and the frames are an ffmpeg test pattern. Nothing
produced here is ever reported.

Two runs of one made-up video: `offline` (every tick computed, nothing
dropped) and `live` (wall-clock ticks, the busy ones written as dropped lines).

    python -m chole_demo mock      # writes runs/mock/ and prints the hashes
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import shutil
import statistics
import subprocess
import time
from pathlib import Path

API_VERSION = "1.0"
CHECKPOINT = "mock"
STAMP = "20261105T000000"
VIDEO_ID = "mock:01"  # not a split id: the real server would refuse it
D = 2  # the decision clock, s of video time; ticks at t = 1 + tick * D
N_FRAMES = 480  # frames t = 0..479 at 1 fps
SEED = 5
WALL0 = 1_793_900_000.0  # a fixed wall clock, so the logs are deterministic
THRESHOLDS = {
    "low_phase_conf": 0.5,
    "phase_backward_p": 0.05,
    "dropped_rate": 0.2,
    "dropped_window": 30,
    "event_hold_s": 60,
}
FLICKER_S = 10
K_STATES = 8
TOOLS_BIN_S = 30
MODES = ("offline", "live")


def run_id(mode: str) -> str:
    return f"{CHECKPOINT}-{mode}-D{D}-{STAMP}"


# the two logs again as runs still being written (step 2), their lines coming out over
# time, `pace` wall seconds to a second: the live one each line when live has it; the
# offline one as fast as the model goes, one decision after another's compute
WRITING = f"{run_id('live')}-writing"
WRITING_OFFLINE = f"{run_id('offline')}-writing"
WRITING_MODES = {WRITING: "live", WRITING_OFFLINE: "offline"}


def _release_s(lines: list[dict], mode: str) -> list[float]:
    """When each body line is written, in seconds from the run's start."""
    t_first = min(x["t_frame"] for x in lines)
    out, busy = [], 0.0
    for x in lines:
        if mode == "offline":
            busy += x["encode_s"] + x["compute_s"] if x["kind"] == "decision" else 0.0
            out.append(busy)
        elif x["kind"] == "decision":
            out.append(x["t_frame"] + x["encode_s"] + x["compute_s"] - t_first)
        else:
            out.append(x["t_frame"] - t_first)
    return out


PHASES = [
    "Preparation",
    "CalotTriangleDissection",
    "ClippingCutting",
    "GallbladderDissection",
    "GallbladderPackaging",
    "CleaningCoagulation",
    "GallbladderRetraction",
]
TOOLS = [
    "grasper",
    "clipper",
    "scissors",
    "energy",
    "suction_irrigation",
    "specimen_bag",
    "stapler",
    "other",
]
FLAGS = ["bleeding", "clipping_before_cvs", "poor_visibility"]
CVS = ["two_structures", "triangle_cleared", "cystic_plate"]

# The mock procedure: (phase, duration s), 480 s in all, made up.
SCHEDULE = [
    ("Preparation", 30),
    ("CalotTriangleDissection", 170),
    ("ClippingCutting", 60),
    ("GallbladderDissection", 110),
    ("GallbladderPackaging", 35),
    ("CleaningCoagulation", 45),
    ("GallbladderRetraction", 30),
]

# Tools in view per phase, as (tool, start fraction, end fraction) of the phase.
PHASE_TOOLS = {
    "Preparation": [("grasper", 0.2, 1.0)],
    "CalotTriangleDissection": [("grasper", 0.0, 1.0), ("energy:hook", 0.1, 0.95)],
    "ClippingCutting": [("grasper", 0.0, 1.0), ("clipper", 0.05, 0.6), ("scissors", 0.65, 0.95)],
    "GallbladderDissection": [("grasper", 0.0, 1.0), ("energy:hook", 0.05, 0.9)],
    "GallbladderPackaging": [("grasper", 0.0, 1.0), ("specimen_bag", 0.15, 1.0)],
    "CleaningCoagulation": [
        ("grasper", 0.0, 1.0),
        ("suction_irrigation", 0.0, 0.7),
        ("energy:bipolar", 0.6, 1.0),
    ],
    "GallbladderRetraction": [("grasper", 0.0, 1.0), ("specimen_bag", 0.0, 0.8)],
}

# Next steps per phase, as (fraction of the phase, verb, target).
PHASE_STEPS = {
    "Preparation": [(0.5, "retract", "gallbladder")],
    "CalotTriangleDissection": [
        (0.1, "dissect", "cystic_duct"),
        (0.4, "dissect", "cystic_artery"),
        (0.75, "dissect", "cystic_plate"),
    ],
    "ClippingCutting": [
        (0.05, "clip", "cystic_duct"),
        (0.35, "clip", "cystic_artery"),
        (0.65, "cut", "cystic_duct"),
        (0.8, "cut", "cystic_artery"),
    ],
    "GallbladderDissection": [(0.05, "dissect", "gallbladder"), (0.6, "coagulate", "liver")],
    "GallbladderPackaging": [(0.2, "pack", "gallbladder")],
    "CleaningCoagulation": [(0.05, "aspirate", "fluid"), (0.6, "coagulate", "liver")],
    "GallbladderRetraction": [(0.1, "retract", "specimen_bag")],
}

# Made-up stand-ins for the serving priors (GET /api/priors). Not fitted on anything.
MOCK_NEXT_PHASE = {
    "Preparation": {"CalotTriangleDissection": 0.93, "GallbladderDissection": 0.07},
    "CalotTriangleDissection": {"ClippingCutting": 0.9, "GallbladderDissection": 0.1},
    "ClippingCutting": {"GallbladderDissection": 0.88, "CalotTriangleDissection": 0.12},
    "GallbladderDissection": {"GallbladderPackaging": 0.7, "CleaningCoagulation": 0.3},
    "GallbladderPackaging": {"CleaningCoagulation": 0.75, "GallbladderRetraction": 0.25},
    "CleaningCoagulation": {"GallbladderRetraction": 0.85, "GallbladderPackaging": 0.15},
    "GallbladderRetraction": {"CleaningCoagulation": 0.6, "GallbladderPackaging": 0.4},
}
MOCK_TOOLS_300S = {
    "Preparation": {"grasper": 0.97, "energy": 0.8, "suction_irrigation": 0.12},
    "CalotTriangleDissection": {"grasper": 0.98, "energy": 0.9, "clipper": 0.55, "scissors": 0.3},
    "ClippingCutting": {"grasper": 0.95, "scissors": 0.85, "energy": 0.6, "clipper": 0.5},
    "GallbladderDissection": {"grasper": 0.96, "energy": 0.88, "specimen_bag": 0.45},
    "GallbladderPackaging": {"specimen_bag": 0.9, "grasper": 0.85, "suction_irrigation": 0.4},
    "CleaningCoagulation": {"suction_irrigation": 0.8, "energy": 0.6, "grasper": 0.7},
    "GallbladderRetraction": {"grasper": 0.9, "specimen_bag": 0.75, "other": 0.2},
}
MOCK_DURATION = {  # phase: (median s, 90th percentile s), made up
    "Preparation": (35, 70),
    "CalotTriangleDissection": (120, 150),
    "ClippingCutting": (55, 100),
    "GallbladderDissection": (100, 180),
    "GallbladderPackaging": (35, 70),
    "CleaningCoagulation": (40, 90),
    "GallbladderRetraction": (30, 60),
}

# The event kinds of api.md v0.1: severity, field, wording (verbatim).
EVENT_KINDS = {
    "poor_visibility": (
        "warn",
        "risk_flags.poor_visibility",
        (
            "Poor visibility: blur, smoke, lens on tissue or out of body "
            "(the model's one flag for all of them)."
        ),
    ),
    "blood": ("info", "blood", "Blood in view: present."),
    "active_bleeding": ("alert", "risk_flags.bleeding", "Active bleeding."),
    "clipping_before_cvs": (
        "alert",
        "risk_flags.clipping_before_cvs",
        (
            "Clipping before the critical view of safety is achieved. This is the nearest "
            "label to an unsafe step; the model has no label for a bad cut."
        ),
    ),
    "low_phase_conf": ("info", "phase_conf", "Uncertain phase: confidence below the threshold."),
    "phase_backward": (
        "warn",
        "phase",
        "Unexpected phase order: the phase moved against the usual sequence.",
    ),
    "phase_running_long": (
        "info",
        "phase",
        "Phase running long: past the 90th percentile of its usual duration.",
    ),
    "fallback": ("warn", "reply", "The model's output was invalid; the previous state is shown."),
    "decisions_dropped": ("warn", "delay", "The model is behind: decisions are being dropped."),
}
BLOOD_SIGNIFICANT = ("warn", "Blood in view: significant.")

# Scripted mock moments, in s of video time.
SMOKE = (119, 135)
BLOOD = (299, 361)
BLEEDING = (317, 331)
BACKWARD = (289, 295)
CVS_AT = {"two_structures": 141, "triangle_cleared": 167, "cystic_plate": 211}


def _val_figures(precision: float, npv: float, met: float, calls1: int, calls0: int) -> dict:
    labelled = calls1 + calls0
    return {
        "precision": {
            "value": precision,
            "ci": [precision - 0.05, precision + 0.05],
            "calls": calls1,
        },
        "npv": {"value": npv, "ci": [npv - 0.01, min(1.0, npv + 0.01)], "calls": calls0},
        "met_share": {"value": met, "positives": round(met * labelled), "labelled": labelled},
        "points": labelled,
        "videos": 12,
    }


# api.md v1.13's `val_reading` in its shape, made up like everything here: the
# figures a test draws beside a served CVS; nothing here is read from a report
VAL_READING = {
    "report": "reports/results.json",
    "sha256": "made-up",
    "section": "cvs_claim val/stateless",
    "split": "val",
    "commits": {"chole-eval": "made-up"},
    "note": "made-up figures for the mock",
    "criteria": {
        "two_structures": _val_figures(0.41, 0.93, 0.18, 310, 890),
        "triangle_cleared": _val_figures(0.36, 0.95, 0.12, 250, 950),
        "cystic_plate": _val_figures(0.33, 0.96, 0.09, 220, 980),
    },
    "out_of_fold": {"two_structures": _val_figures(0.39, 0.92, 0.18, 330, 870)},
}
FALLBACK_AT = {151, 403}
SLOW = (365, 415)


def _phase_bounds() -> list[tuple[str, int, int]]:
    out, t = [], 0
    for name, dur in SCHEDULE:
        out.append((name, t, t + dur))
        t += dur
    return out


BOUNDS = _phase_bounds()
TOOL_INTERVALS = [
    (tool, a + fa * (b - a), a + fb * (b - a))
    for name, a, b in BOUNDS
    for tool, fa, fb in PHASE_TOOLS[name]
]
STEP_TIMES = [
    (a + f * (b - a), verb, target)
    for name, a, b in BOUNDS
    for f, verb, target in PHASE_STEPS[name]
]


def _scene(t: int) -> tuple[str, int, int]:
    for name, a, b in BOUNDS:
        if a <= t < b:
            return name, a, b
    return BOUNDS[-1]


def _tools_at(t: int) -> list[str]:
    return sorted({tool for tool, a, b in TOOL_INTERVALS if a <= t < b})


def _base(tool: str) -> str:
    return tool.split(":")[0]


def _next_tool(t: int, horizon: int = 30) -> dict:
    now = {_base(x) for x in _tools_at(t)}
    for tool, a, _ in sorted(TOOL_INTERVALS, key=lambda x: x[1]):
        if t < a <= t + horizon and _base(tool) not in now:
            return {"tool": _base(tool), "within_s": round(a - t)}
    return {"tool": "none"}


def _next_step(t: int, horizon: int = 30) -> dict:
    for at, verb, target in STEP_TIMES:
        if t < at <= t + horizon:
            return {"verb": verb, "target": target, "within_s": round(at - t)}
    return {"verb": "continue"}


def _bucket(s: float) -> str:
    if s < 30:
        return "<30s"
    if s < 120:
        return "30-120s"
    if s < 300:
        return "2-5min"
    return ">5min"


def _rationale(phase: str, cvs: dict, tools: list[str], flags: dict) -> str:
    done = [k.replace("_", " ") for k, v in cvs.items() if v]
    parts = [f"{phase} under way"]
    parts.append(f"{', '.join(done)} achieved" if done else "critical view not yet achieved")
    if tools:
        parts.append(f"{', '.join(_base(x) for x in tools)} in view")
    if flags["poor_visibility"]:
        parts.append("view obscured")
    if flags["bleeding"]:
        parts.append("active bleeding")
    return "; ".join(parts) + "."


def _model(t: int, rng: random.Random) -> tuple[dict, dict]:
    """The packed contract as the mock model emits it, and the server's confidences."""
    phase, a, b = _scene(t)
    conf = 0.86 + 0.1 * rng.random()
    if t - a < 4:
        conf = 0.55 + 0.15 * rng.random()  # just after a transition
    if SMOKE[0] <= t < SMOKE[1]:
        conf = 0.38 + 0.08 * rng.random()
    if BACKWARD[0] <= t < BACKWARD[1]:
        phase, conf = "ClippingCutting", 0.46
    remaining = max(0.0, b - t + rng.gauss(0, 6))
    cvs = {k: int(t >= CVS_AT[k]) for k in CVS}
    tools = _tools_at(t)
    flags = {
        "bleeding": int(BLEEDING[0] <= t < BLEEDING[1]),
        "clipping_before_cvs": int("clipper" in tools and not all(cvs.values())),
        "poor_visibility": int(SMOKE[0] <= t < SMOKE[1]),
    }
    nt = _next_tool(t)
    if nt["tool"] != "none" and rng.random() < 0.15:  # a wrong call now and then
        nt = {**nt, "tool": rng.choice([x for x in TOOLS if x != nt["tool"]])}
    blood = "none"
    if BLOOD[0] <= t < BLOOD[1]:
        blood = "significant" if BLEEDING[0] <= t < BLEEDING[1] else "present"
    packed = {
        "t": t,
        "phase": phase,
        "phase_remaining": {"bucket": _bucket(remaining), "estimate_s": round(remaining)},
        "tools_now": tools,
        "next_tool": nt,
        "cvs": cvs,
        "risk_flags": flags,
        "blood": blood,
        "next_step": _next_step(t),
        "rationale": _rationale(phase, cvs, tools, flags),
    }
    confs = {
        "phase_conf": round(conf, 3),
        "tools_now_conf": {_base(x): round(0.8 + 0.19 * rng.random(), 3) for x in tools},
        "next_tool": round(0.5 + 0.4 * rng.random(), 3),
        "next_step": round(0.45 + 0.4 * rng.random(), 3),
    }
    return packed, confs


def _complete(packed: dict, confs: dict) -> dict:
    """What the server adds to the packed contract (api.md v0.1, State)."""
    s = copy.deepcopy(packed)
    s["phase_conf"] = confs["phase_conf"]
    s["tools_now_conf"] = confs["tools_now_conf"]
    s["next_tool"]["conf"] = confs["next_tool"]
    s["next_step"]["conf"] = confs["next_step"]
    s["risk_flags_shown"] = [f for f in FLAGS if s["risk_flags"][f] == 1]
    return s


class _Memory:
    """The running memory of api.md v0.1."""

    def __init__(self) -> None:
        self.segments: list[dict] = []  # phase, start_t, end_t (smoothed by FLICKER_S)
        self.candidate: tuple[str, int] | None = None
        self.tools_seen: dict[str, dict] = {}
        self.cvs_first: dict[str, int | None] = {k: None for k in CVS}
        self.flags: dict[str, list[list]] = {f: [] for f in FLAGS}
        self.last_states: list[dict] = []
        self.predictions: list[dict] = []
        self.scored: list[dict] = []
        self.nt_hits = 0
        self.nt_n = 0
        self.remaining_err: list[float] = []

    def _phase(self, t: int, phase: str) -> bool:
        """Smooth the model's calls; True when a new segment opened."""
        if not self.segments:
            self.segments.append({"phase": phase, "start_t": t, "end_t": None})
            return True
        if phase == self.segments[-1]["phase"]:
            self.candidate = None
            return False
        if self.candidate is None or self.candidate[0] != phase:
            self.candidate = (phase, t)
        new, since = self.candidate
        if t - since < FLICKER_S:
            return False
        self.segments[-1]["end_t"] = since
        self.segments.append({"phase": new, "start_t": since, "end_t": None})
        self.candidate = None
        return True

    def update(self, seq: int, t: int, s: dict) -> None:
        if self._phase(t, s["phase"]) and len(self.segments) > 1:
            change = self.segments[-1]["start_t"]
            for p in self.predictions:
                if p["kind"] == "phase_remaining" and p["outcome"] == "pending":
                    err = change - (p["made_t"] + p["value"]["estimate_s"])
                    p.update(outcome="scored", error_s=err)
                    self.remaining_err.append(abs(err))
        for tool in s["tools_now"]:
            seen = self.tools_seen.setdefault(_base(tool), {"first_t": t, "last_t": t})
            seen["last_t"] = t
        for k in CVS:
            if s["cvs"][k] == 1 and self.cvs_first[k] is None:
                self.cvs_first[k] = t
        for f in FLAGS:
            spans = self.flags[f]
            on = s["risk_flags"][f] == 1
            if on and (not spans or spans[-1][1] is not None):
                spans.append([t, None])
            if not on and spans and spans[-1][1] is None:
                spans[-1][1] = t
        bases = {_base(x) for x in s["tools_now"]}
        for p in self.predictions:
            if p["kind"] != "next_tool" or p["outcome"] != "pending":
                continue
            if p["value"]["tool"] in bases:
                p["outcome"] = "hit"
            elif t >= p["due_t"]:
                p["outcome"] = "miss"
            if p["outcome"] != "pending":
                self.nt_hits += p["outcome"] == "hit"
                self.nt_n += 1
        if s["next_tool"]["tool"] != "none":
            value = {"tool": s["next_tool"]["tool"], "within_s": s["next_tool"]["within_s"]}
            self._predict(seq, t, "next_tool", value, t + 30)
        if t % 30 == 1:  # one remaining-time call every 30 s keeps the list short
            est = s["phase_remaining"]["estimate_s"]
            self._predict(seq, t, "phase_remaining", {"estimate_s": est}, t + est)
        done = [p for p in self.predictions if p["outcome"] != "pending"]
        self.scored = (self.scored + done)[-5:]
        self.predictions = [p for p in self.predictions if p["outcome"] == "pending"]
        self.last_states = (self.last_states + [s])[-K_STATES:]

    def _predict(self, seq: int, t: int, kind: str, value: dict, due: int) -> None:
        self.predictions.append(
            {
                "made_seq": seq,
                "made_t": t,
                "kind": kind,
                "value": value,
                "due_t": due,
                "outcome": "pending",
            }
        )

    def snapshot(self, t: int) -> dict:
        timeline = []
        for seg in self.segments:
            end = seg["end_t"] if seg["end_t"] is not None else t
            median, _ = MOCK_DURATION[seg["phase"]]
            elapsed = end - seg["start_t"]
            timeline.append(
                {**seg, "elapsed_s": float(elapsed), "pace": round(elapsed / median, 3)}
            )
        cur = self.segments[-1]
        median, p90 = MOCK_DURATION[cur["phase"]]
        elapsed = t - cur["start_t"]
        errs = self.remaining_err
        return {
            "t": t,
            "phase_timeline": timeline,
            "current_phase": {
                "phase": cur["phase"],
                "start_t": cur["start_t"],
                "elapsed_s": float(elapsed),
                "prior_median_s": float(median),
                "prior_p90_s": float(p90),
                "pace": round(elapsed / median, 3),
            },
            "tools_seen": copy.deepcopy(self.tools_seen),
            "cvs_first_achieved": dict(self.cvs_first),
            "flags": copy.deepcopy(self.flags),
            "last_states": copy.deepcopy(self.last_states),
            "predictions": copy.deepcopy(self.scored + self.predictions),
            "self_consistency": {
                "next_tool": {
                    "n": self.nt_n,
                    "hit_rate": round(self.nt_hits / self.nt_n, 3) if self.nt_n else None,
                },
                "next_step": {"n": 0, "hit_rate": None},
                "phase_remaining": {
                    "n": len(errs),
                    "mae_s": round(statistics.fmean(errs), 1) if errs else None,
                },
            },
        }


class _Events:
    """The event box of api.md v0.1, with its default hold rule: visible until
    event_hold_s after t_raised or while the condition holds, whichever is later."""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def update(self, t: int, holding: dict[str, object]) -> list[dict]:
        hold = THRESHOLDS["event_hold_s"]
        open_ = {e["kind"]: e for e in self.entries if e["t_cleared"] is None}
        for kind, value in holding.items():
            severity, field, wording = EVENT_KINDS[kind]
            if kind == "blood" and value == "significant":
                severity, wording = BLOOD_SIGNIFICANT
            e = open_.get(kind)
            if e is None:
                self.entries.append(
                    {
                        "id": f"{VIDEO_ID}/{kind}/{t}",
                        "kind": kind,
                        "severity": severity,
                        "field": field,
                        "value": value,
                        "t_raised": t,
                        "t_last": t,
                        "t_cleared": None,
                        "visible": True,
                        "wording": wording,
                    }
                )
            else:
                e.update(t_last=t, value=value, severity=severity, wording=wording)
        for kind, e in open_.items():
            if kind not in holding:
                e["t_cleared"] = t
        for e in self.entries:
            e["visible"] = e["t_cleared"] is None or t < e["t_raised"] + hold
        self.entries = [e for e in self.entries if e["visible"]]
        return sorted(copy.deepcopy(self.entries), key=lambda e: -e["t_raised"])


# The fields of the reply as the model packs it (api.md v1.0 previous_state): the
# server-completed ones (phase_conf, tools_now_conf, risk_flags_shown) left out.
PACKED = (
    "t",
    "phase",
    "phase_remaining",
    "tools_now",
    "next_tool",
    "cvs",
    "risk_flags",
    "blood",
    "next_step",
    "rationale",
)


def _outlook(phase: str, elapsed: float, next_tool: str, in_view: set[str]) -> dict:
    median, _ = MOCK_DURATION[phase]
    tools = dict(MOCK_TOOLS_300S[phase])
    if elapsed > median:  # late in the phase: lean toward the next phase's tools
        following = max(MOCK_NEXT_PHASE[phase].items(), key=lambda kv: kv[1])[0]
        for tool, p in MOCK_TOOLS_300S[following].items():
            tools[tool] = round(max(tools.get(tool, 0.0), 0.5 * tools.get(tool, 0.0) + 0.5 * p), 3)
    nxt = sorted(MOCK_NEXT_PHASE[phase].items(), key=lambda kv: -kv[1])
    ranked = sorted(tools.items(), key=lambda kv: -kv[1])
    return {
        "next_phase": [{"phase": p, "p": v} for p, v in nxt],
        "tools_300s": [
            {"tool": x, "p": v, "model_next_tool": x == next_tool, "in_view": x in in_view}
            for x, v in ranked
        ],
        "elapsed_bin_s": int(elapsed // TOOLS_BIN_S) * TOOLS_BIN_S,
    }


def _quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * len(s)))]


def _holding(state: dict, prev: dict | None, mem: dict, fallback: bool, ticks: list[bool]):
    """The conditions of the event kinds that hold at this decision."""
    h: dict[str, object] = {}
    flags = state["risk_flags"]
    if flags["poor_visibility"] == 1:
        h["poor_visibility"] = 1
    if state["blood"] in ("present", "significant"):
        h["blood"] = state["blood"]
    if flags["bleeding"] == 1:
        h["active_bleeding"] = 1
    if flags["clipping_before_cvs"] == 1:
        h["clipping_before_cvs"] = 1
    if state["phase_conf"] < THRESHOLDS["low_phase_conf"]:
        h["low_phase_conf"] = state["phase_conf"]
    if prev is not None and state["phase"] != prev["state"]["phase"]:
        p = MOCK_NEXT_PHASE[prev["state"]["phase"]].get(state["phase"], 0.0)
        if p < THRESHOLDS["phase_backward_p"]:
            h["phase_backward"] = state["phase"]
    cur = mem["current_phase"]
    if cur["elapsed_s"] > cur["prior_p90_s"]:
        h["phase_running_long"] = cur["phase"]
    if fallback:
        h["fallback"] = True
    window = ticks[-THRESHOLDS["dropped_window"] :]
    if sum(window) / len(window) > THRESHOLDS["dropped_rate"]:
        h["decisions_dropped"] = round(sum(window) / len(window), 3)
    return h


def _header(common: dict, mode: str) -> dict:
    return {
        "kind": "header",
        **common,
        "checkpoint": CHECKPOINT,
        "mode": mode,
        "D": D,
        "source": "mock",
        "seed": SEED,
        "thresholds": dict(THRESHOLDS),
        "flicker_s": FLICKER_S,
        # the video's length in the header; api.md names it in v0.3
        "n_frames": N_FRAMES,
        "t_first": 0,
        "t_last": N_FRAMES - 1,
        "video": {"source": "mock_test_pattern", "fps": VIDEO_FPS, "t0": 0},
        "checkpoint_manifest_sha256": None,
        "wheel": None,
        "data_manifest_sha256": None,
        "serving_manifest_sha256": None,
        "commits": {"chole_eval": None, "chole_docs": None},
        "tenant": None,
        "note": "chole-demo feeds/mock.py: made-up values, no project data read",
    }


def generate(mode: str = "offline") -> list[dict]:
    """One mock decision log in api.md v0.1 lines. Deterministic."""
    if mode not in MODES:
        raise ValueError(f"mode {mode!r}")
    rng = random.Random(SEED)
    common = {"api_version": API_VERSION, "run": run_id(mode), "video_id": VIDEO_ID}
    lines: list[dict] = [_header(common, mode)]
    memory, events = _Memory(), _Events()
    prev: dict | None = None  # the last completed decision
    accepted: dict | None = None  # the last accepted state
    computes: list[float] = []
    ticks: list[bool] = []  # per tick: dropped?
    counts = {"decisions": 0, "dropped": 0, "valid": 0, "fallback": 0}
    wall = WALL0
    busy_until = -math.inf
    tick = 0
    while (t := 1 + tick * D) < N_FRAMES:
        compute = math.exp(rng.gauss(math.log(1.35), 0.18))
        if SLOW[0] <= t < SLOW[1]:
            compute *= 2.0
        encode = max(0.05, 0.18 + rng.gauss(0, 0.03))
        packed, confs = _model(t, rng)
        if mode == "live" and t < busy_until:
            ticks.append(True)
            counts["dropped"] += 1
            lines.append(
                {"kind": "dropped", **common, "tick": tick, "t_frame": t, "busy_seq": prev["seq"]}
            )
            tick += 1
            continue
        ticks.append(False)
        if mode == "live":
            arrival = WALL0 + t + 0.05
            t_request = arrival + encode
            busy_until = t + encode + compute
        else:
            arrival = None
            t_request = wall + encode
        fallback = t in FALLBACK_AT and accepted is not None
        reply = json.dumps(packed, separators=(",", ":"))
        if fallback:
            reply = reply[:97]  # a truncated reply
            state = {**copy.deepcopy(accepted), "t": t}
        else:
            state = _complete(packed, confs)
            accepted = state
        seq = counts["decisions"]
        memory.update(seq, t, state)
        computes.append(compute)
        mem = memory.snapshot(t)
        elapsed = mem["current_phase"]["elapsed_s"]
        decision = {
            "kind": "decision",
            **common,
            "tick": tick,
            "seq": seq,
            "t_frame": t,
            "window": {
                "start": max(0, t - 31),
                "end": t,
                "pairs": (t - max(0, t - 31) + 1) // 2,
                "memory": [[s, s + 1] for s in range(max(0, t - 331), max(0, t - 31), 76)][:4],
                "current": t,
            },
            "prev_seq": None if prev is None else prev["seq"],
            "t_frame_arrival": None if arrival is None else round(arrival, 3),
            "t_request": round(t_request, 3),
            "t_response": round(t_request + compute, 3),
            "compute_s": round(compute, 3),
            "encode_s": round(encode, 3),
            "batch": 1,
            "previous_state": None
            if prev is None
            else json.dumps({k: v for k, v in prev["state"].items() if k in PACKED}),
            "prior_block": (
                f"MOCK prior block. Phase {mem['current_phase']['phase']}, elapsed "
                f"{int(elapsed)} s, pace {mem['current_phase']['pace']:.2f} of the median."
            ),
            "reply": reply,
            "valid": not fallback,
            "fallback": fallback,
            "parse_error": "unterminated JSON (truncated reply)" if fallback else None,
            "state": state,
            "outlook": _outlook(
                state["phase"],
                elapsed,
                state["next_tool"]["tool"],
                {_base(x) for x in state["tools_now"]},
            ),
            "delay": {
                "n": seq + 1,
                "compute_p50_s": round(_quantile(computes, 0.5), 3),
                "compute_p95_s": round(_quantile(computes, 0.95), 3),
                "staleness_s": round(compute + 0.5, 3),
                "dropped_rate_est": round(sum(c > D for c in computes) / len(computes), 4),
                "dropped_rate_observed": (
                    round(sum(ticks) / len(ticks), 4) if mode == "live" else None
                ),
            },
            "events": events.update(t, _holding(state, prev, mem, fallback, ticks)),
            "memory": mem,
            "tool_scores": dict(state["tools_now_conf"]),
        }
        lines.append(decision)
        counts["decisions"] += 1
        counts["valid"] += not fallback
        counts["fallback"] += fallback
        wall = t_request + compute
        prev = decision
        tick += 1
    lines.append({"kind": "end", "api_version": API_VERSION, **counts})
    return lines


def answer(decision: dict, question: str) -> dict:
    """A mock interactive turn: no model is connected (api.md v0.1 has no such endpoint)."""
    s = decision["state"]
    mm, ss = divmod(int(decision["t_frame"]), 60)
    return {
        "api_version": API_VERSION,
        "question": question,
        "answer": (
            f"MOCK reply, no model connected. At {mm:02d}:{ss:02d} the mock state is "
            f"{s['phase']} (conf {s['phase_conf']:.2f}); "
            f"tools {', '.join(s['tools_now']) or 'none'}."
        ),
        "t": decision["t_frame"],
        "compute_s": 0.0,
        "mock": True,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


FRAME_SIZES = {"current": "644x392", "video": "336x196"}  # api.md v0.1, GET /api/frames
# The video itself (GET /api/video/{video_id}, by byte ranges): the
# same test pattern at a source-like rate and size; H.264 on the CPU (no GPU).
VIDEO_FPS = 25
VIDEO_SIZE = "854x480"


def build(out_dir: Path) -> dict[str, Path]:
    """Write both runs' logs and the test-pattern frames under out_dir."""
    out = {}
    for mode in MODES:
        d = out_dir / run_id(mode)
        d.mkdir(parents=True, exist_ok=True)
        log = d / f"{VIDEO_ID}.jsonl"
        log.write_text("".join(json.dumps(x, separators=(",", ":")) + "\n" for x in generate(mode)))
        out[f"log_{mode}"] = log
    for variant, size in FRAME_SIZES.items():
        fd = out_dir / "frames" / variant
        if not (fd / f"{N_FRAMES - 1:04d}.jpg").exists():
            _test_pattern(fd, size)
        out[f"frame0_{variant}"] = fd / "0000.jpg"
    video = out_dir / "video" / f"{VIDEO_ID}.mp4"
    if not video.exists():
        _test_video(video)
    out["video"] = video
    return out


def _ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is needed for the mock's test pattern")
    return ffmpeg


def _test_video(path: Path) -> None:
    """The test pattern as a video, one keyframe a second so a seek lands at once;
    written beside its final name and renamed, so a half-written file is never served."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".part.mp4")
    subprocess.run(
        [
            _ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={VIDEO_SIZE}:rate={VIDEO_FPS}:duration={N_FRAMES}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p",
            "-g", str(VIDEO_FPS), "-movflags", "+faststart", str(tmp),
        ],
        check=True,
    )  # fmt: skip
    tmp.replace(path)


def _test_pattern(frame_dir: Path, size: str) -> None:
    frame_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            _ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=1:duration={N_FRAMES}",
            "-start_number", "0", "-q:v", "5", str(frame_dir / "%04d.jpg"),
        ],
        check=True,
    )  # fmt: skip


class MockSource:
    """The mock behind the adapter's interface (client.adapter.ScreenSource): it
    answers with api.md v0.1 lines, as chole-eval's server will."""

    def __init__(self, runs_dir: Path, pace: float = 1.0) -> None:
        self.dir = runs_dir / "mock"
        self._built = False
        self._lines: dict[str, list[dict]] = {}
        self.pace = pace  # the writing run: wall seconds to a video second
        # each writing run starts when it is first followed, not with the source, so a
        # page that takes long to open on the CPU renderer still finds it being written
        self._t0: dict[str, float] = {}
        self._writing: dict[str, list[tuple[float, dict]]] = {}

    def _writing_lines(self, run: str) -> list[tuple[float, dict]]:
        """A writing run's lines, each with the wall second (from the start) it comes."""
        if run not in self._writing:
            mode = WRITING_MODES[run]
            lines = [dict(x, run=run) for x in self.load(run_id(mode), VIDEO_ID)]
            body = [x for x in lines if x["kind"] in ("decision", "dropped")]
            at = [s * self.pace for s in _release_s(body, mode)]
            timed = sorted(zip(at, body, strict=True), key=lambda p: p[0])
            self._writing[run] = [(0.0, lines[0]), *timed, (timed[-1][0] + self.pace, lines[-1])]
        return self._writing[run]

    def _released(self, run: str) -> list[dict]:
        lines = self._writing_lines(run)
        if run not in self._t0:
            return lines[:1]  # the header alone until someone follows it
        now = time.monotonic() - self._t0[run]
        return [x for at, x in lines if at <= now]

    def writing(self, run: str) -> bool:
        return len(self._released(run)) < len(self._writing_lines(run))

    async def follow(self, run: str, video_id: str):
        import asyncio

        self._check(run, video_id)
        if run not in WRITING_MODES:
            raise KeyError(f"{run} is not being written")
        t0 = self._t0.setdefault(run, time.monotonic())
        for at, x in self._writing_lines(run):
            wait = t0 + at - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            yield x

    def _ensure(self) -> None:
        if not self._built:
            build(self.dir)
            self._built = True

    def runs(self) -> list[dict]:
        done = [
            {"run": run_id(m), "video_ids": [VIDEO_ID], "mode": m, "source": "mock",
             "status": "done"}
            for m in MODES
        ]  # fmt: skip
        return done + [
            {"run": run, "video_ids": [VIDEO_ID], "mode": mode, "source": "mock",
             "status": "running" if self.writing(run) else "done"}
            for run, mode in WRITING_MODES.items()
        ]  # fmt: skip

    def load(self, run: str, video_id: str) -> list[dict]:
        self._check(run, video_id)
        if run in WRITING_MODES:
            return self._released(run)
        if run not in self._lines:
            self._ensure()
            path = self.dir / run / f"{VIDEO_ID}.jsonl"
            self._lines[run] = [json.loads(x) for x in path.read_text().splitlines()]
        return self._lines[run]

    def frame_path(self, video_id: str, t: int, variant: str) -> Path:
        if video_id != VIDEO_ID or variant not in FRAME_SIZES or not 0 <= t < N_FRAMES:
            raise KeyError(f"no mock frame {video_id}/{t} ({variant})")
        self._ensure()
        return self.dir / "frames" / variant / f"{t:04d}.jpg"

    def video_path(self, video_id: str) -> Path:
        if video_id != VIDEO_ID:
            raise KeyError(f"no mock video {video_id}")
        self._ensure()
        return self.dir / "video" / f"{VIDEO_ID}.mp4"

    def ask(self, run: str, video_id: str, t: float, question: str) -> dict:
        decisions = [x for x in self.load(run, video_id) if x["kind"] == "decision"]
        current = decisions[0]
        for d in decisions:
            if d["t_frame"] > t:
                break
            current = d
        return answer(current, question)

    @staticmethod
    def _check(run: str, video_id: str) -> None:
        if run not in {run_id(m) for m in MODES} | set(WRITING_MODES) or video_id != VIDEO_ID:
            raise KeyError(f"no mock log {run}/{video_id}")


def describe(paths: dict[str, Path]) -> str:
    return "\n".join(f"{k}: {p} sha256 {_sha256(p)}" for k, p in paths.items())

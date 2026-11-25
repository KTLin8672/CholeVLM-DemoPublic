"""The one adapter between a decision source and the screen.

The screen consumes a rollout in api.md v1.0's decision-line shape, cut to the
fields it draws, plus a small `meta` the adapter derives from the header. A source
answers with API lines: the model server (`ApiSource`, the real logs) or the
mock (`feeds/mock.py`, for tests). When the API moves past the pinned version
(`configs/api.yaml`), this file maps the new lines onto the screen's shape; nothing
else in the repo changes.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx
import yaml

REPO = Path(__file__).resolve().parents[3]
API_YAML = REPO / "configs" / "api.yaml"
API_LOCAL = REPO / "configs" / "api.local.yaml"
DEFAULT_ENDPOINT = "http://127.0.0.1:8710"

DECISION_KEYS = {
    "kind", "api_version", "run", "video_id", "tick", "seq", "t_frame", "window", "prev_seq",
    "t_frame_arrival", "t_request", "t_response", "compute_s", "encode_s",
    "reply", "valid", "fallback", "parse_error", "state", "outlook", "delay", "events", "memory",
}  # fmt: skip
# Not passed on, with every other key the screen does not draw: `previous_state`,
# `cvs_probs` (v1.9), since the 1.10 pin `prior_block` (the prior's own text, never
# drawn; its next-step clause changes form under v1.10's `prev_next_step: zeroed`), and
# the memory's `cvs_first_achieved`: no criterion is drawn as
# achieved, and the screen's CVS is the served one, a screening signal. The
# reply's own CVS leaves nowhere: not the state's `cvs`, not the
# earlier states the memory keeps, not the `"cvs"` member of the raw reply's text.
STATE_KEYS = {
    "t", "phase", "phase_conf", "phase_remaining", "tools_now", "tools_now_conf", "next_tool",
    "risk_flags", "risk_flags_shown", "blood", "next_step", "rationale",
}  # fmt: skip
# the memory as the screen draws it: the phase it holds (the Now lane's "memory:" line),
# the timeline's phases and its flag marks (api.md "Memory")
MEMORY_KEYS = ("current_phase", "phase_timeline", "flags")
# a reply that does not parse: its `"cvs": …` member found outside a string, cut whole
# and the reply withheld when it cannot be (a bracket that closes the
# wrong kind) or when a CVS key is still left in it
REPLY_CVS = re.compile(r'(?<!\\)"cvs"\s*:\s*')
REPLY_CVS_LEFT = re.compile(r'(?<!\\)"(?:cvs|two_structures|triangle_cleared|cystic_plate)"\s*:')
REPLY_WITHHELD = "unparsed, withheld"
SCALAR = re.compile(r"[^,{}\[\]]*")
COMMA = re.compile(r"\s*,\s*")
EVENT_KEYS = {
    "id", "kind", "severity", "field", "value", "t_raised", "t_last", "t_cleared", "visible",
    "wording",
}  # fmt: skip
# The run's source → the feed the screen labels (a "synthetic" feed is labelled on every frame).
# `test_root` (api.md v1.4): the one early held-out video's run, its frames encoded live.
FEED_BY_SOURCE = {"mock": "mock", "val_shards": "real", "test_root": "real"}
MOCK_BANNER = "MOCK FEED, made-up decisions"
# on every frame of a real video, the dataset, its makers, the
# licence and the research line; the 1 fps video served is an adaptation under it
DATASETS = {"cholec80": "Cholec80", "cholect50": "CholecT50", "endoscapes": "Endoscapes"}


def attribution(video_id: str) -> str:
    name = DATASETS.get(video_id.split(":")[0].lower(), video_id.split(":")[0])
    return (
        f"{name} · CAMMA, University of Strasbourg · CC BY-NC-SA 4.0 · "
        "the 1 fps video is an adaptation under the same licence · research demo, not for clinical use"
    )


# one video of a dataset the model never trained on (HeiChole,
# held out whole) on the screen, labelled on every frame, and public
# only where its licence allows (configs/api.yaml `public_held_out`); else the owner's
HELD_OUT = {"heichole": "HeiChole"}
IN_DISTRIBUTION = {"train", "val"}


def held_out(video_id: str, split: str | None = None) -> str | None:
    """The label a video from outside the model's training distribution carries on
    every frame, or None: by its dataset, or by the split its header names."""
    name = HELD_OUT.get(video_id.split(":")[0].lower())
    if name:
        return f"out-of-distribution: a hospital the model never trained on ({name})"
    if split is not None and split not in IN_DISTRIBUTION:
        return f"held out of the model's training ({split})"
    return None


def public_held_out(path: Path = API_YAML) -> set[str]:
    """The held-out videos whose licence allows public display (each one a log row)."""
    return set(yaml.safe_load(path.read_text()).get("public_held_out") or [])


def _attr(header: dict) -> dict:
    return (header.get("video") or {}).get("attribution") or {}


def _credit(header: dict) -> str | None:
    """The attribution a real frame carries: ours for the datasets we know, else the
    API's own (api.md v1.2 `video.attribution`); None if there is none."""
    vid = header["video_id"]
    if vid.split(":")[0].lower() in DATASETS:
        return attribution(vid)
    a = _attr(header)
    parts = [a.get(k) for k in ("dataset", "holder", "licence", "adaptation", "research_line")]
    return " · ".join(parts) if all(parts) else a.get("line")


class ScreenSource(Protocol):
    def runs(self) -> list[dict]: ...

    def load(self, run: str, video_id: str) -> list[dict]: ...

    def frame_path(self, video_id: str, t: int, variant: str) -> Path: ...

    def video_path(self, video_id: str) -> Path: ...

    def ask(self, run: str, video_id: str, t: float, question: str) -> dict: ...

    # a run still being written (status "running" in `runs`): its lines so far, then
    # each new one as it is written, then its end; one connection, which may drop
    def follow(self, run: str, video_id: str) -> AsyncIterator[dict]: ...


def demo_config(path: Path = API_YAML) -> dict:
    """The videos the demo shows, in their order, and nothing else;
    and the run kept public until each of them that is not held out has a finished run,
    so the page is never empty."""
    c = yaml.safe_load(path.read_text())
    return {
        "videos": list(c.get("demo_videos") or []),
        "interim": c.get("interim"),
        "exclude_runs": list(c.get("exclude_runs") or []),
    }


def default_video(path: Path = API_YAML) -> str | None:
    """The video the screen opens on: the demo's first."""
    videos = demo_config(path)["videos"]
    return videos[0] if videos else yaml.safe_load(path.read_text()).get("default_video")


def pinned_version(path: Path = API_YAML) -> str:
    v = yaml.safe_load(path.read_text())["api_version"]
    if v is None:
        raise ValueError(f"{path}: no API version pinned")
    return str(v)


def _version(v) -> tuple[int, int] | None:
    try:
        major, minor = str(v).split(".")
        return int(major), int(minor)
    except ValueError:
        return None


def speaks(line_version, pinned: str) -> bool:
    """A line this client reads: the pinned major, at or below the pinned minor
    (api.md: a minor bump only adds fields, a breaking change is a major one), so a
    log written under 1.0 still reads once the pin is at 1.2; a newer minor is refused
    until the pin moves."""
    v, p = _version(line_version), _version(pinned)
    return v is not None and p is not None and v[0] == p[0] and v[1] <= p[1]


def _missing(obj: dict, keys: set[str], what: str) -> None:
    gone = keys - obj.keys()
    if gone:
        raise ValueError(f"{what} lacks {sorted(gone)}")


# api.md v1.5: the self-probe hint on a decision of a run served with it. The probe's
# three numbers are present when the hint line was shown and absent when not.
CVS_KEYS = ("two_structures", "triangle_cleared", "cystic_plate")
# api.md v1.11: in a run whose header has `cvs_served`, each decision's served CVS, per
# criterion its value and where it came from (drawn
# as a screening signal, "not seen" or "possibly seen", never as achieved): the
# reply's own value, the reply's probability over a threshold fixed on val (`p1`), or the
# temporal CVS specialist's call on the probe's table
CVS_SOURCES = ("reply", "p1", "specialist")
# api.md v1.12: what each prompt is given besides the video and the frame; a log without
# the key is in the trained form
DECISION_FORMS = ("trained", "stateless")


def _share(x, count: str) -> dict | None:
    """One of val's figures as the page draws it: its value and the count it is read on."""
    if not isinstance(x, dict):
        return None
    v, n = x.get("value"), x.get(count)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
        return None
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        return None
    return {"value": v, "n": n}


def val_reading(v) -> dict | None:
    """api.md v1.13's `val_reading` (the header's, or `GET /api/runs/{run}`'s
    `cvs_served_val`) cut to what the engineer's page draws:
    per criterion val's precision (over its "met" calls), the share of "not met" calls
    that is right (`npv`, over its calls) and the share of labelled points met, with the
    points and videos they are read on. A criterion served by p1 had its threshold fixed
    on those points, so its out-of-fold figures are drawn in their place, marked so. The
    report's path, hash, commits and note stay on the server. None when the API
    has none, says it is unavailable, or a figure is missing: the page then draws none."""
    if not isinstance(v, dict) or not isinstance(v.get("criteria"), dict):
        return None
    oof = v.get("out_of_fold") if isinstance(v.get("out_of_fold"), dict) else {}
    out = {}
    for k in CVS_KEYS:
        c = oof.get(k) if isinstance(oof.get(k), dict) else v["criteria"].get(k)
        if not isinstance(c, dict):
            return None
        figs = {
            "precision": _share(c.get("precision"), "calls"),
            "npv": _share(c.get("npv"), "calls"),
            "met_share": _share(c.get("met_share"), "labelled"),
        }
        points, videos = c.get("points"), c.get("videos")
        if None in figs.values() or not all(
            isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in (points, videos)
        ):
            return None
        out[k] = {**figs, "points": points, "videos": videos, "out_of_fold": k in oof}
    return out


def served_cvs(d: dict) -> dict:
    """A decision's `cvs_served` cut to each criterion's value (0, 1 or null) and source;
    anything else in it is an error, never drawn."""
    cs = d.get("cvs_served")
    if cs is None or not isinstance(cs, dict):
        raise ValueError(f"decision {d.get('seq')} lacks ['cvs_served']")
    out = {}
    for k in CVS_KEYS:
        c = cs.get(k)
        if not isinstance(c, dict) or c.get("source") not in CVS_SOURCES:
            raise ValueError(f"decision {d.get('seq')} cvs_served.{k} has no known source")
        v = c.get("value")
        if v not in (0, 1, None) or isinstance(v, bool):
            raise ValueError(f"decision {d.get('seq')} cvs_served.{k} value {v!r}")
        out[k] = {"value": v, "source": c["source"]}
    return out


def _unfamiliar(hint: dict, threshold: float) -> bool:
    """The frame's familiarity distance over the run's threshold (api.md v1.5: a
    distance, so over is less familiar; the hint line is omitted there)."""
    f = hint.get("familiarity")
    return isinstance(f, (int, float)) and f > threshold


def _value_end(text: str, i: int) -> int | None:
    """Where the JSON value that starts at `text[i]` ends, read from text that need not
    parse: a string to its closing quote, an object or an array to its own closing
    bracket (strings and their escapes skipped), a bare value to the next comma or
    bracket; the text's end when it never closes (a reply cut short); None at a bracket
    that closes the wrong kind."""
    if i >= len(text) or text[i] not in '"{[':
        return SCALAR.match(text, i).end()
    want, in_str, j = [], False, i
    while j < len(text):
        c = text[j]
        if in_str:
            if c == "\\":
                j += 1
            elif c == '"':
                in_str = False
                if not want:
                    return j + 1
        elif c == '"':
            in_str = True
        elif c in "{[":
            want.append("}" if c == "{" else "]")
        elif c in "}]":
            if not want or want.pop() != c:
                return None
            if not want:
                return j + 1
        j += 1
    return len(text)


def _cut_cvs(text: str) -> str:
    """A reply that does not parse, less every `"cvs"` member, each cut whole with the
    comma that joins it; `REPLY_WITHHELD` when one cannot be cut or a CVS key is left."""
    kept, pos = [], 0
    while m := REPLY_CVS.search(text, pos):
        end = _value_end(text, m.end())
        if end is None:
            return REPLY_WITHHELD
        head = text[pos : m.start()]
        if comma := COMMA.match(text, end):
            end = comma.end()
        elif end < len(text):  # the object's last member: the comma before it goes
            head = head.rstrip().removesuffix(",")
        kept.append(head)
        pos = end
    kept.append(text[pos:])
    out = "".join(kept)
    return REPLY_WITHHELD if REPLY_CVS_LEFT.search(out) else out


def reply_text(reply):
    """The raw reply as the engineer's pane prints it, without its own `"cvs"` member:
    a reply that parses is written again without it, in the
    model's compact form and order, so it is no longer the model's bytes (the pane says
    so); one that does not parse has the member cut whole, or is withheld."""
    if isinstance(reply, dict):
        return {k: v for k, v in reply.items() if k != "cvs"}
    if not isinstance(reply, str):
        return reply
    try:
        obj = json.loads(reply)
    except ValueError:
        return _cut_cvs(reply)
    if not isinstance(obj, dict):
        return _cut_cvs(reply)
    if "cvs" not in obj:
        return reply
    rest = {k: v for k, v in obj.items() if k != "cvs"}
    return json.dumps(rest, ensure_ascii=False, separators=(",", ":"))


def ask_answer(reply: dict) -> dict:
    """The interactive turn as the page draws it: the answer and nothing else. A refusal keeps its code and its reason."""
    if "error" in reply:
        return {"error": str(reply["error"]), "detail": str(reply.get("detail", ""))}
    return {"answer": str(reply.get("answer", ""))}


def normalize_decision(d: dict, hint_threshold: float | None = None, served: bool = False) -> dict:
    """Check a decision line has the screen's shape and keep only those fields.
    A missing field is an error, never invented; a field the
    screen does not draw never leaves the server (the share is public). In a run
    served with the hint (its header's `hint.threshold` given), the line's `hint` is
    cut to what the engineer view draws: whether the hint line was
    shown, whether the scene was unfamiliar, and the probe's three numbers, null where
    the line carried none. In a run whose header has `cvs_served` (api.md v1.11), the
    line's served CVS is kept, cut by `served_cvs`. The memory is cut to what the
    screen draws (`MEMORY_KEYS`; its first-achieved CVS times are cut),
    and the reply's own CVS is cut from the state and from the reply's text."""
    _missing(d, DECISION_KEYS, f"decision {d.get('seq')}")
    _missing(d["state"], STATE_KEYS, f"decision {d.get('seq')} state")
    for e in d["events"]:
        _missing(e, EVENT_KEYS, f"decision {d.get('seq')} event")
    out = {k: d[k] for k in DECISION_KEYS}
    out["state"] = {k: d["state"][k] for k in STATE_KEYS}
    out["reply"] = reply_text(d["reply"])
    if isinstance(d["memory"], dict):
        out["memory"] = {k: d["memory"][k] for k in MEMORY_KEYS if k in d["memory"]}
    if hint_threshold is not None:
        h = d.get("hint")
        if not isinstance(h, dict):
            raise ValueError(f"decision {d.get('seq')} lacks ['hint']")
        _missing(h, {"familiarity", "hint_shown"}, f"decision {d.get('seq')} hint")
        out["hint"] = {
            "shown": h["hint_shown"] is True,
            "unfamiliar": _unfamiliar(h, hint_threshold),
            **{k: h.get(k) if isinstance(h.get(k), (int, float)) else None for k in CVS_KEYS},
        }
    if served:
        out["cvs_served"] = served_cvs(d)
    return out


# api.md v1.3: `dropped_rate_est` is the share of ticks a live loop at D would skip,
# `over_d_rate` the share of replies over D; below 1.3 the first meant the second
SKIP_SINCE = (1, 3)


def skip_share(busy_s: list[float], D: float) -> float:
    """The share of ticks a live loop at D would skip under the busy-until rule (api.md
    v1.3): a decision busy for `compute_s + encode_s` holds k = max(1, ceil(busy / D))
    ticks and skips k - 1; over the decisions so far, sum(k - 1) / sum(k)."""
    if not busy_s:
        return 0.0
    k = [max(1, math.ceil(b / D - 1e-9)) for b in busy_s]
    return round(sum(x - 1 for x in k) / sum(k), 4)


class Delays:
    """The delay figures in v1.3's sense, whatever version a line speaks: a line below 1.3 has its over-D share moved to `over_d_rate` and the skip
    share computed from the decisions so far by api.md's formula; a 1.3 line is kept
    as the server wrote it. Fed every decision of a log once, in order."""

    def __init__(self, D: float) -> None:
        self.D, self.busy = D, []

    def read(self, d: dict) -> dict:
        self.busy.append(d["compute_s"] + (d.get("encode_s") or 0.0))
        v = _version(d.get("api_version"))
        if v is None or v >= SKIP_SINCE or not isinstance(d.get("delay"), dict):
            return d
        dl = dict(d["delay"])
        dl["over_d_rate"] = dl.get("dropped_rate_est")
        dl["dropped_rate_est"] = skip_share(self.busy, self.D)
        return {**d, "delay": dl}


class Unfamiliar:
    """The "unfamiliar scene" event, worked out here from the decision
    lines, since the API's event box has no such kind: a scene is unfamiliar while its
    frame's `hint.familiarity` is over the header's `hint.threshold`; the event is
    raised once it has been so for `RAISE_S` of video time, and held as the model server holds
    its own (api.md "Event"): visible at least `event_hold_s` from
    `t_raised` and longer while it holds, reopened if it returns while still visible,
    and shown once more, invisible, when it leaves the box. Fed every decision of one
    stream once, in order."""

    KIND = "unfamiliar_scene"
    RAISE_S = 10
    # the wording written as the box's other entries are
    WORDING = (
        "Unfamiliar scene: the footage is unlike the training videos, so the vision hint is off."
    )

    def __init__(self, video_id: str, threshold: float, hold_s: float) -> None:
        self.video_id, self.threshold, self.hold_s = video_id, threshold, hold_s
        self.since: int | None = None  # the first second of the present unfamiliar stretch
        self.ev: dict | None = None

    def read(self, line: dict, cut: dict) -> dict:
        t = line["t_frame"]
        over = _unfamiliar(line["hint"], self.threshold)
        self.since = (t if self.since is None else self.since) if over else None
        if over and t - self.since >= self.RAISE_S:
            if self.ev is None:
                self.ev = {
                    "id": f"{self.video_id}/{self.KIND}/{t}", "kind": self.KIND,
                    "severity": "info", "field": "hint.familiarity", "t_raised": t,
                    "wording": self.WORDING,
                }  # fmt: skip
            self.ev.update(value=round(line["hint"]["familiarity"], 2), t_last=t, t_cleared=None)
        elif self.ev is not None and self.ev["t_cleared"] is None:
            self.ev["t_cleared"] = t
        if self.ev is None:
            return cut
        self.ev["visible"] = self.ev["t_cleared"] is None or t - self.ev["t_raised"] < self.hold_s
        ev = dict(self.ev)
        if not ev["visible"]:
            self.ev = None
        return {**cut, "events": [*cut["events"], ev]}


class Reader:
    """One stream's decision lines for the screen, read in order: each cut to the
    screen's fields, its delay figures in v1.3's sense (`Delays`), and in a run served
    with the hint (api.md v1.5) the "unfamiliar scene" event (`Unfamiliar`). A run
    without the `hint` key shows neither the probe's numbers nor the event. In a run with
    the served CVS (api.md v1.11) each decision carries it, as it is: nothing is worked out
    from it, and the memory's `cvs_first_achieved` (the reply's own CVS) is cut away."""

    def __init__(self, header: dict) -> None:
        self.delays = Delays(header["D"])
        hint = header.get("hint")
        self.threshold = hint.get("threshold") if isinstance(hint, dict) else None
        if hint is not None and not isinstance(self.threshold, (int, float)):
            raise ValueError("the header's hint lacks its threshold")
        hold = (header.get("thresholds") or {}).get("event_hold_s", 60)
        self.unfamiliar = (
            Unfamiliar(header["video_id"], self.threshold, hold)
            if self.threshold is not None
            else None
        )
        self.served = header.get("cvs_served") is not None
        if self.served and not isinstance(header["cvs_served"], dict):
            raise ValueError("the header's cvs_served is not an object")

    def read(self, line: dict) -> dict:
        cut = self.delays.read(normalize_decision(line, self.threshold, self.served))
        return self.unfamiliar.read(line, cut) if self.unfamiliar else cut


# What the engineer view says of the model: the checkpoint's name and
# its gate's result and figures (api.md v1.6 `checkpoint.gate`). Both are training's words;
# only a name and a line of plain words and figures are passed on (no path, no host).
SAFE_NAME = re.compile(r"[A-Za-z0-9._-]{1,64}")
SAFE_LINE = re.compile(r"[A-Za-z0-9 _.,:;()\[\]<>=+%'#*±×≥≤…–—-]{1,600}")
# The verdict comes from `met` alone, and of the line only the criteria's figures are shown,
# never its head or a parenthetical ("NOT MET (the owner's written decision
# to proceed)" read as if a decision had been given): "head: name value vs bar met; ...".
GATE_HEAD = re.compile(r"[^:]*\bgate\b[^:]*:(.*)", re.IGNORECASE | re.DOTALL)
GATE_CLAUSE = re.compile(
    r"([A-Za-z0-9_]{1,64}) (-?\d+(?:\.\d+)?) vs (-?\d+(?:\.\d+)?) (met|not met)", re.IGNORECASE
)
# A clause with a figure against a bar in it is a criterion; one without is a note (Stage 3's
# line ends on "next_step top-3 beside the like-for-like rows ... (reported): the model 0.6741,
# ..."), which is not a criterion and is not shown.
GATE_FIGURE = re.compile(r"-?\d+(?:\.\d+)? vs -?\d+(?:\.\d+)?", re.IGNORECASE)


def gate_figures(line) -> str | None:
    """Each criterion of a gate's line as "name value vs bar met|not met", its notes (the
    clauses with no figure against a bar) left out; None when a clause with such a figure is
    not a plain criterion (a parenthetical in it), or when there is no criterion."""
    if not isinstance(line, str) or not SAFE_LINE.fullmatch(line):
        return None
    head = GATE_HEAD.fullmatch(line)
    clauses = [c.strip() for c in head.group(1).split(";") if c.strip()] if head else []
    figures = [c for c in clauses if GATE_FIGURE.search(c)]
    parsed = [GATE_CLAUSE.fullmatch(c) for c in figures]
    if not parsed or not all(parsed):
        return None
    return "; ".join(f"{m[1]} {m[2]} vs {m[3]} {m[4].lower()}" for m in parsed)


def decision_form(header: dict) -> str:
    """The run's decision form (api.md v1.12): "trained" or "stateless"; a log without
    the key is in the trained form."""
    f = header.get("decision_form")
    if f is None:
        return "trained"
    name = f.get("name") if isinstance(f, dict) else None
    if name not in DECISION_FORMS:
        raise ValueError(f"unknown decision form {name!r}")
    return name


def model_line(header: dict) -> dict:
    """`checkpoint`, the name; `gate`: "met", "not met", "none" (an export with no
    gate) or None (a log before v1.6, which does not record it); `gate_line`, the
    criteria's figures (`gate_figures`)."""
    ck = header.get("checkpoint")
    ck = ck if isinstance(ck, dict) else {"name": ck}
    name = ck.get("name")
    out = {
        "checkpoint": name if isinstance(name, str) and SAFE_NAME.fullmatch(name) else None,
        "gate": None,
        "gate_line": None,
    }
    if "gate" not in ck:
        return out
    gate = ck["gate"]
    if not isinstance(gate, dict) or not isinstance(gate.get("met"), bool):
        return {**out, "gate": "none"}
    return {
        **out,
        "gate": "met" if gate["met"] else "not met",
        "gate_line": gate_figures(gate.get("line")),
    }


DROPPED_KEYS = ("kind", "tick", "t_frame")
END_COUNTS = ("decisions", "dropped", "fallback", "valid")


def to_screen(lines: list[dict], pinned: str, cvs_val: dict | None = None) -> dict:
    """A decision log (header, decision and dropped lines, end) for the screen. `cvs_val`
    is val's reading of the run's served CVS as the run's listing carries it (api.md
    v1.13 `cvs_served_val`, already cut by `val_reading`), for a log written before the
    header carried its own."""
    if not lines or lines[0].get("kind") != "header":
        raise ValueError("a decision log starts with its header")
    for x in lines:
        if not speaks(x.get("api_version"), pinned):
            raise ValueError(f"line speaks API {x.get('api_version')!r}; this client pins {pinned}")
    header = lines[0]
    source = header.get("source")
    if source not in FEED_BY_SOURCE:
        raise ValueError(f"unknown source {source!r}")
    feed = FEED_BY_SOURCE[source]
    credit = _credit(header) if feed == "real" else None
    if feed == "real" and not credit:
        raise ValueError("a real video without its attribution is not shown")
    reader = Reader(header)
    decisions = [reader.read(x) for x in lines if x["kind"] == "decision"]
    dropped = [{k: x.get(k) for k in DROPPED_KEYS} for x in lines if x["kind"] == "dropped"]
    end = {k: lines[-1].get(k) for k in END_COUNTS} if lines[-1]["kind"] == "end" else None
    last_t = max((x["t_frame"] for x in decisions + dropped), default=0)
    meta = {
        "api_version": pinned,
        "run": header["run"],
        "video_id": header["video_id"],
        "mode": header["mode"],
        "D": header["D"],
        "source": source,
        "feed": feed,
        "banner": MOCK_BANNER if feed == "mock" else None,
        "attribution": credit,
        # outside the training distribution: said on every frame, in
        # the API's words where it gives them (api.md v1.4 `attribution.ood`)
        "held_out": _attr(header).get("ood") or held_out(header["video_id"], header.get("split")),
        "thresholds": header["thresholds"],
        "flicker_s": header.get("flicker_s"),
        # served with the self-probe hint (api.md v1.5): its numbers on the engineer view
        "hint": reader.threshold is not None,
        # the served CVS on each decision (api.md v1.11): the screen's CVS reading, a
        # screening signal; without it the run shows none
        "cvs_served": reader.served,
        # val's precision, NPV and share met beside it (api.md v1.13), the header's own or the listing's; None where there are none
        "cvs_val": (
            (val_reading(header["cvs_served"].get("val_reading")) or cvs_val)
            if reader.served
            else None
        ),
        # the checkpoint and its gate, for the engineer view
        "model": model_line(header),
        # what each prompt was given (api.md v1.12): "trained" or "stateless"
        "decision_form": decision_form(header),
        # The video's length: the header's n_frames (api.md v1.0); else the last tick's frame.
        "duration_s": header.get("n_frames") or last_t + 1,
        # the player's file: its rate and the video second its time 0 stands for
        "video": {k: (header.get("video") or {}).get(k) for k in ("fps", "t0")},
        # where the rollout's decisions begin and end: a run of a stretch (`from_t`) opens
        # there, and past its end the screen says "no decision after"
        "first_decision_t": min((d["t_frame"] for d in decisions), default=None),
        "last_decision_t": max((d["t_frame"] for d in decisions), default=None),
    }
    # the raw header stays on the server: it may carry paths, hosts and manifests
    return {"meta": meta, "decisions": decisions, "dropped": dropped, "end": end}


def _served_form(f) -> bool | None:
    s = f.get("served") if isinstance(f, dict) else None
    return s if isinstance(s, bool) else None


class ApiSource:
    """The model server (api.md v1.0) as the screen's source. Runs and logs are
    read here; frames and the video are proxied by the demo server from `upstream`,
    so the browser talks to the demo server alone. Nothing about the upstream's
    header (paths, hosts, manifests) reaches the screen: `to_screen` keeps `meta`."""

    def __init__(
        self, endpoint: str = DEFAULT_ENDPOINT, client: httpx.Client | None = None
    ) -> None:
        self.upstream = endpoint.rstrip("/")
        self.http = client or httpx.Client(base_url=self.upstream, timeout=30)

    def _get(self, path: str) -> httpx.Response:
        r = self.http.get(path)
        if r.status_code == 404:
            raise KeyError(path)
        r.raise_for_status()
        return r

    def runs(self) -> list[dict]:
        listed = self._get("/api/runs").json()
        if isinstance(listed, dict):  # {"api_version", "runs": [...]}
            listed = listed.get("runs", [])
        out = []
        for entry in listed:
            name = entry if isinstance(entry, str) else entry.get("run") or entry.get("name")
            info = self._get(f"/api/runs/{quote(name, safe='')}").json()
            # `done` (or no status, as in 1.0) or `running`: since API 1.2 a run still
            # being written lists its videos too; the server shows it only as followed
            status = info.get("status", "done")
            if status not in ("done", "running"):
                continue
            manifest = info.get("manifest") or {}
            # each video's log size: how much of it the run covers (about 9 KB a
            # decision), so the screen opens on the fullest run of a video
            sizes = {
                f["path"].removesuffix(".jsonl"): f.get("size", 0)
                for f in manifest.get("files", [])
                if isinstance(f, dict) and "path" in f
            }
            # a run still being written has no manifest yet: its fields are the info's own
            fields = {**manifest, **info}
            from_t = fields.get("from_t")
            ck = fields.get("checkpoint")
            ck = ck if isinstance(ck, dict) else {"name": ck}
            mode = fields.get("mode", "offline")
            out.append({
                "run": name,
                "video_ids": info.get("video_ids") or manifest.get("video_ids") or [],
                "mode": mode,
                "source": manifest.get("source", "val_shards"),
                "sizes": sizes,
                # a stretch's first second (API 1.2 `from_t`); None for a whole video
                "from_t": from_t,
                # an offline rollout of whole videos: not a stretch (`from_t`, `limit`), not
                # sampled points (`from_rows`: the parity and reconciliation runs), not a
                # live replay; only such a run is a demo video's
                "whole": fields.get("kind", "rollout") == "rollout" and mode == "offline"
                and not (from_t or fields.get("limit") or fields.get("from_rows")),
                "status": status,
                # which checkpoint wrote it (its manifest's hash, else its name) and when the
                # run began (unix seconds; None before API 1.2): the newest checkpoint's runs
                # are the ones a demo video is shown from
                "checkpoint": ck.get("manifest_sha256") or ck.get("name"),
                "created": fields.get("created"),
                # the API version the run was written in (its manifest's; a run still being
                # written has only the info's): a newer minor than the pin is not listed,
                # since the screen refuses its lines until the pin moves
                "api_version": manifest.get("api_version") or info.get("api_version"),
                # api.md v1.7: an ablation row's run (A10, the hint dropped); the demo is
                # never shown one, since it is not its checkpoint as served
                "ablation": bool(fields.get("ablation")),
                # api.md v1.12: whether the run is in its checkpoint's served decision form
                # (True, False, or None for a log before v1.12, which does not say): of a
                # checkpoint's runs a demo video is shown from one in the served form
                "served": _served_form(fields.get("decision_form")),
                # api.md v1.13: val's reading of the served CVS, cut to what is drawn
                "cvs_val": val_reading(info.get("cvs_served_val")),
                # api.md v1.4: a video whose licence does not allow public display
                "private": {
                    v for v, a in (info.get("attribution") or {}).items()
                    if isinstance(a, dict) and a.get("public") is False
                },
            })  # fmt: skip
        return out

    def load(self, run: str, video_id: str) -> list[dict]:
        r = self._get(f"/api/load/{quote(run, safe='')}/{quote(video_id, safe='')}")
        return [json.loads(x) for x in r.text.splitlines() if x.strip()]

    def frame_path(self, video_id: str, t: int, variant: str) -> Path:
        raise KeyError("frames are proxied from the upstream")

    def video_path(self, video_id: str) -> Path:
        raise KeyError("the video is proxied from the upstream")

    async def follow(self, run: str, video_id: str) -> AsyncIterator[dict]:
        """api.md v1.1: `WS /api/stream` follows a run still being written. The socket
        is opened first and sent to its end (a seek past the last second), then the
        stored lines are read, so a line written in between is in one or the other;
        the follower keeps each line once."""
        from websockets.asyncio.client import connect

        path = f"{quote(run, safe='')}/{quote(video_id, safe='')}"
        ws_url = "ws" + self.upstream.removeprefix("http") + f"/api/stream/{path}?speed=1000"
        async with connect(ws_url, max_size=2**24, open_timeout=10, ping_interval=20) as ws:
            json.loads(await ws.recv())  # hello: its header is the stored log's first line
            await ws.send(json.dumps({"type": "seek", "t": 10**9}))
            async with httpx.AsyncClient(
                base_url=self.upstream, timeout=30, transport=getattr(self, "async_transport", None)
            ) as client:
                r = await client.get(f"/api/load/{path}")
                r.raise_for_status()
            for x in r.text.splitlines():
                if x.strip():
                    yield json.loads(x)
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") in ("decision", "dropped", "end") and msg.get("line"):
                    yield msg["line"]
                    if msg["type"] == "end":
                        return

    def ask(self, run: str, video_id: str, t: float, question: str) -> dict:
        r = self.http.post(
            "/api/ask", json={"run": run, "video_id": video_id, "t": t, "question": question}
        )
        body = r.json()
        if r.status_code >= 400:
            # the upstream's reason, in its own words (no_model, not_admitted), nothing more
            return {"error": body.get("error", "refused"), "detail": body.get("detail", "")}
        return body


def endpoint(path: Path = API_LOCAL) -> str:
    if path.exists():
        return (yaml.safe_load(path.read_text()) or {}).get("endpoint", DEFAULT_ENDPOINT)
    return DEFAULT_ENDPOINT


def open_source(kind: str, runs_dir: Path) -> ScreenSource:
    if kind == "mock":
        from chole_demo.feeds.mock import MockSource

        return MockSource(runs_dir)
    if kind == "api":
        return ApiSource(endpoint())
    if kind == "replay":
        from chole_demo.feeds.replay import ReplaySource

        source = ReplaySource(runs_dir)
        for video_id in source.missing():
            print(
                f"no picture yet for {video_id}: "
                f"python -m chole_demo.feeds.replay {video_id} PATH"
            )
        return source
    raise ValueError(f"source {kind!r}: 'api' (the model server), 'mock' or 'replay'")

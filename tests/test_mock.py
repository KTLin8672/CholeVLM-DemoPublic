"""The mock feed speaks chole-eval's API v1.0 and is deterministic."""

import itertools
import json
from pathlib import Path

import pytest

from chole_demo.client.adapter import DECISION_KEYS, EVENT_KEYS, STATE_KEYS, to_screen
from chole_demo.feeds import mock

BUCKETS = {"<30s", "30-120s", "2-5min", ">5min"}


@pytest.fixture(scope="module", params=mock.MODES)
def log(request):
    return mock.generate(request.param)


def decisions(lines):
    return [x for x in lines if x["kind"] == "decision"]


def test_deterministic():
    for mode in mock.MODES:
        assert json.dumps(mock.generate(mode)) == json.dumps(mock.generate(mode))


def test_line_kinds_and_counts(log):
    assert log[0]["kind"] == "header" and log[-1]["kind"] == "end"
    assert {x["kind"] for x in log[1:-1]} <= {"decision", "dropped"}
    end = log[-1]
    ds = decisions(log)
    assert end["decisions"] == len(ds)
    assert end["dropped"] == sum(x["kind"] == "dropped" for x in log)
    assert end["fallback"] == sum(d["fallback"] for d in ds)
    assert end["valid"] == sum(d["valid"] for d in ds)
    assert all(x["api_version"] == mock.API_VERSION for x in log)


def test_decision_clock(log):
    ticks = [x for x in log if x["kind"] in ("decision", "dropped")]
    assert [x["tick"] for x in ticks] == list(range(len(ticks)))
    assert all(x["t_frame"] == 1 + x["tick"] * mock.D for x in ticks)  # odd seconds
    ds = decisions(log)
    assert [d["seq"] for d in ds] == list(range(len(ds)))
    for a, b in itertools.pairwise(ds):
        assert b["prev_seq"] == a["seq"]
    if log[0]["mode"] == "offline":
        assert log[-1]["dropped"] == 0
        assert all(d["t_frame_arrival"] is None for d in ds)
    else:
        assert log[-1]["dropped"] > 0
        assert all(d["tick"] - d["seq"] >= 0 for d in ds)


def test_shapes(log):
    for d in decisions(log):
        assert DECISION_KEYS <= d.keys()
        s = d["state"]
        assert STATE_KEYS <= s.keys()
        assert s["phase"] in mock.PHASES
        assert s["phase_remaining"]["bucket"] in BUCKETS
        assert all(t.split(":")[0] in mock.TOOLS for t in s["tools_now"])
        assert set(s["tools_now_conf"]) == {t.split(":")[0] for t in s["tools_now"]}
        assert s["next_tool"]["tool"] in set(mock.TOOLS) | {"none"}
        assert set(s["risk_flags"]) == set(mock.FLAGS)
        assert s["risk_flags_shown"] == [f for f in mock.FLAGS if s["risk_flags"][f] == 1]
        assert s["blood"] in {"none", "present", "significant"}
        if s["next_step"]["verb"] in ("continue", "other"):
            assert "target" not in s["next_step"]
        assert d["t_response"] - d["t_request"] == pytest.approx(d["compute_s"], abs=2e-3)
        assert d["delay"]["n"] == d["seq"] + 1
        for e in d["events"]:
            assert EVENT_KEYS <= e.keys()
        m = d["memory"]
        assert m["t"] == d["t_frame"]
        assert len(m["last_states"]) <= mock.K_STATES


def test_fallback_keeps_the_accepted_state():
    ds = decisions(mock.generate("offline"))
    falls = [i for i, d in enumerate(ds) if d["fallback"]]
    assert falls
    for i in falls:
        d = ds[i]
        assert not d["valid"] and d["parse_error"]
        with pytest.raises(json.JSONDecodeError):
            json.loads(d["reply"])
        prev = {k: v for k, v in ds[i - 1]["state"].items() if k != "t"}
        assert {k: v for k, v in d["state"].items() if k != "t"} == prev


def test_every_event_kind_and_its_wording():
    raised = set()
    hold = mock.THRESHOLDS["event_hold_s"]
    for mode in mock.MODES:
        for d in decisions(mock.generate(mode)):
            for e in d["events"]:
                raised.add(e["kind"])
                severity, field, wording = mock.EVENT_KINDS[e["kind"]]
                if e["kind"] == "blood" and e["value"] == "significant":
                    severity, wording = mock.BLOOD_SIGNIFICANT
                assert (e["severity"], e["field"], e["wording"]) == (severity, field, wording)
                assert e["visible"]
                assert e["t_cleared"] is None or d["t_frame"] < e["t_raised"] + hold
                assert e["id"] == f"{mock.VIDEO_ID}/{e['kind']}/{e['t_raised']}"
    assert raised == set(mock.EVENT_KINDS)


def test_memory_smooths_a_flicker():
    last = decisions(mock.generate("offline"))[-1]["memory"]
    phases = [p["phase"] for p in last["phase_timeline"]]
    assert phases == mock.PHASES  # the 6 s backward call opened no segment
    assert all(v is not None for v in last["cvs_first_achieved"].values())
    sc = last["self_consistency"]
    assert 0 < sc["next_tool"]["hit_rate"] < 1
    assert sc["next_step"] == {"n": 0, "hit_rate": None}
    assert sc["phase_remaining"]["n"] > 0


def test_adapter_reads_both_runs():
    for mode in mock.MODES:
        r = to_screen(mock.generate(mode), mock.API_VERSION)
        assert r["meta"]["feed"] == "mock" and r["meta"]["banner"]
        assert r["meta"]["duration_s"] == mock.N_FRAMES
        assert "header" not in r  # the raw header stays on the server


def test_reads_no_project_data():
    src = Path(mock.__file__).read_text()
    for word in ("DATA_ROOT", "ARTIFACT_ROOT", "parquet", "priors_train", "split.json"):
        assert word not in src

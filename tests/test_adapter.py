"""The adapter: the pinned API version, the feed by source, nothing invented."""

import copy
import json
from pathlib import Path

import pytest

from chole_demo.client.adapter import (
    API_YAML,
    CVS_KEYS,
    MEMORY_KEYS,
    REPLY_WITHHELD,
    Delays,
    Unfamiliar,
    ask_answer,
    held_out,
    model_line,
    pinned_version,
    reply_text,
    skip_share,
    speaks,
    to_screen,
    val_reading,
)
from chole_demo.feeds import mock


@pytest.fixture(scope="module")
def lines():
    return mock.generate("offline")


def test_the_pin_is_v1_13():
    assert pinned_version(API_YAML) == "1.13"


def test_a_two_digit_minor_is_read_as_a_number():
    """ "1.10" is newer than "1.9", never 1.1: the pin and the lines compare as integers."""
    assert speaks("1.9", "1.10") and speaks("1.10", "1.10") and speaks("1.0", "1.10")
    assert not speaks("1.10", "1.9") and not speaks("1.11", "1.10") and not speaks("2.0", "1.10")


def test_an_older_minor_of_the_pinned_major_reads(lines):
    assert speaks("1.0", "1.4") and speaks("1.3", "1.4") and speaks("1.4", "1.4")
    assert not speaks("1.5", "1.4") and not speaks("2.0", "1.4") and not speaks(None, "1.4")
    assert to_screen(lines, "1.4")["meta"]["api_version"] == "1.4"


def test_the_skip_share_is_api_md_v1_3s_formula():
    # api.md v1.3: at D = 4 a decision of 20.3 s holds six ticks and skips five
    assert skip_share([20.3], 4) == round(5 / 6, 4)
    assert skip_share([4.0, 3.9, 1.0], 4) == 0.0  # done by the next tick: nothing skipped
    assert skip_share([4.1, 20.3], 4) == round((1 + 5) / (2 + 6), 4)
    assert skip_share([], 4) == 0.0


def test_a_line_below_1_3_reads_in_1_3s_sense(lines):
    """The mock speaks 1.0, where dropped_rate_est was the over-D share: the screen
    gets that as over_d_rate and the skip share computed from the decisions so far."""
    D = lines[0]["D"]
    raw = [x for x in lines if x["kind"] == "decision"]
    got = to_screen(lines, "1.3")["decisions"]
    busy = []
    for x, d in zip(raw, got, strict=True):
        busy.append(x["compute_s"] + x["encode_s"])
        assert d["delay"]["over_d_rate"] == x["delay"]["dropped_rate_est"]
        assert d["delay"]["dropped_rate_est"] == skip_share(busy, D)
    assert any(d["delay"]["dropped_rate_est"] != d["delay"]["over_d_rate"] for d in got)
    assert "over_d_rate" not in raw[-1]["delay"]  # the source's lines are left as they came


def test_a_1_3_line_is_kept_as_the_server_wrote_it(lines):
    one = next(x for x in lines if x["kind"] == "decision")
    new = dict(
        one, api_version="1.3", delay={**one["delay"], "dropped_rate_est": 0.5, "over_d_rate": 0.25}
    )
    delays = Delays(4)
    assert delays.read(new)["delay"] == new["delay"]
    # it still counts toward the share of an older line after it (a run resumed under one name)
    old = dict(one, compute_s=20.3, encode_s=0.0)
    assert delays.read(old)["delay"]["dropped_rate_est"] == skip_share(
        [one["compute_s"] + one["encode_s"], 20.3], 4
    )


def test_unpinned_is_refused(tmp_path):
    p = tmp_path / "api.yaml"
    p.write_text("api_version: null\n")
    with pytest.raises(ValueError, match="no API version"):
        pinned_version(p)


def test_a_newer_or_another_major_version_is_refused(lines):
    for v in ("1.1", "2.0"):
        other = copy.deepcopy(lines)
        other[5]["api_version"] = v
        with pytest.raises(ValueError, match="pins 1.0"):
            to_screen(other, "1.0")


def test_unknown_source_is_refused(lines):
    other = copy.deepcopy(lines)
    other[0]["source"] = "somewhere"
    with pytest.raises(ValueError, match="unknown source"):
        to_screen(other, "1.0")


def test_a_missing_field_is_an_error(lines):
    other = copy.deepcopy(lines)
    del other[3]["state"]["blood"]
    with pytest.raises(ValueError, match="blood"):
        to_screen(other, "1.0")


def test_the_header_comes_first(lines):
    with pytest.raises(ValueError, match="header"):
        to_screen(lines[1:], "1.0")


def test_a_live_run_without_its_end_line(lines):
    r = to_screen(lines[:-1], "1.0")
    assert r["end"] is None and len(r["decisions"]) == 240


def test_the_length_from_the_header_or_the_last_tick(lines):
    assert to_screen(lines, "1.0")["meta"]["duration_s"] == mock.N_FRAMES
    other = copy.deepcopy(lines)
    del other[0]["n_frames"]
    last = max(x["t_frame"] for x in other if x["kind"] in ("decision", "dropped"))
    assert to_screen(other, "1.0")["meta"]["duration_s"] == last + 1


def test_a_held_out_video_says_so_on_every_frame(lines):
    """HeiChole, a hospital the model never trained on, labelled; its
    attribution is the API's own (api.md v1.2), and without one it is not shown."""
    assert held_out("cholec80:12") is None and held_out("cholec80:12", "val") is None
    hei = held_out("heichole:3")
    assert hei == "out-of-distribution: a hospital the model never trained on (HeiChole)"
    assert held_out("cholec80:70", "test") == "held out of the model's training (test)"
    other = copy.deepcopy(lines)
    for x in other:
        x["video_id"] = "heichole:3"
    other[0].update(source="val_shards", split="held", video={"fps": 1, "t0": 0, "attribution": {
        "dataset": "HeiChole", "holder": "its makers", "licence": "its licence",
        "adaptation": "1 fps frames as an H.264 video", "research_line": "research demo, not for clinical use",
    }})  # fmt: skip
    meta = to_screen(other, "1.3")["meta"]
    assert meta["held_out"] == hei and meta["feed"] == "real"
    assert meta["attribution"].startswith("HeiChole · its makers · its licence")
    # api.md v1.4: the early video's run reads its frames from the test root, and the
    # API gives the line itself (`attribution.ood`), which the screen carries as given
    other[0].update(source="test_root")
    other[0]["video"]["attribution"].update(public=False, ood="the API's own line")
    meta = to_screen(other, "1.4")["meta"]
    assert meta["held_out"] == "the API's own line" and meta["feed"] == "real"
    assert "False" not in meta["attribution"] and "own line" not in meta["attribution"]
    del other[0]["video"]["attribution"]
    with pytest.raises(ValueError, match="attribution"):
        to_screen(other, "1.4")


# api.md v1.5-v1.6: a run served with the self-probe hint, built on the mock's log
THRESHOLD = 74.6455
UNFAMILIAR = range(101, 141)  # the mock decides at odd seconds: 101 ... 139


def hinted(lines: list[dict]) -> list[dict]:
    out = copy.deepcopy(lines)
    for x in out:
        x["api_version"] = "1.7"
    out[0]["hint"] = {
        "probe": "probe-cvs-v1",
        "manifest_sha256": "b22c8d10",
        "threshold": THRESHOLD,
    }
    out[0]["checkpoint"] = {
        "name": "stage2c-best", "manifest_sha256": "0f0f", "form": "gate",
        "gate": {"met": False, "line": "stage 2 gate NOT MET (val): triangle_cleared 0.74 vs 0.78 not met"},
    }  # fmt: skip
    for x in out:
        if x["kind"] != "decision":
            continue
        far = x["t_frame"] in UNFAMILIAR
        shown = not far and x["seq"] > 0  # the first decision has no prior block
        x["hint"] = {"familiarity": 120.5 if far else 26.4, "hint_shown": shown}
        if shown:
            x["hint"].update(two_structures=0.62, triangle_cleared=0.31, cystic_plate=0.12)
    return out


def test_a_hinted_run_carries_the_probes_numbers_cut(lines):
    """The engineer view shows the probe's three numbers, labelled the
    probe's; they are present where the hint line was shown and null where it was not;
    the familiarity distance itself stays on the server."""
    r = to_screen(hinted(lines), "1.7")
    assert r["meta"]["hint"] is True
    first, second = r["decisions"][0], r["decisions"][1]
    assert first["hint"] == {"shown": False, "unfamiliar": False, "two_structures": None,
                             "triangle_cleared": None, "cystic_plate": None}  # fmt: skip
    assert second["hint"] == {"shown": True, "unfamiliar": False, "two_structures": 0.62,
                              "triangle_cleared": 0.31, "cystic_plate": 0.12}  # fmt: skip
    far = next(d for d in r["decisions"] if d["t_frame"] == 101)
    assert far["hint"]["shown"] is False and far["hint"]["unfamiliar"] is True
    assert far["hint"]["two_structures"] is None
    assert all("familiarity" not in d["hint"] for d in r["decisions"])
    assert "probe-cvs" not in str(r) and "b22c8d10" not in str(r) and "0f0f" not in str(r)


def test_the_unfamiliar_scene_event_is_raised_after_10_s_and_held_60(lines):
    r = to_screen(hinted(lines), "1.7")
    seen = {}
    for d in r["decisions"]:
        ev = [e for e in d["events"] if e["kind"] == "unfamiliar_scene"]
        assert len(ev) <= 1
        seen[d["t_frame"]] = ev[0] if ev else None
    # unfamiliar from 101: raised once it has held 10 s, at the decision of 111
    assert all(seen[t] is None for t in range(1, 111, 2))
    ev = seen[111]
    assert ev["t_raised"] == 111 and ev["visible"] and ev["t_cleared"] is None
    assert ev["severity"] == "info" and ev["field"] == "hint.familiarity"
    assert ev["wording"] == ("Unfamiliar scene: the footage is unlike the training videos, "
                             "so the vision hint is off.")  # fmt: skip
    assert seen[139]["t_last"] == 139 and seen[139]["t_cleared"] is None
    # familiar again at 141: cleared there, still in the box until 60 s after it was raised
    assert seen[141]["t_cleared"] == 141 and seen[141]["visible"]
    assert seen[169]["visible"] and seen[171]["visible"] is False  # shown once more, invisible
    assert all(seen[t] is None for t in range(173, mock.N_FRAMES, 2))
    assert len({e["id"] for e in seen.values() if e}) == 1


def test_the_unfamiliar_event_reopens_and_needs_10_s_to_be_raised():
    ev = Unfamiliar("v", THRESHOLD, 60)

    def at(t, far):
        line = {"t_frame": t, "hint": {"familiarity": 99.0 if far else 10.0}}
        out = ev.read(line, {"events": []})["events"]
        return out[0] if out else None

    assert at(1, True) is None and at(5, True) is None and at(9, False) is None
    assert at(11, True) is None and at(19, True) is None  # 8 s: not yet
    e = at(21, True)
    assert e["t_raised"] == 21
    assert at(25, False)["t_cleared"] == 25
    # unfamiliar again while the event is still in the box: it reopens once the scene
    # has held 10 s again, the same event
    assert at(29, True)["t_cleared"] == 25
    e = at(39, True)
    assert e["t_raised"] == 21 and e["t_cleared"] is None and e["t_last"] == 39
    assert at(41, False)["visible"] and at(81, False)["visible"] is False
    assert at(83, False) is None


def test_a_run_without_the_hint_shows_neither_numbers_nor_event(lines):
    """api.md v1.5: a run served without the hint has no `hint` key; a stray one on a
    line is not read."""
    other = copy.deepcopy(lines)
    other[5]["hint"] = {"familiarity": 500.0, "hint_shown": False}
    r = to_screen(other, "1.7")
    assert r["meta"]["hint"] is False
    assert all("hint" not in d for d in r["decisions"])
    assert not any(e["kind"] == "unfamiliar_scene" for d in r["decisions"] for e in d["events"])


def test_a_hinted_run_missing_its_fields_is_an_error(lines):
    other = hinted(lines)
    del other[3]["hint"]
    with pytest.raises(ValueError, match="hint"):
        to_screen(other, "1.7")
    other = hinted(lines)
    del other[3]["hint"]["familiarity"]
    with pytest.raises(ValueError, match="familiarity"):
        to_screen(other, "1.7")
    other = hinted(lines)
    del other[0]["hint"]["threshold"]
    with pytest.raises(ValueError, match="threshold"):
        to_screen(other, "1.7")


def test_the_prompt_pin_and_the_cvs_probabilities_are_read_and_never_passed_on(lines):
    """api.md v1.8 (the header's `prompt`) and v1.9 (each decision's `cvs_probs`): read
    under the 1.9 pin, nothing new drawn, so neither reaches the page."""
    newer = hinted(lines)
    for x in newer:
        x["api_version"] = "1.9"
        if x["kind"] == "decision":
            x["cvs_probs"] = {"two_structures": {"0": 0.91, "1": 0.08, "null": 0.01}}
    newer[0]["prompt"] = {"prev_cvs": "zeroed"}
    assert speaks("1.9", pinned_version(API_YAML))
    r = to_screen(newer, pinned_version(API_YAML))
    assert len(r["decisions"]) == len(to_screen(hinted(lines), "1.7")["decisions"])
    text = json.dumps(r)
    assert "cvs_probs" not in text and "prev_cvs" not in text and "zeroed" not in text


def test_the_previous_next_step_zeroed_is_read_and_never_passed_on(lines):
    """api.md v1.10: the prompt pin names `prev_next_step`, and
    with it zeroed `previous_state` has no next_step and `prior_block` takes the phase's
    own clause; nothing new drawn, and since this pin no `prior_block` reaches the page."""
    newer = hinted(lines)
    for x in newer:
        x["api_version"] = "1.10"
        if x["kind"] == "decision":
            x["previous_state"] = {"phase": "calot_triangle_dissection", "cvs": [0, 0, 0]}
            x["prior_block"] = "Priors: zeroed-form marker. Next step: dissect:cystic_duct 31%."
    newer[0]["prompt"] = {"prev_cvs": "zeroed", "prev_next_step": "zeroed"}
    r = to_screen(newer, pinned_version(API_YAML))
    plain = to_screen(hinted(lines), "1.7")
    assert [d["state"] for d in r["decisions"]] == [d["state"] for d in plain["decisions"]]
    text = json.dumps(r)
    for word in ("prior_block", "previous_state", "prev_next_step", "zeroed", "zeroed-form marker"):
        assert word not in text, word
    with pytest.raises(ValueError, match="1.14"):
        to_screen([dict(x, api_version="1.14") for x in newer], pinned_version(API_YAML))


def test_the_model_line_names_the_checkpoint_and_its_gate(lines):
    """api.md v1.6: the engineer view names the checkpoint and its
    gate's result and line; a log before v1.6 does not record the gate."""
    meta = to_screen(hinted(lines), "1.7")["meta"]
    assert meta["model"] == {
        "checkpoint": "stage2c-best", "gate": "not met",
        "gate_line": "triangle_cleared 0.74 vs 0.78 not met",
    }  # fmt: skip
    line = ("stage 1 gate MET: phase_within_3_of_specialist 0.9097 vs 0.7968 met; "
            "tool_mAP_within_3_of_specialist 0.8349 vs 0.6208 met; json_validity_99_5 1.0 vs 0.995 met")  # fmt: skip
    ck = {"name": "stage1-best", "gate": {"met": True, "line": line}}
    assert model_line({"checkpoint": ck}) == {
        "checkpoint": "stage1-best",
        "gate": "met",
        "gate_line": line.removeprefix("stage 1 gate MET: "),
    }
    # the verdict from `met`, the criteria's figures, never the line's
    # head or a parenthetical, whatever the line says of a decision
    real = ("stage 2 gate NOT MET (the owner's written decision to proceed): "
            "cvs_two_structures_3_above_probe 0.7171 vs 0.7293 NOT met; "
            "no_stage1_regression_tool_mAP 0.8382 vs 0.8349 met; no_stage1_regression_json_validity 1.0 vs 1.0 met")  # fmt: skip
    got = model_line({"checkpoint": {"name": "stage2c-best", "gate": {"met": False, "line": real}}})
    assert got["gate"] == "not met"
    assert got["gate_line"] == (
        "cvs_two_structures_3_above_probe 0.7171 vs 0.7293 not met; "
        "no_stage1_regression_tool_mAP 0.8382 vs 0.8349 met; no_stage1_regression_json_validity 1.0 vs 1.0 met"
    )  # fmt: skip
    # Stage 3's line, as its manifest carries it: a closing note with no figure against a
    # bar, left out, and the four criteria shown
    s3 = ("stage 3 gate NOT MET: next_step_top3_10_above_transition 0.6741 vs 0.7275 NOT met; "
          "rationale_contradiction_under_bar 0.01 vs 0.02 met; qa_15_above_zero_shot 0.604 vs 0.395 met; "
          "qa_10_above_majority 0.604 vs 0.3935 met; next_step top-3 beside the like-for-like rows on "
          "4326 points (reported): the model 0.6741, the gate's reference 0.7275, the phase table 0.6667, "
          "the constant 0.5987")  # fmt: skip
    got = model_line({"checkpoint": {"name": "stage3-final", "gate": {"met": False, "line": s3}}})
    assert got == {
        "checkpoint": "stage3-final", "gate": "not met",
        "gate_line": "next_step_top3_10_above_transition 0.6741 vs 0.7275 not met; "
        "rationale_contradiction_under_bar 0.01 vs 0.02 met; qa_15_above_zero_shot 0.604 vs 0.395 met; "
        "qa_10_above_majority 0.604 vs 0.3935 met",
    }  # fmt: skip
    note = "stage 2 gate NOT MET: a 0.7 vs 0.8 not met; proceeding anyway"  # a note: left out
    assert (
        model_line({"checkpoint": {"name": "s", "gate": {"met": False, "line": note}}})["gate_line"]
        == "a 0.7 vs 0.8 not met"
    )
    for odd in (
        "stage 2 gate NOT MET: a 0.7 vs 0.8 not met (decided to proceed)",  # a parenthetical in a clause
        "stage 2 gate NOT MET: a 0.7 vs 0.8 not met; b 0.9 vs 0.8 (waived)",  # a figure not a criterion
        "triangle_cleared 0.74 vs 0.78 not met",  # no head
        "stage 2 gate NOT MET:",  # no criterion
        "stage 2 gate NOT MET: proceeding anyway",  # notes alone
    ):
        assert (
            model_line({"checkpoint": {"name": "s", "gate": {"met": False, "line": odd}}})[
                "gate_line"
            ]
            is None
        ), odd
    assert model_line({"checkpoint": {"name": "x", "gate": None}})["gate"] == "none"
    assert model_line({"checkpoint": {"name": "stage1-best", "form": "merged"}}) == {
        "checkpoint": "stage1-best", "gate": None, "gate_line": None}  # fmt: skip
    assert model_line({"checkpoint": "mock"})["checkpoint"] == "mock"
    assert model_line({})["checkpoint"] is None
    # only plain words and figures pass: never a path, a host or an address
    for bad in ("read from /data/run/gate.json", "gate MET on box ~ok", "by someone@somewhere"):
        got = model_line({"checkpoint": {"name": "s", "gate": {"met": True, "line": bad}}})
        assert got["gate"] == "met" and got["gate_line"] is None
    assert model_line({"checkpoint": {"name": "../../etc"}})["checkpoint"] is None


def served(lines: list[dict], form: str = "stateless") -> list[dict]:
    """The mock's log as a stateless run of `stage3-final` with the served CVS carries it
    (api.md v1.11, v1.12): no hint, the header's choice, each decision's `cvs_served`."""
    out = copy.deepcopy(lines)
    for x in out:
        x["api_version"] = "1.12"
    out[0]["decision_form"] = {"name": form, "reading": "each decision alone", "rows": "gate-blank/",
                               "served": True, "by": "the evaluation's ruling"}  # fmt: skip
    out[0]["cvs_served"] = {
        "choice": {"report": "reports/diagnostics/cvs-choice.json", "sha256": "a99e", "rows": "gate-blank"},
        "criteria": {"two_structures": {"source": "p1", "threshold": 0.000261}},
        "specialist": {"name": "cvs-specialist-hints-oof", "manifest_sha256": "b2de"},
    }  # fmt: skip
    for x in out:
        if x["kind"] == "decision":
            x["previous_state"] = x["prior_block"] = None
            reply = x["state"]["cvs"]
            x["cvs_served"] = {
                "two_structures": {"value": int(x["t_frame"] >= 100), "source": "p1"},
                "triangle_cleared": {"value": reply["triangle_cleared"], "source": "specialist"},
                "cystic_plate": {"value": None, "source": "reply"},
            }
    return out


def test_the_served_cvs_is_passed_on_with_its_source_and_the_form_named(lines):
    """api.md v1.11 and v1.12: each decision's
    served CVS is passed on as each criterion's value and source, and nothing is worked
    out from it; the meta names the decision form; nothing else of the header's choice
    leaves the server."""
    r = to_screen(served(lines), pinned_version(API_YAML))
    assert r["meta"]["cvs_served"] is True and r["meta"]["decision_form"] == "stateless"
    assert r["meta"]["hint"] is False
    ds = r["decisions"]
    late = next(d for d in ds if d["t_frame"] >= 100)
    assert late["cvs_served"]["two_structures"] == {"value": 1, "source": "p1"}
    assert late["cvs_served"]["cystic_plate"] == {"value": None, "source": "reply"}
    assert all("cvs_served_first" not in d for d in ds)
    # the memory stays the server's, but for its first-achieved CVS times, cut away in
    # every run (no criterion is drawn as achieved)
    plain = to_screen(lines, "1.0")["decisions"]
    assert [d["memory"] for d in ds] == [d["memory"] for d in plain]
    assert all("cvs_first_achieved" not in d["memory"] for d in ds + plain)
    assert all("phase_timeline" in d["memory"] and "flags" in d["memory"] for d in ds)
    text = json.dumps(r)
    for word in (
        "0.000261",
        "reports/",
        "a99e",
        "b2de",
        "cvs-specialist",
        "gate-blank",
        "each decision alone",
    ):
        assert word not in text, word
    # a log before v1.11 has no served CVS, and one before v1.12 is in the trained form
    old = to_screen(hinted(lines), "1.7")
    assert old["meta"]["cvs_served"] is False and old["meta"]["decision_form"] == "trained"
    assert all("cvs_served" not in d for d in old["decisions"])


def test_the_replys_own_cvs_and_the_undrawn_memory_never_leave(lines):
    """The reply's own CVS leaves nowhere, neither the state's
    `cvs`, nor the earlier states the memory keeps, nor the raw reply's `"cvs"` member;
    the memory carries only what the screen draws; the rest of the reply is as the model
    wrote it, and the clipping-before-CVS flag stays."""
    by_seq = {x["seq"]: x for x in lines if x["kind"] == "decision"}
    for r in (to_screen(served(lines), pinned_version(API_YAML)), to_screen(lines, "1.0")):
        ds = r["decisions"]
        assert ds and all("cvs" not in d["state"] for d in ds)
        assert all("clipping_before_cvs" in d["state"]["risk_flags"] for d in ds)
        assert all(set(d["memory"]) == set(MEMORY_KEYS) for d in ds)
        assert all('"cvs"' not in d["reply"] for d in ds)
        for d in ds:
            sent = by_seq[d["seq"]]["reply"]
            try:
                whole = json.loads(sent)
            except ValueError:
                continue
            assert json.loads(d["reply"]) == {k: v for k, v in whole.items() if k != "cvs"}
            assert list(json.loads(d["reply"])) == [k for k in whole if k != "cvs"]
        text = json.dumps(r)
        assert '"last_states"' not in text and '"self_consistency"' not in text


@pytest.mark.parametrize(
    "sent, kept",
    [
        ('{"t":1,"phase":"P","cvs":{"two_structures":1}}', '{"t":1,"phase":"P"}'),
        ('{"t":1,"cvs":{"two_structures":1,"triangle_cl', '{"t":1,'),
        ('{"t":1,"cvs":{"two_structures":1},"risk', '{"t":1,"risk'),
        ('{"t":1,"cvs":[1,0,1],"x":2', '{"t":1,"x":2'),
        ('{"t":1,"phase":"P"}', '{"t":1,"phase":"P"}'),
        ("not json at all", "not json at all"),
        # a nested value is cut whole, however it ends
        ('{"t":1,"cvs":{"two_structures":{"v":1,"p":0.9},"cystic_plate":0},"risk', '{"t":1,"risk'),
        ('{"t":1,"cvs":{"two_structures":{"v":1,"p":0.9},"cyst', '{"t":1,'),
        ('{"t":1,"cvs":{"a":{"b":[1,{"c":0}]}}} and then', '{"t":1} and then'),
        ('{"t":1,"cvs":{"why":"a } and a {","two_structures":1},"x":2', '{"t":1,"x":2'),
        ('{"t":1,"cvs":"yes \\" , ok","x":2', '{"t":1,"x":2'),
        ('[{"cvs":{"two_structures":1}}', "[{}"),
        (
            '{"t":1,"rationale":"its \\"cvs\\": not reached","x',
            '{"t":1,"rationale":"its \\"cvs\\": not reached","x',
        ),
        # what cannot be cut whole, or leaves a CVS key, is withheld
        ('{"t":1,"cvs":{"two_structures":[1}],"x":2', REPLY_WITHHELD),
        ('{"t":1,"two_structures":1,"x', REPLY_WITHHELD),
    ],
)
def test_the_reply_text_loses_its_cvs_member_however_it_ends(sent, kept):
    assert reply_text(sent) == kept
    assert '"cvs"' not in kept.replace('\\"cvs\\"', "")


def test_the_page_knows_a_withheld_reply_by_the_adapters_words():
    """The engineer's pane marks an unparsed reply as shown "as it came, less any cvs"
    unless the adapter withheld it, which it knows by the same words."""
    page = (Path(__file__).parents[1] / "web/src/panels.js").read_text()
    assert f"const WITHHELD = '{REPLY_WITHHELD}';" in page


def test_a_criterion_key_left_in_an_unparsed_reply_withholds_it():
    """The withholding check knows every criterion the screen draws."""
    for k in CVS_KEYS:
        assert reply_text(f'{{"t":1,"{k}":0,"x') == REPLY_WITHHELD


def test_vals_reading_is_cut_to_the_three_figures_with_their_counts():
    """api.md v1.13: per criterion val's precision, NPV and
    share met, each with the count it is read on, and the points and videos; a p1
    criterion's out-of-fold figures in place of the in-sample ones, marked so; the
    report's path, hash, commits, note and intervals stay on the server."""
    cut = val_reading(mock.VAL_READING)
    assert list(cut) == list(CVS_KEYS)
    assert cut["two_structures"] == {
        "precision": {"value": 0.39, "n": 330}, "npv": {"value": 0.92, "n": 870},
        "met_share": {"value": 0.18, "n": 1200}, "points": 1200, "videos": 12, "out_of_fold": True,
    }  # fmt: skip
    assert cut["triangle_cleared"]["precision"] == {"value": 0.36, "n": 250}
    assert not cut["triangle_cleared"]["out_of_fold"] and not cut["cystic_plate"]["out_of_fold"]
    text = json.dumps(cut)
    assert "results.json" not in text and "made-up" not in text and '"ci"' not in text


@pytest.mark.parametrize(
    "spoil",
    [
        lambda v: {"unavailable": "the report's section read another choice"},
        lambda v: v["criteria"].pop("cystic_plate"),
        lambda v: v["criteria"]["triangle_cleared"]["npv"].pop("calls"),
        lambda v: v["criteria"]["cystic_plate"]["precision"].update(value=1.4),
        lambda v: v["criteria"]["cystic_plate"].update(points=0),
        lambda v: v["criteria"]["cystic_plate"]["met_share"].update(value=True),
    ],
)
def test_a_val_reading_that_is_unavailable_or_incomplete_draws_nothing(spoil):
    v = copy.deepcopy(mock.VAL_READING)
    out = spoil(v)
    assert val_reading(out if isinstance(out, dict) and "unavailable" in out else v) is None


def test_the_rollout_carries_vals_reading_from_its_header_or_its_listing(lines):
    """A log written under v1.13 carries the reading in its header's `cvs_served`; one
    written before takes the listing's (`GET /api/runs/{run}`'s `cvs_served_val`); a run
    without the served CVS carries none."""
    cut = val_reading(mock.VAL_READING)
    new = served(lines)
    for x in new:
        x["api_version"] = "1.13"
    new[0]["cvs_served"]["val_reading"] = mock.VAL_READING
    assert to_screen(new, "1.13")["meta"]["cvs_val"] == cut
    assert to_screen(served(lines), "1.13")["meta"]["cvs_val"] is None
    assert to_screen(served(lines), "1.13", cut)["meta"]["cvs_val"] == cut
    assert to_screen(lines, "1.13", cut)["meta"]["cvs_val"] is None
    assert "results.json" not in json.dumps(to_screen(new, "1.13"))


def test_the_ask_answer_is_cut_to_what_the_page_draws():
    """The interactive turn carries its answer alone; a refusal
    keeps its code and reason."""
    up = {"api_version": "1.12", "answer": "a grasper", "t": 5, "compute_s": 1.2, "valid": True}
    assert ask_answer(up) == {"answer": "a grasper"}
    no = {"api_version": "1.12", "error": "no_model", "detail": "no model", "extra": 1}
    assert ask_answer(no) == {"error": "no_model", "detail": "no model"}


@pytest.mark.parametrize(
    "spoil, match",
    [
        (lambda d: d.pop("cvs_served"), "lacks"),
        (lambda d: d["cvs_served"]["two_structures"].update(source="guess"), "no known source"),
        (lambda d: d["cvs_served"]["triangle_cleared"].update(value=0.7), "value"),
        (lambda d: d["cvs_served"]["triangle_cleared"].update(value=True), "value"),
        (lambda d: d["cvs_served"].pop("cystic_plate"), "no known source"),
    ],
)
def test_a_served_cvs_the_screen_cannot_read_is_refused(lines, spoil, match):
    """Rule 5: a served CVS without a known source or with a value that is not 0, 1 or
    null is never drawn, nor filled in."""
    bad = served(lines)
    spoil(next(x for x in bad if x["kind"] == "decision"))
    with pytest.raises(ValueError, match=match):
        to_screen(bad, pinned_version(API_YAML))
    form = served(lines)
    form[0]["decision_form"]["name"] = "blank"
    with pytest.raises(ValueError, match="decision form"):
        to_screen(form, pinned_version(API_YAML))

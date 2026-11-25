"""Following a run as it is written: the follower keeps every
line once and in order across upstream drops, says when it is reconnecting, refuses a
newer API than the pin, and writes the session log once even across a restart."""

import asyncio
import json

from chole_demo import follow
from chole_demo.client.adapter import to_screen
from chole_demo.feeds import mock
from chole_demo.follow import Follow
from chole_demo.session_log import SessionLog

LIVE = mock.generate("live")
HEADER, BODY, END = LIVE[0], LIVE[1:-1], LIVE[-1]


def _key(x):
    return x["kind"], x["tick"]


def _scripted(*attempts):
    """An opener whose n-th connection yields attempts[n] and then drops (or ends)."""
    calls = []

    async def opener(run, video_id):
        calls.append(1)
        lines = attempts[min(len(calls), len(attempts)) - 1]
        for x in lines:
            await asyncio.sleep(0)
            yield x
        if lines and lines[-1]["kind"] != "end":
            raise ConnectionError("the upstream went away")

    return opener, calls


def _drain(hub, after=0):
    async def go():
        out = []
        async for m in hub.watch(after, ping_s=5):
            out.append(m)
        return out

    return go()


def test_drops_are_reconnected_and_every_line_kept_once_in_order(tmp_path, monkeypatch):
    monkeypatch.setattr(follow, "BACKOFF_S", (0.01,))
    half = len(BODY) // 2
    # first connection: the start, then a drop; second: all again from the store, then the end
    opener, calls = _scripted([HEADER, *BODY[:half]], [HEADER, *BODY, END])

    async def main():
        hub = Follow(mock.WRITING, mock.VIDEO_ID, opener, "1.0", SessionLog(tmp_path, "r", "v"))
        hub.start()
        msgs = await asyncio.wait_for(_drain(hub), 10)
        await hub.stop()
        return hub, msgs

    _, msgs = asyncio.run(main())
    assert len(calls) == 2
    statuses = [m["upstream"] for m in msgs if m["type"] == "status"]
    assert statuses[-1] == "ended" and msgs[-1]["type"] == "end"
    lines = [m["line"] for m in msgs if m["type"] == "line"]
    assert [_key(x) for x in lines] == [_key(x) for x in BODY]
    logged = [json.loads(x)["line"] for x in (tmp_path / "r" / "v.jsonl").read_text().splitlines()]
    assert len(logged) == len(BODY) + 2 and logged[-1]["kind"] == "end"
    # the delay figures as a replay reads them (api.md v1.3), each decision counted once
    whole = to_screen([HEADER, *BODY, END], "1.0")["decisions"]
    assert [x["delay"] for x in lines if x["kind"] == "decision"] == [d["delay"] for d in whole]
    assert all("over_d_rate" not in x["delay"] for x in logged if x["kind"] == "decision")


def test_a_viewer_sees_the_reconnecting_state_then_the_rest(monkeypatch):
    monkeypatch.setattr(follow, "BACKOFF_S", (0.3,))
    opener, _ = _scripted([HEADER, *BODY[:3]], [HEADER, *BODY, END])

    async def main():
        hub = Follow("r", "v", opener, "1.0", None)
        hub.start()
        msgs = await asyncio.wait_for(_drain(hub), 10)
        await hub.stop()
        return msgs

    msgs = asyncio.run(main())
    statuses = [m["upstream"] for m in msgs if m["type"] == "status"]
    assert "reconnecting" in statuses and statuses.index("reconnecting") < statuses.index("ended")
    assert [_key(m["line"]) for m in msgs if m["type"] == "line"] == [_key(x) for x in BODY]


def test_a_newer_api_than_the_pin_is_not_shown(monkeypatch):
    monkeypatch.setattr(follow, "BACKOFF_S", (0.01,))
    newer = [dict(x, api_version="1.9") for x in LIVE]
    opener, calls = _scripted(newer)

    async def main():
        hub = Follow("r", "v", opener, "1.0", None)
        hub.start()
        msgs = await asyncio.wait_for(_drain(hub), 10)
        await hub.stop()
        return hub, msgs

    hub, msgs = asyncio.run(main())
    assert hub.upstream == "unreadable" and not hub.items and len(calls) == 1
    assert msgs[-1] == {"type": "status", "upstream": "unreadable"}


def test_a_header_the_screen_refuses_ends_the_follow(monkeypatch):
    """An unknown source or a real video without its attribution is refused once, not retried as if the connection had dropped."""
    monkeypatch.setattr(follow, "BACKOFF_S", (0.01,))
    odd = [dict(x) for x in LIVE]
    odd[0] = dict(odd[0], source="somewhere_new")
    opener, calls = _scripted(odd)

    async def main():
        hub = Follow("r", "v", opener, "1.4", None)
        hub.start()
        msgs = await asyncio.wait_for(_drain(hub), 10)
        await hub.stop()
        return hub, msgs

    hub, msgs = asyncio.run(main())
    assert hub.upstream == "unreadable" and hub.meta is None and not hub.items
    assert len(calls) == 1 and msgs[-1] == {"type": "status", "upstream": "unreadable"}


def test_the_session_log_survives_a_restart_without_duplicates(tmp_path):
    first = SessionLog(tmp_path, "stage1:run/../x", "cholec80:12")
    for x in LIVE[:10]:
        first.write(x)
    again = SessionLog(tmp_path, "stage1:run/../x", "cholec80:12")
    for x in LIVE:
        again.write(x)
    assert again.path.is_relative_to(tmp_path) and ".." not in again.path.parts
    logged = [json.loads(x) for x in again.path.read_text().splitlines()]
    assert [_key(x["line"]) if "tick" in x["line"] else x["line"]["kind"] for x in logged] == [
        _key(x) if "tick" in x else x["kind"] for x in LIVE
    ]
    assert all(isinstance(x["received"], float) for x in logged)


def test_a_run_served_with_the_hint_is_followed_with_its_numbers_and_event(monkeypatch):
    """api.md v1.5: the probe's numbers and the "unfamiliar scene" event reach a viewer
    of a run being written as they reach a replay (the adapter's one reader)."""
    lines = [dict(x, api_version="1.7") for x in LIVE[:40]]
    lines[0]["hint"] = {"probe": "p", "manifest_sha256": "h", "threshold": 74.6}
    for x in lines[1:]:
        if x["kind"] == "decision":
            x["hint"] = {"familiarity": 90.0, "hint_shown": False}
    opener, _ = _scripted(lines)
    monkeypatch.setattr(follow, "BACKOFF_S", (5,))

    async def main():
        hub = Follow("r", "v", opener, "1.7", None)
        hub.start()
        for _ in range(200):
            await asyncio.sleep(0.01)
            if len(hub.items) == len(lines) - 1:
                break
        await hub.stop()
        return hub

    hub = asyncio.run(main())
    assert hub.meta["hint"] is True
    got = [x for x in hub.items if x["kind"] == "decision"]
    assert got and all(d["hint"]["unfamiliar"] and not d["hint"]["shown"] for d in got)
    raised = [e for d in got for e in d["events"] if e["kind"] == "unfamiliar_scene"]
    first = min(d["t_frame"] for d in got)
    assert raised and min(e["t_raised"] for e in raised) >= first + 10

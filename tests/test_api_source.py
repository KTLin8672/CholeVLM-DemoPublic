"""The screen on the model server (api.md v1.0): the runs and
the logs read through the adapter, the frames and the video proxied by byte ranges,
the configured video first, and nothing about the upstream reaching the browser."""

import json

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from chole_demo.client.adapter import ApiSource, default_video, demo_config, pinned_version
from chole_demo.feeds import mock
from chole_demo.owner import Owner
from chole_demo.server import create_app

PASSWORD = "a test password, not the owner's"


def _owner(tmp_path):
    owner = Owner(tmp_path / "owner.local.yaml")
    owner.set_password(PASSWORD)
    return owner


RUN = "stage1-best-offline-D4-20261106T002825"
VID = "cholec80:12"
SECRET = "/home/someone/private/path"  # what the upstream may carry and must not leak


def _real_like_log():
    lines = [dict(x) for x in mock.generate("offline")]
    for x in lines:
        x["run"], x["video_id"] = RUN, VID
    h = lines[0]
    h["source"] = "val_shards"
    h["commits"] = {"chole_eval": {"commit": "abc", "path": SECRET}}
    h["video"] = {"source": "shards_1fps", "fps": 1, "t0": 0}
    lines[1]["batch"], lines[1]["note"] = 8, SECRET  # a field the screen does not draw
    return lines


LOG = _real_like_log()
VIDEO = bytes(range(256)) * 8

# a later run of a stretch of the same video (`from_t`), written by
# the server at API 1.2; its log is larger than the first run's
STRETCH = "stage1-best-offline-D4-20261106T180000"
FROM_T = 493
WRITING = "stage1-best-offline-D4-20261106T190000"  # still being written: followed only


def _stretch_log():
    lines = [dict(x) for x in mock.generate("offline")]
    for x in lines:
        x["run"], x["video_id"], x["api_version"] = STRETCH, VID, "1.2"
        if "t_frame" in x:
            x["t_frame"] += FROM_T
    lines[0].update(source="val_shards", video={"source": "shards_1fps", "fps": 1, "t0": 0})
    return lines


STRETCH_LOG = _stretch_log()

# a held-out video, its licence not yet known to allow public display,
# as api.md v1.4 writes its run: `source: test_root`, the header's `split`, the frames
# encoded live, `attribution.public` false and `attribution.ood` the line on its frames
OOD_RUN, OOD_VID = "stage1-best-merged-ood-D8", "heichole:3"
OOD_LINE = "out-of-distribution: a hospital the model never trained on (HeiChole)"
OOD_ATTR = {
    "dataset": "HeiChole", "holder": "its makers", "licence": "non-commercial research",
    "public": False, "ood": OOD_LINE, "adaptation": "1 fps frames of the dataset as an H.264 video",
    "research_line": "research demo, not for clinical use", "line": "HeiChole; its licence",
}  # fmt: skip
# a video of another dataset the API marks not public (api.md v1.4): hidden the same way
PRIVATE_VID = "cholect50:99"


def _ood_log():
    lines = [dict(x) for x in mock.generate("offline")]
    for x in lines:
        x["run"], x["video_id"], x["api_version"] = OOD_RUN, OOD_VID, "1.4"
        if x["kind"] == "decision":
            x["encode_s"] = 1.5
    lines[0].update(source="test_root", split="ood_test",
                    live_encode={"pad_to": {"pairs": 8, "current": 1}, "tower": "qwen3_5-4b"},
                    video={"source": "test_root_1fps", "fps": 1, "t0": 0, "attribution": OOD_ATTR})  # fmt: skip
    return lines


OOD_LOG = _ood_log()

# a second whole run of the video, its log larger: the screen opens the video on it
FULLER = "stage1-best-merged-cholec80_12-D2"
DEMO_VID, DEMO_RUN = "cholect50:VID103", "stage1-best-merged-cholect50_VID103-D4"
# runs that hold a demo video and are not its run: a parity or
# reconciliation run's sampled points, a latency test's live replay, the first ticks only,
# evaluation's whole offline run over its own five videos; and a live replay stopped before
# its manifest was written, its fields in the info alone (the model server, 2026-11-07)
NOT_DEMO = {
    "stage1-best-offline-D4-parity": {"manifest": {"from_rows": {"path": SECRET}}},
    "stage1-best-live-D4-latency": {"manifest": {"mode": "live"}},
    "stage1-best-offline-D4-first8": {"manifest": {"limit": 8}},
    "stage1-best-merged-parity5-D8": {"video_ids": ["endoscapes:124", DEMO_VID]},
    "stage1-best-merged-parity5-live-D8": {
        "status": "running", "manifest": None, "mode": "live", "speed": 1.0, "from_t": 0, "limit": 0,
    },
}  # fmt: skip


def upstream(request: httpx.Request) -> httpx.Response:
    p = request.url.raw_path.decode()
    if p == "/api/runs":
        runs = [RUN, STRETCH, WRITING, OOD_RUN, FULLER, *NOT_DEMO]
        return httpx.Response(200, json={"api_version": "1.2", "runs": runs})
    if p.removeprefix("/api/runs/") in NOT_DEMO:
        extra = dict(NOT_DEMO[p.removeprefix("/api/runs/")])
        manifest = {"kind": "rollout", "mode": "offline", "source": "val_shards"}
        info = {"status": "done", "video_ids": [DEMO_VID], "manifest": manifest}
        if "manifest" in extra:
            m = extra.pop("manifest")
            info["manifest"] = m if m is None else {**manifest, **m}
        return httpx.Response(200, json={**info, **extra})
    if p == f"/api/runs/{FULLER}":
        files = [{"path": f"{VID}.jsonl", "size": 150000}]
        manifest = {"kind": "rollout", "mode": "offline", "from_t": 0, "limit": 0, "files": files}
        return httpx.Response(
            200, json={"status": "done", "video_ids": [VID], "manifest": manifest}
        )
    if p == f"/api/runs/{OOD_RUN}":
        attr = {OOD_VID: OOD_ATTR, PRIVATE_VID: {**OOD_ATTR, "dataset": "CholecT50", "ood": None}}
        return httpx.Response(200, json={"status": "done", "video_ids": [OOD_VID, PRIVATE_VID],
                                         "attribution": attr,
                                         "manifest": {"mode": "offline", "source": "test_root"}})  # fmt: skip
    if p == f"/api/load/{OOD_RUN}/heichole%3A3":
        return httpx.Response(200, text="".join(json.dumps(x) + "\n" for x in OOD_LOG))
    if p.startswith(("/api/frames/heichole%3A3/", "/api/frames/cholect50%3A99/")) or p in (
        "/api/video/heichole%3A3",
        "/api/video/cholect50%3A99",
    ):
        return httpx.Response(
            200, content=b"\xff\xd8jpg\xff\xd9", headers={"content-type": "image/jpeg"}
        )
    if p == f"/api/runs/{WRITING}":  # API 1.2 lists a running run's videos too
        return httpx.Response(200, json={"status": "running", "video_ids": [VID], "from_t": 0})
    for run, size in ((RUN, 71391), (STRETCH, 280000)):
        if p == f"/api/runs/{run}":
            files = [{"path": f"{VID}.jsonl", "size": size}, {"path": "endoscapes:124.jsonl"}]
            return httpx.Response(
                200,
                json={
                    "status": "done",
                    "from_t": FROM_T if run == STRETCH else None,
                    "video_ids": ["endoscapes:124", VID],
                    "manifest": {
                        "mode": "offline", "source": "val_shards", "path": SECRET, "files": files,
                    },
                },
            )  # fmt: skip
    for run, log in ((RUN, LOG), (STRETCH, STRETCH_LOG)):
        if p == f"/api/load/{run}/cholec80%3A12":
            return httpx.Response(200, text="".join(json.dumps(x) + "\n" for x in log))
    if p.startswith("/api/frames/cholec80%3A12/"):
        return httpx.Response(
            200,
            content=b"\xff\xd8jpg\xff\xd9",
            headers={"content-type": "image/jpeg", "x-path": SECRET},
        )
    if p == "/api/video/cholec80%3A12":
        rng = request.headers.get("range")
        hdr = {"content-type": "video/mp4", "accept-ranges": "bytes", "x-video-source": SECRET}
        if rng:
            a, b = (int(v) for v in rng.removeprefix("bytes=").split("-"))
            hdr["content-range"] = f"bytes {a}-{b}/{len(VIDEO)}"
            return httpx.Response(206, content=VIDEO[a : b + 1], headers=hdr)
        return httpx.Response(200, content=VIDEO, headers=hdr)
    if p == "/api/ask":
        return httpx.Response(
            503,
            json={
                "api_version": "1.1",
                "error": "no_model",
                "detail": "this server holds no model",
            },
        )
    return httpx.Response(404, json={"error": "not_found", "detail": SECRET})


@pytest.fixture
def client(tmp_path):
    source = ApiSource(
        "http://upstream.test",
        client=httpx.Client(
            base_url="http://upstream.test", transport=httpx.MockTransport(upstream)
        ),
    )
    source.async_transport = httpx.MockTransport(upstream)
    app = create_app(
        source,
        web_dist=tmp_path / "nodist",
        access_log=tmp_path / "a.log",
        pinned=pinned_version(),
        owner=_owner(tmp_path),
        demo={"videos": [VID, "endoscapes:124", OOD_VID, PRIVATE_VID], "interim": None},
    )
    return TestClient(app)


def with_demo_run(request: httpx.Request) -> httpx.Response:
    """The upstream once the demo's own run of its video exists: whole, offline."""
    p = request.url.raw_path.decode()
    if p == "/api/runs":
        runs = upstream(request).json()["runs"] + [DEMO_RUN]
        return httpx.Response(200, json={"api_version": "1.4", "runs": runs})
    if p == f"/api/runs/{DEMO_RUN}":
        manifest = {"kind": "rollout", "mode": "offline", "from_t": 0, "limit": 0, "D": 4}
        return httpx.Response(
            200, json={"status": "done", "video_ids": [DEMO_VID], "manifest": manifest}
        )
    return upstream(request)


# an earlier whole run of the demo's video at D = 8: half the decisions, half the log
DEMO_RUN_D8 = "stage1-best-merged-cholect50_VID103-D8"


def with_two_demo_runs(request: httpx.Request) -> httpx.Response:
    """Two whole runs of one demo video, as HeiChole's D = 8 and D = 4 (2026-11-07)."""
    p = request.url.raw_path.decode()
    if p == "/api/runs":
        runs = with_demo_run(request).json()["runs"] + [DEMO_RUN_D8]
        return httpx.Response(200, json={"api_version": "1.4", "runs": runs})
    for run, d, size in ((DEMO_RUN, 4, 2000), (DEMO_RUN_D8, 8, 1000)):
        if p == f"/api/runs/{run}":
            files = [{"path": f"{DEMO_VID}.jsonl", "size": size}]
            manifest = {"kind": "rollout", "mode": "offline", "from_t": 0, "limit": 0, "D": d,
                        "files": files}  # fmt: skip
            return httpx.Response(
                200, json={"status": "done", "video_ids": [DEMO_VID], "manifest": manifest}
            )
    return with_demo_run(request)


# the final model's whole run of the demo's video, smaller than the first checkpoint's;
# and a later rerun of the first checkpoint, fuller than either
FINAL_RUN = "stage3-final-merged-cholect50_VID103-D4"
RERUN = "stage1-best-merged-cholect50_VID103-D4-r2"


def with_final_model(request: httpx.Request) -> httpx.Response:
    """The upstream the day the final model's run exists."""
    p = request.url.raw_path.decode()
    runs = {  # run: (checkpoint, its manifest's hash, created, log size)
        DEMO_RUN_D8: ("stage1-best", "s1", 50.0, 1000),
        DEMO_RUN: ("stage1-best", "s1", 100.0, 2000),
        FINAL_RUN: ("stage3-final", "s3", 300.0, 1500),
        RERUN: ("stage1-best", "s1", 400.0, 2500),
    }
    if p == "/api/runs":
        listed = upstream(request).json()["runs"] + list(runs)
        return httpx.Response(200, json={"api_version": "1.4", "runs": listed})
    for run, (name, sha, created, size) in runs.items():
        if p == f"/api/runs/{run}":
            manifest = {
                "kind": "rollout", "mode": "offline", "from_t": 0, "limit": 0, "D": 4,
                "checkpoint": {"name": name, "manifest_sha256": sha, "form": "merged"},
                "created": created, "files": [{"path": f"{DEMO_VID}.jsonl", "size": size}],
            }  # fmt: skip
            return httpx.Response(
                200, json={"status": "done", "video_ids": [DEMO_VID], "manifest": manifest}
            )
    return with_demo_run(request)


def _app(tmp_path, demo, fake=upstream):
    source = ApiSource(
        "http://upstream.test",
        client=httpx.Client(base_url="http://upstream.test", transport=httpx.MockTransport(fake)),
    )
    source.async_transport = httpx.MockTransport(fake)
    app = create_app(
        source, web_dist=tmp_path / "nodist", access_log=tmp_path / "a.log",
        pinned=pinned_version(), owner=_owner(tmp_path), demo=demo,
    )  # fmt: skip
    return TestClient(app)


def test_the_configured_video_comes_first_on_its_fullest_run(client):
    vids = client.get("/api/videos").json()
    assert vids[0]["video_id"] == VID  # the fixture's demo list opens on it
    pairs = [(v["run"], v["video_id"], v["writing"]) for v in vids]
    assert pairs[:2] == [(FULLER, VID, False), (WRITING, VID, True)]
    # one finished run a video: RUN's whole run of it is smaller
    assert (RUN, VID, False) not in pairs and (RUN, "endoscapes:124", False) in pairs
    # a stretch of a demo video is not its run, nor are the runs of NOT_DEMO
    assert {v["run"] for v in vids} == {FULLER, RUN, WRITING} and SECRET not in json.dumps(vids)
    keys = {"run", "video_id", "mode", "source", "from_t", "writing", "held_out"}
    assert all(set(v) == keys and v["held_out"] is False for v in vids)
    assert vids[0]["from_t"] == 0


def test_a_run_still_being_written_is_never_served_as_a_replay(client):
    # API 1.2 lists its videos while it runs (the stretch was, 2026-11-06 08:05-08:16)
    assert client.get(f"/api/rollout/{WRITING}/cholec80%3A12").status_code == 409


def test_a_stretch_written_at_1_2_reads_and_opens_at_its_start(tmp_path):
    # served as the real one is: the interim, while the demo's videos have no run
    client = _app(tmp_path, {"videos": [DEMO_VID], "interim": {"run": STRETCH, "video": VID}})
    res = client.get(f"/api/rollout/{STRETCH}/cholec80%3A12")
    r = res.json()
    assert res.status_code == 200 and r["meta"]["api_version"] == pinned_version()
    assert all("over_d_rate" in d["delay"] for d in r["decisions"])  # read in 1.3's sense
    assert r["meta"]["first_decision_t"] == min(d["t_frame"] for d in r["decisions"]) >= FROM_T


def without_fuller(request: httpx.Request) -> httpx.Response:
    """The upstream before FULLER: RUN is the video's one finished whole run."""
    if request.url.raw_path.decode() == "/api/runs":
        runs = [r for r in upstream(request).json()["runs"] if r != FULLER]
        return httpx.Response(200, json={"api_version": "1.2", "runs": runs})
    return upstream(request)


def test_the_real_log_reaches_the_screen_without_the_upstreams_details(tmp_path):
    client = _app(tmp_path, {"videos": [VID, "endoscapes:124"], "interim": None}, without_fuller)
    res = client.get(f"/api/rollout/{RUN}/cholec80%3A12")
    r = res.json()
    assert res.status_code == 200 and r["meta"]["feed"] == "real" and r["meta"]["banner"] is None
    assert r["meta"]["video"] == {"fps": 1, "t0": 0}
    assert r["meta"]["last_decision_t"] == max(d["t_frame"] for d in r["decisions"])
    assert SECRET not in res.text and "batch" not in r["decisions"][0]
    assert r["meta"]["attribution"].startswith(
        "Cholec80 · CAMMA, University of Strasbourg · CC BY-NC-SA 4.0"
    )
    assert "not for clinical use" in r["meta"]["attribution"]


def test_only_listed_videos_are_served(client):
    assert client.get(f"/api/rollout/{RUN}/cholec80%3A99").status_code == 404
    assert client.get("/api/video/cholec80%3A99").status_code == 404


def test_frames_and_video_are_proxied_with_safe_headers_only(client):
    f = client.get("/api/frames/cholec80%3A12/5.jpg?variant=video")
    assert (
        f.status_code == 200
        and f.headers["content-type"] == "image/jpeg"
        and "x-path" not in f.headers
    )
    v = client.get("/api/video/cholec80%3A12", headers={"Range": "bytes=256-511"})
    assert v.status_code == 206 and v.content == bytes(range(256))
    assert (
        v.headers["content-range"] == f"bytes 256-511/{len(VIDEO)}"
        and "x-video-source" not in v.headers
    )
    missing = client.get("/api/frames/other%3A1/5.jpg")
    assert missing.status_code == 404 and SECRET not in missing.text


def test_ask_passes_the_no_model_answer_on(client):
    assert client.post("/api/owner", json={"password": PASSWORD}).status_code == 200
    body = {"run": RUN, "video_id": VID, "t": 5, "question": "describe the scene"}
    res = client.post("/api/ask", json=body)
    assert res.status_code == 503 and res.json()["error"] == "no_model"


# step 2: following a run still being written through the model server's stream (api.md v1.1)
def _stream_upstream(store: list, written: list):
    """A stand-in for the model server: `/api/load` gives the lines stored so far;
    `WS /api/stream` sends hello, then (after a seek past the end) each line written
    after it opened. One line is written just after the socket opens, before the
    client reads the store: it reaches the client twice and must be shown once."""
    import asyncio as aio

    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route, WebSocketRoute

    async def load(request):
        return PlainTextResponse("".join(json.dumps(x) + "\n" for x in store))

    async def stream(ws):
        await ws.accept()
        sent = len(store)
        await ws.send_json({"type": "hello", "api_version": "1.0", "header": store[0]})
        store.append(written.pop(0))  # written between the socket and the client's read
        while True:
            await aio.sleep(0.02)
            for x in store[sent:]:
                await ws.send_json({"type": x["kind"], "line": x})
                if x["kind"] == "end":
                    await ws.close()
                    return
            sent = len(store)
            if written:
                store.append(written.pop(0))

    return Starlette(routes=[Route("/api/load/{run}/{video}", load),
                             WebSocketRoute("/api/stream/{run}/{video}", stream)])  # fmt: skip


def test_a_run_being_written_is_followed_through_the_stream_without_a_gap():
    import asyncio as aio
    import socket
    import threading
    import time

    import uvicorn

    from chole_demo.feeds import mock
    from chole_demo.follow import Follow

    lines = mock.generate("live")
    store, written = lines[:6], lines[6:]
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(_stream_upstream(store, written), host="127.0.0.1",
                                           port=port, log_level="warning"))  # fmt: skip
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.02)
    source = ApiSource(f"http://127.0.0.1:{port}")

    async def main():
        hub = Follow("r", mock.VIDEO_ID, source.follow, pinned_version(), None)
        hub.start()
        out = [m async for m in hub.watch(0, ping_s=5)]
        await hub.stop()
        return out

    try:
        msgs = aio.run(aio.wait_for(main(), 30))
    finally:
        server.should_exit = True
    got = [(m["line"]["kind"], m["line"]["tick"]) for m in msgs if m["type"] == "line"]
    want = [(x["kind"], x["tick"]) for x in lines if x["kind"] in ("decision", "dropped")]
    assert got == want and msgs[-1]["type"] == "end"


def test_a_held_out_video_is_the_owners_until_its_licence_allows(client):
    """To a visitor it does not exist; signed in, the owner sees it
    labelled on every frame, with the API's attribution."""
    assert all(v["video_id"] != OOD_VID for v in client.get("/api/videos").json())
    for path in (f"/api/rollout/{OOD_RUN}/heichole%3A3", "/api/frames/heichole%3A3/1.jpg",
                 "/api/video/heichole%3A3"):  # fmt: skip
        assert client.get(path).status_code == 404, path
    with client.websocket_connect(f"/api/follow/{OOD_RUN}/heichole%3A3") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4404
    assert client.post("/api/owner", json={"password": PASSWORD}).status_code == 200
    mine = [v for v in client.get("/api/videos").json() if v["video_id"] == OOD_VID]
    assert len(mine) == 1 and mine[0]["held_out"] is True
    r = client.get(f"/api/rollout/{OOD_RUN}/heichole%3A3").json()
    assert r["meta"]["held_out"] == OOD_LINE and r["meta"]["feed"] == "real"
    assert r["meta"]["attribution"].startswith("HeiChole · its makers")
    res = client.get("/api/frames/heichole%3A3/1.jpg")
    assert res.status_code == 200 and res.headers["cache-control"].startswith("private")


def test_a_video_the_api_marks_not_public_is_the_owners(client):
    """api.md v1.4 `attribution.public: false`, whatever its dataset."""
    assert all(v["video_id"] != PRIVATE_VID for v in client.get("/api/videos").json())
    for path in ("/api/frames/cholect50%3A99/1.jpg", "/api/video/cholect50%3A99"):
        assert client.get(path).status_code == 404, path
    assert client.post("/api/owner", json={"password": PASSWORD}).status_code == 200
    mine = [v for v in client.get("/api/videos").json() if v["video_id"] == PRIVATE_VID]
    assert len(mine) == 1 and mine[0]["held_out"] is False
    res = client.get("/api/frames/cholect50%3A99/1.jpg")
    assert res.status_code == 200 and res.headers["cache-control"].startswith("private")


def test_the_demo_is_its_three_videos_and_nothing_else():
    """The configured list, the eventful case first."""
    c = demo_config()
    assert c["videos"] == ["cholect50:VID103", "cholec80:46", "heichole:4"]
    assert c["exclude_runs"] == ["stage1-best-offline-D4-20261106T002825"]
    assert default_video() == "cholect50:VID103"
    assert c["interim"] == {"run": "stage1-best-merged-cholec80_12-t493-613-D4", "video": VID}


def test_until_its_videos_are_run_the_interim_stretch_holds_the_page(tmp_path):
    """No run of the demo's val video yet: only the interim stretch is listed and served;
    every other run and video is gone, and the held-out one is still the owner's."""
    client = _app(
        tmp_path,
        {"videos": [DEMO_VID, OOD_VID, PRIVATE_VID], "interim": {"run": STRETCH, "video": VID}},
    )
    vids = client.get("/api/videos").json()
    assert [(v["run"], v["video_id"]) for v in vids] == [(STRETCH, VID)]
    assert client.get(f"/api/rollout/{STRETCH}/cholec80%3A12").status_code == 200
    assert client.get(f"/api/rollout/{RUN}/cholec80%3A12").status_code == 404
    assert client.get("/api/frames/cholec80%3A12/500.jpg").status_code == 200
    assert client.get("/api/frames/endoscapes%3A124/5.jpg").status_code == 404
    assert client.post("/api/owner", json={"password": PASSWORD}).status_code == 200
    mine = [(v["run"], v["video_id"]) for v in client.get("/api/videos").json()]
    # the stretch opens the page
    assert mine == [(STRETCH, VID), (OOD_RUN, OOD_VID), (OOD_RUN, PRIVATE_VID)]


def test_once_its_videos_are_run_the_interim_goes(tmp_path):
    demo = {"videos": [DEMO_VID, OOD_VID], "interim": {"run": STRETCH, "video": VID}}
    client = _app(tmp_path, demo, with_demo_run)
    vids = client.get("/api/videos").json()
    assert {(v["run"], v["video_id"]) for v in vids} == {(DEMO_RUN, DEMO_VID)}  # its whole run
    assert client.get(f"/api/rollout/{STRETCH}/cholec80%3A12").status_code == 404
    assert client.get("/api/frames/cholec80%3A12/500.jpg").status_code == 404


def test_an_excluded_run_leaves_the_demo_whatever_it_holds(tmp_path):
    """A run named in `exclude_runs` leaves, whatever it holds."""
    demo = {
        "videos": [DEMO_VID, OOD_VID],
        "interim": {"run": STRETCH, "video": VID},
        "exclude_runs": [DEMO_RUN],
    }
    vids = _app(tmp_path, demo, with_demo_run).get("/api/videos").json()
    # its one whole run gone, the video has none: the interim holds the page
    assert [(v["run"], v["video_id"]) for v in vids] == [(STRETCH, VID)]


def test_a_demo_video_is_shown_from_its_whole_offline_runs_only(tmp_path):
    """The demo's runs are its videos whole, offline. A parity or
    reconciliation run's sampled points, a latency test's live replay (finished, or
    stopped before its manifest), a run of the first ticks and evaluation's whole run over
    its own five videos hold a demo video, are not its run, and do not retire the interim."""
    demo = {"videos": [DEMO_VID, OOD_VID], "interim": {"run": STRETCH, "video": VID}}
    vids = _app(tmp_path, demo).get("/api/videos").json()
    assert [(v["run"], v["video_id"]) for v in vids] == [(STRETCH, VID)]
    vids = _app(tmp_path, demo, with_demo_run).get("/api/videos").json()
    assert [(v["run"], v["video_id"]) for v in vids] == [(DEMO_RUN, DEMO_VID)]


def test_a_demo_video_is_listed_from_one_finished_run(tmp_path):
    """Of a video's
    finished whole runs, the one that covers most of it is listed and served; the other
    is neither, to anyone."""
    demo = {"videos": [DEMO_VID, OOD_VID], "interim": {"run": STRETCH, "video": VID}}
    client = _app(tmp_path, demo, with_two_demo_runs)
    vids = client.get("/api/videos").json()
    assert [(v["run"], v["video_id"]) for v in vids] == [(DEMO_RUN, DEMO_VID)]
    assert client.post("/api/owner", json={"password": PASSWORD}).status_code == 200
    mine = [(v["run"], v["video_id"]) for v in client.get("/api/videos").json()]
    assert (DEMO_RUN_D8, DEMO_VID) not in mine and (DEMO_RUN, DEMO_VID) in mine
    assert client.get(f"/api/rollout/{DEMO_RUN_D8}/cholect50%3AVID103").status_code == 404


def test_the_final_models_run_replaces_the_earlier_checkpoints(tmp_path):
    """A demo video is shown from the newest checkpoint's finished whole
    run, and of that checkpoint's runs the fullest; the earlier checkpoints' runs stay
    stored and unlisted. A checkpoint is as new as its first run, so a later, fuller rerun
    of the first checkpoint does not bring it back."""
    demo = {"videos": [DEMO_VID, OOD_VID], "interim": {"run": STRETCH, "video": VID}}
    client = _app(tmp_path, demo, with_final_model)
    vids = client.get("/api/videos").json()
    assert [(v["run"], v["video_id"]) for v in vids] == [(FINAL_RUN, DEMO_VID)]
    assert {"checkpoint", "created"}.isdisjoint(vids[0])  # nothing more is served
    for run in (DEMO_RUN, DEMO_RUN_D8, RERUN):
        assert client.get(f"/api/rollout/{run}/cholect50%3AVID103").status_code == 404


def with_final_model_newer_minor(request: httpx.Request) -> httpx.Response:
    """The final model's run written in a minor the client does not pin yet."""
    r = with_final_model(request)
    if request.url.raw_path.decode() == f"/api/runs/{FINAL_RUN}":
        info = r.json()
        info["manifest"]["api_version"] = "1.99"
        return httpx.Response(200, json=info)
    return r


def test_a_run_in_a_newer_minor_is_not_listed_until_the_pin_moves(tmp_path):
    """The screen refuses a line in a newer minor than its pin, so a newer
    checkpoint's run written in one would not open: the listing keeps the older run."""
    demo = {"videos": [DEMO_VID, OOD_VID], "interim": {"run": STRETCH, "video": VID}}
    client = _app(tmp_path, demo, with_final_model_newer_minor)
    vids = client.get("/api/videos").json()
    assert [(v["run"], v["video_id"]) for v in vids] == [(RERUN, DEMO_VID)]
    assert "api_version" not in vids[0]  # nothing more is served
    assert client.get(f"/api/rollout/{FINAL_RUN}/cholect50%3AVID103").status_code == 404


ABLATION_RUN = "stage3-final-merged-cholect50_VID103-D4-a10"


def with_final_model_and_its_ablation(request: httpx.Request) -> httpx.Response:
    """An ablation row's run of the final checkpoint (api.md v1.7: A10, the hint dropped),
    newer and fuller than the demo's run of it."""
    p = request.url.raw_path.decode()
    if p == "/api/runs":
        r = with_final_model(request).json()
        return httpx.Response(200, json={**r, "runs": [*r["runs"], ABLATION_RUN]})
    if p == f"/api/runs/{ABLATION_RUN}":
        info = with_final_model(
            httpx.Request("GET", f"http://upstream.test/api/runs/{FINAL_RUN}")
        ).json()
        info["manifest"].update(
            created=350.0, files=[{"path": f"{DEMO_VID}.jsonl", "size": 3000}],
            ablation={"row": "A10", "omitted": "hint", "hint": {"threshold": 74.6}},
        )  # fmt: skip
        return httpx.Response(200, json=info)
    return with_final_model(request)


def test_an_ablation_rows_run_is_never_on_the_demo(tmp_path):
    """api.md v1.7: an A10 run is its checkpoint with the hint dropped, not the checkpoint
    as served, and the demo is never shown one, however new or full."""
    demo = {"videos": [DEMO_VID, OOD_VID], "interim": {"run": STRETCH, "video": VID}}
    client = _app(tmp_path, demo, with_final_model_and_its_ablation)
    vids = client.get("/api/videos").json()
    assert [(v["run"], v["video_id"]) for v in vids] == [(FINAL_RUN, DEMO_VID)]
    assert "ablation" not in vids[0]
    assert client.get(f"/api/rollout/{ABLATION_RUN}/cholect50%3AVID103").status_code == 404


STATELESS_RUN = "stage3-final-gate-stateless-cholect50_VID103-D4"
TRAINED_RUN = "stage3-final-gate-trained-cholect50_VID103-D4"


def with_final_model_in_two_forms(forms):
    """The final checkpoint's run of the demo's video again in a named decision form
    (api.md v1.12), each smaller than its first run, which names none (a log before
    v1.12): `forms` maps the run to `(name, served)`."""

    def fake(request: httpx.Request) -> httpx.Response:
        p = request.url.raw_path.decode()
        if p == "/api/runs":
            r = with_final_model(request).json()
            return httpx.Response(200, json={**r, "runs": [*r["runs"], *forms]})
        for run, (name, served) in forms.items():
            if p == f"/api/runs/{run}":
                info = with_final_model(
                    httpx.Request("GET", f"http://upstream.test/api/runs/{FINAL_RUN}")
                ).json()
                info["manifest"].update(
                    created=500.0, api_version="1.12",
                    files=[{"path": f"{DEMO_VID}.jsonl", "size": 900}],
                    decision_form={"name": name, "reading": "...", "rows": "gate-blank/",
                                   "served": served, "by": "the evaluation's ruling"},
                )  # fmt: skip
                return httpx.Response(200, json=info)
        return with_final_model(request)

    return fake


def test_a_demo_video_is_shown_from_its_checkpoints_served_form(tmp_path):
    """api.md v1.12: `stage3-final` is served stateless, so of its runs
    a demo video is shown from one in the served form, however small; a run that says it
    is not in the served form comes after one that does not say (a log before v1.12)."""
    demo = {"videos": [DEMO_VID, OOD_VID], "interim": {"run": STRETCH, "video": VID}}
    both = {STATELESS_RUN: ("stateless", True), TRAINED_RUN: ("trained", False)}
    client = _app(tmp_path, demo, with_final_model_in_two_forms(both))
    vids = client.get("/api/videos").json()
    assert [(v["run"], v["video_id"]) for v in vids] == [(STATELESS_RUN, DEMO_VID)]
    assert "served" not in vids[0] and "decision_form" not in json.dumps(vids)
    assert client.get(f"/api/rollout/{FINAL_RUN}/cholect50%3AVID103").status_code == 404
    unserved = {TRAINED_RUN: ("trained", False)}
    client = _app(tmp_path, demo, with_final_model_in_two_forms(unserved))
    vids = client.get("/api/videos").json()
    assert [(v["run"], v["video_id"]) for v in vids] == [(FINAL_RUN, DEMO_VID)]


def test_the_decision_log_is_compressed_and_the_video_never(tmp_path):
    """The share's transfer is the ngrok account's allowance (it ran out once):
    the JSON goes gzip-compressed to a browser that accepts it; the video's byte ranges,
    the whole video and the frames go as they are."""
    client = _app(tmp_path, {"videos": [VID, "endoscapes:124"], "interim": None}, without_fuller)
    r = client.get(f"/api/rollout/{RUN}/cholec80%3A12", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip"
    assert r.json()["meta"]["video_id"] == VID  # decoded as the browser would
    for h in ({"Range": "bytes=256-511"}, {}):
        v = client.get("/api/video/cholec80%3A12", headers={**h, "Accept-Encoding": "gzip"})
        assert "content-encoding" not in v.headers and v.content[:4] == bytes(range(256))[:4]
    f = client.get(
        "/api/frames/cholec80%3A12/5.jpg?variant=video", headers={"Accept-Encoding": "gzip"}
    )
    assert "content-encoding" not in f.headers


def with_served_val(request: httpx.Request, reading=None) -> httpx.Response:
    """A run written before api.md v1.13 with the served CVS (v1.11): its log's header
    names the choice and each decision carries `cvs_served`; `GET /api/runs/{run}` carries
    val's reading of it, `cvs_served_val`, read now (v1.13)."""
    p = request.url.raw_path.decode()
    if p == f"/api/runs/{RUN}":
        info = upstream(request).json()
        info["cvs_served_val"] = reading or {**mock.VAL_READING, "report": SECRET}
        return httpx.Response(200, json=info)
    if p == f"/api/load/{RUN}/cholec80%3A12":
        log = [dict(x, api_version="1.12") for x in LOG]
        log[0]["cvs_served"] = {"choice": {"report": SECRET, "rows": "gate-blank"}, "criteria": {}}
        for i, x in enumerate(log):
            if x["kind"] == "decision":
                log[i] = dict(x, cvs_served={
                    "two_structures": {"value": 1, "source": "p1"},
                    "triangle_cleared": {"value": 0, "source": "specialist"},
                    "cystic_plate": {"value": None, "source": "reply"},
                })  # fmt: skip
        return httpx.Response(200, text="".join(json.dumps(x) + "\n" for x in log))
    return upstream(request)


def test_vals_reading_of_the_served_cvs_comes_from_the_runs_listing(tmp_path):
    """api.md v1.13: a log written before v1.13 takes val's
    reading from `GET /api/runs/{run}`, cut to the figures the engineer's page draws;
    nothing else of it, its report's path among it, reaches the browser."""
    client = _app(tmp_path, {"videos": [], "interim": None}, with_served_val)
    r = client.get(f"/api/rollout/{RUN}/cholec80%3A12")
    assert r.status_code == 200
    val = r.json()["meta"]["cvs_val"]
    assert val["two_structures"]["out_of_fold"] and val["cystic_plate"]["npv"]["n"] == 980
    assert SECRET not in r.text and "results.json" not in r.text
    assert "cvs_val" not in json.dumps(client.get("/api/videos").json())


def test_a_val_reading_the_api_cannot_give_draws_none(tmp_path):
    unavailable = {"unavailable": "the report's section read another choice"}
    fake = lambda request: with_served_val(request, unavailable)
    client = _app(tmp_path, {"videos": [], "interim": None}, fake)
    r = client.get(f"/api/rollout/{RUN}/cholec80%3A12")
    assert r.status_code == 200 and r.json()["meta"]["cvs_served"]
    assert r.json()["meta"]["cvs_val"] is None

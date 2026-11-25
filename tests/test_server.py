"""The demo server: loopback only, the logs through the adapter, the frames, the
ask box and the access log."""

import json

import pytest
from starlette.testclient import TestClient

from chole_demo.client.adapter import DECISION_KEYS
from chole_demo.feeds import mock
from chole_demo.owner import Owner
from chole_demo.server import check_host, create_app

PASSWORD = "a test password, not the owner's"
OFFLINE = mock.run_id("offline")
LIVE = mock.run_id("live")


class FakeMock(mock.MockSource):
    """The mock without ffmpeg or files: logs in memory, one tiny frame."""

    def __init__(self, tmp_path, pace=1.0):
        super().__init__(tmp_path, pace=pace)
        self._lines = {mock.run_id(m): mock.generate(m) for m in mock.MODES}
        self.jpg = tmp_path / "f.jpg"
        self.jpg.write_bytes(b"\xff\xd8 mock \xff\xd9")
        self.mp4 = tmp_path / "v.mp4"
        self.mp4.write_bytes(bytes(range(256)) * 4)

    def frame_path(self, video_id, t, variant):
        if video_id != mock.VIDEO_ID or not 0 <= t < mock.N_FRAMES:
            raise KeyError("no frame")
        return self.jpg

    def video_path(self, video_id):
        if video_id != mock.VIDEO_ID:
            raise KeyError("no video")
        return self.mp4


@pytest.fixture
def client(tmp_path):
    app = create_app(
        FakeMock(tmp_path),
        web_dist=tmp_path / "nodist",
        access_log=tmp_path / "access.log",
        pinned="1.0",
        owner=_owner(tmp_path),
    )
    return TestClient(app)


def _owner(tmp_path):
    owner = Owner(tmp_path / "owner.local.yaml")
    owner.set_password(PASSWORD)
    return owner


def _sign_in(client, password=PASSWORD):
    return client.post("/api/owner", json={"password": password})


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_loopback_allowed(host):
    check_host(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "100.64.0.1", "192.168.1.5", "example.com"])
def test_other_hosts_refused(host):
    with pytest.raises(ValueError):
        check_host(host)


def test_videos(client):
    vids = client.get("/api/videos").json()
    assert {(v["run"], v["writing"]) for v in vids[-2:]} == {(r, True) for r in mock.WRITING_MODES}
    done = {(v["run"], v["mode"]) for v in vids if not v["writing"]}
    assert done == {(OFFLINE, "offline"), (LIVE, "live")}
    assert all(v["video_id"] == mock.VIDEO_ID for v in vids)


# step 2: a run still being written is followed, never served as a replay
def test_a_run_being_written_is_not_served_as_a_replay(client):
    r = client.get(f"/api/rollout/{mock.WRITING}/mock%3A01")
    assert r.status_code == 409 and r.json()["error"] == "writing"


def _follow(tmp_path, pace=0.002, **kw):
    app = create_app(
        FakeMock(tmp_path, pace=pace),
        web_dist=tmp_path / "nodist",
        access_log=tmp_path / "access.log",
        pinned="1.0",
        owner=_owner(tmp_path),
        sessions_dir=tmp_path / "sessions",
        **kw,
    )
    return TestClient(app)


def test_following_a_run_gives_every_line_once_in_order_then_its_end(tmp_path):
    with _follow(tmp_path) as c, c.websocket_connect(f"/api/follow/{mock.WRITING}/mock%3A01") as ws:
        msgs = []
        while not msgs or msgs[-1]["type"] != "end":
            msgs.append(ws.receive_json())
    meta = next(m["meta"] for m in msgs if m["type"] == "meta")
    lines = [m["line"] for m in msgs if m["type"] == "line"]
    assert meta["mode"] == "live" and meta["banner"] == "MOCK FEED, made-up decisions"
    assert [m["i"] for m in msgs if m["type"] == "line"] == list(range(len(lines)))
    body = [x for x in mock.generate("live") if x["kind"] in ("decision", "dropped")]
    assert sorted((x["kind"], x["tick"]) for x in lines) == sorted(
        (x["kind"], x["tick"]) for x in body
    )
    assert all(set(x) <= DECISION_KEYS for x in lines)  # cut to the screen's fields
    assert msgs[-1]["end"]["decisions"] == sum(x["kind"] == "decision" for x in body)
    log = (tmp_path / "sessions").rglob("*.jsonl")
    logged = [json.loads(x)["line"] for f in log for x in f.read_text().splitlines()]
    assert logged[0]["kind"] == "header" and logged[-1]["kind"] == "end"
    assert len(logged) == len(body) + 2  # every line once, the header and the end


def test_a_viewer_that_reconnects_picks_up_where_it_left(tmp_path):
    with _follow(tmp_path) as c:
        with c.websocket_connect(f"/api/follow/{mock.WRITING}/mock%3A01") as ws:
            first = [ws.receive_json() for _ in range(6)]
        held = sum(m["type"] == "line" for m in first)
        with c.websocket_connect(f"/api/follow/{mock.WRITING}/mock%3A01?after={held}") as ws:
            nxt = ws.receive_json()
            while nxt["type"] != "line":
                nxt = ws.receive_json()
    assert nxt["i"] == held


def test_follow_refuses_a_finished_run_and_too_many_sockets(tmp_path):
    from starlette.websockets import WebSocketDisconnect

    def refused(c, url):
        with c.websocket_connect(url) as ws, pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        return e.value.code

    with _follow(tmp_path, pace=5.0) as c:
        assert refused(c, f"/api/follow/{OFFLINE}/mock%3A01") == 4404
        url = f"/api/follow/{mock.WRITING}/mock%3A01"
        opened = [c.websocket_connect(url) for _ in range(4)]
        socks = [o.__enter__() for o in opened]
        for s in socks:
            assert s.receive_json()["type"] in ("meta", "status")
        assert refused(c, url) == 4429
        for o in opened:
            o.__exit__(None, None, None)


def test_a_refusal_reaches_a_real_browser_socket_as_its_code(tmp_path):
    # a socket closed before its handshake arrives as HTTP 403 and code 1006, unreadable:
    # the screen must see 4404 to switch to the stored replay (found through ngrok)
    import asyncio
    import socket
    import threading
    import time

    import uvicorn
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed

    app = create_app(FakeMock(tmp_path, pace=5.0), web_dist=tmp_path / "nodist",
                     access_log=tmp_path / "a.log", pinned="1.0", owner=_owner(tmp_path),
                     sessions_dir=tmp_path / "s")  # fmt: skip
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.02)

    async def code():
        async with connect(f"ws://127.0.0.1:{port}/api/follow/{OFFLINE}/mock%3A01") as ws:
            try:
                await ws.recv()
            except ConnectionClosed as e:
                return e.rcvd.code

    try:
        assert asyncio.run(code()) == 4404
    finally:
        server.should_exit = True


def test_rollout_by_encoded_id(client):
    r = client.get(f"/api/rollout/{OFFLINE}/mock%3A01").json()
    assert r["meta"]["banner"] == "MOCK FEED, made-up decisions"
    assert r["meta"]["api_version"] == "1.0" and r["meta"]["mode"] == "offline"
    assert len(r["decisions"]) == 240 and r["end"]["decisions"] == 240
    live = client.get(f"/api/rollout/{LIVE}/mock%3A01").json()
    assert len(live["dropped"]) == live["end"]["dropped"] > 0
    assert client.get(f"/api/rollout/{OFFLINE}/nope").status_code == 404


def test_frames(client):
    res = client.get("/api/frames/mock%3A01/123.jpg?variant=current")
    assert res.status_code == 200 and res.headers["content-type"] == "image/jpeg"
    assert client.get("/api/frames/mock%3A01/9999.jpg").status_code == 404
    assert client.get("/api/frames/other%3A01/1.jpg").status_code == 404


def test_video_by_byte_ranges(client):
    whole = client.get("/api/video/mock%3A01")
    assert whole.status_code == 200 and whole.headers["content-type"] == "video/mp4"
    assert len(whole.content) == 1024
    part = client.get("/api/video/mock%3A01", headers={"Range": "bytes=256-511"})
    assert part.status_code == 206 and part.content == bytes(range(256))
    assert part.headers["content-range"] == "bytes 256-511/1024"
    assert client.get("/api/video/other%3A01").status_code == 404


def test_ask_is_the_owners(client):
    body = {"run": OFFLINE, "video_id": mock.VIDEO_ID, "t": 125, "question": "describe the scene"}
    refused = client.post("/api/ask", json=body)
    assert refused.status_code == 403 and refused.json()["error"] == "owner_only"
    assert client.get("/api/me").json() == {"owner": False}
    assert _sign_in(client, "wrong").status_code == 403
    assert _sign_in(client, "").status_code == 403
    assert client.post("/api/owner", content=b"not json").status_code == 403
    assert client.get("/api/me").json() == {"owner": False}
    signed_in = _sign_in(client)
    assert signed_in.status_code == 200 and signed_in.json() == {"owner": True}
    cookie = signed_in.headers["set-cookie"].lower()
    assert "chole_owner" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/me").json() == {"owner": True}
    assert client.post("/api/ask", json=body).status_code == 200


def test_signing_out_drops_this_browsers_cookie(client):
    """The Owner tab's Sign out."""
    _sign_in(client)
    assert client.get("/api/me").json() == {"owner": True}
    out = client.delete("/api/owner")
    assert out.status_code == 200 and out.json() == {"owner": False}
    cookie = out.headers["set-cookie"].lower()
    assert "chole_owner" in cookie and "max-age=0" in cookie and "httponly" in cookie
    assert client.get("/api/me").json() == {"owner": False}
    body = {"run": OFFLINE, "video_id": mock.VIDEO_ID, "t": 125, "question": "describe the scene"}
    assert client.post("/api/ask", json=body).json()["error"] == "owner_only"
    assert _sign_in(client).status_code == 200  # the password still signs in


def test_there_is_no_sign_in_link(client):
    assert client.get("/owner?token=anything").status_code == 404
    assert client.get("/api/owner").status_code == 405  # a password is posted, never in a URL


def test_rate_limited(tmp_path):
    app = create_app(
        FakeMock(tmp_path),
        web_dist=tmp_path / "nodist",
        access_log=tmp_path / "a.log",
        pinned="1.0",
        owner=_owner(tmp_path),
        limits={"media": 2, "api": 3, "ask": 1, "signin": 2},
    )
    c = TestClient(app)
    codes = [c.get("/api/videos").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    assert (
        c.get("/api/videos", headers={"x-forwarded-for": "203.0.113.9"}).status_code == 200
    )  # another visitor
    guesses = [_sign_in(c, "wrong").status_code for _ in range(3)]
    assert guesses == [403, 403, 429]
    other = {"x-forwarded-for": "198.51.100.7"}  # its sign-in tries used up, its sign-out free
    tries = [c.post("/api/owner", json={"password": "x"}, headers=other) for _ in range(2)]
    assert [r.status_code for r in tries] == [403, 403]
    assert c.delete("/api/owner", headers=other).status_code == 200


def test_a_made_up_forwarded_for_is_still_one_visitor(tmp_path):
    """ngrok puts the address it saw after any X-Forwarded-For the visitor sent (a header
    line of its own, or the list's end), so the limits key on the last value: a new made-up
    first value on every request is still one visitor (found 2026-11-24 through the share)."""
    app = create_app(
        FakeMock(tmp_path),
        web_dist=tmp_path / "nodist",
        access_log=tmp_path / "a.log",
        pinned="1.0",
        owner=_owner(tmp_path),
        limits={"media": 2, "api": 3, "ask": 1, "signin": 2},
    )
    c = TestClient(app)
    seen = "198.51.100.4"  # what ngrok saw
    lines = [[("x-forwarded-for", f"203.0.113.{i}"), ("x-forwarded-for", seen)] for i in range(4)]
    assert [c.get("/api/videos", headers=h).status_code for h in lines] == [200, 200, 200, 429]
    joined = {"x-forwarded-for": f"203.0.113.77, {seen}"}
    assert c.get("/api/videos", headers=joined).status_code == 429
    log = [json.loads(x) for x in (tmp_path / "a.log").read_text().splitlines()]
    assert log[0]["visitor"] == seen and log[0]["forwarded_for"] == f"203.0.113.0, {seen}"


def test_ask(client):
    _sign_in(client)
    body = {"run": OFFLINE, "video_id": mock.VIDEO_ID, "t": 125, "question": "describe the scene"}
    reply = client.post("/api/ask", json=body).json()
    assert set(reply) == {"answer"} and "MOCK reply" in reply["answer"]  # nothing else leaves
    blank = {"run": OFFLINE, "video_id": mock.VIDEO_ID, "question": " "}
    assert client.post("/api/ask", json=blank).status_code == 400


def test_no_build_says_so(client):
    assert client.get("/").status_code == 503


def test_the_page_is_checked_again_on_every_load(tmp_path):
    """A deploy shows at the next load: the page is sent with `no-cache` (checked again,
    a 304 while unchanged); its hashed scripts keep their own caching."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!DOCTYPE html><title>t</title>")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)")
    app = create_app(
        FakeMock(tmp_path),
        web_dist=dist,
        access_log=tmp_path / "a.log",
        pinned="1.0",
        owner=_owner(tmp_path),
    )
    c = TestClient(app)
    page = c.get("/")
    assert page.status_code == 200 and page.headers["cache-control"] == "no-cache"
    again = c.get("/", headers={"If-None-Match": page.headers["etag"]})
    assert again.status_code == 304
    assert "no-cache" not in c.get("/assets/index-abc123.js").headers.get("cache-control", "")


def test_access_logged(client, tmp_path):
    client.get("/api/videos", headers={"Tailscale-User-Login": "someone@example.com"})
    lines = [json.loads(x) for x in (tmp_path / "access.log").read_text().splitlines()]
    assert lines[-1]["path"] == "/api/videos"
    assert lines[-1]["user"] == "someone@example.com"
    assert (tmp_path / "access.log").stat().st_mode & 0o777 == 0o600  # it holds addresses


def test_an_older_access_log_is_made_private(tmp_path):
    log = tmp_path / "old.log"
    log.write_text("")
    log.chmod(0o664)
    app = create_app(
        FakeMock(tmp_path), web_dist=tmp_path / "nodist", access_log=log, pinned="1.0",
        owner=_owner(tmp_path),
    )  # fmt: skip
    TestClient(app).get("/api/videos")  # the middleware is built at the first request
    assert log.stat().st_mode & 0o777 == 0o600


def test_says_nothing_about_its_host(client):
    res = client.get(f"/api/rollout/{OFFLINE}/mock%3A01")
    assert res.headers["x-robots-tag"] == "noindex, nofollow"
    assert res.headers["referrer-policy"] == "no-referrer"
    assert res.headers["x-frame-options"] == "DENY"  # no other site frames the Owner tab
    assert res.headers["content-security-policy"] == "frame-ancestors 'none'"
    body = res.text
    assert "header" not in res.json() and "/home/" not in body and "note" not in body
    missing = client.get("/api/frames/mock%3A01/9999.jpg").json()
    assert missing == {"error": "not_found", "detail": "no such run, video or frame"}

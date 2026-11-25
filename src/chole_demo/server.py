"""The demo's web server: the built page, the decision logs, the video, the frames, the ask box.

It binds to loopback only (never 0.0.0.0). Since the owner's
choice of 2026-11-05 it is public through ngrok (`python -m chole_demo share`),
read-only; asking the model is the owner's, after his password (`owner.py`). It says
nothing about its host: the API carries only what the screen draws (no raw
header, no paths), errors are generic, and no server banner is sent. Every
request is logged locally as a JSON line (who, what, when).
"""

from __future__ import annotations

import collections
import contextlib
import hmac
import ipaddress
import json
import os
import time
from pathlib import Path
from urllib.parse import quote

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from chole_demo.client.adapter import (
    ScreenSource,
    ask_answer,
    default_video,
    demo_config,
    held_out,
    pinned_version,
    public_held_out,
    speaks,
    to_screen,
)
from chole_demo.follow import Hubs
from chole_demo.owner import Owner

REPO = Path(__file__).resolve().parents[2]
WEB_DIST = REPO / "web" / "dist"
RUNS = REPO / "runs"
DEFAULT_PORT = 8781
OWNER_FILE = REPO / "configs" / "owner.local.yaml"  # gitignored: the owner's keys (owner.py)
OWNER_COOKIE = "chole_owner"
# per visitor and minute: the media a player needs, the rest of
# the API, the model's one public door, ask (the owner's alone), and the owner's sign-in
LIMITS = {"media": 900, "api": 240, "ask": 12, "signin": 5}
# wrong passwords from everyone together: past this many in ten minutes, every sign-in
# waits for the window to pass (a guesser with many addresses gains nothing)
SIGNIN_FAILURES = 30
# runs followed as they are written (step 2): sockets open at once, per visitor and in all
FOLLOW_LIMITS = {"visitor": 4, "total": 64}


def _address(headers, client) -> str:
    """Who is asking, as ngrok saw them: the last X-Forwarded-For value. ngrok puts the
    address it saw after any the visitor sent (on a header line of its own, or at the end of
    the list), so a first value is the visitor's to choose: keyed on it, a made-up value on
    every request would slip every per-visitor limit (found 2026-11-24)."""
    values = [v.strip() for line in headers.getlist("x-forwarded-for") for v in line.split(",")]
    values = [v for v in values if v]
    return values[-1] if values else (client.host if client else "?")


def _visitor(request: Request) -> str:
    return _address(request.headers, request.client)


def _forwarded(headers) -> str | None:
    """Every X-Forwarded-For value, in order, for the log: what was claimed and what ngrok saw."""
    return ", ".join(headers.getlist("x-forwarded-for")) or None


def _append(path: Path, entry: dict) -> None:
    """One line of the access log, which only this account may read (it holds addresses)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(entry) + "\n")


class RateLimit(BaseHTTPMiddleware):
    """A sliding minute per visitor and kind: over the limit, 429 and nothing served."""

    def __init__(self, app, limits: dict[str, int]) -> None:
        super().__init__(app)
        self.limits = limits
        self.seen: dict[tuple[str, str], collections.deque] = collections.defaultdict(
            collections.deque
        )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)
        if path.startswith(("/api/frames/", "/api/video/")):
            kind = "media"
        elif path == "/api/ask":
            kind = "ask"
        elif path == "/api/owner" and request.method == "POST":
            kind = "signin"  # signing out (DELETE) is not a guess at the password
        else:
            kind = "api"
        q = self.seen[(_visitor(request), kind)]
        now = time.monotonic()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.limits[kind]:
            return JSONResponse(
                {"error": "rate_limited", "detail": "too many requests; wait a minute"},
                status_code=429,
            )
        q.append(now)
        return await call_next(request)


def check_host(host: str) -> None:
    """Loopback only: the world reaches the server only through the ngrok share."""
    if host == "localhost":
        return
    try:
        ok = ipaddress.ip_address(host).is_loopback
    except ValueError:
        ok = False
    if not ok:
        raise ValueError(f"refusing to bind {host!r}: loopback only")


class AccessLog(BaseHTTPMiddleware):
    def __init__(self, app, path: Path) -> None:
        super().__init__(app)
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.chmod(0o600)  # a log written before 2026-11-24 was readable by every account

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # what a crawler or a linked page could learn: nothing, and not indexed
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # no other site may show the page in a frame: its Owner tab takes the password
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        # the page itself is checked again on every load (its ETag answers 304 while it is
        # unchanged), so a deploy shows at the next load, not after the browser's own guess
        # at freshness (the owner saw the old columns after 2026-11-23's); its scripts and
        # styles carry their hash in their names and keep their caching
        ctype = response.headers.get("content-type", "")
        if ctype.startswith("text/html") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-cache"
        entry = {
            "time": round(time.time(), 3),
            "client": request.client.host if request.client else None,
            "forwarded_for": _forwarded(request.headers),
            "visitor": _visitor(request),
            "user": request.headers.get("tailscale-user-login"),
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
        }
        _append(self.path, entry)
        return response


def create_app(
    source: ScreenSource,
    web_dist: Path = WEB_DIST,
    access_log: Path | None = None,
    pinned: str | None = None,
    owner: Owner | None = None,
    limits: dict[str, int] | None = None,
    sessions_dir: Path | None = None,
    demo: dict | None = None,
):
    pinned = pinned or pinned_version()
    access_log = access_log or RUNS / "access.log"
    owner = owner or Owner(OWNER_FILE)
    owner.cookie()  # the file made (a token) before the first visitor

    def is_owner(request: Request | WebSocket) -> bool:
        signed = owner.cookie()
        return signed is not None and hmac.compare_digest(
            request.cookies.get(OWNER_COOKIE, ""), signed
        )

    # a video from outside the training distribution whose licence is not known to allow
    # public display is the owner's to see: to anyone else it does
    # not exist, in the listing or behind it
    # (and so is any video the API marks `attribution.public: false`, api.md v1.4)
    public = public_held_out()

    def _hidden(video: str, request: Request | WebSocket, private) -> bool:
        if is_owner(request):
            return False
        return (held_out(video) is not None and video not in public) or video in private

    async def hidden(video: str, request: Request | WebSocket) -> bool:
        try:
            private = (await listed())["private"]
        except httpx.HTTPError:  # nothing is served without the upstream anyway
            private = set()
        return _hidden(video, request, private)

    # the runs and videos the source lists: the only ones served or proxied
    # (`pairs` finished, `writing` still being written: followed, never served as a replay)
    listing: dict = {"at": 0.0, "pairs": set(), "writing": set(), "videos": set(), "private": set()}

    upstream = getattr(source, "upstream", None)  # chole-eval's server: frames and video proxied
    # the demo shows its videos and nothing else, in their order; its
    # interim run stays until each of them that is not held out has a finished run
    demo = demo if demo is not None else demo_config()
    order = demo.get("videos") or []
    interim = demo.get("interim")
    excluded = set(demo.get("exclude_runs") or [])

    # a demo video is shown from the demo's own runs only (the three
    # videos whole at D = 4 are the demo's runs): whole-video and offline, holding nothing
    # but the demo's videos. A stretch, the sampled points of a parity or reconciliation
    # run, a live replay of a latency test, and evaluation's runs over its own sets of
    # videos (the parity five) hold a demo video too, and are not its run
    def demo_run(r: dict, v: str) -> bool:
        return (
            v in order
            and r.get("whole", True)
            and set(r["video_ids"]) <= set(order)
            # a run in a newer minor than the pin would not open: the older run stays listed
            and (r.get("api_version") is None or speaks(r["api_version"], pinned))
            # an ablation row's run (api.md v1.7: A10, the hint dropped) is not the
            # checkpoint as served, and the demo is never shown one
            and not r.get("ablation")
        )

    def on_demo(runs: list[dict]) -> list[dict]:
        if not (upstream and order):
            return runs  # the mock, or no list configured
        runs = [r for r in runs if r["run"] not in excluded]
        done = {
            v for r in runs if r.get("status", "done") == "done" for v in r["video_ids"]
            if demo_run(r, v)
        }  # fmt: skip
        keep = interim and not all(v in done for v in order if held_out(v) is None)
        # one finished run a video (the owner, 2026-11-07: HeiChole's D = 8 run beside its
        # D = 4 run, "only the 4 s run"): the newest checkpoint's (the
        # final model's runs replace the earlier checkpoints', which stay stored and
        # unlisted), and of its runs, in its served form, the one that covers most of the
        # video, where the screen opened it already; a run still being written is
        # followed beside it.
        # A checkpoint's age is its first run's: a later rerun of an old one is still old
        born: dict = {}
        for r in runs:
            if r.get("created") is not None:
                k = r.get("checkpoint")
                born[k] = min(born.get(k, r["created"]), r["created"])
        # of one checkpoint's runs, one in its served decision form first (api.md v1.12,
        # `stage3-final` is served stateless; a log before v1.12 does not
        # say, and comes after a run that says it is served and before one that says not)
        form = lambda r: {True: 1, None: 0, False: -1}[r.get("served")]
        newer = lambda r, v: (
            born.get(r.get("checkpoint"), float("-inf")),
            form(r),
            r.get("sizes", {}).get(v, 0),
        )
        best: dict[str, dict] = {}
        for r in runs:
            if r.get("status", "done") != "done":
                continue
            for v in r["video_ids"]:
                if demo_run(r, v) and (v not in best or newer(r, v) > newer(best[v], v)):
                    best[v] = r
        shown = lambda r, v: r.get("status", "done") != "done" or best[v]["run"] == r["run"]
        out = []
        for r in runs:
            vids = [
                v for v in r["video_ids"]
                if (demo_run(r, v) and shown(r, v))
                or (keep and (r["run"], v) == (interim["run"], interim["video"]))
            ]  # fmt: skip
            if vids:
                out.append({**r, "video_ids": vids})
        return out

    # its place in the listing: the demo's order; the interim run after the videos that
    # are not held out, so it opens the page until they exist
    first_held = next((i for i, v in enumerate(order) if held_out(v) is not None), len(order))
    rank = {v: float(i) for i, v in enumerate(order)}

    async def listed(fresh: bool = False) -> dict:
        if fresh or time.monotonic() - listing["at"] > 60:
            runs = on_demo(await run_in_threadpool(source.runs))
            by = lambda st: {
                (r["run"], v) for r in runs if r.get("status", "done") == st for v in r["video_ids"]
            }
            listing["pairs"], listing["writing"] = by("done"), by("running")
            listing["videos"] = {v for _, v in listing["pairs"] | listing["writing"]}
            listing["private"] = set().union(*(r.get("private", ()) for r in runs))
            # api.md v1.13: val's reading of each run's served CVS, already cut
            listing["cvs_val"] = {r["run"]: r.get("cvs_val") for r in runs}
            listing["at"] = time.monotonic()
        return listing

    first = default_video()
    proxy_client: list[httpx.AsyncClient] = []

    async def proxy(path: str, request: Request, keep: tuple[str, ...], extra: dict | None = None):
        """Stream one upstream response through (a Range request passes on), with only
        the named headers: nothing else about the upstream reaches the browser."""
        if not proxy_client:
            transport = getattr(source, "async_transport", None)  # tests: a fake upstream
            proxy_client.append(
                httpx.AsyncClient(base_url=upstream, timeout=30, transport=transport)
            )
        client = proxy_client[0]
        fwd = {k: v for k, v in request.headers.items() if k.lower() == "range"}
        try:
            req = client.build_request("GET", path, params=dict(request.query_params), headers=fwd)
            up = await client.send(req, stream=True)
        except httpx.HTTPError:
            return error("upstream", "the model server did not answer", 502)
        if up.status_code >= 400:
            await up.aclose()
            return error("not_found", "no such run, video or frame", 404)
        headers = {k: v for k, v in up.headers.items() if k.lower() in keep}
        headers.update(extra or {})
        if up.is_stream_consumed:  # an upstream answer already read in full
            await up.aclose()
            return Response(up.content, status_code=up.status_code, headers=headers)
        return StreamingResponse(
            up.aiter_raw(),
            status_code=up.status_code,
            headers=headers,
            background=BackgroundTask(up.aclose),
        )

    # errors name the problem only: an exception's text could carry a path
    def error(code: str, detail: str, status: int) -> JSONResponse:
        return JSONResponse({"error": code, "detail": detail}, status_code=status)

    async def videos(request: Request):
        try:
            runs = on_demo(await run_in_threadpool(source.runs))
        except httpx.HTTPError:
            return error("upstream", "the model server did not answer", 502)
        listed = [
            {"run": r["run"], "video_id": v, "mode": r["mode"], "source": r["source"],
             "from_t": r.get("from_t"), "writing": r.get("status", "done") == "running",
             "held_out": held_out(v) is not None, "_size": r.get("sizes", {}).get(v, 0)}
            for r in runs
            for v in r["video_ids"]
            if not _hidden(v, request, r.get("private", ()))
        ]  # fmt: skip

        # the screen opens on the demo's first video, on the finished
        # run that covers most of it; a run still being written comes after,
        # marked, and is followed, never shown as if it were done
        def place(x: dict) -> float:
            if order:
                return rank.get(x["video_id"], first_held - 0.5)
            return float(x["video_id"] != first)

        listed.sort(key=lambda x: (place(x), x["writing"], -x.pop("_size")))
        return JSONResponse(listed)

    async def rollout(request: Request):
        run, video = request.path_params["run"], request.path_params["video"]
        if await hidden(video, request):
            return error("not_found", "no such run, video or frame", 404)
        try:
            known = await listed()
            if (run, video) in known["writing"]:
                known = await listed(fresh=True)  # it may have ended since the last look
            if (run, video) in known["writing"]:
                return error("writing", "this run is still being written: follow it", 409)
            if upstream and (run, video) not in known["pairs"]:
                raise KeyError(video)
            lines = await run_in_threadpool(source.load, run, video)
        except KeyError:
            return error("not_found", "no such run, video or frame", 404)
        except httpx.HTTPError:
            return error("upstream", "the model server did not answer", 502)
        return JSONResponse(to_screen(lines, pinned, known.get("cvs_val", {}).get(run)))

    async def frame(request: Request):
        video, t = request.path_params["video"], request.path_params["t"]
        variant = request.query_params.get("variant", "current")
        if await hidden(video, request):
            return error("not_found", "no such run, video or frame", 404)
        own = held_out(video) or video in listing["private"]
        cache = "private, max-age=3600" if own else "max-age=3600"
        if upstream:
            try:
                if video not in (await listed())["videos"]:
                    return error("not_found", "no such run, video or frame", 404)
            except httpx.HTTPError:
                return error("upstream", "the model server did not answer", 502)
            path = f"/api/frames/{quote(video, safe='')}/{t}.jpg"
            return await proxy(
                path, request, ("content-type", "content-length"), {"Cache-Control": cache}
            )
        try:
            path = source.frame_path(video, t, variant)
        except KeyError:
            return error("not_found", "no such run, video or frame", 404)
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": cache})

    async def video(request: Request):
        if await hidden(request.path_params["video"], request):
            return error("not_found", "no such run, video or frame", 404)
        if upstream:
            try:
                if request.path_params["video"] not in (await listed())["videos"]:
                    return error("not_found", "no such run, video or frame", 404)
            except httpx.HTTPError:
                return error("upstream", "the model server did not answer", 502)
            path = f"/api/video/{quote(request.path_params['video'], safe='')}"
            keep = ("content-type", "content-length", "content-range", "accept-ranges")
            return await proxy(path, request, keep)
        try:
            path = source.video_path(request.path_params["video"])
        except KeyError:
            return error("not_found", "no such run, video or frame", 404)
        # FileResponse answers a Range request with 206 and the asked bytes
        return FileResponse(path, media_type="video/mp4")

    # the owner signs in on the page with his password (no user name, no other
    # address); the cookie it sets is what lets a question reach the model
    failures: collections.deque = collections.deque()

    async def sign_in(request: Request):
        now = time.monotonic()
        while failures and now - failures[0] > 600:
            failures.popleft()
        if len(failures) >= SIGNIN_FAILURES:
            return error("rate_limited", "too many wrong passwords; wait ten minutes", 429)
        try:
            password = str((await request.json()).get("password", ""))
        except (ValueError, AttributeError):
            password = ""
        if not await run_in_threadpool(owner.check, password[:1024]):
            failures.append(now)
            return error("forbidden", "wrong password", 403)
        res = JSONResponse({"owner": True})
        secure = request.headers.get("x-forwarded-proto") == "https"
        res.set_cookie(
            OWNER_COOKIE,
            owner.cookie(),
            max_age=30 * 86400,
            httponly=True,
            secure=secure,
            samesite="strict",
        )
        return res

    # the Owner tab's "Sign out" (the owner, 2026-11-07): this browser's cookie dropped;
    # the password and every other browser stay as they are
    async def sign_out(request: Request):
        res = JSONResponse({"owner": False})
        secure = request.headers.get("x-forwarded-proto") == "https"
        res.delete_cookie(OWNER_COOKIE, httponly=True, secure=secure, samesite="strict")
        return res

    async def owner_route(request: Request):
        return await (sign_out if request.method == "DELETE" else sign_in)(request)

    async def me(request: Request):
        return JSONResponse({"owner": is_owner(request)})

    async def ask(request: Request):
        if not is_owner(request):
            return error("owner_only", "asking the model is the owner's; sign in first", 403)
        body = await request.json()
        question = str(body.get("question", "")).strip()
        if not question:
            return error("empty_question", "the question is empty", 400)
        try:
            reply = await run_in_threadpool(
                source.ask, body["run"], body["video_id"], float(body.get("t", 0.0)), question
            )
        except httpx.HTTPError:
            return error("upstream", "the model server did not answer", 502)
        if "error" in reply:
            return JSONResponse(ask_answer(reply), status_code=503)
        return JSONResponse(ask_answer(reply))

    # a run still being written, followed for every viewer at once (follow.py)
    hubs = (
        Hubs(source.follow, pinned, sessions_dir or RUNS / "sessions")
        if hasattr(source, "follow")
        else None
    )
    following: collections.Counter = collections.Counter()

    async def follow(ws: WebSocket):
        run, video = ws.path_params["run"], ws.path_params["video"]
        who = _address(ws.headers, ws.client)
        known = await listed()
        if hubs is not None and (run, video) not in known["writing"]:
            known = await listed(fresh=True)
        # accepted before any refusal: a socket closed before its handshake reaches the
        # browser as HTTP 403 and close code 1006, and the screen must read why
        await ws.accept()
        if (
            hubs is None
            or await hidden(video, ws)
            or ((run, video) not in known["writing"] and (run, video) not in hubs.hubs)
        ):
            await ws.close(code=4404)  # not being written (finished meanwhile): load the replay
            return
        if (
            following[who] >= FOLLOW_LIMITS["visitor"]
            or following.total() >= FOLLOW_LIMITS["total"]
        ):
            await ws.close(code=4429)
            return
        try:
            after = max(0, int(ws.query_params.get("after", 0)))
        except ValueError:
            after = 0
        following[who] += 1
        _append(access_log, {"time": round(time.time(), 3), "client": ws.client.host if ws.client else None,
                             "forwarded_for": _forwarded(ws.headers), "visitor": who,
                             "method": "WS", "path": ws.url.path, "status": 101})  # fmt: skip
        try:
            async for msg in hubs.get(run, video).watch(after):
                await ws.send_json(msg)
            await ws.close()
        except Exception:  # noqa: BLE001, S110 - the viewer went away: nothing to do
            pass
        finally:
            following[who] -= 1

    @contextlib.asynccontextmanager
    async def lifespan(app):
        yield
        if hubs is not None:
            await hubs.close()

    routes = [
        Route("/api/videos", videos),
        WebSocketRoute("/api/follow/{run}/{video}", follow),
        Route("/api/rollout/{run}/{video}", rollout),
        Route("/api/frames/{video}/{t:int}.jpg", frame),
        Route("/api/video/{video}", video),
        Route("/api/ask", ask, methods=["POST"]),
        Route("/api/me", me),
        Route("/api/owner", owner_route, methods=["POST", "DELETE"]),
    ]
    if web_dist.is_dir():
        routes.append(Mount("/", StaticFiles(directory=web_dist, html=True)))
    else:

        async def no_build(request: Request):
            return PlainTextResponse("web/dist is missing: run `npm run build` in web/", 503)

        routes.append(Route("/", no_build))
    middleware = [
        Middleware(AccessLog, path=access_log),
        # the decision log is JSON, about 30 times smaller compressed (VID103's 7.1 MB is
        # 0.23 MB): the share's monthly transfer is the owner's ngrok allowance, which
        # ran out on 2026-11-09. Never the video (its byte ranges are left as they are,
        # and a 1 fps H.264 does not shrink) nor the frames and pictures.
        Middleware(
            GZipMiddleware,
            minimum_size=1024,
            compresslevel=6,
            exclude_content_types=("text/event-stream", "video/mp4", "image/jpeg", "image/webp"),
        ),
        Middleware(RateLimit, limits=limits or LIMITS),
    ]
    return Starlette(routes=routes, middleware=middleware, lifespan=lifespan)


def serve(source: ScreenSource, host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
    import uvicorn

    check_host(host)
    uvicorn.run(create_app(source), host=host, port=port, access_log=False, server_header=False)

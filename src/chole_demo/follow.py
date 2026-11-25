"""Following a run as it is written.

One `Follow` per run and video, shared by every viewer: it opens the source's stream
(chole-eval's `WS /api/stream`, api.md v1.1, joined with the lines already stored),
keeps the lines cut to the screen's fields, and hands them to each viewer from where
that viewer left off. When the upstream goes away (a restart, a dropped socket) it
reconnects with a growing pause and takes up where it was: lines are kept once by
their kind and tick, so nothing is shown twice and nothing is skipped.

It also writes the session log (`session_log.py`): every line as it arrived, with
the wall time it arrived, for the §8 synthetic row in step 3.

The browser's side is `/api/follow/{run}/{video}` in `server.py`, a WebSocket that
sends `meta`, then each `line` in order, `status` when the upstream's state changes,
a `ping` when idle, and `end`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from chole_demo.client.adapter import (
    DROPPED_KEYS,
    END_COUNTS,
    Reader,
    normalize_decision,
    speaks,
    to_screen,
)
from chole_demo.session_log import SessionLog

BACKOFF_S = (1, 2, 4, 8, 15, 30)
log = logging.getLogger(__name__)

Opener = Callable[[str, str], AsyncIterator[dict]]


class Follow:
    """A run being written, followed once for every viewer."""

    def __init__(
        self, run: str, video_id: str, opener: Opener, pinned: str, log: SessionLog | None
    ) -> None:
        self.run, self.video_id = run, video_id
        self.opener, self.pinned, self.log = opener, pinned, log
        self.meta: dict | None = None
        self.items: list[dict] = []  # decision and dropped lines, cut, in tick order
        self.end: dict | None = None
        self.upstream = "connecting"  # following | reconnecting | ended | unreadable
        self._seen: set[tuple[str, int]] = set()
        self._reader: Reader | None = None  # from the header: D, the hint's threshold
        self._changed = asyncio.Condition()
        self._task: asyncio.Task | None = None

    @property
    def over(self) -> bool:
        return self.upstream in ("ended", "unreadable")

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _set(self, upstream: str | None = None) -> None:
        async with self._changed:
            if upstream:
                self.upstream = upstream
            self._changed.notify_all()

    async def _run(self) -> None:
        tries = 0
        while not self.over:
            try:
                async for line in self.opener(self.run, self.video_id):
                    if self.upstream != "following":
                        await self._set("following")
                    tries = 0
                    await self._take(line)
                    if self.over:
                        break
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - any upstream failure: try again, say so
                log.info(
                    "follow %s %s: upstream lost (%s)", self.run, self.video_id, type(e).__name__
                )
            if not self.over:
                await self._set("reconnecting")
                await asyncio.sleep(BACKOFF_S[min(tries, len(BACKOFF_S) - 1)])
                tries += 1

    async def _take(self, line: dict) -> None:
        kind = line.get("kind")
        if not speaks(line.get("api_version"), self.pinned):
            await self._set("unreadable")  # a newer API waits for the pin to move
            return
        if self.log:
            self.log.write(line)
        if kind == "header":
            if self.meta is None:
                try:
                    self._reader = Reader(line)
                    self.meta = to_screen([line], self.pinned)["meta"]
                except (ValueError, KeyError):  # a source or a header the screen refuses
                    await self._set("unreadable")  # not retried
                    return
        elif kind in ("decision", "dropped"):
            key = (kind, int(line["tick"]))
            if key in self._seen:
                return
            self._seen.add(key)
            if kind == "decision":
                cut = self._reader.read(line) if self._reader else normalize_decision(line)
            else:
                cut = {k: line.get(k) for k in DROPPED_KEYS}
            self.items.append(cut)
        elif kind == "end":
            self.end = {k: line.get(k) for k in END_COUNTS}
            self.upstream = "ended"
        await self._set()

    def _news(self, after: int, sent_meta: bool, sent_status: str | None) -> bool:
        return (
            (self.meta is not None and not sent_meta)
            or len(self.items) > after
            or self.upstream != sent_status
        )

    async def watch(self, after: int = 0, ping_s: float = 15.0) -> AsyncIterator[dict]:
        """The messages for one viewer, from line `after` on (a viewer that reconnects
        passes how many lines it holds)."""
        sent_meta, sent_status = False, None
        while True:
            async with self._changed:
                news = lambda a=after, m=sent_meta, s=sent_status: self._news(a, m, s)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._changed.wait_for(news), ping_s)
                if not news():
                    yield {"type": "ping"}
                    continue
                items, upstream, meta = self.items[after:], self.upstream, self.meta
            if meta is not None and not sent_meta:
                sent_meta = True
                yield {"type": "meta", "meta": meta}
            if upstream != sent_status:  # before the lines: a backlog can be long
                sent_status = upstream
                yield {"type": "status", "upstream": upstream}
            if meta is not None:
                for line in items:
                    yield {"type": "line", "i": after, "line": line}
                    after += 1
            if upstream == "ended":
                yield {"type": "end", "end": self.end}
                return
            if upstream == "unreadable":
                return


class Hubs:
    """The runs being followed, one `Follow` each, started on the first viewer."""

    def __init__(self, opener: Opener, pinned: str, sessions_dir: Path | None) -> None:
        self.opener, self.pinned, self.sessions_dir = opener, pinned, sessions_dir
        self.hubs: dict[tuple[str, str], Follow] = {}

    def get(self, run: str, video_id: str) -> Follow:
        key = (run, video_id)
        hub = self.hubs.get(key)
        if hub is None or hub.upstream == "unreadable":
            log = SessionLog(self.sessions_dir, run, video_id) if self.sessions_dir else None
            hub = self.hubs[key] = Follow(run, video_id, self.opener, self.pinned, log)
            hub.start()
        return hub

    async def close(self) -> None:
        for hub in self.hubs.values():
            await hub.stop()

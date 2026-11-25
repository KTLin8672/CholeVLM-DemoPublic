"""chole-demo's commands.

python -m chole_demo mock                  # build the mock rollout and video, print hashes
python -m chole_demo serve [--port 8781]   # the screen on 127.0.0.1 (--source api: the model server)
python -m chole_demo share [--port 8781]   # share it through ngrok, public and read-only
python -m chole_demo owner-password        # set the owner's password for asking the model
python -m chole_demo record [--run R --video V] [--from T] [--seconds 120] [--replace]   # recordings/
python -m chole_demo bake-instruments      # the tools page's pictures from their 3D models
python -m chole_demo tenant -- CMD ...      # heavy CPU work beside training, bounded (v4.3)
"""

from __future__ import annotations

import argparse

from chole_demo.client.adapter import open_source
from chole_demo.server import DEFAULT_PORT, RUNS, serve


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="chole_demo")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mock", help="build the mock rollout and its test-pattern video")
    s = sub.add_parser("serve", help="serve the screen on loopback")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    s.add_argument("--source", default="mock", choices=["mock", "api", "replay"])
    sh = sub.add_parser(
        "share", help="share the running screen through ngrok, public and read-only"
    )
    sh.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub.add_parser("owner-password", help="set the owner's password for asking the model")
    r = sub.add_parser("record", help="record the screen frame by frame into recordings/")
    r.add_argument("--run", help="a listed run (default: the screen's first)")
    r.add_argument("--video", help="its video_id (default: the run's first listed)")
    r.add_argument("--from", dest="start", type=float, help="video second to start at")
    r.add_argument("--seconds", type=float, default=120.0)
    r.add_argument("--fps", type=int, default=30)
    r.add_argument("--size", default="1920x1080")
    r.add_argument("--view", default="presenter", choices=["presenter", "engineer"])
    r.add_argument("--port", type=int, default=DEFAULT_PORT)
    r.add_argument(
        "--replace", action="store_true", help="record over a recording of the same name"
    )
    sub.add_parser(
        "bake-instruments",
        help="draw the instruments' pictures from their 3D models into web/public/instruments/",
    )
    t = sub.add_parser(
        "tenant",
        help="run heavy CPU work (renders, screen tests) in its scope, under the step canary",
    )
    t.add_argument("command", nargs=argparse.REMAINDER)
    args = p.parse_args(argv)

    if args.cmd == "mock":
        from chole_demo.feeds.mock import build, describe

        print(describe(build(RUNS / "mock")))
    elif args.cmd == "serve":
        serve(open_source(args.source, RUNS), host=args.host, port=args.port)
    elif args.cmd == "share":
        from chole_demo.share import share

        raise SystemExit(share(args.port))
    elif args.cmd == "owner-password":
        from chole_demo.owner import Owner, set_password_interactively
        from chole_demo.server import OWNER_FILE

        raise SystemExit(set_password_interactively(Owner(OWNER_FILE)))
    elif args.cmd == "record":
        from chole_demo.record import record

        w, h = (int(x) for x in args.size.split("x"))
        record(
            args.run,
            args.video,
            args.start,
            args.seconds,
            args.fps,
            (w, h),
            args.view,
            args.port,
            replace=args.replace,
        )
    elif args.cmd == "bake-instruments":
        from chole_demo.bake import main as bake

        bake()
    elif args.cmd == "tenant":
        from chole_demo.tenant import run

        cmd = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not cmd:
            p.error("tenant: a command to run")
        raise SystemExit(run(cmd))


if __name__ == "__main__":
    main()

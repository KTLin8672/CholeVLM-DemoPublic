"""`python -m chole_demo bake-instruments`: the instruments' pictures for the tools page,
drawn once from their 3D models (web/src/room/instruments.js) and written to
web/public/instruments/<name>.webp, which the build ships with the page: each
tool shown in 2D, drawn from its 3D model.

It starts Vite's dev server on its own loopback port (5173), opens `bake.html`
in headless Chromium (Playwright's, in the venv), takes the pictures the page draws and
stops the server. Run it after a change to a model, under `tenant` while training runs;
the pictures are committed, so a build needs no GPU and no browser. It writes nothing when
the page drew no picture; it draws over the committed ones, which git keeps.
"""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import subprocess
import time
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web"
OUT = WEB / "public" / "instruments"
PORT = 5173  # Vite's dev server (vite.config.js), loopback only


def _up(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def bake(out: Path = OUT) -> dict[str, str]:
    from playwright.sync_api import sync_playwright

    if _up(PORT):
        raise SystemExit(f"port {PORT} is in use: stop the other Vite dev server first")
    venv = Path(os.environ.get("VIRTUAL_ENV", Path.home() / ".virtualenvs" / "CholeVLMDemo"))
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(venv / "ms-playwright"))
    vite = subprocess.Popen(
        ["npx", "vite", "--host", "127.0.0.1", "--port", str(PORT), "--strictPort"],
        cwd=WEB, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        for _ in range(200):
            if _up(PORT):
                break
            time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{PORT}/bake.html")
            page.wait_for_function("window.__baked !== undefined", timeout=300_000)
            baked: dict[str, str] = page.evaluate("window.__baked")
            browser.close()
    finally:
        vite.terminate()
        vite.wait(timeout=10)
    if not baked:
        raise SystemExit("no pictures: the page had no WebGL")
    out.mkdir(parents=True, exist_ok=True)
    sums = {}
    for name, url in sorted(baked.items()):
        head, data = url.split(",", 1)
        if head != "data:image/webp;base64":
            raise SystemExit(f"{name}: not a WebP ({head})")
        raw = base64.b64decode(data)
        (out / f"{name}.webp").write_bytes(raw)
        sums[name] = hashlib.sha256(raw).hexdigest()
    return sums


def main() -> None:
    for name, sha in bake().items():
        print(f"{name}.webp sha256 {sha}")

"""Share the screen through ngrok, in public and read-only.

The demo server stays on loopback; the owner's ngrok agent, already
installed and logged in by him, carries that one port to his account's public HTTPS
address. Viewing is open and read-only; asking the model is the owner's alone (his
password, typed in the page's Ask box; `owner.py`). At the edge a traffic policy tells crawlers
not to index and sends no referrer. Run as a user service (deploy/), the share
survives the session.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import yaml

from chole_demo.server import DEFAULT_PORT, REPO, RUNS

POLICY = RUNS / "share" / "policy.yml"
AGENT_API = "http://127.0.0.1:4040/api/tunnels"  # the agent's own inspector, loopback
__all__ = ["POLICY", "REPO", "policy", "share"]


def _private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)


def policy() -> dict:
    """ngrok traffic policy for the public share: nothing indexed, no referrer sent."""
    headers = {"x-robots-tag": "noindex, nofollow", "referrer-policy": "no-referrer"}
    return {
        "on_http_response": [{"actions": [{"type": "add-headers", "config": {"headers": headers}}]}]
    }


def _public_url(timeout: float = 20.0) -> str | None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(AGENT_API, timeout=2) as r:
                tunnels = json.load(r).get("tunnels", [])
            for t in tunnels:
                if t.get("public_url", "").startswith("https://"):
                    return t["public_url"]
        except OSError:
            pass
        time.sleep(0.5)
    return None


def share(port: int = DEFAULT_PORT) -> int:
    ngrok = shutil.which("ngrok") or str(Path.home() / ".local" / "bin" / "ngrok")
    if not Path(ngrok).exists():
        raise SystemExit(
            "ngrok is not installed (the owner's: install it and run `ngrok config add-authtoken`)"
        )
    # the server may still be starting (the two user services start together)
    for attempt in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3).close()
            break
        except OSError as e:
            if attempt == 59:
                raise SystemExit(f"the demo server is not answering on 127.0.0.1:{port}") from e
            time.sleep(1)
    _private(POLICY, yaml.safe_dump(policy()))
    cmd = [ngrok, "http", f"http://127.0.0.1:{port}", "--traffic-policy-file", str(POLICY)]
    agent = subprocess.Popen([*cmd, "--log", "stdout", "--log-level", "warn"])
    url = _public_url()
    if url is None:
        agent.terminate()
        raise SystemExit("ngrok did not report a public address; see its log above")
    print(
        f"shared at {url}: public and read-only; asking is the owner's, by his password",
        flush=True,
    )
    try:
        return agent.wait()
    except KeyboardInterrupt:
        agent.terminate()
        return 0

"""The owner's sign-in to ask the model (the owner, 2026-11-05: a
password typed on the page itself, no user name, no other address).

Everything lives in the gitignored `configs/owner.local.yaml`, mode 600:
- `token`: a random key, made once and never typed; it signs the sign-in cookie.
- `password_hash`: the scrypt hash of the owner's password. He sets it with
  `python -m chole_demo owner-password` (asked twice, never echoed). He may also write
  `password: …` in the file himself; the next sign-in attempt replaces that line with
  its hash, so the password never stays in the file as typed.

The file is read again whenever it changes, so a new password needs no restart. The
cookie is bound to the hash, so setting a new password signs out every browser.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import os
import secrets
import threading
from pathlib import Path

import yaml

N, R, P = 2**14, 8, 1  # scrypt: about 16 MB and some tens of ms a try
MIN_LENGTH = 8  # the owner, 2026-11-05: "i want to use a 8 charter password"


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${N}${R}${P}${b64(salt)}${b64(key)}"


def verify(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, key = stored.split("$")
        if kind != "scrypt":
            return False
        got = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, base64.b64decode(key))


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(yaml.safe_dump(data))
    os.replace(tmp, path)
    os.chmod(path, 0o600)


class Owner:
    """The owner's keys, read from `path` (created with a token if missing)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._seen: tuple[float, int] | None = None
        self._data: dict = {}

    def _load(self) -> dict:
        with self._lock:
            if not self.path.exists():
                _write(self.path, {"token": secrets.token_urlsafe(24)})
            st = self.path.stat()
            if self._seen != (st.st_mtime, st.st_size):
                data = yaml.safe_load(self.path.read_text()) or {}
                if not data.get("token"):
                    data["token"] = secrets.token_urlsafe(24)
                    _write(self.path, data)
                if data.get("password"):  # typed into the file: keep its hash only
                    data["password_hash"] = hash_password(str(data.pop("password")))
                    _write(self.path, data)
                os.chmod(self.path, 0o600)
                st = self.path.stat()
                self._seen, self._data = (st.st_mtime, st.st_size), data
            return self._data

    def has_password(self) -> bool:
        return bool(self._load().get("password_hash"))

    def check(self, password: str) -> bool:
        stored = self._load().get("password_hash")
        return bool(stored) and bool(password) and verify(password, stored)

    def cookie(self) -> str | None:
        """The signed-in cookie's value; none while no password is set."""
        data = self._load()
        if not data.get("password_hash"):
            return None
        msg = b"chole-demo owner\0" + data["password_hash"].encode()
        return hmac.new(data["token"].encode(), msg, hashlib.sha256).hexdigest()

    def set_password(self, password: str) -> None:
        data = dict(self._load())
        data.pop("password", None)
        data["password_hash"] = hash_password(password)
        _write(self.path, data)


def set_password_interactively(owner: Owner) -> int:
    """`python -m chole_demo owner-password`: asked twice, never echoed, never logged."""
    first = getpass.getpass("New owner password: ")
    if len(first) < MIN_LENGTH:
        print(f"Too short: at least {MIN_LENGTH} characters. Nothing changed.")
        return 1
    if getpass.getpass("Again: ") != first:
        print("The two did not match. Nothing changed.")
        return 1
    owner.set_password(first)
    print(
        f"Set (its hash is in {owner.path.name}). Browsers signed in before are signed out; "
        "type the password in the Ask box on the page."
    )
    return 0

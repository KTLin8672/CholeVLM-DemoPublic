"""The owner's password (typed on the page, no user name, no
other address): only its hash is kept, in a file only he can read; a new password
signs every browser out."""

import stat

import pytest
import yaml

from chole_demo import owner as o


@pytest.fixture
def owner(tmp_path):
    return o.Owner(tmp_path / "owner.local.yaml")


def test_only_the_hash_is_kept(owner):
    owner.set_password("correct horse battery")
    text = owner.path.read_text()
    assert "correct horse battery" not in text and "password_hash: scrypt$" in text
    assert stat.S_IMODE(owner.path.stat().st_mode) == 0o600
    assert owner.check("correct horse battery")
    assert not owner.check("correct horse batterY") and not owner.check("")


def test_no_password_no_owner(owner):
    assert owner.cookie() is None and not owner.check("") and not owner.has_password()
    assert yaml.safe_load(owner.path.read_text())["token"]  # the file is made, with its key


def test_a_password_typed_into_the_file_is_replaced_by_its_hash(owner):
    owner.cookie()
    data = yaml.safe_load(owner.path.read_text())
    owner.path.write_text(yaml.safe_dump({**data, "password": "typed by hand, twelve+"}))
    assert owner.check("typed by hand, twelve+")
    after = yaml.safe_load(owner.path.read_text())
    assert "password" not in after and after["token"] == data["token"]
    assert stat.S_IMODE(owner.path.stat().st_mode) == 0o600


def test_a_new_password_signs_everyone_out(owner):
    owner.set_password("the first password")
    first = owner.cookie()
    owner.set_password("the second password")
    assert owner.cookie() != first and not owner.check("the first password")


def test_a_malformed_hash_never_passes(owner):
    owner.cookie()
    data = yaml.safe_load(owner.path.read_text())
    owner.path.write_text(yaml.safe_dump({**data, "password_hash": "plain$text"}))
    assert not owner.check("plain") and not owner.check("text")


def test_the_command_asks_twice_and_wants_eight(owner, monkeypatch):
    answers = iter(["seven77"])
    monkeypatch.setattr(o.getpass, "getpass", lambda prompt="": next(answers))
    assert o.set_password_interactively(owner) == 1 and not owner.has_password()
    answers = iter(["a long enough password", "a different password"])
    assert o.set_password_interactively(owner) == 1 and not owner.has_password()
    answers = iter(["eight888", "eight888"])
    assert o.set_password_interactively(owner) == 0 and owner.check("eight888")

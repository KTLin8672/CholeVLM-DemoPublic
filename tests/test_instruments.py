"""The tools page's pictures: every instrument the page can name
has its picture, drawn from its 3D model by `python -m chole_demo bake-instruments` and
shipped with the page; no browser here."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
PICS = WEB / "public" / "instruments"


def test_every_named_picture_is_shipped_and_drawn_from_a_model():
    panels = (WEB / "src" / "panels.js").read_text()
    table = re.search(r"const PICTURE = \{(.*?)\};", panels, re.DOTALL).group(1)
    named = set(re.findall(r":\s*'([a-z_]+)'", table))
    models = (WEB / "src" / "room" / "instruments.js").read_text()
    built = set(re.findall(r"^  ([a-z_]+)\(M\) \{", models, re.MULTILINE))
    assert named == built == {
        "grasper", "clipper", "scissors", "hook", "bipolar", "suction_irrigation",
        "specimen_bag", "stapler", "other",
    }  # fmt: skip
    for name in named:
        raw = (PICS / f"{name}.webp").read_bytes()
        assert raw[:4] == b"RIFF" and raw[8:12] == b"WEBP", name
        assert b"EXIF" not in raw and b"XMP " not in raw, name  # nothing but the picture

"""The replay: stored outputs in the page's form, the picture made from the user's own copy."""

import json
import shutil
import subprocess
from urllib.parse import quote

import pytest
from starlette.testclient import TestClient

from chole_demo.client.adapter import open_source
from chole_demo.feeds.replay import OUTPUTS, SIZES, ReplaySource, make
from chole_demo.owner import Owner
from chole_demo.server import create_app

STORED = sorted(OUTPUTS.glob("*.json"))
FIRST, SECOND = "cholect50:VID103", "cholec80:46"
PASSWORD = "a long test password"


def _app(tmp_path, signed_in=False):
    owner = Owner(tmp_path / "owner.local.yaml")
    owner.set_password(PASSWORD)
    client = TestClient(
        create_app(
            ReplaySource(tmp_path),
            web_dist=tmp_path / "nodist",
            access_log=tmp_path / "access.log",
            owner=owner,
        )
    )
    if signed_in:
        assert client.post("/api/owner", json={"password": PASSWORD}).status_code == 200
    return client


def _run(video_id):
    return json.loads((OUTPUTS / f"{video_id.replace(':', '_')}.json").read_text())["meta"]["run"]


def _jpeg_size(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return tuple(int(x) for x in out.stdout.strip().split(","))


def test_the_stored_outputs_are_the_pages_form():
    assert [p.name for p in STORED] == ["cholec80_46.json", "cholect50_VID103.json"]
    for path in STORED:
        text = path.read_text()
        rollout = json.loads(text)
        assert set(rollout) == {"meta", "decisions", "dropped", "end"}
        meta = rollout["meta"]
        assert path.stem == meta["video_id"].replace(":", "_")
        assert meta["held_out"] is None and meta["feed"] == "real"
        assert "research demo, not for clinical use" in meta["attribution"]
        assert len(rollout["decisions"]) == rollout["end"]["decisions"]
        assert '"cvs":' not in text  # the model's own CVS reading is not in them


def test_listed_in_the_demos_order_and_served_as_stored(tmp_path):
    client = _app(tmp_path)
    listed = client.get("/api/videos").json()
    assert [x["video_id"] for x in listed] == [FIRST, SECOND]
    for video_id in (FIRST, SECOND):
        r = client.get(f"/api/rollout/{_run(video_id)}/{quote(video_id, safe='')}")
        stored = OUTPUTS / f"{video_id.replace(':', '_')}.json"
        assert r.status_code == 200 and r.json() == json.loads(stored.read_text())
    assert client.get(f"/api/rollout/other/{quote(FIRST, safe='')}").status_code == 404
    assert client.get(f"/api/rollout/{_run(FIRST)}/heichole%3A4").status_code == 404


def test_no_picture_until_it_is_made(tmp_path):
    client = _app(tmp_path)
    assert ReplaySource(tmp_path).missing() == [SECOND, FIRST]
    assert client.get(f"/api/video/{quote(FIRST, safe='')}").status_code == 404
    assert client.get(f"/api/frames/{quote(FIRST, safe='')}/0.jpg").status_code == 404


def test_the_picture_from_a_folder_of_frames(tmp_path):
    folder = tmp_path / "frames"
    folder.mkdir()
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=854x480:rate=1",
         "-frames:v", "7", "-start_number", "1", str(folder / "video46_%06d.png")],
        check=True,
    )  # fmt: skip
    (folder / "video46_000004.png").unlink()  # a missing second repeats the one before it
    done = make(SECOND, folder, tmp_path)
    assert done == {"video": SECOND, "seconds": 7, "outputs_seconds": 1653}
    for variant, size in SIZES.items():
        frames = sorted((tmp_path / "replay" / "frames" / variant / "cholec80_46").glob("*.jpg"))
        assert [p.name for p in frames] == [f"{t:05d}.jpg" for t in range(7)]
        assert _jpeg_size(frames[0]) == size
    client = _app(tmp_path)
    r = client.get(f"/api/video/{quote(SECOND, safe='')}", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    r = client.get(f"/api/frames/{quote(SECOND, safe='')}/6.jpg?variant=video")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/frames/{quote(SECOND, safe='')}/7.jpg").status_code == 404


def test_the_picture_from_a_video_file(tmp_path):
    video = tmp_path / "video103.mp4"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25",
         "-t", "5", "-pix_fmt", "yuv420p", str(video)],
        check=True,
    )  # fmt: skip
    done = make(FIRST, video, tmp_path)
    assert done["seconds"] == 5
    mp4 = tmp_path / "replay" / "video" / "cholect50_VID103.mp4"
    assert _jpeg_size(mp4) == SIZES["current"]
    assert ReplaySource(tmp_path).missing() == [SECOND]


def test_asking_says_no_model_is_connected(tmp_path):
    body = {"run": _run(FIRST), "video_id": FIRST, "t": 10, "question": "which phase?"}
    assert _app(tmp_path).post("/api/ask", json=body).status_code == 403
    r = _app(tmp_path, signed_in=True).post("/api/ask", json=body)
    assert r.status_code == 503 and r.json()["error"] == "no_model"


def test_serve_takes_the_replay_as_a_source(tmp_path):
    assert isinstance(open_source("replay", tmp_path), ReplaySource)


@pytest.fixture(autouse=True)
def _ffmpeg():
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.fail("ffmpeg and ffprobe are needed (the README's Before you start)")

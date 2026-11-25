"""A delivered result is not replaced unless the command is told to: `record` refuses
to record over a recording of the same name. No browser."""

import pytest

from chole_demo.__main__ import main
from chole_demo.record import refuse_existing


def test_record_refuses_to_record_over_a_recording(tmp_path):
    out = tmp_path / "VID-run-0s-120s-presenter.mp4"
    refuse_existing(out, replace=False)  # nothing there: goes ahead
    out.write_bytes(b"a deliverable")
    with pytest.raises(SystemExit, match="--replace"):
        refuse_existing(out, replace=False)
    refuse_existing(out, replace=True)
    assert out.read_bytes() == b"a deliverable"


def test_record_takes_replace(monkeypatch):
    seen = []
    monkeypatch.setattr("chole_demo.record.record", lambda *a, replace=False: seen.append(replace))
    main(["record"])
    main(["record", "--replace"])
    assert seen == [False, True]

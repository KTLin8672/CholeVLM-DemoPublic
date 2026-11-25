"""The tenant wrapper: training's step before and after, no start
during a dev evaluation or a gate, and the canary that stops the job past 1.25x the median.
No scope here (`scoped=False`): the job is a plain child process."""

import json
import sys
import threading
import time

from chole_demo.tenant import STOPPED, run

SLEEP = [sys.executable, "-c", "import time; time.sleep(30)"]


def _status(path, **kw):
    s = {"busy": True, "run": "stage2b", "phase": "training", "step": 900,
         "last_step_s": 121.0, "step_s_median": 120.0, "updated": "t"}  # fmt: skip
    s.update(kw)
    path.write_text(json.dumps(s))


def test_a_short_job_runs_and_the_steps_are_read(tmp_path, capsys):
    st = tmp_path / "train-spark.json"
    _status(st)
    code = run([sys.executable, "-c", "raise SystemExit(3)"], st, scoped=False, poll=0.1)
    out = capsys.readouterr().out
    assert code == 3
    assert "training before: stage2b step 900" in out and "training after:" in out


def test_no_start_during_a_dev_evaluation(tmp_path):
    st = tmp_path / "train-spark.json"
    _status(st, phase="dev_eval")
    t0 = time.monotonic()
    assert run(SLEEP, st, scoped=False, poll=0.1) == STOPPED
    assert time.monotonic() - t0 < 5


def test_the_canary_stops_the_job_on_a_slow_step(tmp_path, capsys):
    st = tmp_path / "train-spark.json"
    _status(st)
    # a new step at 1.3x the median, a moment after the job starts
    threading.Timer(0.5, lambda: _status(st, step=901, last_step_s=156.0)).start()
    t0 = time.monotonic()
    code = run(SLEEP, st, scoped=False, poll=0.2)
    assert code == STOPPED and time.monotonic() - t0 < 10
    assert "over 1.25 x the median" in capsys.readouterr().out


def test_a_step_under_the_limit_lets_it_run(tmp_path):
    st = tmp_path / "train-spark.json"
    _status(st)
    threading.Timer(0.3, lambda: _status(st, step=901, last_step_s=149.0)).start()
    code = run([sys.executable, "-c", "import time; time.sleep(1.2)"], st, scoped=False, poll=0.2)
    assert code == 0

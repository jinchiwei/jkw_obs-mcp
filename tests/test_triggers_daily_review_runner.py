"""Tests for the daily-review boot-trigger entry point."""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from jkw_obs_mcp.triggers.daily_review_runner import main, should_run_today


# ---- should_run_today ----


def test_should_run_when_state_file_missing(tmp_path):
    state = tmp_path / "missing.json"
    assert should_run_today(state) is True


def test_should_run_when_state_file_corrupt(tmp_path):
    state = tmp_path / "state.json"
    state.write_text("{not valid json")
    assert should_run_today(state) is True


def test_should_run_when_last_run_at_missing_in_json(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"foo": "bar"}))
    assert should_run_today(state) is True


def test_should_run_when_last_run_was_yesterday(tmp_path):
    state = tmp_path / "state.json"
    today = dt.date(2026, 4, 27)
    yesterday = dt.datetime(2026, 4, 26, 10, 0, 0, tzinfo=dt.UTC)
    state.write_text(json.dumps({"last_run_at": yesterday.isoformat()}))
    assert should_run_today(state, today=today) is True


def test_should_skip_when_last_run_was_today(tmp_path):
    state = tmp_path / "state.json"
    today = dt.date(2026, 4, 27)
    # Noon UTC falls within "today" in every timezone within UTC±12, so this
    # test is timezone-independent.
    midday_today = dt.datetime(2026, 4, 27, 12, 0, 0, tzinfo=dt.UTC)
    state.write_text(json.dumps({"last_run_at": midday_today.isoformat()}))
    assert should_run_today(state, today=today) is False


def test_should_run_when_last_run_was_far_in_past(tmp_path):
    state = tmp_path / "state.json"
    today = dt.date(2026, 4, 27)
    last_year = dt.datetime(2025, 4, 27, 0, 0, 0, tzinfo=dt.UTC)
    state.write_text(json.dumps({"last_run_at": last_year.isoformat()}))
    assert should_run_today(state, today=today) is True


def test_should_run_when_run_crossed_local_midnight_into_next_utc_day(tmp_path):
    """Regression: a run completed late local-time stores a UTC timestamp whose
    UTC date is already 'tomorrow'. should_run_today must compare LOCAL dates
    (not UTC dates) so the next day's local 'today' still triggers a fresh run.

    Concrete scenario: PDT user runs at 22:00 local on 2026-04-27.
    UTC equivalent: 05:00 on 2026-04-28. State file stores "2026-04-28T05:00:00+00:00".
    Next morning (2026-04-28 local), should_run_today must return True because
    in local time the previous run was on 2026-04-27.
    """
    monkeypatch_tz = "America/Los_Angeles"
    saved_tz = os.environ.get("TZ")
    os.environ["TZ"] = monkeypatch_tz
    time.tzset()
    try:
        state = tmp_path / "state.json"
        # 05:00 UTC on 2026-04-28 == 22:00 PDT on 2026-04-27 (UTC-7)
        late_yesterday_local = dt.datetime(2026, 4, 28, 5, 0, 0, tzinfo=dt.UTC)
        state.write_text(json.dumps({"last_run_at": late_yesterday_local.isoformat()}))

        # Today (local) is 2026-04-28
        today_local = dt.date(2026, 4, 28)
        assert should_run_today(state, today=today_local) is True
    finally:
        if saved_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = saved_tz
        time.tzset()


# ---- main() with injectable runner ----


def test_main_returns_0_when_today_already_ran(tmp_path):
    """If should_run_today is False, runner is never called, main returns 0."""
    state = tmp_path / "state.json"
    today = dt.date(2026, 4, 27)
    state.write_text(json.dumps({"last_run_at": dt.datetime(2026, 4, 27, 8, 0, tzinfo=dt.UTC).isoformat()}))

    called = []

    def fake_runner() -> int:
        called.append(True)
        return 0

    with patch("jkw_obs_mcp.triggers.daily_review_runner._state_path", return_value=state), \
         patch("jkw_obs_mcp.triggers.daily_review_runner._today", return_value=today):
        rc = main(_runner=fake_runner)

    assert rc == 0
    assert called == []  # runner was never invoked


def test_main_invokes_runner_when_stale(tmp_path):
    """If should_run_today is True, runner is invoked."""
    state = tmp_path / "missing.json"  # absent -> should_run_today=True

    called = []

    def fake_runner() -> int:
        called.append(True)
        return 0

    with patch("jkw_obs_mcp.triggers.daily_review_runner._state_path", return_value=state):
        rc = main(_runner=fake_runner)

    assert rc == 0
    assert called == [True]


def test_main_returns_1_when_runner_raises(tmp_path):
    """Runner raising must not propagate -- main catches, logs, returns 1."""
    state = tmp_path / "missing.json"

    def angry_runner() -> int:
        raise RuntimeError("simulated failure")

    with patch("jkw_obs_mcp.triggers.daily_review_runner._state_path", return_value=state):
        rc = main(_runner=angry_runner)

    assert rc == 1

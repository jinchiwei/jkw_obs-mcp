"""Tests for the daily-review boot-trigger entry point."""

from __future__ import annotations

import datetime as dt
import json
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
    earlier_today = dt.datetime(2026, 4, 27, 1, 0, 0, tzinfo=dt.UTC)
    state.write_text(json.dumps({"last_run_at": earlier_today.isoformat()}))
    assert should_run_today(state, today=today) is False


def test_should_run_when_last_run_was_far_in_past(tmp_path):
    state = tmp_path / "state.json"
    today = dt.date(2026, 4, 27)
    last_year = dt.datetime(2025, 4, 27, 0, 0, 0, tzinfo=dt.UTC)
    state.write_text(json.dumps({"last_run_at": last_year.isoformat()}))
    assert should_run_today(state, today=today) is True


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

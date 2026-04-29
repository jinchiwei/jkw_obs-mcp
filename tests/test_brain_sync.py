"""Tests for brain_sync.sync.ensure_brain_repo_fresh."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

from jkw_obs_mcp.brain_sync.sync import ensure_brain_repo_fresh


def test_pulls_when_no_state_file(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert any("pull" in " ".join(args) for args in runs)
    assert state.is_file()


def test_skips_when_cache_fresh(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    one_min_ago = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    state.write_text(json.dumps({"last_pull_at": one_min_ago.isoformat()}))
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert runs == []  # never called subprocess


def test_pulls_when_cache_stale(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    ten_min_ago = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10)
    state.write_text(json.dumps({"last_pull_at": ten_min_ago.isoformat()}))
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert any("pull" in " ".join(args) for args in runs)


def test_max_age_zero_always_pulls(tmp_path):
    """max_age_minutes=0 means 'always pull, ignore cache'."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    just_now = dt.datetime.now(dt.UTC)
    state.write_text(json.dumps({"last_pull_at": just_now.isoformat()}))
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        ensure_brain_repo_fresh(vault, max_age_minutes=0)

    assert any("pull" in " ".join(args) for args in runs)


def test_pull_failure_does_not_raise(tmp_path, capsys):
    """Pull failure (offline / network) logs to stderr but doesn't raise."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"

    def fake_run(args, **kwargs):
        class R: returncode = 1; stderr = "could not resolve host"; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        ensure_brain_repo_fresh(vault, max_age_minutes=5)  # MUST NOT RAISE

    err = capsys.readouterr().err
    assert "pull" in err.lower() or "fail" in err.lower()
    assert not state.exists()  # state NOT updated on failure


def test_pull_failure_with_corrupt_state_still_works(tmp_path, capsys):
    """If state file is malformed, fall through to pull (don't crash)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    state.write_text("{not valid json")
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert any("pull" in " ".join(args) for args in runs)

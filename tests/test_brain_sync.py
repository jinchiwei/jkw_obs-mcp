"""Tests for brain_sync.sync.ensure_brain_repo_fresh."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

from jkw_obs_mcp.brain_sync.sync import ensure_brain_repo_fresh


def _fake_run_factory(*, pre_sha="abc123", post_sha="def456", pull_rc=0, pull_err=""):
    """Build a fake subprocess.run that handles git rev-parse + pull.

    Returns (fake_run_callable, runs_list). The callable yields pre_sha for the
    first rev-parse, post_sha for the second; pull_rc + pull_err for the pull.
    Other commands return rc=0.
    """
    runs = []
    rev_calls = {"count": 0}

    def fake_run(args, **kwargs):
        runs.append(args)
        if "rev-parse" in args:
            rev_calls["count"] += 1
            sha = pre_sha if rev_calls["count"] == 1 else post_sha
            class R: returncode = 0; stderr = ""; stdout = sha + "\n"
            return R()
        if "pull" in args:
            class R:
                returncode = pull_rc
                stderr = pull_err
                stdout = ""
            return R()
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    return fake_run, runs


def test_pulls_when_no_state_file(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    fake_run, runs = _fake_run_factory(pre_sha="aaa", post_sha="bbb")

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is True  # HEAD moved aaa -> bbb
    assert any("pull" in args for args in runs)
    assert state.is_file()


def test_skips_when_cache_fresh(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    one_min_ago = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    state.write_text(json.dumps({"last_pull_at": one_min_ago.isoformat()}))
    fake_run, runs = _fake_run_factory()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is False  # cache hit, no pull
    assert runs == []


def test_pulls_when_cache_stale(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    ten_min_ago = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10)
    state.write_text(json.dumps({"last_pull_at": ten_min_ago.isoformat()}))
    fake_run, runs = _fake_run_factory(pre_sha="aaa", post_sha="bbb")

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is True
    assert any("pull" in args for args in runs)


def test_max_age_zero_always_pulls(tmp_path):
    """max_age_minutes=0 means 'always pull, ignore cache'."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    just_now = dt.datetime.now(dt.UTC)
    state.write_text(json.dumps({"last_pull_at": just_now.isoformat()}))
    fake_run, runs = _fake_run_factory(pre_sha="aaa", post_sha="bbb")

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=0)

    assert result is True
    assert any("pull" in args for args in runs)


def test_pull_failure_does_not_raise(tmp_path, capsys):
    """Pull failure (offline / network) logs to stderr but doesn't raise. Returns False."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    fake_run, _ = _fake_run_factory(pull_rc=1, pull_err="could not resolve host")

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is False
    err = capsys.readouterr().err
    assert "pull" in err.lower() or "fail" in err.lower()
    assert not state.exists()


def test_pull_failure_with_corrupt_state_still_works(tmp_path):
    """If state file is malformed, fall through to pull (don't crash)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    state.write_text("{not valid json")
    fake_run, runs = _fake_run_factory(pre_sha="aaa", post_sha="bbb")

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is True
    assert any("pull" in args for args in runs)


def test_returns_false_when_pull_succeeds_but_head_unchanged(tmp_path):
    """Pull ran but HEAD didn't move (already up to date) → return False."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    fake_run, runs = _fake_run_factory(pre_sha="abc", post_sha="abc")  # same SHA

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is False  # pull happened but no new content
    assert any("pull" in args for args in runs)
    assert state.is_file()  # state IS updated (pull was successful even if no-op)


def test_rev_parse_failure_returns_false(tmp_path, capsys):
    """If `git rev-parse HEAD` fails (e.g., not a git repo), gracefully return False."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"

    def fake_run(args, **kwargs):
        if "rev-parse" in args:
            class R: returncode = 1; stderr = "not a git repository"; stdout = ""
            return R()
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is False  # graceful — never raise

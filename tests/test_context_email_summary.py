"""Tests for load_recent_email_summary()."""

from __future__ import annotations

import datetime as dt

from jkw_obs_mcp.context.email_summary import load_recent_email_summary


def test_returns_today_summary_when_present(tmp_path):
    vault = tmp_path / "vault"
    today = dt.date.today().isoformat()
    email_dir = vault / "kb" / "dreamingmachine" / "email"
    email_dir.mkdir(parents=True)
    (email_dir / f"{today}.md").write_text("# Email Pulse\n\nstub content")

    out = load_recent_email_summary(vault, machine_id="dreamingmachine")
    assert out is not None
    assert "stub content" in out


def test_returns_none_when_missing(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    assert load_recent_email_summary(vault, machine_id="dreamingmachine") is None


def test_returns_none_when_email_dir_exists_but_no_file(tmp_path):
    vault = tmp_path / "vault"
    (vault / "kb" / "dreamingmachine" / "email").mkdir(parents=True)
    assert load_recent_email_summary(vault, machine_id="dreamingmachine") is None


def test_returns_none_when_only_old_summaries_present(tmp_path):
    """Yesterday's summary is stale — daily review wants today's freshness only."""
    vault = tmp_path / "vault"
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    email_dir = vault / "kb" / "dreamingmachine" / "email"
    email_dir.mkdir(parents=True)
    (email_dir / f"{yesterday}.md").write_text("yesterday's pulse")

    assert load_recent_email_summary(vault, machine_id="dreamingmachine") is None

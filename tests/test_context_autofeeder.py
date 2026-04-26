"""AutofeederContext tests."""

import datetime as dt
from pathlib import Path

import pytest

from jkw_obs_mcp.context.autofeeder import load_recent_autofeeder_digests


def test_returns_recent_digests(tmp_path):
    """Files matching <vault>/臥龍/Autofeeder/<profile>/<YYYY-MM-DD>.md are loaded."""
    vault = tmp_path / "vault"
    af_root = vault / "臥龍" / "Autofeeder"
    today_str = dt.date.today().isoformat()

    # One profile, one recent digest
    (af_root / "meningioma").mkdir(parents=True)
    (af_root / "meningioma" / f"{today_str}.md").write_text(
        "# meningioma 2026-04-25\n\n## TL;DR\n- key paper found"
    )

    # Old digest — should be skipped
    old_date = (dt.date.today() - dt.timedelta(days=10)).isoformat()
    (af_root / "alzheimers").mkdir(parents=True)
    (af_root / "alzheimers" / f"{old_date}.md").write_text("OLD content")

    digests = load_recent_autofeeder_digests(vault, days=2)

    assert len(digests) == 1
    assert digests[0].profile == "meningioma"
    assert "key paper found" in digests[0].content


def test_returns_empty_when_no_digests(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    assert load_recent_autofeeder_digests(vault, days=7) == []


def test_handles_missing_autofeeder_root(tmp_path):
    """Vault doesn't have 臥龍/Autofeeder yet — returns []."""
    vault = tmp_path / "vault"
    (vault / "Admin").mkdir(parents=True)
    assert load_recent_autofeeder_digests(vault, days=7) == []

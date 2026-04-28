"""Tests for installer.gmail_oauth step."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from jkw_obs_mcp.installer.gmail_oauth import gmail_oauth_setup


def test_skips_when_token_already_cached(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "gmail-token.json").write_text('{"token": "x"}')

    status = gmail_oauth_setup(config_dir=cfg)

    assert status["skipped"] is True
    assert "token" in status["reason"].lower()


def test_returns_walkthrough_when_client_secret_missing(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    # No client_secret.json, no gmail-token.json

    status = gmail_oauth_setup(config_dir=cfg)

    assert status["skipped"] is True
    assert "client_secret" in status["reason"].lower()
    assert "google" in status["walkthrough"].lower()
    assert "console.cloud.google.com" in status["walkthrough"]


def test_triggers_oauth_when_client_secret_present_and_no_token(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "google-client-secret.json").write_text('{"installed": {"client_id": "x"}}')

    fake_creds = MagicMock()
    fake_adapter = MagicMock()
    fake_adapter._ensure_credentials.return_value = fake_creds

    with patch(
        "jkw_obs_mcp.adapter.gmail.GmailAdapter",
        return_value=fake_adapter,
    ):
        status = gmail_oauth_setup(config_dir=cfg)

    assert status["skipped"] is False
    fake_adapter._ensure_credentials.assert_called_once()


def test_returns_failure_when_oauth_flow_returns_none(tmp_path):
    """If GmailAdapter._ensure_credentials returns None (user cancelled, etc.),
    the installer records the failure but doesn't crash."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "google-client-secret.json").write_text('{"installed": {"client_id": "x"}}')

    fake_adapter = MagicMock()
    fake_adapter._ensure_credentials.return_value = None

    with patch(
        "jkw_obs_mcp.adapter.gmail.GmailAdapter",
        return_value=fake_adapter,
    ):
        status = gmail_oauth_setup(config_dir=cfg)

    assert status["skipped"] is True
    assert "fail" in status["reason"].lower() or "oauth" in status["reason"].lower()

"""GmailAdapter credential cache + refresh tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jkw_obs_mcp.adapter.gmail import GmailAdapter


def test_load_credentials_returns_none_when_token_missing(tmp_path):
    adapter = GmailAdapter(
        client_secret_path=tmp_path / "client_secret.json",
        token_path=tmp_path / "token.json",
    )
    assert adapter._load_credentials() is None


def test_load_credentials_returns_credentials_when_present(tmp_path):
    """A valid token.json returns a Credentials instance via from_authorized_user_info."""
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps({
        "token": "abc",
        "refresh_token": "def",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake-client-id",
        "client_secret": "fake-client-secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
    }))

    adapter = GmailAdapter(
        client_secret_path=tmp_path / "client_secret.json",
        token_path=token_path,
    )
    creds = adapter._load_credentials()
    assert creds is not None
    assert creds.token == "abc"
    assert creds.refresh_token == "def"


def test_save_credentials_writes_json_with_mode_600(tmp_path):
    adapter = GmailAdapter(
        client_secret_path=tmp_path / "client_secret.json",
        token_path=tmp_path / "token.json",
    )

    fake_creds = MagicMock()
    fake_creds.to_json.return_value = '{"token": "xyz"}'

    adapter._save_credentials(fake_creds)

    token_path = tmp_path / "token.json"
    assert token_path.is_file()
    assert token_path.read_text() == '{"token": "xyz"}'
    # Confirm restrictive permissions (mode 600 = 0o600 = u=rw)
    mode = token_path.stat().st_mode & 0o777
    assert mode == 0o600


def test_credentials_refresh_when_expired(tmp_path):
    """If creds.expired and refresh_token present, adapter calls creds.refresh()."""
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps({
        "token": "stale",
        "refresh_token": "rt",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "id",
        "client_secret": "secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
    }))

    fake_creds = MagicMock()
    fake_creds.expired = True
    fake_creds.refresh_token = "rt"
    fake_creds.valid = True
    fake_creds.to_json.return_value = '{"token": "fresh"}'

    with patch(
        "jkw_obs_mcp.adapter.gmail.Credentials.from_authorized_user_info",
        return_value=fake_creds,
    ):
        adapter = GmailAdapter(
            client_secret_path=tmp_path / "client_secret.json",
            token_path=token_path,
        )
        creds = adapter._ensure_credentials()

    fake_creds.refresh.assert_called_once()
    assert creds is fake_creds


def test_ensure_credentials_returns_none_when_no_refresh_path_available(tmp_path):
    """No token, no client_secret, no interactive flow available — return None.

    The compiler treats None as 'graceful degrade, return empty result.'
    """
    adapter = GmailAdapter(
        client_secret_path=tmp_path / "client_secret.json",
        token_path=tmp_path / "token.json",
        _allow_interactive=False,
    )
    assert adapter._ensure_credentials() is None


def test_ensure_credentials_runs_interactive_flow_when_token_missing(tmp_path):
    """No token, but client_secret present and interactive allowed → bootstrap OAuth."""
    client_secret_path = tmp_path / "client_secret.json"
    client_secret_path.write_text('{"installed": {"client_id": "x"}}')
    token_path = tmp_path / "token.json"

    fake_creds = MagicMock()
    fake_creds.to_json.return_value = '{"token": "fresh-from-bootstrap"}'

    fake_flow = MagicMock()
    fake_flow.run_local_server.return_value = fake_creds

    with patch(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        return_value=fake_flow,
    ):
        adapter = GmailAdapter(
            client_secret_path=client_secret_path,
            token_path=token_path,
            _allow_interactive=True,
        )
        creds = adapter._ensure_credentials()

    assert creds is fake_creds
    fake_flow.run_local_server.assert_called_once()
    # Token was persisted to disk
    assert token_path.is_file()
    assert token_path.read_text() == '{"token": "fresh-from-bootstrap"}'
    assert (token_path.stat().st_mode & 0o777) == 0o600


def test_save_credentials_atomic_replace_no_644_window(tmp_path):
    """Regression test: token file must be 600 the moment it appears at the target path.

    Enforced by writing to a tempfile chmod'd 600 first, then os.replace().
    No leftover temp files should remain.
    """
    adapter = GmailAdapter(
        client_secret_path=tmp_path / "client_secret.json",
        token_path=tmp_path / "token.json",
    )

    fake_creds = MagicMock()
    fake_creds.to_json.return_value = '{"token": "secret-refresh-token"}'

    adapter._save_credentials(fake_creds)

    token_path = tmp_path / "token.json"
    assert token_path.is_file()
    assert (token_path.stat().st_mode & 0o777) == 0o600
    # No leftover temp files in the directory
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".token-")]
    assert leftovers == []

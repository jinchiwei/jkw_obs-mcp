"""GmailAdapter.fetch_recent_threads tests with mocked Google client."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

from jkw_obs_mcp.adapter.gmail import EmailMessage, EmailThread, GmailAdapter


def _make_adapter(tmp_path):
    """A GmailAdapter with no real OAuth — _ensure_credentials patched per test."""
    return GmailAdapter(
        client_secret_path=tmp_path / "secret.json",
        token_path=tmp_path / "token.json",
        _allow_interactive=False,
    )


def _fake_thread_payload(thread_id: str, messages: list[dict]) -> dict:
    """Shape that service.users().threads().get(...).execute() returns."""
    return {"id": thread_id, "messages": messages}


def _fake_message(
    msg_id: str, sender: str, recipient: str, subject: str, body: str = "Hi"
) -> dict:
    return {
        "id": msg_id,
        "threadId": "t1",
        "labelIds": ["INBOX", "CATEGORY_PRIMARY"],
        "internalDate": "1714060800000",  # ms since epoch
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": recipient},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Mon, 27 Apr 2026 09:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {
                "data": _b64url(body),
                "size": len(body),
            },
        },
        "snippet": body[:80],
    }


def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii")


def test_fetch_returns_empty_when_no_credentials(tmp_path):
    """Adapter without credentials degrades to []."""
    adapter = _make_adapter(tmp_path)
    # _ensure_credentials returns None (no token, no client secret, no interactive)
    threads = adapter.fetch_recent_threads(query="in:inbox", max_threads=10)
    assert threads == []


def test_fetch_returns_empty_when_api_raises(tmp_path):
    """Any Google client error -> returns [], never raises."""
    adapter = _make_adapter(tmp_path)
    fake_creds = MagicMock(valid=True)

    fake_service = MagicMock()
    fake_service.users().threads().list().execute.side_effect = Exception("rate limit")

    with patch.object(adapter, "_ensure_credentials", return_value=fake_creds), \
         patch("jkw_obs_mcp.adapter.gmail.build", return_value=fake_service):
        threads = adapter.fetch_recent_threads(query="in:inbox", max_threads=10)

    assert threads == []


def test_fetch_returns_empty_when_no_threads_match(tmp_path):
    adapter = _make_adapter(tmp_path)
    fake_creds = MagicMock(valid=True)

    fake_service = MagicMock()
    fake_service.users().threads().list.return_value.execute.return_value = {}

    with patch.object(adapter, "_ensure_credentials", return_value=fake_creds), \
         patch("jkw_obs_mcp.adapter.gmail.build", return_value=fake_service):
        threads = adapter.fetch_recent_threads(query="in:inbox", max_threads=10)

    assert threads == []


def test_fetch_groups_messages_into_threads(tmp_path):
    """Thread list returns IDs; each thread is fetched in detail."""
    adapter = _make_adapter(tmp_path)
    fake_creds = MagicMock(valid=True)

    fake_service = MagicMock()

    # threads().list() returns a list of {id} stubs
    fake_service.users().threads().list.return_value.execute.return_value = {
        "threads": [{"id": "t1"}, {"id": "t2"}]
    }

    # threads().get() returns full thread payloads
    thread_t1 = _fake_thread_payload("t1", [
        _fake_message("m1", "alice@example.com", "me@example.com", "Hello", "Body 1"),
        _fake_message("m2", "me@example.com", "alice@example.com", "Re: Hello", "Body 2"),
    ])
    thread_t2 = _fake_thread_payload("t2", [
        _fake_message("m3", "bob@example.com", "me@example.com", "Question?"),
    ])

    fake_service.users().threads().get.return_value.execute.side_effect = [thread_t1, thread_t2]

    # Profile lookup returns user's email address
    fake_service.users().getProfile.return_value.execute.return_value = {
        "emailAddress": "me@example.com"
    }

    with patch.object(adapter, "_ensure_credentials", return_value=fake_creds), \
         patch("jkw_obs_mcp.adapter.gmail.build", return_value=fake_service):
        threads = adapter.fetch_recent_threads(query="in:inbox", max_threads=10)

    assert len(threads) == 2
    assert isinstance(threads[0], EmailThread)
    assert isinstance(threads[0].messages[0], EmailMessage)
    assert threads[0].thread_id == "t1"
    assert threads[0].subject == "Hello"
    assert len(threads[0].messages) == 2
    assert threads[0].messages[0].sender == "alice@example.com"
    # is_from_self is the only computed field — verify it's set correctly
    assert threads[0].messages[0].is_from_self is False  # alice is not me
    assert threads[0].messages[1].is_from_self is True   # me@example.com is me
    assert threads[1].thread_id == "t2"
    assert threads[1].subject == "Question?"


def test_fetch_caches_user_email_address(tmp_path):
    """getProfile is called exactly once even across multiple fetches."""
    adapter = _make_adapter(tmp_path)
    fake_creds = MagicMock(valid=True)

    fake_service = MagicMock()
    fake_service.users().threads().list.return_value.execute.return_value = {}
    fake_service.users().getProfile.return_value.execute.return_value = {
        "emailAddress": "me@example.com"
    }

    with patch.object(adapter, "_ensure_credentials", return_value=fake_creds), \
         patch("jkw_obs_mcp.adapter.gmail.build", return_value=fake_service):
        adapter.fetch_recent_threads(query="in:inbox", max_threads=10)
        adapter.fetch_recent_threads(query="in:inbox", max_threads=10)

    assert adapter._cached_user_email == "me@example.com"
    # Behavioral check: getProfile().execute() called exactly once across 2 fetches
    assert fake_service.users().getProfile().execute.call_count == 1


def test_fetch_caches_empty_string_when_profile_missing_email(tmp_path):
    """If getProfile response lacks emailAddress, cache the empty-string sentinel
    so subsequent fetches don't loop back into getProfile every call."""
    adapter = _make_adapter(tmp_path)
    fake_creds = MagicMock(valid=True)

    fake_service = MagicMock()
    fake_service.users().threads().list.return_value.execute.return_value = {}
    # Unexpected response shape — no emailAddress key
    fake_service.users().getProfile.return_value.execute.return_value = {}

    with patch.object(adapter, "_ensure_credentials", return_value=fake_creds), \
         patch("jkw_obs_mcp.adapter.gmail.build", return_value=fake_service):
        adapter.fetch_recent_threads(query="in:inbox", max_threads=10)
        adapter.fetch_recent_threads(query="in:inbox", max_threads=10)

    # Sentinel value, not None — prevents the "is None → re-fetch" loop
    assert adapter._cached_user_email == ""
    assert fake_service.users().getProfile().execute.call_count == 1

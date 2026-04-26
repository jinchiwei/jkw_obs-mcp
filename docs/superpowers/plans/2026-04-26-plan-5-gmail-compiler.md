# Plan 5: Gmail Compiler + Daily Review Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Pull recent inbox via Gmail API (read-only OAuth), filter using Gmail's own `category:primary` classification, summarize threads via Anthropic into `kb/<machine>/email/<date>.md`, and bundle into `generate_daily_review` so the daily review's "Open threads" section can surface emails waiting on Jin's reply.

**Architecture:** `GmailAdapter` (OAuth credential cache + thread fetch) → `_classify_thread_state` (pure function, returns enum) → `EmailCompiler` (renders Jinja prompt, calls Anthropic, writes via `VaultAdapter.write_kb_note`). New context loader `load_recent_email_summary` reads today's summary file. `DailyReviewGenerator.generate()` invokes `EmailCompiler.compile()` first (wrapped in try/except for graceful degradation), then reads its output as a prompt input. `kb/<machine>/email/` is excluded from the `obsidian-git` mirror so email content never reaches cluster infrastructure.

**Tech Stack:** existing deps (anthropic[bedrock], jinja2). Plus `google-api-python-client`, `google-auth-oauthlib`, `google-auth`, `html2text` under a new `[gmail]` optional extra.

**Realistic effort: ~1 week** (11 tasks).

---

## File Structure

```
jkw_obs-mcp/
├── pyproject.toml                                Modify: add [gmail] optional extra
├── src/jkw_obs_mcp/
│   ├── adapter/
│   │   └── gmail.py                              GmailAdapter — OAuth + thread fetch
│   ├── compilers/
│   │   └── email_compiler.py                     EmailCompiler — Jinja + Anthropic
│   ├── context/
│   │   └── email_summary.py                      load_recent_email_summary
│   ├── generation/prompts/
│   │   ├── email_summary.j2                      Jinja template (thread-grouped)
│   │   └── daily_review.j2                       Modify: add "Email pulse" section + INPUTS hook
│   ├── generators/
│   │   └── daily_review.py                       Modify: invoke EmailCompiler, read summary
│   └── mcp/server.py                             Modify: register compile_email tool, wire EmailCompiler
└── tests/
    ├── test_gmail_adapter_token.py               OAuth credential cache + refresh
    ├── test_gmail_adapter_fetch.py               fetch_recent_threads with mocked Google client
    ├── test_gmail_body_extract.py                MIME body extraction
    ├── test_email_thread_state.py                Thread-state classifier (4 cases)
    ├── test_email_compiler.py                    EmailCompiler (mocked everything)
    ├── test_context_email_summary.py             load_recent_email_summary
    ├── test_mcp_compile_email_tool.py            compile_email tool surface + dispatch
    └── test_generator_daily_review.py            Modify: email integration tests
```

---

## Task 1: pyproject.toml — `[gmail]` optional extra

**Files:** Modify `pyproject.toml`.

This task is pure infrastructure: add the optional dep group so `pip install -e ".[gmail]"` resolves Google's API client + html2text. No code or test changes yet.

- [ ] **Step 1: Read current `pyproject.toml`**

Run: `cat pyproject.toml`

Confirm the existing `[project.optional-dependencies]` block looks like:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]
mac = [
    "pyobjc-framework-EventKit>=12.0",
]
```

- [ ] **Step 2: Add `gmail` extra**

Edit `pyproject.toml` to add the `gmail` extra after `mac`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]
mac = [
    "pyobjc-framework-EventKit>=12.0",
]
gmail = [
    "google-api-python-client>=2.100",
    "google-auth-oauthlib>=1.2",
    "google-auth>=2.30",
    "html2text>=2024.2.26",
]
```

- [ ] **Step 3: Activate env and install the new extra**

Run:
```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream
pip install -e ".[gmail]"
```

Expected: pip resolves all four packages, no conflicts.

- [ ] **Step 4: Smoke-test the imports**

Run:
```bash
python -c "from googleapiclient.discovery import build; from google.oauth2.credentials import Credentials; from google_auth_oauthlib.flow import InstalledAppFlow; import html2text; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 5: Run the existing test suite to confirm no regressions**

Run: `pytest tests/ -q`
Expected: 97 passed (Plan 4's count).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "chore: add [gmail] optional extra (google-api-python-client, html2text)"
```

---

## Task 2: GmailAdapter — credential cache and refresh

**Files:** Create `src/jkw_obs_mcp/adapter/gmail.py`, `tests/test_gmail_adapter_token.py`.

This task implements just the credential loading/saving/refreshing surface. Thread fetch comes in Task 3.

- [ ] **Step 1: Failing tests at `tests/test_gmail_adapter_token.py`**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gmail_adapter_token.py -v`
Expected: ModuleNotFoundError (jkw_obs_mcp.adapter.gmail doesn't exist).

- [ ] **Step 3: Write `src/jkw_obs_mcp/adapter/gmail.py` (token-only surface)**

```python
"""GmailAdapter — read-only Gmail access via Google's API client.

This module handles two concerns: (1) credential cache + refresh, and
(2) thread fetch. This file currently implements (1); thread fetch lands
in the next plan task.

Token storage: ~/.config/jkw-obs-mcp/gmail-token.json (mode 600).
Client secret: ~/.config/jkw-obs-mcp/google-client-secret.json (mode 600).
Both are gitignored and the user creates them via the Google Cloud
Console OAuth desktop flow (covered in Plan 6 installer).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailAdapter:
    """Owns the OAuth credential lifecycle and (later) thread fetching.

    Construction does no I/O. Credential load happens on first call to
    _ensure_credentials(). That makes the adapter safe to instantiate at
    MCP server startup even if the user has not yet bootstrapped Gmail.
    """

    def __init__(
        self,
        *,
        client_secret_path: Path,
        token_path: Path,
        _allow_interactive: bool = True,
    ) -> None:
        self.client_secret_path = client_secret_path
        self.token_path = token_path
        self._allow_interactive = _allow_interactive

    def _load_credentials(self) -> Credentials | None:
        """Load credentials from token_path, or return None if missing/invalid."""
        if not self.token_path.is_file():
            return None
        try:
            data = json.loads(self.token_path.read_text())
            return Credentials.from_authorized_user_info(data, SCOPES)
        except (json.JSONDecodeError, ValueError):
            return None

    def _save_credentials(self, creds: Credentials) -> None:
        """Persist credentials.to_json() with mode 600."""
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(creds.to_json())
        os.chmod(self.token_path, 0o600)

    def _ensure_credentials(self) -> Credentials | None:
        """Return valid Credentials or None.

        Resolution order:
          1. Load cached token. If valid, return.
          2. If expired but has refresh_token, refresh and return.
          3. If interactive allowed and client_secret present, run OAuth flow.
          4. Otherwise return None (caller treats as 'no Gmail access today').
        """
        creds = self._load_credentials()
        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save_credentials(creds)
            return creds

        if self._allow_interactive and self.client_secret_path.is_file():
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.client_secret_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
            self._save_credentials(creds)
            return creds

        return None
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `pytest tests/test_gmail_adapter_token.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run full suite to confirm no regressions**

Run: `pytest tests/ -q`
Expected: 102 passed (97 + 5).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/adapter/gmail.py tests/test_gmail_adapter_token.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: GmailAdapter — OAuth credential cache + refresh"
```

---

## Task 3: GmailAdapter — fetch_recent_threads

**Files:** Modify `src/jkw_obs_mcp/adapter/gmail.py`, create `tests/test_gmail_adapter_fetch.py`.

Add the thread-fetch method. This wraps the Google API and returns a list of strongly-typed `EmailThread` objects so downstream code (classifier, compiler) doesn't have to think about Gmail JSON shape.

- [ ] **Step 1: Failing tests at `tests/test_gmail_adapter_fetch.py`**

```python
"""GmailAdapter.fetch_recent_threads tests with mocked Google client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

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
    import base64
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii")


def test_fetch_returns_empty_when_no_credentials(tmp_path):
    """Adapter without credentials degrades to []."""
    adapter = _make_adapter(tmp_path)
    # _ensure_credentials returns None (no token, no client secret, no interactive)
    threads = adapter.fetch_recent_threads(query="in:inbox", max_threads=10)
    assert threads == []


def test_fetch_returns_empty_when_api_raises(tmp_path):
    """Any Google client error → returns [], never raises."""
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
    assert threads[0].thread_id == "t1"
    assert threads[0].subject == "Hello"
    assert len(threads[0].messages) == 2
    assert threads[0].messages[0].sender == "alice@example.com"
    assert threads[1].thread_id == "t2"
    assert threads[1].subject == "Question?"


def test_fetch_caches_user_email_address(tmp_path):
    """getProfile is called once even across multiple fetches."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gmail_adapter_fetch.py -v`
Expected: ImportError (`EmailMessage`, `EmailThread`, and `fetch_recent_threads` don't exist yet).

- [ ] **Step 3: Extend `src/jkw_obs_mcp/adapter/gmail.py`**

Add at top of file (after `SCOPES`):

```python
import base64
from dataclasses import dataclass

from googleapiclient.discovery import build
```

Add data classes before the `GmailAdapter` class:

```python
@dataclass(frozen=True)
class EmailMessage:
    """One message in a thread, flattened."""

    message_id: str
    sender: str           # raw "Name <email>" or just "email"
    recipient: str
    subject: str
    date: str             # raw RFC2822 string from headers
    body: str             # extracted plain text or stripped HTML
    is_from_self: bool    # set by adapter using getProfile() email


@dataclass(frozen=True)
class EmailThread:
    """A Gmail thread with its messages in chronological order."""

    thread_id: str
    subject: str
    messages: list[EmailMessage]
```

Add a `_cached_user_email` attribute initialization in `__init__`:

```python
    def __init__(
        self,
        *,
        client_secret_path: Path,
        token_path: Path,
        _allow_interactive: bool = True,
    ) -> None:
        self.client_secret_path = client_secret_path
        self.token_path = token_path
        self._allow_interactive = _allow_interactive
        self._cached_user_email: str | None = None
```

Add the `fetch_recent_threads` method on `GmailAdapter`:

```python
    def fetch_recent_threads(
        self, *, query: str, max_threads: int = 50
    ) -> list[EmailThread]:
        """Return parsed threads matching `query`. Returns [] on any failure."""
        creds = self._ensure_credentials()
        if creds is None:
            return []

        try:
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)

            # Cache the user's own email address (used to mark is_from_self)
            if self._cached_user_email is None:
                profile = service.users().getProfile(userId="me").execute()
                self._cached_user_email = profile.get("emailAddress")

            list_resp = (
                service.users()
                .threads()
                .list(userId="me", q=query, maxResults=max_threads)
                .execute()
            )
            thread_stubs = list_resp.get("threads", [])

            results: list[EmailThread] = []
            for stub in thread_stubs:
                detail = (
                    service.users()
                    .threads()
                    .get(userId="me", id=stub["id"], format="full")
                    .execute()
                )
                results.append(self._parse_thread(detail))
            return results
        except Exception:
            # Graceful degrade — log via stderr in real ops, but never raise.
            # Daily review's email section becomes empty for this run.
            return []

    def _parse_thread(self, detail: dict) -> EmailThread:
        messages = [self._parse_message(m) for m in detail.get("messages", [])]
        subject = messages[0].subject if messages else "(no subject)"
        return EmailThread(
            thread_id=detail["id"],
            subject=subject,
            messages=messages,
        )

    def _parse_message(self, msg: dict) -> EmailMessage:
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        sender = headers.get("From", "")
        is_from_self = bool(
            self._cached_user_email and self._cached_user_email in sender
        )
        body = _extract_message_body(msg.get("payload", {}))
        return EmailMessage(
            message_id=msg.get("id", ""),
            sender=sender,
            recipient=headers.get("To", ""),
            subject=headers.get("Subject", "(no subject)"),
            date=headers.get("Date", ""),
            body=body,
            is_from_self=is_from_self,
        )


def _extract_message_body(payload: dict) -> str:
    """Stub — full implementation lands in Task 4 (body extraction)."""
    # Minimal: try the top-level body if it's text/plain.
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")
    if mime == "text/plain" and body_data:
        try:
            return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        except Exception:
            return ""
    return ""
```

The stub `_extract_message_body` handles only the simple `text/plain` case. Task 4 replaces it with multipart-aware extraction. This is intentional — keeps Task 3 testable with the simple fixture before we add MIME-walking complexity.

- [ ] **Step 4: Run tests to verify all pass**

Run: `pytest tests/test_gmail_adapter_fetch.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 107 passed (102 + 5).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/adapter/gmail.py tests/test_gmail_adapter_fetch.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: GmailAdapter.fetch_recent_threads + EmailThread/EmailMessage dataclasses"
```

---

## Task 4: MIME body extraction

**Files:** Modify `src/jkw_obs_mcp/adapter/gmail.py` (replace `_extract_message_body`), create `tests/test_gmail_body_extract.py`.

Replace the stub body extractor with a real implementation that walks multipart MIME, prefers `text/plain`, falls back to HTML-stripped `text/html`, and handles nested multipart/alternative + multipart/mixed.

- [ ] **Step 1: Failing tests at `tests/test_gmail_body_extract.py`**

```python
"""MIME body extraction tests."""

from __future__ import annotations

import base64

from jkw_obs_mcp.adapter.gmail import _extract_message_body


def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii")


def test_extracts_text_plain_when_present():
    payload = {
        "mimeType": "text/plain",
        "body": {"data": _b64url("Hello world")},
    }
    assert _extract_message_body(payload) == "Hello world"


def test_returns_empty_when_no_body_data():
    payload = {"mimeType": "text/plain", "body": {}}
    assert _extract_message_body(payload) == ""


def test_strips_html_when_no_text_plain():
    html = "<p>Hello <b>world</b></p>"
    payload = {
        "mimeType": "text/html",
        "body": {"data": _b64url(html)},
    }
    out = _extract_message_body(payload)
    assert "Hello" in out
    assert "world" in out
    assert "<p>" not in out
    assert "<b>" not in out


def test_handles_multipart_alternative_prefers_text_plain():
    """multipart/alternative with both text/plain and text/html → use text/plain."""
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": _b64url("plain text version")},
            },
            {
                "mimeType": "text/html",
                "body": {"data": _b64url("<p>html version</p>")},
            },
        ],
    }
    assert _extract_message_body(payload) == "plain text version"


def test_handles_multipart_alternative_fallback_to_html():
    """multipart/alternative with only text/html → use it (stripped)."""
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/html",
                "body": {"data": _b64url("<p>only html</p>")},
            },
        ],
    }
    out = _extract_message_body(payload)
    assert "only html" in out
    assert "<p>" not in out


def test_handles_nested_multipart():
    """multipart/mixed wrapping multipart/alternative wrapping text/plain."""
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": _b64url("nested plain")},
                    },
                ],
            },
            {
                "mimeType": "application/pdf",
                "filename": "attachment.pdf",
                "body": {"attachmentId": "abc"},
            },
        ],
    }
    assert _extract_message_body(payload) == "nested plain"


def test_returns_empty_string_when_no_text_part_anywhere():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "application/pdf",
                "body": {"attachmentId": "abc"},
            },
        ],
    }
    assert _extract_message_body(payload) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gmail_body_extract.py -v`
Expected: most pass with the stub for `text/plain`, but `test_strips_html_when_no_text_plain`, `test_handles_multipart_*`, and `test_handles_nested_multipart` fail because the stub only handles top-level `text/plain`.

- [ ] **Step 3: Replace `_extract_message_body` in `src/jkw_obs_mcp/adapter/gmail.py`**

Delete the stub and replace with:

```python
def _extract_message_body(payload: dict) -> str:
    """Walk MIME parts to find a usable body.

    Preference order:
      1. text/plain (top-level or inside multipart)
      2. text/html (stripped to plain text via html2text)
      3. ""
    """
    plain = _find_part_by_mime(payload, "text/plain")
    if plain is not None:
        return plain

    html = _find_part_by_mime(payload, "text/html")
    if html is not None:
        try:
            import html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.body_width = 0  # don't wrap
            return h.handle(html).strip()
        except ImportError:
            # html2text missing — strip tags via a crude regex fallback
            import re
            return re.sub(r"<[^>]+>", " ", html).strip()

    return ""


def _find_part_by_mime(payload: dict, target_mime: str) -> str | None:
    """Recursively search for a part with `mimeType == target_mime`. Returns decoded body."""
    if payload.get("mimeType") == target_mime:
        data = payload.get("body", {}).get("data")
        if data:
            try:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            except Exception:
                return None

    for part in payload.get("parts", []):
        found = _find_part_by_mime(part, target_mime)
        if found is not None:
            return found

    return None
```

- [ ] **Step 4: Run body extraction tests**

Run: `pytest tests/test_gmail_body_extract.py -v`
Expected: 7 passed.

- [ ] **Step 5: Re-run Task 3's fetch tests + full suite**

Run: `pytest tests/ -q`
Expected: 114 passed (107 + 7).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/adapter/gmail.py tests/test_gmail_body_extract.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: MIME body extraction — multipart-aware, html2text fallback"
```

---

## Task 5: Thread-state classifier

**Files:** Create `src/jkw_obs_mcp/compilers/email_state.py`, `tests/test_email_thread_state.py`.

A pure function that takes an `EmailThread` plus a "last seen" timestamp and returns a single state label. Priority order: `WAITING_ON_YOU` > `FIRST_TOUCH` > `RECENT_ACTIVITY`. Threads where the latest message is from self AND there's no new inbound activity get `RECENT_ACTIVITY` only if there was prior new activity, else they're effectively un-classified (caller filters).

- [ ] **Step 1: Failing tests at `tests/test_email_thread_state.py`**

```python
"""Thread-state classifier tests."""

from __future__ import annotations

import datetime as dt

from jkw_obs_mcp.adapter.gmail import EmailMessage, EmailThread
from jkw_obs_mcp.compilers.email_state import ThreadState, classify_thread_state


def _msg(sender: str, is_from_self: bool, when: dt.datetime, body: str = "hi") -> EmailMessage:
    return EmailMessage(
        message_id=f"m-{when.timestamp()}",
        sender=sender,
        recipient="me@example.com",
        subject="(test)",
        date=when.strftime("%a, %d %b %Y %H:%M:%S +0000"),
        body=body,
        is_from_self=is_from_self,
    )


def _thread(messages: list[EmailMessage]) -> EmailThread:
    return EmailThread(thread_id="t", subject="(test)", messages=messages)


NOW = dt.datetime(2026, 4, 27, 12, 0, 0, tzinfo=dt.UTC)
DAY_AGO = NOW - dt.timedelta(days=1)
WEEK_AGO = NOW - dt.timedelta(days=7)


def test_waiting_on_you_when_last_msg_is_inbound():
    """Thread ends with a message from someone else → WAITING_ON_YOU."""
    thread = _thread([
        _msg("me@example.com", True, WEEK_AGO),
        _msg("alice@example.com", False, DAY_AGO),
    ])
    assert classify_thread_state(thread, now=NOW) == ThreadState.WAITING_ON_YOU


def test_first_touch_when_single_inbound_message_in_window():
    """Brand new thread, single message from outside, recent → FIRST_TOUCH."""
    thread = _thread([
        _msg("alice@example.com", False, DAY_AGO),
    ])
    assert classify_thread_state(thread, now=NOW) == ThreadState.FIRST_TOUCH


def test_recent_activity_when_you_replied_last_but_thread_has_new_inbound():
    """Multi-message thread with new inbound + your reply on top → still RECENT_ACTIVITY.

    (You handled it; nothing pending.)
    """
    thread = _thread([
        _msg("alice@example.com", False, WEEK_AGO),
        _msg("alice@example.com", False, DAY_AGO),
        _msg("me@example.com", True, NOW - dt.timedelta(hours=1)),
    ])
    assert classify_thread_state(thread, now=NOW) == ThreadState.RECENT_ACTIVITY


def test_first_touch_takes_priority_over_recent_activity():
    """Single-message thread that you DID reply to is still RECENT_ACTIVITY (multi-msg).

    But a single inbound message you haven't replied to yet is FIRST_TOUCH.
    """
    thread = _thread([
        _msg("alice@example.com", False, DAY_AGO),
    ])
    # Single inbound, no reply → FIRST_TOUCH (which also implies WAITING_ON_YOU
    # semantics, but the more specific FIRST_TOUCH takes priority)
    assert classify_thread_state(thread, now=NOW) == ThreadState.FIRST_TOUCH


def test_returns_recent_activity_for_multi_message_thread_you_replied_to():
    thread = _thread([
        _msg("alice@example.com", False, WEEK_AGO),
        _msg("me@example.com", True, DAY_AGO),
    ])
    assert classify_thread_state(thread, now=NOW) == ThreadState.RECENT_ACTIVITY


def test_handles_thread_with_only_outbound_messages():
    """Edge case: a thread with only your messages (you wrote, no reply yet)."""
    thread = _thread([
        _msg("me@example.com", True, DAY_AGO),
    ])
    assert classify_thread_state(thread, now=NOW) == ThreadState.RECENT_ACTIVITY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_email_thread_state.py -v`
Expected: ImportError (module doesn't exist yet).

- [ ] **Step 3: Write `src/jkw_obs_mcp/compilers/email_state.py`**

```python
"""Pure-function thread state classifier for the email compiler.

States (single-valued, priority-ordered):
    WAITING_ON_YOU — multi-message thread, last message inbound (not replied to)
    FIRST_TOUCH    — single-message thread, message inbound (new conversation)
    RECENT_ACTIVITY — anything else: multi-message threads where you replied,
                      or threads with only outbound messages

The compiler renders threads grouped by state. WAITING_ON_YOU is highest signal.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum

from jkw_obs_mcp.adapter.gmail import EmailThread


class ThreadState(str, Enum):
    WAITING_ON_YOU = "waiting_on_you"
    FIRST_TOUCH = "first_touch"
    RECENT_ACTIVITY = "recent_activity"


def classify_thread_state(thread: EmailThread, *, now: dt.datetime) -> ThreadState:
    """Bucket a thread into a single state.

    `now` is injectable for tests. Production passes datetime.now(UTC).
    """
    if not thread.messages:
        return ThreadState.RECENT_ACTIVITY

    # Single-message thread, inbound → FIRST_TOUCH
    if len(thread.messages) == 1 and not thread.messages[0].is_from_self:
        return ThreadState.FIRST_TOUCH

    # Multi-message thread where the latest message is inbound → WAITING_ON_YOU
    last = thread.messages[-1]
    if not last.is_from_self:
        return ThreadState.WAITING_ON_YOU

    return ThreadState.RECENT_ACTIVITY
```

Also create `src/jkw_obs_mcp/compilers/__init__.py` if not present (it should exist from Plan 3).

- [ ] **Step 4: Run tests to verify all pass**

Run: `pytest tests/test_email_thread_state.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 120 passed (114 + 6).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/compilers/email_state.py tests/test_email_thread_state.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: thread-state classifier (WAITING_ON_YOU / FIRST_TOUCH / RECENT_ACTIVITY)"
```

---

## Task 6: email_summary.j2 prompt template

**Files:** Create `src/jkw_obs_mcp/generation/prompts/email_summary.j2`.

Static Jinja template — no test, just a file commit. The compiler test in Task 7 verifies the template loads and renders.

- [ ] **Step 1: Write the template**

Create `src/jkw_obs_mcp/generation/prompts/email_summary.j2`:

```
You are summarizing the user's recent email activity for their morning daily-review note.

Today: {{ today }}
Machine: {{ machine_id }}

Compose a structured Obsidian-friendly markdown note. Be concrete, prefer subject lines and sender names over prose. Don't fabricate. If a thread is genuinely low-signal, omit it.

Required structure:

# Email Pulse — {{ today }}

## Waiting on you
{% if waiting_on_you %}
- For each of {{ waiting_on_you|length }} threads, write one bullet containing:
  the subject (bold), the sender's short name, a one-line gist of the latest inbound message, and a concrete one-line "suggested next action."
- When referencing a thread, include the Gmail permalink: `https://mail.google.com/mail/u/0/#inbox/<thread_id>` (substitute the actual thread_id from INPUTS below).
{% else %}
- "Nothing waiting on you right now."
{% endif %}

## New conversations
{% if first_touch %}
- For each of {{ first_touch|length }} new threads, one bullet with the bolded subject, the sender's short name, and a one-line summary of the body.
{% else %}
- "No new conversations."
{% endif %}

## Active threads (FYI)
{% if recent_activity %}
- For each of {{ recent_activity|length }} active threads, one short bullet with the bolded subject and a one-line note on the latest activity (who replied last, what changed).
- Keep this section terse — these are threads you've already engaged with.
{% else %}
- "No other active threads."
{% endif %}

---

INPUTS

{% for thread in waiting_on_you %}
=== WAITING_ON_YOU thread {{ thread.thread_id }} ===
Subject: {{ thread.subject }}
Permalink: https://mail.google.com/mail/u/0/#inbox/{{ thread.thread_id }}
Messages:
{% for msg in thread.messages %}
[{{ msg.date }}] From: {{ msg.sender }}
{{ msg.body[:1500] }}{% if msg.body|length > 1500 %}... [truncated]{% endif %}

{% endfor %}

{% endfor %}

{% for thread in first_touch %}
=== FIRST_TOUCH thread {{ thread.thread_id }} ===
Subject: {{ thread.subject }}
Permalink: https://mail.google.com/mail/u/0/#inbox/{{ thread.thread_id }}
{% for msg in thread.messages %}
[{{ msg.date }}] From: {{ msg.sender }}
{{ msg.body[:1500] }}{% if msg.body|length > 1500 %}... [truncated]{% endif %}

{% endfor %}

{% endfor %}

{% for thread in recent_activity %}
=== RECENT_ACTIVITY thread {{ thread.thread_id }} ===
Subject: {{ thread.subject }}
Permalink: https://mail.google.com/mail/u/0/#inbox/{{ thread.thread_id }}
Most recent: [{{ thread.messages[-1].date }}] From: {{ thread.messages[-1].sender }}
{{ thread.messages[-1].body[:800] }}{% if thread.messages[-1].body|length > 800 %}... [truncated]{% endif %}

{% endfor %}
```

- [ ] **Step 2: Verify the template loads**

Run:
```bash
python -c "
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
prompts = Path('src/jkw_obs_mcp/generation/prompts')
env = Environment(loader=FileSystemLoader(str(prompts)))
t = env.get_template('email_summary.j2')
out = t.render(today='2026-04-27', machine_id='dreamingmachine', waiting_on_you=[], first_touch=[], recent_activity=[])
assert 'Email Pulse — 2026-04-27' in out
print('ok')
"
```
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/jkw_obs_mcp/generation/prompts/email_summary.j2
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: email_summary.j2 — Jinja prompt template (thread-state-grouped)"
```

---

## Task 7: EmailCompiler

**Files:** Create `src/jkw_obs_mcp/compilers/email_compiler.py`, `tests/test_email_compiler.py`.

Composes adapter + classifier + Anthropic + `VaultAdapter.write_kb_note`. Mirrors the `PaperCompiler` / `ClipCompiler` pattern: injectable client (so tests stub Anthropic), template loaded once at construction.

- [ ] **Step 1: Failing tests at `tests/test_email_compiler.py`**

```python
"""EmailCompiler tests with stubbed Gmail + Anthropic."""

from __future__ import annotations

import datetime as dt

import pytest

from jkw_obs_mcp.adapter.gmail import EmailMessage, EmailThread
from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.compilers.email_compiler import EmailCompiler


def _msg(sender: str, is_self: bool, body: str = "hi") -> EmailMessage:
    return EmailMessage(
        message_id=f"m-{sender}-{int(is_self)}",
        sender=sender,
        recipient="me@example.com",
        subject="Hi",
        date="Mon, 27 Apr 2026 09:00:00 +0000",
        body=body,
        is_from_self=is_self,
    )


def _thread(thread_id: str, subject: str, msgs: list[EmailMessage]) -> EmailThread:
    return EmailThread(thread_id=thread_id, subject=subject, messages=msgs)


class StubAnthropic:
    def __init__(self, response: str = "# Email Pulse — 2026-04-27\n\nstub") -> None:
        self.response = response
        self.last_prompt: str | None = None

    def complete(self, *, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        self.last_prompt = prompt
        return self.response


class StubGmail:
    def __init__(self, threads: list[EmailThread]) -> None:
        self.threads = threads
        self.last_query: str | None = None

    def fetch_recent_threads(self, *, query: str, max_threads: int = 50) -> list[EmailThread]:
        self.last_query = query
        return self.threads


@pytest.fixture
def adapter(tmp_vault):
    return VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")


def test_compile_writes_to_kb_email_subdir(adapter, tmp_vault):
    threads = [
        _thread("t1", "Hello", [
            _msg("alice@example.com", False),
            _msg("alice@example.com", False),
        ]),
    ]
    compiler = EmailCompiler(
        gmail=StubGmail(threads),
        client=StubAnthropic("# Email Pulse — 2026-04-27\n\ngenerated"),
        vault_adapter=adapter,
    )

    out_path = compiler.compile()

    assert out_path is not None
    assert out_path.is_file()
    assert "kb/dreamingmachine/email" in str(out_path)
    assert out_path.read_text().startswith("# Email Pulse")


def test_compile_returns_none_when_no_threads(adapter):
    """Empty inbox → no file written, returns None (signals 'no email today')."""
    compiler = EmailCompiler(
        gmail=StubGmail([]),
        client=StubAnthropic(),
        vault_adapter=adapter,
    )
    out_path = compiler.compile()
    assert out_path is None


def test_compile_groups_threads_by_state_in_prompt(adapter):
    """The prompt includes WAITING_ON_YOU + FIRST_TOUCH + RECENT_ACTIVITY sections."""
    waiting = _thread("t1", "Reply needed", [
        _msg("alice@example.com", False),
        _msg("me@example.com", True),
        _msg("alice@example.com", False),
    ])
    first = _thread("t2", "First touch", [
        _msg("bob@example.com", False),
    ])
    recent = _thread("t3", "Wrapped up", [
        _msg("carol@example.com", False),
        _msg("me@example.com", True),
    ])

    client = StubAnthropic()
    compiler = EmailCompiler(
        gmail=StubGmail([waiting, first, recent]),
        client=client,
        vault_adapter=adapter,
    )
    compiler.compile()

    prompt = client.last_prompt
    assert "WAITING_ON_YOU thread t1" in prompt
    assert "FIRST_TOUCH thread t2" in prompt
    assert "RECENT_ACTIVITY thread t3" in prompt


def test_compile_uses_default_query_with_category_primary(adapter):
    gmail = StubGmail([])
    compiler = EmailCompiler(
        gmail=gmail,
        client=StubAnthropic(),
        vault_adapter=adapter,
    )
    compiler.compile()

    assert gmail.last_query is not None
    assert "category:primary" in gmail.last_query


def test_compile_passes_through_when_gmail_returns_empty(adapter):
    """No threads = no API call = None. Caller's daily review degrades gracefully."""
    client = StubAnthropic()
    compiler = EmailCompiler(
        gmail=StubGmail([]),
        client=client,
        vault_adapter=adapter,
    )
    out = compiler.compile()
    assert out is None
    assert client.last_prompt is None  # never invoked Claude
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_email_compiler.py -v`
Expected: ImportError (`EmailCompiler` doesn't exist).

- [ ] **Step 3: Write `src/jkw_obs_mcp/compilers/email_compiler.py`**

```python
"""EmailCompiler: pulls recent threads from Gmail, classifies them, summarizes
them via Anthropic, writes kb/<machine>/email/<today>.md.

Architecture mirrors PaperCompiler / ClipCompiler in this directory: injectable
client + adapter, prompt template loaded once at construction.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from jkw_obs_mcp.adapter.gmail import EmailThread, GmailAdapter
from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.compilers.email_state import ThreadState, classify_thread_state


_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "generation" / "prompts"
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
    keep_trailing_newline=True,
)

# Gmail's primary tab + recent window. Promotions / Updates / Forums / Social
# are excluded automatically by category:primary.
_DEFAULT_QUERY = "in:inbox category:primary newer_than:2d"


class EmailCompiler:
    """Composes Gmail adapter + thread classifier + Anthropic into kb/email/<today>.md."""

    def __init__(
        self,
        *,
        gmail: GmailAdapter,
        client,
        vault_adapter: VaultAdapter,
        query: str = _DEFAULT_QUERY,
    ) -> None:
        self.gmail = gmail
        self.client = client
        self.vault_adapter = vault_adapter
        self.query = query
        self._template = _env.get_template("email_summary.j2")

    def compile(self) -> Path | None:
        """Fetch threads, classify, summarize, write summary file. Returns the
        path of the written file, or None if there were no threads (signals
        'no email content today' to callers)."""
        threads = self.gmail.fetch_recent_threads(query=self.query, max_threads=50)
        if not threads:
            return None

        now = dt.datetime.now(dt.UTC)
        buckets: dict[ThreadState, list[EmailThread]] = {
            ThreadState.WAITING_ON_YOU: [],
            ThreadState.FIRST_TOUCH: [],
            ThreadState.RECENT_ACTIVITY: [],
        }
        for thread in threads:
            state = classify_thread_state(thread, now=now)
            buckets[state].append(thread)

        today = dt.date.today().isoformat()
        prompt = self._template.render(
            today=today,
            machine_id=self.vault_adapter.machine_id,
            waiting_on_you=buckets[ThreadState.WAITING_ON_YOU],
            first_touch=buckets[ThreadState.FIRST_TOUCH],
            recent_activity=buckets[ThreadState.RECENT_ACTIVITY],
        )

        markdown = self.client.complete(
            prompt=prompt,
            system="You are a focused email-pulse note-taker.",
        )

        out_path = self.vault_adapter.write_kb_note(
            filename=f"{today}.md",
            content=markdown,
            subdir="email",
        )
        return out_path
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `pytest tests/test_email_compiler.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 125 passed (120 + 5).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/compilers/email_compiler.py tests/test_email_compiler.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: EmailCompiler — fetch + classify + summarize → kb/<machine>/email/<today>.md"
```

---

## Task 8: load_recent_email_summary context loader

**Files:** Create `src/jkw_obs_mcp/context/email_summary.py`, `tests/test_context_email_summary.py`.

Tiny utility the daily-review generator uses to read today's email pulse from the vault. Returns the file contents, or `None` if missing/stale.

- [ ] **Step 1: Failing tests at `tests/test_context_email_summary.py`**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_context_email_summary.py -v`
Expected: ImportError.

- [ ] **Step 3: Write `src/jkw_obs_mcp/context/email_summary.py`**

```python
"""Load today's email-pulse summary from the vault for daily-review context."""

from __future__ import annotations

import datetime as dt
from pathlib import Path


def load_recent_email_summary(vault_root: Path, *, machine_id: str) -> str | None:
    """Return today's email summary if it exists at
    `<vault>/kb/<machine_id>/email/<today>.md`, else None.

    The compiler writes today's file at the start of generate_daily_review;
    this loader reads it as a prompt input. If compile failed (no creds, API
    error), the file won't exist and we return None — graceful degrade.
    """
    today = dt.date.today().isoformat()
    path = vault_root / "kb" / machine_id / "email" / f"{today}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `pytest tests/test_context_email_summary.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 129 passed (125 + 4).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/context/email_summary.py tests/test_context_email_summary.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: load_recent_email_summary() context loader"
```

---

## Task 9: compile_email MCP tool + obsidian-git ignore

**Files:** Modify `src/jkw_obs_mcp/mcp/server.py`. Create `tests/test_mcp_compile_email_tool.py`.

Register a new MCP tool `compile_email` that lazy-builds `EmailCompiler` (mirrors the lazy `compile_raw` and `generate_daily_review` patterns). Also update the obsidian-git ignore list so `kb/<machine>/email/` doesn't sync to clusters.

- [ ] **Step 1: Failing tests at `tests/test_mcp_compile_email_tool.py`**

```python
"""MCP tool registration + dispatch for compile_email."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from jkw_obs_mcp.adapter.gmail import EmailMessage, EmailThread
from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.compilers.email_compiler import EmailCompiler
from jkw_obs_mcp.mcp.server import dispatch_tool, tools_for_adapter


class StubAnthropic:
    def complete(self, *, prompt, system="", max_tokens=4096):
        return f"# Email Pulse — {dt.date.today().isoformat()}\n\nstub"


class StubGmail:
    def __init__(self, threads):
        self.threads = threads

    def fetch_recent_threads(self, *, query, max_threads=50):
        return self.threads


def _msg(sender, is_self):
    return EmailMessage(
        message_id="m1", sender=sender, recipient="me@example.com",
        subject="Hi", date="Mon, 27 Apr 2026 09:00:00 +0000",
        body="hello", is_from_self=is_self,
    )


@pytest.fixture
def adapter_with_email(tmp_vault, tmp_path):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    threads = [
        EmailThread(thread_id="t1", subject="Hello", messages=[
            _msg("alice@example.com", False),
        ]),
    ]
    adapter.email_compiler = EmailCompiler(
        gmail=StubGmail(threads),
        client=StubAnthropic(),
        vault_adapter=adapter,
    )
    return adapter


def test_tool_surface_includes_compile_email(adapter_with_email):
    tools = tools_for_adapter(adapter_with_email)
    names = {t.name for t in tools}
    assert "compile_email" in names


@pytest.mark.asyncio
async def test_dispatch_compile_email_writes_summary(adapter_with_email, tmp_vault):
    result = await dispatch_tool(adapter_with_email, "compile_email", {})

    text = result[0].text
    today = dt.date.today().isoformat()
    expected = tmp_vault / "kb" / "dreamingmachine" / "email" / f"{today}.md"
    assert expected.is_file()
    assert str(expected) in text or "email" in text


@pytest.mark.asyncio
async def test_dispatch_compile_email_handles_no_threads(tmp_vault):
    """Empty inbox → tool returns informational message, no crash."""
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    adapter.email_compiler = EmailCompiler(
        gmail=StubGmail([]),  # no threads
        client=StubAnthropic(),
        vault_adapter=adapter,
    )

    result = await dispatch_tool(adapter, "compile_email", {})
    text = result[0].text
    assert "no" in text.lower() or "skipped" in text.lower() or "empty" in text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_compile_email_tool.py -v`
Expected: tool not registered, dispatch fails.

- [ ] **Step 3: Modify `src/jkw_obs_mcp/mcp/server.py` — append a Tool entry**

In `tools_for_adapter`, append (after the existing `generate_daily_review` Tool, before the closing `]`):

```python
        Tool(
            name="compile_email",
            description="Pull recent Gmail threads (Primary inbox, last 2 days), "
            "classify by waiting-on-you / new-conversation / active-thread, and write "
            "a structured summary to kb/<machine>/email/<date>.md. Mac-only; the file "
            "is excluded from the obsidian-git mirror.",
            inputSchema={"type": "object", "properties": {}},
        ),
```

- [ ] **Step 4: Modify `dispatch_tool` — add a branch before the final raise**

```python
    if name == "compile_email":
        # Lazy-build EmailCompiler on first call (needs Gmail OAuth + Anthropic).
        compiler = getattr(adapter, "email_compiler", None)
        if compiler is None:
            from pathlib import Path
            from jkw_obs_mcp.adapter.gmail import GmailAdapter
            from jkw_obs_mcp.compilers.email_compiler import EmailCompiler
            from jkw_obs_mcp.generation.anthropic_client import AnthropicClient

            cfg_dir = Path.home() / ".config" / "jkw-obs-mcp"
            gmail = GmailAdapter(
                client_secret_path=cfg_dir / "google-client-secret.json",
                token_path=cfg_dir / "gmail-token.json",
            )
            client = AnthropicClient(model=adapter.anthropic_model)
            compiler = EmailCompiler(
                gmail=gmail, client=client, vault_adapter=adapter
            )
            adapter.email_compiler = compiler

        out_path = compiler.compile()
        if out_path is None:
            return [TextContent(
                type="text",
                text="no recent threads matched (empty inbox or no Gmail credentials)",
            )]
        return [TextContent(type="text", text=f"wrote {out_path}")]
```

- [ ] **Step 5: Wire `email_compiler = None` placeholder in `main()`**

In `main()`, after the existing `adapter.daily_review_generator = None  # lazy-built on first call` line, add:

```python
    adapter.email_compiler = None  # lazy-built on first compile_email dispatch
```

- [ ] **Step 6: Run tests to verify all pass**

Run: `pytest tests/test_mcp_compile_email_tool.py -v`
Expected: 3 passed.

- [ ] **Step 7: Update obsidian-git plugin ignore**

The `obsidian-git` plugin reads `.gitignore` inside the vault directory. Edit (or create) `<vault>/.gitignore` and add:

```
kb/*/email/
```

(Adjust path if the vault uses a different convention.)

In the repo, this is **not** a code change — it's a one-time manual edit on the user's vault. Document it as a note in the plan file but don't try to ship a vault config change from the MCP repo.

- [ ] **Step 8: Run full suite**

Run: `pytest tests/ -q`
Expected: 132 passed (129 + 3).

- [ ] **Step 9: Commit**

```bash
git add src/jkw_obs_mcp/mcp/server.py tests/test_mcp_compile_email_tool.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: compile_email MCP tool + main() lazy-builds EmailCompiler"
```

---

## Task 10: generate_daily_review integration

**Files:** Modify `src/jkw_obs_mcp/generators/daily_review.py`, `src/jkw_obs_mcp/generation/prompts/daily_review.j2`, `tests/test_generator_daily_review.py`.

Bundle `EmailCompiler.compile()` into `generate_daily_review` (wrapped in try/except — graceful degrade) and surface the email summary in the daily review prompt as a new "Email pulse" section.

- [ ] **Step 1: Add failing tests in `tests/test_generator_daily_review.py`**

Append at the bottom of the file:

```python
def test_generate_calls_email_compiler_when_attached(adapter_with_state):
    """If adapter has email_compiler, generate() calls it before assembling prompt."""

    class StubEmailCompiler:
        def __init__(self):
            self.called = False

        def compile(self):
            self.called = True
            return None  # No threads → returns None, daily review continues

    stub = StubEmailCompiler()
    adapter_with_state.email_compiler = stub

    client = StubAnthropic()
    gen = DailyReviewGenerator(adapter=adapter_with_state, client=client)
    gen.generate()

    assert stub.called


def test_generate_includes_email_summary_in_prompt_when_present(
    adapter_with_state, tmp_vault
):
    """A non-empty email summary file under kb/<machine>/email/ is fed into the prompt."""
    today = dt.date.today().isoformat()
    email_dir = tmp_vault / "kb" / "dreamingmachine" / "email"
    email_dir.mkdir(parents=True)
    (email_dir / f"{today}.md").write_text(
        "# Email Pulse\n\n## Waiting on you\n- **Reply to Roberto** about BARDA"
    )

    client = StubAnthropic()
    gen = DailyReviewGenerator(adapter=adapter_with_state, client=client)
    gen.generate()

    assert "Roberto" in client.last_prompt
    assert "BARDA" in client.last_prompt


def test_generate_handles_email_compile_failure_gracefully(adapter_with_state):
    """EmailCompiler.compile() raising must not break the daily review."""

    class FailingCompiler:
        def compile(self):
            raise RuntimeError("simulated network error")

    adapter_with_state.email_compiler = FailingCompiler()

    client = StubAnthropic()
    gen = DailyReviewGenerator(adapter=adapter_with_state, client=client)
    out_path = gen.generate()  # MUST NOT raise

    assert out_path.is_file()
    # Prompt should still render with no email section content
    assert "no recent email summary" in client.last_prompt.lower() or \
           "(no email summary)" in client.last_prompt.lower()


def test_generate_works_without_email_compiler_attribute(adapter_with_state):
    """If adapter never got email_compiler attached, generate() proceeds anyway."""
    # Don't attach email_compiler — should still work
    if hasattr(adapter_with_state, "email_compiler"):
        delattr(adapter_with_state, "email_compiler")

    client = StubAnthropic()
    gen = DailyReviewGenerator(adapter=adapter_with_state, client=client)
    out_path = gen.generate()  # MUST NOT raise

    assert out_path.is_file()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_generator_daily_review.py -v`
Expected: at least 4 failures (new tests).

- [ ] **Step 3: Modify `src/jkw_obs_mcp/generators/daily_review.py`**

Add to imports:

```python
from jkw_obs_mcp.context.email_summary import load_recent_email_summary
```

In `DailyReviewGenerator.generate()`, AFTER the `today_iso = today_dt.isoformat()` lines and BEFORE the `events = ...` line, insert the bundled email-compile call:

```python
        # Bundled email compile — graceful degrade on any failure.
        compiler = getattr(self.adapter, "email_compiler", None)
        if compiler is not None:
            try:
                compiler.compile()
            except Exception:
                # Email failure must NEVER block the daily review.
                # The summary file simply won't exist, and the load below returns None.
                pass
```

Then in the input-gathering block, add (parallel to the existing `digests = load_recent_autofeeder_digests(...)` line):

```python
        email_summary = load_recent_email_summary(
            self.adapter.vault_root, machine_id=self.adapter.machine_id
        )
```

In the `self._template.render(...)` call, add `email_summary=email_summary` to the kwargs:

```python
        prompt = self._template.render(
            machine_id=self.adapter.machine_id,
            today=today_str,
            last_review=last_run.isoformat() if last_run else "(never)",
            events=events,
            vault_deltas=deltas,
            autofeeder_digests=digests,
            open_tasks=open_tasks,
            email_summary=email_summary,
        )
```

- [ ] **Step 4: Modify `src/jkw_obs_mcp/generation/prompts/daily_review.j2`**

Add a new "Email pulse" section AFTER "Today's events" and BEFORE "Looming this week":

```
## Email pulse
{% if email_summary %}
- The full email summary is in INPUTS below. Surface the 2-3 highest-leverage items here, especially anything in "Waiting on you." Cite subject + sender. Cross-reference with calendar/open tasks where relevant.
{% else %}
- "(no recent email summary)"
{% endif %}
```

Then in the INPUTS block at the bottom (after the `Open tasks` section, before the `Vault deltas` section), add:

```
Email pulse (from kb/{{ machine_id }}/email/today.md):
{% if email_summary %}
{{ email_summary }}
{% else %}
(no recent email summary)
{% endif %}
```

- [ ] **Step 5: Run daily-review tests**

Run: `pytest tests/test_generator_daily_review.py -v`
Expected: all pass (existing + 4 new).

- [ ] **Step 6: Run full suite**

Run: `pytest tests/ -q`
Expected: 136 passed (132 + 4).

- [ ] **Step 7: Commit**

```bash
git add src/jkw_obs_mcp/generators/daily_review.py src/jkw_obs_mcp/generation/prompts/daily_review.j2 tests/test_generator_daily_review.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: bundle email compile into generate_daily_review (graceful degrade)"
```

---

## Task 11: Manual end-to-end smoke test + plan-5-complete tag

This task is non-TDD — exercises the real Gmail OAuth bootstrap, real Versa API, and writes real summary files.

- [ ] **Step 1: Set up Google OAuth client (one-time)**

In Google Cloud Console (https://console.cloud.google.com):
1. Create or select a project (e.g., `jkw-obs-mcp-personal`).
2. Enable the Gmail API: **APIs & Services → Library → Gmail API → Enable**.
3. Configure OAuth consent screen: **APIs & Services → OAuth consent screen**. User type: External. App name: `jkw-obs-mcp`. Scopes: `gmail.readonly`. Test users: add `mrjinch@gmail.com`.
4. Create credentials: **APIs & Services → Credentials → Create credentials → OAuth client ID**. Application type: **Desktop app**. Download the JSON.
5. Save the downloaded JSON as `~/.config/jkw-obs-mcp/google-client-secret.json` and `chmod 600 ~/.config/jkw-obs-mcp/google-client-secret.json`.

- [ ] **Step 2: Update obsidian-git ignore in the vault**

Edit `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs/.gitignore` (create if missing) and add:

```
kb/*/email/
```

This ensures email summaries are never pushed by the obsidian-git plugin.

- [ ] **Step 3: Restart Claude Code**

Quit and relaunch so the MCP server picks up the new `compile_email` tool.

- [ ] **Step 4: Verify the tool surface**

In Claude Code, ask:

> List all jkw-obs tools.

Expected: 9 tools (the previous 8 + `compile_email`).

- [ ] **Step 5: Run compile_email (first time triggers OAuth)**

In Claude Code, ask:

> Use jkw-obs `compile_email`.

Expected: a browser tab opens for Google OAuth consent. Approve `gmail.readonly`. Token caches at `~/.config/jkw-obs-mcp/gmail-token.json`. Tool returns `wrote ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs/kb/dreamingmachine/email/<YYYY-MM-DD>.md`.

Open the file in Obsidian. Verify three sections (Waiting on you / New conversations / Active threads). Spot-check one or two real items match recent inbox content.

- [ ] **Step 6: Run generate_daily_review (now bundled with email)**

In Claude Code, ask:

> Use jkw-obs `generate_daily_review`.

Expected: ~10–30s. Output writes `kb/dreamingmachine/daily/<today>.md`. Verify the daily review now has an "Email pulse" section with 2-3 surfaced items, and that "Open threads" cross-references at least one email thread.

- [ ] **Step 7: Verify graceful degradation**

Temporarily rename the token to simulate auth failure:

```bash
mv ~/.config/jkw-obs-mcp/gmail-token.json ~/.config/jkw-obs-mcp/gmail-token.json.bak
```

Run `generate_daily_review` again.

Expected: succeeds. Email pulse section says "(no recent email summary)" or similar. All other sections (calendar, vault deltas, autofeeder, open tasks) still render normally.

Restore the token:

```bash
mv ~/.config/jkw-obs-mcp/gmail-token.json.bak ~/.config/jkw-obs-mcp/gmail-token.json
```

- [ ] **Step 8: Verify cluster mirror exclusion**

Force an obsidian-git push from the Obsidian UI (Source Control → Push). Then check `https://github.com/jinchiwei/jkw_obs-brain` — confirm `kb/dreamingmachine/email/` is **not** in the pushed tree. (If it is, fix `.gitignore` and force-remove from history.)

- [ ] **Step 9: Tag and push**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git tag plan-5-complete
git push origin main --tags
```

---

## Self-Review Checklist

- [ ] All 11 tasks committed
- [ ] `pytest -v` shows full suite green (~136 tests)
- [ ] `compile_email` MCP tool produces real `kb/dreamingmachine/email/<today>.md` with three sections
- [ ] `generate_daily_review` includes an "Email pulse" section that surfaces real waiting-on-you items
- [ ] Gmail token revoked / removed → daily review still ships, email section says "(no recent email summary)"
- [ ] `kb/*/email/` is excluded from the obsidian-git mirror (verified by inspecting the github.com/jinchiwei/jkw_obs-brain tree)
- [ ] `~/.config/jkw-obs-mcp/google-client-secret.json` and `~/.config/jkw-obs-mcp/gmail-token.json` both have mode 600
- [ ] `git tag plan-5-complete` pushed

When all boxes ticked, Plan 5 done. Plan 6 (installer for the Google OAuth bootstrap + the daily-review on-boot LaunchAgent) or Plan 7 (cluster rollout) next.

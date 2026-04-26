"""GmailAdapter — read-only Gmail access via Google's API client.

This module handles two concerns: (1) credential cache + refresh, and
(2) thread fetch. Both are implemented here.

Token storage: ~/.config/jkw-obs-mcp/gmail-token.json (mode 600).
Client secret: ~/.config/jkw-obs-mcp/google-client-secret.json (mode 600).
Both are gitignored and the user creates them via the Google Cloud
Console OAuth desktop flow (covered in Plan 6 installer).
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any  # noqa: F401 — used by GmailAdapter methods added in Task 3

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


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


class GmailAdapter:
    """Owns the OAuth credential lifecycle and Gmail thread fetching.

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
        self._cached_user_email: str | None = None

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
        """Persist credentials.to_json() with mode 600.

        Writes to a tempfile in the same directory, chmods to 600 before any
        bytes are written, then atomically replaces the target. This avoids a
        TOCTOU window where the token file would briefly sit at the umask
        default (typically 644) and expose the long-lived refresh token to
        other local processes.
        """
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        # delete=False so we can atomically rename it; cleanup on failure below.
        fd, tmp_path = tempfile.mkstemp(
            prefix=".token-", suffix=".tmp", dir=self.token_path.parent
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(creds.to_json())
            os.replace(tmp_path, self.token_path)
        except Exception:
            # Best-effort cleanup; let the original exception propagate.
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise

    def _ensure_credentials(self) -> Credentials | None:
        """Return valid Credentials or None.

        Resolution order:
          1. Load cached token. If expired but has refresh_token, refresh and return.
          2. If still valid (not expired, token present), return as-is.
          3. If interactive allowed and client_secret present, run OAuth flow.
          4. Otherwise return None (caller treats as 'no Gmail access today').

        Note: in real google-auth Credentials, `valid` is `not expired and token`,
        so steps 1 and 2 are mutually exclusive. Order matters only because tests
        use MagicMock where `valid` and `expired` can be set independently.
        """
        creds = self._load_credentials()

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save_credentials(creds)
            return creds

        if creds and creds.valid:
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

    def fetch_recent_threads(
        self, *, query: str, max_threads: int = 50
    ) -> list[EmailThread]:
        """Return parsed threads matching `query`. Returns [] on any failure."""
        creds = self._ensure_credentials()
        if creds is None:
            return []

        try:
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)

            # Cache the user's own email address (used to mark is_from_self).
            # Use empty-string sentinel after a failed lookup so we don't
            # re-fetch on every call if getProfile returns an unexpected shape.
            if self._cached_user_email is None:
                profile = service.users().getProfile(userId="me").execute()
                self._cached_user_email = profile.get("emailAddress") or ""

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
    """Stub — full implementation lands in Task 4 (body extraction).

    This intentionally handles only the simple top-level text/plain case.
    Task 4 replaces this with multipart-aware extraction. Test fixtures in
    Task 3 only use simple text/plain payloads.
    """
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")
    if mime == "text/plain" and body_data:
        try:
            return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        except Exception:
            return ""
    return ""

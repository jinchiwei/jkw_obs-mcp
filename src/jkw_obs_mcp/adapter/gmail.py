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

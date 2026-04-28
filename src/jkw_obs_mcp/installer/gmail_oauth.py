"""Step: walk user through Google Cloud OAuth + bootstrap the gmail.readonly token.

Three branches:
  1. token already cached → skip ("already configured")
  2. client_secret.json missing → print walkthrough, skip
  3. client_secret.json present, no token → trigger interactive OAuth flow

The actual OAuth interaction (browser pop, scope grant, token cache) lives
in GmailAdapter._ensure_credentials (Plan 5 Task 2). This installer step
just orchestrates the call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


_WALKTHROUGH = """\
Google Cloud OAuth setup (one-time, ~5 min):

  1. Go to https://console.cloud.google.com
  2. Select or create a project (e.g., 'jkw-obs-mcp-personal')
  3. APIs & Services → Library → Gmail API → Enable
  4. APIs & Services → OAuth consent screen → External (or Audience → External
     in newer console UI). Fill in app name and your email. Submit.
  5. APIs & Services → Credentials → Create credentials → OAuth client ID
     → Application type: Desktop app → Create
  6. Download the JSON
  7. Save it to ~/.config/jkw-obs-mcp/google-client-secret.json
     (mkdir the directory first if needed)
  8. chmod 600 ~/.config/jkw-obs-mcp/google-client-secret.json

Then re-run jkw-obs-mcp-setup. The script will detect the file and trigger
the first OAuth flow (browser will open, accept gmail.readonly scope).
"""


def gmail_oauth_setup(*, config_dir: Path | None = None) -> dict[str, Any]:
    """Bootstrap Gmail OAuth credentials. Returns a status dict.

    Skip semantics:
      - "token already cached" → already done, no work needed
      - "client_secret.json missing" → user hasn't done Google Cloud setup yet,
        we return the walkthrough text so the installer can print it
      - "OAuth flow failed" → user cancelled or other failure during the
        interactive flow; not fatal
    """
    if config_dir is None:
        config_dir = Path.home() / ".config" / "jkw-obs-mcp"

    client_secret = config_dir / "google-client-secret.json"
    token = config_dir / "gmail-token.json"

    if token.is_file():
        return {"skipped": True, "reason": "token already cached"}

    if not client_secret.is_file():
        return {
            "skipped": True,
            "reason": "client_secret.json missing",
            "walkthrough": _WALKTHROUGH,
        }

    # Trigger first OAuth flow via the real adapter from Plan 5.
    from jkw_obs_mcp.adapter.gmail import GmailAdapter
    adapter = GmailAdapter(
        client_secret_path=client_secret,
        token_path=token,
    )
    creds = adapter._ensure_credentials()
    if creds is None:
        return {"skipped": True, "reason": "OAuth flow failed (user cancelled?)"}
    return {"skipped": False, "token_path": str(token)}

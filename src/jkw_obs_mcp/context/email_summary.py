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

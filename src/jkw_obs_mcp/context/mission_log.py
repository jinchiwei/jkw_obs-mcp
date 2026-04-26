"""Load the user's Mission Log (primary todo stack) as daily-review context.

Mission Log is a single markdown file at <vault>/Tasks/Mission Log.md. Unlike
autofeeder digests or vault deltas (filtered by recency), the daily review
always reads the *current* contents — it's the source of truth for what's
actively on Jin's plate, regardless of when it was last edited.
"""

from __future__ import annotations

from pathlib import Path


_MISSION_LOG_REL = Path("Tasks") / "Mission Log.md"


def load_mission_log(vault_root: Path) -> str | None:
    """Return Mission Log contents, or None if the file is missing."""
    path = vault_root / _MISSION_LOG_REL
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")

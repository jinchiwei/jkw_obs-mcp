"""ensure_brain_repo_fresh — pull the brain repo if cached pull is stale.

The brain repo IS the user's vault directory (same git repo). This helper
pulls it via subprocess with a freshness cache so we don't hammer git on
every search_vault call. State file: ~/.config/jkw-obs-mcp/brain-last-pull.json
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


def _state_path() -> Path:
    """State file location. Function so tests can monkey-patch."""
    return Path.home() / ".config" / "jkw-obs-mcp" / "brain-last-pull.json"


def ensure_brain_repo_fresh(vault_root: Path, *, max_age_minutes: int = 5) -> None:
    """Pull the brain repo if the last pull was older than max_age_minutes.

    max_age_minutes=0 means "always pull, ignore cache" (use this before writes).
    max_age_minutes=N (typically 5) caches across reads in the same session burst.

    Cheap no-op when fresh. Logs to stderr but does NOT raise on pull failure
    — a flaky network shouldn't break a search_vault call. State file is only
    updated on successful pull, so failures naturally retry on the next call.
    """
    state = _state_path()

    if max_age_minutes > 0 and state.is_file():
        try:
            data = json.loads(state.read_text())
            last_pull = dt.datetime.fromisoformat(data["last_pull_at"])
            age_seconds = (dt.datetime.now(dt.UTC) - last_pull).total_seconds()
            if age_seconds < max_age_minutes * 60:
                return
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    result = subprocess.run(
        ["git", "-C", str(vault_root), "pull", "--ff-only"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"brain repo pull failed (rc={result.returncode}): {result.stderr.strip()}",
            file=sys.stderr,
        )
        return

    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps({"last_pull_at": dt.datetime.now(dt.UTC).isoformat()})
    )

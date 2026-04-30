"""ensure_brain_repo_fresh — pull the brain repo if cached pull is stale.

The brain repo IS the user's vault directory (same git repo). This helper
pulls it via subprocess with a freshness cache so we don't hammer git on
every search_vault call. State file: ~/.config/jkw-obs-mcp/brain-last-pull.json

Returns bool: True if the pull moved HEAD (caller may want to reindex).
False on cache hit, pull failure, or pull-no-op.
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


def _head_sha(vault_root: Path) -> str | None:
    """Return current HEAD SHA, or None if not a git repo / rev-parse fails."""
    proc = subprocess.run(
        ["git", "-C", str(vault_root), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def ensure_brain_repo_fresh(vault_root: Path, *, max_age_minutes: int = 5) -> bool:
    """Pull the brain repo if the last pull was older than max_age_minutes.

    Returns True if a pull was performed AND HEAD moved (callers may want to
    reindex). Returns False on cache hit, pull failure, or pull-no-op.

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
                return False  # cache hit, no pull
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Capture HEAD before pulling so we can detect whether anything changed.
    pre_sha = _head_sha(vault_root)
    if pre_sha is None:
        # Not a git repo or rev-parse failed; nothing meaningful to do.
        return False

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
        return False

    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps({"last_pull_at": dt.datetime.now(dt.UTC).isoformat()})
    )

    post_sha = _head_sha(vault_root)
    if post_sha is None:
        return False  # rev-parse broken post-pull; conservative no-reindex
    return post_sha != pre_sha

"""List vault .md files modified since a given timestamp."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path


_SKIP_DIRS = frozenset({".obsidian", ".trash", ".git", ".direnv", ".venv", "node_modules"})


@dataclass(frozen=True)
class VaultDelta:
    """One vault file modified since the cutoff."""

    rel_path: str
    mtime: dt.datetime


def vault_delta_since(vault_root: Path, since: dt.datetime) -> list[VaultDelta]:
    """Return all vault .md files whose mtime is on/after `since`.

    Skips _SKIP_DIRS (matches indexer.walker's exclusions).
    """
    vault_root = vault_root.resolve()
    cutoff_ts = since.timestamp()
    results: list[VaultDelta] = []

    for path in sorted(vault_root.rglob("*.md")):
        if not path.is_file():
            continue
        rel = path.relative_to(vault_root)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        st = path.stat()
        if st.st_mtime < cutoff_ts:
            continue
        results.append(
            VaultDelta(
                rel_path=rel.as_posix(),
                mtime=dt.datetime.fromtimestamp(st.st_mtime, tz=dt.UTC),
            )
        )

    return results

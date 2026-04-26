"""Walk the Obsidian vault and report markdown files with content hashes."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


# Top-level dirs that are NEVER scanned. .obsidian holds plugin code/state,
# .trash is recoverable in the Obsidian UI (not signal), .git is repo metadata,
# .pytest_cache and __pycache__ are tooling artifacts that can leak into a
# vault if a tool is run with the vault as its rootdir.
_SKIP_DIRS = frozenset({
    ".obsidian", ".trash", ".git", ".direnv", ".venv", "node_modules",
    ".pytest_cache", "__pycache__",
})


@dataclass(frozen=True)
class VaultEntry:
    """One markdown note discovered during a vault walk."""

    rel_path: str           # vault-relative, posix-style (forward slashes)
    content_hash: str       # sha256 hex of file content


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def walk_vault(vault_root: Path) -> Iterator[VaultEntry]:
    """Yield VaultEntry for every .md file under vault_root, skipping hidden /
    metadata dirs (.obsidian, .trash, .git, etc.)."""
    vault_root = vault_root.resolve()
    for path in sorted(vault_root.rglob("*.md")):
        if not path.is_file():
            continue
        # Skip if any path segment matches a SKIP_DIRS entry.
        if any(part in _SKIP_DIRS for part in path.relative_to(vault_root).parts):
            continue
        rel = path.relative_to(vault_root).as_posix()
        yield VaultEntry(rel_path=rel, content_hash=_sha256_of_file(path))

"""Top-level indexer: composes walker + embedder + store. Idempotent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jkw_obs_mcp.indexer.embedder import Embedder
from jkw_obs_mcp.indexer.store import SqliteVecStore
from jkw_obs_mcp.indexer.walker import walk_vault


@dataclass(frozen=True)
class ReindexStats:
    """Counts from a single reindex pass."""

    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0

    def __str__(self) -> str:
        return (
            f"added={self.added} updated={self.updated} "
            f"unchanged={self.unchanged} removed={self.removed}"
        )


class Indexer:
    """Composes the walker + embedder + store. The only public method most
    callers need is reindex()."""

    def __init__(
        self, vault_root: Path, store: SqliteVecStore, embedder: Embedder
    ) -> None:
        self.vault_root = vault_root
        self.store = store
        self.embedder = embedder

    def reindex(self, scope: str = "incremental") -> ReindexStats:
        """Walk the vault, embed new/changed files, drop deleted ones.

        scope:
          - "full"        — rebuild every entry (does NOT drop the table; just
                            re-embeds and upserts everything).
          - "incremental" — only embed paths whose content_hash differs from
                            what's already in the store.
        """
        if scope not in {"full", "incremental"}:
            raise ValueError(f"unknown reindex scope: {scope!r}")

        existing = self.store.all_paths()  # {path: content_hash}
        seen_paths: set[str] = set()

        added = 0
        updated = 0
        unchanged = 0

        # Pass 1: walk the vault, embed + upsert any new/changed files.
        for entry in walk_vault(self.vault_root):
            seen_paths.add(entry.rel_path)
            existing_hash = existing.get(entry.rel_path)

            if scope == "incremental" and existing_hash == entry.content_hash:
                unchanged += 1
                continue

            content = (self.vault_root / entry.rel_path).read_text(encoding="utf-8")
            vec = self.embedder.embed_one(content)
            self.store.upsert(
                path=entry.rel_path,
                content_hash=entry.content_hash,
                embedding=vec,
            )

            if existing_hash is None:
                added += 1
            else:
                updated += 1

        # Pass 2: drop entries for files that no longer exist on disk.
        removed = 0
        for path in existing.keys() - seen_paths:
            self.store.delete(path)
            removed += 1

        return ReindexStats(
            added=added, updated=updated, unchanged=unchanged, removed=removed
        )

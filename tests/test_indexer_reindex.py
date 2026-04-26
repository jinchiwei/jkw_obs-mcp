"""End-to-end indexer tests. Use a stub embedder (deterministic) so the test
suite doesn't need fastembed loaded."""

from pathlib import Path

import pytest

from jkw_obs_mcp.indexer.indexer import Indexer, ReindexStats
from jkw_obs_mcp.indexer.store import SqliteVecStore


class StubEmbedder:
    """Deterministic embedder for tests — hashes text into a fixed-length vec."""

    dimension = 4

    def embed_one(self, text: str) -> list[float]:
        # Deterministic 4-dim vector based on first 4 chars.
        padded = (text + "\x00\x00\x00\x00")[:4]
        return [float(ord(c)) for c in padded]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


@pytest.fixture
def indexer(tmp_vault, tmp_path):
    db = tmp_path / "test.db"
    store = SqliteVecStore(db_path=db, dimension=4)
    store.init_schema()
    return Indexer(vault_root=tmp_vault, store=store, embedder=StubEmbedder())


def test_reindex_full_inserts_every_md_file(indexer, tmp_vault):
    stats = indexer.reindex(scope="full")

    assert isinstance(stats, ReindexStats)
    assert stats.added >= 1
    assert stats.unchanged == 0
    assert "Admin/Saiyan.md" in indexer.store.all_paths()


def test_reindex_incremental_skips_unchanged_files(indexer):
    # First run: full
    indexer.reindex(scope="full")
    initial_paths = indexer.store.all_paths()

    # Second run: incremental — nothing changed, should skip everything.
    stats = indexer.reindex(scope="incremental")

    assert stats.added == 0
    assert stats.updated == 0
    assert stats.unchanged >= 1
    assert indexer.store.all_paths() == initial_paths


def test_reindex_picks_up_new_file(indexer, tmp_vault):
    indexer.reindex(scope="full")

    (tmp_vault / "Arcadia").mkdir(exist_ok=True)
    (tmp_vault / "Arcadia" / "new.md").write_text("# new note\n")

    stats = indexer.reindex(scope="incremental")

    assert stats.added == 1
    assert "Arcadia/new.md" in indexer.store.all_paths()


def test_reindex_picks_up_modified_file(indexer, tmp_vault):
    indexer.reindex(scope="full")
    old_hash = indexer.store.all_paths()["Admin/Saiyan.md"]

    (tmp_vault / "Admin" / "Saiyan.md").write_text("# Saiyan\nnew workout content\n")

    stats = indexer.reindex(scope="incremental")

    new_hash = indexer.store.all_paths()["Admin/Saiyan.md"]
    assert stats.updated == 1
    assert new_hash != old_hash


def test_reindex_removes_deleted_files(indexer, tmp_vault):
    indexer.reindex(scope="full")
    assert "Admin/Saiyan.md" in indexer.store.all_paths()

    (tmp_vault / "Admin" / "Saiyan.md").unlink()

    stats = indexer.reindex(scope="incremental")

    assert stats.removed == 1
    assert "Admin/Saiyan.md" not in indexer.store.all_paths()

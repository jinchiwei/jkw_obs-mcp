"""Tests for the sqlite-vec store. Uses in-memory DB."""

from pathlib import Path

import pytest

from jkw_obs_mcp.indexer.store import SqliteVecStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteVecStore:
    db = tmp_path / "embeddings.db"
    s = SqliteVecStore(db_path=db, dimension=4)
    s.init_schema()
    return s


def test_upsert_then_query(store):
    store.upsert(path="Admin/x.md", content_hash="h1", embedding=[1.0, 0.0, 0.0, 0.0])
    store.upsert(path="Admin/y.md", content_hash="h2", embedding=[0.0, 1.0, 0.0, 0.0])

    # Query closest to [0.9, 0.1, 0, 0] — should rank x.md first.
    hits = store.query(query_vec=[0.9, 0.1, 0.0, 0.0], top_k=2)

    assert len(hits) == 2
    assert hits[0].path == "Admin/x.md"
    assert hits[1].path == "Admin/y.md"
    assert hits[0].distance < hits[1].distance


def test_upsert_replaces_existing_path(store):
    store.upsert(path="Admin/x.md", content_hash="h1", embedding=[1.0, 0.0, 0.0, 0.0])
    store.upsert(path="Admin/x.md", content_hash="h2", embedding=[0.0, 0.0, 0.0, 1.0])

    # Should still be one row, with the new hash + new vector.
    paths = store.all_paths()
    assert paths == {"Admin/x.md": "h2"}


def test_all_paths_returns_dict_of_path_to_hash(store):
    store.upsert(path="a.md", content_hash="ha", embedding=[1.0, 0.0, 0.0, 0.0])
    store.upsert(path="b.md", content_hash="hb", embedding=[0.0, 1.0, 0.0, 0.0])

    assert store.all_paths() == {"a.md": "ha", "b.md": "hb"}


def test_delete_by_path(store):
    store.upsert(path="a.md", content_hash="ha", embedding=[1.0, 0.0, 0.0, 0.0])
    store.upsert(path="b.md", content_hash="hb", embedding=[0.0, 1.0, 0.0, 0.0])

    store.delete(path="a.md")

    assert store.all_paths() == {"b.md": "hb"}

"""Tests that the MCP server's search tools register and dispatch correctly.

Uses a stub embedder + real sqlite-vec store. Skips the live fastembed model
so the suite stays fast."""

from pathlib import Path

import pytest

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.indexer.indexer import Indexer
from jkw_obs_mcp.indexer.store import SqliteVecStore
from jkw_obs_mcp.mcp.server import dispatch_tool, tools_for_adapter


class StubEmbedder:
    dimension = 4

    def embed_one(self, text: str) -> list[float]:
        padded = (text + "\x00\x00\x00\x00")[:4]
        return [float(ord(c)) for c in padded]

    def embed_batch(self, texts):
        return [self.embed_one(t) for t in texts]


@pytest.fixture
def indexed_adapter(tmp_vault, tmp_path):
    """Build a VaultAdapter + populate a real sqlite-vec store via Indexer."""
    db = tmp_path / "search.db"
    store = SqliteVecStore(db_path=db, dimension=4)
    store.init_schema()
    embedder = StubEmbedder()
    indexer = Indexer(vault_root=tmp_vault, store=store, embedder=embedder)
    indexer.reindex(scope="full")

    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    # Attach the indexer artefacts so dispatch_tool can find them.
    adapter.embedder = embedder
    adapter.store = store
    return adapter


def test_tool_surface_includes_search_and_find_similar(indexed_adapter):
    tools = tools_for_adapter(indexed_adapter)
    names = {t.name for t in tools}
    assert "search_vault" in names
    assert "find_similar" in names


@pytest.mark.asyncio
async def test_dispatch_search_vault_returns_paths(indexed_adapter):
    result = await dispatch_tool(
        indexed_adapter, "search_vault", {"query": "Saiyan", "top_k": 5}
    )

    text = result[0].text
    # search_vault returns a markdown-ish list of paths + scores
    assert "Admin/Saiyan.md" in text


@pytest.mark.asyncio
async def test_dispatch_find_similar_returns_paths(indexed_adapter):
    result = await dispatch_tool(
        indexed_adapter, "find_similar", {"text": "workout log", "top_k": 5}
    )

    text = result[0].text
    assert "Admin/Saiyan.md" in text


@pytest.mark.asyncio
async def test_dispatch_reindex_runs_indexer(indexed_adapter, tmp_vault):
    # Add a new note that the existing index doesn't know about.
    (tmp_vault / "Arcadia").mkdir(exist_ok=True)
    (tmp_vault / "Arcadia" / "fresh.md").write_text("# fresh\n")

    # Need to attach an Indexer onto the adapter (same pattern as embedder/store).
    from jkw_obs_mcp.indexer.indexer import Indexer
    indexed_adapter.indexer = Indexer(
        vault_root=tmp_vault,
        store=indexed_adapter.store,
        embedder=indexed_adapter.embedder,
    )

    result = await dispatch_tool(
        indexed_adapter, "reindex", {"scope": "incremental"}
    )

    text = result[0].text
    assert "added=1" in text
    assert "Arcadia/fresh.md" in indexed_adapter.store.all_paths()

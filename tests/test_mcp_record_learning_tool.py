"""MCP tool registration + dispatch for record_learning."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.mcp.server import dispatch_tool, tools_for_adapter


@pytest.fixture
def adapter_with_indexer(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    adapter.indexer = MagicMock()
    return adapter


def test_tool_surface_includes_record_learning(adapter_with_indexer):
    tools = tools_for_adapter(adapter_with_indexer)
    names = {t.name for t in tools}
    assert "record_learning" in names


def test_tool_input_schema_has_category_enum(adapter_with_indexer):
    tools = tools_for_adapter(adapter_with_indexer)
    rl = next(t for t in tools if t.name == "record_learning")
    cat_schema = rl.inputSchema["properties"]["category"]
    assert cat_schema["enum"] == ["constraints", "decisions", "postmortems", "results"]


def test_tool_input_schema_marks_required_fields(adapter_with_indexer):
    tools = tools_for_adapter(adapter_with_indexer)
    rl = next(t for t in tools if t.name == "record_learning")
    required = set(rl.inputSchema["required"])
    assert {"category", "title", "content"} <= required


@pytest.mark.asyncio
async def test_dispatch_writes_file_and_returns_status(adapter_with_indexer, tmp_vault):
    """Successful dispatch writes the file and returns a status string."""
    def fake_run(args, **kwargs):
        # args = ["git", "-C", vault_root, <subcmd>, ...]
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.learnings.recorder.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run):
        result = await dispatch_tool(
            adapter_with_indexer,
            "record_learning",
            {
                "category": "constraints",
                "title": "Test learning",
                "content": "This is the body of the learning, padded out to be more than 50 chars long.",
                "tags": ["test"],
                "applies_to": ["jkw-obs-mcp"],
            },
        )

    text = result[0].text
    assert "wrote" in text.lower() or "kb/dreamingmachine/learnings/constraints" in text
    expected_dir = tmp_vault / "kb" / "dreamingmachine" / "learnings" / "constraints"
    md_files = list(expected_dir.glob("*-test-learning.md"))
    assert len(md_files) == 1


@pytest.mark.asyncio
async def test_dispatch_invalid_category_raises(adapter_with_indexer):
    with pytest.raises(ValueError):
        await dispatch_tool(
            adapter_with_indexer,
            "record_learning",
            {
                "category": "bogus",
                "title": "Test learning",
                "content": "x" * 100,
            },
        )


@pytest.mark.asyncio
async def test_dispatch_offline_returns_pushed_false_status(adapter_with_indexer, tmp_vault):
    """When push fails (offline), status text mentions sync incomplete."""

    def fake_run(args, **kwargs):
        # args = ["git", "-C", vault_root, <subcmd>, ...]
        subcmd = args[3] if len(args) > 3 else ""
        class R: returncode = 0; stderr = ""; stdout = ""
        if subcmd == "push":
            R.returncode = 1
            R.stderr = "could not resolve host"
        return R()

    with patch("jkw_obs_mcp.learnings.recorder.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run):
        result = await dispatch_tool(
            adapter_with_indexer,
            "record_learning",
            {
                "category": "constraints",
                "title": "Offline test",
                "content": "x" * 100,
            },
        )

    text = result[0].text
    assert "wrote" in text.lower()
    assert "not pushed" in text.lower() or "local only" in text.lower() or "pushed=false" in text.lower()


@pytest.mark.asyncio
async def test_search_vault_calls_ensure_brain_repo_fresh(adapter_with_indexer):
    """search_vault dispatch calls ensure_brain_repo_fresh(max_age_minutes=5)."""
    fake_embedder = MagicMock()
    fake_embedder.embed_one.return_value = [0.0] * 768
    adapter_with_indexer.embedder = fake_embedder
    fake_store = MagicMock()
    fake_store.query.return_value = []
    adapter_with_indexer.store = fake_store

    pull_calls = []

    def fake_pull(vault_root, *, max_age_minutes):
        pull_calls.append(max_age_minutes)

    with patch("jkw_obs_mcp.mcp.server.ensure_brain_repo_fresh", side_effect=fake_pull):
        await dispatch_tool(
            adapter_with_indexer, "search_vault", {"query": "test"}
        )

    assert pull_calls == [5]


@pytest.mark.asyncio
async def test_find_similar_calls_ensure_brain_repo_fresh(adapter_with_indexer):
    fake_embedder = MagicMock()
    fake_embedder.embed_one.return_value = [0.0] * 768
    adapter_with_indexer.embedder = fake_embedder
    fake_store = MagicMock()
    fake_store.query.return_value = []
    adapter_with_indexer.store = fake_store

    pull_calls = []

    def fake_pull(vault_root, *, max_age_minutes):
        pull_calls.append(max_age_minutes)

    with patch("jkw_obs_mcp.mcp.server.ensure_brain_repo_fresh", side_effect=fake_pull):
        await dispatch_tool(
            adapter_with_indexer, "find_similar", {"text": "test"}
        )

    assert pull_calls == [5]


@pytest.mark.asyncio
async def test_search_vault_reindexes_when_pulled_new(adapter_with_indexer):
    """When ensure_brain_repo_fresh returns True (new content pulled), reindex before query."""
    fake_embedder = MagicMock()
    fake_embedder.embed_one.return_value = [0.0] * 768
    adapter_with_indexer.embedder = fake_embedder
    fake_store = MagicMock()
    fake_store.query.return_value = []
    adapter_with_indexer.store = fake_store

    with patch("jkw_obs_mcp.mcp.server.ensure_brain_repo_fresh", return_value=True):
        await dispatch_tool(
            adapter_with_indexer, "search_vault", {"query": "test"}
        )

    adapter_with_indexer.indexer.reindex.assert_called_once_with(scope="incremental")


@pytest.mark.asyncio
async def test_search_vault_skips_reindex_when_not_pulled(adapter_with_indexer):
    """When ensure_brain_repo_fresh returns False (cache hit / no change), skip reindex."""
    fake_embedder = MagicMock()
    fake_embedder.embed_one.return_value = [0.0] * 768
    adapter_with_indexer.embedder = fake_embedder
    fake_store = MagicMock()
    fake_store.query.return_value = []
    adapter_with_indexer.store = fake_store

    with patch("jkw_obs_mcp.mcp.server.ensure_brain_repo_fresh", return_value=False):
        await dispatch_tool(
            adapter_with_indexer, "search_vault", {"query": "test"}
        )

    adapter_with_indexer.indexer.reindex.assert_not_called()


@pytest.mark.asyncio
async def test_find_similar_reindexes_when_pulled_new(adapter_with_indexer):
    fake_embedder = MagicMock()
    fake_embedder.embed_one.return_value = [0.0] * 768
    adapter_with_indexer.embedder = fake_embedder
    fake_store = MagicMock()
    fake_store.query.return_value = []
    adapter_with_indexer.store = fake_store

    with patch("jkw_obs_mcp.mcp.server.ensure_brain_repo_fresh", return_value=True):
        await dispatch_tool(
            adapter_with_indexer, "find_similar", {"text": "test"}
        )

    adapter_with_indexer.indexer.reindex.assert_called_once_with(scope="incremental")


@pytest.mark.asyncio
async def test_find_similar_skips_reindex_when_not_pulled(adapter_with_indexer):
    fake_embedder = MagicMock()
    fake_embedder.embed_one.return_value = [0.0] * 768
    adapter_with_indexer.embedder = fake_embedder
    fake_store = MagicMock()
    fake_store.query.return_value = []
    adapter_with_indexer.store = fake_store

    with patch("jkw_obs_mcp.mcp.server.ensure_brain_repo_fresh", return_value=False):
        await dispatch_tool(
            adapter_with_indexer, "find_similar", {"text": "test"}
        )

    adapter_with_indexer.indexer.reindex.assert_not_called()

"""Tests for the compile_raw MCP tool."""

from pathlib import Path

import pytest

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.compilers.base import CompileState
from jkw_obs_mcp.compilers.clips import ClipCompiler
from jkw_obs_mcp.compilers.papers import PaperCompiler
from jkw_obs_mcp.mcp.server import dispatch_tool, tools_for_adapter


class StubAnthropic:
    def __init__(self, response: str = "# Compiled\n\n## TL;DR\nstub") -> None:
        self.response = response

    def complete(self, *, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        return self.response


@pytest.fixture
def adapter_with_compilers(tmp_vault, tmp_path):
    """Adapter with paper + clip compilers attached, and a vault that has
    raw/papers/foo.md and raw/clips/bar.md staged."""
    raw_papers = tmp_vault / "raw" / "papers"
    raw_papers.mkdir(parents=True)
    (raw_papers / "foo.md").write_text("Title: foo\nAbstract: x")

    raw_clips = tmp_vault / "raw" / "clips"
    raw_clips.mkdir(parents=True)
    (raw_clips / "bar.md").write_text("Article body about y")

    state_path = tmp_path / "compile-state.json"

    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    client = StubAnthropic()
    adapter.compilers = {
        "papers": PaperCompiler(client=client),
        "clips": ClipCompiler(client=client),
    }
    adapter.compile_state_path = state_path
    return adapter


def test_tool_surface_includes_compile_raw(adapter_with_compilers):
    tools = tools_for_adapter(adapter_with_compilers)
    names = {t.name for t in tools}
    assert "compile_raw" in names


@pytest.mark.asyncio
async def test_dispatch_compile_raw_all(adapter_with_compilers, tmp_vault):
    result = await dispatch_tool(
        adapter_with_compilers, "compile_raw", {"scope": "all"}
    )
    text = result[0].text
    assert "papers: added=1" in text
    assert "clips: added=1" in text

    assert (tmp_vault / "kb" / "dreamingmachine" / "papers" / "foo.md").is_file()
    assert (tmp_vault / "kb" / "dreamingmachine" / "clips" / "bar.md").is_file()


@pytest.mark.asyncio
async def test_dispatch_compile_raw_papers_only(adapter_with_compilers, tmp_vault):
    result = await dispatch_tool(
        adapter_with_compilers, "compile_raw", {"scope": "papers"}
    )
    text = result[0].text
    assert "papers: added=1" in text
    # Clips should NOT have been compiled
    assert not (tmp_vault / "kb" / "dreamingmachine" / "clips" / "bar.md").exists()

"""Tests for the MCP server's tool registration and dispatch.

We test the dispatcher functions directly (`tools_for_adapter`, `dispatch_tool`)
rather than the live MCP server — those are pure functions, easy to unit test
without faking the MCP runtime. The thin wiring layer in `build_server` is
exercised by the manual smoke test in Task 14.
"""

from pathlib import Path

import pytest

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.mcp.server import dispatch_tool, tools_for_adapter


def test_tools_for_adapter_includes_read_note(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}

    assert "read_note" in names


@pytest.mark.asyncio
async def test_dispatch_read_note_returns_file_content(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    result = await dispatch_tool(adapter, "read_note", {"path": "Admin/Saiyan.md"})

    # MCP tools return a list of content blocks; the first text block is the file content.
    assert len(result) >= 1
    text = result[0].text
    assert "workout log" in text

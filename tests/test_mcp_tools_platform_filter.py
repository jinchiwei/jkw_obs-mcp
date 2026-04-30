"""Platform filter for tools_for_adapter — Mac-only tools excluded on Linux."""

from __future__ import annotations

from unittest.mock import patch

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.mcp.server import tools_for_adapter


_MAC_ONLY_TOOLS = {"compile_raw", "compile_email", "generate_daily_review"}
_CROSS_PLATFORM_TOOLS = {
    "read_note",
    "list_notes",
    "write_kb_note",
    "search_vault",
    "find_similar",
    "reindex",
    "record_learning",
}


def test_darwin_returns_all_ten_tools(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    with patch("jkw_obs_mcp.mcp.server.platform.system", return_value="Darwin"):
        tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}
    assert names == _CROSS_PLATFORM_TOOLS | _MAC_ONLY_TOOLS
    assert len(tools) == 10


def test_linux_excludes_mac_only_tools(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="scs")
    with patch("jkw_obs_mcp.mcp.server.platform.system", return_value="Linux"):
        tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}
    assert names == _CROSS_PLATFORM_TOOLS
    assert _MAC_ONLY_TOOLS.isdisjoint(names)
    assert len(tools) == 7


def test_unknown_platform_excludes_mac_only_tools(tmp_vault):
    """Conservative: anything that isn't Darwin gets the Linux tool set."""
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="scs")
    with patch("jkw_obs_mcp.mcp.server.platform.system", return_value="Windows"):
        tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}
    assert _MAC_ONLY_TOOLS.isdisjoint(names)


def test_record_learning_is_present_on_linux(tmp_vault):
    """record_learning must be available on cluster sessions — load-bearing for Plan 8."""
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="scs")
    with patch("jkw_obs_mcp.mcp.server.platform.system", return_value="Linux"):
        tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}
    assert "record_learning" in names


def test_search_vault_is_present_on_linux(tmp_vault):
    """search_vault must be available on cluster sessions — load-bearing for Plan 8."""
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="scs")
    with patch("jkw_obs_mcp.mcp.server.platform.system", return_value="Linux"):
        tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}
    assert "search_vault" in names

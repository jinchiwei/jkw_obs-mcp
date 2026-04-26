"""MCP server for jkw_obs_mcp.

Two layers:
1. Pure functions (`tools_for_adapter`, `dispatch_tool`) — easy to unit test.
2. Thin wiring layer (`build_server`) — registers the pure functions as MCP
   handlers. Exercised only by the manual smoke test (Plan 1 Task 14) and
   in production at startup.
"""

from __future__ import annotations

from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from jkw_obs_mcp.adapter.vault import VaultAdapter


def tools_for_adapter(adapter: VaultAdapter) -> list[Tool]:
    """Return the MCP Tool definitions exposed by this server.

    The adapter argument is here for future per-machine tool gating
    (e.g. only register get_upcoming_events on macOS) — unused in Plan 1.
    """
    _ = adapter  # reserved for future use
    return [
        Tool(
            name="read_note",
            description="Read a markdown note from the Obsidian vault. "
            "Path is relative to the vault root (e.g. 'Admin/Saiyan.md').",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Vault-relative path to the .md file",
                    },
                },
                "required": ["path"],
            },
        ),
    ]


async def dispatch_tool(
    adapter: VaultAdapter, name: str, arguments: dict[str, Any]
) -> list[TextContent]:
    """Dispatch a tool call to the right adapter method."""
    if name == "read_note":
        text = adapter.read_note(arguments["path"])
        return [TextContent(type="text", text=text)]
    raise ValueError(f"unknown tool: {name}")


def build_server(adapter: VaultAdapter) -> Server:
    """Create an MCP Server with the vault tools registered.

    Production entry only. For unit tests, use tools_for_adapter and
    dispatch_tool directly.
    """
    server = Server("jkw-obs-mcp")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return tools_for_adapter(adapter)

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        return await dispatch_tool(adapter, name, arguments)

    return server

"""MCP server for jkw_obs_mcp.

Two layers:
1. Pure functions (`tools_for_adapter`, `dispatch_tool`) — easy to unit test.
2. Thin wiring layer (`build_server`) — registers the pure functions as MCP
   handlers. Exercised only by the manual smoke test (Plan 1 Task 14) and
   in production at startup.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.config import detect_machine_id, load_config, load_machines


def tools_for_adapter(adapter: VaultAdapter) -> list[Tool]:
    """Return the MCP Tool definitions exposed by this server."""
    _ = adapter
    return [
        Tool(
            name="read_note",
            description="Read a markdown note from the Obsidian vault. "
            "Path is relative to the vault root (e.g. 'Admin/Saiyan.md').",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Vault-relative path"}
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="list_notes",
            description="List all markdown files in the vault, optionally "
            "scoped to a subdirectory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdir": {
                        "type": "string",
                        "description": "Vault-relative subdir to scope the listing",
                        "default": "",
                    },
                },
            },
        ),
        Tool(
            name="write_kb_note",
            description="Write a markdown note into kb/<this-machine>/<subdir>/. "
            "Refuses writes outside the machine's kb sandbox.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                    "subdir": {"type": "string", "default": "ad-hoc"},
                },
                "required": ["filename", "content"],
            },
        ),
        Tool(
            name="search_vault",
            description="Semantic search over the Obsidian vault. "
            "Returns the top-K notes most similar to the query, ranked by distance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="find_similar",
            description="Find notes semantically similar to the given text. "
            "Same retrieval as search_vault, but framed for 'notes like this'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="reindex",
            description="Re-walk the vault and update the embeddings index. "
            "Scope: 'incremental' (only changed files, default) or 'full' "
            "(re-embed everything).",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["incremental", "full"],
                        "default": "incremental",
                    },
                },
            },
        ),
        Tool(
            name="compile_raw",
            description="Compile raw/<type>/ files into kb/<machine>/<type>/ via "
            "server-side Claude prompts. Scope: 'all' (every type) or one of "
            "'papers', 'clips'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "default": "all",
                    },
                },
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
    if name == "list_notes":
        paths = adapter.list_notes(subdir=arguments.get("subdir", ""))
        text = "\n".join(str(p) for p in paths)
        return [TextContent(type="text", text=text)]
    if name == "write_kb_note":
        written = adapter.write_kb_note(
            filename=arguments["filename"],
            content=arguments["content"],
            subdir=arguments.get("subdir", "ad-hoc"),
        )
        return [TextContent(type="text", text=f"wrote {written}")]
    if name == "search_vault":
        query_vec = adapter.embedder.embed_one(arguments["query"])
        hits = adapter.store.query(query_vec, top_k=arguments.get("top_k", 10))
        lines = [f"- `{h.path}` (distance {h.distance:.4f})" for h in hits]
        return [TextContent(type="text", text="\n".join(lines))]
    if name == "find_similar":
        query_vec = adapter.embedder.embed_one(arguments["text"])
        hits = adapter.store.query(query_vec, top_k=arguments.get("top_k", 5))
        lines = [f"- `{h.path}` (distance {h.distance:.4f})" for h in hits]
        return [TextContent(type="text", text="\n".join(lines))]
    if name == "reindex":
        stats = adapter.indexer.reindex(scope=arguments.get("scope", "incremental"))
        return [TextContent(type="text", text=str(stats))]
    if name == "compile_raw":
        from jkw_obs_mcp.compilers.base import CompileState, compile_all
        scope = arguments.get("scope", "all")
        state_path = adapter.compile_state_path
        state = CompileState.load(state_path)
        compilers = adapter.compilers
        if scope != "all":
            if scope not in compilers:
                raise ValueError(
                    f"unknown compile scope {scope!r}; "
                    f"available: {sorted(compilers)} or 'all'"
                )
            compilers = {scope: compilers[scope]}

        lines: list[str] = []
        for _key, compiler in compilers.items():
            stats = compile_all(
                compiler=compiler,
                vault_root=adapter.vault_root,
                machine_id=adapter.machine_id,
                state=state,
                state_path=state_path,
            )
            lines.append(str(stats))
        return [TextContent(type="text", text="\n".join(lines))]
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


def main() -> None:
    """Entry point for the `jkw-obs-mcp` console script.

    Loads ~/.config/jkw-obs-mcp/config.toml and the bundled machines.toml,
    builds the VaultAdapter, and serves over stdio.
    """
    cfg_path = Path(os.path.expanduser("~/.config/jkw-obs-mcp/config.toml"))
    if not cfg_path.exists():
        raise SystemExit(
            f"config not found at {cfg_path}. Run install.sh to bootstrap."
        )

    cfg = load_config(cfg_path)

    # machines.toml ships with the package; locate it relative to this file.
    pkg_root = Path(__file__).resolve().parent.parent.parent.parent
    machines_path = pkg_root / "machines.toml"
    if not machines_path.exists():
        raise SystemExit(f"machines.toml not found at {machines_path}")
    registry = load_machines(machines_path)

    # Validate config.machine_id against registry + actual hostname (defense in depth).
    if cfg.machine_id not in registry:
        raise SystemExit(
            f"config.machine.id={cfg.machine_id!r} is not in machines.toml. "
            f"Known: {list(k for k, _ in registry.items())}"
        )

    detected = detect_machine_id(registry)
    if detected != cfg.machine_id:
        raise SystemExit(
            f"hostname suggests {detected!r} but config says {cfg.machine_id!r}. "
            f"Edit ~/.config/jkw-obs-mcp/config.toml or update machines.toml."
        )

    adapter = VaultAdapter(vault_root=cfg.vault_root, machine_id=cfg.machine_id)

    # Initialize the embeddings backend once at startup. Subsequent reindexes
    # reuse this Embedder instance.
    from jkw_obs_mcp.indexer.embedder import FastembedEmbedder
    from jkw_obs_mcp.indexer.store import SqliteVecStore

    db_path = cfg.embeddings.db_path
    if not db_path.is_absolute():
        # Resolve relative to repo root (same convention as machines.toml).
        db_path = pkg_root / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    embedder = FastembedEmbedder(model_name=cfg.embeddings.model)
    store = SqliteVecStore(db_path=db_path, dimension=embedder.dimension)
    store.init_schema()

    from jkw_obs_mcp.indexer.indexer import Indexer
    indexer = Indexer(vault_root=adapter.vault_root, store=store, embedder=embedder)
    adapter.indexer = indexer

    # Attach onto the adapter so dispatch_tool can use them. Adapter doesn't
    # define these as constructor args (kept clean for unit tests of the FS path);
    # we set them here as plain instance attributes.
    adapter.embedder = embedder
    adapter.store = store

    # Wire the raw → compile → kb pipeline. Compilers run server-side Claude
    # prompts via the AnthropicClient; compile-state.json (sha256 dedup) lives
    # alongside embeddings.db under data/.
    from jkw_obs_mcp.compilers.clips import ClipCompiler
    from jkw_obs_mcp.compilers.papers import PaperCompiler
    from jkw_obs_mcp.generation.anthropic_client import AnthropicClient

    anthropic_client = AnthropicClient(model=cfg.generation.model)
    adapter.compilers = {
        "papers": PaperCompiler(client=anthropic_client),
        "clips": ClipCompiler(client=anthropic_client),
    }
    adapter.compile_state_path = db_path.parent / "compile-state.json"

    server = build_server(adapter)

    async def _run() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(_run())

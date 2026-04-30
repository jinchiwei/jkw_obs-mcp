"""Register jkw-obs as an MCP server with Claude Code.

If `claude` CLI is on PATH, run `claude mcp add jkw-obs --command jkw-obs-mcp`.
Otherwise (or if the add fails), print the exact command for the user to run
after installing Claude Code.

Idempotent: checks `claude mcp list` first and skips the add if already present.
"""

from __future__ import annotations

import shutil
import subprocess


_INSTALL_COMMAND = "claude mcp add jkw-obs --command jkw-obs-mcp"


def register_mcp_server() -> dict:
    """Try to register jkw-obs with Claude Code. Returns status dict.

    Returns:
      {
        "registered": bool,                # True if jkw-obs is now registered
                                           # (either we added it OR it was already there)
        "already_registered": bool,        # True if it was already registered
        "instruction": str | None,         # printed when manual action is required
        "error": str | None,               # populated on subprocess failure
      }
    """
    result: dict = {
        "registered": False,
        "already_registered": False,
        "instruction": None,
        "error": None,
    }

    claude_path = shutil.which("claude")
    if claude_path is None:
        result["instruction"] = (
            f"Claude Code CLI not found on PATH. After installing Claude Code, run:\n\n"
            f"    {_INSTALL_COMMAND}\n"
        )
        print(result["instruction"])
        return result

    # Idempotency: check if jkw-obs is already registered
    list_proc = subprocess.run(
        ["claude", "mcp", "list"],
        capture_output=True, text=True,
    )
    if list_proc.returncode == 0 and "jkw-obs" in list_proc.stdout:
        result["registered"] = True
        result["already_registered"] = True
        return result

    # Run the add command
    add_proc = subprocess.run(
        ["claude", "mcp", "add", "jkw-obs", "--command", "jkw-obs-mcp"],
        capture_output=True, text=True,
    )
    if add_proc.returncode != 0:
        result["error"] = add_proc.stderr.strip() or add_proc.stdout.strip()
        result["instruction"] = (
            f"`claude mcp add` failed: {result['error']}\n"
            f"Run manually:\n\n    {_INSTALL_COMMAND}\n"
        )
        print(result["instruction"])
        return result

    result["registered"] = True
    return result

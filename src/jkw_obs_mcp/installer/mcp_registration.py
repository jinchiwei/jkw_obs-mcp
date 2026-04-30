"""Register jkw-obs as an MCP server with Claude Code.

Registers with the ABSOLUTE path to the installed jkw-obs-mcp binary so Claude
Code can spawn it without our venv being activated. Resolves via shutil.which
at registration time (the bootstrap activates the venv before running the
installer, so `jkw-obs-mcp` is on PATH at this moment and which() returns the
venv-resolved absolute path).

Modern Claude Code (v2.x) syntax: `claude mcp add [opts] <name> -- <command>`.
- `--scope user` so the registration is global to the user account, not
  project-local (default `local` scope ties the registration to whatever cwd
  `claude` was first run from — wrong for a tool that should be available in
  every session).
- The `--` separator disambiguates the subprocess command from any
  `claude mcp add` flags.

If `claude` CLI is missing OR `jkw-obs-mcp` is not on PATH, fall back to printing
the exact command. Idempotent: checks `claude mcp list` first and skips the add
if already present.
"""

from __future__ import annotations

import shutil
import subprocess


def _install_command(server_path: str) -> str:
    """Render the human-readable copy-paste command."""
    return f"claude mcp add --scope user jkw-obs -- {server_path}"


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

    # Resolve the absolute path to jkw-obs-mcp (the installed entry point).
    # The venv is active when this runs, so which() returns the venv-resolved path.
    server_path = shutil.which("jkw-obs-mcp") or "jkw-obs-mcp"

    claude_path = shutil.which("claude")
    if claude_path is None:
        result["instruction"] = (
            f"Claude Code CLI not found on PATH. After installing Claude Code, run:\n\n"
            f"    {_install_command(server_path)}\n"
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

    # Run the add command. `--` separates the mcp-add flags from the subcommand.
    add_proc = subprocess.run(
        ["claude", "mcp", "add", "--scope", "user", "jkw-obs", "--", server_path],
        capture_output=True, text=True,
    )
    if add_proc.returncode != 0:
        result["error"] = add_proc.stderr.strip() or add_proc.stdout.strip()
        result["instruction"] = (
            f"`claude mcp add` failed: {result['error']}\n"
            f"Run manually:\n\n    {_install_command(server_path)}\n"
        )
        print(result["instruction"])
        return result

    result["registered"] = True
    return result

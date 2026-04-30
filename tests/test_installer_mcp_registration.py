"""Tests for installer.mcp_registration."""

from __future__ import annotations

from unittest.mock import patch

from jkw_obs_mcp.installer.mcp_registration import register_mcp_server


# Sentinel absolute path for the mocked jkw-obs-mcp binary location.
_FAKE_SERVER_PATH = "/home/user/arcadia/jkw_obs-mcp/.venv/bin/jkw-obs-mcp"


def _fake_which(server_path=_FAKE_SERVER_PATH, claude_path="/usr/local/bin/claude"):
    """Build a side_effect for shutil.which that returns different paths per name."""
    def which(name):
        if name == "jkw-obs-mcp":
            return server_path
        if name == "claude":
            return claude_path
        return None
    return which


def test_runs_claude_mcp_add_when_cli_available():
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               side_effect=_fake_which()), \
         patch("jkw_obs_mcp.installer.mcp_registration.subprocess.run",
               side_effect=fake_run):
        result = register_mcp_server()

    assert result["registered"] is True
    assert result["instruction"] is None
    assert any("mcp" in args and "add" in args for args in runs)


def test_prints_command_when_claude_cli_missing(capsys):
    """When claude is not on PATH, print the command for manual run."""
    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               side_effect=_fake_which(claude_path=None)):
        result = register_mcp_server()

    assert result["registered"] is False
    assert result["instruction"] is not None
    assert "claude mcp add" in result["instruction"]
    # The instruction is also printed to stdout for the installer's report
    captured = capsys.readouterr()
    assert "claude mcp add" in captured.out


def test_claude_mcp_add_failure_returns_instruction(capsys):
    """If claude is on PATH but the add command fails, fall back to instruction."""
    def fake_run(args, **kwargs):
        class R: returncode = 1; stderr = "already registered"; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               side_effect=_fake_which()), \
         patch("jkw_obs_mcp.installer.mcp_registration.subprocess.run",
               side_effect=fake_run):
        result = register_mcp_server()

    assert result["registered"] is False
    assert result["error"] is not None
    assert "already registered" in result["error"]
    assert result["instruction"] is not None


def test_already_registered_is_idempotent(capsys):
    """If `claude mcp list` shows jkw-obs already there, skip the add."""
    list_calls = []
    add_calls = []

    def fake_run(args, **kwargs):
        if "list" in args:
            list_calls.append(args)
            class R:
                returncode = 0
                stderr = ""
                stdout = "jkw-obs: jkw-obs-mcp\nother-server: foo\n"
            return R()
        add_calls.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               side_effect=_fake_which()), \
         patch("jkw_obs_mcp.installer.mcp_registration.subprocess.run",
               side_effect=fake_run):
        result = register_mcp_server()

    assert result["registered"] is True
    assert result["already_registered"] is True
    assert len(list_calls) == 1
    assert len(add_calls) == 0  # never tried to add


def test_instruction_text_includes_exact_command():
    """The instruction text must be a copy-paste-ready command using the absolute path."""
    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               side_effect=_fake_which(claude_path=None)):
        result = register_mcp_server()

    inst = result["instruction"]
    # Modern Claude Code v2.x syntax: `claude mcp add [opts] <name> -- <command>`
    assert "claude mcp add" in inst
    assert "jkw-obs" in inst
    # Absolute path is load-bearing — Claude Code spawns the server without our
    # venv activated, so PATH lookup wouldn't find a venv-installed binary.
    assert _FAKE_SERVER_PATH in inst
    assert f"-- {_FAKE_SERVER_PATH}" in inst
    # No template-variable placeholders
    assert "{" not in inst
    assert "<" not in inst


def test_instruction_falls_back_to_relative_command_when_server_not_on_path(capsys):
    """If jkw-obs-mcp is not on PATH (e.g., venv not activated), fall back to relative."""
    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               side_effect=_fake_which(server_path=None, claude_path=None)):
        result = register_mcp_server()

    inst = result["instruction"]
    assert "-- jkw-obs-mcp" in inst


def test_add_command_uses_absolute_path_user_scope_and_separator():
    """Modern claude mcp add: --scope user, name, --, ABSOLUTE-PATH-to-jkw-obs-mcp."""
    add_calls = []

    def fake_run(args, **kwargs):
        if "add" in args:
            add_calls.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               side_effect=_fake_which()), \
         patch("jkw_obs_mcp.installer.mcp_registration.subprocess.run",
               side_effect=fake_run):
        register_mcp_server()

    assert len(add_calls) == 1
    args = add_calls[0]
    # Required tokens
    assert "add" in args
    assert "--scope" in args
    assert "user" in args
    assert "--" in args
    assert "jkw-obs" in args
    # The server path passed to claude is the ABSOLUTE path, not the bare name
    assert _FAKE_SERVER_PATH in args
    # `--` must come BEFORE the server path (separates flags from subcommand)
    assert args.index("--") < args.index(_FAKE_SERVER_PATH)
    # `--command` flag MUST NOT appear (was removed in Claude Code v2.x)
    assert "--command" not in args

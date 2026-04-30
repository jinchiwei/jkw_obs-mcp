"""Tests for installer.mcp_registration."""

from __future__ import annotations

from unittest.mock import patch

from jkw_obs_mcp.installer.mcp_registration import register_mcp_server


def test_runs_claude_mcp_add_when_cli_available():
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               return_value="/usr/local/bin/claude"), \
         patch("jkw_obs_mcp.installer.mcp_registration.subprocess.run",
               side_effect=fake_run):
        result = register_mcp_server()

    assert result["registered"] is True
    assert result["instruction"] is None
    assert any("mcp" in args and "add" in args for args in runs)


def test_prints_command_when_claude_cli_missing(capsys):
    """When claude is not on PATH, print the command for manual run."""
    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               return_value=None):
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
               return_value="/usr/local/bin/claude"), \
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
               return_value="/usr/local/bin/claude"), \
         patch("jkw_obs_mcp.installer.mcp_registration.subprocess.run",
               side_effect=fake_run):
        result = register_mcp_server()

    assert result["registered"] is True
    assert result["already_registered"] is True
    assert len(list_calls) == 1
    assert len(add_calls) == 0  # never tried to add


def test_instruction_text_includes_exact_command():
    """The instruction text must be a copy-paste-ready command."""
    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               return_value=None):
        result = register_mcp_server()

    inst = result["instruction"]
    assert "claude mcp add jkw-obs" in inst
    # No placeholders or template variables
    assert "{" not in inst
    assert "<" not in inst

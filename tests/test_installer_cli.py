"""Tests for installer.cli orchestrator."""

from __future__ import annotations

from unittest.mock import patch

from jkw_obs_mcp.installer.cli import main


def test_main_returns_0_on_darwin(capsys):
    """All four steps run on Darwin. Mocks all of them."""
    with patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Darwin"), \
         patch(
             "jkw_obs_mcp.installer.cli.create_config_dir",
             return_value={"env_scaffolded": True, "env_already_existed": False},
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.is_hostname_registered",
             return_value=True,
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.gmail_oauth_setup",
             return_value={"skipped": True, "reason": "token already cached"},
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.install_launchd_agent",
             return_value={"skipped": False, "plist_path": "/fake"},
         ):
        rc = main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "Darwin" in out
    assert "config dir" in out.lower()
    assert "machines.toml" in out.lower()
    assert "gmail" in out.lower()
    assert "launchd" in out.lower()


def test_main_skips_mac_only_steps_on_linux(capsys):
    """Linux runs config_dir + machines_check, but skips Gmail and launchd."""
    gmail_called = []
    launchd_called = []

    def fake_gmail(**_kwargs):
        gmail_called.append(True)
        return {"skipped": True}

    def fake_launchd(**_kwargs):
        launchd_called.append(True)
        return {"skipped": True}

    with patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Linux"), \
         patch(
             "jkw_obs_mcp.installer.cli.create_config_dir",
             return_value={"env_scaffolded": True, "env_already_existed": False},
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.is_hostname_registered",
             return_value=True,
         ), \
         patch("jkw_obs_mcp.installer.cli.gmail_oauth_setup", side_effect=fake_gmail), \
         patch("jkw_obs_mcp.installer.cli.install_launchd_agent", side_effect=fake_launchd):
        rc = main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "Linux" in out
    # Gmail and launchd functions were NOT called on Linux
    assert gmail_called == []
    assert launchd_called == []
    # The orchestrator printed that they were skipped
    assert "skipped" in out.lower()


def test_main_warns_when_hostname_not_registered(capsys):
    """If hostname isn't in machines.toml, print the instruction and don't fail.

    The orchestrator can't safely auto-append (which machine_id?), so it
    surfaces the missing entry to the user and continues with other steps.
    """
    with patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Linux"), \
         patch(
             "jkw_obs_mcp.installer.cli.create_config_dir",
             return_value={"env_scaffolded": True, "env_already_existed": False},
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.is_hostname_registered",
             return_value=False,
         ):
        rc = main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "machines.toml" in out.lower()
    assert "register" in out.lower() or "not registered" in out.lower() or "add" in out.lower()

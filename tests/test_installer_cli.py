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
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.bootstrap_brain_repo",
             return_value={"cloned": False, "pulled": True, "config_written": False,
                           "config_already_existed": True, "error": None},
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.register_mcp_server",
             return_value={"registered": True, "already_registered": True,
                           "instruction": None, "error": None},
         ), \
         patch("jkw_obs_mcp.installer.cli.detect_machine_id", return_value="mac"):
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
         patch("jkw_obs_mcp.installer.cli.install_launchd_agent", side_effect=fake_launchd), \
         patch(
             "jkw_obs_mcp.installer.cli.bootstrap_brain_repo",
             return_value={"cloned": True, "pulled": False, "config_written": True,
                           "config_already_existed": False, "error": None},
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.register_mcp_server",
             return_value={"registered": True, "already_registered": False,
                           "instruction": None, "error": None},
         ), \
         patch("jkw_obs_mcp.installer.cli.detect_machine_id", return_value="scs"):
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
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.bootstrap_brain_repo",
             return_value={"cloned": True, "pulled": False, "config_written": True,
                           "config_already_existed": False, "error": None},
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.register_mcp_server",
             return_value={"registered": True, "already_registered": False,
                           "instruction": None, "error": None},
         ), \
         patch("jkw_obs_mcp.installer.cli.detect_machine_id", return_value="unknown"):
        rc = main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "machines.toml" in out.lower()
    assert "register" in out.lower() or "not registered" in out.lower() or "add" in out.lower()


def test_main_calls_bootstrap_brain_repo(tmp_path, monkeypatch):
    """The main() orchestrator runs brain repo bootstrap on all platforms."""
    monkeypatch.setenv("HOME", str(tmp_path))
    bootstrap_calls = []

    def fake_bootstrap(**kwargs):
        bootstrap_calls.append(kwargs)
        return {"cloned": True, "pulled": False, "config_written": True,
                "config_already_existed": False, "error": None}

    with patch("jkw_obs_mcp.installer.cli.bootstrap_brain_repo",
               side_effect=fake_bootstrap), \
         patch("jkw_obs_mcp.installer.cli.register_mcp_server",
               return_value={"registered": True, "already_registered": False,
                             "instruction": None, "error": None}), \
         patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Linux"), \
         patch("jkw_obs_mcp.installer.cli.current_hostname", return_value="callosum"), \
         patch("jkw_obs_mcp.installer.cli.is_hostname_registered", return_value=True):
        rc = main()

    assert rc == 0
    assert len(bootstrap_calls) == 1
    kwargs = bootstrap_calls[0]
    assert "jkw_obs-brain" in str(kwargs["target_dir"])
    assert "arcadia" in str(kwargs["target_dir"])


def test_main_calls_register_mcp_server_on_linux(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    mcp_calls = []

    def fake_register():
        mcp_calls.append(True)
        return {"registered": True, "already_registered": False,
                "instruction": None, "error": None}

    with patch("jkw_obs_mcp.installer.cli.bootstrap_brain_repo",
               return_value={"cloned": True, "pulled": False, "config_written": True,
                             "config_already_existed": False, "error": None}), \
         patch("jkw_obs_mcp.installer.cli.register_mcp_server",
               side_effect=fake_register), \
         patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Linux"), \
         patch("jkw_obs_mcp.installer.cli.current_hostname", return_value="callosum"), \
         patch("jkw_obs_mcp.installer.cli.is_hostname_registered", return_value=True):
        rc = main()

    assert rc == 0
    assert len(mcp_calls) == 1


def test_main_calls_register_mcp_server_on_darwin_too(monkeypatch, tmp_path):
    """MCP registration runs on Mac too, after the Mac-only Gmail/launchd steps."""
    monkeypatch.setenv("HOME", str(tmp_path))
    mcp_calls = []

    def fake_register():
        mcp_calls.append(True)
        return {"registered": True, "already_registered": False,
                "instruction": None, "error": None}

    with patch("jkw_obs_mcp.installer.cli.bootstrap_brain_repo",
               return_value={"cloned": False, "pulled": True, "config_written": False,
                             "config_already_existed": True, "error": None}), \
         patch("jkw_obs_mcp.installer.cli.register_mcp_server",
               side_effect=fake_register), \
         patch("jkw_obs_mcp.installer.cli.gmail_oauth_setup",
               return_value={"already_setup": True}), \
         patch("jkw_obs_mcp.installer.cli.install_launchd_agent",
               return_value={"already_installed": True}), \
         patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Darwin"), \
         patch("jkw_obs_mcp.installer.cli.current_hostname",
               return_value="dreamingmachine"), \
         patch("jkw_obs_mcp.installer.cli.is_hostname_registered", return_value=True):
        rc = main()

    assert rc == 0
    assert len(mcp_calls) == 1


def test_main_passes_machine_id_to_bootstrap(monkeypatch, tmp_path):
    """Machine ID detected from hostname is threaded into bootstrap_brain_repo."""
    monkeypatch.setenv("HOME", str(tmp_path))
    bootstrap_calls = []

    def fake_bootstrap(**kwargs):
        bootstrap_calls.append(kwargs)
        return {"cloned": True, "pulled": False, "config_written": True,
                "config_already_existed": False, "error": None}

    with patch("jkw_obs_mcp.installer.cli.bootstrap_brain_repo",
               side_effect=fake_bootstrap), \
         patch("jkw_obs_mcp.installer.cli.register_mcp_server",
               return_value={"registered": True, "already_registered": False,
                             "instruction": None, "error": None}), \
         patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Linux"), \
         patch("jkw_obs_mcp.installer.cli.current_hostname", return_value="callosum"), \
         patch("jkw_obs_mcp.installer.cli.is_hostname_registered", return_value=True), \
         patch("jkw_obs_mcp.installer.cli.detect_machine_id", return_value="scs"):
        main()

    assert bootstrap_calls[0]["machine_id"] == "scs"

"""Tests for installer.launchd install/uninstall."""

from __future__ import annotations

import platform
from pathlib import Path
from unittest.mock import patch

from jkw_obs_mcp.installer.launchd import (
    LABEL,
    install_launchd_agent,
    uninstall_launchd_agent,
)


def test_install_skips_on_linux(tmp_path):
    plist_path = tmp_path / "fake.plist"
    with patch("jkw_obs_mcp.installer.launchd.platform.system", return_value="Linux"):
        status = install_launchd_agent(plist_path=plist_path)
    assert status["skipped"] is True
    assert "non-darwin" in status["reason"].lower() or "linux" in status["reason"].lower()
    assert not plist_path.exists()  # nothing written


def test_install_writes_plist_and_calls_launchctl_on_darwin(tmp_path):
    plist_path = tmp_path / "agent.plist"
    fake_runs = []

    def fake_run(args, **kwargs):
        fake_runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.launchd.platform.system", return_value="Darwin"), \
         patch("jkw_obs_mcp.installer.launchd.subprocess.run", side_effect=fake_run):
        status = install_launchd_agent(plist_path=plist_path)

    # Plist was written
    assert plist_path.is_file()
    content = plist_path.read_text()
    assert LABEL in content
    assert "<integer>300</integer>" in content

    # launchctl bootout (idempotent cleanup) called first, then bootstrap
    assert any("bootout" in " ".join(args) for args in fake_runs)
    assert any("bootstrap" in " ".join(args) for args in fake_runs)
    assert status["skipped"] is False


def test_install_is_idempotent(tmp_path):
    """Re-running install on an already-installed system bootouts existing first."""
    plist_path = tmp_path / "agent.plist"
    fake_runs = []

    def fake_run(args, **kwargs):
        fake_runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.launchd.platform.system", return_value="Darwin"), \
         patch("jkw_obs_mcp.installer.launchd.subprocess.run", side_effect=fake_run):
        install_launchd_agent(plist_path=plist_path)
        install_launchd_agent(plist_path=plist_path)

    # Each install does bootout-then-bootstrap, so we should see 2 of each
    bootouts = sum(1 for a in fake_runs if "bootout" in " ".join(a))
    bootstraps = sum(1 for a in fake_runs if "bootstrap" in " ".join(a))
    assert bootouts == 2
    assert bootstraps == 2


def test_uninstall_skips_on_linux(tmp_path):
    plist_path = tmp_path / "agent.plist"
    plist_path.write_text("not used")
    with patch("jkw_obs_mcp.installer.launchd.platform.system", return_value="Linux"):
        status = uninstall_launchd_agent(plist_path=plist_path)
    assert status["skipped"] is True
    assert plist_path.is_file()  # not removed on Linux


def test_uninstall_bootouts_and_removes_plist_on_darwin(tmp_path):
    plist_path = tmp_path / "agent.plist"
    plist_path.write_text("placeholder plist contents")
    fake_runs = []

    def fake_run(args, **kwargs):
        fake_runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.launchd.platform.system", return_value="Darwin"), \
         patch("jkw_obs_mcp.installer.launchd.subprocess.run", side_effect=fake_run):
        status = uninstall_launchd_agent(plist_path=plist_path)

    assert any("bootout" in " ".join(args) for args in fake_runs)
    assert not plist_path.exists()
    assert status["skipped"] is False

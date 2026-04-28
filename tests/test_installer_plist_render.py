"""Plist render output validity tests."""

from __future__ import annotations

import plistlib
import sys

from jkw_obs_mcp.installer.launchd import LABEL, render_plist


def test_render_plist_returns_well_formed_xml():
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["Label"] == LABEL


def test_render_plist_uses_sys_executable_by_default():
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["ProgramArguments"][0] == sys.executable


def test_render_plist_accepts_custom_python_path():
    xml = render_plist(python_path="/opt/homebrew/bin/python3.12")
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["ProgramArguments"][0] == "/opt/homebrew/bin/python3.12"


def test_render_plist_invokes_module_form():
    """ProgramArguments invokes the trigger via `python -m`, not by absolute script path."""
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["ProgramArguments"][1] == "-m"
    assert parsed["ProgramArguments"][2] == "jkw_obs_mcp.triggers.daily_review_runner"


def test_render_plist_sets_start_interval_300():
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["StartInterval"] == 300


def test_render_plist_sets_run_at_load_true():
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["RunAtLoad"] is True


def test_render_plist_does_not_set_start_calendar_interval():
    """Plan 4's StartCalendarInterval=8am is gone — wake-from-sleep doesn't catch it."""
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert "StartCalendarInterval" not in parsed


def test_render_plist_log_paths_under_library_logs():
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert "/Library/Logs/" in parsed["StandardOutPath"]
    assert "/Library/Logs/" in parsed["StandardErrorPath"]

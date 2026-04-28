"""launchd LaunchAgent management for the daily-review boot trigger.

This file defines the plist template renderer (works on any platform) and
the install/uninstall functions (Mac-only — Task 6 adds those). On Linux,
the install function is a no-op.
"""

from __future__ import annotations

import sys
from pathlib import Path


LABEL = "com.jinchiwei.jkw-obs-mcp.daily-review"


_PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>jkw_obs_mcp.triggers.daily_review_runner</string>
    </array>

    <!-- Fires every 5 min while awake. Paused during sleep; resumes on wake.
         RunAtLoad=true also fires once at session login (covers full restarts). -->
    <key>StartInterval</key>
    <integer>300</integer>

    <key>RunAtLoad</key>
    <true/>

    <!-- Don't start a second instance if a previous run is still going. -->
    <key>AbandonProcessGroup</key>
    <false/>

    <key>StandardOutPath</key>
    <string>{log_out}</string>
    <key>StandardErrorPath</key>
    <string>{log_err}</string>
</dict>
</plist>
"""


def render_plist(*, python_path: str | None = None, label: str = LABEL) -> str:
    """Return the plist XML with the given Python path embedded.

    `python_path` defaults to the current `sys.executable` so the LaunchAgent
    points at the interpreter the user installed jkw-obs-mcp into. If they
    later move the conda env, re-run jkw-obs-mcp-setup to re-render.
    """
    if python_path is None:
        python_path = sys.executable
    home = Path.home()
    return _PLIST_TEMPLATE.format(
        label=label,
        python_path=python_path,
        log_out=str(home / "Library" / "Logs" / f"{label}.log"),
        log_err=str(home / "Library" / "Logs" / f"{label}.err"),
    )

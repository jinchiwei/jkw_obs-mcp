"""launchd LaunchAgent management for the daily-review boot trigger.

This file defines the plist template renderer (works on any platform) and
the install/uninstall functions (Mac-only — Task 6 adds those). On Linux,
the install function is a no-op.
"""

from __future__ import annotations

import os
import platform
import subprocess
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


def _default_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def install_launchd_agent(*, plist_path: Path | None = None) -> dict[str, object]:
    """Render the plist, write it to LaunchAgents, and `launchctl bootstrap`.

    Idempotent: bootouts any existing instance first (ignoring failures, since
    'no such service' is fine on first install).

    No-op on non-Darwin platforms.
    """
    if platform.system() != "Darwin":
        return {"skipped": True, "reason": "non-darwin platform"}

    if plist_path is None:
        plist_path = _default_plist_path()

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(render_plist())

    target = f"gui/{os.getuid()}/{LABEL}"
    domain = f"gui/{os.getuid()}"

    # Idempotent cleanup of any prior instance. Failures here are expected
    # on first install (service not registered yet), so we ignore returncode.
    subprocess.run(
        ["launchctl", "bootout", target],
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        ["launchctl", "bootstrap", domain, str(plist_path)],
        capture_output=True,
        text=True,
    )
    return {
        "skipped": False,
        "plist_path": str(plist_path),
        "bootstrap_returncode": result.returncode,
        "stderr": result.stderr,
    }


def uninstall_launchd_agent(*, plist_path: Path | None = None) -> dict[str, object]:
    """`launchctl bootout` and remove the plist file. No-op on Linux."""
    if platform.system() != "Darwin":
        return {"skipped": True, "reason": "non-darwin platform"}

    if plist_path is None:
        plist_path = _default_plist_path()

    target = f"gui/{os.getuid()}/{LABEL}"
    result = subprocess.run(
        ["launchctl", "bootout", target],
        capture_output=True,
        text=True,
    )
    if plist_path.is_file():
        plist_path.unlink()
    return {
        "skipped": False,
        "bootout_returncode": result.returncode,
        "stderr": result.stderr,
    }

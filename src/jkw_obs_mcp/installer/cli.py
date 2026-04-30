"""jkw-obs-mcp-setup — platform-aware installer orchestrator.

Runs the shared setup steps unconditionally and Mac-only steps (Gmail OAuth,
launchd) only on Darwin. Idempotent: re-running on a configured machine
prints a clean status summary without overwriting anything.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from jkw_obs_mcp.config import detect_machine_id, load_machines
from jkw_obs_mcp.installer.bootstrap_brain_repo import bootstrap_brain_repo
from jkw_obs_mcp.installer.config_dir import create_config_dir
from jkw_obs_mcp.installer.gmail_oauth import gmail_oauth_setup
from jkw_obs_mcp.installer.launchd import install_launchd_agent
from jkw_obs_mcp.installer.machines_check import (
    current_hostname,
    is_hostname_registered,
)
from jkw_obs_mcp.installer.mcp_registration import register_mcp_server


def main() -> int:
    """Entry point for `jkw-obs-mcp-setup`."""
    plat = platform.system()
    print(f"Detected platform: {plat}")
    print(f"Python: {sys.executable}")
    print(f"Hostname: {current_hostname()}")
    print()

    status: dict[str, object] = {}

    print("Step 1: config dir")
    status["config_dir"] = create_config_dir()
    print(f"  → {status['config_dir']}")
    print()

    print("Step 2: machines.toml hostname")
    machines_toml = _find_machines_toml()
    hostname = current_hostname()
    if is_hostname_registered(machines_toml):
        status["machines"] = {"already_registered": True, "hostname": hostname}
        print(f"  → already registered: {hostname}")
    else:
        status["machines"] = {
            "already_registered": False,
            "hostname": hostname,
            "instruction": (
                f"Hostname {hostname!r} is not registered in {machines_toml}. "
                f"Add a [machine_id] block and re-run jkw-obs-mcp-setup."
            ),
        }
        print(f"  → not registered: {hostname}")
        print(f"    Add an entry to {machines_toml} and re-run setup.")
    print()

    if plat == "Darwin":
        print("Step 3: Gmail OAuth (Mac only)")
        status["gmail"] = gmail_oauth_setup()
        print(f"  → {status['gmail']}")
        if isinstance(status["gmail"], dict) and "walkthrough" in status["gmail"]:
            print()
            print(status["gmail"]["walkthrough"])
        print()

        print("Step 4: launchd boot trigger (Mac only)")
        status["launchd"] = install_launchd_agent()
        print(f"  → {status['launchd']}")
    else:
        print("Step 3: Gmail OAuth — skipped (Mac-only feature)")
        print("Step 4: launchd boot trigger — skipped (Mac-only feature)")
        status["gmail"] = {"skipped": True, "reason": f"non-darwin ({plat})"}
        status["launchd"] = {"skipped": True, "reason": f"non-darwin ({plat})"}

    # Step 5: brain repo bootstrap (all platforms)
    print("Step 5: brain repo bootstrap")
    machines_registry = load_machines(machines_toml)
    machine_id = detect_machine_id(
        machines_registry,
        hostname=current_hostname(),
        os_name=plat.lower(),
    )
    config_path = Path.home() / ".config" / "jkw-obs-mcp" / "config.toml"
    target_dir = Path.home() / "arcadia" / "jkw_obs-brain"
    status["brain_repo"] = bootstrap_brain_repo(
        brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
        target_dir=target_dir,
        machine_id=machine_id,
        config_path=config_path,
    )
    print(f"  → {status['brain_repo']}")
    print()

    # Step 6: MCP registration (all platforms)
    print("Step 6: MCP server registration with Claude Code")
    status["mcp_registration"] = register_mcp_server()
    print(f"  → {status['mcp_registration']}")
    print()

    print("Setup complete.")
    return 0


def _find_machines_toml() -> Path:
    """Walk up from this file to find the repo root, then return machines.toml.

    Falls back to ./machines.toml if no pyproject.toml ancestor is found
    (e.g., the package is installed but not from a source checkout).
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent / "machines.toml"
    return Path.cwd() / "machines.toml"


if __name__ == "__main__":
    sys.exit(main())

"""Step: validate that the running hostname is registered in machines.toml.

If absent, the installer prompts the user for a machine_id + os_type and
calls `append_hostname` to add a new block. We intentionally don't auto-
guess the machine_id — it's a deliberate human choice (e.g., 'fac' vs.
'fac-login01').
"""

from __future__ import annotations

import socket
import tomllib
from pathlib import Path


def current_hostname() -> str:
    """Return the short hostname (no FQDN suffix)."""
    return socket.gethostname().split(".")[0]


def is_hostname_registered(machines_toml: Path, *, hostname: str | None = None) -> bool:
    """True if `hostname` matches a machine_id or any hostname_aliases entry.

    Returns False (rather than raising) for missing or unparseable machines.toml.
    """
    if hostname is None:
        hostname = current_hostname()
    if not machines_toml.is_file():
        return False
    try:
        data = tomllib.loads(machines_toml.read_text())
    except tomllib.TOMLDecodeError:
        return False

    for machine_id, info in data.items():
        if machine_id == hostname:
            return True
        aliases = info.get("hostname_aliases", []) if isinstance(info, dict) else []
        if hostname in aliases:
            return True
    return False


def append_hostname(
    machines_toml: Path,
    *,
    machine_id: str,
    os_type: str,
    hostname: str | None = None,
) -> None:
    """Append a new `[machine_id]` block to machines.toml.

    Caller's responsibility to check `is_hostname_registered` first to avoid
    duplicate entries (TOML allows duplicate keys but most parsers reject).
    """
    if hostname is None:
        hostname = current_hostname()

    block = (
        f"\n[{machine_id}]\n"
        f'hostname_aliases = ["{hostname}"]\n'
        f'os = "{os_type}"\n'
    )
    with machines_toml.open("a") as f:
        f.write(block)

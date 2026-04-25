"""Configuration loading for jkw_obs_mcp."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Per-machine configuration loaded from config.toml."""

    vault_root: Path
    machine_id: str
    daily_review_enabled: bool = False


def load_config(path: Path) -> Config:
    """Load Config from a TOML file. Expands ~ in vault_root."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    paths = data.get("paths", {})
    machine = data.get("machine", {})
    generation = data.get("generation", {})

    vault_root_str = paths.get("vault_root", "")
    if not vault_root_str:
        raise ValueError(f"{path}: [paths].vault_root is required")
    vault_root = Path(vault_root_str).expanduser().resolve()

    machine_id = machine.get("id", "")
    if not machine_id:
        raise ValueError(f"{path}: [machine].id is required")

    return Config(
        vault_root=vault_root,
        machine_id=machine_id,
        daily_review_enabled=generation.get("daily_review_enabled", False),
    )


@dataclass(frozen=True)
class MachineEntry:
    """One machine in the registry."""

    machine_id: str
    hostname_aliases: list[str]
    os: str


class MachineRegistry:
    """Read-only mapping of machine_id -> MachineEntry."""

    def __init__(self, entries: dict[str, MachineEntry]) -> None:
        self._entries = entries

    def __contains__(self, machine_id: str) -> bool:
        return machine_id in self._entries

    def __getitem__(self, machine_id: str) -> MachineEntry:
        return self._entries[machine_id]

    def __iter__(self):
        return iter(self._entries.values())

    def items(self):
        return self._entries.items()


def load_machines(path: Path) -> MachineRegistry:
    """Load the machines.toml registry file."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    entries: dict[str, MachineEntry] = {}
    for machine_id, body in data.items():
        entries[machine_id] = MachineEntry(
            machine_id=machine_id,
            hostname_aliases=list(body.get("hostname_aliases", [])),
            os=body.get("os", ""),
        )
    return MachineRegistry(entries)

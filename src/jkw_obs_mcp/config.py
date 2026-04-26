"""Configuration loading for jkw_obs_mcp."""

from __future__ import annotations

import platform
import socket
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from jkw_obs_mcp.errors import UnknownMachineError


@dataclass(frozen=True)
class EmbeddingsConfig:
    """Embeddings backend configuration."""

    backend: str = "fastembed"
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    db_path: Path = Path("data/embeddings.db")


@dataclass(frozen=True)
class Config:
    """Per-machine configuration loaded from config.toml."""

    vault_root: Path
    machine_id: str
    daily_review_enabled: bool = False
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)


def load_config(path: Path) -> Config:
    """Load Config from a TOML file. Expands ~ in vault_root + db_path."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    paths = data.get("paths", {})
    machine = data.get("machine", {})
    generation = data.get("generation", {})
    emb = data.get("embeddings", {})

    vault_root_str = paths.get("vault_root", "")
    if not vault_root_str:
        raise ValueError(f"{path}: [paths].vault_root is required")
    vault_root = Path(vault_root_str).expanduser().resolve()

    machine_id = machine.get("id", "")
    if not machine_id:
        raise ValueError(f"{path}: [machine].id is required")

    # Embeddings section is optional — defaults from EmbeddingsConfig apply.
    db_path_str = emb.get("db_path", "data/embeddings.db")
    db_path = Path(db_path_str).expanduser()
    embeddings = EmbeddingsConfig(
        backend=emb.get("backend", "fastembed"),
        model=emb.get("model", "sentence-transformers/all-MiniLM-L6-v2"),
        db_path=db_path,
    )

    return Config(
        vault_root=vault_root,
        machine_id=machine_id,
        daily_review_enabled=generation.get("daily_review_enabled", False),
        embeddings=embeddings,
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


def detect_machine_id(
    registry: MachineRegistry,
    *,
    hostname: str | None = None,
    os_name: str | None = None,
) -> str:
    """Resolve the current machine's id from hostname + os.

    Hostname matching is CASE-SENSITIVE. os acts as a tiebreaker. Both args
    are optional for testability — if omitted, uses socket.gethostname() and
    platform.system().
    """
    if hostname is None:
        hostname = socket.gethostname()
        # Strip domain suffix e.g. "dreamingmachine.local" -> "dreamingmachine"
        hostname = hostname.split(".", 1)[0]
    if os_name is None:
        os_name = platform.system().lower()

    for entry in registry:
        if hostname in entry.hostname_aliases and entry.os == os_name:
            return entry.machine_id

    raise UnknownMachineError(hostname=hostname, os_name=os_name)

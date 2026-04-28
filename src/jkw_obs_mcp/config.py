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
    """Embeddings backend configuration.

    Default model: jinaai/jina-embeddings-v2-base-zh
      - 768-dim, ~640MB, 8192-token context, English+Chinese bilingual
      - Designed for mixed-language personal knowledge bases
      - In fastembed's catalog (drop-in via TextEmbedding)
    """

    backend: str = "fastembed"
    model: str = "jinaai/jina-embeddings-v2-base-zh"
    db_path: Path = Path("data/embeddings.db")


@dataclass(frozen=True)
class GenerationConfig:
    """Server-side LLM generation settings."""

    model: str = "claude-opus-4-7"
    daily_review_enabled: bool = False


@dataclass(frozen=True)
class Config:
    """Per-machine configuration loaded from config.toml."""

    vault_root: Path
    machine_id: str
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    # KEPT for backward compat with existing callers — points to generation.daily_review_enabled
    daily_review_enabled: bool = False


def load_config(path: Path) -> Config:
    """Load Config from a TOML file. Expands ~ in vault_root + db_path."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    paths = data.get("paths", {})
    machine = data.get("machine", {})
    gen = data.get("generation", {})
    emb = data.get("embeddings", {})

    vault_root_str = paths.get("vault_root", "")
    if not vault_root_str:
        raise ValueError(f"{path}: [paths].vault_root is required")
    vault_root = Path(vault_root_str).expanduser().resolve()

    machine_id = machine.get("id", "")
    if not machine_id:
        raise ValueError(f"{path}: [machine].id is required")

    # Generation section is optional — defaults from GenerationConfig apply.
    generation = GenerationConfig(
        model=gen.get("model", "claude-opus-4-7"),
        daily_review_enabled=gen.get("daily_review_enabled", False),
    )

    # Embeddings section is optional — defaults from EmbeddingsConfig apply.
    db_path_str = emb.get("db_path", "data/embeddings.db")
    db_path = Path(db_path_str).expanduser()
    embeddings = EmbeddingsConfig(
        backend=emb.get("backend", "fastembed"),
        model=emb.get("model", "jinaai/jina-embeddings-v2-base-zh"),
        db_path=db_path,
    )

    return Config(
        vault_root=vault_root,
        machine_id=machine_id,
        generation=generation,
        embeddings=embeddings,
        # Mirror generation.daily_review_enabled at top level for backward compat.
        daily_review_enabled=generation.daily_review_enabled,
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

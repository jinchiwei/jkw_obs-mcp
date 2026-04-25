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

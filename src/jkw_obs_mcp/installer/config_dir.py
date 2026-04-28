"""Step: create ~/.config/jkw-obs-mcp/ and scaffold .env if missing."""

from __future__ import annotations

import os
from pathlib import Path


def create_config_dir(
    *,
    config_dir: Path | None = None,
    env_example: Path | None = None,
) -> dict[str, bool]:
    """Create config dir if missing; scaffold .env from env_example if missing.

    Idempotent. Returns a status dict for the installer's final report:
      {
        "env_scaffolded": True if we wrote a new .env this run,
        "env_already_existed": True if a .env was already there,
      }
    """
    if config_dir is None:
        config_dir = Path.home() / ".config" / "jkw-obs-mcp"
    if env_example is None:
        # Resolve relative to repo root: src/jkw_obs_mcp/installer/config_dir.py
        # → up 4 → repo root.
        env_example = Path(__file__).resolve().parents[3] / ".env.example"

    config_dir.mkdir(parents=True, exist_ok=True)

    env_path = config_dir / ".env"
    if env_path.is_file():
        return {"env_scaffolded": False, "env_already_existed": True}

    if not env_example.is_file():
        return {"env_scaffolded": False, "env_already_existed": False}

    env_path.write_text(env_example.read_text())
    os.chmod(env_path, 0o600)
    return {"env_scaffolded": True, "env_already_existed": False}

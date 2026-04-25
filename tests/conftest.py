"""Shared pytest fixtures."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    """Empty temp dir to stand in for ~/.config/jkw-obs-mcp/."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    return cfg


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Temp vault root with a tiny tree of fixture markdown files."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Admin").mkdir()
    (vault / "Admin" / "Saiyan.md").write_text("# Saiyan\nworkout log\n")
    (vault / "kb").mkdir()
    (vault / "kb" / "dreamingmachine").mkdir()
    return vault


@pytest.fixture
def tmp_machines_toml(tmp_path: Path) -> Path:
    """Minimal machines.toml for tests."""
    p = tmp_path / "machines.toml"
    p.write_text(
        """
[dreamingmachine]
hostname_aliases = ["dreamingmachine"]
os = "darwin"

[scs]
hostname_aliases = ["callosum"]
os = "linux"

[teal]
hostname_aliases = ["mxj-tealitx"]
os = "linux"
"""
    )
    return p

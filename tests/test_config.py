from pathlib import Path

import pytest

from jkw_obs_mcp.config import Config, load_config


def test_load_config_from_toml(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[paths]
vault_root = "/some/vault"

[machine]
id = "dreamingmachine"

[generation]
daily_review_enabled = true
"""
    )

    cfg = load_config(cfg_file)

    assert isinstance(cfg, Config)
    assert cfg.vault_root == Path("/some/vault")
    assert cfg.machine_id == "dreamingmachine"
    assert cfg.daily_review_enabled is True


def test_load_config_expands_home_in_vault_root(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[paths]
vault_root = "~/vault"

[machine]
id = "dreamingmachine"
"""
    )

    cfg = load_config(cfg_file)

    assert "~" not in str(cfg.vault_root)
    assert str(cfg.vault_root).endswith("/vault")

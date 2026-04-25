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


from jkw_obs_mcp.config import MachineRegistry, load_machines


def test_load_machines_returns_registry(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)

    assert isinstance(registry, MachineRegistry)
    assert "dreamingmachine" in registry
    assert "scs" in registry
    assert "teal" in registry

    dm = registry["dreamingmachine"]
    assert dm.hostname_aliases == ["dreamingmachine"]
    assert dm.os == "darwin"

    teal = registry["teal"]
    assert teal.hostname_aliases == ["mxj-tealitx"]
    assert teal.os == "linux"


def test_load_machines_lookup_by_id_raises_on_missing(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)
    import pytest as _pytest
    with _pytest.raises(KeyError):
        registry["nonexistent"]

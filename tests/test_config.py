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


from jkw_obs_mcp.config import detect_machine_id
from jkw_obs_mcp.errors import UnknownMachineError


def test_detect_dreamingmachine_on_mac(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)
    machine_id = detect_machine_id(
        registry, hostname="dreamingmachine", os_name="darwin"
    )
    assert machine_id == "dreamingmachine"


def test_detect_scs_on_linux(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)
    machine_id = detect_machine_id(registry, hostname="callosum", os_name="linux")
    assert machine_id == "scs"


def test_detect_is_case_sensitive(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)
    # tealw alias is "mxj-tealitx" lowercase — uppercase should NOT match.
    with pytest.raises(UnknownMachineError):
        detect_machine_id(registry, hostname="MXJ-TEALITX", os_name="linux")


def test_detect_uses_os_as_tiebreaker(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)
    # dreamingmachine is os=darwin; same hostname on linux must NOT match.
    with pytest.raises(UnknownMachineError):
        detect_machine_id(registry, hostname="dreamingmachine", os_name="linux")


def test_detect_raises_unknown_machine_on_no_match(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)
    with pytest.raises(UnknownMachineError) as excinfo:
        detect_machine_id(registry, hostname="random-laptop", os_name="darwin")
    assert excinfo.value.hostname == "random-laptop"
    assert excinfo.value.os_name == "darwin"


def test_load_config_includes_embeddings_section(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[paths]
vault_root = "/some/vault"

[machine]
id = "dreamingmachine"

[embeddings]
backend = "fastembed"
model = "sentence-transformers/all-MiniLM-L6-v2"
db_path = "~/data/embeddings.db"
"""
    )

    cfg = load_config(cfg_file)

    assert cfg.embeddings.backend == "fastembed"
    assert cfg.embeddings.model == "sentence-transformers/all-MiniLM-L6-v2"
    assert "~" not in str(cfg.embeddings.db_path)


def test_load_config_uses_embeddings_defaults_when_section_absent(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[paths]
vault_root = "/some/vault"

[machine]
id = "dreamingmachine"
"""
    )

    cfg = load_config(cfg_file)

    assert cfg.embeddings.backend == "fastembed"
    assert cfg.embeddings.model == "jinaai/jina-embeddings-v2-base-zh"
    # default db_path is under <repo_root>/data/embeddings.db
    assert str(cfg.embeddings.db_path).endswith("data/embeddings.db")


def test_load_config_includes_generation_section(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[paths]
vault_root = "/some/vault"

[machine]
id = "dreamingmachine"

[generation]
model = "claude-opus-4-7"
"""
    )

    cfg = load_config(cfg_file)

    assert cfg.generation.model == "claude-opus-4-7"


def test_load_config_uses_generation_defaults_when_section_absent(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[paths]
vault_root = "/some/vault"

[machine]
id = "dreamingmachine"
"""
    )

    cfg = load_config(cfg_file)

    # Default model is current production-ready Claude
    assert cfg.generation.model == "claude-opus-4-7"
    # daily_review_enabled stays at the existing default
    assert cfg.generation.daily_review_enabled is False

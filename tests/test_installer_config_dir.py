"""Tests for installer.config_dir step."""

from __future__ import annotations

from pathlib import Path

from jkw_obs_mcp.installer.config_dir import create_config_dir


def test_creates_config_dir_when_missing(tmp_path):
    cfg = tmp_path / "cfg"
    env_example = tmp_path / "env_example"
    env_example.write_text("ANTHROPIC_API_KEY=...\n")

    status = create_config_dir(config_dir=cfg, env_example=env_example)

    assert cfg.is_dir()
    assert (cfg / ".env").is_file()
    assert status["env_scaffolded"] is True
    assert status["env_already_existed"] is False


def test_chmod_600_on_scaffolded_env(tmp_path):
    cfg = tmp_path / "cfg"
    env_example = tmp_path / "env_example"
    env_example.write_text("KEY=val\n")

    create_config_dir(config_dir=cfg, env_example=env_example)

    mode = (cfg / ".env").stat().st_mode & 0o777
    assert mode == 0o600


def test_idempotent_when_dir_already_exists(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / ".env").write_text("EXISTING=true\n")
    env_example = tmp_path / "env_example"
    env_example.write_text("DIFFERENT=value\n")

    status = create_config_dir(config_dir=cfg, env_example=env_example)

    # .env was preserved, NOT overwritten
    assert (cfg / ".env").read_text() == "EXISTING=true\n"
    assert status["env_scaffolded"] is False
    assert status["env_already_existed"] is True


def test_handles_missing_env_example_gracefully(tmp_path):
    """If .env.example is absent (e.g., running from a non-repo install),
    create the dir but skip env scaffolding rather than crashing."""
    cfg = tmp_path / "cfg"
    env_example = tmp_path / "does-not-exist"

    status = create_config_dir(config_dir=cfg, env_example=env_example)

    assert cfg.is_dir()
    assert not (cfg / ".env").exists()
    assert status["env_scaffolded"] is False
    assert status["env_already_existed"] is False

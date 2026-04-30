"""Tests for installer.bootstrap_brain_repo."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from jkw_obs_mcp.installer.bootstrap_brain_repo import bootstrap_brain_repo


def _fake_run_success():
    """All git subcommands return rc=0."""
    def fake_run(args, **kwargs):
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()
    return fake_run


def test_creates_arcadia_dir_if_missing(tmp_path):
    target = tmp_path / "arcadia" / "jkw_obs-brain"
    config = tmp_path / "config.toml"
    assert not target.parent.exists()

    with patch("jkw_obs_mcp.installer.bootstrap_brain_repo.subprocess.run",
               side_effect=_fake_run_success()):
        bootstrap_brain_repo(
            brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
            target_dir=target,
            machine_id="scs",
            config_path=config,
        )

    assert target.parent.is_dir()


def test_clones_when_target_dir_missing(tmp_path):
    target = tmp_path / "arcadia" / "jkw_obs-brain"
    config = tmp_path / "config.toml"
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.bootstrap_brain_repo.subprocess.run",
               side_effect=fake_run):
        result = bootstrap_brain_repo(
            brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
            target_dir=target,
            machine_id="scs",
            config_path=config,
        )

    # Find the clone call (args[3] is target dir position; just check substring)
    assert any("clone" in args and str(target) in args for args in runs)
    assert result["cloned"] is True
    assert result["pulled"] is False


def test_pulls_when_target_dir_exists(tmp_path):
    target = tmp_path / "arcadia" / "jkw_obs-brain"
    target.mkdir(parents=True)
    (target / ".git").mkdir()  # mark it as an existing git repo
    config = tmp_path / "config.toml"
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.bootstrap_brain_repo.subprocess.run",
               side_effect=fake_run):
        result = bootstrap_brain_repo(
            brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
            target_dir=target,
            machine_id="scs",
            config_path=config,
        )

    assert not any("clone" in args for args in runs)
    assert any("pull" in args for args in runs)
    assert result["cloned"] is False
    assert result["pulled"] is True


def test_writes_config_toml_if_missing(tmp_path):
    target = tmp_path / "arcadia" / "jkw_obs-brain"
    config = tmp_path / "config.toml"

    with patch("jkw_obs_mcp.installer.bootstrap_brain_repo.subprocess.run",
               side_effect=_fake_run_success()):
        result = bootstrap_brain_repo(
            brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
            target_dir=target,
            machine_id="scs",
            config_path=config,
        )

    assert config.is_file()
    content = config.read_text()
    assert 'vault_root = "' in content
    assert "jkw_obs-brain" in content
    assert 'id = "scs"' in content
    assert result["config_written"] is True


def test_leaves_existing_config_toml_alone(tmp_path):
    target = tmp_path / "arcadia" / "jkw_obs-brain"
    config = tmp_path / "config.toml"
    config.write_text('# existing config\n[paths]\nvault_root = "/custom/path"\n')

    with patch("jkw_obs_mcp.installer.bootstrap_brain_repo.subprocess.run",
               side_effect=_fake_run_success()):
        result = bootstrap_brain_repo(
            brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
            target_dir=target,
            machine_id="scs",
            config_path=config,
        )

    # Existing content preserved
    content = config.read_text()
    assert "# existing config" in content
    assert "/custom/path" in content
    assert result["config_written"] is False
    assert result["config_already_existed"] is True


def test_clone_failure_returns_error(tmp_path):
    target = tmp_path / "arcadia" / "jkw_obs-brain"
    config = tmp_path / "config.toml"

    def fake_run(args, **kwargs):
        class R:
            returncode = 1 if "clone" in args else 0
            stderr = "permission denied" if "clone" in args else ""
            stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.bootstrap_brain_repo.subprocess.run",
               side_effect=fake_run):
        result = bootstrap_brain_repo(
            brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
            target_dir=target,
            machine_id="scs",
            config_path=config,
        )

    assert result["cloned"] is False
    assert result["error"] is not None
    assert "permission" in result["error"].lower() or "clone" in result["error"].lower()
    # config.toml NOT written when clone failed (the brain repo isn't there)
    assert not config.exists()

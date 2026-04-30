"""Bootstrap the brain repo on a fresh cluster: clone-or-pull + write config.toml.

Idempotent. Re-running on a configured cluster is a no-op (pull instead of clone,
preserve existing config.toml). Returns a status dict for the installer's final
report.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def bootstrap_brain_repo(
    *,
    brain_repo_url: str,
    target_dir: Path,
    machine_id: str,
    config_path: Path,
    sparse_paths: list[str] | None = None,
) -> dict:
    """Clone or pull the brain repo, then write config.toml if missing.

    target_dir is the absolute path where the brain repo lives (e.g.,
    ~/arcadia/jkw_obs-brain). Parent dirs are created if missing.

    sparse_paths: if provided as a non-empty list, perform a sparse-checkout
    clone — git clone --no-checkout, then sparse-checkout init --no-cone,
    then sparse-checkout set <paths>, then checkout. Only the specified paths
    materialize in the working tree; other paths exist in git history but not
    on disk. Use for monitored environments (cdx) where personal paths in the
    brain repo (Ephesus, dm, daily reviews, email digests) must not be
    physically present.

    Re-runs on an existing clone always do `git pull --ff-only` regardless of
    sparse_paths — the sparse-checkout pattern persists in .git/info/.

    Returns:
      {
        "cloned": bool,                   # True if we just cloned
        "pulled": bool,                   # True if we pulled an existing clone
        "config_written": bool,           # True if config.toml was created
        "config_already_existed": bool,   # True if config.toml was preserved
        "error": str | None,              # populated on git failure
      }
    """
    result: dict = {
        "cloned": False,
        "pulled": False,
        "config_written": False,
        "config_already_existed": False,
        "error": None,
    }

    target_dir.parent.mkdir(parents=True, exist_ok=True)

    use_sparse = bool(sparse_paths)

    if (target_dir / ".git").is_dir():
        pull = subprocess.run(
            ["git", "-C", str(target_dir), "pull", "--ff-only"],
            capture_output=True, text=True,
        )
        if pull.returncode != 0:
            result["error"] = f"git pull failed: {pull.stderr.strip()}"
            return result
        result["pulled"] = True
    elif use_sparse:
        clone = subprocess.run(
            ["git", "clone", "--no-checkout", brain_repo_url, str(target_dir)],
            capture_output=True, text=True,
        )
        if clone.returncode != 0:
            result["error"] = f"git clone failed: {clone.stderr.strip()}"
            return result
        init = subprocess.run(
            ["git", "-C", str(target_dir), "sparse-checkout", "init", "--no-cone"],
            capture_output=True, text=True,
        )
        if init.returncode != 0:
            result["error"] = f"sparse-checkout init failed: {init.stderr.strip()}"
            return result
        sset = subprocess.run(
            ["git", "-C", str(target_dir), "sparse-checkout", "set", *sparse_paths],
            capture_output=True, text=True,
        )
        if sset.returncode != 0:
            result["error"] = f"sparse-checkout set failed: {sset.stderr.strip()}"
            return result
        co = subprocess.run(
            ["git", "-C", str(target_dir), "checkout"],
            capture_output=True, text=True,
        )
        if co.returncode != 0:
            result["error"] = f"git checkout failed: {co.stderr.strip()}"
            return result
        result["cloned"] = True
    else:
        clone = subprocess.run(
            ["git", "clone", brain_repo_url, str(target_dir)],
            capture_output=True, text=True,
        )
        if clone.returncode != 0:
            result["error"] = f"git clone failed: {clone.stderr.strip()}"
            return result
        result["cloned"] = True

    if config_path.is_file():
        result["config_already_existed"] = True
        return result

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_render_config_toml(
        vault_root=target_dir,
        machine_id=machine_id,
    ))
    result["config_written"] = True
    return result


def _render_config_toml(*, vault_root: Path, machine_id: str) -> str:
    """Render a minimal config.toml for a fresh cluster.

    Schema must match what jkw_obs_mcp.config.load_config expects:
      [paths] vault_root = "..."
      [machine] id = "..."
      [embeddings] model = "jinaai/jina-embeddings-v2-base-zh"
      [generation] daily_review_enabled = false
    """
    return (
        f'[paths]\n'
        f'vault_root = "{vault_root}"\n'
        f'\n'
        f'[machine]\n'
        f'id = "{machine_id}"\n'
        f'\n'
        f'[generation]\n'
        f'daily_review_enabled = false\n'
        f'\n'
        f'[embeddings]\n'
        f'model = "jinaai/jina-embeddings-v2-base-zh"\n'
    )

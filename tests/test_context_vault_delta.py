"""VaultDelta tests — files modified since a timestamp."""

import datetime as dt
import os
import time
from pathlib import Path

from jkw_obs_mcp.context.vault_delta import vault_delta_since


def test_returns_files_newer_than_cutoff(tmp_vault):
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(hours=24)
    deltas = vault_delta_since(tmp_vault, since=cutoff)

    paths = {d.rel_path for d in deltas}
    assert "Admin/Saiyan.md" in paths


def test_skips_files_older_than_cutoff(tmp_vault, tmp_path):
    """Backdate Admin/Saiyan.md by 30 days; should not appear."""
    saiyan = tmp_vault / "Admin" / "Saiyan.md"
    old_time = time.time() - 30 * 24 * 3600
    os.utime(saiyan, (old_time, old_time))

    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    deltas = vault_delta_since(tmp_vault, since=cutoff)

    paths = {d.rel_path for d in deltas}
    assert "Admin/Saiyan.md" not in paths


def test_skips_obsidian_and_trash(tmp_vault):
    """Same skip-dir convention as the indexer's walker."""
    (tmp_vault / ".obsidian").mkdir(exist_ok=True)
    (tmp_vault / ".obsidian" / "config.md").write_text("plugin config")
    (tmp_vault / ".trash").mkdir(exist_ok=True)
    (tmp_vault / ".trash" / "old.md").write_text("trashed")

    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(hours=24)
    deltas = vault_delta_since(tmp_vault, since=cutoff)

    paths = {d.rel_path for d in deltas}
    assert all(not p.startswith(".obsidian/") for p in paths)
    assert all(not p.startswith(".trash/") for p in paths)

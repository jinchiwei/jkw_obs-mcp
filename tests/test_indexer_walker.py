from pathlib import Path

import pytest

from jkw_obs_mcp.indexer.walker import VaultEntry, walk_vault


def test_walk_vault_yields_md_files(tmp_vault):
    entries = list(walk_vault(tmp_vault))

    paths = {e.rel_path for e in entries}
    assert "Admin/Saiyan.md" in paths


def test_walk_vault_returns_content_hashes(tmp_vault):
    entries = list(walk_vault(tmp_vault))
    saiyan = next(e for e in entries if e.rel_path == "Admin/Saiyan.md")
    assert isinstance(saiyan, VaultEntry)
    assert len(saiyan.content_hash) == 64  # sha256 hex digest length
    # Same file twice should hash identically
    again = next(e for e in walk_vault(tmp_vault) if e.rel_path == "Admin/Saiyan.md")
    assert saiyan.content_hash == again.content_hash


def test_walk_vault_skips_obsidian_and_trash(tmp_vault):
    # Add a few files we should NOT walk.
    (tmp_vault / ".obsidian").mkdir(exist_ok=True)
    (tmp_vault / ".obsidian" / "workspace.json").write_text("{}")
    (tmp_vault / ".trash").mkdir(exist_ok=True)
    (tmp_vault / ".trash" / "old.md").write_text("# old")
    (tmp_vault / ".git").mkdir(exist_ok=True)
    (tmp_vault / ".git" / "HEAD").write_text("ref: ...")

    paths = {e.rel_path for e in walk_vault(tmp_vault)}

    assert all(not p.startswith(".obsidian/") for p in paths)
    assert all(not p.startswith(".trash/") for p in paths)
    assert all(not p.startswith(".git/") for p in paths)


def test_walk_vault_only_md_files(tmp_vault):
    (tmp_vault / "scratch.txt").write_text("not markdown")

    paths = {e.rel_path for e in walk_vault(tmp_vault)}

    assert all(p.endswith(".md") for p in paths)

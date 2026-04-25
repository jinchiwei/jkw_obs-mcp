from pathlib import Path

import pytest

from jkw_obs_mcp.adapter.vault import VaultAdapter


def test_read_note_returns_content(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    content = adapter.read_note("Admin/Saiyan.md")

    assert "workout log" in content
    assert content.startswith("# Saiyan")


def test_read_note_rejects_path_traversal(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    from jkw_obs_mcp.errors import SandboxViolationError

    with pytest.raises(SandboxViolationError):
        adapter.read_note("../../../etc/passwd")


def test_list_notes_returns_relative_paths(tmp_vault):
    # Add a few more files to make this interesting.
    (tmp_vault / "Arcadia").mkdir()
    (tmp_vault / "Arcadia" / "lab-meeting.md").write_text("# Lab Meeting\n")

    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    notes = adapter.list_notes()

    paths = sorted(str(p) for p in notes)
    assert "Admin/Saiyan.md" in paths
    assert "Arcadia/lab-meeting.md" in paths
    # Only .md files
    assert all(p.endswith(".md") for p in paths)


def test_list_notes_filters_by_subdir(tmp_vault):
    (tmp_vault / "Arcadia").mkdir()
    (tmp_vault / "Arcadia" / "lab-meeting.md").write_text("# Lab Meeting\n")

    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    notes = adapter.list_notes(subdir="Admin")

    paths = sorted(str(p) for p in notes)
    assert paths == ["Admin/Saiyan.md"]

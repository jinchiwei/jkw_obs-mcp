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


def test_write_kb_note_writes_to_machine_subfolder(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    written = adapter.write_kb_note(
        filename="2026-04-25.md",
        content="# Today\n- ate cake\n",
        subdir="daily",
    )

    expected = tmp_vault / "kb" / "dreamingmachine" / "daily" / "2026-04-25.md"
    assert written == expected
    assert expected.read_text() == "# Today\n- ate cake\n"


def test_write_kb_note_creates_subdir_if_missing(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    adapter.write_kb_note(filename="x.md", content="hi", subdir="ad-hoc/deep/nested")

    assert (
        tmp_vault / "kb" / "dreamingmachine" / "ad-hoc" / "deep" / "nested" / "x.md"
    ).read_text() == "hi"


def test_write_kb_note_rejects_traversal_in_filename(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    from jkw_obs_mcp.errors import SandboxViolationError

    with pytest.raises(SandboxViolationError):
        adapter.write_kb_note(
            filename="../../../etc/evil.md", content="x", subdir="ad-hoc"
        )


def test_write_kb_note_rejects_traversal_in_subdir(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    from jkw_obs_mcp.errors import SandboxViolationError

    with pytest.raises(SandboxViolationError):
        adapter.write_kb_note(filename="x.md", content="x", subdir="../mac")


def test_write_kb_note_rejects_writing_to_other_machines_folder(tmp_vault):
    """SCS shouldn't be able to write to kb/dreamingmachine/."""
    (tmp_vault / "kb" / "scs").mkdir()
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="scs")

    from jkw_obs_mcp.errors import SandboxViolationError

    # Even if subdir = "../dreamingmachine/daily", resolution must keep us in kb/scs/.
    with pytest.raises(SandboxViolationError):
        adapter.write_kb_note(
            filename="x.md", content="x", subdir="../dreamingmachine/daily"
        )

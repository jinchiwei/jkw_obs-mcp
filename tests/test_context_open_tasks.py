"""Tests for load_open_tasks()."""

from jkw_obs_mcp.context.open_tasks import load_open_tasks


def test_returns_none_when_tasks_dir_missing(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    assert load_open_tasks(vault) is None


def test_returns_none_when_tasks_dir_empty(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Tasks").mkdir(parents=True)
    assert load_open_tasks(vault) is None


def test_returns_none_when_only_completed_tasks(tmp_path):
    vault = tmp_path / "vault"
    tasks = vault / "Tasks"
    tasks.mkdir(parents=True)
    (tasks / "Inbox.md").write_text("- [x] Done\n- [x] Also done\n")
    assert load_open_tasks(vault) is None


def test_extracts_open_task_lines_grouped_by_file(tmp_path):
    vault = tmp_path / "vault"
    tasks = vault / "Tasks"
    tasks.mkdir(parents=True)
    (tasks / "Inbox.md").write_text(
        "- [ ] Buy groceries\n- [x] Done thing\n- [ ] Submit MCAT 🔺\n"
    )
    (tasks / "Arcadia.md").write_text("- [ ] RSNA Abstract 🔺\n")

    result = load_open_tasks(vault)

    assert result is not None
    assert "### Tasks/Inbox.md" in result
    assert "### Tasks/Arcadia.md" in result
    assert "Buy groceries" in result
    assert "Submit MCAT 🔺" in result
    assert "RSNA Abstract 🔺" in result
    # Done tasks are filtered
    assert "Done thing" not in result


def test_skips_mission_log_query_file(tmp_path):
    """Mission Log.md is just Tasks-plugin queries, not actual tasks."""
    vault = tmp_path / "vault"
    tasks = vault / "Tasks"
    tasks.mkdir(parents=True)
    (tasks / "Mission Log.md").write_text(
        "## Open\n```tasks\nnot done\n```\n- [ ] this should be skipped\n"
    )
    (tasks / "Inbox.md").write_text("- [ ] real task\n")

    result = load_open_tasks(vault)

    assert result is not None
    assert "Mission Log" not in result
    assert "real task" in result
    assert "this should be skipped" not in result


def test_preserves_indented_subtasks(tmp_path):
    vault = tmp_path / "vault"
    tasks = vault / "Tasks"
    tasks.mkdir(parents=True)
    (tasks / "Arcadia.md").write_text(
        "- [ ] Big task\n  - [ ] Subtask 1\n  - [ ] Subtask 2\n"
    )

    result = load_open_tasks(vault)

    assert result is not None
    assert "- [ ] Big task" in result
    assert "  - [ ] Subtask 1" in result
    assert "  - [ ] Subtask 2" in result

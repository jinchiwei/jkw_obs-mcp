"""Tests for load_mission_log()."""

from jkw_obs_mcp.context.mission_log import load_mission_log


def test_returns_contents_when_file_exists(tmp_path):
    vault = tmp_path / "vault"
    tasks = vault / "Tasks"
    tasks.mkdir(parents=True)
    (tasks / "Mission Log.md").write_text("# Mission Log\n\n- [ ] Buy groceries\n- [ ] Submit MCAT")

    content = load_mission_log(vault)

    assert content is not None
    assert "Buy groceries" in content
    assert "Submit MCAT" in content


def test_returns_none_when_missing(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    assert load_mission_log(vault) is None


def test_returns_none_when_tasks_dir_exists_but_no_file(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Tasks").mkdir(parents=True)
    assert load_mission_log(vault) is None

"""Tests for learnings.recorder._commit_and_push (mocked subprocess)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from jkw_obs_mcp.learnings.recorder import _commit_and_push


def _fake_runner(returncodes_by_subcmd):
    """Build a fake subprocess.run.

    `returncodes_by_subcmd` is a list of (subcmd_substring, returncode, stderr) tuples.
    Each call matches the FIRST tuple whose substring is in the args, then is removed.
    """
    pending = list(returncodes_by_subcmd)

    def fake_run(args, **kwargs):
        joined = " ".join(args)
        for i, (sub, rc, err) in enumerate(pending):
            if sub in joined:
                pending.pop(i)
                class R:
                    returncode = rc
                    stderr = err
                    stdout = ""
                return R()
        # Default: success
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    return fake_run


def test_happy_path_push_succeeds(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    file_path = vault / "kb" / "dreamingmachine" / "learnings" / "constraints" / "2026-04-28-test.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("# test")

    fake = _fake_runner([
        ("add", 0, ""),
        ("commit", 0, ""),
        ("push", 0, ""),
    ])

    with patch("jkw_obs_mcp.learnings.recorder.subprocess.run", side_effect=fake):
        pushed, reason = _commit_and_push(
            vault_root=vault, file_path=file_path, title="test"
        )

    assert pushed is True
    assert reason is None


def test_push_conflict_then_retry_succeeds(tmp_path):
    """First push fails (conflict), pull --rebase succeeds, retry push succeeds."""
    vault = tmp_path / "vault"
    vault.mkdir()
    file_path = vault / "kb" / "dreamingmachine" / "learnings" / "constraints" / "2026-04-28-test.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("# test")

    subcmds = []  # track git subcommands (not full arg strings) to avoid path substring collisions

    def fake_run(args, **kwargs):
        # args[0]="git", args[1]="-C", args[2]=vault, args[3]=subcommand ...
        subcmd = args[3] if len(args) > 3 else ""
        subcmds.append(subcmd)
        # First push fails; all other calls succeed
        if subcmd == "push" and subcmds.count("push") == 1:
            class R: returncode = 1; stderr = "fast-forward rejected"; stdout = ""
            return R()
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.learnings.recorder.subprocess.run", side_effect=fake_run):
        pushed, reason = _commit_and_push(
            vault_root=vault, file_path=file_path, title="test"
        )

    assert pushed is True
    assert reason is None
    # Sequence: add, commit, push (fail), pull --rebase, push (succeed)
    assert subcmds.count("push") == 2
    assert any(s == "pull" for s in subcmds)


def test_push_fails_twice_returns_false_with_reason(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    file_path = vault / "kb" / "dreamingmachine" / "learnings" / "constraints" / "2026-04-28-test.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("# test")

    fake = _fake_runner([
        ("add", 0, ""),
        ("commit", 0, ""),
        ("push", 1, "fast-forward rejected"),
        ("rebase", 0, ""),
        ("push", 1, "still rejected"),
    ])

    with patch("jkw_obs_mcp.learnings.recorder.subprocess.run", side_effect=fake):
        pushed, reason = _commit_and_push(
            vault_root=vault, file_path=file_path, title="test"
        )

    assert pushed is False
    assert reason is not None
    assert "rejected" in reason.lower() or "push" in reason.lower()


def test_pull_rebase_failure_returns_false(tmp_path):
    """If pull --rebase itself fails (e.g., merge conflict), give up gracefully."""
    vault = tmp_path / "vault"
    vault.mkdir()
    file_path = vault / "kb" / "dreamingmachine" / "learnings" / "constraints" / "2026-04-28-test.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("# test")

    fake = _fake_runner([
        ("add", 0, ""),
        ("commit", 0, ""),
        ("push", 1, "rejected"),
        ("rebase", 1, "merge conflict"),
    ])

    with patch("jkw_obs_mcp.learnings.recorder.subprocess.run", side_effect=fake):
        pushed, reason = _commit_and_push(
            vault_root=vault, file_path=file_path, title="test"
        )

    assert pushed is False
    assert reason is not None
    assert "rebase" in reason.lower() or "conflict" in reason.lower()


def test_commit_failure_returns_false_no_push_attempted(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    file_path = vault / "kb" / "dreamingmachine" / "learnings" / "constraints" / "2026-04-28-test.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("# test")

    subcmds = []  # track git subcommands to avoid path substring collisions

    def fake_run(args, **kwargs):
        subcmd = args[3] if len(args) > 3 else ""
        subcmds.append(subcmd)
        if subcmd == "commit":
            class R: returncode = 1; stderr = "nothing to commit"; stdout = ""
            return R()
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.learnings.recorder.subprocess.run", side_effect=fake_run):
        pushed, reason = _commit_and_push(
            vault_root=vault, file_path=file_path, title="test"
        )

    assert pushed is False
    assert "commit" in reason.lower()
    # Push never attempted
    assert "push" not in subcmds


def test_commit_message_uses_title(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    file_path = vault / "kb" / "dreamingmachine" / "learnings" / "constraints" / "2026-04-28-test.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("# test")

    captured = []

    def fake_run(args, **kwargs):
        captured.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.learnings.recorder.subprocess.run", side_effect=fake_run):
        _commit_and_push(
            vault_root=vault, file_path=file_path, title="UCSF Versa requires VPN"
        )

    # Find the commit call and check its -m argument
    commit_call = next(args for args in captured if "commit" in args)
    msg_idx = commit_call.index("-m")
    assert "kb: UCSF Versa requires VPN" == commit_call[msg_idx + 1]

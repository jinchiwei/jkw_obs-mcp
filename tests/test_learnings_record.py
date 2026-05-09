"""Tests for learnings.recorder.record_learning end-to-end (mocked deps)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jkw_obs_mcp.learnings.recorder import LearningResult, record_learning


@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    return v


def _patch_io_layer(*, push_succeeds=True):
    """Standard patch set: subprocess git ops always succeed by default.

    Inspects args[3] (git subcommand) directly — substring-matching the joined
    args breaks because tmp_path contains the test function name, which can
    contain "push" / "commit" / etc.
    """
    def fake_run(args, **kwargs):
        # args = ["git", "-C", vault_root, <subcmd>, ...]
        subcmd = args[3] if len(args) > 3 else ""
        class R: returncode = 0; stderr = ""; stdout = ""
        if subcmd == "push" and not push_succeeds:
            R.returncode = 1
            R.stderr = "rejected"
        return R()
    return patch("jkw_obs_mcp.learnings.recorder.subprocess.run", side_effect=fake_run)


def test_invalid_category_raises(vault):
    fake_indexer = MagicMock()
    with pytest.raises(ValueError, match="invalid category"):
        record_learning(
            category="bogus",
            title="some title",
            content="some content " * 10,
            tags=[],
            applies_to=[],
            vault_root=vault,
            machine_id="dreamingmachine",
            indexer=fake_indexer,
        )


def test_short_title_raises(vault):
    fake_indexer = MagicMock()
    with pytest.raises(ValueError, match="title"):
        record_learning(
            category="constraints",
            title="ab",
            content="x" * 100,
            tags=[],
            applies_to=[],
            vault_root=vault,
            machine_id="dreamingmachine",
            indexer=fake_indexer,
        )


def test_short_content_raises(vault):
    fake_indexer = MagicMock()
    with pytest.raises(ValueError, match="content"):
        record_learning(
            category="constraints",
            title="some title",
            content="too short",
            tags=[],
            applies_to=[],
            vault_root=vault,
            machine_id="dreamingmachine",
            indexer=fake_indexer,
        )


def test_unicode_only_title_raises(vault):
    """Title that produces empty slug is invalid."""
    fake_indexer = MagicMock()
    with pytest.raises(ValueError, match="slug"):
        record_learning(
            category="constraints",
            title="自我提升",
            content="x" * 100,
            tags=[],
            applies_to=[],
            vault_root=vault,
            machine_id="dreamingmachine",
            indexer=fake_indexer,
        )


def test_newline_in_title_raises(vault):
    """A newline in the title would break frontmatter — orchestrator rejects."""
    fake_indexer = MagicMock()
    with pytest.raises(ValueError, match="newline"):
        record_learning(
            category="constraints",
            title="some\ntitle",
            content="x" * 100,
            tags=[],
            applies_to=[],
            vault_root=vault,
            machine_id="dreamingmachine",
            indexer=fake_indexer,
        )


def test_results_category_accepts_short_content(vault):
    """`results` category is for terse metric snapshots — no 50-char minimum."""
    fake_indexer = MagicMock()

    with _patch_io_layer():
        result = record_learning(
            category="results",
            title="bact 3-site fold AUC",
            content="0.976",
            tags=["bact"],
            applies_to=[],
            vault_root=vault,
            machine_id="dreamingmachine",
            indexer=fake_indexer,
        )

    assert result.written is True
    assert result.path.is_file()
    assert "kb/dreamingmachine/learnings/results" in str(result.path)
    assert result.path.name.endswith("-bact-3-site-fold-auc.md")
    body = result.path.read_text()
    assert "0.976" in body


def test_short_content_still_rejected_for_non_results_categories(vault):
    """Short content is only allowed for `results`; other categories require 50+ chars."""
    fake_indexer = MagicMock()
    for cat in ("constraints", "decisions", "postmortems"):
        with pytest.raises(ValueError, match="content"):
            record_learning(
                category=cat,
                title="some title",
                content="too short",
                tags=[],
                applies_to=[],
                vault_root=vault,
                machine_id="dreamingmachine",
                indexer=fake_indexer,
            )


def test_happy_path_writes_file_and_returns_pushed_true(vault):
    fake_indexer = MagicMock()

    with _patch_io_layer():
        result = record_learning(
            category="constraints",
            title="UCSF Versa requires VPN",
            content="full content " * 10,
            tags=["ucsf", "versa"],
            applies_to=["jkw-obs-mcp"],
            vault_root=vault,
            machine_id="dreamingmachine",
            indexer=fake_indexer,
        )

    assert isinstance(result, LearningResult)
    assert result.written is True
    assert result.pushed is True
    assert result.reason is None
    assert result.path.is_file()
    assert "kb/dreamingmachine/learnings/constraints" in str(result.path)
    assert result.path.name.endswith("-ucsf-versa-requires-vpn.md")
    body = result.path.read_text()
    assert body.startswith("---\n")
    assert "title: UCSF Versa requires VPN" in body
    assert "machine: dreamingmachine" in body
    assert "tags: [ucsf, versa]" in body
    assert "applies_to: [jkw-obs-mcp]" in body
    assert "full content" in body


def test_push_failure_returns_pushed_false_but_file_still_written(vault):
    fake_indexer = MagicMock()

    with _patch_io_layer(push_succeeds=False):
        result = record_learning(
            category="constraints",
            title="some title",
            content="x" * 100,
            tags=[],
            applies_to=[],
            vault_root=vault,
            machine_id="dreamingmachine",
            indexer=fake_indexer,
        )

    assert result.written is True
    assert result.path.is_file()
    assert result.pushed is False
    assert result.reason is not None


def test_reindex_called_with_incremental(vault):
    fake_indexer = MagicMock()

    with _patch_io_layer():
        record_learning(
            category="constraints",
            title="some title",
            content="x" * 100,
            tags=[],
            applies_to=[],
            vault_root=vault,
            machine_id="dreamingmachine",
            indexer=fake_indexer,
        )

    fake_indexer.reindex.assert_called_once_with(scope="incremental")


def test_reindex_failure_does_not_break_call(vault, capsys):
    """Reindex failure logs warning but record_learning returns successfully."""
    fake_indexer = MagicMock()
    fake_indexer.reindex.side_effect = RuntimeError("indexer broken")

    with _patch_io_layer():
        result = record_learning(
            category="constraints",
            title="some title",
            content="x" * 100,
            tags=[],
            applies_to=[],
            vault_root=vault,
            machine_id="dreamingmachine",
            indexer=fake_indexer,
        )

    assert result.written is True
    assert result.pushed is True
    err = capsys.readouterr().err
    assert "reindex" in err.lower() or "fail" in err.lower()


def test_indexer_none_skips_reindex_silently(vault):
    """If no indexer is wired (e.g., tests, lightweight setup), don't crash."""
    with _patch_io_layer():
        result = record_learning(
            category="constraints",
            title="some title",
            content="x" * 100,
            tags=[],
            applies_to=[],
            vault_root=vault,
            machine_id="dreamingmachine",
            indexer=None,
        )

    assert result.written is True


def test_brain_pull_called_before_write(vault):
    """ensure_brain_repo_fresh(max_age_minutes=0) is called before file write."""
    fake_indexer = MagicMock()
    pull_was_called = []

    def fake_pull(vault_root, *, max_age_minutes):
        pull_was_called.append(max_age_minutes)

    with _patch_io_layer(), \
         patch("jkw_obs_mcp.learnings.recorder.ensure_brain_repo_fresh", side_effect=fake_pull):
        record_learning(
            category="constraints",
            title="some title",
            content="x" * 100,
            tags=[],
            applies_to=[],
            vault_root=vault,
            machine_id="dreamingmachine",
            indexer=fake_indexer,
        )

    assert pull_was_called == [0]

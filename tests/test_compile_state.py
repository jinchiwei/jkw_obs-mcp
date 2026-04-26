"""CompileState dedup contract tests."""

import json
from pathlib import Path

from jkw_obs_mcp.compilers.base import CompileState


def test_loads_empty_state_when_file_missing(tmp_path: Path) -> None:
    state = CompileState.load(tmp_path / "compile-state.json")
    assert state.entries == {}


def test_loads_existing_state(tmp_path: Path) -> None:
    state_file = tmp_path / "compile-state.json"
    state_file.write_text(json.dumps({
        "raw/papers/foo.md": {
            "sha256": "abc",
            "compiled_at": "2026-04-25T10:00:00Z",
            "kb_outputs": ["kb/dreamingmachine/papers/foo.md"],
        }
    }))

    state = CompileState.load(state_file)

    assert "raw/papers/foo.md" in state.entries
    assert state.entries["raw/papers/foo.md"].sha256 == "abc"


def test_is_stale_when_path_missing_from_state(tmp_path: Path) -> None:
    state = CompileState.load(tmp_path / "compile-state.json")
    assert state.is_stale("raw/papers/never-seen.md", current_sha256="xyz") is True


def test_is_stale_when_sha_changed(tmp_path: Path) -> None:
    state_file = tmp_path / "compile-state.json"
    state_file.write_text(json.dumps({
        "raw/papers/foo.md": {"sha256": "old", "compiled_at": "...", "kb_outputs": []}
    }))
    state = CompileState.load(state_file)
    assert state.is_stale("raw/papers/foo.md", current_sha256="new") is True


def test_is_not_stale_when_sha_matches(tmp_path: Path) -> None:
    state_file = tmp_path / "compile-state.json"
    state_file.write_text(json.dumps({
        "raw/papers/foo.md": {"sha256": "abc", "compiled_at": "...", "kb_outputs": []}
    }))
    state = CompileState.load(state_file)
    assert state.is_stale("raw/papers/foo.md", current_sha256="abc") is False


def test_record_compilation_writes_state(tmp_path: Path) -> None:
    state_file = tmp_path / "compile-state.json"
    state = CompileState.load(state_file)
    state.record(
        raw_path="raw/papers/foo.md",
        sha256="abc",
        kb_outputs=["kb/dreamingmachine/papers/foo.md"],
    )
    state.save(state_file)

    reloaded = CompileState.load(state_file)
    assert reloaded.entries["raw/papers/foo.md"].sha256 == "abc"
    assert reloaded.entries["raw/papers/foo.md"].kb_outputs == [
        "kb/dreamingmachine/papers/foo.md"
    ]

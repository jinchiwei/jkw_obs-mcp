"""Tests for learnings.recorder._resolve_path."""

from __future__ import annotations

from pathlib import Path

from jkw_obs_mcp.learnings.recorder import _resolve_path


def test_basic_path_no_collision(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    path = _resolve_path(
        vault_root=vault,
        machine_id="dreamingmachine",
        category="constraints",
        date="2026-04-28",
        slug="ucsf-network",
    )

    assert path == vault / "kb" / "dreamingmachine" / "learnings" / "constraints" / "2026-04-28-ucsf-network.md"
    # Parent dir was created
    assert path.parent.is_dir()


def test_collision_appends_dash_2(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    base = vault / "kb" / "dreamingmachine" / "learnings" / "constraints"
    base.mkdir(parents=True)
    (base / "2026-04-28-ucsf-network.md").write_text("existing")

    path = _resolve_path(
        vault_root=vault,
        machine_id="dreamingmachine",
        category="constraints",
        date="2026-04-28",
        slug="ucsf-network",
    )

    assert path.name == "2026-04-28-ucsf-network-2.md"


def test_collision_increments_to_3(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    base = vault / "kb" / "dreamingmachine" / "learnings" / "constraints"
    base.mkdir(parents=True)
    (base / "2026-04-28-ucsf-network.md").write_text("a")
    (base / "2026-04-28-ucsf-network-2.md").write_text("b")

    path = _resolve_path(
        vault_root=vault,
        machine_id="dreamingmachine",
        category="constraints",
        date="2026-04-28",
        slug="ucsf-network",
    )

    assert path.name == "2026-04-28-ucsf-network-3.md"


def test_creates_intermediate_dirs(tmp_path):
    """If kb/<machine>/learnings/<category>/ doesn't exist, create it."""
    vault = tmp_path / "vault"
    vault.mkdir()

    path = _resolve_path(
        vault_root=vault,
        machine_id="newmachine",
        category="postmortems",
        date="2026-04-28",
        slug="some-bug",
    )

    assert path.parent.is_dir()
    assert path.parent.name == "postmortems"

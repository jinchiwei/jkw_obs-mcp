"""Tests for learnings.recorder._render_frontmatter."""

from __future__ import annotations

from jkw_obs_mcp.learnings.recorder import _render_frontmatter


def test_basic_frontmatter_shape():
    out = _render_frontmatter(
        title="Versa requires UCSF VPN",
        date="2026-04-28",
        machine="dreamingmachine",
        tags=["ucsf", "versa", "network"],
        applies_to=["jkw-obs-mcp"],
    )

    assert out.startswith("---\n")
    assert out.endswith("---\n")
    assert "title: Versa requires UCSF VPN" in out
    assert "date: 2026-04-28" in out
    assert "machine: dreamingmachine" in out
    assert "tags: [ucsf, versa, network]" in out
    assert "applies_to: [jkw-obs-mcp]" in out


def test_empty_tags_renders_as_empty_brackets():
    out = _render_frontmatter(
        title="test",
        date="2026-04-28",
        machine="dreamingmachine",
        tags=[],
        applies_to=[],
    )
    assert "tags: []" in out
    assert "applies_to: []" in out


def test_single_tag():
    out = _render_frontmatter(
        title="test",
        date="2026-04-28",
        machine="dreamingmachine",
        tags=["one"],
        applies_to=["jkw-obs-mcp"],
    )
    assert "tags: [one]" in out
    assert "applies_to: [jkw-obs-mcp]" in out


def test_field_order_is_stable():
    """Order of frontmatter fields must be deterministic for diff readability."""
    out = _render_frontmatter(
        title="t",
        date="2026-04-28",
        machine="m",
        tags=[],
        applies_to=[],
    )
    title_idx = out.index("title:")
    date_idx = out.index("date:")
    machine_idx = out.index("machine:")
    tags_idx = out.index("tags:")
    applies_idx = out.index("applies_to:")
    assert title_idx < date_idx < machine_idx < tags_idx < applies_idx

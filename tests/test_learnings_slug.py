"""Tests for learnings.recorder._slugify."""

from __future__ import annotations

import pytest

from jkw_obs_mcp.learnings.recorder import _slugify


def test_basic_kebab_case():
    assert _slugify("Versa requires UCSF VPN") == "versa-requires-ucsf-vpn"


def test_strips_punctuation():
    assert _slugify("icalBuddy 1.10.1 broken!!") == "icalbuddy-1-10-1-broken"


def test_collapses_runs_of_whitespace_and_hyphens():
    assert _slugify("foo   bar -- baz") == "foo-bar-baz"


def test_strips_leading_and_trailing_hyphens():
    assert _slugify("--foo bar--") == "foo-bar"


def test_truncates_at_word_boundary_when_possible():
    """A long title gets truncated, preferring word boundaries up to max_len."""
    long_title = "a very long title with many words that exceeds the limit substantially"
    out = _slugify(long_title, max_len=30)
    assert len(out) <= 30
    assert not out.endswith("-")  # word-boundary truncation
    assert "very-long-title" in out


def test_truncate_falls_back_to_hard_cut_if_no_word_boundary():
    """A single ridiculous word gets hard-truncated."""
    out = _slugify("supercalifragilisticexpialidociouslongword", max_len=20)
    assert len(out) <= 20


def test_unicode_is_stripped():
    """Non-ASCII chars (including CJK) get stripped — slug is ASCII only."""
    assert _slugify("自我提升 self improvement") == "self-improvement"


def test_empty_after_stripping_returns_empty():
    """All-punctuation or all-unicode title returns empty string. Caller validates."""
    assert _slugify("!!!") == ""
    assert _slugify("自我提升") == ""


def test_default_max_len_is_60():
    out = _slugify("a" * 100)
    assert len(out) == 60

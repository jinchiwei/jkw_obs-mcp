# Plan 7: Learnings Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Ship `record_learning` MCP tool that bundles the full kb-write cycle (pull → write → commit → push → reindex) behind a single call, plus `ensure_brain_repo_fresh` helper for cached cross-machine read freshness.

**Architecture:** Pure-function helpers (`_slugify`, `_render_frontmatter`, `_resolve_path`) compose under one orchestrator (`record_learning`). Git ops via subprocess with retry-once-on-conflict for the cross-machine concurrent-write race. Push failures degrade to local-only writes (file is the load-bearing artifact, sync is best-effort). Auto-reindex calls existing `Indexer.reindex(scope='incremental')` so new notes are searchable in the same session. `ensure_brain_repo_fresh` is a separate cheap helper that caches pulls at configurable max-age; called with `max_age=0` before writes (always fresh) and optionally `max_age=5` before reads (cached freshness).

**Tech Stack:** Python stdlib only — `subprocess` for git, `pathlib`, `re`, `datetime`, `json`. No new pip deps.

**Realistic effort: ~3 days** (8 tasks).

---

## File Structure

```
jkw_obs-mcp/
├── src/jkw_obs_mcp/
│   ├── brain_sync/
│   │   ├── __init__.py                    Empty
│   │   └── sync.py                        ensure_brain_repo_fresh helper
│   ├── learnings/
│   │   ├── __init__.py                    Empty
│   │   └── recorder.py                    record_learning + private helpers
│   └── mcp/server.py                      Modify: register record_learning tool;
│                                          add ensure_brain_repo_fresh hook to
│                                          search_vault + find_similar
└── tests/
    ├── test_brain_sync.py                 ensure_brain_repo_fresh
    ├── test_learnings_slug.py             _slugify edge cases
    ├── test_learnings_frontmatter.py      _render_frontmatter shape
    ├── test_learnings_path.py             _resolve_path + collision handling
    ├── test_learnings_git.py              _commit_and_push w/ mocked subprocess
    ├── test_learnings_record.py           record_learning end-to-end (mocked deps)
    └── test_mcp_record_learning_tool.py   MCP tool surface + dispatch
```

---

## Task 1: `brain_sync` module — `ensure_brain_repo_fresh`

**Files:** Create `src/jkw_obs_mcp/brain_sync/__init__.py`, `src/jkw_obs_mcp/brain_sync/sync.py`. Create `tests/test_brain_sync.py`.

Standalone helper that pulls the brain repo if the last pull was older than `max_age_minutes`. State file at `~/.config/jkw-obs-mcp/brain-last-pull.json`. Pull failures are logged to stderr but never raise.

- [ ] **Step 1: Failing tests at `tests/test_brain_sync.py`**

```python
"""Tests for brain_sync.sync.ensure_brain_repo_fresh."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

from jkw_obs_mcp.brain_sync.sync import ensure_brain_repo_fresh


def test_pulls_when_no_state_file(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert any("pull" in " ".join(args) for args in runs)
    assert state.is_file()


def test_skips_when_cache_fresh(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    # Last pull was 1 minute ago; max_age 5 minutes → skip
    one_min_ago = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    state.write_text(json.dumps({"last_pull_at": one_min_ago.isoformat()}))
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert runs == []  # never called subprocess


def test_pulls_when_cache_stale(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    ten_min_ago = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10)
    state.write_text(json.dumps({"last_pull_at": ten_min_ago.isoformat()}))
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert any("pull" in " ".join(args) for args in runs)


def test_max_age_zero_always_pulls(tmp_path):
    """max_age_minutes=0 means 'always pull, ignore cache'."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    # Even a recent pull doesn't satisfy max_age=0
    just_now = dt.datetime.now(dt.UTC)
    state.write_text(json.dumps({"last_pull_at": just_now.isoformat()}))
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        ensure_brain_repo_fresh(vault, max_age_minutes=0)

    assert any("pull" in " ".join(args) for args in runs)


def test_pull_failure_does_not_raise(tmp_path, capsys):
    """Pull failure (offline / network) logs to stderr but doesn't raise."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"

    def fake_run(args, **kwargs):
        class R: returncode = 1; stderr = "could not resolve host"; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        ensure_brain_repo_fresh(vault, max_age_minutes=5)  # MUST NOT RAISE

    err = capsys.readouterr().err
    assert "pull" in err.lower() or "fail" in err.lower()
    assert not state.exists()  # state NOT updated on failure


def test_pull_failure_with_corrupt_state_still_works(tmp_path, capsys):
    """If state file is malformed, fall through to pull (don't crash)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    state.write_text("{not valid json")
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        ensure_brain_repo_fresh(vault, max_age_minutes=5)

    # Treated as no state → pull happens
    assert any("pull" in " ".join(args) for args in runs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_brain_sync.py -v`
Expected: ImportError (`brain_sync.sync` doesn't exist).

- [ ] **Step 3: Create `src/jkw_obs_mcp/brain_sync/__init__.py`**

```python
"""Brain repo sync helpers — cached pull-on-demand for cross-machine kb."""
```

- [ ] **Step 4: Create `src/jkw_obs_mcp/brain_sync/sync.py`**

```python
"""ensure_brain_repo_fresh — pull the brain repo if cached pull is stale.

The brain repo IS the user's vault directory (same git repo). This helper
pulls it via subprocess with a freshness cache so we don't hammer git on
every search_vault call. State file: ~/.config/jkw-obs-mcp/brain-last-pull.json
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


def _state_path() -> Path:
    """State file location. Function so tests can monkey-patch."""
    return Path.home() / ".config" / "jkw-obs-mcp" / "brain-last-pull.json"


def ensure_brain_repo_fresh(vault_root: Path, *, max_age_minutes: int = 5) -> None:
    """Pull the brain repo if the last pull was older than max_age_minutes.

    max_age_minutes=0 means "always pull, ignore cache" (use this before writes).
    max_age_minutes=N (typically 5) caches across reads in the same session burst.

    Cheap no-op when fresh. Logs to stderr but does NOT raise on pull failure
    — a flaky network shouldn't break a search_vault call. State file is only
    updated on successful pull, so failures naturally retry on the next call.
    """
    state = _state_path()

    if max_age_minutes > 0 and state.is_file():
        try:
            data = json.loads(state.read_text())
            last_pull = dt.datetime.fromisoformat(data["last_pull_at"])
            age_seconds = (dt.datetime.now(dt.UTC) - last_pull).total_seconds()
            if age_seconds < max_age_minutes * 60:
                return
        except (json.JSONDecodeError, KeyError, ValueError):
            # Corrupt state → fall through to pull
            pass

    result = subprocess.run(
        ["git", "-C", str(vault_root), "pull", "--ff-only"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Log but don't raise. State file unchanged → next call retries.
        print(
            f"brain repo pull failed (rc={result.returncode}): {result.stderr.strip()}",
            file=sys.stderr,
        )
        return

    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps({"last_pull_at": dt.datetime.now(dt.UTC).isoformat()})
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_brain_sync.py -v`
Expected: 6 passed.

- [ ] **Step 6: Run full suite**

Run: `pytest tests/ -q`
Expected: 185 passed (179 + 6).

- [ ] **Step 7: Commit**

```bash
git add src/jkw_obs_mcp/brain_sync/__init__.py src/jkw_obs_mcp/brain_sync/sync.py tests/test_brain_sync.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: ensure_brain_repo_fresh — cached pull-on-demand for brain repo"
```

---

## Task 2: `learnings/recorder.py` — slug + frontmatter (pure functions)

**Files:** Create `src/jkw_obs_mcp/learnings/__init__.py`, `src/jkw_obs_mcp/learnings/recorder.py` (with just slug + frontmatter for now). Create `tests/test_learnings_slug.py`, `tests/test_learnings_frontmatter.py`.

Two pure functions: `_slugify(title, max_len=60)` and `_render_frontmatter(*, title, date, machine, tags, applies_to)`. No I/O, easy to TDD.

- [ ] **Step 1: Failing tests at `tests/test_learnings_slug.py`**

```python
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
```

- [ ] **Step 2: Failing tests at `tests/test_learnings_frontmatter.py`**

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_learnings_slug.py tests/test_learnings_frontmatter.py -v`
Expected: ImportError.

- [ ] **Step 4: Create `src/jkw_obs_mcp/learnings/__init__.py`**

```python
"""record_learning MCP tool + supporting helpers for kb learnings."""
```

- [ ] **Step 5: Create `src/jkw_obs_mcp/learnings/recorder.py` with just slug + frontmatter**

```python
"""record_learning core — slug, frontmatter, path, git ops, orchestrator.

This module implements the `record_learning` MCP tool's logic. Pure functions
at the bottom (slug, frontmatter, path resolution); orchestrator at top
composing them with subprocess git ops and an injectable indexer for reindex.

For testability, all I/O-bound helpers (git, indexer) accept injectable args.
The MCP layer wires real ones in.
"""

from __future__ import annotations

import re


def _slugify(title: str, max_len: int = 60) -> str:
    """kebab-case the title, strip non-[a-z0-9-], truncate at word boundary.

    Returns "" if nothing survives stripping (caller must validate).
    """
    s = title.lower()
    # Strip everything that isn't alphanumeric, whitespace, or hyphen
    s = re.sub(r"[^a-z0-9\s\-]", "", s)
    # Collapse runs of whitespace/hyphens to a single hyphen
    s = re.sub(r"[\s\-]+", "-", s)
    # Strip leading/trailing hyphens
    s = s.strip("-")
    if len(s) <= max_len:
        return s
    # Truncate at word boundary if possible
    truncated = s[:max_len]
    last_hyphen = truncated.rfind("-")
    if last_hyphen > max_len // 2:  # keep word boundary if it's not too aggressive
        return truncated[:last_hyphen]
    return truncated.rstrip("-")


def _render_frontmatter(
    *,
    title: str,
    date: str,
    machine: str,
    tags: list[str],
    applies_to: list[str],
) -> str:
    """Generate YAML frontmatter string.

    Field order is stable: title, date, machine, tags, applies_to.
    Tags and applies_to render as flow-style lists (e.g., `[a, b, c]` or `[]`).
    Tag values must not contain commas; caller's responsibility.
    """
    tags_str = ", ".join(tags)
    applies_str = ", ".join(applies_to)
    return (
        "---\n"
        f"title: {title}\n"
        f"date: {date}\n"
        f"machine: {machine}\n"
        f"tags: [{tags_str}]\n"
        f"applies_to: [{applies_str}]\n"
        "---\n"
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_learnings_slug.py tests/test_learnings_frontmatter.py -v`
Expected: 13 passed (9 slug + 4 frontmatter).

- [ ] **Step 7: Run full suite**

Run: `pytest tests/ -q`
Expected: 198 passed (185 + 13).

- [ ] **Step 8: Commit**

```bash
git add src/jkw_obs_mcp/learnings/__init__.py src/jkw_obs_mcp/learnings/recorder.py tests/test_learnings_slug.py tests/test_learnings_frontmatter.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: learnings.recorder — _slugify + _render_frontmatter helpers"
```

---

## Task 3: `learnings/recorder.py` — path resolution + collision

**Files:** Modify `src/jkw_obs_mcp/learnings/recorder.py` (append `_resolve_path`). Create `tests/test_learnings_path.py`.

Pure-ish: takes vault_root, machine_id, category, date, slug; returns the target file path. Handles existing-file collisions by appending `-2`, `-3`, etc.

- [ ] **Step 1: Failing tests at `tests/test_learnings_path.py`**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_learnings_path.py -v`
Expected: ImportError on `_resolve_path`.

- [ ] **Step 3: Append `_resolve_path` to `src/jkw_obs_mcp/learnings/recorder.py`**

Add to imports at top:
```python
from pathlib import Path
```

Append after `_render_frontmatter`:

```python
def _resolve_path(
    *,
    vault_root: Path,
    machine_id: str,
    category: str,
    date: str,
    slug: str,
) -> Path:
    """Compute the target file path. Append -2, -3 if collision.

    Creates intermediate dirs (kb/<machine>/learnings/<category>/) if missing.
    """
    base_dir = vault_root / "kb" / machine_id / "learnings" / category
    base_dir.mkdir(parents=True, exist_ok=True)

    path = base_dir / f"{date}-{slug}.md"
    if not path.exists():
        return path

    # Collision: try -2, -3, ...
    for i in range(2, 100):
        path = base_dir / f"{date}-{slug}-{i}.md"
        if not path.exists():
            return path
    raise RuntimeError(f"too many collisions for slug {slug!r} on {date}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_learnings_path.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 202 passed (198 + 4).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/learnings/recorder.py tests/test_learnings_path.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: learnings.recorder — _resolve_path with collision handling"
```

---

## Task 4: `learnings/recorder.py` — git ops with retry

**Files:** Modify `src/jkw_obs_mcp/learnings/recorder.py` (append `_commit_and_push`). Create `tests/test_learnings_git.py`.

Add → commit → push, with `git pull --rebase` + retry once on push failure. Returns `(pushed: bool, reason: str | None)`.

- [ ] **Step 1: Failing tests at `tests/test_learnings_git.py`**

```python
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

    runs = []

    def fake_run(args, **kwargs):
        runs.append(" ".join(args))
        joined = " ".join(args)
        # First push fails, pull succeeds, second push succeeds
        if "push" in joined and runs.count(joined) == 1:
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
    assert sum("push" in r for r in runs) == 2
    assert any("rebase" in r for r in runs)


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

    runs = []

    def fake_run(args, **kwargs):
        runs.append(" ".join(args))
        joined = " ".join(args)
        if "commit" in joined:
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
    assert sum("push" in r for r in runs) == 0


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_learnings_git.py -v`
Expected: ImportError on `_commit_and_push`.

- [ ] **Step 3: Append `_commit_and_push` to `src/jkw_obs_mcp/learnings/recorder.py`**

Add `import subprocess` to imports at top.

Append after `_resolve_path`:

```python
def _commit_and_push(
    *,
    vault_root: Path,
    file_path: Path,
    title: str,
) -> tuple[bool, str | None]:
    """Add → commit → push, retry-once-on-conflict.

    Returns (pushed: bool, reason: str | None). On push failure, the local
    commit IS still made — caller's responsibility to inform user that
    cross-machine sync is delayed.
    """
    # Stage
    add = subprocess.run(
        ["git", "-C", str(vault_root), "add", str(file_path)],
        capture_output=True, text=True,
    )
    if add.returncode != 0:
        return False, f"git add failed: {add.stderr.strip()}"

    # Commit
    commit = subprocess.run(
        ["git", "-C", str(vault_root), "commit", "-m", f"kb: {title}"],
        capture_output=True, text=True,
    )
    if commit.returncode != 0:
        return False, f"git commit failed: {commit.stderr.strip()}"

    # First push attempt
    push = subprocess.run(
        ["git", "-C", str(vault_root), "push"],
        capture_output=True, text=True,
    )
    if push.returncode == 0:
        return True, None

    # Push failed — try pull --rebase + retry once
    rebase = subprocess.run(
        ["git", "-C", str(vault_root), "pull", "--rebase"],
        capture_output=True, text=True,
    )
    if rebase.returncode != 0:
        return False, f"pull --rebase failed: {rebase.stderr.strip()}"

    retry = subprocess.run(
        ["git", "-C", str(vault_root), "push"],
        capture_output=True, text=True,
    )
    if retry.returncode == 0:
        return True, None

    return False, f"git push failed after retry: {retry.stderr.strip()}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_learnings_git.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 208 passed (202 + 6).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/learnings/recorder.py tests/test_learnings_git.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: learnings.recorder — _commit_and_push with retry-on-conflict"
```

---

## Task 5: `learnings/recorder.py` — `record_learning` orchestrator

**Files:** Modify `src/jkw_obs_mcp/learnings/recorder.py` (append `LearningResult` dataclass + `record_learning`). Create `tests/test_learnings_record.py`.

The full orchestrator: validate inputs → resolve path → pull brain repo → write file → commit-and-push → reindex → return result.

- [ ] **Step 1: Failing tests at `tests/test_learnings_record.py`**

```python
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
    """Standard patch set: subprocess git ops always succeed by default."""
    def fake_run(args, **kwargs):
        joined = " ".join(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        if "push" in joined and not push_succeeds:
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
            content="some content " * 10,  # >50 chars
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
    # File exists at expected path shape
    assert result.path.is_file()
    assert "kb/dreamingmachine/learnings/constraints" in str(result.path)
    assert result.path.name.endswith("-ucsf-versa-requires-vpn.md")
    # Content includes frontmatter + body
    body = result.path.read_text()
    assert body.startswith("---\n")
    assert "title: UCSF Versa requires VPN" in body
    assert "machine: dreamingmachine" in body
    assert "tags: [ucsf, versa]" in body
    assert "applies_to: [jkw-obs-mcp]" in body
    assert "full content" in body  # body content present


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

    assert result.written is True  # file was created
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

    assert pull_was_called == [0]  # max_age_minutes=0 means always-pull
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_learnings_record.py -v`
Expected: ImportError on `LearningResult` / `record_learning`.

- [ ] **Step 3: Append the orchestrator to `src/jkw_obs_mcp/learnings/recorder.py`**

Add to imports at top:
```python
import datetime as dt
import sys
from dataclasses import dataclass
from typing import Any

from jkw_obs_mcp.brain_sync.sync import ensure_brain_repo_fresh
```

Append after `_commit_and_push`:

```python
@dataclass(frozen=True)
class LearningResult:
    """Status returned from record_learning."""

    written: bool          # True if local file was created
    path: Path             # absolute path to the new file
    pushed: bool           # True if successfully synced to brain repo
    reason: str | None = None  # if pushed=False, why


_VALID_CATEGORIES = {"constraints", "decisions", "postmortems"}


def record_learning(
    *,
    category: str,
    title: str,
    content: str,
    tags: list[str],
    applies_to: list[str],
    vault_root: Path,
    machine_id: str,
    indexer: Any | None = None,
) -> LearningResult:
    """Write a learning note + commit + push + reindex.

    Path: kb/<machine_id>/learnings/<category>/<YYYY-MM-DD>-<slug>.md
    Frontmatter: title, date, machine, tags, applies_to (auto-generated).
    Reindex via injected `indexer` (call indexer.reindex(scope='incremental')).

    Returns LearningResult. pushed=False does NOT mean failure — the file is
    still written locally and the local commit was made; obsidian-git plugin
    or a manual `git push` will propagate later.
    """
    # Validate inputs
    if category not in _VALID_CATEGORIES:
        raise ValueError(
            f"invalid category {category!r}; must be one of {sorted(_VALID_CATEGORIES)}"
        )
    if len(title) < 3:
        raise ValueError(f"title too short: {title!r}")
    if len(content) < 50:
        raise ValueError("content must be at least 50 characters")

    slug = _slugify(title)
    if not slug:
        raise ValueError(f"title produces empty slug after normalization: {title!r}")

    today = dt.date.today().isoformat()

    # Pull brain repo before write (always fresh)
    ensure_brain_repo_fresh(vault_root, max_age_minutes=0)

    # Resolve path (handles collision by appending -2, -3, etc.)
    path = _resolve_path(
        vault_root=vault_root,
        machine_id=machine_id,
        category=category,
        date=today,
        slug=slug,
    )

    # Render frontmatter and write file
    frontmatter = _render_frontmatter(
        title=title,
        date=today,
        machine=machine_id,
        tags=tags,
        applies_to=applies_to,
    )
    path.write_text(frontmatter + "\n" + content + ("\n" if not content.endswith("\n") else ""))

    # Commit and push (with retry-on-conflict)
    pushed, reason = _commit_and_push(
        vault_root=vault_root, file_path=path, title=title
    )

    # Reindex (incremental walk picks up the new file via mtime)
    if indexer is not None:
        try:
            indexer.reindex(scope="incremental")
        except Exception as exc:
            print(f"reindex failed (non-fatal): {exc}", file=sys.stderr)

    return LearningResult(written=True, path=path, pushed=pushed, reason=reason)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_learnings_record.py -v`
Expected: 9 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 217 passed (208 + 9).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/learnings/recorder.py tests/test_learnings_record.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: record_learning orchestrator — pull + write + commit + push + reindex"
```

---

## Task 6: MCP tool registration — `record_learning`

**Files:** Modify `src/jkw_obs_mcp/mcp/server.py`. Create `tests/test_mcp_record_learning_tool.py`.

Register `record_learning` as an MCP Tool with strict `inputSchema` (category enum, title minLength, content minLength). Add dispatch branch that calls `record_learning(...)` with vault_root + machine_id from adapter and the indexer attached at startup.

- [ ] **Step 1: Failing tests at `tests/test_mcp_record_learning_tool.py`**

```python
"""MCP tool registration + dispatch for record_learning."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.mcp.server import dispatch_tool, tools_for_adapter


@pytest.fixture
def adapter_with_indexer(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    adapter.indexer = MagicMock()
    return adapter


def test_tool_surface_includes_record_learning(adapter_with_indexer):
    tools = tools_for_adapter(adapter_with_indexer)
    names = {t.name for t in tools}
    assert "record_learning" in names


def test_tool_input_schema_has_category_enum(adapter_with_indexer):
    tools = tools_for_adapter(adapter_with_indexer)
    rl = next(t for t in tools if t.name == "record_learning")
    cat_schema = rl.inputSchema["properties"]["category"]
    assert cat_schema["enum"] == ["constraints", "decisions", "postmortems"]


def test_tool_input_schema_marks_required_fields(adapter_with_indexer):
    tools = tools_for_adapter(adapter_with_indexer)
    rl = next(t for t in tools if t.name == "record_learning")
    required = set(rl.inputSchema["required"])
    assert {"category", "title", "content"} <= required


@pytest.mark.asyncio
async def test_dispatch_writes_file_and_returns_status(adapter_with_indexer, tmp_vault):
    """Successful dispatch writes the file and returns a status string."""
    runs = []

    def fake_run(args, **kwargs):
        runs.append(" ".join(args))
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.learnings.recorder.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run):
        result = await dispatch_tool(
            adapter_with_indexer,
            "record_learning",
            {
                "category": "constraints",
                "title": "Test learning",
                "content": "This is the body of the learning, padded out to be more than 50 chars long.",
                "tags": ["test"],
                "applies_to": ["jkw-obs-mcp"],
            },
        )

    text = result[0].text
    assert "wrote" in text.lower() or "kb/dreamingmachine/learnings/constraints" in text
    # File exists in tmp_vault
    expected_dir = tmp_vault / "kb" / "dreamingmachine" / "learnings" / "constraints"
    md_files = list(expected_dir.glob("*-test-learning.md"))
    assert len(md_files) == 1


@pytest.mark.asyncio
async def test_dispatch_invalid_category_raises(adapter_with_indexer):
    with pytest.raises(ValueError):
        await dispatch_tool(
            adapter_with_indexer,
            "record_learning",
            {
                "category": "bogus",
                "title": "Test learning",
                "content": "x" * 100,
            },
        )


@pytest.mark.asyncio
async def test_dispatch_offline_returns_pushed_false_status(adapter_with_indexer, tmp_vault):
    """When push fails (offline), status text mentions sync incomplete."""

    def fake_run(args, **kwargs):
        joined = " ".join(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        if "push" in joined:
            R.returncode = 1
            R.stderr = "could not resolve host"
        return R()

    with patch("jkw_obs_mcp.learnings.recorder.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run):
        result = await dispatch_tool(
            adapter_with_indexer,
            "record_learning",
            {
                "category": "constraints",
                "title": "Offline test",
                "content": "x" * 100,
            },
        )

    text = result[0].text
    # Status text surfaces that push didn't succeed
    assert "wrote" in text.lower()
    assert "not pushed" in text.lower() or "local only" in text.lower() or "pushed=false" in text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_record_learning_tool.py -v`
Expected: tool not registered.

- [ ] **Step 3: Modify `src/jkw_obs_mcp/mcp/server.py`**

In `tools_for_adapter`, append (after the `compile_email` Tool, before the closing `]`):

```python
        Tool(
            name="record_learning",
            description="Write a kb learning note (constraints / decisions / postmortems) "
            "to kb/<machine>/learnings/<category>/<date>-<slug>.md. Pulls brain repo "
            "first, writes file with auto-generated frontmatter, commits, pushes "
            "(retry-once-on-conflict), and reindexes. On push failure (offline), the "
            "file is still written and committed locally — sync delayed. Use for "
            "Jin-specific or UCSF-specific or project-internal insights that "
            "Anthropic's training cannot have.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["constraints", "decisions", "postmortems"],
                    },
                    "title": {"type": "string", "minLength": 3},
                    "content": {"type": "string", "minLength": 50},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                    "applies_to": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                },
                "required": ["category", "title", "content"],
            },
        ),
```

In `dispatch_tool`, add a branch BEFORE the final `raise ValueError(f"unknown tool: {name}")`:

```python
    if name == "record_learning":
        from jkw_obs_mcp.learnings.recorder import record_learning
        result = record_learning(
            category=arguments["category"],
            title=arguments["title"],
            content=arguments["content"],
            tags=arguments.get("tags", []),
            applies_to=arguments.get("applies_to", []),
            vault_root=adapter.vault_root,
            machine_id=adapter.machine_id,
            indexer=getattr(adapter, "indexer", None),
        )
        if result.pushed:
            text = f"wrote {result.path}"
        else:
            text = (
                f"wrote {result.path} (local only; not pushed: {result.reason})"
            )
        return [TextContent(type="text", text=text)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mcp_record_learning_tool.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 223 passed (217 + 6).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/mcp/server.py tests/test_mcp_record_learning_tool.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: record_learning MCP tool registration + dispatch"
```

---

## Task 7: Cached pull-on-read for `search_vault` and `find_similar`

**Files:** Modify `src/jkw_obs_mcp/mcp/server.py` (add `ensure_brain_repo_fresh(max_age=5)` calls to two dispatch branches). Add tests inline to existing `tests/test_mcp_search_tools.py` (or extend `tests/test_mcp_record_learning_tool.py` if separate is clearer).

Wires the freshness cache into reads. With `max_age=5` minutes, a burst of 10 search calls in one session does one git pull total. After 5 min idle, next search triggers a fresh pull.

- [ ] **Step 1: Append failing tests to `tests/test_mcp_record_learning_tool.py`**

```python
@pytest.mark.asyncio
async def test_search_vault_calls_ensure_brain_repo_fresh(adapter_with_indexer):
    """search_vault dispatch calls ensure_brain_repo_fresh(max_age_minutes=5)."""
    # Wire embedder + store mocks so search dispatch can run
    fake_embedder = MagicMock()
    fake_embedder.embed_one.return_value = [0.0] * 768
    adapter_with_indexer.embedder = fake_embedder
    fake_store = MagicMock()
    fake_store.query.return_value = []
    adapter_with_indexer.store = fake_store

    pull_calls = []

    def fake_pull(vault_root, *, max_age_minutes):
        pull_calls.append(max_age_minutes)

    with patch("jkw_obs_mcp.mcp.server.ensure_brain_repo_fresh", side_effect=fake_pull):
        await dispatch_tool(
            adapter_with_indexer, "search_vault", {"query": "test"}
        )

    assert pull_calls == [5]


@pytest.mark.asyncio
async def test_find_similar_calls_ensure_brain_repo_fresh(adapter_with_indexer):
    fake_embedder = MagicMock()
    fake_embedder.embed_one.return_value = [0.0] * 768
    adapter_with_indexer.embedder = fake_embedder
    fake_store = MagicMock()
    fake_store.query.return_value = []
    adapter_with_indexer.store = fake_store

    pull_calls = []

    def fake_pull(vault_root, *, max_age_minutes):
        pull_calls.append(max_age_minutes)

    with patch("jkw_obs_mcp.mcp.server.ensure_brain_repo_fresh", side_effect=fake_pull):
        await dispatch_tool(
            adapter_with_indexer, "find_similar", {"text": "test"}
        )

    assert pull_calls == [5]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_record_learning_tool.py -v -k "ensure_brain"`
Expected: AttributeError or test failures (ensure_brain_repo_fresh not imported into mcp.server, not called from search dispatch).

- [ ] **Step 3: Modify `src/jkw_obs_mcp/mcp/server.py`**

Add to imports near the top:
```python
from jkw_obs_mcp.brain_sync.sync import ensure_brain_repo_fresh
```

In `dispatch_tool`, find the `search_vault` branch and add a `ensure_brain_repo_fresh` call as the FIRST line of the branch body:

```python
    if name == "search_vault":
        ensure_brain_repo_fresh(adapter.vault_root, max_age_minutes=5)
        query_vec = adapter.embedder.embed_one(arguments["query"])
        # ... existing code unchanged
```

Same for the `find_similar` branch:

```python
    if name == "find_similar":
        ensure_brain_repo_fresh(adapter.vault_root, max_age_minutes=5)
        query_vec = adapter.embedder.embed_one(arguments["text"])
        # ... existing code unchanged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mcp_record_learning_tool.py -v`
Expected: 8 passed (6 + 2 new).

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 225 passed (223 + 2). Confirm `test_mcp_search_tools.py` still passes — those tests don't mock `ensure_brain_repo_fresh`, so they need to not be broken by the new call. Likely the fastembed-backed real path will trigger a real `git pull` attempt against the test's tmp_vault that ISN'T a git repo, and `ensure_brain_repo_fresh` will log a warning and continue. That's the contract — never raise on pull failure. Test should still pass.

If `test_mcp_search_tools.py` fails because of unexpected stderr output, narrow the assertion (or add `capsys.readouterr()` to swallow). Don't suppress the warning behavior — it's correct.

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/mcp/server.py tests/test_mcp_record_learning_tool.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: search_vault + find_similar pull brain repo (cached, max_age=5min)"
```

---

## Task 8: Manual end-to-end smoke test + plan-7-complete tag

This task is non-TDD — exercises the real MCP tool from a Claude Code session against the live brain repo.

- [ ] **Step 1: Restart Claude Code** so the MCP server picks up the new `record_learning` tool.

- [ ] **Step 2: Verify tool surface**

In Claude Code, ask:

> List all jkw-obs tools.

Expected: 10 tools (the previous 9 + `record_learning`).

- [ ] **Step 3: Write a real learning via the MCP tool**

In Claude Code, ask:

> Use jkw-obs `record_learning`:
> - category: decisions
> - title: Plan 7 ships record_learning
> - content: Plan 7 closes the manual-prompt friction for kb writes. The MCP tool record_learning bundles pull → write → commit → push → reindex. Built 2026-04-28. From now on logging a kb learning is a single tool call, not a 10-line prompt.
> - tags: [jkw-obs-mcp, kb, plan-7]
> - applies_to: [jkw-obs-mcp]

Expected output: `wrote /Users/jinchiwei/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs/kb/dreamingmachine/learnings/decisions/2026-04-28-plan-7-ships-record-learning.md`

Verify:
1. The file exists at that path
2. Frontmatter shape matches the 5 backfilled notes (`title`, `date`, `machine`, `tags`, `applies_to`)
3. Body content present after the closing `---`

- [ ] **Step 4: Verify push to brain repo**

Open https://github.com/jinchiwei/jkw_obs-brain in your browser and navigate to `kb/dreamingmachine/learnings/decisions/`. The new file should be there within seconds.

If it's NOT there: check the err log or the tool output. Most likely off-VPN at a network blip, in which case the tool returned `wrote ... (local only; not pushed: <reason>)` — the file IS local, it'll sync when you next push.

- [ ] **Step 5: Verify search_vault finds the new note**

In Claude Code, ask:

> Use jkw-obs `search_vault` for: Plan 7 record_learning

Expected: top hit is the just-written note. Distance < 1.0 (good match because the title and query are highly similar).

- [ ] **Step 6: Verify offline graceful degrade**

Disconnect from network (turn off wifi briefly). Then in Claude Code:

> Use jkw-obs `record_learning`:
> - category: postmortems
> - title: offline write test
> - content: This is a test that runs while wifi is off so we can verify the offline path. The tool should write the file and commit locally, but the push will fail with a network error. Status should reflect that.
> - tags: [test]

Expected output: `wrote /path/...md (local only; not pushed: ...)` — the file is created, the local commit is made, but pushed=False with a network error in the reason.

Reconnect wifi. Run:
```bash
cd "/Users/jinchiwei/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs"
git push
```

The pending commit propagates. Verify on github.com/jinchiwei/jkw_obs-brain.

You can leave the test file in the brain repo or `git rm` it via Obsidian — either works.

- [ ] **Step 7: Tag and push**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git push origin main
git tag plan-7-complete
git push origin --tags
```

---

## Self-Review Checklist

- [ ] All 8 tasks committed
- [ ] `pytest -q` shows full suite green (~225 tests)
- [ ] `record_learning` MCP tool surfaces in Claude Code (10 jkw-obs tools total)
- [ ] A real learning written via the tool appears in the vault and on github.com/jinchiwei/jkw_obs-brain within seconds
- [ ] `search_vault` finds the just-written note in the same session (auto-reindex works)
- [ ] Offline test: tool returns `wrote ... (local only; not pushed: ...)` and the file is committed locally; push later propagates it
- [ ] `git tag plan-7-complete` pushed

When all boxes ticked, Plan 7 done. Plan 8 (cluster rollout to scs/fac/cph) is next — and a key benefit of Plan 7 is that as soon as a cluster is online, `record_learning` works there too with no additional code (it's machine-id-agnostic; cluster writes go to `kb/<cluster>/learnings/...`).

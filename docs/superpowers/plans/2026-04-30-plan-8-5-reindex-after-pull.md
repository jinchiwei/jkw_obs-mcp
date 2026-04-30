# Plan 8.5: Reindex After Pull Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the cross-machine search gap. After Plan 8.5, writing a learning on machine A surfaces in `search_vault` results on machine B without manual reindex — within the 5-minute pull cache window.

**Architecture:** `ensure_brain_repo_fresh` returns `bool` indicating whether the pull moved HEAD. Dispatch branches for `search_vault` and `find_similar` in `mcp/server.py` check the return value and call `indexer.reindex(scope='incremental')` only when there's actually new content. Zero overhead on cache hits or no-op pulls; exactly one reindex per actual remote change.

**Tech Stack:** Python stdlib only. No new pip deps. No new modules — just a signature change in `brain_sync/sync.py` and ~6 lines added across two dispatch branches in `mcp/server.py`.

**Realistic effort: ~1 hour CC time** (3 tasks).

---

## File Structure

```
jkw_obs-mcp/
├── src/jkw_obs_mcp/
│   ├── brain_sync/sync.py                       MODIFY: -> bool return; capture
│   │                                                    pre/post-pull HEAD via
│   │                                                    `git rev-parse`
│   └── mcp/server.py                            MODIFY: search_vault + find_similar
│                                                        dispatch branches conditionally
│                                                        reindex on pulled_new=True
└── tests/
    ├── test_brain_sync.py                       MODIFY: existing 6 tests assert bool
    │                                                    return; add 2 tests for
    │                                                    HEAD-changed detection
    └── test_mcp_record_learning_tool.py         MODIFY: existing 2 tests adjust
                                                          fake_pull return; add 2
                                                          tests for reindex-when-new
```

**Why this layout:**
- No new files. The change is too small to warrant new modules; everything fits in existing files.
- Both edited modules already follow the established pattern (subprocess for git, mocked in tests via `patch("...subprocess.run", ...)`).

---

## Task 1: `ensure_brain_repo_fresh` returns bool

**Files:**
- Modify: `src/jkw_obs_mcp/brain_sync/sync.py` — change return type, capture pre/post-pull HEAD, return whether HEAD changed
- Modify: `tests/test_brain_sync.py` — existing 6 tests need to assert the bool return; add 2 new tests for HEAD-change detection

Current signature: `def ensure_brain_repo_fresh(vault_root: Path, *, max_age_minutes: int = 5) -> None`. New signature: same params, returns `bool`.

Behavior:
- Cache hit (state file fresh AND `max_age_minutes > 0`) → return `False` (no pull attempted).
- Pull failure (rc != 0) → return `False`.
- Pull success but HEAD unchanged (already up to date) → return `False`.
- Pull success AND HEAD moved → return `True`.

To detect HEAD change cheaply, run `git rev-parse HEAD` BEFORE and AFTER the pull. Compare strings. If different, return True.

- [ ] **Step 1: Update existing tests at `tests/test_brain_sync.py` to assert bool return**

The existing 6 tests call `ensure_brain_repo_fresh(...)` and assert nothing about the return. Update them so each one asserts the return value matches the expected scenario. Specifically:

- `test_pulls_when_no_state_file` — pull happens, but our fake_run doesn't simulate HEAD change, so use a fake that tracks `rev-parse` calls and returns different SHAs. Assert `result is True` (since no state file means we always pull, and the test SHOULD verify that the helper correctly reports HEAD change when the fake says HEAD moved).
- `test_skips_when_cache_fresh` — assert `result is False` (no pull attempted).
- `test_pulls_when_cache_stale` — same shape as `test_pulls_when_no_state_file`: simulate HEAD change, assert `result is True`.
- `test_max_age_zero_always_pulls` — simulate HEAD change, assert `result is True`.
- `test_pull_failure_does_not_raise` — assert `result is False` (pull failed).
- `test_pull_failure_with_corrupt_state_still_works` — simulate HEAD change after the pull, assert `result is True`.

Modify the fake_run helpers in each test to handle `rev-parse` calls. The pattern:
```python
revs = iter(["abc123\n", "def456\n"])  # pre-pull, post-pull

def fake_run(args, **kwargs):
    runs.append(args)
    if "rev-parse" in args:
        class R: returncode = 0; stderr = ""; stdout = next(revs, "abc123\n")
        return R()
    class R: returncode = 0; stderr = ""; stdout = ""
    return R()
```

For tests that should report `False` (no HEAD change), have `revs` yield the same SHA twice:
```python
revs = iter(["abc123\n", "abc123\n"])
```

Full updated test file (replace existing content):

```python
"""Tests for brain_sync.sync.ensure_brain_repo_fresh."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

from jkw_obs_mcp.brain_sync.sync import ensure_brain_repo_fresh


def _fake_run_factory(*, pre_sha="abc123", post_sha="def456", pull_rc=0, pull_err=""):
    """Build a fake subprocess.run that handles git rev-parse + pull.

    Returns (fake_run_callable, runs_list). The callable yields pre_sha for the
    first rev-parse, post_sha for the second; pull_rc + pull_err for the pull.
    Other commands return rc=0.
    """
    runs = []
    rev_calls = {"count": 0}

    def fake_run(args, **kwargs):
        runs.append(args)
        if "rev-parse" in args:
            rev_calls["count"] += 1
            sha = pre_sha if rev_calls["count"] == 1 else post_sha
            class R: returncode = 0; stderr = ""; stdout = sha + "\n"
            return R()
        if "pull" in args:
            class R:
                returncode = pull_rc
                stderr = pull_err
                stdout = ""
            return R()
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    return fake_run, runs


def test_pulls_when_no_state_file(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    fake_run, runs = _fake_run_factory(pre_sha="aaa", post_sha="bbb")

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is True  # HEAD moved aaa -> bbb
    assert any("pull" in args for args in runs)
    assert state.is_file()


def test_skips_when_cache_fresh(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    one_min_ago = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    state.write_text(json.dumps({"last_pull_at": one_min_ago.isoformat()}))
    fake_run, runs = _fake_run_factory()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is False  # cache hit, no pull
    assert runs == []


def test_pulls_when_cache_stale(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    ten_min_ago = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10)
    state.write_text(json.dumps({"last_pull_at": ten_min_ago.isoformat()}))
    fake_run, runs = _fake_run_factory(pre_sha="aaa", post_sha="bbb")

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is True
    assert any("pull" in args for args in runs)


def test_max_age_zero_always_pulls(tmp_path):
    """max_age_minutes=0 means 'always pull, ignore cache'."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    just_now = dt.datetime.now(dt.UTC)
    state.write_text(json.dumps({"last_pull_at": just_now.isoformat()}))
    fake_run, runs = _fake_run_factory(pre_sha="aaa", post_sha="bbb")

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=0)

    assert result is True
    assert any("pull" in args for args in runs)


def test_pull_failure_does_not_raise(tmp_path, capsys):
    """Pull failure (offline / network) logs to stderr but doesn't raise. Returns False."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    fake_run, _ = _fake_run_factory(pull_rc=1, pull_err="could not resolve host")

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is False
    err = capsys.readouterr().err
    assert "pull" in err.lower() or "fail" in err.lower()
    assert not state.exists()


def test_pull_failure_with_corrupt_state_still_works(tmp_path):
    """If state file is malformed, fall through to pull (don't crash)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    state.write_text("{not valid json")
    fake_run, runs = _fake_run_factory(pre_sha="aaa", post_sha="bbb")

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is True
    assert any("pull" in args for args in runs)


def test_returns_false_when_pull_succeeds_but_head_unchanged(tmp_path):
    """Pull ran but HEAD didn't move (already up to date) → return False."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"
    fake_run, runs = _fake_run_factory(pre_sha="abc", post_sha="abc")  # same SHA

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is False  # pull happened but no new content
    assert any("pull" in args for args in runs)
    # State IS updated (the pull was successful, even if no-op)
    assert state.is_file()


def test_rev_parse_failure_returns_false(tmp_path, capsys):
    """If `git rev-parse HEAD` fails (e.g., not a git repo), gracefully return False."""
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state.json"

    def fake_run(args, **kwargs):
        if "rev-parse" in args:
            class R: returncode = 1; stderr = "not a git repository"; stdout = ""
            return R()
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.brain_sync.sync.subprocess.run", side_effect=fake_run), \
         patch("jkw_obs_mcp.brain_sync.sync._state_path", return_value=state):
        result = ensure_brain_repo_fresh(vault, max_age_minutes=5)

    assert result is False  # graceful — never raise
```

- [ ] **Step 2: Run tests to verify they fail**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/test_brain_sync.py -v
```

Expected: existing tests now fail because `ensure_brain_repo_fresh` returns `None`, not `bool`. The 2 new tests (`test_returns_false_when_pull_succeeds_but_head_unchanged`, `test_rev_parse_failure_returns_false`) also fail.

- [ ] **Step 3: Modify `src/jkw_obs_mcp/brain_sync/sync.py`**

Replace the function body with this version. Key changes: return type is `bool`; capture pre/post-pull HEAD via `git rev-parse`; rev-parse failures gracefully return `False`.

```python
"""ensure_brain_repo_fresh — pull the brain repo if cached pull is stale.

The brain repo IS the user's vault directory (same git repo). This helper
pulls it via subprocess with a freshness cache so we don't hammer git on
every search_vault call. State file: ~/.config/jkw-obs-mcp/brain-last-pull.json

Returns bool: True if the pull moved HEAD (caller may want to reindex).
False on cache hit, pull failure, or pull-no-op.
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


def _head_sha(vault_root: Path) -> str | None:
    """Return current HEAD SHA, or None if not a git repo / rev-parse fails."""
    proc = subprocess.run(
        ["git", "-C", str(vault_root), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def ensure_brain_repo_fresh(vault_root: Path, *, max_age_minutes: int = 5) -> bool:
    """Pull the brain repo if the last pull was older than max_age_minutes.

    Returns True if a pull was performed AND HEAD moved (callers may want to
    reindex). Returns False on cache hit, pull failure, or pull-no-op.

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
                return False  # cache hit, no pull
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Capture HEAD before pulling so we can detect whether anything changed.
    pre_sha = _head_sha(vault_root)
    if pre_sha is None:
        # Not a git repo or rev-parse failed; nothing meaningful to do.
        return False

    result = subprocess.run(
        ["git", "-C", str(vault_root), "pull", "--ff-only"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"brain repo pull failed (rc={result.returncode}): {result.stderr.strip()}",
            file=sys.stderr,
        )
        return False

    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps({"last_pull_at": dt.datetime.now(dt.UTC).isoformat()})
    )

    post_sha = _head_sha(vault_root)
    if post_sha is None:
        return False  # rev-parse broken post-pull; conservative no-reindex
    return post_sha != pre_sha
```

- [ ] **Step 4: Run tests to verify they pass**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/test_brain_sync.py -v
```

Expected: 8 passed (the original 6 + 2 new).

- [ ] **Step 5: Run full suite to check for fallout in other tests**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/ -q
```

Expected: most tests pass, but tests in `tests/test_mcp_record_learning_tool.py` that mock `ensure_brain_repo_fresh` with a no-return-value `fake_pull` may need adjusting if they assert anything about return values. If they don't assert (most don't), they'll continue to pass — Python implicitly returns None which evaluates falsy in our `if pulled_new:` check.

Confirm test count is at minimum 251 (Plan 8 head); ideally 253 (251 + 2 new brain_sync tests). If some other tests fail due to the return-type change, fix them in this task before proceeding.

If `test_brain_pull_called_before_write` in `tests/test_learnings_record.py` fails because the helper's behavior changed: that test only asserts the helper was called with `max_age_minutes=0`, not about the return value. Should still pass. If not, debug.

- [ ] **Step 6: Commit**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git add src/jkw_obs_mcp/brain_sync/sync.py tests/test_brain_sync.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: ensure_brain_repo_fresh returns bool (HEAD changed)"
```

---

## Task 2: Conditional reindex in search_vault + find_similar dispatch

**Files:**
- Modify: `src/jkw_obs_mcp/mcp/server.py` — search_vault and find_similar dispatch branches conditionally call `indexer.reindex(scope='incremental')` when `pulled_new=True`
- Modify: `tests/test_mcp_record_learning_tool.py` — adjust existing tests (fake_pull now returns bool); add 2 new tests asserting reindex is called when pulled_new=True and skipped when False

- [ ] **Step 1: Add new tests to `tests/test_mcp_record_learning_tool.py`**

After the existing `test_search_vault_calls_ensure_brain_repo_fresh` and `test_find_similar_calls_ensure_brain_repo_fresh` tests, append these:

```python
@pytest.mark.asyncio
async def test_search_vault_reindexes_when_pulled_new(adapter_with_indexer):
    """When ensure_brain_repo_fresh returns True (new content pulled), reindex before query."""
    fake_embedder = MagicMock()
    fake_embedder.embed_one.return_value = [0.0] * 768
    adapter_with_indexer.embedder = fake_embedder
    fake_store = MagicMock()
    fake_store.query.return_value = []
    adapter_with_indexer.store = fake_store

    # Helper returns True → caller should reindex
    with patch("jkw_obs_mcp.mcp.server.ensure_brain_repo_fresh", return_value=True):
        await dispatch_tool(
            adapter_with_indexer, "search_vault", {"query": "test"}
        )

    adapter_with_indexer.indexer.reindex.assert_called_once_with(scope="incremental")


@pytest.mark.asyncio
async def test_search_vault_skips_reindex_when_not_pulled(adapter_with_indexer):
    """When ensure_brain_repo_fresh returns False (cache hit / no change), skip reindex."""
    fake_embedder = MagicMock()
    fake_embedder.embed_one.return_value = [0.0] * 768
    adapter_with_indexer.embedder = fake_embedder
    fake_store = MagicMock()
    fake_store.query.return_value = []
    adapter_with_indexer.store = fake_store

    # Helper returns False → no reindex
    with patch("jkw_obs_mcp.mcp.server.ensure_brain_repo_fresh", return_value=False):
        await dispatch_tool(
            adapter_with_indexer, "search_vault", {"query": "test"}
        )

    adapter_with_indexer.indexer.reindex.assert_not_called()


@pytest.mark.asyncio
async def test_find_similar_reindexes_when_pulled_new(adapter_with_indexer):
    fake_embedder = MagicMock()
    fake_embedder.embed_one.return_value = [0.0] * 768
    adapter_with_indexer.embedder = fake_embedder
    fake_store = MagicMock()
    fake_store.query.return_value = []
    adapter_with_indexer.store = fake_store

    with patch("jkw_obs_mcp.mcp.server.ensure_brain_repo_fresh", return_value=True):
        await dispatch_tool(
            adapter_with_indexer, "find_similar", {"text": "test"}
        )

    adapter_with_indexer.indexer.reindex.assert_called_once_with(scope="incremental")


@pytest.mark.asyncio
async def test_find_similar_skips_reindex_when_not_pulled(adapter_with_indexer):
    fake_embedder = MagicMock()
    fake_embedder.embed_one.return_value = [0.0] * 768
    adapter_with_indexer.embedder = fake_embedder
    fake_store = MagicMock()
    fake_store.query.return_value = []
    adapter_with_indexer.store = fake_store

    with patch("jkw_obs_mcp.mcp.server.ensure_brain_repo_fresh", return_value=False):
        await dispatch_tool(
            adapter_with_indexer, "find_similar", {"text": "test"}
        )

    adapter_with_indexer.indexer.reindex.assert_not_called()
```

- [ ] **Step 2: Run new tests to verify they fail**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/test_mcp_record_learning_tool.py -v -k "reindex_when_pulled_new or skips_reindex_when_not_pulled"
```

Expected: 4 failures — the dispatch branches don't yet call `indexer.reindex` based on the helper's return value.

- [ ] **Step 3: Modify `src/jkw_obs_mcp/mcp/server.py`**

Find the `search_vault` dispatch branch:

```python
    if name == "search_vault":
        ensure_brain_repo_fresh(adapter.vault_root, max_age_minutes=5)
        query_vec = adapter.embedder.embed_one(arguments["query"])
        hits = adapter.store.query(query_vec, top_k=arguments.get("top_k", 10))
        lines = [f"- `{h.path}` (distance {h.distance:.4f})" for h in hits]
        return [TextContent(type="text", text="\n".join(lines))]
```

Replace with:

```python
    if name == "search_vault":
        pulled_new = ensure_brain_repo_fresh(adapter.vault_root, max_age_minutes=5)
        if pulled_new and getattr(adapter, "indexer", None) is not None:
            adapter.indexer.reindex(scope="incremental")
        query_vec = adapter.embedder.embed_one(arguments["query"])
        hits = adapter.store.query(query_vec, top_k=arguments.get("top_k", 10))
        lines = [f"- `{h.path}` (distance {h.distance:.4f})" for h in hits]
        return [TextContent(type="text", text="\n".join(lines))]
```

Find the `find_similar` dispatch branch:

```python
    if name == "find_similar":
        ensure_brain_repo_fresh(adapter.vault_root, max_age_minutes=5)
        query_vec = adapter.embedder.embed_one(arguments["text"])
        hits = adapter.store.query(query_vec, top_k=arguments.get("top_k", 5))
        lines = [f"- `{h.path}` (distance {h.distance:.4f})" for h in hits]
        return [TextContent(type="text", text="\n".join(lines))]
```

Replace with:

```python
    if name == "find_similar":
        pulled_new = ensure_brain_repo_fresh(adapter.vault_root, max_age_minutes=5)
        if pulled_new and getattr(adapter, "indexer", None) is not None:
            adapter.indexer.reindex(scope="incremental")
        query_vec = adapter.embedder.embed_one(arguments["text"])
        hits = adapter.store.query(query_vec, top_k=arguments.get("top_k", 5))
        lines = [f"- `{h.path}` (distance {h.distance:.4f})" for h in hits]
        return [TextContent(type="text", text="\n".join(lines))]
```

- [ ] **Step 4: Run tests to verify they pass**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/test_mcp_record_learning_tool.py -v
```

Expected: 12 passed (8 from Plan 7 + 4 new from this task).

- [ ] **Step 5: Run full suite**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/ -q
```

Expected: 257 passed (251 from Plan 8 + 2 from Task 1 + 4 from Task 2).

If any tests fail due to the existing tests in `test_mcp_record_learning_tool.py` that pre-existed Plan 7 (e.g., `test_search_vault_calls_ensure_brain_repo_fresh`) — those tests use a `fake_pull` that returns None implicitly. Under the new `if pulled_new and indexer:` check, None is falsy → indexer.reindex is NOT called. The pre-existing tests don't assert anything about reindex, so they continue to pass. If a different test fails, debug.

- [ ] **Step 6: Commit**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git add src/jkw_obs_mcp/mcp/server.py tests/test_mcp_record_learning_tool.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: search_vault + find_similar reindex when pull moved HEAD"
```

---

## Task 3: Cross-machine smoke test + plan-8-5-complete tag

This task is non-TDD. Verifies the cross-machine read flow works end-to-end without manual intervention.

**Files:** None — captures findings as kb learnings if surprises arise.

- [ ] **Step 1: Push the fix to origin/main + pull on scs**

On Mac:
```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git push origin main
```

On scs (via SSH from Mac):
```bash
ssh scs 'cd ~/arcadia/jkw_obs-mcp && git pull --ff-only && source .venv/bin/activate && pip install -e . > /dev/null 2>&1 && echo "scs updated"'
```

If `pip install -e .` is needed because of code changes — usually not, since `-e` mode picks up source changes automatically — skip it. Verify scs has the latest commit:
```bash
ssh scs 'cd ~/arcadia/jkw_obs-mcp && git log --oneline -1'
```
Expected: matches origin/main HEAD.

- [ ] **Step 2: Forward direction — write on Mac, search from scs**

On Mac, write a small test learning via `record_learning` (you can use the actual smoke-test learning content; this becomes a real artifact recording Plan 8.5's close-out):

> category: decisions
> title: Plan 8.5 closes cross-machine search latency
> content: After Plan 8.5, writing a learning on machine A surfaces in search_vault on machine B without manual reindex. ensure_brain_repo_fresh now returns True iff the pull moved HEAD; search_vault and find_similar dispatch branches reindex incrementally only when there's actually new content to index. Verified with the symmetric round trip Mac → scs and scs → Mac on 2026-04-30.
> tags: [jkw-obs-mcp, plan-8-5, cross-machine, search]
> applies_to: [jkw-obs-mcp]

After it pushes, **wait 5+ minutes** so scs's existing pull cache expires (or, if you can't wait, restart the Claude Code session on scs which clears the in-process state — actually scrap that, the cache is in the on-disk state file `~/.config/jkw-obs-mcp/brain-last-pull.json`, so wait or delete that file on scs).

Then in a Claude Code session on scs, ask:

> Use jkw-obs search_vault for: Plan 8.5 cross-machine search

Expected: top hit is the just-written note with distance < 1.0. **Crucially: no manual reindex was needed on scs.**

- [ ] **Step 3: Reverse direction — write on scs, search from Mac**

On scs, write a learning via Claude Code:

> category: decisions
> title: Plan 8.5 verified scs to Mac direction
> content: ...

After it pushes, wait 5+ minutes (or delete `~/.config/jkw-obs-mcp/brain-last-pull.json` on Mac to force a fresh pull-with-reindex).

Then in a Claude Code session on Mac, ask:

> Use jkw-obs search_vault for: Plan 8.5 verified scs to Mac

Expected: top hit is the scs-written note. No manual reindex on Mac.

- [ ] **Step 4: Idempotency / no-spurious-reindex check**

In a Claude Code session on Mac, run `search_vault` 3 times in quick succession with arbitrary queries. Watch for unexpected delays — there should be NO reindex on the 2nd and 3rd searches (cache hit means no pull means no reindex). If you see noticeable latency on calls 2-3, something's off.

- [ ] **Step 5: Tag and push**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git tag plan-8-5-complete
git push origin plan-8-5-complete
```

---

## Self-Review Checklist

- [ ] Task 1: `ensure_brain_repo_fresh` signature is `-> bool`; 8 tests pass (6 updated + 2 new)
- [ ] Task 2: `search_vault` and `find_similar` reindex only when `pulled_new=True`; 12 tests in `test_mcp_record_learning_tool.py` pass (8 from Plan 7 + 4 new)
- [ ] Full suite: 257 passed (251 + 6 new)
- [ ] Task 3 forward: Mac → scs cross-machine search worked without manual reindex
- [ ] Task 3 reverse: scs → Mac cross-machine search worked without manual reindex
- [ ] Tag `plan-8-5-complete` pushed

When all boxes ticked, Plan 8.5 done.

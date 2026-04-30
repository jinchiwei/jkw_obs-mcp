# Plan 8: Cluster Rollout (scs first) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship jkw-obs-mcp to scs (UCSF login node) so any Claude Code session there can read the brain (`search_vault`, `find_similar`, `read_note`, `list_notes`, `reindex`) and write learnings (`record_learning`). Build the bootstrap machinery as the foundation for Plans 9-12 (per-cluster rollouts to fac/cph/teal/cdx).

**Architecture:** Three layers. (1) `scripts/bootstrap.sh` — thin shell wrapper (~30 lines) that handles "I have nothing": detect Python 3.11+, mkdir `~/arcadia/`, clone `jkw_obs-mcp`, create `.venv/` (uv if available, stdlib `python3 -m venv` fallback), `pip install -e .`, exec `jkw-obs-mcp-setup`. (2) Python installer extension — two new modules (`bootstrap_brain_repo`, `mcp_registration`) wired into the existing `installer/cli.py` orchestrator. (3) Tool-surface filter — `tools_for_adapter` in `mcp/server.py` excludes `compile_raw`, `compile_email`, `generate_daily_review` when `platform.system() != "Darwin"`. Plan 8 ships scs as part of the same plan because scs is the smoke test for the machinery.

**Tech Stack:** Python stdlib only — `subprocess` for git + `claude` CLI, `pathlib`, `platform`, `tomllib` (read-only) / `tomli_w` is NOT used; we write TOML by hand since the schema is tiny. Bash 4+ for bootstrap.sh. No new pip deps.

**Realistic effort: ~2-3 days** (7 tasks).

---

## File Structure

```
jkw_obs-mcp/
├── scripts/
│   └── bootstrap.sh                              NEW: shell bootstrap (curl-able)
├── src/jkw_obs_mcp/
│   ├── installer/
│   │   ├── bootstrap_brain_repo.py               NEW: clone-or-pull jkw_obs-brain;
│   │   │                                              write config.toml
│   │   ├── mcp_registration.py                   NEW: claude mcp add or print-and-copy
│   │   └── cli.py                                MODIFY: add Steps 5+6 (brain repo,
│   │                                                     mcp registration)
│   └── mcp/server.py                             MODIFY: tools_for_adapter filters
│                                                         compile/daily-review on non-Darwin
└── tests/
    ├── test_installer_bootstrap_brain_repo.py    NEW: clone, pull, config.toml write
    ├── test_installer_mcp_registration.py        NEW: claude-cli vs print-and-copy
    ├── test_mcp_tools_platform_filter.py         NEW: 6 tools on Linux, 10 on Darwin
    └── test_installer_cli.py                     MODIFY (or NEW): step ordering on Linux
```

**Why this layout:**
- `bootstrap.sh` is at top level under `scripts/` so the curl URL is obvious and stable.
- New installer modules sit next to existing ones (`config_dir.py`, `gmail_oauth.py`, `launchd.py`) following established convention.
- The platform filter lives in `tools_for_adapter` (the surface) rather than in each dispatch branch — one gate, not five.
- Tests for installer modules use the same `tmp_path` + mocked `subprocess.run` pattern Plan 7 established (see `tests/test_brain_sync.py`).

---

## Task 1: Manual scs recon — pre-implementation environment check

This task is non-TDD. It's a manual verification that scs is set up enough for the rest of the plan to work. Skip nothing; surprises here become Plan 8 Task adjustments before code is written.

**Files:** None — this task creates a kb learning if surprises are found.

- [ ] **Step 1: SSH into scs**

```bash
ssh callosum
```

(`callosum` is the registered hostname alias for scs in `machines.toml`. If your SSH config maps differently, use whichever ssh target you normally use.)

- [ ] **Step 2: Confirm Python version is 3.11+**

```bash
python3 --version
```

Expected: `Python 3.11.x` or higher.

If 3.10 or older: STOP. Capture as a Plan 8 blocker. Either install a newer Python (pyenv / conda / module load) or document the version-pin requirement in the design doc.

- [ ] **Step 3: Confirm GitHub SSH key is set up for the brain repo**

```bash
ssh -T git@github.com
```

Expected: `Hi jinchiwei! You've successfully authenticated...`

If `Permission denied`: STOP. Set up an SSH key on scs (`ssh-keygen -t ed25519`, copy `~/.ssh/id_ed25519.pub` to GitHub → Settings → SSH keys). Bootstrap.sh assumes this works; Task 6 won't be able to clone otherwise.

- [ ] **Step 4: Confirm the brain repo is reachable**

```bash
git ls-remote git@github.com:jinchiwei/jkw_obs-brain.git HEAD
```

Expected: a single line with the HEAD SHA. Confirms the repo exists, is accessible, and your auth works for it specifically.

- [ ] **Step 5: Check for `claude` CLI on PATH**

```bash
command -v claude && claude --version
```

If found: note the version; the bootstrap will run `claude mcp add` automatically.
If not found: bootstrap will fall back to print-and-copy. Note this so Task 7 (smoke test) tests both paths.

- [ ] **Step 6: Check for `uv`**

```bash
command -v uv && uv --version
```

If found: bootstrap takes the fast path.
If not found: bootstrap uses stdlib `python3 -m venv` fallback. Both paths must work; this just informs the smoke test.

- [ ] **Step 7: Check `~/arcadia/` and home dir quota**

```bash
ls -la ~/arcadia 2>/dev/null && echo "exists" || echo "missing"
quota -s 2>/dev/null || df -h ~
```

If `~/arcadia` exists: fine, bootstrap will reuse it.
If missing: fine, bootstrap will `mkdir -p ~/arcadia`.
If home quota is under 1GB free: STOP. The brain repo is ~80MB but the venv + jina-zh model adds ~700MB. Plan a workaround (symlink `~/arcadia/jkw_obs-mcp/.venv` to `/scratch/$USER/...`) before Task 6.

- [ ] **Step 8: Capture findings**

If anything in Steps 2-7 surprised you (wrong Python, no SSH key, no `claude`, no `uv`, tight quota), use `record_learning` from your Mac Claude session right now to capture it as a `constraints` learning. Title example: `scs: Python 3.10 default — pyenv required`.

If everything was clean, no learning needed — proceed to Task 2.

- [ ] **Step 9: No commit (this task makes no code changes)**

This task's output is either GO (proceed to Task 2) or a kb learning + adjusted plan. No files in jkw_obs-mcp change.

---

## Task 2: Platform filter for tools_for_adapter

**Files:**
- Modify: `src/jkw_obs_mcp/mcp/server.py` — `tools_for_adapter` filters by platform
- Test: `tests/test_mcp_tools_platform_filter.py` (new file)

`tools_for_adapter` currently returns all 10 tools unconditionally. On a Linux cluster, `compile_raw`, `compile_email`, and `generate_daily_review` should be excluded — they need Anthropic creds (Versa needs UCSF VPN), Gmail OAuth, and Mac-only EventKit calendar. Filter by `platform.system()`.

- [ ] **Step 1: Failing tests at `tests/test_mcp_tools_platform_filter.py`**

```python
"""Platform filter for tools_for_adapter — Mac-only tools excluded on Linux."""

from __future__ import annotations

from unittest.mock import patch

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.mcp.server import tools_for_adapter


_MAC_ONLY_TOOLS = {"compile_raw", "compile_email", "generate_daily_review"}
_CROSS_PLATFORM_TOOLS = {
    "read_note",
    "list_notes",
    "write_kb_note",
    "search_vault",
    "find_similar",
    "reindex",
    "record_learning",
}


def test_darwin_returns_all_ten_tools(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    with patch("jkw_obs_mcp.mcp.server.platform.system", return_value="Darwin"):
        tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}
    assert names == _CROSS_PLATFORM_TOOLS | _MAC_ONLY_TOOLS
    assert len(tools) == 10


def test_linux_excludes_mac_only_tools(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="scs")
    with patch("jkw_obs_mcp.mcp.server.platform.system", return_value="Linux"):
        tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}
    assert names == _CROSS_PLATFORM_TOOLS
    assert _MAC_ONLY_TOOLS.isdisjoint(names)
    assert len(tools) == 7


def test_unknown_platform_excludes_mac_only_tools(tmp_vault):
    """Conservative: anything that isn't Darwin gets the Linux tool set."""
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="scs")
    with patch("jkw_obs_mcp.mcp.server.platform.system", return_value="Windows"):
        tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}
    assert _MAC_ONLY_TOOLS.isdisjoint(names)


def test_record_learning_is_present_on_linux(tmp_vault):
    """record_learning must be available on cluster sessions — load-bearing for Plan 8."""
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="scs")
    with patch("jkw_obs_mcp.mcp.server.platform.system", return_value="Linux"):
        tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}
    assert "record_learning" in names


def test_search_vault_is_present_on_linux(tmp_vault):
    """search_vault must be available on cluster sessions — load-bearing for Plan 8."""
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="scs")
    with patch("jkw_obs_mcp.mcp.server.platform.system", return_value="Linux"):
        tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}
    assert "search_vault" in names
```

- [ ] **Step 2: Run tests to verify they fail**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/test_mcp_tools_platform_filter.py -v
```

Expected: 5 failures — `tools_for_adapter` doesn't import `platform` and doesn't filter, so the Linux tests will see all 10 tools.

- [ ] **Step 3: Modify `src/jkw_obs_mcp/mcp/server.py`**

At the top of the file, add `import platform` to the existing imports (currently has `import asyncio`, `import os`, etc.).

In `tools_for_adapter`, wrap the existing list of `Tool(...)` entries so the Mac-only ones are conditionally included. The cleanest shape: keep the full list as before, then filter at the end.

Replace the function body (the line `_ = adapter` and `return [...]`) with:

```python
    _ = adapter
    all_tools = [
        # ... existing 10 Tool entries unchanged ...
    ]
    if platform.system() == "Darwin":
        return all_tools
    mac_only = {"compile_raw", "compile_email", "generate_daily_review"}
    return [t for t in all_tools if t.name not in mac_only]
```

The full list of `Tool(...)` entries inside `all_tools = [...]` is exactly what was previously inside the bare `return [...]` — copy verbatim.

- [ ] **Step 4: Run tests to verify they pass**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/test_mcp_tools_platform_filter.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run full suite**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/ -q
```

Expected: 234 passed (229 + 5).

- [ ] **Step 6: Commit**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git add src/jkw_obs_mcp/mcp/server.py tests/test_mcp_tools_platform_filter.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: tools_for_adapter filters compile/daily-review on non-Darwin"
```

---

## Task 3: `installer/bootstrap_brain_repo.py` — clone-or-pull + write config.toml

**Files:**
- Create: `src/jkw_obs_mcp/installer/bootstrap_brain_repo.py`
- Test: `tests/test_installer_bootstrap_brain_repo.py` (new file)

Module that handles two responsibilities:
1. Ensure `~/arcadia/` exists, then clone `jkw_obs-brain` into `~/arcadia/jkw_obs-brain` if not already there. If already cloned, run `git pull --ff-only`.
2. Write `~/.config/jkw-obs-mcp/config.toml` with `vault_root = "~/arcadia/jkw_obs-brain"` and `machine.id = <auto-detected>` if the file doesn't exist. If it does, leave it alone (idempotent).

Public function: `bootstrap_brain_repo(*, brain_repo_url: str, target_dir: Path, machine_id: str, config_path: Path) -> dict`. Returns a status dict for the installer's final report.

- [ ] **Step 1: Failing tests at `tests/test_installer_bootstrap_brain_repo.py`**

```python
"""Tests for installer.bootstrap_brain_repo."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from jkw_obs_mcp.installer.bootstrap_brain_repo import bootstrap_brain_repo


def _fake_run_success():
    """All git subcommands return rc=0."""
    def fake_run(args, **kwargs):
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()
    return fake_run


def test_creates_arcadia_dir_if_missing(tmp_path):
    target = tmp_path / "arcadia" / "jkw_obs-brain"
    config = tmp_path / "config.toml"
    assert not target.parent.exists()

    with patch("jkw_obs_mcp.installer.bootstrap_brain_repo.subprocess.run",
               side_effect=_fake_run_success()):
        bootstrap_brain_repo(
            brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
            target_dir=target,
            machine_id="scs",
            config_path=config,
        )

    assert target.parent.is_dir()


def test_clones_when_target_dir_missing(tmp_path):
    target = tmp_path / "arcadia" / "jkw_obs-brain"
    config = tmp_path / "config.toml"
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.bootstrap_brain_repo.subprocess.run",
               side_effect=fake_run):
        result = bootstrap_brain_repo(
            brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
            target_dir=target,
            machine_id="scs",
            config_path=config,
        )

    # Find the clone call
    assert any("clone" in args and str(target) in args for args in runs)
    assert result["cloned"] is True
    assert result["pulled"] is False


def test_pulls_when_target_dir_exists(tmp_path):
    target = tmp_path / "arcadia" / "jkw_obs-brain"
    target.mkdir(parents=True)
    (target / ".git").mkdir()  # mark it as an existing git repo
    config = tmp_path / "config.toml"
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.bootstrap_brain_repo.subprocess.run",
               side_effect=fake_run):
        result = bootstrap_brain_repo(
            brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
            target_dir=target,
            machine_id="scs",
            config_path=config,
        )

    assert not any("clone" in args for args in runs)
    assert any("pull" in args for args in runs)
    assert result["cloned"] is False
    assert result["pulled"] is True


def test_writes_config_toml_if_missing(tmp_path):
    target = tmp_path / "arcadia" / "jkw_obs-brain"
    config = tmp_path / "config.toml"

    with patch("jkw_obs_mcp.installer.bootstrap_brain_repo.subprocess.run",
               side_effect=_fake_run_success()):
        result = bootstrap_brain_repo(
            brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
            target_dir=target,
            machine_id="scs",
            config_path=config,
        )

    assert config.is_file()
    content = config.read_text()
    assert 'vault_root = "' in content
    assert "jkw_obs-brain" in content
    assert 'id = "scs"' in content
    assert result["config_written"] is True


def test_leaves_existing_config_toml_alone(tmp_path):
    target = tmp_path / "arcadia" / "jkw_obs-brain"
    config = tmp_path / "config.toml"
    config.write_text('# existing config\n[paths]\nvault_root = "/custom/path"\n')

    with patch("jkw_obs_mcp.installer.bootstrap_brain_repo.subprocess.run",
               side_effect=_fake_run_success()):
        result = bootstrap_brain_repo(
            brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
            target_dir=target,
            machine_id="scs",
            config_path=config,
        )

    # Existing content preserved
    content = config.read_text()
    assert "# existing config" in content
    assert "/custom/path" in content
    assert result["config_written"] is False
    assert result["config_already_existed"] is True


def test_clone_failure_returns_error(tmp_path):
    target = tmp_path / "arcadia" / "jkw_obs-brain"
    config = tmp_path / "config.toml"

    def fake_run(args, **kwargs):
        class R:
            returncode = 1 if "clone" in args else 0
            stderr = "permission denied" if "clone" in args else ""
            stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.bootstrap_brain_repo.subprocess.run",
               side_effect=fake_run):
        result = bootstrap_brain_repo(
            brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
            target_dir=target,
            machine_id="scs",
            config_path=config,
        )

    assert result["cloned"] is False
    assert result["error"] is not None
    assert "permission" in result["error"].lower() or "clone" in result["error"].lower()
    # config.toml NOT written when clone failed (the brain repo isn't there)
    assert not config.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/test_installer_bootstrap_brain_repo.py -v
```

Expected: ImportError — `bootstrap_brain_repo` module doesn't exist.

- [ ] **Step 3: Create `src/jkw_obs_mcp/installer/bootstrap_brain_repo.py`**

```python
"""Bootstrap the brain repo on a fresh cluster: clone-or-pull + write config.toml.

Idempotent. Re-running on a configured cluster is a no-op (pull instead of clone,
preserve existing config.toml). Returns a status dict for the installer's final
report.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def bootstrap_brain_repo(
    *,
    brain_repo_url: str,
    target_dir: Path,
    machine_id: str,
    config_path: Path,
) -> dict:
    """Clone or pull the brain repo, then write config.toml if missing.

    target_dir is the absolute path where the brain repo lives (e.g.,
    ~/arcadia/jkw_obs-brain). Parent dirs are created if missing.

    Returns:
      {
        "cloned": bool,                   # True if we just cloned
        "pulled": bool,                   # True if we pulled an existing clone
        "config_written": bool,           # True if config.toml was created
        "config_already_existed": bool,   # True if config.toml was preserved
        "error": str | None,              # populated on git failure
      }
    """
    result: dict = {
        "cloned": False,
        "pulled": False,
        "config_written": False,
        "config_already_existed": False,
        "error": None,
    }

    # Ensure parent dir exists (e.g., ~/arcadia/)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    # Clone or pull
    if (target_dir / ".git").is_dir():
        pull = subprocess.run(
            ["git", "-C", str(target_dir), "pull", "--ff-only"],
            capture_output=True, text=True,
        )
        if pull.returncode != 0:
            result["error"] = f"git pull failed: {pull.stderr.strip()}"
            return result
        result["pulled"] = True
    else:
        clone = subprocess.run(
            ["git", "clone", brain_repo_url, str(target_dir)],
            capture_output=True, text=True,
        )
        if clone.returncode != 0:
            result["error"] = f"git clone failed: {clone.stderr.strip()}"
            return result
        result["cloned"] = True

    # Write config.toml if missing
    if config_path.is_file():
        result["config_already_existed"] = True
        return result

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_render_config_toml(
        vault_root=target_dir,
        machine_id=machine_id,
    ))
    result["config_written"] = True
    return result


def _render_config_toml(*, vault_root: Path, machine_id: str) -> str:
    """Render a minimal config.toml for a fresh cluster.

    Schema must match what jkw_obs_mcp.config.load_config expects:
      [paths] vault_root = "..."
      [machine] id = "..."
      [embeddings] model = "jinaai/jina-embeddings-v2-base-zh"
      [generation] daily_review_enabled = false
    """
    return (
        f'[paths]\n'
        f'vault_root = "{vault_root}"\n'
        f'\n'
        f'[machine]\n'
        f'id = "{machine_id}"\n'
        f'\n'
        f'[generation]\n'
        f'daily_review_enabled = false\n'
        f'\n'
        f'[embeddings]\n'
        f'model = "jinaai/jina-embeddings-v2-base-zh"\n'
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/test_installer_bootstrap_brain_repo.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run full suite**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/ -q
```

Expected: 240 passed (234 + 6).

- [ ] **Step 6: Commit**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git add src/jkw_obs_mcp/installer/bootstrap_brain_repo.py tests/test_installer_bootstrap_brain_repo.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: installer.bootstrap_brain_repo — clone-or-pull + config.toml"
```

---

## Task 4: `installer/mcp_registration.py` — claude mcp add or print-and-copy

**Files:**
- Create: `src/jkw_obs_mcp/installer/mcp_registration.py`
- Test: `tests/test_installer_mcp_registration.py` (new file)

Module that registers jkw-obs as an MCP server with Claude Code. Two paths: (a) if `claude` CLI is on PATH, run `claude mcp add jkw-obs --command jkw-obs-mcp` and report success; (b) if not, print the exact command for the user to run after installing Claude Code.

Public function: `register_mcp_server() -> dict`. Returns a status dict.

- [ ] **Step 1: Failing tests at `tests/test_installer_mcp_registration.py`**

```python
"""Tests for installer.mcp_registration."""

from __future__ import annotations

from unittest.mock import patch

from jkw_obs_mcp.installer.mcp_registration import register_mcp_server


def test_runs_claude_mcp_add_when_cli_available():
    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               return_value="/usr/local/bin/claude"), \
         patch("jkw_obs_mcp.installer.mcp_registration.subprocess.run",
               side_effect=fake_run):
        result = register_mcp_server()

    assert result["registered"] is True
    assert result["instruction"] is None
    assert any("mcp" in args and "add" in args for args in runs)


def test_prints_command_when_claude_cli_missing(capsys):
    """When claude is not on PATH, print the command for manual run."""
    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               return_value=None):
        result = register_mcp_server()

    assert result["registered"] is False
    assert result["instruction"] is not None
    assert "claude mcp add" in result["instruction"]
    # The instruction is also printed to stdout for the installer's report
    captured = capsys.readouterr()
    assert "claude mcp add" in captured.out


def test_claude_mcp_add_failure_returns_instruction(capsys):
    """If claude is on PATH but the add command fails, fall back to instruction."""
    def fake_run(args, **kwargs):
        class R: returncode = 1; stderr = "already registered"; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               return_value="/usr/local/bin/claude"), \
         patch("jkw_obs_mcp.installer.mcp_registration.subprocess.run",
               side_effect=fake_run):
        result = register_mcp_server()

    assert result["registered"] is False
    assert result["error"] is not None
    assert "already registered" in result["error"]
    assert result["instruction"] is not None


def test_already_registered_is_idempotent(capsys):
    """If `claude mcp list` shows jkw-obs already there, skip the add."""
    list_calls = []
    add_calls = []

    def fake_run(args, **kwargs):
        if "list" in args:
            list_calls.append(args)
            class R:
                returncode = 0
                stderr = ""
                stdout = "jkw-obs: jkw-obs-mcp\nother-server: foo\n"
            return R()
        add_calls.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               return_value="/usr/local/bin/claude"), \
         patch("jkw_obs_mcp.installer.mcp_registration.subprocess.run",
               side_effect=fake_run):
        result = register_mcp_server()

    assert result["registered"] is True
    assert result["already_registered"] is True
    assert len(list_calls) == 1
    assert len(add_calls) == 0  # never tried to add


def test_instruction_text_includes_exact_command():
    """The instruction text must be a copy-paste-ready command."""
    with patch("jkw_obs_mcp.installer.mcp_registration.shutil.which",
               return_value=None):
        result = register_mcp_server()

    inst = result["instruction"]
    assert "claude mcp add jkw-obs" in inst
    # No placeholders or template variables
    assert "{" not in inst
    assert "<" not in inst
```

- [ ] **Step 2: Run tests to verify they fail**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/test_installer_mcp_registration.py -v
```

Expected: ImportError — `mcp_registration` module doesn't exist.

- [ ] **Step 3: Create `src/jkw_obs_mcp/installer/mcp_registration.py`**

```python
"""Register jkw-obs as an MCP server with Claude Code.

If `claude` CLI is on PATH, run `claude mcp add jkw-obs --command jkw-obs-mcp`.
Otherwise (or if the add fails), print the exact command for the user to run
after installing Claude Code.

Idempotent: checks `claude mcp list` first and skips the add if already present.
"""

from __future__ import annotations

import shutil
import subprocess


_INSTALL_COMMAND = "claude mcp add jkw-obs --command jkw-obs-mcp"


def register_mcp_server() -> dict:
    """Try to register jkw-obs with Claude Code. Returns status dict.

    Returns:
      {
        "registered": bool,                # True if jkw-obs is now registered
                                           # (either we added it OR it was already there)
        "already_registered": bool,        # True if it was already registered
        "instruction": str | None,         # printed when manual action is required
        "error": str | None,               # populated on subprocess failure
      }
    """
    result: dict = {
        "registered": False,
        "already_registered": False,
        "instruction": None,
        "error": None,
    }

    claude_path = shutil.which("claude")
    if claude_path is None:
        result["instruction"] = (
            f"Claude Code CLI not found on PATH. After installing Claude Code, run:\n\n"
            f"    {_INSTALL_COMMAND}\n"
        )
        print(result["instruction"])
        return result

    # Idempotency: check if jkw-obs is already registered
    list_proc = subprocess.run(
        ["claude", "mcp", "list"],
        capture_output=True, text=True,
    )
    if list_proc.returncode == 0 and "jkw-obs" in list_proc.stdout:
        result["registered"] = True
        result["already_registered"] = True
        return result

    # Run the add command
    add_proc = subprocess.run(
        ["claude", "mcp", "add", "jkw-obs", "--command", "jkw-obs-mcp"],
        capture_output=True, text=True,
    )
    if add_proc.returncode != 0:
        result["error"] = add_proc.stderr.strip() or add_proc.stdout.strip()
        result["instruction"] = (
            f"`claude mcp add` failed: {result['error']}\n"
            f"Run manually:\n\n    {_INSTALL_COMMAND}\n"
        )
        print(result["instruction"])
        return result

    result["registered"] = True
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/test_installer_mcp_registration.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run full suite**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/ -q
```

Expected: 245 passed (240 + 5).

- [ ] **Step 6: Commit**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git add src/jkw_obs_mcp/installer/mcp_registration.py tests/test_installer_mcp_registration.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: installer.mcp_registration — claude mcp add with print-and-copy fallback"
```

---

## Task 5: Extend `installer/cli.py` with new steps

**Files:**
- Modify: `src/jkw_obs_mcp/installer/cli.py`
- Test: `tests/test_installer_cli.py` (new file — there's currently no test for cli.py)

Wire the two new modules into the existing orchestrator. The cli.py currently has Steps 1-4 (config_dir, machines.toml check, Gmail OAuth Mac-only, launchd Mac-only). We add:
- **Step 5: brain repo bootstrap** — runs on all platforms (Mac and Linux)
- **Step 6: MCP registration** — runs on all platforms

Steps 5 and 6 run AFTER the existing Mac-only Steps 3-4 (so that on a Mac fresh install, Gmail OAuth happens before brain repo bootstrap — though they don't actually depend on each other, the order matches install/setup mental model).

Brain repo URL is hard-coded to `git@github.com:jinchiwei/jkw_obs-brain.git`. Target dir is `~/arcadia/jkw_obs-brain`. Machine_id comes from `detect_machine_id` (which uses `current_hostname()` against machines.toml).

- [ ] **Step 1: Failing tests at `tests/test_installer_cli.py`**

```python
"""Tests for installer.cli orchestration — Step 5 (brain repo) and Step 6 (mcp)."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from jkw_obs_mcp.installer.cli import main


def test_main_calls_bootstrap_brain_repo(tmp_path, monkeypatch, capsys):
    """The main() orchestrator runs brain repo bootstrap on all platforms."""
    monkeypatch.setenv("HOME", str(tmp_path))
    bootstrap_calls = []

    def fake_bootstrap(**kwargs):
        bootstrap_calls.append(kwargs)
        return {"cloned": True, "pulled": False, "config_written": True,
                "config_already_existed": False, "error": None}

    with patch("jkw_obs_mcp.installer.cli.bootstrap_brain_repo",
               side_effect=fake_bootstrap), \
         patch("jkw_obs_mcp.installer.cli.register_mcp_server",
               return_value={"registered": True, "already_registered": False,
                             "instruction": None, "error": None}), \
         patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Linux"), \
         patch("jkw_obs_mcp.installer.cli.current_hostname", return_value="callosum"), \
         patch("jkw_obs_mcp.installer.cli.is_hostname_registered", return_value=True):
        rc = main()

    assert rc == 0
    assert len(bootstrap_calls) == 1
    kwargs = bootstrap_calls[0]
    assert "jkw_obs-brain" in str(kwargs["target_dir"])
    assert "arcadia" in str(kwargs["target_dir"])


def test_main_calls_register_mcp_server_on_linux(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    mcp_calls = []

    def fake_register():
        mcp_calls.append(True)
        return {"registered": True, "already_registered": False,
                "instruction": None, "error": None}

    with patch("jkw_obs_mcp.installer.cli.bootstrap_brain_repo",
               return_value={"cloned": True, "pulled": False, "config_written": True,
                             "config_already_existed": False, "error": None}), \
         patch("jkw_obs_mcp.installer.cli.register_mcp_server",
               side_effect=fake_register), \
         patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Linux"), \
         patch("jkw_obs_mcp.installer.cli.current_hostname", return_value="callosum"), \
         patch("jkw_obs_mcp.installer.cli.is_hostname_registered", return_value=True):
        rc = main()

    assert rc == 0
    assert len(mcp_calls) == 1


def test_main_calls_register_mcp_server_on_darwin_too(monkeypatch, tmp_path):
    """MCP registration runs on Mac too, after the Mac-only Gmail/launchd steps."""
    monkeypatch.setenv("HOME", str(tmp_path))
    mcp_calls = []

    def fake_register():
        mcp_calls.append(True)
        return {"registered": True, "already_registered": False,
                "instruction": None, "error": None}

    with patch("jkw_obs_mcp.installer.cli.bootstrap_brain_repo",
               return_value={"cloned": False, "pulled": True, "config_written": False,
                             "config_already_existed": True, "error": None}), \
         patch("jkw_obs_mcp.installer.cli.register_mcp_server",
               side_effect=fake_register), \
         patch("jkw_obs_mcp.installer.cli.gmail_oauth_setup",
               return_value={"already_setup": True}), \
         patch("jkw_obs_mcp.installer.cli.install_launchd_agent",
               return_value={"already_installed": True}), \
         patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Darwin"), \
         patch("jkw_obs_mcp.installer.cli.current_hostname",
               return_value="dreamingmachine"), \
         patch("jkw_obs_mcp.installer.cli.is_hostname_registered", return_value=True):
        rc = main()

    assert rc == 0
    assert len(mcp_calls) == 1


def test_main_passes_machine_id_to_bootstrap(monkeypatch, tmp_path):
    """Machine ID detected from hostname is threaded into bootstrap_brain_repo."""
    monkeypatch.setenv("HOME", str(tmp_path))
    bootstrap_calls = []

    def fake_bootstrap(**kwargs):
        bootstrap_calls.append(kwargs)
        return {"cloned": True, "pulled": False, "config_written": True,
                "config_already_existed": False, "error": None}

    with patch("jkw_obs_mcp.installer.cli.bootstrap_brain_repo",
               side_effect=fake_bootstrap), \
         patch("jkw_obs_mcp.installer.cli.register_mcp_server",
               return_value={"registered": True, "already_registered": False,
                             "instruction": None, "error": None}), \
         patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Linux"), \
         patch("jkw_obs_mcp.installer.cli.current_hostname", return_value="callosum"), \
         patch("jkw_obs_mcp.installer.cli.is_hostname_registered", return_value=True), \
         patch("jkw_obs_mcp.installer.cli.detect_machine_id", return_value="scs"):
        main()

    assert bootstrap_calls[0]["machine_id"] == "scs"
```

- [ ] **Step 2: Run tests to verify they fail**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/test_installer_cli.py -v
```

Expected: ImportError on `bootstrap_brain_repo` and `register_mcp_server` not existing in `installer.cli` module namespace.

- [ ] **Step 3: Modify `src/jkw_obs_mcp/installer/cli.py`**

Add new imports near the existing `from jkw_obs_mcp.installer.* import` block:

```python
from jkw_obs_mcp.installer.bootstrap_brain_repo import bootstrap_brain_repo
from jkw_obs_mcp.installer.mcp_registration import register_mcp_server
from jkw_obs_mcp.config import detect_machine_id, load_machines
```

(`detect_machine_id` and `load_machines` already exist in `jkw_obs_mcp.config` — verified by Plan 1's `tests/test_config.py`.)

In `main()`, after the existing platform-specific block (lines ~57-73 — the `if plat == "Darwin":` / `else:` block ending with `status["launchd"] = {...}`), add:

```python
    # Step 5: brain repo bootstrap (all platforms)
    print("Step 5: brain repo bootstrap")
    machines_registry = load_machines(machines_toml)
    machine_id = detect_machine_id(
        machines_registry,
        hostname=current_hostname(),
        os_name=plat.lower(),
    )
    config_path = Path.home() / ".config" / "jkw-obs-mcp" / "config.toml"
    target_dir = Path.home() / "arcadia" / "jkw_obs-brain"
    status["brain_repo"] = bootstrap_brain_repo(
        brain_repo_url="git@github.com:jinchiwei/jkw_obs-brain.git",
        target_dir=target_dir,
        machine_id=machine_id,
        config_path=config_path,
    )
    print(f"  → {status['brain_repo']}")
    print()

    # Step 6: MCP registration (all platforms)
    print("Step 6: MCP server registration with Claude Code")
    status["mcp_registration"] = register_mcp_server()
    print(f"  → {status['mcp_registration']}")
    print()
```

You also need `import platform` at the top — already present.

- [ ] **Step 4: Run tests to verify they pass**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/test_installer_cli.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run full suite**

```
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pytest tests/ -q
```

Expected: 249 passed (245 + 4).

- [ ] **Step 6: Commit**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git add src/jkw_obs_mcp/installer/cli.py tests/test_installer_cli.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: installer.cli — wire brain repo bootstrap + MCP registration steps"
```

---

## Task 6: `scripts/bootstrap.sh` — single-command bootstrap from fresh SSH

**Files:**
- Create: `scripts/bootstrap.sh`

Thin shell wrapper. Job: take a fresh SSH session into a Linux cluster and produce a working MCP node. Handles "I have nothing": detect Python, mkdir `~/arcadia/`, clone `jkw_obs-mcp`, create `.venv/` (uv-or-stdlib), `pip install -e .`, exec `jkw-obs-mcp-setup`.

Idempotent. Re-running on a configured machine passes through to the Python installer which itself is idempotent.

This task has no Python tests — exercised by the Task 7 smoke test on actual scs hardware.

- [ ] **Step 1: Create `scripts/bootstrap.sh`**

```bash
#!/usr/bin/env bash
# bootstrap.sh — single-command setup for jkw-obs-mcp on a fresh Linux cluster.
#
# Usage: curl -fsSL https://raw.githubusercontent.com/jinchiwei/jkw_obs-mcp/main/scripts/bootstrap.sh | bash
#
# What this does:
#   1. Verifies Python 3.11+ is on PATH
#   2. Ensures ~/arcadia/ exists
#   3. Clones jkw_obs-mcp to ~/arcadia/jkw_obs-mcp (or pulls if present)
#   4. Creates ~/arcadia/jkw_obs-mcp/.venv (via uv if available, else python3 -m venv)
#   5. pip install -e . into the venv
#   6. Execs jkw-obs-mcp-setup (which clones brain repo, writes config, registers MCP)
#
# Idempotent. Re-running is safe.

set -euo pipefail

REPO_URL="https://github.com/jinchiwei/jkw_obs-mcp.git"
ARCADIA_DIR="$HOME/arcadia"
REPO_DIR="$ARCADIA_DIR/jkw_obs-mcp"
VENV_DIR="$REPO_DIR/.venv"

echo "==> jkw-obs-mcp bootstrap"

# Step 1: Python 3.11+
echo "Step 1: checking Python version"
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found on PATH. Install Python 3.11+ and re-run." >&2
    exit 1
fi
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    echo "ERROR: Python $PY_VERSION found; need 3.11+. Install a newer Python and re-run." >&2
    exit 1
fi
echo "  → Python $PY_VERSION"

# Step 2: ~/arcadia/
echo "Step 2: ensuring $ARCADIA_DIR exists"
mkdir -p "$ARCADIA_DIR"
echo "  → $ARCADIA_DIR"

# Step 3: clone or pull jkw_obs-mcp
echo "Step 3: jkw_obs-mcp repo"
if [ -d "$REPO_DIR/.git" ]; then
    echo "  → already cloned at $REPO_DIR; pulling latest"
    git -C "$REPO_DIR" pull --ff-only
else
    echo "  → cloning $REPO_URL to $REPO_DIR"
    git clone "$REPO_URL" "$REPO_DIR"
fi

# Step 4: create venv
echo "Step 4: virtualenv at $VENV_DIR"
if [ -d "$VENV_DIR" ]; then
    echo "  → already exists; reusing"
elif command -v uv >/dev/null 2>&1; then
    echo "  → using uv to create venv"
    (cd "$REPO_DIR" && uv venv)
else
    echo "  → using stdlib python3 -m venv"
    python3 -m venv "$VENV_DIR"
fi

# Step 5: install package
echo "Step 5: installing jkw_obs_mcp package"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
if command -v uv >/dev/null 2>&1; then
    (cd "$REPO_DIR" && uv pip install -e .)
else
    pip install --upgrade pip
    (cd "$REPO_DIR" && pip install -e .)
fi
echo "  → installed"

# Step 6: run jkw-obs-mcp-setup
echo "Step 6: running jkw-obs-mcp-setup"
jkw-obs-mcp-setup

echo
echo "==> Bootstrap complete."
echo
echo "To use: in a new shell, run \`source $VENV_DIR/bin/activate\` to get jkw-obs-mcp on PATH."
echo "Or in Claude Code: the tool surface should now include jkw-obs (7 tools on Linux)."
```

- [ ] **Step 2: Make it executable**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
chmod +x scripts/bootstrap.sh
```

- [ ] **Step 3: Lint with shellcheck (if available)**

```bash
command -v shellcheck && shellcheck scripts/bootstrap.sh || echo "shellcheck not installed; skipping"
```

If shellcheck flags real issues (not the SC1091 source warning which is suppressed), fix them. SC1091 is the standard "can't follow non-constant source" warning and is correctly suppressed inline.

- [ ] **Step 4: Quick local sanity check**

Run the script in dry-run-ish mode by checking it parses without errors:

```bash
bash -n scripts/bootstrap.sh && echo "syntax OK"
```

Expected: `syntax OK`. We don't actually run it on the Mac (it would clone to `~/arcadia/jkw_obs-mcp` which already exists at `~/arcadia/臥龍/obsidian/jkw_obs-mcp`); the real exercise is the Task 7 smoke test on scs.

- [ ] **Step 5: Commit**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git add scripts/bootstrap.sh
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: scripts/bootstrap.sh — single-command cluster setup"
```

- [ ] **Step 6: Push to origin**

The bootstrap URL embeds `main` branch — the script needs to be on origin/main BEFORE the smoke test, otherwise `curl https://raw.githubusercontent.com/jinchiwei/jkw_obs-mcp/main/scripts/bootstrap.sh` 404s.

```bash
git push origin main
```

---

## Task 7: Smoke test on scs + plan-8-complete tag

This task is non-TDD. Exercises the real bootstrap flow against actual scs hardware. The smoke test is the proof that the machinery works.

**Files:** None — captures findings as kb learnings.

- [ ] **Step 1: SSH into scs as a fresh user (no prior jkw_obs-mcp setup)**

```bash
ssh callosum
```

If you already set up jkw_obs-mcp on scs during Task 1 recon, blow it away first to test the full bootstrap path:

```bash
rm -rf ~/arcadia/jkw_obs-mcp ~/arcadia/jkw_obs-brain ~/.config/jkw-obs-mcp
```

(Comment if you'd rather test idempotency by re-running on top of the existing install. Both are valid smoke tests; clean install is more thorough.)

- [ ] **Step 2: Run bootstrap.sh**

```bash
curl -fsSL https://raw.githubusercontent.com/jinchiwei/jkw_obs-mcp/main/scripts/bootstrap.sh | bash
```

Expected timeline (no exact numbers — capture actual times as a learning):
- Step 1 (Python check): instant
- Step 2 (mkdir arcadia): instant
- Step 3 (git clone): ~5-10s
- Step 4 (venv create): instant if stdlib, ~1s if uv
- Step 5 (pip install -e .): 30-90s (downloads sqlite-vec, fastembed, mcp, anthropic — slow because of fastembed's ONNX)
- Step 6 (jkw-obs-mcp-setup): ~10-30s (git clone of brain repo, claude mcp add)

Total: ~1-3 minutes if everything is clean.

If anything fails: capture the exact error as a `constraints` or `postmortems` kb learning. Title example: `scs bootstrap: pip install fails behind FAC tunnel`.

- [ ] **Step 3: Verify on-disk state**

```bash
ls -la ~/arcadia/
ls -la ~/arcadia/jkw_obs-mcp/.venv/bin/ | head
ls -la ~/arcadia/jkw_obs-brain/kb/
cat ~/.config/jkw-obs-mcp/config.toml
```

Expected:
- `~/arcadia/` contains both `jkw_obs-mcp/` and `jkw_obs-brain/`
- `.venv/bin/` has `python3`, `pip`, `jkw-obs-mcp`, `jkw-obs-mcp-setup`
- `~/arcadia/jkw_obs-brain/kb/` has subdirs for `dreamingmachine`, etc. (mirrors the GitHub repo)
- `config.toml` has `vault_root = "/home/<user>/arcadia/jkw_obs-brain"` and `[machine] id = "scs"`

- [ ] **Step 4: Verify Claude Code sees the tool**

In a new SSH session (so PATH and shell state are fresh) on scs, with Claude Code installed:

```
$ claude
> List jkw-obs tools
```

Expected: 7 tools (`read_note`, `list_notes`, `write_kb_note`, `search_vault`, `find_similar`, `reindex`, `record_learning`). The 3 Mac-only tools (`compile_raw`, `compile_email`, `generate_daily_review`) must NOT appear.

If Claude Code wasn't installed yet on scs, the bootstrap printed the `claude mcp add jkw-obs --command jkw-obs-mcp` command. Install Claude Code (out of scope of this plan), run the printed command, then retry.

- [ ] **Step 5: Smoke test record_learning from scs**

```
> Use jkw-obs record_learning to write:
>   category: decisions
>   title: Plan 8 ships scs cluster rollout
>   content: First non-Mac cluster wired up. Machinery works: bootstrap.sh + Python installer + claude mcp add. Total bootstrap time was about <X> minutes from fresh SSH. Future clusters (Plans 9-12) follow this pattern. record_learning end-to-end works on Linux, embedder runs jina-zh via fastembed-onnx, push goes to jkw_obs-brain main.
>   tags: [jkw-obs-mcp, plan-8, scs, cluster-rollout]
>   applies_to: [jkw-obs-mcp]
```

Expected: `wrote /home/<user>/arcadia/jkw_obs-brain/kb/scs/learnings/decisions/2026-04-29-plan-8-ships-scs-cluster-rollout.md`

Verify the file exists at that path on scs. Verify it appears at https://github.com/jinchiwei/jkw_obs-brain/tree/main/kb/scs/learnings/decisions/ within seconds.

- [ ] **Step 6: Smoke test cross-machine read**

On dreamingmachine (back to your Mac), in a new Claude Code session:

```
> Use jkw-obs search_vault for: Plan 8 cluster rollout scs
```

Expected: top hit is the just-written note from scs. The brain repo pull (cached at 5 min from Plan 7) propagates the new commit. If the search misses, it's because the cache is stale — wait <5 min, then `reindex` and re-search.

- [ ] **Step 7: Smoke test idempotency**

Back on scs, run bootstrap.sh again:

```bash
curl -fsSL https://raw.githubusercontent.com/jinchiwei/jkw_obs-mcp/main/scripts/bootstrap.sh | bash
```

Expected: every step prints "already X; reusing" or its equivalent. No errors. No reinstalls. No double-registration. Claude Code's tool surface still shows 7 jkw-obs tools (not 14).

- [ ] **Step 8: Capture findings**

If anything in Steps 2-7 was surprising — bootstrap step took 10x expected, FAC blocked something, MCP registration needed a manual workaround, idempotency wasn't quite idempotent — write a kb `constraints` or `postmortems` learning from your Mac Claude session.

If everything was clean, write a single kb `decisions` learning summarizing the rollout (similar to Plan 7's smoke-test-result learning).

- [ ] **Step 9: Push and tag**

Back on the Mac, in `~/arcadia/臥龍/obsidian/jkw_obs-mcp`:

```bash
git push origin main
git tag plan-8-complete
git push origin --tags
```

---

## Self-Review Checklist

- [ ] All 7 tasks committed (Task 1 makes no commits; Tasks 2-6 each commit; Task 7 tags)
- [ ] `pytest -q` shows full suite green (~249 tests at end of Task 5)
- [ ] `bootstrap.sh` syntax-checks on Mac; exercised on scs in Task 7
- [ ] On scs: Claude Code shows 7 jkw-obs tools (not 10, not 6, not 0)
- [ ] On scs: `record_learning` writes to `kb/scs/learnings/...`, commits, pushes
- [ ] On Mac: `search_vault` finds the just-written scs note within 5 min
- [ ] Idempotency: re-running bootstrap.sh on scs is a no-op
- [ ] `git tag plan-8-complete` pushed

When all boxes ticked, Plan 8 done. Plans 9-12 (per-cluster rollouts to fac/cph/teal/cdx) follow with the same machinery; each gets ~3-5 tasks.

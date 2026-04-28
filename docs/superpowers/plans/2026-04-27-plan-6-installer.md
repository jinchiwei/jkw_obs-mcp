# Plan 6: Platform-Aware Installer + Boot Trigger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Ship `jkw-obs-mcp-setup` (platform-aware installer that works on Mac and Linux clusters) and `jkw-obs-mcp-daily-review` (the missing boot-trigger console-script Plan 4 referenced but never implemented). On Mac, daily review fires within 5 min of waking the laptop; on Linux clusters, the same setup command gets a working MCP without trying to register launchd.

**Architecture:** Two new console-scripts in `pyproject.toml`. `triggers/daily_review_runner.py` is a tiny script invoked by launchd every 5 min — reads `~/.config/jkw-obs-mcp/last-daily-review.json`, compares today's date to last_run_at's date, fires `generate_daily_review` if stale, no-ops otherwise (~10ms). `installer/` package has small focused modules per setup step (config_dir, machines_check, launchd, gmail_oauth) plus a `cli.py` orchestrator that detects platform via `platform.system()` and runs the appropriate steps. Mac-only steps (launchd, Gmail OAuth) skip cleanly on Linux. Plist template gets `StartInterval=300` (handles wake-from-sleep) plus `RunAtLoad=true` (belt-and-suspenders for restarts).

**Tech Stack:** stdlib only for installer (pathlib, platform, subprocess, socket, tomllib, plistlib). Reuses existing `GmailAdapter` (Plan 5) for OAuth bootstrap. Reuses existing `DailyReviewGenerator` (Plan 4) for the boot-trigger run path.

**Realistic effort: ~3-4 days** (9 tasks).

---

## File Structure

```
jkw_obs-mcp/
├── pyproject.toml                            Modify: add 2 console-script entries
├── src/jkw_obs_mcp/
│   ├── installer/
│   │   ├── __init__.py                       Empty
│   │   ├── cli.py                            jkw-obs-mcp-setup orchestrator
│   │   ├── config_dir.py                     create ~/.config/jkw-obs-mcp/, scaffold .env
│   │   ├── gmail_oauth.py                    Mac: walk through Google Cloud + bootstrap token
│   │   ├── launchd.py                        Mac: render plist + launchctl bootstrap
│   │   └── machines_check.py                 validate hostname against machines.toml
│   └── triggers/
│       ├── __init__.py                       Empty
│       └── daily_review_runner.py            jkw-obs-mcp-daily-review boot-trigger entry
├── services/launchd/
│   └── com.jinchiwei.jkw-obs-mcp.daily-review.plist   REPLACED: StartInterval=300, RunAtLoad=true
└── tests/
    ├── test_triggers_daily_review_runner.py  date-comparison + main() with stub runner
    ├── test_installer_plist_render.py        plist XML validity (plistlib)
    ├── test_installer_config_dir.py          dir creation, .env scaffolding, idempotency
    ├── test_installer_machines_check.py      hostname registry lookup
    ├── test_installer_launchd.py             plist rendering + mocked subprocess
    ├── test_installer_gmail_oauth.py         walkthrough text + mocked GmailAdapter
    └── test_installer_cli.py                 platform dispatch + status report
```

---

## Task 1: Console-script entries + module skeletons

**Files:** Modify `pyproject.toml`. Create `src/jkw_obs_mcp/installer/__init__.py`, `src/jkw_obs_mcp/installer/cli.py`, `src/jkw_obs_mcp/triggers/__init__.py`, `src/jkw_obs_mcp/triggers/daily_review_runner.py`.

This is pure infrastructure. Adds the console-script entries so subsequent tasks can run `which jkw-obs-mcp-setup` to verify wiring. Stubs out the modules so tests in Tasks 2-8 have something to import.

- [ ] **Step 1: Read current `pyproject.toml`** to confirm structure.

Run: `cat pyproject.toml`

The `[project.scripts]` section currently has only:
```toml
[project.scripts]
jkw-obs-mcp = "jkw_obs_mcp.mcp.server:main"
```

- [ ] **Step 2: Add the two new console-script entries**

Edit `pyproject.toml` to expand `[project.scripts]`:

```toml
[project.scripts]
jkw-obs-mcp = "jkw_obs_mcp.mcp.server:main"
jkw-obs-mcp-setup = "jkw_obs_mcp.installer.cli:main"
jkw-obs-mcp-daily-review = "jkw_obs_mcp.triggers.daily_review_runner:main"
```

- [ ] **Step 3: Create `src/jkw_obs_mcp/installer/__init__.py`**

```python
"""Platform-aware installer for jkw-obs-mcp.

`jkw-obs-mcp-setup` is the entry point. It runs shared setup steps unconditionally
and Mac-only steps (launchd, Gmail OAuth) only on Darwin.
"""
```

- [ ] **Step 4: Create `src/jkw_obs_mcp/installer/cli.py` with stub `main()`**

```python
"""jkw-obs-mcp-setup entry point — orchestrates platform-aware setup."""

from __future__ import annotations


def main() -> int:
    """Stub. Real implementation lands in Task 8."""
    print("jkw-obs-mcp-setup: not yet implemented (Plan 6 Task 8)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
```

- [ ] **Step 5: Create `src/jkw_obs_mcp/triggers/__init__.py`**

```python
"""launchd / cron entry points for time-based MCP-driven actions.

`daily_review_runner.main()` is invoked by the launchd LaunchAgent every
5 minutes (StartInterval=300). It exits 0 silently if today's daily review
already exists, fires generate_daily_review if not.
"""
```

- [ ] **Step 6: Create `src/jkw_obs_mcp/triggers/daily_review_runner.py` with stub `main()`**

```python
"""Stub. Real implementation lands in Task 2."""

from __future__ import annotations


def main() -> int:
    """Stub returning 0. Real logic in Task 2."""
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
```

- [ ] **Step 7: Reinstall the package so console-scripts get registered**

Run:
```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream
pip install -e ".[dev,mac,gmail]"
```

Expected: pip resolves quickly (already-installed deps), wheel rebuilds with the new entry points.

- [ ] **Step 8: Verify console-scripts are invokable**

Run:
```bash
which jkw-obs-mcp-setup
which jkw-obs-mcp-daily-review
jkw-obs-mcp-setup
jkw-obs-mcp-daily-review; echo "exit=$?"
```

Expected:
- Both `which` lines return paths under the deepdream env.
- `jkw-obs-mcp-setup` prints `jkw-obs-mcp-setup: not yet implemented (Plan 6 Task 8)` and exits 0.
- `jkw-obs-mcp-daily-review` produces no output and prints `exit=0`.

- [ ] **Step 9: Run full test suite to confirm no regressions**

Run: `pytest tests/ -q`
Expected: 139 passed (Plan 5's count).

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml src/jkw_obs_mcp/installer/__init__.py src/jkw_obs_mcp/installer/cli.py src/jkw_obs_mcp/triggers/__init__.py src/jkw_obs_mcp/triggers/daily_review_runner.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "chore: add jkw-obs-mcp-setup and jkw-obs-mcp-daily-review console-script stubs"
```

---

## Task 2: Boot-trigger module — date logic + main()

**Files:** Modify `src/jkw_obs_mcp/triggers/daily_review_runner.py`. Create `tests/test_triggers_daily_review_runner.py`.

The boot-trigger has two concerns: the pure date-comparison logic (`should_run_today`) and the actual run wiring (`_run_daily_review`). `main()` glues them together with an injectable runner so tests can swap in a stub.

- [ ] **Step 1: Failing tests at `tests/test_triggers_daily_review_runner.py`**

```python
"""Tests for the daily-review boot-trigger entry point."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

from jkw_obs_mcp.triggers.daily_review_runner import main, should_run_today


# ---- should_run_today ----


def test_should_run_when_state_file_missing(tmp_path):
    state = tmp_path / "missing.json"
    assert should_run_today(state) is True


def test_should_run_when_state_file_corrupt(tmp_path):
    state = tmp_path / "state.json"
    state.write_text("{not valid json")
    assert should_run_today(state) is True


def test_should_run_when_last_run_at_missing_in_json(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"foo": "bar"}))
    assert should_run_today(state) is True


def test_should_run_when_last_run_was_yesterday(tmp_path):
    state = tmp_path / "state.json"
    today = dt.date(2026, 4, 27)
    yesterday = dt.datetime(2026, 4, 26, 10, 0, 0, tzinfo=dt.UTC)
    state.write_text(json.dumps({"last_run_at": yesterday.isoformat()}))
    assert should_run_today(state, today=today) is True


def test_should_skip_when_last_run_was_today(tmp_path):
    state = tmp_path / "state.json"
    today = dt.date(2026, 4, 27)
    earlier_today = dt.datetime(2026, 4, 27, 1, 0, 0, tzinfo=dt.UTC)
    state.write_text(json.dumps({"last_run_at": earlier_today.isoformat()}))
    assert should_run_today(state, today=today) is False


def test_should_run_when_last_run_was_far_in_past(tmp_path):
    state = tmp_path / "state.json"
    today = dt.date(2026, 4, 27)
    last_year = dt.datetime(2025, 4, 27, 0, 0, 0, tzinfo=dt.UTC)
    state.write_text(json.dumps({"last_run_at": last_year.isoformat()}))
    assert should_run_today(state, today=today) is True


# ---- main() with injectable runner ----


def test_main_returns_0_when_today_already_ran(tmp_path):
    """If should_run_today is False, runner is never called, main returns 0."""
    state = tmp_path / "state.json"
    today = dt.date(2026, 4, 27)
    state.write_text(json.dumps({"last_run_at": dt.datetime(2026, 4, 27, 8, 0, tzinfo=dt.UTC).isoformat()}))

    called = []

    def fake_runner() -> int:
        called.append(True)
        return 0

    with patch("jkw_obs_mcp.triggers.daily_review_runner._state_path", return_value=state), \
         patch("jkw_obs_mcp.triggers.daily_review_runner._today", return_value=today):
        rc = main(_runner=fake_runner)

    assert rc == 0
    assert called == []  # runner was never invoked


def test_main_invokes_runner_when_stale(tmp_path):
    """If should_run_today is True, runner is invoked."""
    state = tmp_path / "missing.json"  # absent → should_run_today=True

    called = []

    def fake_runner() -> int:
        called.append(True)
        return 0

    with patch("jkw_obs_mcp.triggers.daily_review_runner._state_path", return_value=state):
        rc = main(_runner=fake_runner)

    assert rc == 0
    assert called == [True]


def test_main_returns_1_when_runner_raises(tmp_path):
    """Runner raising must not propagate — main catches, logs, returns 1."""
    state = tmp_path / "missing.json"

    def angry_runner() -> int:
        raise RuntimeError("simulated failure")

    with patch("jkw_obs_mcp.triggers.daily_review_runner._state_path", return_value=state):
        rc = main(_runner=angry_runner)

    assert rc == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_triggers_daily_review_runner.py -v`
Expected: ImportError on `should_run_today`, attribute errors on `_state_path` / `_today` (don't exist yet).

- [ ] **Step 3: Replace `src/jkw_obs_mcp/triggers/daily_review_runner.py` with the full implementation**

```python
"""Boot-trigger entry point for the daily review.

Invoked by launchd every 5 minutes (StartInterval=300) on macOS, and
optionally by cron / manual run on Linux. Reads the state file and only
fires `generate_daily_review` if today's date is later than last_run_at's
date. Otherwise exits 0 silently. Cost when no-op: ~10ms.

Errors during the actual run are logged to stderr (which launchd captures
to ~/Library/Logs/com.jinchiwei.jkw-obs-mcp.daily-review.err) but never
re-raised — a crash in the trigger should not crash the LaunchAgent.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Callable


def _state_path() -> Path:
    """Where the daily-review state file lives. Function so tests can monkey-patch."""
    return Path.home() / ".config" / "jkw-obs-mcp" / "last-daily-review.json"


def _today() -> dt.date:
    """Wrapper around dt.date.today() for test injection."""
    return dt.date.today()


def should_run_today(
    state_path: Path,
    *,
    today: dt.date | None = None,
) -> bool:
    """Return True if a daily review should run now.

    True when: state file missing, corrupt, missing the `last_run_at` key,
    or the persisted last_run_at is on a strictly earlier date than `today`.
    False only when state file exists, parses cleanly, and last_run_at's
    date matches today.
    """
    if today is None:
        today = _today()

    if not state_path.is_file():
        return True

    try:
        data = json.loads(state_path.read_text())
        ts = data.get("last_run_at")
        if not ts:
            return True
        last_run = dt.datetime.fromisoformat(ts)
        return last_run.date() < today
    except (json.JSONDecodeError, KeyError, ValueError):
        return True


def main(*, _runner: Callable[[], int] | None = None) -> int:
    """LaunchAgent entry point. Returns 0 on success or no-op, 1 on error.

    `_runner` is injectable for tests; production callers pass nothing and
    the real `_run_daily_review` is used.
    """
    state = _state_path()
    if not should_run_today(state):
        return 0

    runner = _runner if _runner is not None else _run_daily_review
    try:
        return runner()
    except Exception as exc:
        print(f"daily-review trigger failed: {exc}", file=sys.stderr)
        return 1


def _run_daily_review() -> int:
    """Build the adapter + generator from config and invoke generate().

    Mirrors the wiring in mcp/server.py:main() but synchronous and exits
    after one generate(). Loads ~/.config/jkw-obs-mcp/.env first (same
    secrets-loading pattern as the MCP server).
    """
    from dotenv import load_dotenv

    from jkw_obs_mcp.adapter.calendar import CalendarAdapter
    from jkw_obs_mcp.adapter.gmail import GmailAdapter
    from jkw_obs_mcp.adapter.vault import VaultAdapter
    from jkw_obs_mcp.compilers.email_compiler import EmailCompiler
    from jkw_obs_mcp.config import load_config
    from jkw_obs_mcp.generation.anthropic_client import AnthropicClient
    from jkw_obs_mcp.generators.daily_review import DailyReviewGenerator

    cfg_dir = Path.home() / ".config" / "jkw-obs-mcp"
    env_path = cfg_dir / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)

    cfg = load_config(cfg_dir / "config.toml")
    adapter = VaultAdapter(vault_root=cfg.vault_root, machine_id=cfg.machine_id)
    adapter.calendar = CalendarAdapter()
    adapter.daily_review_state_path = cfg_dir / "last-daily-review.json"
    adapter.anthropic_model = cfg.generation.model

    client = AnthropicClient(model=cfg.generation.model)
    adapter.email_compiler = EmailCompiler(
        gmail=GmailAdapter(
            client_secret_path=cfg_dir / "google-client-secret.json",
            token_path=cfg_dir / "gmail-token.json",
        ),
        client=client,
        vault_adapter=adapter,
    )

    gen = DailyReviewGenerator(adapter=adapter, client=client)
    out_path = gen.generate()
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_triggers_daily_review_runner.py -v`
Expected: 9 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 148 passed (139 + 9).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/triggers/daily_review_runner.py tests/test_triggers_daily_review_runner.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: jkw-obs-mcp-daily-review boot trigger with date-based skip logic"
```

---

## Task 3: Plist template + render function

**Files:** Modify `services/launchd/com.jinchiwei.jkw-obs-mcp.daily-review.plist`. Create `src/jkw_obs_mcp/installer/launchd.py` (render function only — install/uninstall in Task 6). Create `tests/test_installer_plist_render.py`.

The Plan 4 plist template is hardcoded with the wrong cadence (StartCalendarInterval=8am) and a fake conda path. We replace the static template with a Python function that renders a parametrizable plist using the running interpreter's actual `sys.executable`. Validate XML well-formedness via `plistlib`.

- [ ] **Step 1: Failing tests at `tests/test_installer_plist_render.py`**

```python
"""Plist render output validity tests."""

from __future__ import annotations

import plistlib
import sys

from jkw_obs_mcp.installer.launchd import LABEL, render_plist


def test_render_plist_returns_well_formed_xml():
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["Label"] == LABEL


def test_render_plist_uses_sys_executable_by_default():
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["ProgramArguments"][0] == sys.executable


def test_render_plist_accepts_custom_python_path():
    xml = render_plist(python_path="/opt/homebrew/bin/python3.12")
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["ProgramArguments"][0] == "/opt/homebrew/bin/python3.12"


def test_render_plist_invokes_module_form():
    """ProgramArguments invokes the trigger via `python -m`, not by absolute script path."""
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["ProgramArguments"][1] == "-m"
    assert parsed["ProgramArguments"][2] == "jkw_obs_mcp.triggers.daily_review_runner"


def test_render_plist_sets_start_interval_300():
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["StartInterval"] == 300


def test_render_plist_sets_run_at_load_true():
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert parsed["RunAtLoad"] is True


def test_render_plist_does_not_set_start_calendar_interval():
    """Plan 4's StartCalendarInterval=8am is gone — wake-from-sleep doesn't catch it."""
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert "StartCalendarInterval" not in parsed


def test_render_plist_log_paths_under_library_logs():
    xml = render_plist()
    parsed = plistlib.loads(xml.encode("utf-8"))
    assert "/Library/Logs/" in parsed["StandardOutPath"]
    assert "/Library/Logs/" in parsed["StandardErrorPath"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_installer_plist_render.py -v`
Expected: ImportError (`jkw_obs_mcp.installer.launchd` doesn't define `render_plist` or `LABEL` yet).

- [ ] **Step 3: Create `src/jkw_obs_mcp/installer/launchd.py` with render function only**

```python
"""launchd LaunchAgent management for the daily-review boot trigger.

This file defines the plist template renderer (works on any platform) and
the install/uninstall functions (Mac-only — Task 6 adds those). On Linux,
the install function is a no-op.
"""

from __future__ import annotations

import sys
from pathlib import Path


LABEL = "com.jinchiwei.jkw-obs-mcp.daily-review"


_PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>jkw_obs_mcp.triggers.daily_review_runner</string>
    </array>

    <!-- Fires every 5 min while awake. Paused during sleep; resumes on wake.
         RunAtLoad=true also fires once at session login (covers full restarts). -->
    <key>StartInterval</key>
    <integer>300</integer>

    <key>RunAtLoad</key>
    <true/>

    <!-- Don't start a second instance if a previous run is still going. -->
    <key>AbandonProcessGroup</key>
    <false/>

    <key>StandardOutPath</key>
    <string>{log_out}</string>
    <key>StandardErrorPath</key>
    <string>{log_err}</string>
</dict>
</plist>
"""


def render_plist(*, python_path: str | None = None, label: str = LABEL) -> str:
    """Return the plist XML with the given Python path embedded.

    `python_path` defaults to the current `sys.executable` so the LaunchAgent
    points at the interpreter the user installed jkw-obs-mcp into. If they
    later move the conda env, re-run jkw-obs-mcp-setup to re-render.
    """
    if python_path is None:
        python_path = sys.executable
    home = Path.home()
    return _PLIST_TEMPLATE.format(
        label=label,
        python_path=python_path,
        log_out=str(home / "Library" / "Logs" / f"{label}.log"),
        log_err=str(home / "Library" / "Logs" / f"{label}.err"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_installer_plist_render.py -v`
Expected: 8 passed.

- [ ] **Step 5: Replace the legacy plist file with output of `render_plist()`**

The old plist at `services/launchd/com.jinchiwei.jkw-obs-mcp.daily-review.plist` references a hardcoded `/Users/jinchiwei/miniconda3/envs/deepdream/bin/jkw-obs-mcp-daily-review` path and `StartCalendarInterval=8am`. Replace it with a generic version that the installer will overwrite with real `sys.executable` at install time. The committed file is illustrative — the source of truth is the renderer.

Run:
```bash
python -c "from jkw_obs_mcp.installer.launchd import render_plist; print(render_plist(python_path='/path/to/python'))" > services/launchd/com.jinchiwei.jkw-obs-mcp.daily-review.plist
```

- [ ] **Step 6: Run full suite**

Run: `pytest tests/ -q`
Expected: 156 passed (148 + 8).

- [ ] **Step 7: Commit**

```bash
git add src/jkw_obs_mcp/installer/launchd.py tests/test_installer_plist_render.py services/launchd/com.jinchiwei.jkw-obs-mcp.daily-review.plist
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: render_plist() with StartInterval=300 + RunAtLoad=true (replaces 8am cron)"
```

---

## Task 4: Installer — `config_dir` step

**Files:** Create `src/jkw_obs_mcp/installer/config_dir.py`, `tests/test_installer_config_dir.py`.

Pure-function step that creates `~/.config/jkw-obs-mcp/` if missing and scaffolds `.env` from the repo's `.env.example` if a `.env` doesn't already exist. Idempotent: re-running on a configured machine returns a status dict reflecting "already exists" rather than overwriting.

- [ ] **Step 1: Failing tests at `tests/test_installer_config_dir.py`**

```python
"""Tests for installer.config_dir step."""

from __future__ import annotations

from pathlib import Path

from jkw_obs_mcp.installer.config_dir import create_config_dir


def test_creates_config_dir_when_missing(tmp_path):
    cfg = tmp_path / "cfg"
    env_example = tmp_path / "env_example"
    env_example.write_text("ANTHROPIC_API_KEY=...\n")

    status = create_config_dir(config_dir=cfg, env_example=env_example)

    assert cfg.is_dir()
    assert (cfg / ".env").is_file()
    assert status["env_scaffolded"] is True
    assert status["env_already_existed"] is False


def test_chmod_600_on_scaffolded_env(tmp_path):
    cfg = tmp_path / "cfg"
    env_example = tmp_path / "env_example"
    env_example.write_text("KEY=val\n")

    create_config_dir(config_dir=cfg, env_example=env_example)

    mode = (cfg / ".env").stat().st_mode & 0o777
    assert mode == 0o600


def test_idempotent_when_dir_already_exists(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / ".env").write_text("EXISTING=true\n")
    env_example = tmp_path / "env_example"
    env_example.write_text("DIFFERENT=value\n")

    status = create_config_dir(config_dir=cfg, env_example=env_example)

    # .env was preserved, NOT overwritten
    assert (cfg / ".env").read_text() == "EXISTING=true\n"
    assert status["env_scaffolded"] is False
    assert status["env_already_existed"] is True


def test_handles_missing_env_example_gracefully(tmp_path):
    """If .env.example is absent (e.g., running from a non-repo install),
    create the dir but skip env scaffolding rather than crashing."""
    cfg = tmp_path / "cfg"
    env_example = tmp_path / "does-not-exist"

    status = create_config_dir(config_dir=cfg, env_example=env_example)

    assert cfg.is_dir()
    assert not (cfg / ".env").exists()
    assert status["env_scaffolded"] is False
    assert status["env_already_existed"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_installer_config_dir.py -v`
Expected: ImportError on `create_config_dir`.

- [ ] **Step 3: Write `src/jkw_obs_mcp/installer/config_dir.py`**

```python
"""Step: create ~/.config/jkw-obs-mcp/ and scaffold .env if missing."""

from __future__ import annotations

import os
from pathlib import Path


def create_config_dir(
    *,
    config_dir: Path | None = None,
    env_example: Path | None = None,
) -> dict[str, bool]:
    """Create config dir if missing; scaffold .env from env_example if missing.

    Idempotent. Returns a status dict for the installer's final report:
      {
        "env_scaffolded": True if we wrote a new .env this run,
        "env_already_existed": True if a .env was already there,
      }
    """
    if config_dir is None:
        config_dir = Path.home() / ".config" / "jkw-obs-mcp"
    if env_example is None:
        # Resolve relative to repo root: src/jkw_obs_mcp/installer/config_dir.py
        # → up 4 → repo root.
        env_example = Path(__file__).resolve().parents[3] / ".env.example"

    config_dir.mkdir(parents=True, exist_ok=True)

    env_path = config_dir / ".env"
    if env_path.is_file():
        return {"env_scaffolded": False, "env_already_existed": True}

    if not env_example.is_file():
        return {"env_scaffolded": False, "env_already_existed": False}

    env_path.write_text(env_example.read_text())
    os.chmod(env_path, 0o600)
    return {"env_scaffolded": True, "env_already_existed": False}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_installer_config_dir.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 160 passed (156 + 4).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/installer/config_dir.py tests/test_installer_config_dir.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: installer.config_dir — create ~/.config/jkw-obs-mcp + scaffold .env"
```

---

## Task 5: Installer — `machines_check` step

**Files:** Create `src/jkw_obs_mcp/installer/machines_check.py`, `tests/test_installer_machines_check.py`.

Reads the running machine's hostname, parses `machines.toml`, and reports whether the hostname is registered (either as a machine ID directly or in any entry's `hostname_aliases` list). Provides `append_hostname` for the user to opt into auto-registration.

- [ ] **Step 1: Failing tests at `tests/test_installer_machines_check.py`**

```python
"""Tests for installer.machines_check step."""

from __future__ import annotations

import tomllib
from pathlib import Path

from jkw_obs_mcp.installer.machines_check import (
    append_hostname,
    is_hostname_registered,
)


def _write_machines_toml(path: Path, content: str) -> None:
    path.write_text(content)


def test_returns_true_when_hostname_is_a_machine_id(tmp_path):
    machines = tmp_path / "machines.toml"
    _write_machines_toml(machines, """
[dreamingmachine]
hostname_aliases = []
os = "darwin"
""")
    assert is_hostname_registered(machines, hostname="dreamingmachine") is True


def test_returns_true_when_hostname_in_aliases(tmp_path):
    machines = tmp_path / "machines.toml"
    _write_machines_toml(machines, """
[scs]
hostname_aliases = ["callosum"]
os = "linux"
""")
    assert is_hostname_registered(machines, hostname="callosum") is True


def test_returns_false_when_hostname_not_present(tmp_path):
    machines = tmp_path / "machines.toml"
    _write_machines_toml(machines, """
[dreamingmachine]
hostname_aliases = []
os = "darwin"
""")
    assert is_hostname_registered(machines, hostname="randomhost") is False


def test_returns_false_when_machines_toml_missing(tmp_path):
    machines = tmp_path / "missing.toml"
    assert is_hostname_registered(machines, hostname="anything") is False


def test_append_hostname_writes_correct_block(tmp_path):
    machines = tmp_path / "machines.toml"
    _write_machines_toml(machines, """
[dreamingmachine]
hostname_aliases = []
os = "darwin"
""")
    append_hostname(
        machines,
        machine_id="newcluster",
        os_type="linux",
        hostname="newcluster.example.edu",
    )

    parsed = tomllib.loads(machines.read_text())
    assert "newcluster" in parsed
    assert parsed["newcluster"]["os"] == "linux"
    assert "newcluster.example.edu" in parsed["newcluster"]["hostname_aliases"]


def test_append_hostname_then_is_registered(tmp_path):
    machines = tmp_path / "machines.toml"
    _write_machines_toml(machines, """
[dreamingmachine]
hostname_aliases = []
os = "darwin"
""")
    append_hostname(
        machines,
        machine_id="newcluster",
        os_type="linux",
        hostname="newcluster.example.edu",
    )

    assert is_hostname_registered(machines, hostname="newcluster.example.edu") is True
    assert is_hostname_registered(machines, hostname="newcluster") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_installer_machines_check.py -v`
Expected: ImportError on the helpers.

- [ ] **Step 3: Write `src/jkw_obs_mcp/installer/machines_check.py`**

```python
"""Step: validate that the running hostname is registered in machines.toml.

If absent, the installer prompts the user for a machine_id + os_type and
calls `append_hostname` to add a new block. We intentionally don't auto-
guess the machine_id — it's a deliberate human choice (e.g., 'fac' vs.
'fac-login01').
"""

from __future__ import annotations

import socket
import tomllib
from pathlib import Path


def current_hostname() -> str:
    """Return the short hostname (no FQDN suffix)."""
    return socket.gethostname().split(".")[0]


def is_hostname_registered(machines_toml: Path, *, hostname: str | None = None) -> bool:
    """True if `hostname` matches a machine_id or any hostname_aliases entry.

    Returns False (rather than raising) for missing or unparseable machines.toml.
    """
    if hostname is None:
        hostname = current_hostname()
    if not machines_toml.is_file():
        return False
    try:
        data = tomllib.loads(machines_toml.read_text())
    except tomllib.TOMLDecodeError:
        return False

    for machine_id, info in data.items():
        if machine_id == hostname:
            return True
        aliases = info.get("hostname_aliases", []) if isinstance(info, dict) else []
        if hostname in aliases:
            return True
    return False


def append_hostname(
    machines_toml: Path,
    *,
    machine_id: str,
    os_type: str,
    hostname: str | None = None,
) -> None:
    """Append a new `[machine_id]` block to machines.toml.

    Caller's responsibility to check `is_hostname_registered` first to avoid
    duplicate entries (TOML allows duplicate keys but most parsers reject).
    """
    if hostname is None:
        hostname = current_hostname()

    block = (
        f"\n[{machine_id}]\n"
        f'hostname_aliases = ["{hostname}"]\n'
        f'os = "{os_type}"\n'
    )
    with machines_toml.open("a") as f:
        f.write(block)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_installer_machines_check.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 166 passed (160 + 6).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/installer/machines_check.py tests/test_installer_machines_check.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: installer.machines_check — hostname registry validation + append"
```

---

## Task 6: Installer — `launchd` install/uninstall (Mac-only)

**Files:** Modify `src/jkw_obs_mcp/installer/launchd.py` (add install/uninstall functions). Create `tests/test_installer_launchd.py`.

The `render_plist` function from Task 3 stays. We add `install_launchd_agent()` (writes the rendered plist to `~/Library/LaunchAgents/` and runs `launchctl bootstrap`) and `uninstall_launchd_agent()` (runs `launchctl bootout` and removes the file). Both no-op on Linux. Idempotent: re-running install bootouts the existing instance first, then bootstraps fresh.

- [ ] **Step 1: Failing tests at `tests/test_installer_launchd.py`**

```python
"""Tests for installer.launchd install/uninstall."""

from __future__ import annotations

import platform
from pathlib import Path
from unittest.mock import patch

from jkw_obs_mcp.installer.launchd import (
    LABEL,
    install_launchd_agent,
    uninstall_launchd_agent,
)


def test_install_skips_on_linux(tmp_path):
    plist_path = tmp_path / "fake.plist"
    with patch("jkw_obs_mcp.installer.launchd.platform.system", return_value="Linux"):
        status = install_launchd_agent(plist_path=plist_path)
    assert status["skipped"] is True
    assert "non-darwin" in status["reason"].lower() or "linux" in status["reason"].lower()
    assert not plist_path.exists()  # nothing written


def test_install_writes_plist_and_calls_launchctl_on_darwin(tmp_path):
    plist_path = tmp_path / "agent.plist"
    fake_runs = []

    def fake_run(args, **kwargs):
        fake_runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.launchd.platform.system", return_value="Darwin"), \
         patch("jkw_obs_mcp.installer.launchd.subprocess.run", side_effect=fake_run):
        status = install_launchd_agent(plist_path=plist_path)

    # Plist was written
    assert plist_path.is_file()
    content = plist_path.read_text()
    assert LABEL in content
    assert "<integer>300</integer>" in content

    # launchctl bootout (idempotent cleanup) called first, then bootstrap
    assert any("bootout" in " ".join(args) for args in fake_runs)
    assert any("bootstrap" in " ".join(args) for args in fake_runs)
    assert status["skipped"] is False


def test_install_is_idempotent(tmp_path):
    """Re-running install on an already-installed system bootouts existing first."""
    plist_path = tmp_path / "agent.plist"
    fake_runs = []

    def fake_run(args, **kwargs):
        fake_runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.launchd.platform.system", return_value="Darwin"), \
         patch("jkw_obs_mcp.installer.launchd.subprocess.run", side_effect=fake_run):
        install_launchd_agent(plist_path=plist_path)
        install_launchd_agent(plist_path=plist_path)

    # Each install does bootout-then-bootstrap, so we should see 2 of each
    bootouts = sum(1 for a in fake_runs if "bootout" in " ".join(a))
    bootstraps = sum(1 for a in fake_runs if "bootstrap" in " ".join(a))
    assert bootouts == 2
    assert bootstraps == 2


def test_uninstall_skips_on_linux(tmp_path):
    plist_path = tmp_path / "agent.plist"
    plist_path.write_text("not used")
    with patch("jkw_obs_mcp.installer.launchd.platform.system", return_value="Linux"):
        status = uninstall_launchd_agent(plist_path=plist_path)
    assert status["skipped"] is True
    assert plist_path.is_file()  # not removed on Linux


def test_uninstall_bootouts_and_removes_plist_on_darwin(tmp_path):
    plist_path = tmp_path / "agent.plist"
    plist_path.write_text("placeholder plist contents")
    fake_runs = []

    def fake_run(args, **kwargs):
        fake_runs.append(args)
        class R: returncode = 0; stderr = ""; stdout = ""
        return R()

    with patch("jkw_obs_mcp.installer.launchd.platform.system", return_value="Darwin"), \
         patch("jkw_obs_mcp.installer.launchd.subprocess.run", side_effect=fake_run):
        status = uninstall_launchd_agent(plist_path=plist_path)

    assert any("bootout" in " ".join(args) for args in fake_runs)
    assert not plist_path.exists()
    assert status["skipped"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_installer_launchd.py -v`
Expected: ImportError on `install_launchd_agent` / `uninstall_launchd_agent`.

- [ ] **Step 3: Extend `src/jkw_obs_mcp/installer/launchd.py`**

Append to the existing file (after `render_plist`):

```python
import os
import platform
import subprocess


def _default_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def install_launchd_agent(*, plist_path: Path | None = None) -> dict[str, object]:
    """Render the plist, write it to LaunchAgents, and `launchctl bootstrap`.

    Idempotent: bootouts any existing instance first (ignoring failures, since
    'no such service' is fine on first install).

    No-op on non-Darwin platforms.
    """
    if platform.system() != "Darwin":
        return {"skipped": True, "reason": "non-darwin platform"}

    if plist_path is None:
        plist_path = _default_plist_path()

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(render_plist())

    target = f"gui/{os.getuid()}/{LABEL}"
    domain = f"gui/{os.getuid()}"

    # Idempotent cleanup of any prior instance. Failures here are expected
    # on first install (service not registered yet), so we ignore returncode.
    subprocess.run(
        ["launchctl", "bootout", target],
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        ["launchctl", "bootstrap", domain, str(plist_path)],
        capture_output=True,
        text=True,
    )
    return {
        "skipped": False,
        "plist_path": str(plist_path),
        "bootstrap_returncode": result.returncode,
        "stderr": result.stderr,
    }


def uninstall_launchd_agent(*, plist_path: Path | None = None) -> dict[str, object]:
    """`launchctl bootout` and remove the plist file. No-op on Linux."""
    if platform.system() != "Darwin":
        return {"skipped": True, "reason": "non-darwin platform"}

    if plist_path is None:
        plist_path = _default_plist_path()

    target = f"gui/{os.getuid()}/{LABEL}"
    result = subprocess.run(
        ["launchctl", "bootout", target],
        capture_output=True,
        text=True,
    )
    if plist_path.is_file():
        plist_path.unlink()
    return {
        "skipped": False,
        "bootout_returncode": result.returncode,
        "stderr": result.stderr,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_installer_launchd.py -v`
Expected: 5 passed.

- [ ] **Step 5: Re-run plist-render tests to confirm Task 3 still passes**

Run: `pytest tests/test_installer_plist_render.py -v`
Expected: 8 passed.

- [ ] **Step 6: Run full suite**

Run: `pytest tests/ -q`
Expected: 171 passed (166 + 5).

- [ ] **Step 7: Commit**

```bash
git add src/jkw_obs_mcp/installer/launchd.py tests/test_installer_launchd.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: installer.launchd — idempotent install/uninstall with launchctl bootstrap"
```

---

## Task 7: Installer — `gmail_oauth` step (Mac-only)

**Files:** Create `src/jkw_obs_mcp/installer/gmail_oauth.py`, `tests/test_installer_gmail_oauth.py`.

Walks the user through Google Cloud OAuth setup with copy-pasteable instructions, validates that `client_secret.json` is at the right path, then triggers the first OAuth flow via `GmailAdapter._ensure_credentials()` (Plan 5 already implements the actual interactive flow). Three skip cases are handled cleanly: token already cached → skip; client_secret missing → return walkthrough text; OAuth flow fails → record reason.

- [ ] **Step 1: Failing tests at `tests/test_installer_gmail_oauth.py`**

```python
"""Tests for installer.gmail_oauth step."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from jkw_obs_mcp.installer.gmail_oauth import gmail_oauth_setup


def test_skips_when_token_already_cached(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "gmail-token.json").write_text('{"token": "x"}')

    status = gmail_oauth_setup(config_dir=cfg)

    assert status["skipped"] is True
    assert "token" in status["reason"].lower()


def test_returns_walkthrough_when_client_secret_missing(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    # No client_secret.json, no gmail-token.json

    status = gmail_oauth_setup(config_dir=cfg)

    assert status["skipped"] is True
    assert "client_secret" in status["reason"].lower()
    assert "google" in status["walkthrough"].lower()
    assert "console.cloud.google.com" in status["walkthrough"]


def test_triggers_oauth_when_client_secret_present_and_no_token(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "google-client-secret.json").write_text('{"installed": {"client_id": "x"}}')

    fake_creds = MagicMock()
    fake_adapter = MagicMock()
    fake_adapter._ensure_credentials.return_value = fake_creds

    with patch(
        "jkw_obs_mcp.installer.gmail_oauth.GmailAdapter",
        return_value=fake_adapter,
    ):
        status = gmail_oauth_setup(config_dir=cfg)

    assert status["skipped"] is False
    fake_adapter._ensure_credentials.assert_called_once()


def test_returns_failure_when_oauth_flow_returns_none(tmp_path):
    """If GmailAdapter._ensure_credentials returns None (user cancelled, etc.),
    the installer records the failure but doesn't crash."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "google-client-secret.json").write_text('{"installed": {"client_id": "x"}}')

    fake_adapter = MagicMock()
    fake_adapter._ensure_credentials.return_value = None

    with patch(
        "jkw_obs_mcp.installer.gmail_oauth.GmailAdapter",
        return_value=fake_adapter,
    ):
        status = gmail_oauth_setup(config_dir=cfg)

    assert status["skipped"] is True
    assert "fail" in status["reason"].lower() or "oauth" in status["reason"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_installer_gmail_oauth.py -v`
Expected: ImportError on `gmail_oauth_setup`.

- [ ] **Step 3: Write `src/jkw_obs_mcp/installer/gmail_oauth.py`**

```python
"""Step: walk user through Google Cloud OAuth + bootstrap the gmail.readonly token.

Three branches:
  1. token already cached → skip ("already configured")
  2. client_secret.json missing → print walkthrough, skip
  3. client_secret.json present, no token → trigger interactive OAuth flow

The actual OAuth interaction (browser pop, scope grant, token cache) lives
in GmailAdapter._ensure_credentials (Plan 5 Task 2). This installer step
just orchestrates the call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


_WALKTHROUGH = """\
Google Cloud OAuth setup (one-time, ~5 min):

  1. Go to https://console.cloud.google.com
  2. Select or create a project (e.g., 'jkw-obs-mcp-personal')
  3. APIs & Services → Library → Gmail API → Enable
  4. APIs & Services → OAuth consent screen → External (or Audience → External
     in newer console UI). Fill in app name and your email. Submit.
  5. APIs & Services → Credentials → Create credentials → OAuth client ID
     → Application type: Desktop app → Create
  6. Download the JSON
  7. Save it to ~/.config/jkw-obs-mcp/google-client-secret.json
     (mkdir the directory first if needed)
  8. chmod 600 ~/.config/jkw-obs-mcp/google-client-secret.json

Then re-run jkw-obs-mcp-setup. The script will detect the file and trigger
the first OAuth flow (browser will open, accept gmail.readonly scope).
"""


def gmail_oauth_setup(*, config_dir: Path | None = None) -> dict[str, Any]:
    """Bootstrap Gmail OAuth credentials. Returns a status dict.

    Skip semantics:
      - "token already cached" → already done, no work needed
      - "client_secret.json missing" → user hasn't done Google Cloud setup yet,
        we return the walkthrough text so the installer can print it
      - "OAuth flow failed" → user cancelled or other failure during the
        interactive flow; not fatal
    """
    if config_dir is None:
        config_dir = Path.home() / ".config" / "jkw-obs-mcp"

    client_secret = config_dir / "google-client-secret.json"
    token = config_dir / "gmail-token.json"

    if token.is_file():
        return {"skipped": True, "reason": "token already cached"}

    if not client_secret.is_file():
        return {
            "skipped": True,
            "reason": "client_secret.json missing",
            "walkthrough": _WALKTHROUGH,
        }

    # Trigger first OAuth flow via the real adapter from Plan 5.
    from jkw_obs_mcp.adapter.gmail import GmailAdapter
    adapter = GmailAdapter(
        client_secret_path=client_secret,
        token_path=token,
    )
    creds = adapter._ensure_credentials()
    if creds is None:
        return {"skipped": True, "reason": "OAuth flow failed (user cancelled?)"}
    return {"skipped": False, "token_path": str(token)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_installer_gmail_oauth.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 175 passed (171 + 4).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/installer/gmail_oauth.py tests/test_installer_gmail_oauth.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: installer.gmail_oauth — walk user through Google Cloud + bootstrap token"
```

---

## Task 8: Installer — `cli.py` orchestrator + platform dispatch

**Files:** Modify `src/jkw_obs_mcp/installer/cli.py` (replace the Task 1 stub with the real orchestrator). Create `tests/test_installer_cli.py`.

Wires the four step modules together. Detects platform via `platform.system()`. Runs the shared steps (config_dir, machines_check) on every platform; runs the Mac-only steps (gmail_oauth, launchd) only on Darwin. Prints a final status summary.

- [ ] **Step 1: Failing tests at `tests/test_installer_cli.py`**

```python
"""Tests for installer.cli orchestrator."""

from __future__ import annotations

from unittest.mock import patch

from jkw_obs_mcp.installer.cli import main


def test_main_returns_0_on_darwin(capsys):
    """All four steps run on Darwin. Mocks all of them."""
    with patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Darwin"), \
         patch(
             "jkw_obs_mcp.installer.cli.create_config_dir",
             return_value={"env_scaffolded": True, "env_already_existed": False},
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.is_hostname_registered",
             return_value=True,
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.gmail_oauth_setup",
             return_value={"skipped": True, "reason": "token already cached"},
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.install_launchd_agent",
             return_value={"skipped": False, "plist_path": "/fake"},
         ):
        rc = main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "Darwin" in out
    assert "config dir" in out.lower()
    assert "machines.toml" in out.lower()
    assert "gmail" in out.lower()
    assert "launchd" in out.lower()


def test_main_skips_mac_only_steps_on_linux(capsys):
    """Linux runs config_dir + machines_check, but skips Gmail and launchd."""
    gmail_called = []
    launchd_called = []

    def fake_gmail(**_kwargs):
        gmail_called.append(True)
        return {"skipped": True}

    def fake_launchd(**_kwargs):
        launchd_called.append(True)
        return {"skipped": True}

    with patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Linux"), \
         patch(
             "jkw_obs_mcp.installer.cli.create_config_dir",
             return_value={"env_scaffolded": True, "env_already_existed": False},
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.is_hostname_registered",
             return_value=True,
         ), \
         patch("jkw_obs_mcp.installer.cli.gmail_oauth_setup", side_effect=fake_gmail), \
         patch("jkw_obs_mcp.installer.cli.install_launchd_agent", side_effect=fake_launchd):
        rc = main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "Linux" in out
    # Gmail and launchd functions were NOT called on Linux
    assert gmail_called == []
    assert launchd_called == []
    # The orchestrator printed that they were skipped
    assert "skipped" in out.lower()


def test_main_warns_when_hostname_not_registered(capsys):
    """If hostname isn't in machines.toml, print the instruction and don't fail.

    The orchestrator can't safely auto-append (which machine_id?), so it
    surfaces the missing entry to the user and continues with other steps.
    """
    with patch("jkw_obs_mcp.installer.cli.platform.system", return_value="Linux"), \
         patch(
             "jkw_obs_mcp.installer.cli.create_config_dir",
             return_value={"env_scaffolded": True, "env_already_existed": False},
         ), \
         patch(
             "jkw_obs_mcp.installer.cli.is_hostname_registered",
             return_value=False,
         ):
        rc = main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "machines.toml" in out.lower()
    assert "register" in out.lower() or "not registered" in out.lower() or "add" in out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_installer_cli.py -v`
Expected: 3 failures (current `main` is the Task 1 stub that just prints a placeholder).

- [ ] **Step 3: Replace `src/jkw_obs_mcp/installer/cli.py` with the orchestrator**

```python
"""jkw-obs-mcp-setup — platform-aware installer orchestrator.

Runs the shared setup steps unconditionally and Mac-only steps (Gmail OAuth,
launchd) only on Darwin. Idempotent: re-running on a configured machine
prints a clean status summary without overwriting anything.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from jkw_obs_mcp.installer.config_dir import create_config_dir
from jkw_obs_mcp.installer.gmail_oauth import gmail_oauth_setup
from jkw_obs_mcp.installer.launchd import install_launchd_agent
from jkw_obs_mcp.installer.machines_check import (
    current_hostname,
    is_hostname_registered,
)


def main() -> int:
    """Entry point for `jkw-obs-mcp-setup`."""
    plat = platform.system()
    print(f"Detected platform: {plat}")
    print(f"Python: {sys.executable}")
    print(f"Hostname: {current_hostname()}")
    print()

    status: dict[str, object] = {}

    print("Step 1: config dir")
    status["config_dir"] = create_config_dir()
    print(f"  → {status['config_dir']}")
    print()

    print("Step 2: machines.toml hostname")
    machines_toml = _find_machines_toml()
    hostname = current_hostname()
    if is_hostname_registered(machines_toml):
        status["machines"] = {"already_registered": True, "hostname": hostname}
        print(f"  → already registered: {hostname}")
    else:
        status["machines"] = {
            "already_registered": False,
            "hostname": hostname,
            "instruction": (
                f"Hostname {hostname!r} is not registered in {machines_toml}. "
                f"Add a [machine_id] block and re-run jkw-obs-mcp-setup."
            ),
        }
        print(f"  → not registered: {hostname}")
        print(f"    Add an entry to {machines_toml} and re-run setup.")
    print()

    if plat == "Darwin":
        print("Step 3: Gmail OAuth (Mac only)")
        status["gmail"] = gmail_oauth_setup()
        print(f"  → {status['gmail']}")
        if isinstance(status["gmail"], dict) and "walkthrough" in status["gmail"]:
            print()
            print(status["gmail"]["walkthrough"])
        print()

        print("Step 4: launchd boot trigger (Mac only)")
        status["launchd"] = install_launchd_agent()
        print(f"  → {status['launchd']}")
    else:
        print("Step 3: Gmail OAuth — skipped (Mac-only feature)")
        print("Step 4: launchd boot trigger — skipped (Mac-only feature)")
        status["gmail"] = {"skipped": True, "reason": f"non-darwin ({plat})"}
        status["launchd"] = {"skipped": True, "reason": f"non-darwin ({plat})"}

    print()
    print("Setup complete.")
    return 0


def _find_machines_toml() -> Path:
    """Walk up from this file to find the repo root, then return machines.toml.

    Falls back to ./machines.toml if no pyproject.toml ancestor is found
    (e.g., the package is installed but not from a source checkout).
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent / "machines.toml"
    return Path.cwd() / "machines.toml"


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_installer_cli.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 178 passed (175 + 3).

- [ ] **Step 6: Manual sanity check on dreamingmachine**

Run:
```bash
jkw-obs-mcp-setup
```

Expected output (something like):
```
Detected platform: Darwin
Python: /Users/jinchiwei/miniconda3/envs/deepdream/bin/python3.12
Hostname: dreamingmachine

Step 1: config dir
  → {'env_scaffolded': False, 'env_already_existed': True}

Step 2: machines.toml hostname
  → already registered: dreamingmachine

Step 3: Gmail OAuth (Mac only)
  → {'skipped': True, 'reason': 'token already cached'}

Step 4: launchd boot trigger (Mac only)
  → {'skipped': False, 'plist_path': '/Users/jinchiwei/Library/LaunchAgents/com.jinchiwei.jkw-obs-mcp.daily-review.plist', 'bootstrap_returncode': 0, 'stderr': ''}

Setup complete.
```

If `bootstrap_returncode` is non-zero, check `stderr` — `launchctl bootstrap` may fail if the agent is already loaded under a different domain. Re-run `jkw-obs-mcp-setup` once; the bootout-then-bootstrap pattern should resolve it.

- [ ] **Step 7: Commit**

```bash
git add src/jkw_obs_mcp/installer/cli.py tests/test_installer_cli.py
git -c user.email="mrjinch@gmail.com" -c user.name="jinchiwei" commit -m "feat: jkw-obs-mcp-setup orchestrator with platform-aware step dispatch"
```

---

## Task 9: Manual end-to-end smoke test + plan-6-complete tag

This task is non-TDD — it exercises the real LaunchAgent on dreamingmachine and verifies the boot trigger fires correctly.

- [ ] **Step 1: Verify the LaunchAgent is loaded**

Run:
```bash
launchctl print "gui/$(id -u)/com.jinchiwei.jkw-obs-mcp.daily-review" | head -40
```

Expected:
- `state = running` or `state = waiting` (StartInterval-driven services oscillate between these states)
- `program = /Users/jinchiwei/miniconda3/envs/deepdream/bin/python3.12` (or whichever interpreter you're in)
- `arguments = python -m jkw_obs_mcp.triggers.daily_review_runner`
- `start interval = 300`
- `run at load = 1`

If the agent isn't loaded, re-run `jkw-obs-mcp-setup` and check the bootstrap return code.

- [ ] **Step 2: Trigger the agent manually and watch the no-op path**

If today's daily review already exists (i.e., `~/.config/jkw-obs-mcp/last-daily-review.json` was updated today), the trigger should be a no-op.

Run:
```bash
launchctl kickstart "gui/$(id -u)/com.jinchiwei.jkw-obs-mcp.daily-review"
sleep 2
ls -la ~/Library/Logs/com.jinchiwei.jkw-obs-mcp.daily-review.*
cat ~/Library/Logs/com.jinchiwei.jkw-obs-mcp.daily-review.err
```

Expected: log files exist, error log is empty (or contains the previous run's "wrote ..." message). The kickstart fires the runner, runner sees today's date matches state file, exits 0 silently.

- [ ] **Step 3: Force a stale-state run to verify generate fires**

Move today's state aside to simulate "haven't run today yet":

```bash
mv ~/.config/jkw-obs-mcp/last-daily-review.json ~/.config/jkw-obs-mcp/last-daily-review.json.bak
launchctl kickstart "gui/$(id -u)/com.jinchiwei.jkw-obs-mcp.daily-review"
# Wait ~30s for generate_daily_review (Anthropic call)
sleep 45
cat ~/Library/Logs/com.jinchiwei.jkw-obs-mcp.daily-review.err
ls -la ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/jkw_obs/kb/dreamingmachine/daily/
```

Expected:
- The error log shows `wrote /Users/jinchiwei/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs/kb/dreamingmachine/daily/2026-04-27.md`
- A fresh state file is at `~/.config/jkw-obs-mcp/last-daily-review.json` with today's `last_run_at`
- Today's daily-review note has been re-written

Then restore the original state file (or just delete the .bak — the new one is more recent and correct):
```bash
rm -f ~/.config/jkw-obs-mcp/last-daily-review.json.bak
```

- [ ] **Step 4: Verify wake-from-sleep behavior (passive observation)**

Close the laptop lid for at least 5 minutes, then reopen. Within 5 min of waking:

```bash
tail -1 ~/Library/Logs/com.jinchiwei.jkw-obs-mcp.daily-review.err
ls -la ~/.config/jkw-obs-mcp/last-daily-review.json
```

If today already had a review when you closed the lid: the no-op fires, error log shows nothing new, state file unchanged. If yesterday's state was the most recent: a new review fires within 5 min.

- [ ] **Step 5: (Optional) Verify on Linux**

If you have access to a Linux test machine (e.g., a VM), clone the repo, `pip install -e ".[dev]"` (no `mac` or `gmail` extras), and run:

```bash
jkw-obs-mcp-setup
```

Expected:
- `Detected platform: Linux`
- Step 1 (config dir) succeeds
- Step 2 (machines.toml) reports "not registered" with instructions to add the hostname
- Step 3 prints "Gmail OAuth — skipped (Mac-only feature)"
- Step 4 prints "launchd boot trigger — skipped (Mac-only feature)"
- Exit code 0

This is optional because Plan 7 will exercise the cluster path more thoroughly.

- [ ] **Step 6: Tag and push**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git push origin main
git tag plan-6-complete
git push origin --tags
```

---

## Self-Review Checklist

- [ ] All 9 tasks committed
- [ ] `pytest -v` shows full suite green (~178 tests)
- [ ] `jkw-obs-mcp-setup` prints platform-aware status report on dreamingmachine
- [ ] `jkw-obs-mcp-daily-review` exits 0 in <100ms when today's review already exists
- [ ] `launchctl print` shows the agent loaded with `start interval = 300` and `run at load = 1`
- [ ] Forcing a stale state and kickstarting the agent re-generates today's daily review
- [ ] Wake-from-sleep next morning produces a fresh daily review within 5 min
- [ ] `git tag plan-6-complete` pushed

When all boxes ticked, Plan 6 done. Plan 7 (cluster rollout to scs/fac/cph) is next — it'll mostly be running `jkw-obs-mcp-setup` on each cluster plus deciding the cluster-side daily-review trigger (likely "skip — clusters lack the personal context").

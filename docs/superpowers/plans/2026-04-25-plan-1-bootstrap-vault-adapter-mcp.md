# Plan 1: Bootstrap + Vault Adapter + Minimal MCP

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a minimal MCP server on dreamingmachine that exposes vault read/list/write tools to Claude Code, with sandboxed writes to `kb/dreamingmachine/` and machine_id auto-detection. No embeddings, no compilers, no generators yet — just the bedrock that everything else builds on.

**Architecture:** Python package `jkw_obs_mcp` installed as a stdio MCP server. Config via `~/.config/jkw-obs-mcp/config.toml` (per-machine) + `machines.toml` (versioned, hostname → machine_id). VaultAdapter encapsulates all filesystem ops with hard-coded sandbox: writes only allowed under `<vault_root>/kb/<machine_id>/`. MCP layer registers three tools (`read_note`, `list_notes`, `write_kb_note`) and serves over stdio.

**Tech Stack:** Python 3.11+, `mcp` SDK (Anthropic, official), `tomllib` (stdlib), `pytest`, `pytest-asyncio`. No embeddings/network deps in this plan.

---

## File Structure

Repo root: `~/arcadia/臥龍/obsidian/jkw_obs-mcp/` (Mac), `~/arcadia/obsidian/jkw_obs-mcp/` (clusters).

```
jkw_obs-mcp/
├── pyproject.toml                      Package metadata + dependencies
├── README.md                           Install + usage (starter version)
├── .gitignore                          Excludes .venv/, __pycache__/, *.egg-info/, data/
├── .python-version                     pyenv hint: 3.11
├── machines.toml                       Hostname → machine_id registry (versioned)
├── install.sh                          Stub for Plan 6 (echoes "use Plan 6 install")
├── src/
│   └── jkw_obs_mcp/
│       ├── __init__.py                 Version constant
│       ├── errors.py                   UnknownMachineError, SandboxViolationError
│       ├── config.py                   load_config(), load_machines(), detect_machine_id()
│       ├── adapter/
│       │   ├── __init__.py
│       │   └── vault.py                VaultAdapter: read_note, list_notes, write_kb_note
│       └── mcp/
│           ├── __init__.py
│           └── server.py               Tool registration + stdio entry point
└── tests/
    ├── __init__.py
    ├── conftest.py                     Shared pytest fixtures (temp vault, fake config)
    ├── test_config.py                  Config + machine detection
    ├── test_vault.py                   Read/list/write/sandbox
    └── test_mcp_server.py              Smoke: tools register and respond
```

Each file has one responsibility. `vault.py` handles all filesystem ops. `config.py` does only loading + detection. `server.py` does only MCP wiring (no business logic).

---

## Task 1: Repo skeleton — pyproject.toml + .gitignore + .python-version

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.python-version`
- Create: `src/jkw_obs_mcp/__init__.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "jkw-obs-mcp"
version = "0.1.0"
description = "Personal second-brain MCP server over an Obsidian vault"
requires-python = ">=3.11"
authors = [{ name = "Jin Wei", email = "mrjinch@gmail.com" }]
license = { text = "MIT" }
dependencies = [
    "mcp>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[project.scripts]
jkw-obs-mcp = "jkw_obs_mcp.mcp.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/jkw_obs_mcp"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write `.gitignore`**

```
# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/
*.egg-info/
build/
dist/

# Venv
.venv/
venv/
.python-version-local

# Runtime data (per machine, regeneratable)
data/
*.db
*.db-shm
*.db-wal
*.log

# Editor / OS
.DS_Store
.idea/
.vscode/
*.swp
```

- [ ] **Step 3: Write `.python-version`**

```
3.11
```

- [ ] **Step 4: Write `src/jkw_obs_mcp/__init__.py`**

```python
"""Personal second-brain MCP server over an Obsidian vault."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Verify package can be installed in editable mode**

Run: `cd ~/arcadia/臥龍/obsidian/jkw_obs-mcp && python3.11 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
Expected: install succeeds, `pip show jkw-obs-mcp` lists version 0.1.0.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore .python-version src/jkw_obs_mcp/__init__.py
git commit -m "feat: bootstrap pyproject.toml + package skeleton"
```

---

## Task 2: Smoke test that the package imports

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Write `tests/__init__.py`**

```python
```

(Empty file — makes tests/ a package.)

- [ ] **Step 2: Write the failing test at `tests/test_smoke.py`**

```python
import jkw_obs_mcp


def test_version_is_set():
    assert jkw_obs_mcp.__version__ == "0.1.0"
```

- [ ] **Step 3: Run the test**

Run: `pytest tests/test_smoke.py -v`
Expected: PASS (since `__init__.py` from Task 1 already sets `__version__`).

- [ ] **Step 4: Commit**

```bash
git add tests/__init__.py tests/test_smoke.py
git commit -m "test: smoke test that package imports"
```

---

## Task 3: Errors module

**Files:**
- Create: `src/jkw_obs_mcp/errors.py`
- Create: `tests/test_errors.py`

- [ ] **Step 1: Write the failing test at `tests/test_errors.py`**

```python
import pytest

from jkw_obs_mcp.errors import (
    UnknownMachineError,
    SandboxViolationError,
)


def test_unknown_machine_error_carries_hostname_and_os():
    err = UnknownMachineError(hostname="strange-host", os_name="linux")
    assert err.hostname == "strange-host"
    assert err.os_name == "linux"
    assert "strange-host" in str(err)
    assert "linux" in str(err)


def test_sandbox_violation_error_carries_attempted_path():
    err = SandboxViolationError(attempted_path="/tmp/escape", allowed_root="/vault/kb/mac")
    assert err.attempted_path == "/tmp/escape"
    assert err.allowed_root == "/vault/kb/mac"
    assert "/tmp/escape" in str(err)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jkw_obs_mcp.errors'`.

- [ ] **Step 3: Write `src/jkw_obs_mcp/errors.py`**

```python
"""Domain-specific errors raised by jkw_obs_mcp."""


class JkwObsMcpError(Exception):
    """Base class for all jkw_obs_mcp errors."""


class UnknownMachineError(JkwObsMcpError):
    """Raised when the current host doesn't match any machine in machines.toml."""

    def __init__(self, hostname: str, os_name: str) -> None:
        self.hostname = hostname
        self.os_name = os_name
        super().__init__(
            f"hostname {hostname!r} (os={os_name!r}) does not match any entry in "
            f"machines.toml. Add an alias or set machine.id explicitly in config.toml."
        )


class SandboxViolationError(JkwObsMcpError):
    """Raised when a write would land outside the allowed kb/<machine_id>/ root."""

    def __init__(self, attempted_path: str, allowed_root: str) -> None:
        self.attempted_path = attempted_path
        self.allowed_root = allowed_root
        super().__init__(
            f"refusing to write to {attempted_path!r}: outside allowed root {allowed_root!r}"
        )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_errors.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/errors.py tests/test_errors.py
git commit -m "feat: domain error types for unknown-machine and sandbox-violation"
```

---

## Task 4: machines.toml registry (versioned data file)

**Files:**
- Create: `machines.toml`

- [ ] **Step 1: Write `machines.toml`**

```toml
# Hostname -> machine_id registry. Used by install.sh and MCP startup
# to auto-detect which machine the server is running on.
#
# Hostname matching is CASE-SENSITIVE. The os field is a tiebreaker for
# future cases like teal-native vs tealw on the same physical hardware.
#
# To add a new machine:
#   1. Add an entry below.
#   2. Bump the file's git history (commit + push).
#   3. On the new machine, git pull and re-run install.sh.

[dreamingmachine]
hostname_aliases = ["dreamingmachine"]
os = "darwin"

[scs]
hostname_aliases = ["callosum"]
os = "linux"

[fac]
hostname_aliases = ["chpc-ucsf-login-vm1"]
os = "linux"

[cph]
hostname_aliases = ["c15pu01"]
os = "linux"

[teal]
# WSL Linux on the MXJ-TEALITX physical machine. Native Windows side
# is deferred to v1.5+.
hostname_aliases = ["mxj-tealitx"]
os = "linux"

[cdx]
# AWS SageMaker default hostname.
hostname_aliases = ["default"]
os = "linux"
```

- [ ] **Step 2: Sanity-check the file parses as TOML**

Run: `python3.11 -c 'import tomllib; print(list(tomllib.loads(open("machines.toml").read()).keys()))'`
Expected: `['dreamingmachine', 'scs', 'fac', 'cph', 'teal', 'cdx']`

- [ ] **Step 3: Commit**

```bash
git add machines.toml
git commit -m "feat: machines.toml registry of hostname -> machine_id mappings"
```

---

## Task 5: Config loader — `load_config()`

**Files:**
- Create: `src/jkw_obs_mcp/config.py`
- Create: `tests/conftest.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write shared fixtures at `tests/conftest.py`**

```python
"""Shared pytest fixtures."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    """Empty temp dir to stand in for ~/.config/jkw-obs-mcp/."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    return cfg


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Temp vault root with a tiny tree of fixture markdown files."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Admin").mkdir()
    (vault / "Admin" / "Saiyan.md").write_text("# Saiyan\nworkout log\n")
    (vault / "kb").mkdir()
    (vault / "kb" / "dreamingmachine").mkdir()
    return vault


@pytest.fixture
def tmp_machines_toml(tmp_path: Path) -> Path:
    """Minimal machines.toml for tests."""
    p = tmp_path / "machines.toml"
    p.write_text(
        """
[dreamingmachine]
hostname_aliases = ["dreamingmachine"]
os = "darwin"

[scs]
hostname_aliases = ["callosum"]
os = "linux"

[teal]
hostname_aliases = ["mxj-tealitx"]
os = "linux"
"""
    )
    return p
```

- [ ] **Step 2: Write the failing test at `tests/test_config.py`**

```python
from pathlib import Path

import pytest

from jkw_obs_mcp.config import Config, load_config


def test_load_config_from_toml(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[paths]
vault_root = "/some/vault"

[machine]
id = "dreamingmachine"

[generation]
daily_review_enabled = true
"""
    )

    cfg = load_config(cfg_file)

    assert isinstance(cfg, Config)
    assert cfg.vault_root == Path("/some/vault")
    assert cfg.machine_id == "dreamingmachine"
    assert cfg.daily_review_enabled is True


def test_load_config_expands_home_in_vault_root(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[paths]
vault_root = "~/vault"

[machine]
id = "dreamingmachine"
"""
    )

    cfg = load_config(cfg_file)

    assert "~" not in str(cfg.vault_root)
    assert str(cfg.vault_root).endswith("/vault")
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'Config' from 'jkw_obs_mcp.config'`.

- [ ] **Step 4: Write `src/jkw_obs_mcp/config.py`**

```python
"""Configuration loading for jkw_obs_mcp."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Per-machine configuration loaded from config.toml."""

    vault_root: Path
    machine_id: str
    daily_review_enabled: bool = False


def load_config(path: Path) -> Config:
    """Load Config from a TOML file. Expands ~ in vault_root."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    paths = data.get("paths", {})
    machine = data.get("machine", {})
    generation = data.get("generation", {})

    vault_root_str = paths.get("vault_root", "")
    if not vault_root_str:
        raise ValueError(f"{path}: [paths].vault_root is required")
    vault_root = Path(vault_root_str).expanduser().resolve()

    machine_id = machine.get("id", "")
    if not machine_id:
        raise ValueError(f"{path}: [machine].id is required")

    return Config(
        vault_root=vault_root,
        machine_id=machine_id,
        daily_review_enabled=generation.get("daily_review_enabled", False),
    )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/config.py tests/conftest.py tests/test_config.py
git commit -m "feat: Config dataclass + load_config() from TOML"
```

---

## Task 6: Machines registry loader — `load_machines()`

**Files:**
- Modify: `src/jkw_obs_mcp/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Add the failing test to `tests/test_config.py`**

Append to the existing test file:

```python
from jkw_obs_mcp.config import MachineRegistry, load_machines


def test_load_machines_returns_registry(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)

    assert isinstance(registry, MachineRegistry)
    assert "dreamingmachine" in registry
    assert "scs" in registry
    assert "teal" in registry

    dm = registry["dreamingmachine"]
    assert dm.hostname_aliases == ["dreamingmachine"]
    assert dm.os == "darwin"

    teal = registry["teal"]
    assert teal.hostname_aliases == ["mxj-tealitx"]
    assert teal.os == "linux"


def test_load_machines_lookup_by_id_raises_on_missing(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)
    import pytest as _pytest
    with _pytest.raises(KeyError):
        registry["nonexistent"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'MachineRegistry'`.

- [ ] **Step 3: Add to `src/jkw_obs_mcp/config.py`**

Append:

```python
@dataclass(frozen=True)
class MachineEntry:
    """One machine in the registry."""

    machine_id: str
    hostname_aliases: list[str]
    os: str


class MachineRegistry:
    """Read-only mapping of machine_id -> MachineEntry."""

    def __init__(self, entries: dict[str, MachineEntry]) -> None:
        self._entries = entries

    def __contains__(self, machine_id: str) -> bool:
        return machine_id in self._entries

    def __getitem__(self, machine_id: str) -> MachineEntry:
        return self._entries[machine_id]

    def __iter__(self):
        return iter(self._entries.values())

    def items(self):
        return self._entries.items()


def load_machines(path: Path) -> MachineRegistry:
    """Load the machines.toml registry file."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    entries: dict[str, MachineEntry] = {}
    for machine_id, body in data.items():
        entries[machine_id] = MachineEntry(
            machine_id=machine_id,
            hostname_aliases=list(body.get("hostname_aliases", [])),
            os=body.get("os", ""),
        )
    return MachineRegistry(entries)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_config.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/config.py tests/test_config.py
git commit -m "feat: MachineRegistry + load_machines() from machines.toml"
```

---

## Task 7: Machine detection — `detect_machine_id()`

**Files:**
- Modify: `src/jkw_obs_mcp/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Add the failing tests to `tests/test_config.py`**

Append:

```python
from jkw_obs_mcp.config import detect_machine_id
from jkw_obs_mcp.errors import UnknownMachineError


def test_detect_dreamingmachine_on_mac(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)
    machine_id = detect_machine_id(
        registry, hostname="dreamingmachine", os_name="darwin"
    )
    assert machine_id == "dreamingmachine"


def test_detect_scs_on_linux(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)
    machine_id = detect_machine_id(registry, hostname="callosum", os_name="linux")
    assert machine_id == "scs"


def test_detect_is_case_sensitive(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)
    # tealw alias is "mxj-tealitx" lowercase — uppercase should NOT match.
    with pytest.raises(UnknownMachineError):
        detect_machine_id(registry, hostname="MXJ-TEALITX", os_name="linux")


def test_detect_uses_os_as_tiebreaker(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)
    # dreamingmachine is os=darwin; same hostname on linux must NOT match.
    with pytest.raises(UnknownMachineError):
        detect_machine_id(registry, hostname="dreamingmachine", os_name="linux")


def test_detect_raises_unknown_machine_on_no_match(tmp_machines_toml):
    registry = load_machines(tmp_machines_toml)
    with pytest.raises(UnknownMachineError) as excinfo:
        detect_machine_id(registry, hostname="random-laptop", os_name="darwin")
    assert excinfo.value.hostname == "random-laptop"
    assert excinfo.value.os_name == "darwin"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'detect_machine_id'`.

- [ ] **Step 3: Add to `src/jkw_obs_mcp/config.py`**

Append:

```python
import platform
import socket

from jkw_obs_mcp.errors import UnknownMachineError


def detect_machine_id(
    registry: MachineRegistry,
    *,
    hostname: str | None = None,
    os_name: str | None = None,
) -> str:
    """Resolve the current machine's id from hostname + os.

    Hostname matching is CASE-SENSITIVE. os acts as a tiebreaker. Both args
    are optional for testability — if omitted, uses socket.gethostname() and
    platform.system().
    """
    if hostname is None:
        hostname = socket.gethostname()
        # Strip domain suffix e.g. "dreamingmachine.local" -> "dreamingmachine"
        hostname = hostname.split(".", 1)[0]
    if os_name is None:
        os_name = platform.system().lower()

    for entry in registry:
        if hostname in entry.hostname_aliases and entry.os == os_name:
            return entry.machine_id

    raise UnknownMachineError(hostname=hostname, os_name=os_name)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_config.py -v`
Expected: PASS (9 tests in this file total).

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/config.py tests/test_config.py
git commit -m "feat: detect_machine_id() with case-sensitive hostname + os tiebreaker"
```

---

## Task 8: VaultAdapter — `read_note()` and `list_notes()`

**Files:**
- Create: `src/jkw_obs_mcp/adapter/__init__.py`
- Create: `src/jkw_obs_mcp/adapter/vault.py`
- Create: `tests/test_vault.py`

- [ ] **Step 1: Write `src/jkw_obs_mcp/adapter/__init__.py`**

```python
```

(Empty file.)

- [ ] **Step 2: Write the failing tests at `tests/test_vault.py`**

```python
from pathlib import Path

import pytest

from jkw_obs_mcp.adapter.vault import VaultAdapter


def test_read_note_returns_content(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    content = adapter.read_note("Admin/Saiyan.md")

    assert "workout log" in content
    assert content.startswith("# Saiyan")


def test_read_note_rejects_path_traversal(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    from jkw_obs_mcp.errors import SandboxViolationError

    with pytest.raises(SandboxViolationError):
        adapter.read_note("../../../etc/passwd")


def test_list_notes_returns_relative_paths(tmp_vault):
    # Add a few more files to make this interesting.
    (tmp_vault / "Arcadia").mkdir()
    (tmp_vault / "Arcadia" / "lab-meeting.md").write_text("# Lab Meeting\n")

    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    notes = adapter.list_notes()

    paths = sorted(str(p) for p in notes)
    assert "Admin/Saiyan.md" in paths
    assert "Arcadia/lab-meeting.md" in paths
    # Only .md files
    assert all(p.endswith(".md") for p in paths)


def test_list_notes_filters_by_subdir(tmp_vault):
    (tmp_vault / "Arcadia").mkdir()
    (tmp_vault / "Arcadia" / "lab-meeting.md").write_text("# Lab Meeting\n")

    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    notes = adapter.list_notes(subdir="Admin")

    paths = sorted(str(p) for p in notes)
    assert paths == ["Admin/Saiyan.md"]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_vault.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jkw_obs_mcp.adapter.vault'`.

- [ ] **Step 4: Write `src/jkw_obs_mcp/adapter/vault.py`**

```python
"""Filesystem adapter for the Obsidian vault.

Encapsulates ALL vault filesystem ops. Sandbox enforcement lives here:
writes go only to <vault_root>/kb/<machine_id>/. Reads are unrestricted
within <vault_root>.
"""

from __future__ import annotations

from pathlib import Path

from jkw_obs_mcp.errors import SandboxViolationError


class VaultAdapter:
    """Reads and writes scoped to one vault + one machine."""

    def __init__(self, vault_root: Path, machine_id: str) -> None:
        self.vault_root = vault_root.resolve()
        self.machine_id = machine_id
        self.kb_root = (self.vault_root / "kb" / machine_id).resolve()

    def read_note(self, rel_path: str) -> str:
        """Read a note at vault-relative path. Returns text content."""
        target = self._resolve_safe(rel_path, allowed_root=self.vault_root)
        return target.read_text(encoding="utf-8")

    def list_notes(self, subdir: str = "") -> list[Path]:
        """List all .md files under vault_root/<subdir>/, recursively.

        Returns vault-relative paths (e.g. "Admin/Saiyan.md").
        """
        if subdir:
            base = self._resolve_safe(subdir, allowed_root=self.vault_root)
        else:
            base = self.vault_root

        return sorted(
            p.relative_to(self.vault_root)
            for p in base.rglob("*.md")
            if p.is_file()
        )

    def _resolve_safe(self, rel_path: str, *, allowed_root: Path) -> Path:
        """Resolve rel_path against allowed_root, refusing path traversal."""
        candidate = (allowed_root / rel_path).resolve()
        try:
            candidate.relative_to(allowed_root)
        except ValueError:
            raise SandboxViolationError(
                attempted_path=str(candidate), allowed_root=str(allowed_root)
            ) from None
        return candidate
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_vault.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/adapter/__init__.py src/jkw_obs_mcp/adapter/vault.py tests/test_vault.py
git commit -m "feat: VaultAdapter.read_note + list_notes with traversal guard"
```

---

## Task 9: VaultAdapter — `write_kb_note()` with sandbox enforcement

**Files:**
- Modify: `src/jkw_obs_mcp/adapter/vault.py`
- Modify: `tests/test_vault.py`

- [ ] **Step 1: Add the failing tests to `tests/test_vault.py`**

Append:

```python
def test_write_kb_note_writes_to_machine_subfolder(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    written = adapter.write_kb_note(
        filename="2026-04-25.md",
        content="# Today\n- ate cake\n",
        subdir="daily",
    )

    expected = tmp_vault / "kb" / "dreamingmachine" / "daily" / "2026-04-25.md"
    assert written == expected
    assert expected.read_text() == "# Today\n- ate cake\n"


def test_write_kb_note_creates_subdir_if_missing(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    adapter.write_kb_note(filename="x.md", content="hi", subdir="ad-hoc/deep/nested")

    assert (
        tmp_vault / "kb" / "dreamingmachine" / "ad-hoc" / "deep" / "nested" / "x.md"
    ).read_text() == "hi"


def test_write_kb_note_rejects_traversal_in_filename(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    from jkw_obs_mcp.errors import SandboxViolationError

    with pytest.raises(SandboxViolationError):
        adapter.write_kb_note(
            filename="../../../etc/evil.md", content="x", subdir="ad-hoc"
        )


def test_write_kb_note_rejects_traversal_in_subdir(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    from jkw_obs_mcp.errors import SandboxViolationError

    with pytest.raises(SandboxViolationError):
        adapter.write_kb_note(filename="x.md", content="x", subdir="../mac")


def test_write_kb_note_rejects_writing_to_other_machines_folder(tmp_vault):
    """SCS shouldn't be able to write to kb/dreamingmachine/."""
    (tmp_vault / "kb" / "scs").mkdir()
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="scs")

    from jkw_obs_mcp.errors import SandboxViolationError

    # Even if subdir = "../dreamingmachine/daily", resolution must keep us in kb/scs/.
    with pytest.raises(SandboxViolationError):
        adapter.write_kb_note(
            filename="x.md", content="x", subdir="../dreamingmachine/daily"
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_vault.py -v`
Expected: FAIL with `AttributeError: 'VaultAdapter' object has no attribute 'write_kb_note'`.

- [ ] **Step 3: Add `write_kb_note` to `src/jkw_obs_mcp/adapter/vault.py`**

Add this method to the `VaultAdapter` class (just before `_resolve_safe`):

```python
    def write_kb_note(self, filename: str, content: str, subdir: str = "ad-hoc") -> Path:
        """Write a note into <vault_root>/kb/<machine_id>/<subdir>/<filename>.

        Rejects path traversal and writes outside kb/<machine_id>/.
        Returns the absolute path written.
        """
        # Resolve subdir relative to kb_root, refusing escape.
        target_dir = self._resolve_safe(subdir, allowed_root=self.kb_root)
        # Resolve filename relative to target_dir, refusing escape.
        target = self._resolve_safe(filename, allowed_root=target_dir)
        # Ensure final path is still under kb_root (defense in depth).
        try:
            target.relative_to(self.kb_root)
        except ValueError:
            raise SandboxViolationError(
                attempted_path=str(target), allowed_root=str(self.kb_root)
            ) from None

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_vault.py -v`
Expected: PASS (9 tests in this file total).

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/adapter/vault.py tests/test_vault.py
git commit -m "feat: VaultAdapter.write_kb_note with sandboxed kb/<machine_id>/ writes"
```

---

## Task 10: MCP server — register `read_note` tool

**Files:**
- Create: `src/jkw_obs_mcp/mcp/__init__.py`
- Create: `src/jkw_obs_mcp/mcp/server.py`
- Create: `tests/test_mcp_server.py`

- [ ] **Step 1: Write `src/jkw_obs_mcp/mcp/__init__.py`**

```python
```

(Empty file.)

- [ ] **Step 2: Write the failing test at `tests/test_mcp_server.py`**

```python
"""Tests for the MCP server's tool registration and dispatch.

We test the dispatcher functions directly (`tools_for_adapter`, `dispatch_tool`)
rather than the live MCP server — those are pure functions, easy to unit test
without faking the MCP runtime. The thin wiring layer in `build_server` is
exercised by the manual smoke test in Task 14.
"""

from pathlib import Path

import pytest

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.mcp.server import dispatch_tool, tools_for_adapter


def test_tools_for_adapter_includes_read_note(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}

    assert "read_note" in names


@pytest.mark.asyncio
async def test_dispatch_read_note_returns_file_content(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    result = await dispatch_tool(adapter, "read_note", {"path": "Admin/Saiyan.md"})

    # MCP tools return a list of content blocks; the first text block is the file content.
    assert len(result) >= 1
    text = result[0].text
    assert "workout log" in text
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_mcp_server.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError: cannot import name 'build_server'`.

- [ ] **Step 4: Write `src/jkw_obs_mcp/mcp/server.py`**

```python
"""MCP server for jkw_obs_mcp.

Two layers:
1. Pure functions (`tools_for_adapter`, `dispatch_tool`) — easy to unit test.
2. Thin wiring layer (`build_server`) — registers the pure functions as MCP
   handlers. Exercised only by the manual smoke test (Plan 1 Task 14) and
   in production at startup.
"""

from __future__ import annotations

from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from jkw_obs_mcp.adapter.vault import VaultAdapter


def tools_for_adapter(adapter: VaultAdapter) -> list[Tool]:
    """Return the MCP Tool definitions exposed by this server.

    The adapter argument is here for future per-machine tool gating
    (e.g. only register get_upcoming_events on macOS) — unused in Plan 1.
    """
    _ = adapter  # reserved for future use
    return [
        Tool(
            name="read_note",
            description="Read a markdown note from the Obsidian vault. "
            "Path is relative to the vault root (e.g. 'Admin/Saiyan.md').",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Vault-relative path to the .md file",
                    },
                },
                "required": ["path"],
            },
        ),
    ]


async def dispatch_tool(
    adapter: VaultAdapter, name: str, arguments: dict[str, Any]
) -> list[TextContent]:
    """Dispatch a tool call to the right adapter method."""
    if name == "read_note":
        text = adapter.read_note(arguments["path"])
        return [TextContent(type="text", text=text)]
    raise ValueError(f"unknown tool: {name}")


def build_server(adapter: VaultAdapter) -> Server:
    """Create an MCP Server with the vault tools registered.

    Production entry only. For unit tests, use tools_for_adapter and
    dispatch_tool directly.
    """
    server = Server("jkw-obs-mcp")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return tools_for_adapter(adapter)

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        return await dispatch_tool(adapter, name, arguments)

    return server
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_mcp_server.py -v`
Expected: PASS (2 tests).

(Note: if `mcp` SDK API has changed since this plan was written, verify against the current `mcp` package docs at https://github.com/modelcontextprotocol/python-sdk and adapt.)

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/mcp/__init__.py src/jkw_obs_mcp/mcp/server.py tests/test_mcp_server.py
git commit -m "feat: MCP server skeleton with read_note tool"
```

---

## Task 11: MCP server — add `list_notes` and `write_kb_note` tools

**Files:**
- Modify: `src/jkw_obs_mcp/mcp/server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Add the failing tests to `tests/test_mcp_server.py`**

Append:

```python
def test_tools_for_adapter_includes_all_three(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    tools = tools_for_adapter(adapter)
    names = {t.name for t in tools}

    assert names == {"read_note", "list_notes", "write_kb_note"}


@pytest.mark.asyncio
async def test_dispatch_list_notes_returns_paths(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    result = await dispatch_tool(adapter, "list_notes", {})

    text = result[0].text
    assert "Admin/Saiyan.md" in text


@pytest.mark.asyncio
async def test_dispatch_write_kb_note_writes_file(tmp_vault):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")

    result = await dispatch_tool(
        adapter,
        "write_kb_note",
        {"filename": "test.md", "content": "# Hello\n", "subdir": "ad-hoc"},
    )

    written_path = tmp_vault / "kb" / "dreamingmachine" / "ad-hoc" / "test.md"
    assert written_path.read_text() == "# Hello\n"
    # Tool returns confirmation text
    assert "test.md" in result[0].text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_mcp_server.py -v`
Expected: FAIL — only `read_note` is registered; new tests for `list_notes` and `write_kb_note` fail.

- [ ] **Step 3: Update `src/jkw_obs_mcp/mcp/server.py`**

Replace the existing `tools_for_adapter` and `dispatch_tool` functions with the full versions:

```python
def tools_for_adapter(adapter: VaultAdapter) -> list[Tool]:
    """Return the MCP Tool definitions exposed by this server."""
    _ = adapter
    return [
        Tool(
            name="read_note",
            description="Read a markdown note from the Obsidian vault. "
            "Path is relative to the vault root (e.g. 'Admin/Saiyan.md').",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Vault-relative path to the .md file",
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="list_notes",
            description="List all markdown files in the vault, optionally "
            "scoped to a subdirectory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdir": {
                        "type": "string",
                        "description": "Vault-relative subdir to scope the listing",
                        "default": "",
                    },
                },
            },
        ),
        Tool(
            name="write_kb_note",
            description="Write a markdown note into kb/<this-machine>/<subdir>/. "
            "Refuses writes outside the machine's kb sandbox.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Filename (e.g. '2026-04-25.md')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full markdown content",
                    },
                    "subdir": {
                        "type": "string",
                        "description": "Subdir under kb/<machine>/",
                        "default": "ad-hoc",
                    },
                },
                "required": ["filename", "content"],
            },
        ),
    ]


async def dispatch_tool(
    adapter: VaultAdapter, name: str, arguments: dict[str, Any]
) -> list[TextContent]:
    """Dispatch a tool call to the right adapter method."""
    if name == "read_note":
        text = adapter.read_note(arguments["path"])
        return [TextContent(type="text", text=text)]
    if name == "list_notes":
        paths = adapter.list_notes(subdir=arguments.get("subdir", ""))
        text = "\n".join(str(p) for p in paths)
        return [TextContent(type="text", text=text)]
    if name == "write_kb_note":
        written = adapter.write_kb_note(
            filename=arguments["filename"],
            content=arguments["content"],
            subdir=arguments.get("subdir", "ad-hoc"),
        )
        return [TextContent(type="text", text=f"wrote {written}")]
    raise ValueError(f"unknown tool: {name}")
```

`build_server` itself doesn't change — its inner handlers already delegate to these two functions.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_mcp_server.py -v`
Expected: PASS (5 tests in this file total).

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/mcp/server.py tests/test_mcp_server.py
git commit -m "feat: list_notes + write_kb_note tools registered on MCP server"
```

---

## Task 12: Stdio entry point — `main()`

**Files:**
- Modify: `src/jkw_obs_mcp/mcp/server.py`

- [ ] **Step 1: Add `main()` to `src/jkw_obs_mcp/mcp/server.py`**

Append to the file:

```python
import asyncio
import os
from pathlib import Path

from mcp.server.stdio import stdio_server

from jkw_obs_mcp.config import detect_machine_id, load_config, load_machines


def main() -> None:
    """Entry point for the `jkw-obs-mcp` console script.

    Loads ~/.config/jkw-obs-mcp/config.toml and the bundled machines.toml,
    builds the VaultAdapter, and serves over stdio.
    """
    cfg_path = Path(os.path.expanduser("~/.config/jkw-obs-mcp/config.toml"))
    if not cfg_path.exists():
        raise SystemExit(
            f"config not found at {cfg_path}. Run install.sh to bootstrap."
        )

    cfg = load_config(cfg_path)

    # machines.toml ships with the package; locate it relative to this file.
    pkg_root = Path(__file__).resolve().parent.parent.parent.parent
    machines_path = pkg_root / "machines.toml"
    if not machines_path.exists():
        raise SystemExit(f"machines.toml not found at {machines_path}")
    registry = load_machines(machines_path)

    # Validate config.machine_id against registry + actual hostname (defense in depth).
    if cfg.machine_id not in registry:
        raise SystemExit(
            f"config.machine.id={cfg.machine_id!r} is not in machines.toml. "
            f"Known: {list(k for k, _ in registry.items())}"
        )

    detected = detect_machine_id(registry)
    if detected != cfg.machine_id:
        raise SystemExit(
            f"hostname suggests {detected!r} but config says {cfg.machine_id!r}. "
            f"Edit ~/.config/jkw-obs-mcp/config.toml or update machines.toml."
        )

    adapter = VaultAdapter(vault_root=cfg.vault_root, machine_id=cfg.machine_id)
    server = build_server(adapter)

    async def _run() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(_run())
```

- [ ] **Step 2: Verify the entry point script registers**

Run: `pip install -e .` (re-install after editing)
Then: `which jkw-obs-mcp`
Expected: prints a path inside `.venv/bin/jkw-obs-mcp` (or similar).

Then: `jkw-obs-mcp` (with no config installed yet)
Expected: exits with `config not found at ~/.config/jkw-obs-mcp/config.toml. Run install.sh to bootstrap.`

- [ ] **Step 3: Commit**

```bash
git add src/jkw_obs_mcp/mcp/server.py
git commit -m "feat: stdio entry point with config + machine validation"
```

---

## Task 13: README starter + install.sh stub

**Files:**
- Create: `README.md`
- Create: `install.sh`

- [ ] **Step 1: Write `README.md`**

```markdown
# jkw_obs-mcp

Personal second-brain MCP server over an Obsidian vault. See the design doc
at `docs/superpowers/plans/` for the full architecture.

## Install (Plan 1 manual setup; full install.sh ships in Plan 6)

```bash
# 1. Clone and enter
git clone git@github.com:jinchiwei/jkw_obs-mcp.git
cd jkw_obs-mcp

# 2. Create venv and install
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 3. Run tests to confirm setup
pytest -v

# 4. Bootstrap config
mkdir -p ~/.config/jkw-obs-mcp
cat > ~/.config/jkw-obs-mcp/config.toml <<'EOF'
[paths]
vault_root = "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs"

[machine]
id = "dreamingmachine"

[generation]
daily_review_enabled = false
EOF

# 5. Smoke test the entry point
jkw-obs-mcp  # exits cleanly if config + machine_id match; runs stdio server otherwise.
```

## Wire into Claude Code

Add to `~/.claude/mcp_servers.json` (or your existing config):

```json
{
  "mcpServers": {
    "jkw-obs": {
      "command": "/absolute/path/to/jkw_obs-mcp/.venv/bin/jkw-obs-mcp"
    }
  }
}
```

Restart Claude Code. The three tools (`read_note`, `list_notes`, `write_kb_note`)
should appear.

## Tools (Plan 1)

- `read_note(path)` — read any markdown file in the vault
- `list_notes(subdir="")` — list all .md files (optionally scoped)
- `write_kb_note(filename, content, subdir="ad-hoc")` — write only to `kb/<this-machine>/`

Embeddings, semantic search, compilers, calendar, daily review — all in later plans.

## Status

Plan 1 of 7. See `docs/superpowers/plans/` for the full roadmap.
```

- [ ] **Step 2: Write `install.sh` stub**

```bash
#!/usr/bin/env bash
# Stub — full installer ships in Plan 6.
echo "install.sh stub: see Plan 6 for the full installer."
echo "For now, follow the manual steps in README.md."
exit 1
```

- [ ] **Step 3: Make install.sh executable**

Run: `chmod +x install.sh`

- [ ] **Step 4: Commit**

```bash
git add README.md install.sh
git commit -m "docs: README + install.sh stub for Plan 1"
```

---

## Task 14: Manual end-to-end smoke test on dreamingmachine

This task is non-TDD — it exercises the real Claude Code integration once
on the actual Mac vault. No automated checks; success is "the tools work in
Claude Code."

- [ ] **Step 1: Bootstrap real config**

Run:

```bash
mkdir -p ~/.config/jkw-obs-mcp
cat > ~/.config/jkw-obs-mcp/config.toml <<'EOF'
[paths]
vault_root = "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs"

[machine]
id = "dreamingmachine"

[generation]
daily_review_enabled = false
EOF
```

- [ ] **Step 2: Confirm jkw-obs-mcp launches without errors**

Run: `jkw-obs-mcp` (with venv activated)
Expected: process hangs waiting for stdio input (this is correct — MCP servers wait for the client). Press Ctrl+C to exit.

- [ ] **Step 3: Wire into Claude Code**

Add to `~/.claude/mcp_servers.json`:

```json
{
  "mcpServers": {
    "jkw-obs": {
      "command": "/Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp/.venv/bin/jkw-obs-mcp"
    }
  }
}
```

(Adjust path if venv lives elsewhere.)

- [ ] **Step 4: Restart Claude Code, verify tools appear**

In a Claude Code session, type `/mcp`. Confirm `jkw-obs` is listed with three tools: `read_note`, `list_notes`, `write_kb_note`.

- [ ] **Step 5: Exercise read_note**

Ask Claude: "Use the jkw-obs MCP server to read Admin/Saiyan.md and tell me how many sets of pull-ups I did this week."

Expected: Claude calls `read_note`, gets the file, summarizes.

- [ ] **Step 6: Exercise write_kb_note**

Ask Claude: "Use jkw-obs to write a test note to kb/dreamingmachine/ad-hoc/plan-1-smoke.md with the content '# Plan 1 smoke test\n\nIt works.'"

Expected: file appears at `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs/kb/dreamingmachine/ad-hoc/plan-1-smoke.md`. Open it in Obsidian to confirm.

- [ ] **Step 7: Exercise sandbox enforcement (negative case)**

Ask Claude: "Use write_kb_note to write to filename '../../../etc/evil.md'."

Expected: tool call fails with a SandboxViolationError surfaced in the response. Nothing written outside `kb/dreamingmachine/`.

- [ ] **Step 8: Commit any final tweaks + tag the milestone**

```bash
# If you adjusted README paths or anything during testing, commit those.
git add -u && git commit -m "docs: tighten README install steps after smoke test" || echo "no changes to commit"
git tag plan-1-complete
git push origin main --tags
```

---

## Self-Review Checklist (run before declaring Plan 1 done)

- [ ] All 14 tasks committed (16+ commits including TDD per task)
- [ ] `pytest -v` passes — all unit tests green
- [ ] `jkw-obs-mcp` runs without errors when config is present
- [ ] Claude Code can call all three tools and they behave correctly
- [ ] Sandbox violations are caught (negative test in Step 7)
- [ ] README is accurate to what shipped
- [ ] No `TODO`, `FIXME`, or placeholder strings left in code or plan
- [ ] `git tag plan-1-complete` exists; pushed to origin

When all boxes ticked, Plan 1 is done. Move to Plan 2 (Embeddings indexer + semantic search).

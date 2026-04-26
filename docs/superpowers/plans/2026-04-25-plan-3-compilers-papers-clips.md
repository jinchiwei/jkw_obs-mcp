# Plan 3: Compilers Framework + Tier 1 (Papers, Clips)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Karpathy-style raw → compile → kb pattern for papers and web clips. Drop a PDF text extract into `raw/papers/`, drop a Web-Clipper article into `raw/clips/`, run `compile_raw` — Claude server-side generates structured summaries into `kb/<machine>/papers/<slug>.md` and `kb/<machine>/clips/<slug>.md` with backlinks to source.

**Architecture:** Three internal modules under `src/jkw_obs_mcp/`. **`generation/anthropic_client.py`** wraps the Anthropic API for server-side prompt calls. **`compilers/base.py`** abstract Compiler with sha256-based dedup contract. **`compilers/papers.py`** + **`compilers/clips.py`** are concrete implementations. `compile_raw` MCP tool walks raw/, dispatches to the right compiler per type, writes outputs into machine-scoped kb/ subfolders. `compile-state.json` tracks `{raw_path: {sha256, compiled_at, kb_outputs[]}}`.

**Tech Stack:** `anthropic` Python SDK (server-side prompt calls), `pymupdf` (PDF extraction for the ingest helper), `jinja2` (prompt templates). Plus a small CLI helper `tools/pdf_to_raw.py` for the user-side PDF→markdown step.

**Realistic effort: ~1.5 weeks** (9 tasks, includes API key setup + real LLM calls + PDF parsing edge cases).

---

## File Structure

```
jkw_obs-mcp/
├── pyproject.toml                              Modify: add anthropic, pymupdf, jinja2
├── tools/
│   └── pdf_to_raw.py                           CLI: PDF → raw/papers/<slug>.md
├── src/jkw_obs_mcp/
│   ├── config.py                               Modify: add GenerationConfig
│   ├── generation/
│   │   ├── __init__.py                         Empty
│   │   ├── anthropic_client.py                 AnthropicClient(api_key, model).complete(prompt)
│   │   └── prompts/
│   │       ├── paper_summary.j2                Jinja2 template for paper compilation
│   │       └── clip_summary.j2                 Jinja2 template for clip compilation
│   ├── compilers/
│   │   ├── __init__.py                         Empty
│   │   ├── base.py                             Compiler protocol + CompileState + CompileStats
│   │   ├── papers.py                           PaperCompiler
│   │   └── clips.py                            ClipCompiler
│   └── mcp/server.py                           Modify: add compile_raw tool + wire compilers in main()
└── tests/
    ├── test_compile_state.py                   Stale-detection contract
    ├── test_compiler_papers.py                 Uses MockAnthropicClient
    ├── test_compiler_clips.py                  Uses MockAnthropicClient
    └── test_mcp_compile_tool.py                MCP tool registration + dispatch
```

---

## Task 1: Deps + GenerationConfig

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/jkw_obs_mcp/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Update `pyproject.toml` dependencies**

```toml
dependencies = [
    "mcp>=1.0.0",
    "fastembed>=0.4.0",
    "sqlite-vec>=0.1.6",
    "anthropic>=0.40.0",
    "pymupdf>=1.24.0",
    "jinja2>=3.1.0",
]
```

- [ ] **Step 2: Re-install in deepdream env**

`source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp && pip install -e ".[dev]"`

Then smoke import: `python -c 'import anthropic, pymupdf, jinja2; print("ok")'`

- [ ] **Step 3: Failing test — append to `tests/test_config.py`**

```python
def test_load_config_includes_generation_section(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[paths]
vault_root = "/some/vault"

[machine]
id = "dreamingmachine"

[generation]
model = "claude-opus-4-7"
"""
    )

    cfg = load_config(cfg_file)

    assert cfg.generation.model == "claude-opus-4-7"


def test_load_config_uses_generation_defaults_when_section_absent(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[paths]
vault_root = "/some/vault"

[machine]
id = "dreamingmachine"
"""
    )

    cfg = load_config(cfg_file)

    # Default model is current production-ready Claude
    assert cfg.generation.model == "claude-opus-4-7"
    # daily_review_enabled stays at the existing default
    assert cfg.generation.daily_review_enabled is False
```

- [ ] **Step 4: Update `src/jkw_obs_mcp/config.py`**

Add a `GenerationConfig` dataclass and migrate `daily_review_enabled` into it:

```python
@dataclass(frozen=True)
class GenerationConfig:
    """Server-side LLM generation settings."""

    model: str = "claude-opus-4-7"
    daily_review_enabled: bool = False
```

Modify `Config`:
```python
@dataclass(frozen=True)
class Config:
    """Per-machine configuration loaded from config.toml."""

    vault_root: Path
    machine_id: str
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    # KEPT for backward compat with existing callers — points to generation.daily_review_enabled
    daily_review_enabled: bool = False
```

In `load_config`, populate `generation` from `data.get("generation", {})`:
```python
gen = data.get("generation", {})
generation = GenerationConfig(
    model=gen.get("model", "claude-opus-4-7"),
    daily_review_enabled=gen.get("daily_review_enabled", False),
)
```

And keep `daily_review_enabled` mirroring `generation.daily_review_enabled` so Plan 1's Config consumers don't break.

- [ ] **Step 5: Run — pass**

`pytest tests/ -v` → expect 51 tests pass (49 + 2 new).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/jkw_obs_mcp/config.py tests/test_config.py
git commit -m "feat: add anthropic+pymupdf+jinja2 deps + GenerationConfig schema"
```

---

## Task 2: AnthropicClient wrapper

**Files:**
- Create: `src/jkw_obs_mcp/generation/__init__.py`
- Create: `src/jkw_obs_mcp/generation/anthropic_client.py`
- Create: `tests/test_anthropic_client.py`

- [ ] **Step 1: Empty package init**

`src/jkw_obs_mcp/generation/__init__.py` (empty file).

- [ ] **Step 2: Failing test at `tests/test_anthropic_client.py`**

```python
"""Tests for the Anthropic client wrapper. Uses a fake client so we don't
make real API calls during the test suite."""

import pytest

from jkw_obs_mcp.generation.anthropic_client import AnthropicClient


class FakeAnthropic:
    """Stand-in for anthropic.Anthropic — captures calls and returns canned text."""

    def __init__(self, response_text: str = "stub response") -> None:
        self.response_text = response_text
        self.calls: list[dict] = []
        self.messages = self  # so client.client.messages.create works

    def create(self, **kwargs):
        self.calls.append(kwargs)
        # Mimic the real API response shape minimally.
        from types import SimpleNamespace
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.response_text)]
        )


def test_complete_passes_prompt_and_model_through():
    fake = FakeAnthropic(response_text="hello back")
    client = AnthropicClient(api_key="sk-fake", model="claude-opus-4-7", _client=fake)

    out = client.complete(prompt="hello world", system="be terse")

    assert out == "hello back"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == "claude-opus-4-7"
    assert call["system"] == "be terse"
    assert call["messages"] == [{"role": "user", "content": "hello world"}]


def test_complete_uses_default_max_tokens():
    fake = FakeAnthropic()
    client = AnthropicClient(api_key="sk-fake", model="claude-opus-4-7", _client=fake)

    client.complete(prompt="x", system="y")

    assert fake.calls[0]["max_tokens"] >= 1024


def test_init_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    fake = FakeAnthropic()
    client = AnthropicClient(model="claude-opus-4-7", _client=fake)
    assert client.api_key == "sk-from-env"


def test_init_raises_on_missing_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicClient(model="claude-opus-4-7")
```

- [ ] **Step 3: Run — fail (ImportError)**

- [ ] **Step 4: Write `src/jkw_obs_mcp/generation/anthropic_client.py`**

```python
"""Thin wrapper around the Anthropic Python SDK for server-side completions."""

from __future__ import annotations

import os
from typing import Any

import anthropic


_DEFAULT_MAX_TOKENS = 4096


class AnthropicClient:
    """Synchronous wrapper. Single entry point: complete(prompt, system)."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        _client: Any = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Export it in the shell that "
                "launches jkw-obs-mcp, e.g. via .env loaded by your shell."
            )
        self.api_key = api_key
        self.model = model
        # Allow tests to inject a fake. In production, build the real client.
        if _client is not None:
            self.client = _client
        else:
            self.client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        *,
        prompt: str,
        system: str = "",
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> str:
        """Run a single user-message completion. Returns the assistant text."""
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        # Concatenate all text blocks (usually 1).
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
```

- [ ] **Step 5: Run — pass (4 tests)**

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/generation/__init__.py src/jkw_obs_mcp/generation/anthropic_client.py tests/test_anthropic_client.py
git commit -m "feat: AnthropicClient wrapper with env-based API key + injectable client for tests"
```

---

## Task 3: CompileState — sha256-based dedup tracking

**Files:**
- Create: `src/jkw_obs_mcp/compilers/__init__.py`
- Create: `src/jkw_obs_mcp/compilers/base.py` (CompileState + CompileStats only; Compiler protocol in Task 4)
- Create: `tests/test_compile_state.py`

- [ ] **Step 1: Empty package init**

- [ ] **Step 2: Failing tests at `tests/test_compile_state.py`**

```python
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
```

- [ ] **Step 3: Run — fail (ImportError)**

- [ ] **Step 4: Write `src/jkw_obs_mcp/compilers/base.py` (state portion)**

```python
"""Compilers framework: dedup state + stats + Compiler protocol.

The Compiler protocol itself lands in the Step 4 update (Task 4 of this plan).
This file currently only contains CompileState + CompileStats so Task 3's tests
pass independently.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CompileEntry:
    """One raw → kb mapping recorded in compile-state.json."""

    sha256: str
    compiled_at: str
    kb_outputs: list[str]


@dataclass(frozen=True)
class CompileStats:
    """Counts from a single compile_raw pass, by type."""

    type_name: str
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return (
            f"{self.type_name}: added={self.added} updated={self.updated} "
            f"unchanged={self.unchanged} failed={self.failed}"
        )


@dataclass
class CompileState:
    """Persistent dedup state for the raw → compile → kb pipeline."""

    entries: dict[str, CompileEntry] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "CompileState":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text())
        return cls(
            entries={
                k: CompileEntry(**v) for k, v in raw.items()
            }
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    k: {
                        "sha256": v.sha256,
                        "compiled_at": v.compiled_at,
                        "kb_outputs": v.kb_outputs,
                    }
                    for k, v in self.entries.items()
                },
                indent=2,
            )
        )

    def is_stale(self, raw_path: str, current_sha256: str) -> bool:
        """True if the raw file needs (re)compilation."""
        entry = self.entries.get(raw_path)
        if entry is None:
            return True
        return entry.sha256 != current_sha256

    def record(self, raw_path: str, sha256: str, kb_outputs: list[str]) -> None:
        self.entries[raw_path] = CompileEntry(
            sha256=sha256,
            compiled_at=dt.datetime.now(dt.UTC).isoformat(),
            kb_outputs=list(kb_outputs),
        )
```

- [ ] **Step 5: Run — pass (6 tests)**

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/compilers/__init__.py src/jkw_obs_mcp/compilers/base.py tests/test_compile_state.py
git commit -m "feat: CompileState + CompileStats — sha256-based dedup tracking for raw → kb"
```

---

## Task 4: Compiler protocol

**Files:**
- Modify: `src/jkw_obs_mcp/compilers/base.py`

- [ ] **Step 1: Add Compiler protocol to `base.py`**

Append:

```python
from typing import Protocol


class Compiler(Protocol):
    """Compilers translate one raw/<type>/ tree into kb/<machine>/<type>/ outputs.

    Implementations must:
      - Define `type_name` (e.g. "papers", "clips") for stats + log lines
      - Define `raw_subdir` (e.g. "papers") and `kb_subdir` (e.g. "papers")
      - Implement compile_one(raw_path, content) -> str (the markdown for kb)
    """

    type_name: str
    raw_subdir: str
    kb_subdir: str

    def compile_one(self, raw_path: str, content: str) -> str: ...
```

(No new test — Compiler is just the contract that papers.py + clips.py implement.)

- [ ] **Step 2: Add an orchestrator `compile_all()` helper**

Append to `base.py`:

```python
import hashlib
from collections.abc import Iterable
from pathlib import Path


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compile_all(
    *,
    compiler: Compiler,
    vault_root: Path,
    machine_id: str,
    state: CompileState,
    state_path: Path,
) -> CompileStats:
    """Walk vault/raw/<compiler.raw_subdir>/, compile new/changed entries.

    Writes compiled output to vault/kb/<machine_id>/<compiler.kb_subdir>/.
    Persists state after each successful compile.
    """
    raw_root = vault_root / "raw" / compiler.raw_subdir
    kb_root = vault_root / "kb" / machine_id / compiler.kb_subdir
    kb_root.mkdir(parents=True, exist_ok=True)

    if not raw_root.is_dir():
        return CompileStats(type_name=compiler.type_name)

    added = updated = unchanged = failed = 0

    for src in sorted(raw_root.rglob("*.md")):
        if not src.is_file():
            continue
        rel = f"raw/{compiler.raw_subdir}/{src.relative_to(raw_root).as_posix()}"
        content = src.read_text(encoding="utf-8")
        sha = _sha256_text(content)

        if not state.is_stale(rel, sha):
            unchanged += 1
            continue

        existed_before = rel in state.entries

        try:
            kb_content = compiler.compile_one(raw_path=rel, content=content)
        except Exception:  # noqa: BLE001 — per-file failure must not abort the whole pass
            failed += 1
            continue

        out_path = kb_root / src.relative_to(raw_root)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(kb_content, encoding="utf-8")

        kb_rel = f"kb/{machine_id}/{compiler.kb_subdir}/{src.relative_to(raw_root).as_posix()}"
        state.record(raw_path=rel, sha256=sha, kb_outputs=[kb_rel])
        state.save(state_path)

        if existed_before:
            updated += 1
        else:
            added += 1

    return CompileStats(
        type_name=compiler.type_name,
        added=added,
        updated=updated,
        unchanged=unchanged,
        failed=failed,
    )
```

- [ ] **Step 3: Run — full suite still green (no new tests)**

`pytest tests/ -v` should still report all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/jkw_obs_mcp/compilers/base.py
git commit -m "feat: Compiler protocol + compile_all() orchestrator with per-file dedup"
```

---

## Task 5: PaperCompiler

**Files:**
- Create: `src/jkw_obs_mcp/generation/prompts/paper_summary.j2`
- Create: `src/jkw_obs_mcp/compilers/papers.py`
- Create: `tests/test_compiler_papers.py`

- [ ] **Step 1: Write the Jinja prompt template**

`src/jkw_obs_mcp/generation/prompts/paper_summary.j2`:

```
You are a research note-taker. Compile the paper extract below into a structured Obsidian-friendly markdown summary suitable for a personal research vault.

Output requirements:
- Frontmatter block at the top with: source_path, compiled_at (ISO8601), type: paper
- Section: ## TL;DR — three bullets, sharpest possible.
- Section: ## Methods — what was done, in 3-5 bullets. Mention sample sizes and key statistical/ML methods if present.
- Section: ## Findings — quantitative results. Numbers > prose. Cite figures/tables if mentioned.
- Section: ## Why this matters — one paragraph connecting to the user's research interests (broadly: medical imaging, neuro-oncology, AI/ML methods, scientific software).
- Section: ## Open questions — 1-3 honest uncertainties or follow-up questions.
- Closing line: "Source: [[{{ raw_path }}]]" for backlinking.

Do not invent citations or numbers. If a section can't be written from the source content, say "Not described in source." instead of fabricating.

Source path: {{ raw_path }}
Source content:
---
{{ content }}
---
```

- [ ] **Step 2: Failing tests at `tests/test_compiler_papers.py`**

```python
"""PaperCompiler tests with a stub AnthropicClient."""

from pathlib import Path

import pytest

from jkw_obs_mcp.compilers.base import CompileState, compile_all
from jkw_obs_mcp.compilers.papers import PaperCompiler


class StubAnthropic:
    def __init__(self, response: str = "## TL;DR\n- stub") -> None:
        self.response = response
        self.last_prompt: str | None = None
        self.calls = 0

    def complete(self, *, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        self.last_prompt = prompt
        self.calls += 1
        return self.response


def test_paper_compiler_renders_template_with_content():
    stub = StubAnthropic()
    compiler = PaperCompiler(client=stub)

    output = compiler.compile_one(
        raw_path="raw/papers/foo.md",
        content="Title: Cool study\nAbstract: We did stuff.",
    )

    assert "## TL;DR" in output
    assert stub.last_prompt is not None
    # The prompt was rendered from the template with the inputs we passed
    assert "raw/papers/foo.md" in stub.last_prompt
    assert "Cool study" in stub.last_prompt


def test_paper_compiler_via_compile_all(tmp_path):
    """End-to-end: drop a file in raw/papers/, run compile_all, verify kb output."""
    vault = tmp_path / "vault"
    raw_dir = vault / "raw" / "papers"
    raw_dir.mkdir(parents=True)
    (raw_dir / "study.md").write_text("Title: A\nAbstract: B")

    stub = StubAnthropic(response="# Compiled\n\n## TL;DR\n- bullet")
    compiler = PaperCompiler(client=stub)
    state_path = tmp_path / "compile-state.json"
    state = CompileState.load(state_path)

    stats = compile_all(
        compiler=compiler,
        vault_root=vault,
        machine_id="dreamingmachine",
        state=state,
        state_path=state_path,
    )

    assert stats.added == 1
    assert stats.failed == 0
    out = vault / "kb" / "dreamingmachine" / "papers" / "study.md"
    assert out.read_text().startswith("# Compiled")


def test_paper_compiler_skips_unchanged(tmp_path):
    """Second pass with no changes should be a no-op."""
    vault = tmp_path / "vault"
    raw_dir = vault / "raw" / "papers"
    raw_dir.mkdir(parents=True)
    (raw_dir / "study.md").write_text("static content")

    stub = StubAnthropic()
    compiler = PaperCompiler(client=stub)
    state_path = tmp_path / "compile-state.json"

    # First pass: 1 added
    state = CompileState.load(state_path)
    s1 = compile_all(
        compiler=compiler, vault_root=vault, machine_id="m", state=state,
        state_path=state_path,
    )
    assert s1.added == 1

    # Second pass: should be unchanged (state file persisted between calls)
    state2 = CompileState.load(state_path)
    s2 = compile_all(
        compiler=compiler, vault_root=vault, machine_id="m", state=state2,
        state_path=state_path,
    )
    assert s2.added == 0
    assert s2.unchanged == 1
    # Stub should have only been called once total
    assert stub.calls == 1
```

- [ ] **Step 3: Run — fail (module missing)**

- [ ] **Step 4: Write `src/jkw_obs_mcp/compilers/papers.py`**

```python
"""Compile raw/papers/<slug>.md into kb/<machine>/papers/<slug>.md.

Uses Anthropic's API (via AnthropicClient) to summarize. Prompt template
lives in ../generation/prompts/paper_summary.j2.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Resolve the prompt template path relative to this file.
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "generation" / "prompts"
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
    keep_trailing_newline=True,
)


class PaperCompiler:
    """Compiler for raw/papers/. Uses an injectable client so tests can stub."""

    type_name = "papers"
    raw_subdir = "papers"
    kb_subdir = "papers"

    def __init__(self, client) -> None:
        self.client = client
        self._template = _env.get_template("paper_summary.j2")

    def compile_one(self, raw_path: str, content: str) -> str:
        prompt = self._template.render(raw_path=raw_path, content=content)
        return self.client.complete(prompt=prompt, system="You are a research note-taker.")
```

- [ ] **Step 5: Run — pass**

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/generation/prompts/paper_summary.j2 src/jkw_obs_mcp/compilers/papers.py tests/test_compiler_papers.py
git commit -m "feat: PaperCompiler — raw/papers/ → kb/<machine>/papers/ via Claude summary prompt"
```

---

## Task 6: ClipCompiler

**Files:**
- Create: `src/jkw_obs_mcp/generation/prompts/clip_summary.j2`
- Create: `src/jkw_obs_mcp/compilers/clips.py`
- Create: `tests/test_compiler_clips.py`

- [ ] **Step 1: Write the Jinja prompt template**

`src/jkw_obs_mcp/generation/prompts/clip_summary.j2`:

```
You are a research note-taker compiling web clips (saved by Obsidian Web Clipper) into a personal research vault.

Output requirements:
- Frontmatter block at the top with: source_path, source_url (extract from clip frontmatter if present), compiled_at (ISO8601), type: clip
- Section: ## TL;DR — 3-5 sentences capturing the article's argument
- Section: ## Key points — 5-8 bullets of substantive claims, methods, or evidence
- Section: ## Why this is in my vault — one paragraph connecting to my apparent research interests (medical imaging, neuro-oncology, AI/ML, scientific software, productivity tools). Be honest if the connection isn't obvious.
- Section: ## Quotable — 1-3 short verbatim quotes worth remembering, with quotation marks
- Closing line: "Source: [[{{ raw_path }}]]" for backlinking

If the article is paywalled / contains only a title or excerpt, say so explicitly and write what you can. Don't fabricate.

Source path: {{ raw_path }}
Source content:
---
{{ content }}
---
```

- [ ] **Step 2: Failing tests at `tests/test_compiler_clips.py`**

```python
"""ClipCompiler tests."""

from pathlib import Path

from jkw_obs_mcp.compilers.base import CompileState, compile_all
from jkw_obs_mcp.compilers.clips import ClipCompiler


class StubAnthropic:
    def __init__(self, response: str = "## TL;DR\nstub article summary") -> None:
        self.response = response

    def complete(self, *, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        return self.response


def test_clip_compiler_compiles_one(tmp_path):
    compiler = ClipCompiler(client=StubAnthropic("# Out\n\nbody"))

    out = compiler.compile_one(
        raw_path="raw/clips/article.md",
        content="---\nsource_url: https://example.com/article\n---\nArticle body.",
    )

    assert "# Out" in out


def test_clip_compiler_via_compile_all(tmp_path):
    vault = tmp_path / "vault"
    raw_dir = vault / "raw" / "clips"
    raw_dir.mkdir(parents=True)
    (raw_dir / "article.md").write_text(
        "---\nsource_url: https://example.com/article\n---\nArticle body."
    )

    compiler = ClipCompiler(client=StubAnthropic(response="# Clip\n\n## TL;DR\nx"))
    state_path = tmp_path / "compile-state.json"
    state = CompileState.load(state_path)

    stats = compile_all(
        compiler=compiler,
        vault_root=vault,
        machine_id="dreamingmachine",
        state=state,
        state_path=state_path,
    )

    assert stats.added == 1
    out = vault / "kb" / "dreamingmachine" / "clips" / "article.md"
    assert out.read_text().startswith("# Clip")
```

- [ ] **Step 3: Run — fail**

- [ ] **Step 4: Write `src/jkw_obs_mcp/compilers/clips.py`**

```python
"""Compile raw/clips/<slug>.md (Obsidian Web Clipper output) into
kb/<machine>/clips/<slug>.md."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "generation" / "prompts"
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
    keep_trailing_newline=True,
)


class ClipCompiler:
    """Compiler for raw/clips/."""

    type_name = "clips"
    raw_subdir = "clips"
    kb_subdir = "clips"

    def __init__(self, client) -> None:
        self.client = client
        self._template = _env.get_template("clip_summary.j2")

    def compile_one(self, raw_path: str, content: str) -> str:
        prompt = self._template.render(raw_path=raw_path, content=content)
        return self.client.complete(prompt=prompt, system="You are a research note-taker.")
```

- [ ] **Step 5: Run — pass**

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/generation/prompts/clip_summary.j2 src/jkw_obs_mcp/compilers/clips.py tests/test_compiler_clips.py
git commit -m "feat: ClipCompiler — raw/clips/ → kb/<machine>/clips/ via Claude summary prompt"
```

---

## Task 7: PDF ingest helper — `tools/pdf_to_raw.py`

**Files:**
- Create: `tools/pdf_to_raw.py`

- [ ] **Step 1: Write the helper**

```python
#!/usr/bin/env python3
"""Extract text from a PDF and write it to vault/raw/papers/<slug>.md.

Usage:
    python tools/pdf_to_raw.py path/to/paper.pdf [--vault VAULT_PATH] [--slug SLUG]

Requires `pymupdf` (installed via the package's dev deps).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, UTC
from pathlib import Path

import pymupdf  # type: ignore[import-untyped]


def _slugify(text: str, max_len: int = 60) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\-_ ]+", "", text)
    text = re.sub(r"\s+", "-", text).strip("-")
    return text[:max_len] or "untitled"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", type=Path, help="Path to the source PDF")
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path(
            os.path.expanduser(
                "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs"
            )
        ),
        help="Vault root (default: dreamingmachine's iCloud vault)",
    )
    parser.add_argument(
        "--slug",
        default=None,
        help="Output slug (default: derived from PDF filename)",
    )
    args = parser.parse_args()

    if not args.pdf_path.is_file():
        sys.exit(f"PDF not found: {args.pdf_path}")

    slug = args.slug or _slugify(args.pdf_path.stem)
    out_dir = args.vault / "raw" / "papers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.md"

    with pymupdf.open(args.pdf_path) as doc:
        pages = [page.get_text("text") for page in doc]
    text = "\n\n".join(pages).strip()

    frontmatter = (
        "---\n"
        f"source_pdf: {args.pdf_path}\n"
        f"slug: {slug}\n"
        f"ingested_at: {datetime.now(UTC).isoformat()}\n"
        "type: paper\n"
        "---\n\n"
    )
    out_path.write_text(frontmatter + text, encoding="utf-8")
    print(f"wrote {out_path} ({len(text)} chars from {len(pages)} pages)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make executable + smoke test**

```bash
chmod +x tools/pdf_to_raw.py
# Smoke: passing --help should not crash
python tools/pdf_to_raw.py --help
```

Expected: argparse help text prints, exit 0.

- [ ] **Step 3: Commit**

```bash
git add tools/pdf_to_raw.py
git commit -m "feat: tools/pdf_to_raw.py — CLI helper to extract PDF text into raw/papers/"
```

---

## Task 8: `compile_raw` MCP tool + main() wiring

**Files:**
- Modify: `src/jkw_obs_mcp/mcp/server.py`
- Create: `tests/test_mcp_compile_tool.py`

- [ ] **Step 1: Failing tests at `tests/test_mcp_compile_tool.py`**

```python
"""Tests for the compile_raw MCP tool."""

from pathlib import Path

import pytest

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.compilers.base import CompileState
from jkw_obs_mcp.compilers.clips import ClipCompiler
from jkw_obs_mcp.compilers.papers import PaperCompiler
from jkw_obs_mcp.mcp.server import dispatch_tool, tools_for_adapter


class StubAnthropic:
    def __init__(self, response: str = "# Compiled\n\n## TL;DR\nstub") -> None:
        self.response = response

    def complete(self, *, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        return self.response


@pytest.fixture
def adapter_with_compilers(tmp_vault, tmp_path):
    """Adapter with paper + clip compilers attached, and a vault that has
    raw/papers/foo.md and raw/clips/bar.md staged."""
    raw_papers = tmp_vault / "raw" / "papers"
    raw_papers.mkdir(parents=True)
    (raw_papers / "foo.md").write_text("Title: foo\nAbstract: x")

    raw_clips = tmp_vault / "raw" / "clips"
    raw_clips.mkdir(parents=True)
    (raw_clips / "bar.md").write_text("Article body about y")

    state_path = tmp_path / "compile-state.json"

    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    client = StubAnthropic()
    adapter.compilers = {
        "papers": PaperCompiler(client=client),
        "clips": ClipCompiler(client=client),
    }
    adapter.compile_state_path = state_path
    return adapter


def test_tool_surface_includes_compile_raw(adapter_with_compilers):
    tools = tools_for_adapter(adapter_with_compilers)
    names = {t.name for t in tools}
    assert "compile_raw" in names


@pytest.mark.asyncio
async def test_dispatch_compile_raw_all(adapter_with_compilers, tmp_vault):
    result = await dispatch_tool(
        adapter_with_compilers, "compile_raw", {"scope": "all"}
    )
    text = result[0].text
    assert "papers: added=1" in text
    assert "clips: added=1" in text

    assert (tmp_vault / "kb" / "dreamingmachine" / "papers" / "foo.md").is_file()
    assert (tmp_vault / "kb" / "dreamingmachine" / "clips" / "bar.md").is_file()


@pytest.mark.asyncio
async def test_dispatch_compile_raw_papers_only(adapter_with_compilers, tmp_vault):
    result = await dispatch_tool(
        adapter_with_compilers, "compile_raw", {"scope": "papers"}
    )
    text = result[0].text
    assert "papers: added=1" in text
    # Clips should NOT have been compiled
    assert not (tmp_vault / "kb" / "dreamingmachine" / "clips" / "bar.md").exists()
```

- [ ] **Step 2: Run — fail (`unknown tool: compile_raw`)**

- [ ] **Step 3: Add `compile_raw` Tool + dispatch branch in `server.py`**

In `tools_for_adapter`, append:

```python
        Tool(
            name="compile_raw",
            description="Compile raw/<type>/ files into kb/<machine>/<type>/ via "
            "server-side Claude prompts. Scope: 'all' (every type) or one of "
            "'papers', 'clips'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "default": "all",
                    },
                },
            },
        ),
```

In `dispatch_tool`, before the final `raise ValueError`:

```python
    if name == "compile_raw":
        from jkw_obs_mcp.compilers.base import CompileState, compile_all
        scope = arguments.get("scope", "all")
        state_path = adapter.compile_state_path
        state = CompileState.load(state_path)
        compilers = adapter.compilers
        if scope != "all":
            if scope not in compilers:
                raise ValueError(
                    f"unknown compile scope {scope!r}; available: {sorted(compilers)} or 'all'"
                )
            compilers = {scope: compilers[scope]}

        lines: list[str] = []
        for _key, compiler in compilers.items():
            stats = compile_all(
                compiler=compiler,
                vault_root=adapter.vault_root,
                machine_id=adapter.machine_id,
                state=state,
                state_path=state_path,
            )
            lines.append(str(stats))
        return [TextContent(type="text", text="\n".join(lines))]
```

- [ ] **Step 4: Wire compilers into `main()`**

Inside `main()`, after the Indexer attachment, add:

```python
    from jkw_obs_mcp.generation.anthropic_client import AnthropicClient
    from jkw_obs_mcp.compilers.papers import PaperCompiler
    from jkw_obs_mcp.compilers.clips import ClipCompiler

    anthropic_client = AnthropicClient(model=cfg.generation.model)
    adapter.compilers = {
        "papers": PaperCompiler(client=anthropic_client),
        "clips": ClipCompiler(client=anthropic_client),
    }
    # compile-state.json lives next to embeddings.db under data/
    adapter.compile_state_path = db_path.parent / "compile-state.json"
```

- [ ] **Step 5: Run — pass**

`pytest tests/ -v` → all tests pass (including the 3 new compile_raw tests).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/mcp/server.py tests/test_mcp_compile_tool.py
git commit -m "feat: compile_raw MCP tool + main() wires PaperCompiler + ClipCompiler"
```

---

## Task 9: Manual end-to-end smoke test on dreamingmachine

This task is non-TDD — exercises real Claude API calls against a real PDF.

**Prerequisite**: `ANTHROPIC_API_KEY` must be set in the shell that launches Claude Code (so the MCP server inherits it). Check: `echo $ANTHROPIC_API_KEY` in a fresh terminal. If empty, add to `~/.zshrc`:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Then restart Claude Code so the MCP server picks up the env var.

- [ ] **Step 1: Restart Claude Code** to pick up new tools (compile_raw) + the env var.

- [ ] **Step 2: Confirm tool registration**

In a Claude session, ask:
> List all tools jkw-obs exposes.

Expected: 7 tools — read_note, list_notes, write_kb_note, search_vault, find_similar, reindex, **compile_raw**.

- [ ] **Step 3: Ingest a real PDF**

Pick a real paper PDF you have. From the project root:
```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream
python tools/pdf_to_raw.py /path/to/some-paper.pdf
```

Expected: `wrote ~/Library/.../jkw_obs/raw/papers/<slug>.md (N chars from M pages)`.

- [ ] **Step 4: Compile the paper**

In Claude Code:
> Use jkw-obs `compile_raw` with scope `papers`.

Expected: `papers: added=1 updated=0 unchanged=0 failed=0`. Real Anthropic API call (costs ~$0.01-0.05 depending on paper length and model).

Open `~/Library/.../jkw_obs/kb/dreamingmachine/papers/<slug>.md` in Obsidian — you should see TL;DR, Methods, Findings, Why this matters, Open questions, plus a `Source: [[raw/papers/<slug>]]` backlink.

- [ ] **Step 5: Save a web article via Obsidian Web Clipper**

Open Web Clipper extension on a real article you've been meaning to read. Configure target folder = `raw/clips/` (one-time setup). Click Save.

A new file appears at `~/Library/.../jkw_obs/raw/clips/<title>.md`.

- [ ] **Step 6: Compile clips**

In Claude Code:
> Use jkw-obs `compile_raw` with scope `clips`.

Expected: `clips: added=1 updated=0 unchanged=0 failed=0`.

Inspect `kb/dreamingmachine/clips/<title>.md` — should have TL;DR / Key points / Why this is in my vault / Quotable / backlink.

- [ ] **Step 7: Search confirms the new compiled notes**

Ask Claude:
> Use jkw-obs `reindex` then `search_vault` for a topic from the paper.

Expected: the just-compiled `kb/dreamingmachine/papers/<slug>.md` ranks at the top.

- [ ] **Step 8: Re-run compile_raw with no changes — should be no-op**

> Use jkw-obs `compile_raw` with scope `all`.

Expected: `papers: added=0 updated=0 unchanged=N`, same for clips. No new API calls (cost = $0).

- [ ] **Step 9: Tag plan-3-complete**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git tag plan-3-complete
git push origin main --tags
```

---

## Self-Review Checklist (before declaring Plan 3 done)

- [ ] All 9 tasks committed
- [ ] `pytest -v` shows ~60+ tests passing
- [ ] One real paper compiled end-to-end (PDF → raw/papers/ → kb/papers/)
- [ ] One real web clip compiled (raw/clips/ → kb/clips/)
- [ ] Re-running compile_raw is a no-op (dedup works)
- [ ] Compiled notes appear in `search_vault` results after reindex
- [ ] `ANTHROPIC_API_KEY` documented in README install section
- [ ] `git tag plan-3-complete` pushed to origin

When all boxes ticked, Plan 3 is done. Plan 4 (calendar adapter + daily review generator) is next.

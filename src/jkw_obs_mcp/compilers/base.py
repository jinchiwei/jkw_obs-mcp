"""Compilers framework: dedup state + stats + Compiler protocol + orchestrator.

CompileState/CompileStats track sha256-based dedup for raw -> kb compilation.
The Compiler protocol is the contract that papers.py + clips.py implement.
compile_all() walks vault/raw/<type>/, dispatches to the compiler, and writes
outputs into vault/kb/<machine>/<type>/ while updating state.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class CompileEntry:
    """One raw -> kb mapping recorded in compile-state.json."""

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
    """Persistent dedup state for the raw -> compile -> kb pipeline."""

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

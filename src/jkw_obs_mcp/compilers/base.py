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

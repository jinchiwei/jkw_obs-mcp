"""record_learning core — slug, frontmatter, path, git ops, orchestrator.

This module implements the `record_learning` MCP tool's logic. Pure functions
at the bottom (slug, frontmatter, path resolution); orchestrator at top
composing them with subprocess git ops and an injectable indexer for reindex.

For testability, all I/O-bound helpers (git, indexer) accept injectable args.
The MCP layer wires real ones in.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jkw_obs_mcp.brain_sync.sync import ensure_brain_repo_fresh


def _slugify(title: str, max_len: int = 60) -> str:
    """kebab-case the title, strip non-[a-z0-9-], truncate at word boundary.

    Returns "" if nothing survives stripping (caller must validate).
    """
    s = title.lower()
    # Replace non-ASCII first (strip unicode entirely)
    s = s.encode("ascii", "ignore").decode("ascii")
    # Replace punctuation (anything that isn't alphanumeric, whitespace, or hyphen) with a space
    # so that e.g. "1.10.1" becomes "1 10 1" rather than "1101"
    s = re.sub(r"[^a-z0-9\s\-]", " ", s)
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
    Caller is responsible for sanitizing inputs: tag/applies_to values must
    not contain commas, and title/date/machine must not contain newlines
    (would break frontmatter structure). The orchestrator validates these.
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
    add = subprocess.run(
        ["git", "-C", str(vault_root), "add", str(file_path)],
        capture_output=True, text=True,
    )
    if add.returncode != 0:
        return False, f"git add failed: {(add.stderr or add.stdout).strip()}"

    commit = subprocess.run(
        ["git", "-C", str(vault_root), "commit", "-m", f"kb: {title}"],
        capture_output=True, text=True,
    )
    if commit.returncode != 0:
        # `git commit` writes "nothing to commit" to stdout, not stderr.
        return False, f"git commit failed: {(commit.stderr or commit.stdout).strip()}"

    push = subprocess.run(
        ["git", "-C", str(vault_root), "push"],
        capture_output=True, text=True,
    )
    if push.returncode == 0:
        return True, None

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


@dataclass(frozen=True)
class LearningResult:
    """Status returned from record_learning."""

    written: bool
    path: Path
    pushed: bool
    reason: str | None = None


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
    if category not in _VALID_CATEGORIES:
        raise ValueError(
            f"invalid category {category!r}; must be one of {sorted(_VALID_CATEGORIES)}"
        )
    if len(title) < 3:
        raise ValueError(f"title too short: {title!r}")
    if "\n" in title:
        raise ValueError("title must not contain newlines (would break frontmatter)")
    if len(content) < 50:
        raise ValueError("content must be at least 50 characters")

    slug = _slugify(title)
    if not slug:
        raise ValueError(f"title produces empty slug after normalization: {title!r}")

    today = dt.date.today().isoformat()

    ensure_brain_repo_fresh(vault_root, max_age_minutes=0)

    path = _resolve_path(
        vault_root=vault_root,
        machine_id=machine_id,
        category=category,
        date=today,
        slug=slug,
    )

    frontmatter = _render_frontmatter(
        title=title,
        date=today,
        machine=machine_id,
        tags=tags,
        applies_to=applies_to,
    )
    path.write_text(frontmatter + "\n" + content + ("\n" if not content.endswith("\n") else ""))

    pushed, reason = _commit_and_push(
        vault_root=vault_root, file_path=path, title=title
    )

    if indexer is not None:
        try:
            indexer.reindex(scope="incremental")
        except Exception as exc:
            print(f"reindex failed (non-fatal): {exc}", file=sys.stderr)

    return LearningResult(written=True, path=path, pushed=pushed, reason=reason)

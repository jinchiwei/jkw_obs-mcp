"""Walk <vault>/Tasks/ for open task lines, group by source file.

Mission Log.md in the user's vault is a Tasks-plugin dynamic query (renders
at view time in Obsidian); reading it raw shows only query syntax. The actual
open-task data lives as `- [ ]` lines across other Tasks/*.md files. This
loader extracts them, preserves Tasks-plugin formatting (priority emojis,
due dates, indentation for subtasks), and groups by file.
"""

from __future__ import annotations

import re
from pathlib import Path


_OPEN_TASK_RE = re.compile(r"^[ \t]*- \[ \] ")
_TASKS_SUBDIR = "Tasks"
_MISSION_LOG = "Mission Log.md"  # query view, not actual tasks — skip


def load_open_tasks(vault_root: Path) -> str | None:
    """Return markdown listing all `- [ ]` lines under <vault>/Tasks/.

    Skips Mission Log.md (it's just Tasks-plugin queries). Returns None if
    Tasks/ doesn't exist or no open tasks are found.
    """
    tasks_dir = vault_root / _TASKS_SUBDIR
    if not tasks_dir.is_dir():
        return None

    sections: list[str] = []
    for md_path in sorted(tasks_dir.rglob("*.md")):
        if not md_path.is_file() or md_path.name == _MISSION_LOG:
            continue
        open_lines = [
            line.rstrip()
            for line in md_path.read_text(encoding="utf-8").splitlines()
            if _OPEN_TASK_RE.match(line)
        ]
        if open_lines:
            rel = md_path.relative_to(vault_root).as_posix()
            sections.append(f"### {rel}\n" + "\n".join(open_lines))

    if not sections:
        return None
    return "\n\n".join(sections)

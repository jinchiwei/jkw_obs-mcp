# Plan 4: Calendar Adapter + Daily Review Generator

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** A morning routine. At 8am every day on dreamingmachine, launchd triggers a generator that synthesizes (a) today's calendar, (b) yesterday's autofeeder digests, (c) vault deltas since the last review, (d) ad-hoc kb writes from the last 24h, into a structured daily-review note at `kb/dreamingmachine/daily/<YYYY-MM-DD>.md`. Lid was closed at 8am? launchd's catch-up fires it on next wake.

**Architecture:** `CalendarAdapter` wraps `icalBuddy` (Mac-only, no-op fallback on Linux). `AutofeederContext` loader reads recent `vault/臥龍/Autofeeder/<profile>/<date>.md`. `VaultDeltaContext` walks vault for `.md` files modified since the last daily-review timestamp (stored in `data/last-daily-review.json`). `DailyReviewGenerator` composes them, renders a Jinja prompt, calls Anthropic, writes the note. Exposed as MCP tool `generate_daily_review`. launchd plist template lands in `services/launchd/`; full installer is deferred to Plan 6.

**Tech Stack:** existing deps (anthropic[bedrock], jinja2). Plus `subprocess` to call icalBuddy. No new pip installs.

**Realistic effort: ~1 week** (8 tasks).

---

## File Structure

```
jkw_obs-mcp/
├── src/jkw_obs_mcp/
│   ├── adapter/
│   │   └── calendar.py                       icalBuddy wrapper
│   ├── context/
│   │   ├── __init__.py                        Empty
│   │   ├── autofeeder.py                     load recent autofeeder digest texts
│   │   └── vault_delta.py                    files modified since last_run_at
│   ├── generators/
│   │   ├── __init__.py                        Empty
│   │   └── daily_review.py                   DailyReviewGenerator + state file mgmt
│   ├── generation/prompts/
│   │   └── daily_review.j2                   Jinja template with all 4 input sections
│   └── mcp/server.py                          Modify: register generate_daily_review tool
├── services/
│   └── launchd/
│       └── com.jinchiwei.jkw-obs-mcp.daily-review.plist   Template; Plan 6 installer copies
└── tests/
    ├── test_calendar.py                       icalBuddy wrapper (mocked subprocess)
    ├── test_context_autofeeder.py
    ├── test_context_vault_delta.py
    ├── test_generator_daily_review.py
    └── test_mcp_daily_review_tool.py
```

---

## Task 1: CalendarAdapter — icalBuddy wrapper

**Files:** Create `src/jkw_obs_mcp/adapter/calendar.py`, `tests/test_calendar.py`.

- [ ] **Step 1: Failing tests at `tests/test_calendar.py`**

```python
"""CalendarAdapter tests using mocked subprocess.run."""

from unittest.mock import patch, MagicMock

import pytest

from jkw_obs_mcp.adapter.calendar import CalendarAdapter, CalendarEvent


def test_returns_empty_list_on_linux():
    """No icalBuddy on Linux — returns [] without crashing."""
    adapter = CalendarAdapter(_platform="linux")
    assert adapter.upcoming(days=7) == []


def test_parses_icalbuddy_output():
    """icalBuddy output is parsed into CalendarEvent objects."""
    fake_stdout = (
        "Standup|||Mon 04/28\n"
        "    07:00 PM - 07:30 PM\n"
        "Lab Meeting|||Tue 04/29\n"
        "    10:00 AM - 11:30 AM\n"
    )

    adapter = CalendarAdapter(_platform="darwin", _ical_buddy_path="/fake/icalBuddy")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_stdout, stderr="")
        events = adapter.upcoming(days=7)

    assert len(events) == 2
    assert events[0].title == "Standup"
    assert "Mon 04/28" in events[0].when
    assert "07:00 PM" in events[0].when
    assert events[1].title == "Lab Meeting"


def test_returns_empty_when_icalbuddy_errors():
    """If icalBuddy exits nonzero (e.g. TCC denied), return [] not raise."""
    adapter = CalendarAdapter(_platform="darwin", _ical_buddy_path="/fake/icalBuddy")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="TCC denied")
        events = adapter.upcoming(days=7)

    assert events == []


def test_returns_empty_when_icalbuddy_missing():
    """If icalBuddy isn't installed at expected path, return []."""
    adapter = CalendarAdapter(_platform="darwin", _ical_buddy_path="/nonexistent")
    assert adapter.upcoming(days=7) == []
```

- [ ] **Step 2: Run — fail (ModuleNotFoundError)**

- [ ] **Step 3: Write `src/jkw_obs_mcp/adapter/calendar.py`**

```python
"""Calendar adapter — icalBuddy wrapper for Mac. No-op on Linux."""

from __future__ import annotations

import platform as _platform_mod
import subprocess
from dataclasses import dataclass
from pathlib import Path


_DEFAULT_ICALBUDDY = "/opt/homebrew/bin/icalBuddy"


@dataclass(frozen=True)
class CalendarEvent:
    """One calendar event flattened from icalBuddy output."""

    title: str
    when: str  # human-readable time string from icalBuddy


class CalendarAdapter:
    """Reads upcoming events from macOS Calendar.app via icalBuddy.

    On Linux (no icalBuddy), all methods return empty results.
    """

    def __init__(
        self,
        *,
        _platform: str | None = None,
        _ical_buddy_path: str = _DEFAULT_ICALBUDDY,
    ) -> None:
        self._platform = (_platform or _platform_mod.system()).lower()
        self._bin = _ical_buddy_path

    def upcoming(self, days: int = 7) -> list[CalendarEvent]:
        if self._platform != "darwin":
            return []
        if not Path(self._bin).is_file():
            return []

        try:
            result = subprocess.run(
                [
                    self._bin,
                    "-f", "-nc", "-nrd", "-npn",
                    "-b", "",
                    "-iep", "title,datetime",
                    "-po", "title,datetime",
                    "-df", "|||%a %m/%d",
                    "-tf", "%I:%M%p",
                    "-eed",
                    "-ec", "Birthdays,Reminders",
                    "eventsFrom:today",
                    "to:today+" + str(days),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        if result.returncode != 0:
            return []

        return _parse(result.stdout)


def _parse(text: str) -> list[CalendarEvent]:
    """Parse the |||-separated icalBuddy output into events.

    Format:
        Title|||Date
            HH:MM AM - HH:MM PM
    """
    events: list[CalendarEvent] = []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        if "|||" in line:
            title, _, date = line.partition("|||")
            time_str = ""
            if i + 1 < len(lines) and not "|||" in lines[i + 1]:
                time_str = lines[i + 1].strip()
                i += 2
            else:
                i += 1
            events.append(CalendarEvent(title=title.strip(), when=f"{date.strip()} {time_str}".strip()))
        else:
            i += 1
    return events
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/adapter/calendar.py tests/test_calendar.py
git commit -m "feat: CalendarAdapter — icalBuddy wrapper, no-op on Linux"
```

---

## Task 2: AutofeederContext loader

**Files:** Create `src/jkw_obs_mcp/context/__init__.py` (empty), `src/jkw_obs_mcp/context/autofeeder.py`, `tests/test_context_autofeeder.py`.

- [ ] **Step 1: Failing tests at `tests/test_context_autofeeder.py`**

```python
"""AutofeederContext tests."""

import datetime as dt
from pathlib import Path

import pytest

from jkw_obs_mcp.context.autofeeder import load_recent_autofeeder_digests


def test_returns_recent_digests(tmp_path):
    """Files matching <vault>/臥龍/Autofeeder/<profile>/<YYYY-MM-DD>.md are loaded."""
    vault = tmp_path / "vault"
    af_root = vault / "臥龍" / "Autofeeder"
    today_str = dt.date.today().isoformat()

    # One profile, one recent digest
    (af_root / "meningioma").mkdir(parents=True)
    (af_root / "meningioma" / f"{today_str}.md").write_text(
        "# meningioma 2026-04-25\n\n## TL;DR\n- key paper found"
    )

    # Old digest — should be skipped
    old_date = (dt.date.today() - dt.timedelta(days=10)).isoformat()
    (af_root / "alzheimers").mkdir(parents=True)
    (af_root / "alzheimers" / f"{old_date}.md").write_text("OLD content")

    digests = load_recent_autofeeder_digests(vault, days=2)

    assert len(digests) == 1
    assert digests[0].profile == "meningioma"
    assert "key paper found" in digests[0].content


def test_returns_empty_when_no_digests(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    assert load_recent_autofeeder_digests(vault, days=7) == []


def test_handles_missing_autofeeder_root(tmp_path):
    """Vault doesn't have 臥龍/Autofeeder yet — returns []."""
    vault = tmp_path / "vault"
    (vault / "Admin").mkdir(parents=True)
    assert load_recent_autofeeder_digests(vault, days=7) == []
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Write `src/jkw_obs_mcp/context/autofeeder.py`**

```python
"""Load recent autofeeder digest texts for daily-review context."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path


_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


@dataclass(frozen=True)
class AutofeederDigest:
    """One profile's digest for a specific date."""

    profile: str
    date: str
    content: str


def load_recent_autofeeder_digests(
    vault_root: Path, days: int = 7
) -> list[AutofeederDigest]:
    """Walk <vault>/臥龍/Autofeeder/<profile>/<YYYY-MM-DD>.md, return entries
    from the last `days` days."""
    af_root = vault_root / "臥龍" / "Autofeeder"
    if not af_root.is_dir():
        return []

    cutoff = dt.date.today() - dt.timedelta(days=days)
    digests: list[AutofeederDigest] = []

    for profile_dir in sorted(af_root.iterdir()):
        if not profile_dir.is_dir():
            continue
        for f in sorted(profile_dir.glob("*.md")):
            m = _DATE_RE.match(f.name)
            if not m:
                continue
            try:
                file_date = dt.date.fromisoformat(m.group(1))
            except ValueError:
                continue
            if file_date < cutoff:
                continue
            digests.append(
                AutofeederDigest(
                    profile=profile_dir.name,
                    date=m.group(1),
                    content=f.read_text(encoding="utf-8"),
                )
            )

    return digests
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/context/__init__.py src/jkw_obs_mcp/context/autofeeder.py tests/test_context_autofeeder.py
git commit -m "feat: load_recent_autofeeder_digests() reads vault/臥龍/Autofeeder/ digests"
```

---

## Task 3: VaultDeltaContext loader

**Files:** Create `src/jkw_obs_mcp/context/vault_delta.py`, `tests/test_context_vault_delta.py`.

- [ ] **Step 1: Failing tests**

```python
"""VaultDelta tests — files modified since a timestamp."""

import datetime as dt
import os
import time
from pathlib import Path

from jkw_obs_mcp.context.vault_delta import vault_delta_since


def test_returns_files_newer_than_cutoff(tmp_vault):
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(hours=24)
    deltas = vault_delta_since(tmp_vault, since=cutoff)

    paths = {d.rel_path for d in deltas}
    assert "Admin/Saiyan.md" in paths


def test_skips_files_older_than_cutoff(tmp_vault, tmp_path):
    """Backdate Admin/Saiyan.md by 30 days; should not appear."""
    saiyan = tmp_vault / "Admin" / "Saiyan.md"
    old_time = time.time() - 30 * 24 * 3600
    os.utime(saiyan, (old_time, old_time))

    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    deltas = vault_delta_since(tmp_vault, since=cutoff)

    paths = {d.rel_path for d in deltas}
    assert "Admin/Saiyan.md" not in paths


def test_skips_obsidian_and_trash(tmp_vault):
    """Same skip-dir convention as the indexer's walker."""
    (tmp_vault / ".obsidian").mkdir(exist_ok=True)
    (tmp_vault / ".obsidian" / "config.md").write_text("plugin config")
    (tmp_vault / ".trash").mkdir(exist_ok=True)
    (tmp_vault / ".trash" / "old.md").write_text("trashed")

    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(hours=24)
    deltas = vault_delta_since(tmp_vault, since=cutoff)

    paths = {d.rel_path for d in deltas}
    assert all(not p.startswith(".obsidian/") for p in paths)
    assert all(not p.startswith(".trash/") for p in paths)
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Write `src/jkw_obs_mcp/context/vault_delta.py`**

```python
"""List vault .md files modified since a given timestamp."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path


_SKIP_DIRS = frozenset({".obsidian", ".trash", ".git", ".direnv", ".venv", "node_modules"})


@dataclass(frozen=True)
class VaultDelta:
    """One vault file modified since the cutoff."""

    rel_path: str
    mtime: dt.datetime


def vault_delta_since(vault_root: Path, since: dt.datetime) -> list[VaultDelta]:
    """Return all vault .md files whose mtime is on/after `since`.

    Skips _SKIP_DIRS (matches indexer.walker's exclusions).
    """
    vault_root = vault_root.resolve()
    cutoff_ts = since.timestamp()
    results: list[VaultDelta] = []

    for path in sorted(vault_root.rglob("*.md")):
        if not path.is_file():
            continue
        rel = path.relative_to(vault_root)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        st = path.stat()
        if st.st_mtime < cutoff_ts:
            continue
        results.append(
            VaultDelta(
                rel_path=rel.as_posix(),
                mtime=dt.datetime.fromtimestamp(st.st_mtime, tz=dt.UTC),
            )
        )

    return results
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/context/vault_delta.py tests/test_context_vault_delta.py
git commit -m "feat: vault_delta_since() — list .md files modified since a cutoff"
```

---

## Task 4: Daily review prompt template

**Files:** Create `src/jkw_obs_mcp/generation/prompts/daily_review.j2`.

- [ ] **Step 1: Write template**

```
You are writing a personal daily-review note for {{ machine_id }} on {{ today }}.

Compose a structured Obsidian-friendly markdown note. Be concrete, prefer numbers/names/concrete artifacts over prose. Keep total length under ~600 words. Don't fabricate.

Required structure:

# Daily Review — {{ today }}

## Today's events
{% if events %}
- For each event in {{ events|length }} calendar items: bullet with title and time, e.g. "- 10:00 AM Lab Meeting"
{% else %}
- "No events on calendar."
{% endif %}

## Looming this week
- Pick the 3-5 most consequential upcoming events from the rest of {{ events|length }} (skip today's; focus on the next 7 days).
- Note any clear deadlines or deliverables you should start prepping for.

## Vault deltas (since last review)
{% if vault_deltas %}
- For each of the {{ vault_deltas|length }} modified .md files, write one bullet: "- `<path>` — one-line gloss of what changed if you can tell from the path/filename, otherwise just the path."
{% else %}
- "No vault content changed since last review."
{% endif %}

## Surfaced from autofeeder
{% if autofeeder_digests %}
- Pull the 3-5 most interesting items across the {{ autofeeder_digests|length }} recent digest(s) below. Lead with paper/article titles. Note score if available.
{% else %}
- "No recent autofeeder digests."
{% endif %}

## Open threads
- Surface 2-4 things that look unfinished from the inputs: half-written notes, papers you started but didn't finish summarizing, calendar prep that's still empty, recurring patterns. Be specific. Empty is a fine answer if nothing applies.

---

INPUTS

Machine: {{ machine_id }}
Today: {{ today }}
Last review: {{ last_review }}

Calendar (next 7 days, {{ events|length }} events):
{% for ev in events %}- {{ ev.title }} — {{ ev.when }}
{% endfor %}

Vault deltas ({{ vault_deltas|length }} files modified since last review):
{% for d in vault_deltas %}- {{ d.rel_path }} (mtime {{ d.mtime }})
{% endfor %}

Autofeeder digests (last 7 days):
{% for digest in autofeeder_digests %}
=== {{ digest.profile }} {{ digest.date }} ===
{{ digest.content }}

{% endfor %}
```

- [ ] **Step 2: Commit**

```bash
git add src/jkw_obs_mcp/generation/prompts/daily_review.j2
git commit -m "feat: daily review Jinja prompt template with structured sections"
```

---

## Task 5: DailyReviewGenerator

**Files:** Create `src/jkw_obs_mcp/generators/__init__.py` (empty), `src/jkw_obs_mcp/generators/daily_review.py`, `tests/test_generator_daily_review.py`.

- [ ] **Step 1: Failing tests**

```python
"""DailyReviewGenerator tests with stubbed inputs."""

import datetime as dt
from pathlib import Path

import pytest

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.generators.daily_review import DailyReviewGenerator


class StubAnthropic:
    def __init__(self, response: str = "# Daily Review — 2026-04-26\n\nstub") -> None:
        self.response = response
        self.last_prompt: str | None = None

    def complete(self, *, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        self.last_prompt = prompt
        return self.response


@pytest.fixture
def adapter_with_state(tmp_vault, tmp_path):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    adapter.daily_review_state_path = tmp_path / "last-daily-review.json"

    class StubCalendar:
        def upcoming(self, days=7):
            from jkw_obs_mcp.adapter.calendar import CalendarEvent
            return [CalendarEvent(title="Standup", when="Mon 04/28 09:00 AM")]

    adapter.calendar = StubCalendar()
    return adapter


def test_generate_writes_daily_note_to_kb(adapter_with_state, tmp_vault):
    client = StubAnthropic(response="# Daily Review — 2026-04-26\n\ngenerated")
    gen = DailyReviewGenerator(adapter=adapter_with_state, client=client)

    out_path = gen.generate()

    assert out_path.is_file()
    assert "kb/dreamingmachine/daily" in str(out_path)
    assert out_path.read_text().startswith("# Daily Review")


def test_generate_includes_calendar_in_prompt(adapter_with_state):
    client = StubAnthropic()
    gen = DailyReviewGenerator(adapter=adapter_with_state, client=client)

    gen.generate()

    assert "Standup" in client.last_prompt
    assert "Mon 04/28" in client.last_prompt


def test_generate_persists_last_review_timestamp(adapter_with_state):
    client = StubAnthropic()
    gen = DailyReviewGenerator(adapter=adapter_with_state, client=client)

    gen.generate()

    assert adapter_with_state.daily_review_state_path.is_file()
    content = adapter_with_state.daily_review_state_path.read_text()
    assert "last_run_at" in content


def test_second_generate_uses_persisted_timestamp(adapter_with_state):
    """The second run's prompt should mention the first run's timestamp as last_review."""
    client = StubAnthropic()
    gen = DailyReviewGenerator(adapter=adapter_with_state, client=client)

    gen.generate()
    first_ts = adapter_with_state.daily_review_state_path.read_text()

    gen.generate()
    second_prompt = client.last_prompt

    # The second prompt's "last_review" line should reference a timestamp,
    # not "(never)"
    assert "Last review:" in second_prompt
    assert "(never)" not in second_prompt
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Write `src/jkw_obs_mcp/generators/daily_review.py`**

```python
"""DailyReviewGenerator: morning digest combining calendar + vault deltas +
autofeeder + last-review state, written to kb/<machine>/daily/<YYYY-MM-DD>.md."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.context.autofeeder import load_recent_autofeeder_digests
from jkw_obs_mcp.context.vault_delta import vault_delta_since


_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "generation" / "prompts"
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
    keep_trailing_newline=True,
)


class DailyReviewGenerator:
    """Composes morning digest from calendar + vault deltas + autofeeder.

    Persists a tiny JSON state file with last_run_at so the next run only
    mentions deltas since the previous review (defaults to last 24h on first run).
    """

    def __init__(self, *, adapter: VaultAdapter, client) -> None:
        self.adapter = adapter
        self.client = client
        self._template = _env.get_template("daily_review.j2")

    def generate(self) -> Path:
        today = dt.date.today().isoformat()
        last_run = self._load_last_run()
        cutoff = last_run or (dt.datetime.now(dt.UTC) - dt.timedelta(hours=24))

        # Gather inputs
        events = self.adapter.calendar.upcoming(days=7) if hasattr(self.adapter, "calendar") else []
        deltas = vault_delta_since(self.adapter.vault_root, since=cutoff)
        digests = load_recent_autofeeder_digests(self.adapter.vault_root, days=2)

        # Render prompt
        prompt = self._template.render(
            machine_id=self.adapter.machine_id,
            today=today,
            last_review=last_run.isoformat() if last_run else "(never)",
            events=events,
            vault_deltas=deltas,
            autofeeder_digests=digests,
        )

        # Call Claude
        markdown = self.client.complete(
            prompt=prompt,
            system="You are a focused daily-review note-taker.",
        )

        # Write into kb/<machine>/daily/<YYYY-MM-DD>.md
        out_path = self.adapter.write_kb_note(
            filename=f"{today}.md",
            content=markdown,
            subdir="daily",
        )
        self._save_last_run(dt.datetime.now(dt.UTC))
        return out_path

    def _load_last_run(self) -> dt.datetime | None:
        path: Path = self.adapter.daily_review_state_path
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            ts = data.get("last_run_at")
            return dt.datetime.fromisoformat(ts) if ts else None
        except (json.JSONDecodeError, ValueError):
            return None

    def _save_last_run(self, when: dt.datetime) -> None:
        path: Path = self.adapter.daily_review_state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"last_run_at": when.isoformat()}, indent=2))
```

- [ ] **Step 4: Run — pass (4 tests)**

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/generators/__init__.py src/jkw_obs_mcp/generators/daily_review.py tests/test_generator_daily_review.py
git commit -m "feat: DailyReviewGenerator — composes calendar+deltas+autofeeder into kb/daily/"
```

---

## Task 6: `generate_daily_review` MCP tool

**Files:** Modify `src/jkw_obs_mcp/mcp/server.py`. Create `tests/test_mcp_daily_review_tool.py`.

- [ ] **Step 1: Failing tests**

```python
"""MCP tool registration + dispatch for generate_daily_review."""

import datetime as dt
from pathlib import Path

import pytest

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.adapter.calendar import CalendarAdapter
from jkw_obs_mcp.generators.daily_review import DailyReviewGenerator
from jkw_obs_mcp.mcp.server import dispatch_tool, tools_for_adapter


class StubAnthropic:
    def complete(self, *, prompt, system="", max_tokens=4096):
        return f"# Daily Review — {dt.date.today().isoformat()}\n\nstub"


@pytest.fixture
def adapter_with_daily_review(tmp_vault, tmp_path):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    adapter.calendar = CalendarAdapter(_platform="linux")  # no-op
    adapter.daily_review_state_path = tmp_path / "last-daily-review.json"
    adapter.daily_review_generator = DailyReviewGenerator(
        adapter=adapter, client=StubAnthropic()
    )
    return adapter


def test_tool_surface_includes_generate_daily_review(adapter_with_daily_review):
    tools = tools_for_adapter(adapter_with_daily_review)
    names = {t.name for t in tools}
    assert "generate_daily_review" in names


@pytest.mark.asyncio
async def test_dispatch_generate_daily_review_writes_note(
    adapter_with_daily_review, tmp_vault
):
    result = await dispatch_tool(adapter_with_daily_review, "generate_daily_review", {})

    text = result[0].text
    today = dt.date.today().isoformat()
    expected = tmp_vault / "kb" / "dreamingmachine" / "daily" / f"{today}.md"
    assert expected.is_file()
    # Tool output mentions where it wrote
    assert str(expected) in text or "daily" in text
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Modify `tools_for_adapter` and `dispatch_tool` in server.py**

In `tools_for_adapter`, append:

```python
        Tool(
            name="generate_daily_review",
            description="Generate today's daily-review note: synthesizes "
            "calendar (Mac), vault deltas since last review, recent autofeeder "
            "digests, and ad-hoc kb writes. Writes to kb/<machine>/daily/<date>.md.",
            inputSchema={"type": "object", "properties": {}},
        ),
```

In `dispatch_tool`, before final raise:

```python
    if name == "generate_daily_review":
        # Lazy-build the generator on first call (needs Anthropic client).
        gen = getattr(adapter, "daily_review_generator", None)
        if gen is None:
            from jkw_obs_mcp.generation.anthropic_client import AnthropicClient
            from jkw_obs_mcp.generators.daily_review import DailyReviewGenerator
            client = AnthropicClient(model=adapter.anthropic_model)
            gen = DailyReviewGenerator(adapter=adapter, client=client)
            adapter.daily_review_generator = gen
        out_path = gen.generate()
        return [TextContent(type="text", text=f"wrote {out_path}")]
```

- [ ] **Step 4: Wire calendar + state path in `main()`**

Inside `main()`, after the compilers stub block, add:

```python
    # Calendar adapter (icalBuddy on Mac, no-op on Linux).
    from jkw_obs_mcp.adapter.calendar import CalendarAdapter
    adapter.calendar = CalendarAdapter()
    adapter.daily_review_state_path = db_path.parent / "last-daily-review.json"
    adapter.daily_review_generator = None  # lazy-built on first call
```

- [ ] **Step 5: Run — pass**

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/mcp/server.py tests/test_mcp_daily_review_tool.py
git commit -m "feat: generate_daily_review MCP tool + main() wires CalendarAdapter"
```

---

## Task 7: launchd plist template

**Files:** Create `services/launchd/com.jinchiwei.jkw-obs-mcp.daily-review.plist`.

- [ ] **Step 1: Write template** (no install yet — Plan 6 ships the installer)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.jinchiwei.jkw-obs-mcp.daily-review</string>

    <!-- Run "jkw-obs-mcp-daily-review" at 8am every morning. launchd's catch-up
         semantics fire it on next wake if the laptop was asleep at 8am. -->
    <key>ProgramArguments</key>
    <array>
        <string>/Users/jinchiwei/miniconda3/envs/deepdream/bin/jkw-obs-mcp-daily-review</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>8</integer>
        <key>Minute</key><integer>0</integer>
    </dict>

    <!-- Don't kick off a second instance if the previous one is still running -->
    <key>AbandonProcessGroup</key>
    <false/>

    <!-- Logs to ~/Library/Logs/jkw-obs-mcp-daily-review.log -->
    <key>StandardOutPath</key>
    <string>/Users/jinchiwei/Library/Logs/jkw-obs-mcp-daily-review.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/jinchiwei/Library/Logs/jkw-obs-mcp-daily-review.err</string>
</dict>
</plist>
```

- [ ] **Step 2: Commit**

```bash
mkdir -p services/launchd
git add services/launchd/com.jinchiwei.jkw-obs-mcp.daily-review.plist
git commit -m "feat: launchd plist template for the daily review job (installed by Plan 6)"
```

---

## Task 8: Manual end-to-end smoke test

This task is non-TDD — exercises the real Versa API and writes a real daily-review note.

- [ ] **Step 1: Restart Claude Code** to pick up the new tool.

- [ ] **Step 2: Verify tool surface**

> List all jkw-obs tools.

Expected: 8 tools (the previous 7 + `generate_daily_review`).

- [ ] **Step 3: Run the generator**

> Use jkw-obs `generate_daily_review`.

Expected: takes ~10-30 seconds (Versa Opus call). Output: `wrote /Users/jinchiwei/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs/kb/dreamingmachine/daily/<YYYY-MM-DD>.md`.

Open that file in Obsidian. Verify all five sections present (Today's events, Looming this week, Vault deltas, Surfaced from autofeeder, Open threads). Calendar events should match what your real Calendar.app shows for today.

If calendar section says "No events on calendar." but you have events: icalBuddy TCC permission may not be granted. Run `/opt/homebrew/bin/icalBuddy eventsToday` from the terminal directly — if it errors, accept the "Allow access to Calendar" prompt that should appear.

- [ ] **Step 4: Run again (idempotency check)**

> Use jkw-obs `generate_daily_review` again.

Expected: overwrites today's daily note with a fresh take. The "Vault deltas since last review" section should be SHORTER than the first run (since the first run set last_review to ~now).

- [ ] **Step 5: Tag and push**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git tag plan-4-complete
git push origin main --tags
```

---

## Self-Review

- [ ] All 8 tasks committed
- [ ] `pytest -v` shows full suite green (~80+ tests)
- [ ] Daily review note exists at `kb/dreamingmachine/daily/<today>.md` with five sections
- [ ] Calendar events match reality (TCC granted)
- [ ] launchd plist template exists at `services/launchd/`
- [ ] `git tag plan-4-complete` pushed

When all boxed ticked, Plan 4 done. Plan 5 (compilers Tier 2) or Plan 6 (installer for the launchd plist) next.

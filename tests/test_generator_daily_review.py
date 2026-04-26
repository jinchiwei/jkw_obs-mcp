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


def test_today_in_prompt_includes_weekday(adapter_with_state):
    """The prompt's `today` value includes weekday so the LLM can't guess wrong."""
    client = StubAnthropic()
    gen = DailyReviewGenerator(adapter=adapter_with_state, client=client)

    gen.generate()

    today_dt = dt.date.today()
    expected = today_dt.strftime("%a %Y-%m-%d")
    assert expected in client.last_prompt


def test_filename_uses_iso_date_only(adapter_with_state, tmp_vault):
    """Output file is `<YYYY-MM-DD>.md`, not `<weekday> <YYYY-MM-DD>.md`."""
    client = StubAnthropic()
    gen = DailyReviewGenerator(adapter=adapter_with_state, client=client)

    out_path = gen.generate()

    today_iso = dt.date.today().isoformat()
    assert out_path.name == f"{today_iso}.md"


def test_open_tasks_in_prompt_when_present(adapter_with_state, tmp_vault):
    """Open tasks under Tasks/*.md are fed into the prompt."""
    tasks = tmp_vault / "Tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "Inbox.md").write_text("- [ ] Buy groceries\n- [ ] Submit MCAT 🔺\n")

    client = StubAnthropic()
    gen = DailyReviewGenerator(adapter=adapter_with_state, client=client)

    gen.generate()

    assert "Buy groceries" in client.last_prompt
    assert "Submit MCAT 🔺" in client.last_prompt


def test_open_tasks_absent_renders_placeholder(adapter_with_state):
    """No Tasks/ dir → prompt has placeholder, no crash."""
    client = StubAnthropic()
    gen = DailyReviewGenerator(adapter=adapter_with_state, client=client)

    gen.generate()  # tmp_vault has no Tasks/ dir by default

    assert "no open tasks" in client.last_prompt.lower()

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

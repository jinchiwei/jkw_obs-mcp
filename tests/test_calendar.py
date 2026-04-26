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

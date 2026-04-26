"""CalendarAdapter tests with mocked EventKit."""

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest

from jkw_obs_mcp.adapter.calendar import CalendarAdapter, CalendarEvent


def test_returns_empty_list_on_linux():
    """No EventKit on Linux — returns [] without crashing."""
    adapter = CalendarAdapter(_platform="linux")
    assert adapter.upcoming(days=7) == []


def test_returns_empty_when_eventkit_unavailable(monkeypatch):
    """EventKit import fails (e.g. PyObjC not installed) — returns []."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "EventKit":
            raise ImportError("simulated missing PyObjC")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    adapter = CalendarAdapter(_platform="darwin")
    assert adapter.upcoming(days=7) == []


def _fake_event(title: str, dtobj: dt.datetime, all_day: bool = False) -> MagicMock:
    """Build a mock EKEvent matching the methods _to_calendar_event reads."""
    ek = MagicMock()
    ek.title.return_value = title

    # Mock the NSDate that startDate() returns
    ts = dtobj.timestamp()
    fake_nsdate = MagicMock()
    fake_nsdate.timeIntervalSince1970.return_value = ts
    ek.startDate.return_value = fake_nsdate

    ek.isAllDay.return_value = all_day
    return ek


def test_returns_empty_when_access_denied():
    """User denied Calendar permission — returns [] without raising."""
    fake_eventkit = MagicMock()
    fake_foundation = MagicMock()

    def fake_request(entity_type, cb):
        cb(False, None)  # denied

    fake_store = MagicMock()
    fake_store.requestAccessToEntityType_completion_.side_effect = fake_request
    fake_eventkit.EKEventStore.alloc.return_value.init.return_value = fake_store

    with patch.dict("sys.modules", {"EventKit": fake_eventkit, "Foundation": fake_foundation}):
        adapter = CalendarAdapter(_platform="darwin")
        events = adapter.upcoming(days=7)

    assert events == []


def test_returns_parsed_events_when_access_granted():
    """Granted access + 2 events → 2 CalendarEvent objects."""
    fake_eventkit = MagicMock()
    fake_foundation = MagicMock()

    def fake_request(entity_type, cb):
        cb(True, None)

    fake_events = [
        _fake_event("Standup", dt.datetime(2026, 4, 27, 19, 0, 0)),
        _fake_event("Lab Meeting", dt.datetime(2026, 4, 28, 10, 0, 0)),
    ]
    fake_store = MagicMock()
    fake_store.requestAccessToEntityType_completion_.side_effect = fake_request
    fake_store.eventsMatchingPredicate_.return_value = fake_events
    fake_eventkit.EKEventStore.alloc.return_value.init.return_value = fake_store

    with patch.dict("sys.modules", {"EventKit": fake_eventkit, "Foundation": fake_foundation}):
        adapter = CalendarAdapter(_platform="darwin")
        events = adapter.upcoming(days=7)

    assert len(events) == 2
    assert events[0].title == "Standup"
    assert "Mon 04/27" in events[0].when
    assert "7:00PM" in events[0].when
    assert events[1].title == "Lab Meeting"
    assert "Tue 04/28" in events[1].when


def test_all_day_event_is_marked_all_day():
    fake_eventkit = MagicMock()
    fake_foundation = MagicMock()

    def fake_request(entity_type, cb):
        cb(True, None)

    fake_store = MagicMock()
    fake_store.requestAccessToEntityType_completion_.side_effect = fake_request
    fake_store.eventsMatchingPredicate_.return_value = [
        _fake_event("Holiday", dt.datetime(2026, 5, 1, 0, 0, 0), all_day=True),
    ]
    fake_eventkit.EKEventStore.alloc.return_value.init.return_value = fake_store

    with patch.dict("sys.modules", {"EventKit": fake_eventkit, "Foundation": fake_foundation}):
        adapter = CalendarAdapter(_platform="darwin")
        events = adapter.upcoming(days=7)

    assert len(events) == 1
    assert "all day" in events[0].when

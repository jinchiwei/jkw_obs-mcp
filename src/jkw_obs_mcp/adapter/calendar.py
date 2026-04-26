"""Calendar adapter — PyObjC EventKit wrapper for macOS. No-op on Linux.

EventKit is Apple's modern Calendar API and natively expands recurring events,
inherits TCC permission from the parent process, and works from any terminal
or launchd job that has been granted Calendar access in System Settings.
"""

from __future__ import annotations

import platform as _platform_mod
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class CalendarEvent:
    """One calendar event flattened for the daily-review prompt."""

    title: str
    when: str  # human-readable string, e.g. "Mon 04/27 11:10AM"


class CalendarAdapter:
    """Reads upcoming events from macOS Calendar.app via PyObjC EventKit.

    On Linux (no Calendar.app, no PyObjC), all methods return empty results.
    """

    def __init__(self, *, _platform: str | None = None) -> None:
        self._platform = (_platform or _platform_mod.system()).lower()

    def upcoming(self, days: int = 7) -> list[CalendarEvent]:
        if self._platform != "darwin":
            return []

        try:
            import EventKit  # noqa: WPS433 — lazy import keeps Linux clean
            from Foundation import NSDate
        except ImportError:
            return []

        store = EventKit.EKEventStore.alloc().init()

        # Synchronously request Calendar access. If already granted, the callback
        # fires immediately. If denied, we get granted=False and bail.
        done = threading.Event()
        result: dict[str, object] = {"granted": False}

        def _cb(granted, _error):
            result["granted"] = bool(granted)
            done.set()

        store.requestAccessToEntityType_completion_(
            EventKit.EKEntityTypeEvent, _cb
        )
        if not done.wait(timeout=15):
            return []
        if not result["granted"]:
            return []

        start = NSDate.date()
        end = NSDate.dateWithTimeIntervalSinceNow_(days * 86400)
        predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
            start, end, None
        )
        ek_events = store.eventsMatchingPredicate_(predicate)

        return [_to_calendar_event(e) for e in ek_events]


def _to_calendar_event(ek_event) -> CalendarEvent:
    """Flatten an EKEvent into a (title, human-readable when) tuple.

    `when` follows the icalBuddy-style "Mon 04/27 11:10AM" so the daily-review
    prompt template can keep the same wording.
    """
    title = str(ek_event.title()) if ek_event.title() else "(untitled)"

    # ek_event.startDate() returns NSDate; format via strftime on a Python datetime.
    import datetime as dt
    nsdate = ek_event.startDate()
    # NSDate.timeIntervalSince1970() gives a UTC-anchored float
    ts = nsdate.timeIntervalSince1970()
    local = dt.datetime.fromtimestamp(ts)

    if ek_event.isAllDay():
        when = local.strftime("%a %m/%d all day")
    else:
        # Strip leading zero on the hour for human readability ("11:10AM" not "11:10 AM")
        time_str = local.strftime("%I:%M%p").lstrip("0")
        when = f"{local.strftime('%a %m/%d')} {time_str}"

    return CalendarEvent(title=title, when=when)

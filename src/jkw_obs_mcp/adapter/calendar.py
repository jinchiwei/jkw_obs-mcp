"""Calendar adapter — icalBuddy wrapper for Mac. No-op on Linux."""

from __future__ import annotations

import platform as _platform_mod
import subprocess
from dataclasses import dataclass
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

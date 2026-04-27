"""Pure-function thread state classifier for the email compiler.

States (single-valued, priority-ordered):
    WAITING_ON_YOU — multi-message thread, last message inbound (not replied to)
    FIRST_TOUCH    — single-message thread, message inbound (new conversation)
    RECENT_ACTIVITY — anything else: multi-message threads where you replied,
                      or threads with only outbound messages

The compiler renders threads grouped by state. WAITING_ON_YOU is highest signal.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum

from jkw_obs_mcp.adapter.gmail import EmailThread


class ThreadState(str, Enum):
    WAITING_ON_YOU = "waiting_on_you"
    FIRST_TOUCH = "first_touch"
    RECENT_ACTIVITY = "recent_activity"


def classify_thread_state(thread: EmailThread, *, now: dt.datetime) -> ThreadState:
    """Bucket a thread into a single state.

    `now` is injectable for tests. Production passes datetime.now(UTC).
    """
    if not thread.messages:
        return ThreadState.RECENT_ACTIVITY

    # Single-message thread, inbound → FIRST_TOUCH
    if len(thread.messages) == 1 and not thread.messages[0].is_from_self:
        return ThreadState.FIRST_TOUCH

    # Multi-message thread where the latest message is inbound → WAITING_ON_YOU
    last = thread.messages[-1]
    if not last.is_from_self:
        return ThreadState.WAITING_ON_YOU

    return ThreadState.RECENT_ACTIVITY

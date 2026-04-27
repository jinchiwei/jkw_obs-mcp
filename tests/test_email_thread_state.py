"""Thread-state classifier tests."""

from __future__ import annotations

import datetime as dt

from jkw_obs_mcp.adapter.gmail import EmailMessage, EmailThread
from jkw_obs_mcp.compilers.email_state import ThreadState, classify_thread_state


def _msg(sender: str, is_from_self: bool, when: dt.datetime, body: str = "hi") -> EmailMessage:
    return EmailMessage(
        message_id=f"m-{when.timestamp()}",
        sender=sender,
        recipient="me@example.com",
        subject="(test)",
        date=when.strftime("%a, %d %b %Y %H:%M:%S +0000"),
        body=body,
        is_from_self=is_from_self,
    )


def _thread(messages: list[EmailMessage]) -> EmailThread:
    return EmailThread(thread_id="t", subject="(test)", messages=messages)


NOW = dt.datetime(2026, 4, 27, 12, 0, 0, tzinfo=dt.UTC)
DAY_AGO = NOW - dt.timedelta(days=1)
WEEK_AGO = NOW - dt.timedelta(days=7)


def test_waiting_on_you_when_last_msg_is_inbound():
    """Thread ends with a message from someone else → WAITING_ON_YOU."""
    thread = _thread([
        _msg("me@example.com", True, WEEK_AGO),
        _msg("alice@example.com", False, DAY_AGO),
    ])
    assert classify_thread_state(thread, now=NOW) == ThreadState.WAITING_ON_YOU


def test_first_touch_when_single_inbound_message_in_window():
    """Brand new thread, single message from outside, recent → FIRST_TOUCH."""
    thread = _thread([
        _msg("alice@example.com", False, DAY_AGO),
    ])
    assert classify_thread_state(thread, now=NOW) == ThreadState.FIRST_TOUCH


def test_recent_activity_when_you_replied_last_but_thread_has_new_inbound():
    """Multi-message thread with new inbound + your reply on top → still RECENT_ACTIVITY.

    (You handled it; nothing pending.)
    """
    thread = _thread([
        _msg("alice@example.com", False, WEEK_AGO),
        _msg("alice@example.com", False, DAY_AGO),
        _msg("me@example.com", True, NOW - dt.timedelta(hours=1)),
    ])
    assert classify_thread_state(thread, now=NOW) == ThreadState.RECENT_ACTIVITY


def test_first_touch_takes_priority_over_recent_activity():
    """Single-message thread that you DID reply to is still RECENT_ACTIVITY (multi-msg).

    But a single inbound message you haven't replied to yet is FIRST_TOUCH.
    """
    thread = _thread([
        _msg("alice@example.com", False, DAY_AGO),
    ])
    # Single inbound, no reply → FIRST_TOUCH (which also implies WAITING_ON_YOU
    # semantics, but the more specific FIRST_TOUCH takes priority)
    assert classify_thread_state(thread, now=NOW) == ThreadState.FIRST_TOUCH


def test_returns_recent_activity_for_multi_message_thread_you_replied_to():
    thread = _thread([
        _msg("alice@example.com", False, WEEK_AGO),
        _msg("me@example.com", True, DAY_AGO),
    ])
    assert classify_thread_state(thread, now=NOW) == ThreadState.RECENT_ACTIVITY


def test_handles_thread_with_only_outbound_messages():
    """Edge case: a thread with only your messages (you wrote, no reply yet)."""
    thread = _thread([
        _msg("me@example.com", True, DAY_AGO),
    ])
    assert classify_thread_state(thread, now=NOW) == ThreadState.RECENT_ACTIVITY

"""EmailCompiler tests with stubbed Gmail + Anthropic."""

from __future__ import annotations

import datetime as dt

import pytest

from jkw_obs_mcp.adapter.gmail import EmailMessage, EmailThread
from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.compilers.email_compiler import EmailCompiler


def _msg(sender: str, is_self: bool, body: str = "hi") -> EmailMessage:
    return EmailMessage(
        message_id=f"m-{sender}-{int(is_self)}",
        sender=sender,
        recipient="me@example.com",
        subject="Hi",
        date="Mon, 27 Apr 2026 09:00:00 +0000",
        body=body,
        is_from_self=is_self,
    )


def _thread(thread_id: str, subject: str, msgs: list[EmailMessage]) -> EmailThread:
    return EmailThread(thread_id=thread_id, subject=subject, messages=msgs)


class StubAnthropic:
    def __init__(self, response: str = "# Email Pulse — 2026-04-27\n\nstub") -> None:
        self.response = response
        self.last_prompt: str | None = None

    def complete(self, *, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        self.last_prompt = prompt
        return self.response


class StubGmail:
    def __init__(self, threads: list[EmailThread]) -> None:
        self.threads = threads
        self.last_query: str | None = None

    def fetch_recent_threads(self, *, query: str, max_threads: int = 50) -> list[EmailThread]:
        self.last_query = query
        return self.threads


@pytest.fixture
def adapter(tmp_vault):
    return VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")


def test_compile_writes_to_kb_email_subdir(adapter, tmp_vault):
    threads = [
        _thread("t1", "Hello", [
            _msg("alice@example.com", False),
            _msg("alice@example.com", False),
        ]),
    ]
    compiler = EmailCompiler(
        gmail=StubGmail(threads),
        client=StubAnthropic("# Email Pulse — 2026-04-27\n\ngenerated"),
        vault_adapter=adapter,
    )

    out_path = compiler.compile()

    assert out_path is not None
    assert out_path.is_file()
    assert "kb/dreamingmachine/email" in str(out_path)
    assert out_path.read_text().startswith("# Email Pulse")


def test_compile_returns_none_when_no_threads(adapter):
    """Empty inbox → no file written, returns None (signals 'no email today')."""
    compiler = EmailCompiler(
        gmail=StubGmail([]),
        client=StubAnthropic(),
        vault_adapter=adapter,
    )
    out_path = compiler.compile()
    assert out_path is None


def test_compile_groups_threads_by_state_in_prompt(adapter):
    """The prompt includes WAITING_ON_YOU + FIRST_TOUCH + RECENT_ACTIVITY sections."""
    waiting = _thread("t1", "Reply needed", [
        _msg("alice@example.com", False),
        _msg("me@example.com", True),
        _msg("alice@example.com", False),
    ])
    first = _thread("t2", "First touch", [
        _msg("bob@example.com", False),
    ])
    recent = _thread("t3", "Wrapped up", [
        _msg("carol@example.com", False),
        _msg("me@example.com", True),
    ])

    client = StubAnthropic()
    compiler = EmailCompiler(
        gmail=StubGmail([waiting, first, recent]),
        client=client,
        vault_adapter=adapter,
    )
    compiler.compile()

    prompt = client.last_prompt
    assert "WAITING_ON_YOU thread t1" in prompt
    assert "FIRST_TOUCH thread t2" in prompt
    assert "RECENT_ACTIVITY thread t3" in prompt


def test_compile_uses_default_query_with_category_primary(adapter):
    gmail = StubGmail([])
    compiler = EmailCompiler(
        gmail=gmail,
        client=StubAnthropic(),
        vault_adapter=adapter,
    )
    compiler.compile()

    assert gmail.last_query is not None
    assert "category:primary" in gmail.last_query


def test_compile_passes_through_when_gmail_returns_empty(adapter):
    """No threads = no API call = None. Caller's daily review degrades gracefully."""
    client = StubAnthropic()
    compiler = EmailCompiler(
        gmail=StubGmail([]),
        client=client,
        vault_adapter=adapter,
    )
    out = compiler.compile()
    assert out is None
    assert client.last_prompt is None  # never invoked Claude

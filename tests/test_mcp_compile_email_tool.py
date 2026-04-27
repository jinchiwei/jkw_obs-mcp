"""MCP tool registration + dispatch for compile_email."""

from __future__ import annotations

import datetime as dt

import pytest

from jkw_obs_mcp.adapter.gmail import EmailMessage, EmailThread
from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.compilers.email_compiler import EmailCompiler
from jkw_obs_mcp.mcp.server import dispatch_tool, tools_for_adapter


class StubAnthropic:
    def complete(self, *, prompt, system="", max_tokens=4096):
        return f"# Email Pulse — {dt.date.today().isoformat()}\n\nstub"


class StubGmail:
    def __init__(self, threads):
        self.threads = threads

    def fetch_recent_threads(self, *, query, max_threads=50):
        return self.threads


def _msg(sender, is_self):
    return EmailMessage(
        message_id="m1", sender=sender, recipient="me@example.com",
        subject="Hi", date="Mon, 27 Apr 2026 09:00:00 +0000",
        body="hello", is_from_self=is_self,
    )


@pytest.fixture
def adapter_with_email(tmp_vault, tmp_path):
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    threads = [
        EmailThread(thread_id="t1", subject="Hello", messages=[
            _msg("alice@example.com", False),
        ]),
    ]
    adapter.email_compiler = EmailCompiler(
        gmail=StubGmail(threads),
        client=StubAnthropic(),
        vault_adapter=adapter,
    )
    return adapter


def test_tool_surface_includes_compile_email(adapter_with_email):
    tools = tools_for_adapter(adapter_with_email)
    names = {t.name for t in tools}
    assert "compile_email" in names


@pytest.mark.asyncio
async def test_dispatch_compile_email_writes_summary(adapter_with_email, tmp_vault):
    result = await dispatch_tool(adapter_with_email, "compile_email", {})

    text = result[0].text
    today = dt.date.today().isoformat()
    expected = tmp_vault / "kb" / "dreamingmachine" / "email" / f"{today}.md"
    assert expected.is_file()
    assert str(expected) in text or "email" in text


@pytest.mark.asyncio
async def test_dispatch_compile_email_handles_no_threads(tmp_vault):
    """Empty inbox → tool returns informational message, no crash."""
    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    adapter.email_compiler = EmailCompiler(
        gmail=StubGmail([]),  # no threads
        client=StubAnthropic(),
        vault_adapter=adapter,
    )

    result = await dispatch_tool(adapter, "compile_email", {})
    text = result[0].text
    assert "no" in text.lower() or "skipped" in text.lower() or "empty" in text.lower()

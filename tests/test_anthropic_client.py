"""Tests for the Anthropic client wrapper.

The wrapper supports two backends:
  - Direct Anthropic API (via ANTHROPIC_API_KEY)
  - AWS Bedrock — including UCSF Versa via ANTHROPIC_BEDROCK_BASE_URL
    (autodetected when AWS_ACCESS_KEY_ID is set)

Tests use injected fakes so no real network calls happen.
"""

from types import SimpleNamespace

import pytest

from jkw_obs_mcp.generation.anthropic_client import AnthropicClient


class FakeAnthropic:
    """Stand-in for anthropic.Anthropic / anthropic.AnthropicBedrock —
    captures messages.create calls and returns canned text."""

    def __init__(self, response_text: str = "stub response") -> None:
        self.response_text = response_text
        self.calls: list[dict] = []
        self.messages = self  # so client.client.messages.create works

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.response_text)]
        )


def test_complete_passes_prompt_and_model_through():
    fake = FakeAnthropic(response_text="hello back")
    client = AnthropicClient(model="claude-opus-4-7", _client=fake)

    out = client.complete(prompt="hello world", system="be terse")

    assert out == "hello back"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == "claude-opus-4-7"
    assert call["system"] == "be terse"
    assert call["messages"] == [{"role": "user", "content": "hello world"}]


def test_complete_uses_default_max_tokens():
    fake = FakeAnthropic()
    client = AnthropicClient(model="claude-opus-4-7", _client=fake)

    client.complete(prompt="x", system="y")

    assert fake.calls[0]["max_tokens"] >= 1024


def test_autodetect_bedrock_when_aws_key_set(monkeypatch):
    """If AWS_ACCESS_KEY_ID is set, the client should pick Bedrock."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA-fake")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake = FakeAnthropic()

    client = AnthropicClient(model="us.anthropic.claude-opus-4-6-v1", _client=fake)

    assert client.backend == "bedrock"


def test_autodetect_direct_api_when_only_anthropic_key_set(monkeypatch):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    fake = FakeAnthropic()

    client = AnthropicClient(model="claude-opus-4-7", _client=fake)

    assert client.backend == "direct"


def test_raises_on_missing_credentials(monkeypatch):
    """No env vars at all → clear error."""
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicClient(model="claude-opus-4-7")

"""Thin wrapper around the Anthropic Python SDK.

Supports two backends, autodetected from environment:
  - Bedrock (AnthropicBedrock) — when AWS_ACCESS_KEY_ID is set.
    Honors ANTHROPIC_BEDROCK_BASE_URL for custom endpoints (e.g. UCSF Versa
    at https://unified-api.ucsf.edu/general/awsai/).
  - Direct API (anthropic.Anthropic) — when ANTHROPIC_API_KEY is set.

If both are set, Bedrock wins (matches autofeeder's convention).
"""

from __future__ import annotations

import os
from typing import Any

import anthropic


_DEFAULT_MAX_TOKENS = 4096


def _build_default_client() -> tuple[Any, str]:
    """Construct the underlying SDK client based on env vars.

    Returns (client, backend_tag). backend_tag is "bedrock" or "direct".
    Raises RuntimeError if neither set of credentials is available.
    """
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    if aws_key:
        from anthropic import AnthropicBedrock

        kwargs: dict[str, Any] = {
            "aws_access_key": aws_key,
            "aws_secret_key": os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
            "aws_region": (
                os.environ.get("AWS_REGION")
                or os.environ.get("AWS_DEFAULT_REGION")
                or "us-west-2"
            ),
        }
        base_url = os.environ.get("ANTHROPIC_BEDROCK_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url
        session_token = os.environ.get("AWS_SESSION_TOKEN")
        if session_token:
            kwargs["aws_session_token"] = session_token
        return AnthropicBedrock(**kwargs), "bedrock"

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "No Anthropic credentials found. Set either:\n"
            "  - ANTHROPIC_API_KEY (direct API), or\n"
            "  - AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY (Bedrock)\n"
            "    with optional ANTHROPIC_BEDROCK_BASE_URL for UCSF Versa."
        )
    return anthropic.Anthropic(api_key=api_key), "direct"


class AnthropicClient:
    """Synchronous wrapper. Single entry point: complete(prompt, system).

    The underlying SDK client is auto-built from env vars unless _client
    is injected (used by tests).
    """

    def __init__(
        self,
        *,
        model: str,
        _client: Any = None,
    ) -> None:
        self.model = model
        if _client is not None:
            self.client = _client
            # Tag explicitly when env says Bedrock; default to "direct" otherwise.
            self.backend = (
                "bedrock" if os.environ.get("AWS_ACCESS_KEY_ID") else "direct"
            )
        else:
            self.client, self.backend = _build_default_client()

    def complete(
        self,
        *,
        prompt: str,
        system: str = "",
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> str:
        """Run a single user-message completion. Returns the assistant text.

        Both anthropic.Anthropic and AnthropicBedrock expose the same
        messages.create() signature, so one call site works for both.
        """
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

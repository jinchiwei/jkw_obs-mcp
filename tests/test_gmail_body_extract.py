"""MIME body extraction tests."""

from __future__ import annotations

import base64

from jkw_obs_mcp.adapter.gmail import _extract_message_body


def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii")


def test_extracts_text_plain_when_present():
    payload = {
        "mimeType": "text/plain",
        "body": {"data": _b64url("Hello world")},
    }
    assert _extract_message_body(payload) == "Hello world"


def test_returns_empty_when_no_body_data():
    payload = {"mimeType": "text/plain", "body": {}}
    assert _extract_message_body(payload) == ""


def test_strips_html_when_no_text_plain():
    html = "<p>Hello <b>world</b></p>"
    payload = {
        "mimeType": "text/html",
        "body": {"data": _b64url(html)},
    }
    out = _extract_message_body(payload)
    assert "Hello" in out
    assert "world" in out
    assert "<p>" not in out
    assert "<b>" not in out


def test_handles_multipart_alternative_prefers_text_plain():
    """multipart/alternative with both text/plain and text/html → use text/plain."""
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": _b64url("plain text version")},
            },
            {
                "mimeType": "text/html",
                "body": {"data": _b64url("<p>html version</p>")},
            },
        ],
    }
    assert _extract_message_body(payload) == "plain text version"


def test_handles_multipart_alternative_fallback_to_html():
    """multipart/alternative with only text/html → use it (stripped)."""
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/html",
                "body": {"data": _b64url("<p>only html</p>")},
            },
        ],
    }
    out = _extract_message_body(payload)
    assert "only html" in out
    assert "<p>" not in out


def test_handles_nested_multipart():
    """multipart/mixed wrapping multipart/alternative wrapping text/plain."""
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": _b64url("nested plain")},
                    },
                ],
            },
            {
                "mimeType": "application/pdf",
                "filename": "attachment.pdf",
                "body": {"attachmentId": "abc"},
            },
        ],
    }
    assert _extract_message_body(payload) == "nested plain"


def test_returns_empty_string_when_no_text_part_anywhere():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "application/pdf",
                "body": {"attachmentId": "abc"},
            },
        ],
    }
    assert _extract_message_body(payload) == ""

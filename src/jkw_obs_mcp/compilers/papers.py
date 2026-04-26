"""Compile raw/papers/<slug>.md into kb/<machine>/papers/<slug>.md.

Uses Anthropic's API (via AnthropicClient) to summarize. Prompt template
lives in ../generation/prompts/paper_summary.j2.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Resolve the prompt template path relative to this file.
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "generation" / "prompts"
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
    keep_trailing_newline=True,
)


class PaperCompiler:
    """Compiler for raw/papers/. Uses an injectable client so tests can stub."""

    type_name = "papers"
    raw_subdir = "papers"
    kb_subdir = "papers"

    def __init__(self, client) -> None:
        self.client = client
        self._template = _env.get_template("paper_summary.j2")

    def compile_one(self, raw_path: str, content: str) -> str:
        prompt = self._template.render(raw_path=raw_path, content=content)
        return self.client.complete(prompt=prompt, system="You are a research note-taker.")

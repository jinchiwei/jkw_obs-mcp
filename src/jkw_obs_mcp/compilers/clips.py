"""Compile raw/clips/<slug>.md (Obsidian Web Clipper output) into
kb/<machine>/clips/<slug>.md."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "generation" / "prompts"
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
    keep_trailing_newline=True,
)


class ClipCompiler:
    """Compiler for raw/clips/."""

    type_name = "clips"
    raw_subdir = "clips"
    kb_subdir = "clips"

    def __init__(self, client) -> None:
        self.client = client
        self._template = _env.get_template("clip_summary.j2")

    def compile_one(self, raw_path: str, content: str) -> str:
        prompt = self._template.render(raw_path=raw_path, content=content)
        return self.client.complete(prompt=prompt, system="You are a research note-taker.")

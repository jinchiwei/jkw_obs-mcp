"""PaperCompiler tests with a stub AnthropicClient."""

from pathlib import Path

import pytest

from jkw_obs_mcp.compilers.base import CompileState, compile_all
from jkw_obs_mcp.compilers.papers import PaperCompiler


class StubAnthropic:
    def __init__(self, response: str = "## TL;DR\n- stub") -> None:
        self.response = response
        self.last_prompt: str | None = None
        self.calls = 0

    def complete(self, *, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        self.last_prompt = prompt
        self.calls += 1
        return self.response


def test_paper_compiler_renders_template_with_content():
    stub = StubAnthropic()
    compiler = PaperCompiler(client=stub)

    output = compiler.compile_one(
        raw_path="raw/papers/foo.md",
        content="Title: Cool study\nAbstract: We did stuff.",
    )

    assert "## TL;DR" in output
    assert stub.last_prompt is not None
    # The prompt was rendered from the template with the inputs we passed
    assert "raw/papers/foo.md" in stub.last_prompt
    assert "Cool study" in stub.last_prompt


def test_paper_compiler_via_compile_all(tmp_path):
    """End-to-end: drop a file in raw/papers/, run compile_all, verify kb output."""
    vault = tmp_path / "vault"
    raw_dir = vault / "raw" / "papers"
    raw_dir.mkdir(parents=True)
    (raw_dir / "study.md").write_text("Title: A\nAbstract: B")

    stub = StubAnthropic(response="# Compiled\n\n## TL;DR\n- bullet")
    compiler = PaperCompiler(client=stub)
    state_path = tmp_path / "compile-state.json"
    state = CompileState.load(state_path)

    stats = compile_all(
        compiler=compiler,
        vault_root=vault,
        machine_id="dreamingmachine",
        state=state,
        state_path=state_path,
    )

    assert stats.added == 1
    assert stats.failed == 0
    out = vault / "kb" / "dreamingmachine" / "papers" / "study.md"
    assert out.read_text().startswith("# Compiled")


def test_paper_compiler_skips_unchanged(tmp_path):
    """Second pass with no changes should be a no-op."""
    vault = tmp_path / "vault"
    raw_dir = vault / "raw" / "papers"
    raw_dir.mkdir(parents=True)
    (raw_dir / "study.md").write_text("static content")

    stub = StubAnthropic()
    compiler = PaperCompiler(client=stub)
    state_path = tmp_path / "compile-state.json"

    # First pass: 1 added
    state = CompileState.load(state_path)
    s1 = compile_all(
        compiler=compiler, vault_root=vault, machine_id="m", state=state,
        state_path=state_path,
    )
    assert s1.added == 1

    # Second pass: should be unchanged (state file persisted between calls)
    state2 = CompileState.load(state_path)
    s2 = compile_all(
        compiler=compiler, vault_root=vault, machine_id="m", state=state2,
        state_path=state_path,
    )
    assert s2.added == 0
    assert s2.unchanged == 1
    # Stub should have only been called once total
    assert stub.calls == 1

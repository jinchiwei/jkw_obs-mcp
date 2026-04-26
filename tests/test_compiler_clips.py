"""ClipCompiler tests."""

from pathlib import Path

from jkw_obs_mcp.compilers.base import CompileState, compile_all
from jkw_obs_mcp.compilers.clips import ClipCompiler


class StubAnthropic:
    def __init__(self, response: str = "## TL;DR\nstub article summary") -> None:
        self.response = response

    def complete(self, *, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        return self.response


def test_clip_compiler_compiles_one(tmp_path):
    compiler = ClipCompiler(client=StubAnthropic("# Out\n\nbody"))

    out = compiler.compile_one(
        raw_path="raw/clips/article.md",
        content="---\nsource_url: https://example.com/article\n---\nArticle body.",
    )

    assert "# Out" in out


def test_clip_compiler_via_compile_all(tmp_path):
    vault = tmp_path / "vault"
    raw_dir = vault / "raw" / "clips"
    raw_dir.mkdir(parents=True)
    (raw_dir / "article.md").write_text(
        "---\nsource_url: https://example.com/article\n---\nArticle body."
    )

    compiler = ClipCompiler(client=StubAnthropic(response="# Clip\n\n## TL;DR\nx"))
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
    out = vault / "kb" / "dreamingmachine" / "clips" / "article.md"
    assert out.read_text().startswith("# Clip")

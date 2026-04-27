"""EmailCompiler: pulls recent threads from Gmail, classifies them, summarizes
them via Anthropic, writes kb/<machine>/email/<today>.md.

Architecture mirrors PaperCompiler / ClipCompiler in this directory: injectable
client + adapter, prompt template loaded once at construction.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from jkw_obs_mcp.adapter.gmail import EmailThread, GmailAdapter
from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.compilers.email_state import ThreadState, classify_thread_state


_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "generation" / "prompts"
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
    keep_trailing_newline=True,
)

# Gmail's primary tab + recent window. Promotions / Updates / Forums / Social
# are excluded automatically by category:primary.
_DEFAULT_QUERY = "in:inbox category:primary newer_than:2d"


class EmailCompiler:
    """Composes Gmail adapter + thread classifier + Anthropic into kb/email/<today>.md."""

    def __init__(
        self,
        *,
        gmail: GmailAdapter,
        client,
        vault_adapter: VaultAdapter,
        query: str = _DEFAULT_QUERY,
    ) -> None:
        self.gmail = gmail
        self.client = client
        self.vault_adapter = vault_adapter
        self.query = query
        self._template = _env.get_template("email_summary.j2")

    def compile(self) -> Path | None:
        """Fetch threads, classify, summarize, write summary file. Returns the
        path of the written file, or None if there were no threads (signals
        'no email content today' to callers)."""
        threads = self.gmail.fetch_recent_threads(query=self.query, max_threads=50)
        if not threads:
            return None

        now = dt.datetime.now(dt.UTC)
        buckets: dict[ThreadState, list[EmailThread]] = {
            ThreadState.WAITING_ON_YOU: [],
            ThreadState.FIRST_TOUCH: [],
            ThreadState.RECENT_ACTIVITY: [],
        }
        for thread in threads:
            state = classify_thread_state(thread, now=now)
            buckets[state].append(thread)

        today = dt.date.today().isoformat()
        prompt = self._template.render(
            today=today,
            machine_id=self.vault_adapter.machine_id,
            waiting_on_you=buckets[ThreadState.WAITING_ON_YOU],
            first_touch=buckets[ThreadState.FIRST_TOUCH],
            recent_activity=buckets[ThreadState.RECENT_ACTIVITY],
        )

        markdown = self.client.complete(
            prompt=prompt,
            system="You are a focused email-pulse note-taker.",
        )

        out_path = self.vault_adapter.write_kb_note(
            filename=f"{today}.md",
            content=markdown,
            subdir="email",
        )
        return out_path

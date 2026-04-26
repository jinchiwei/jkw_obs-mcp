"""DailyReviewGenerator: morning digest combining calendar + vault deltas +
autofeeder + last-review state, written to kb/<machine>/daily/<YYYY-MM-DD>.md."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.context.autofeeder import load_recent_autofeeder_digests
from jkw_obs_mcp.context.vault_delta import vault_delta_since


_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "generation" / "prompts"
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=select_autoescape(),
    keep_trailing_newline=True,
)


class DailyReviewGenerator:
    """Composes morning digest from calendar + vault deltas + autofeeder.

    Persists a tiny JSON state file with last_run_at so the next run only
    mentions deltas since the previous review (defaults to last 24h on first run).
    """

    def __init__(self, *, adapter: VaultAdapter, client) -> None:
        self.adapter = adapter
        self.client = client
        self._template = _env.get_template("daily_review.j2")

    def generate(self) -> Path:
        today = dt.date.today().isoformat()
        last_run = self._load_last_run()
        cutoff = last_run or (dt.datetime.now(dt.UTC) - dt.timedelta(hours=24))

        # Gather inputs
        events = self.adapter.calendar.upcoming(days=7) if hasattr(self.adapter, "calendar") else []
        deltas = vault_delta_since(self.adapter.vault_root, since=cutoff)
        digests = load_recent_autofeeder_digests(self.adapter.vault_root, days=7)

        # Render prompt
        prompt = self._template.render(
            machine_id=self.adapter.machine_id,
            today=today,
            last_review=last_run.isoformat() if last_run else "(never)",
            events=events,
            vault_deltas=deltas,
            autofeeder_digests=digests,
        )

        # Call Claude
        markdown = self.client.complete(
            prompt=prompt,
            system="You are a focused daily-review note-taker.",
        )

        # Write into kb/<machine>/daily/<YYYY-MM-DD>.md
        out_path = self.adapter.write_kb_note(
            filename=f"{today}.md",
            content=markdown,
            subdir="daily",
        )
        self._save_last_run(dt.datetime.now(dt.UTC))
        return out_path

    def _load_last_run(self) -> dt.datetime | None:
        path: Path = self.adapter.daily_review_state_path
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            ts = data.get("last_run_at")
            return dt.datetime.fromisoformat(ts) if ts else None
        except (json.JSONDecodeError, ValueError):
            return None

    def _save_last_run(self, when: dt.datetime) -> None:
        path: Path = self.adapter.daily_review_state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"last_run_at": when.isoformat()}, indent=2))

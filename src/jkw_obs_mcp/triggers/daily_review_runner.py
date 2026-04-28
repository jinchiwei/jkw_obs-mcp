"""Boot-trigger entry point for the daily review.

Invoked by launchd every 5 minutes (StartInterval=300) on macOS, and
optionally by cron / manual run on Linux. Reads the state file and only
fires `generate_daily_review` if today's date is later than last_run_at's
date. Otherwise exits 0 silently. Cost when no-op: ~10ms.

Errors during the actual run are logged to stderr (which launchd captures
to ~/Library/Logs/com.jinchiwei.jkw-obs-mcp.daily-review.err) but never
re-raised -- a crash in the trigger should not crash the LaunchAgent.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Callable


def _state_path() -> Path:
    """Where the daily-review state file lives. Function so tests can monkey-patch."""
    return Path.home() / ".config" / "jkw-obs-mcp" / "last-daily-review.json"


def _today() -> dt.date:
    """Wrapper around dt.date.today() for test injection."""
    return dt.date.today()


def should_run_today(
    state_path: Path,
    *,
    today: dt.date | None = None,
) -> bool:
    """Return True if a daily review should run now.

    True when: state file missing, corrupt, missing the `last_run_at` key,
    or the persisted last_run_at falls on a strictly earlier LOCAL date than
    `today` (also a local date). False only when state file exists, parses
    cleanly, and last_run_at's local date matches today.

    Timezone handling: state files store UTC timestamps (canonical, DST-safe).
    Comparison must use local dates because the user's "day" boundary is
    local midnight, not UTC midnight. Otherwise a run that completes after
    local midnight UTC (e.g., 22:00 PDT = 05:00 UTC the next day) would skip
    today's run because its UTC date appears to match today's local date.
    """
    if today is None:
        today = _today()

    if not state_path.is_file():
        return True

    try:
        data = json.loads(state_path.read_text())
        ts = data.get("last_run_at")
        if not ts:
            return True
        last_run = dt.datetime.fromisoformat(ts)
        # Convert UTC tz-aware timestamp to local datetime, then take local date.
        # astimezone() with no argument converts to system local tz.
        last_run_local_date = last_run.astimezone().date()
        return last_run_local_date < today
    except (json.JSONDecodeError, KeyError, ValueError):
        return True


def main(*, _runner: Callable[[], int] | None = None) -> int:
    """LaunchAgent entry point. Returns 0 on success or no-op, 1 on error.

    `_runner` is injectable for tests; production callers pass nothing and
    the real `_run_daily_review` is used.
    """
    state = _state_path()
    if not should_run_today(state):
        return 0

    runner = _runner if _runner is not None else _run_daily_review
    try:
        return runner()
    except Exception as exc:
        print(f"daily-review trigger failed: {exc}", file=sys.stderr)
        return 1


def _run_daily_review() -> int:
    """Build the adapter + generator from config and invoke generate().

    Mirrors the wiring in mcp/server.py:main() but synchronous and exits
    after one generate(). Loads ~/.config/jkw-obs-mcp/.env first (same
    secrets-loading pattern as the MCP server).
    """
    from dotenv import load_dotenv

    from jkw_obs_mcp.adapter.calendar import CalendarAdapter
    from jkw_obs_mcp.adapter.gmail import GmailAdapter
    from jkw_obs_mcp.adapter.vault import VaultAdapter
    from jkw_obs_mcp.compilers.email_compiler import EmailCompiler
    from jkw_obs_mcp.config import load_config
    from jkw_obs_mcp.generation.anthropic_client import AnthropicClient
    from jkw_obs_mcp.generators.daily_review import DailyReviewGenerator

    cfg_dir = Path.home() / ".config" / "jkw-obs-mcp"
    env_path = cfg_dir / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)

    cfg = load_config(cfg_dir / "config.toml")
    adapter = VaultAdapter(vault_root=cfg.vault_root, machine_id=cfg.machine_id)
    adapter.calendar = CalendarAdapter()
    adapter.daily_review_state_path = cfg_dir / "last-daily-review.json"
    adapter.anthropic_model = cfg.generation.model

    client = AnthropicClient(model=cfg.generation.model)
    adapter.email_compiler = EmailCompiler(
        gmail=GmailAdapter(
            client_secret_path=cfg_dir / "google-client-secret.json",
            token_path=cfg_dir / "gmail-token.json",
        ),
        client=client,
        vault_adapter=adapter,
    )

    gen = DailyReviewGenerator(adapter=adapter, client=client)
    out_path = gen.generate()
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

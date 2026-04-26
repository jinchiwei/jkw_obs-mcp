"""Load recent autofeeder digest texts for daily-review context."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path


_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


@dataclass(frozen=True)
class AutofeederDigest:
    """One profile's digest for a specific date."""

    profile: str
    date: str
    content: str


def load_recent_autofeeder_digests(
    vault_root: Path, days: int = 7
) -> list[AutofeederDigest]:
    """Walk <vault>/臥龍/Autofeeder/<profile>/<YYYY-MM-DD>.md, return entries
    from the last `days` days."""
    af_root = vault_root / "臥龍" / "Autofeeder"
    if not af_root.is_dir():
        return []

    cutoff = dt.date.today() - dt.timedelta(days=days)
    digests: list[AutofeederDigest] = []

    for profile_dir in sorted(af_root.iterdir()):
        if not profile_dir.is_dir():
            continue
        for f in sorted(profile_dir.glob("*.md")):
            m = _DATE_RE.match(f.name)
            if not m:
                continue
            try:
                file_date = dt.date.fromisoformat(m.group(1))
            except ValueError:
                continue
            if file_date < cutoff:
                continue
            digests.append(
                AutofeederDigest(
                    profile=profile_dir.name,
                    date=m.group(1),
                    content=f.read_text(encoding="utf-8"),
                )
            )

    return digests

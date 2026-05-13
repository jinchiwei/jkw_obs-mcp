#!/usr/bin/env python3
"""Extract text from a PDF and write it to vault/raw/papers/<slug>.md.

Usage:
    python tools/pdf_to_raw.py path/to/paper.pdf [--vault VAULT_PATH] [--slug SLUG]

Requires `pymupdf` (installed via the package's dev deps).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, UTC
from pathlib import Path

import pymupdf  # type: ignore[import-untyped]


def _slugify(text: str, max_len: int = 60) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\-_ ]+", "", text)
    text = re.sub(r"\s+", "-", text).strip("-")
    return text[:max_len] or "untitled"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", type=Path, help="Path to the source PDF")
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path(os.path.expanduser("~/arcadia/jkw_dm")),
        help="Vault root (default: ~/arcadia/jkw_dm — Obsidian Sync vault)",
    )
    parser.add_argument(
        "--slug",
        default=None,
        help="Output slug (default: derived from PDF filename)",
    )
    args = parser.parse_args()

    if not args.pdf_path.is_file():
        sys.exit(f"PDF not found: {args.pdf_path}")

    slug = args.slug or _slugify(args.pdf_path.stem)
    out_dir = args.vault / "raw" / "papers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.md"

    with pymupdf.open(args.pdf_path) as doc:
        pages = [page.get_text("text") for page in doc]
    text = "\n\n".join(pages).strip()

    frontmatter = (
        "---\n"
        f"source_pdf: {args.pdf_path}\n"
        f"slug: {slug}\n"
        f"ingested_at: {datetime.now(UTC).isoformat()}\n"
        "type: paper\n"
        "---\n\n"
    )
    out_path.write_text(frontmatter + text, encoding="utf-8")
    print(f"wrote {out_path} ({len(text)} chars from {len(pages)} pages)")


if __name__ == "__main__":
    main()

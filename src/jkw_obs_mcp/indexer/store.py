"""sqlite-vec backed store for the embeddings index.

Schema:
  - notes(path TEXT PRIMARY KEY, content_hash TEXT NOT NULL,
          indexed_at TEXT NOT NULL DEFAULT (datetime('now')))
  - notes_vec(rowid INTEGER PRIMARY KEY, embedding FLOAT[<dim>]) — vec0 virtual table
  - notes.rowid is the join key into notes_vec.
"""

from __future__ import annotations

import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path

import sqlite_vec


@dataclass(frozen=True)
class Hit:
    """One semantic-search hit."""

    path: str
    distance: float


def _serialize_vec(vec: list[float]) -> bytes:
    """Pack a list of floats into the format sqlite-vec expects."""
    return struct.pack(f"{len(vec)}f", *vec)


class SqliteVecStore:
    """SQLite + sqlite-vec backed embeddings store."""

    def __init__(self, db_path: Path, dimension: int) -> None:
        self.db_path = db_path
        self.dimension = dimension
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            self._conn = conn
        return self._conn

    def init_schema(self) -> None:
        conn = self._connect()
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS notes (
                path TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                indexed_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_vec USING vec0(
                embedding FLOAT[{self.dimension}]
            );
            """
        )
        conn.commit()

    def upsert(self, path: str, content_hash: str, embedding: list[float]) -> None:
        if len(embedding) != self.dimension:
            raise ValueError(
                f"embedding dim {len(embedding)} != store dim {self.dimension}"
            )
        conn = self._connect()
        # Delete existing row for path (and its vec) so the rowid match stays clean.
        cur = conn.execute("SELECT rowid FROM notes WHERE path = ?", (path,))
        row = cur.fetchone()
        if row is not None:
            old_rowid = row[0]
            conn.execute("DELETE FROM notes_vec WHERE rowid = ?", (old_rowid,))
            conn.execute("DELETE FROM notes WHERE path = ?", (path,))

        cur = conn.execute(
            "INSERT INTO notes(path, content_hash) VALUES (?, ?)",
            (path, content_hash),
        )
        rowid = cur.lastrowid
        conn.execute(
            "INSERT INTO notes_vec(rowid, embedding) VALUES (?, ?)",
            (rowid, _serialize_vec(embedding)),
        )
        conn.commit()

    def delete(self, path: str) -> None:
        conn = self._connect()
        cur = conn.execute("SELECT rowid FROM notes WHERE path = ?", (path,))
        row = cur.fetchone()
        if row is None:
            return
        rowid = row[0]
        conn.execute("DELETE FROM notes_vec WHERE rowid = ?", (rowid,))
        conn.execute("DELETE FROM notes WHERE path = ?", (path,))
        conn.commit()

    def query(self, query_vec: list[float], top_k: int = 10) -> list[Hit]:
        if len(query_vec) != self.dimension:
            raise ValueError(
                f"query dim {len(query_vec)} != store dim {self.dimension}"
            )
        conn = self._connect()
        # vec0 knn requires either LIMIT or a `k = ?` constraint applied
        # directly on the virtual table — joins push LIMIT outward, so we
        # do the knn in a subquery and join afterward.
        cur = conn.execute(
            """
            SELECT n.path, v.distance
            FROM (
                SELECT rowid, distance
                FROM notes_vec
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?
            ) v
            JOIN notes n ON n.rowid = v.rowid
            ORDER BY v.distance
            """,
            (_serialize_vec(query_vec), top_k),
        )
        return [Hit(path=row[0], distance=row[1]) for row in cur.fetchall()]

    def all_paths(self) -> dict[str, str]:
        """Returns {path: content_hash} for every indexed note."""
        conn = self._connect()
        cur = conn.execute("SELECT path, content_hash FROM notes")
        return {row[0]: row[1] for row in cur.fetchall()}

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

# Plan 2: Embeddings Indexer + Semantic Search

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a sqlite-vec-backed embeddings index over the Obsidian vault and expose `search_vault(query)` + `find_similar(text)` MCP tools. After this plan ships, Claude on dreamingmachine can semantically search the vault — "what did I write about meningioma last month" returns ranked results in <500ms.

**Architecture:** Three internal modules under `src/jkw_obs_mcp/indexer/`. **Embedder** wraps fastembed (ONNX, default; ~100MB, no torch). **Store** wraps sqlite-vec for vector ops. **Walker** discovers vault `.md` files and tracks (path, content_hash) to drive incremental re-embedding. **Indexer.reindex()** composes them: walker produces stale items, embedder embeds, store upserts. New MCP tools call store.query for retrieval.

**Tech Stack:** `fastembed` (ONNX, lightweight), `sqlite-vec` (vector extension), Python 3.11+ stdlib `hashlib` + `sqlite3`, existing `mcp` SDK. Adds 2 deps to pyproject.toml.

---

## File Structure

```
jkw_obs-mcp/
├── pyproject.toml                       Modify: add fastembed, sqlite-vec deps
├── src/jkw_obs_mcp/
│   ├── config.py                        Modify: add EmbeddingsConfig + load
│   ├── indexer/
│   │   ├── __init__.py                  Empty
│   │   ├── embedder.py                  EmbedderProtocol + FastembedEmbedder
│   │   ├── store.py                     SqliteVecStore (init, upsert, query, all_paths)
│   │   ├── walker.py                    walk_vault() returning [(rel_path, content_hash)]
│   │   └── indexer.py                   Indexer.reindex(scope) — top-level orchestrator
│   └── mcp/server.py                    Modify: add search_vault + find_similar tools
└── tests/
    ├── test_indexer_embedder.py
    ├── test_indexer_store.py
    ├── test_indexer_walker.py
    ├── test_indexer_reindex.py
    └── test_mcp_search_tools.py
```

---

## Task 1: Add fastembed + sqlite-vec to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update dependencies block**

Replace:
```toml
dependencies = [
    "mcp>=1.0.0",
]
```

With:
```toml
dependencies = [
    "mcp>=1.0.0",
    "fastembed>=0.4.0",
    "sqlite-vec>=0.1.6",
]
```

- [ ] **Step 2: Re-install in deepdream env**

Run: `source ~/miniconda3/etc/profile.d/conda.sh && conda activate deepdream && pip install -e ".[dev]"`
Expected: fastembed + sqlite-vec installed. fastembed pulls onnxruntime (~50MB).

- [ ] **Step 3: Smoke import**

Run: `python -c 'import fastembed, sqlite_vec; print("ok")'`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add fastembed + sqlite-vec for Plan 2 embeddings"
```

---

## Task 2: Add EmbeddingsConfig to config schema

**Files:**
- Modify: `src/jkw_obs_mcp/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Failing test — append to `tests/test_config.py`**

```python
def test_load_config_includes_embeddings_section(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[paths]
vault_root = "/some/vault"

[machine]
id = "dreamingmachine"

[embeddings]
backend = "fastembed"
model = "sentence-transformers/all-MiniLM-L6-v2"
db_path = "~/data/embeddings.db"
"""
    )

    cfg = load_config(cfg_file)

    assert cfg.embeddings.backend == "fastembed"
    assert cfg.embeddings.model == "sentence-transformers/all-MiniLM-L6-v2"
    assert "~" not in str(cfg.embeddings.db_path)


def test_load_config_uses_embeddings_defaults_when_section_absent(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[paths]
vault_root = "/some/vault"

[machine]
id = "dreamingmachine"
"""
    )

    cfg = load_config(cfg_file)

    assert cfg.embeddings.backend == "fastembed"
    assert cfg.embeddings.model == "sentence-transformers/all-MiniLM-L6-v2"
    # default db_path is under <repo_root>/data/embeddings.db
    assert str(cfg.embeddings.db_path).endswith("data/embeddings.db")
```

- [ ] **Step 2: Run — verify ImportError or AttributeError**

Run: `pytest tests/test_config.py -v -k embeddings`
Expected: FAIL — `EmbeddingsConfig` doesn't exist or `Config.embeddings` missing.

- [ ] **Step 3: Update `src/jkw_obs_mcp/config.py`**

Add this dataclass before `Config`:

```python
@dataclass(frozen=True)
class EmbeddingsConfig:
    """Embeddings backend configuration."""

    backend: str = "fastembed"
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    db_path: Path = Path("data/embeddings.db")
```

Modify `Config` to add embeddings field:

```python
@dataclass(frozen=True)
class Config:
    """Per-machine configuration loaded from config.toml."""

    vault_root: Path
    machine_id: str
    daily_review_enabled: bool = False
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
```

(You'll need to `from dataclasses import field` at the top.)

Modify `load_config` to populate the embeddings field:

```python
def load_config(path: Path) -> Config:
    """Load Config from a TOML file. Expands ~ in vault_root + db_path."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    paths = data.get("paths", {})
    machine = data.get("machine", {})
    generation = data.get("generation", {})
    emb = data.get("embeddings", {})

    vault_root_str = paths.get("vault_root", "")
    if not vault_root_str:
        raise ValueError(f"{path}: [paths].vault_root is required")
    vault_root = Path(vault_root_str).expanduser().resolve()

    machine_id = machine.get("id", "")
    if not machine_id:
        raise ValueError(f"{path}: [machine].id is required")

    # Embeddings section is optional — defaults from EmbeddingsConfig apply.
    db_path_str = emb.get("db_path", "data/embeddings.db")
    db_path = Path(db_path_str).expanduser()
    embeddings = EmbeddingsConfig(
        backend=emb.get("backend", "fastembed"),
        model=emb.get("model", "sentence-transformers/all-MiniLM-L6-v2"),
        db_path=db_path,
    )

    return Config(
        vault_root=vault_root,
        machine_id=machine_id,
        daily_review_enabled=generation.get("daily_review_enabled", False),
        embeddings=embeddings,
    )
```

- [ ] **Step 4: Run — tests pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (11 tests now: 9 from Plan 1 + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/config.py tests/test_config.py
git commit -m "feat: EmbeddingsConfig section + defaults in load_config"
```

---

## Task 3: Embedder — `FastembedEmbedder` + protocol

**Files:**
- Create: `src/jkw_obs_mcp/indexer/__init__.py`
- Create: `src/jkw_obs_mcp/indexer/embedder.py`
- Create: `tests/test_indexer_embedder.py`

- [ ] **Step 1: Write `src/jkw_obs_mcp/indexer/__init__.py`**

(Empty file.)

- [ ] **Step 2: Failing test at `tests/test_indexer_embedder.py`**

```python
"""Tests for the embedder. Uses the real fastembed model — slow on first run
(downloads ~30MB), fast thereafter (cached in ~/.cache/fastembed/)."""

import pytest

from jkw_obs_mcp.indexer.embedder import FastembedEmbedder


@pytest.fixture(scope="module")
def embedder() -> FastembedEmbedder:
    return FastembedEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")


def test_embedder_returns_correct_dim(embedder):
    vec = embedder.embed_one("hello world")
    assert len(vec) == 384  # MiniLM-L6 dim


def test_embedder_returns_floats(embedder):
    vec = embedder.embed_one("hello world")
    assert all(isinstance(x, float) for x in vec)


def test_embedder_batch_embeds_consistently(embedder):
    texts = ["alpha", "beta", "gamma"]
    vecs = embedder.embed_batch(texts)
    assert len(vecs) == 3
    assert all(len(v) == 384 for v in vecs)


def test_embedder_dimension_property(embedder):
    assert embedder.dimension == 384
```

- [ ] **Step 3: Run — fail**

Run: `pytest tests/test_indexer_embedder.py -v`
Expected: FAIL — `ModuleNotFoundError: jkw_obs_mcp.indexer.embedder`.

- [ ] **Step 4: Write `src/jkw_obs_mcp/indexer/embedder.py`**

```python
"""Embedder abstraction. Default implementation uses fastembed (ONNX)."""

from __future__ import annotations

from typing import Protocol

from fastembed import TextEmbedding


class Embedder(Protocol):
    """Protocol for any embedder. Returns Python lists of floats so callers
    don't need to know about numpy."""

    @property
    def dimension(self) -> int: ...
    def embed_one(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class FastembedEmbedder:
    """fastembed-backed embedder. ONNX, no torch required."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)
        # Probe the dim with a tiny sentence so we don't bake assumptions in.
        sample = next(iter(self._model.embed(["dim probe"])))
        self._dimension = len(sample)

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_one(self, text: str) -> list[float]:
        vec = next(iter(self._model.embed([text])))
        return [float(x) for x in vec]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in v] for v in self._model.embed(texts)]
```

- [ ] **Step 5: Run — pass**

Run: `pytest tests/test_indexer_embedder.py -v`
Expected: PASS (4 tests). First run downloads the model (~30MB) — be patient.

If fastembed errors with "model not found", check the available list:
```python
from fastembed import TextEmbedding
print([m["model"] for m in TextEmbedding.list_supported_models()])
```
Pick the closest to `sentence-transformers/all-MiniLM-L6-v2`. If unavailable, fall back to `BAAI/bge-small-en-v1.5` (384-dim, included).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/indexer/__init__.py src/jkw_obs_mcp/indexer/embedder.py tests/test_indexer_embedder.py
git commit -m "feat: FastembedEmbedder + Embedder protocol"
```

---

## Task 4: SqliteVecStore — init + upsert + query

**Files:**
- Create: `src/jkw_obs_mcp/indexer/store.py`
- Create: `tests/test_indexer_store.py`

- [ ] **Step 1: Failing tests at `tests/test_indexer_store.py`**

```python
"""Tests for the sqlite-vec store. Uses in-memory DB."""

from pathlib import Path

import pytest

from jkw_obs_mcp.indexer.store import SqliteVecStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteVecStore:
    db = tmp_path / "embeddings.db"
    s = SqliteVecStore(db_path=db, dimension=4)
    s.init_schema()
    return s


def test_upsert_then_query(store):
    store.upsert(path="Admin/x.md", content_hash="h1", embedding=[1.0, 0.0, 0.0, 0.0])
    store.upsert(path="Admin/y.md", content_hash="h2", embedding=[0.0, 1.0, 0.0, 0.0])

    # Query closest to [0.9, 0.1, 0, 0] — should rank x.md first.
    hits = store.query(query_vec=[0.9, 0.1, 0.0, 0.0], top_k=2)

    assert len(hits) == 2
    assert hits[0].path == "Admin/x.md"
    assert hits[1].path == "Admin/y.md"
    assert hits[0].distance < hits[1].distance


def test_upsert_replaces_existing_path(store):
    store.upsert(path="Admin/x.md", content_hash="h1", embedding=[1.0, 0.0, 0.0, 0.0])
    store.upsert(path="Admin/x.md", content_hash="h2", embedding=[0.0, 0.0, 0.0, 1.0])

    # Should still be one row, with the new hash + new vector.
    paths = store.all_paths()
    assert paths == {"Admin/x.md": "h2"}


def test_all_paths_returns_dict_of_path_to_hash(store):
    store.upsert(path="a.md", content_hash="ha", embedding=[1.0, 0.0, 0.0, 0.0])
    store.upsert(path="b.md", content_hash="hb", embedding=[0.0, 1.0, 0.0, 0.0])

    assert store.all_paths() == {"a.md": "ha", "b.md": "hb"}


def test_delete_by_path(store):
    store.upsert(path="a.md", content_hash="ha", embedding=[1.0, 0.0, 0.0, 0.0])
    store.upsert(path="b.md", content_hash="hb", embedding=[0.0, 1.0, 0.0, 0.0])

    store.delete(path="a.md")

    assert store.all_paths() == {"b.md": "hb"}
```

- [ ] **Step 2: Run — fail**

Run: `pytest tests/test_indexer_store.py -v`
Expected: FAIL — `ModuleNotFoundError: jkw_obs_mcp.indexer.store`.

- [ ] **Step 3: Write `src/jkw_obs_mcp/indexer/store.py`**

```python
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
        cur = conn.execute(
            """
            SELECT n.path, v.distance
            FROM notes_vec v
            JOIN notes n ON n.rowid = v.rowid
            WHERE v.embedding MATCH ?
            ORDER BY v.distance
            LIMIT ?
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
```

- [ ] **Step 4: Run — pass**

Run: `pytest tests/test_indexer_store.py -v`
Expected: PASS (4 tests).

If `sqlite_vec.load` or vec0 virtual table errors: check `python -c 'import sqlite_vec; print(sqlite_vec.__version__)'` and ensure the wheel installed. On HPC fallback build: `pip install sqlite-vec --no-binary sqlite-vec`.

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/indexer/store.py tests/test_indexer_store.py
git commit -m "feat: SqliteVecStore — init/upsert/query/delete/all_paths"
```

---

## Task 5: Walker — discover vault `.md` files with content hashes

**Files:**
- Create: `src/jkw_obs_mcp/indexer/walker.py`
- Create: `tests/test_indexer_walker.py`

- [ ] **Step 1: Failing tests at `tests/test_indexer_walker.py`**

```python
from pathlib import Path

import pytest

from jkw_obs_mcp.indexer.walker import VaultEntry, walk_vault


def test_walk_vault_yields_md_files(tmp_vault):
    entries = list(walk_vault(tmp_vault))

    paths = {e.rel_path for e in entries}
    assert "Admin/Saiyan.md" in paths


def test_walk_vault_returns_content_hashes(tmp_vault):
    entries = list(walk_vault(tmp_vault))
    saiyan = next(e for e in entries if e.rel_path == "Admin/Saiyan.md")
    assert isinstance(saiyan, VaultEntry)
    assert len(saiyan.content_hash) == 64  # sha256 hex digest length
    # Same file twice should hash identically
    again = next(e for e in walk_vault(tmp_vault) if e.rel_path == "Admin/Saiyan.md")
    assert saiyan.content_hash == again.content_hash


def test_walk_vault_skips_obsidian_and_trash(tmp_vault):
    # Add a few files we should NOT walk.
    (tmp_vault / ".obsidian").mkdir(exist_ok=True)
    (tmp_vault / ".obsidian" / "workspace.json").write_text("{}")
    (tmp_vault / ".trash").mkdir(exist_ok=True)
    (tmp_vault / ".trash" / "old.md").write_text("# old")
    (tmp_vault / ".git").mkdir(exist_ok=True)
    (tmp_vault / ".git" / "HEAD").write_text("ref: ...")

    paths = {e.rel_path for e in walk_vault(tmp_vault)}

    assert all(not p.startswith(".obsidian/") for p in paths)
    assert all(not p.startswith(".trash/") for p in paths)
    assert all(not p.startswith(".git/") for p in paths)


def test_walk_vault_only_md_files(tmp_vault):
    (tmp_vault / "scratch.txt").write_text("not markdown")

    paths = {e.rel_path for e in walk_vault(tmp_vault)}

    assert all(p.endswith(".md") for p in paths)
```

- [ ] **Step 2: Run — fail**

Run: `pytest tests/test_indexer_walker.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `src/jkw_obs_mcp/indexer/walker.py`**

```python
"""Walk the Obsidian vault and report markdown files with content hashes."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


# Top-level dirs that are NEVER scanned. .obsidian holds plugin code/state,
# .trash is recoverable in the Obsidian UI (not signal), .git is repo metadata.
_SKIP_DIRS = frozenset({".obsidian", ".trash", ".git", ".direnv", ".venv", "node_modules"})


@dataclass(frozen=True)
class VaultEntry:
    """One markdown note discovered during a vault walk."""

    rel_path: str           # vault-relative, posix-style (forward slashes)
    content_hash: str       # sha256 hex of file content


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def walk_vault(vault_root: Path) -> Iterator[VaultEntry]:
    """Yield VaultEntry for every .md file under vault_root, skipping hidden /
    metadata dirs (.obsidian, .trash, .git, etc.)."""
    vault_root = vault_root.resolve()
    for path in sorted(vault_root.rglob("*.md")):
        if not path.is_file():
            continue
        # Skip if any path segment matches a SKIP_DIRS entry.
        if any(part in _SKIP_DIRS for part in path.relative_to(vault_root).parts):
            continue
        rel = path.relative_to(vault_root).as_posix()
        yield VaultEntry(rel_path=rel, content_hash=_sha256_of_file(path))
```

- [ ] **Step 4: Run — pass**

Run: `pytest tests/test_indexer_walker.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/indexer/walker.py tests/test_indexer_walker.py
git commit -m "feat: walk_vault() yields markdown files with sha256 content hashes"
```

---

## Task 6: Indexer — orchestrator + `reindex(scope)`

**Files:**
- Create: `src/jkw_obs_mcp/indexer/indexer.py`
- Create: `tests/test_indexer_reindex.py`

- [ ] **Step 1: Failing tests at `tests/test_indexer_reindex.py`**

```python
"""End-to-end indexer tests. Use a stub embedder (deterministic) so the test
suite doesn't need fastembed loaded."""

from pathlib import Path

import pytest

from jkw_obs_mcp.indexer.indexer import Indexer, ReindexStats
from jkw_obs_mcp.indexer.store import SqliteVecStore


class StubEmbedder:
    """Deterministic embedder for tests — hashes text into a fixed-length vec."""

    dimension = 4

    def embed_one(self, text: str) -> list[float]:
        # Deterministic 4-dim vector based on first 4 chars.
        padded = (text + "\x00\x00\x00\x00")[:4]
        return [float(ord(c)) for c in padded]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


@pytest.fixture
def indexer(tmp_vault, tmp_path):
    db = tmp_path / "test.db"
    store = SqliteVecStore(db_path=db, dimension=4)
    store.init_schema()
    return Indexer(vault_root=tmp_vault, store=store, embedder=StubEmbedder())


def test_reindex_full_inserts_every_md_file(indexer, tmp_vault):
    stats = indexer.reindex(scope="full")

    assert isinstance(stats, ReindexStats)
    assert stats.added >= 1
    assert stats.unchanged == 0
    assert "Admin/Saiyan.md" in indexer.store.all_paths()


def test_reindex_incremental_skips_unchanged_files(indexer):
    # First run: full
    indexer.reindex(scope="full")
    initial_paths = indexer.store.all_paths()

    # Second run: incremental — nothing changed, should skip everything.
    stats = indexer.reindex(scope="incremental")

    assert stats.added == 0
    assert stats.updated == 0
    assert stats.unchanged >= 1
    assert indexer.store.all_paths() == initial_paths


def test_reindex_picks_up_new_file(indexer, tmp_vault):
    indexer.reindex(scope="full")

    (tmp_vault / "Arcadia").mkdir(exist_ok=True)
    (tmp_vault / "Arcadia" / "new.md").write_text("# new note\n")

    stats = indexer.reindex(scope="incremental")

    assert stats.added == 1
    assert "Arcadia/new.md" in indexer.store.all_paths()


def test_reindex_picks_up_modified_file(indexer, tmp_vault):
    indexer.reindex(scope="full")
    old_hash = indexer.store.all_paths()["Admin/Saiyan.md"]

    (tmp_vault / "Admin" / "Saiyan.md").write_text("# Saiyan\nnew workout content\n")

    stats = indexer.reindex(scope="incremental")

    new_hash = indexer.store.all_paths()["Admin/Saiyan.md"]
    assert stats.updated == 1
    assert new_hash != old_hash


def test_reindex_removes_deleted_files(indexer, tmp_vault):
    indexer.reindex(scope="full")
    assert "Admin/Saiyan.md" in indexer.store.all_paths()

    (tmp_vault / "Admin" / "Saiyan.md").unlink()

    stats = indexer.reindex(scope="incremental")

    assert stats.removed == 1
    assert "Admin/Saiyan.md" not in indexer.store.all_paths()
```

- [ ] **Step 2: Run — fail**

Run: `pytest tests/test_indexer_reindex.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `src/jkw_obs_mcp/indexer/indexer.py`**

```python
"""Top-level indexer: composes walker + embedder + store. Idempotent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jkw_obs_mcp.indexer.embedder import Embedder
from jkw_obs_mcp.indexer.store import SqliteVecStore
from jkw_obs_mcp.indexer.walker import walk_vault


@dataclass(frozen=True)
class ReindexStats:
    """Counts from a single reindex pass."""

    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0

    def __str__(self) -> str:
        return (
            f"added={self.added} updated={self.updated} "
            f"unchanged={self.unchanged} removed={self.removed}"
        )


class Indexer:
    """Composes the walker + embedder + store. The only public method most
    callers need is reindex()."""

    def __init__(
        self, vault_root: Path, store: SqliteVecStore, embedder: Embedder
    ) -> None:
        self.vault_root = vault_root
        self.store = store
        self.embedder = embedder

    def reindex(self, scope: str = "incremental") -> ReindexStats:
        """Walk the vault, embed new/changed files, drop deleted ones.

        scope:
          - "full"        — rebuild every entry (does NOT drop the table; just
                            re-embeds and upserts everything).
          - "incremental" — only embed paths whose content_hash differs from
                            what's already in the store.
        """
        if scope not in {"full", "incremental"}:
            raise ValueError(f"unknown reindex scope: {scope!r}")

        existing = self.store.all_paths()  # {path: content_hash}
        seen_paths: set[str] = set()

        added = 0
        updated = 0
        unchanged = 0

        # Pass 1: walk the vault, embed + upsert any new/changed files.
        for entry in walk_vault(self.vault_root):
            seen_paths.add(entry.rel_path)
            existing_hash = existing.get(entry.rel_path)

            if scope == "incremental" and existing_hash == entry.content_hash:
                unchanged += 1
                continue

            content = (self.vault_root / entry.rel_path).read_text(encoding="utf-8")
            vec = self.embedder.embed_one(content)
            self.store.upsert(
                path=entry.rel_path,
                content_hash=entry.content_hash,
                embedding=vec,
            )

            if existing_hash is None:
                added += 1
            else:
                updated += 1

        # Pass 2: drop entries for files that no longer exist on disk.
        removed = 0
        for path in existing.keys() - seen_paths:
            self.store.delete(path)
            removed += 1

        return ReindexStats(
            added=added, updated=updated, unchanged=unchanged, removed=removed
        )
```

- [ ] **Step 4: Run — pass**

Run: `pytest tests/test_indexer_reindex.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/jkw_obs_mcp/indexer/indexer.py tests/test_indexer_reindex.py
git commit -m "feat: Indexer.reindex(scope) — composes walker+embedder+store with mtime/hash dedup"
```

---

## Task 7: MCP tools — `search_vault` + `find_similar`

**Files:**
- Modify: `src/jkw_obs_mcp/mcp/server.py`
- Create: `tests/test_mcp_search_tools.py`

- [ ] **Step 1: Failing tests at `tests/test_mcp_search_tools.py`**

```python
"""Tests that the MCP server's search tools register and dispatch correctly.

Uses a stub embedder + real sqlite-vec store. Skips the live fastembed model
so the suite stays fast."""

from pathlib import Path

import pytest

from jkw_obs_mcp.adapter.vault import VaultAdapter
from jkw_obs_mcp.indexer.indexer import Indexer
from jkw_obs_mcp.indexer.store import SqliteVecStore
from jkw_obs_mcp.mcp.server import dispatch_tool, tools_for_adapter


class StubEmbedder:
    dimension = 4

    def embed_one(self, text: str) -> list[float]:
        padded = (text + "\x00\x00\x00\x00")[:4]
        return [float(ord(c)) for c in padded]

    def embed_batch(self, texts):
        return [self.embed_one(t) for t in texts]


@pytest.fixture
def indexed_adapter(tmp_vault, tmp_path):
    """Build a VaultAdapter + populate a real sqlite-vec store via Indexer."""
    db = tmp_path / "search.db"
    store = SqliteVecStore(db_path=db, dimension=4)
    store.init_schema()
    embedder = StubEmbedder()
    indexer = Indexer(vault_root=tmp_vault, store=store, embedder=embedder)
    indexer.reindex(scope="full")

    adapter = VaultAdapter(vault_root=tmp_vault, machine_id="dreamingmachine")
    # Attach the indexer artefacts so dispatch_tool can find them.
    adapter.embedder = embedder
    adapter.store = store
    return adapter


def test_tool_surface_includes_search_and_find_similar(indexed_adapter):
    tools = tools_for_adapter(indexed_adapter)
    names = {t.name for t in tools}
    assert "search_vault" in names
    assert "find_similar" in names


@pytest.mark.asyncio
async def test_dispatch_search_vault_returns_paths(indexed_adapter):
    result = await dispatch_tool(
        indexed_adapter, "search_vault", {"query": "Saiyan", "top_k": 5}
    )

    text = result[0].text
    # search_vault returns a markdown-ish list of paths + scores
    assert "Admin/Saiyan.md" in text


@pytest.mark.asyncio
async def test_dispatch_find_similar_returns_paths(indexed_adapter):
    result = await dispatch_tool(
        indexed_adapter, "find_similar", {"text": "workout log", "top_k": 5}
    )

    text = result[0].text
    assert "Admin/Saiyan.md" in text
```

- [ ] **Step 2: Run — fail**

Run: `pytest tests/test_mcp_search_tools.py -v`
Expected: FAIL — only the 3 Plan 1 tools are registered.

- [ ] **Step 3: Modify `src/jkw_obs_mcp/mcp/server.py`**

Replace `tools_for_adapter` to add the two search tools:

```python
def tools_for_adapter(adapter: VaultAdapter) -> list[Tool]:
    """Return the MCP Tool definitions exposed by this server."""
    _ = adapter
    return [
        Tool(
            name="read_note",
            description="Read a markdown note from the Obsidian vault. "
            "Path is relative to the vault root (e.g. 'Admin/Saiyan.md').",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Vault-relative path"}
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="list_notes",
            description="List all markdown files in the vault, optionally "
            "scoped to a subdirectory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdir": {
                        "type": "string",
                        "description": "Vault-relative subdir to scope the listing",
                        "default": "",
                    },
                },
            },
        ),
        Tool(
            name="write_kb_note",
            description="Write a markdown note into kb/<this-machine>/<subdir>/. "
            "Refuses writes outside the machine's kb sandbox.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                    "subdir": {"type": "string", "default": "ad-hoc"},
                },
                "required": ["filename", "content"],
            },
        ),
        Tool(
            name="search_vault",
            description="Semantic search over the Obsidian vault. "
            "Returns the top-K notes most similar to the query, ranked by distance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="find_similar",
            description="Find notes semantically similar to the given text. "
            "Same retrieval as search_vault, but framed for 'notes like this'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["text"],
            },
        ),
    ]
```

Replace `dispatch_tool` to handle the two new tools (delegate via adapter.embedder + adapter.store, which the `main()` entry point will attach in Step 5 below):

```python
async def dispatch_tool(
    adapter: VaultAdapter, name: str, arguments: dict[str, Any]
) -> list[TextContent]:
    """Dispatch a tool call to the right adapter method."""
    if name == "read_note":
        text = adapter.read_note(arguments["path"])
        return [TextContent(type="text", text=text)]
    if name == "list_notes":
        paths = adapter.list_notes(subdir=arguments.get("subdir", ""))
        text = "\n".join(str(p) for p in paths)
        return [TextContent(type="text", text=text)]
    if name == "write_kb_note":
        written = adapter.write_kb_note(
            filename=arguments["filename"],
            content=arguments["content"],
            subdir=arguments.get("subdir", "ad-hoc"),
        )
        return [TextContent(type="text", text=f"wrote {written}")]
    if name == "search_vault":
        query_vec = adapter.embedder.embed_one(arguments["query"])
        hits = adapter.store.query(query_vec, top_k=arguments.get("top_k", 10))
        lines = [f"- `{h.path}` (distance {h.distance:.4f})" for h in hits]
        return [TextContent(type="text", text="\n".join(lines))]
    if name == "find_similar":
        query_vec = adapter.embedder.embed_one(arguments["text"])
        hits = adapter.store.query(query_vec, top_k=arguments.get("top_k", 5))
        lines = [f"- `{h.path}` (distance {h.distance:.4f})" for h in hits]
        return [TextContent(type="text", text="\n".join(lines))]
    raise ValueError(f"unknown tool: {name}")
```

- [ ] **Step 4: Modify `main()` in `server.py` to attach embedder + store on the adapter**

Inside `main()`, AFTER `adapter = VaultAdapter(...)` and BEFORE `server = build_server(adapter)`, insert:

```python
    # Initialize the embeddings backend once at startup. Subsequent reindexes
    # reuse this Embedder instance.
    from jkw_obs_mcp.indexer.embedder import FastembedEmbedder
    from jkw_obs_mcp.indexer.store import SqliteVecStore

    db_path = cfg.embeddings.db_path
    if not db_path.is_absolute():
        # Resolve relative to repo root (same convention as machines.toml).
        db_path = pkg_root / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    embedder = FastembedEmbedder(model_name=cfg.embeddings.model)
    store = SqliteVecStore(db_path=db_path, dimension=embedder.dimension)
    store.init_schema()

    # Attach onto the adapter so dispatch_tool can use them. Adapter doesn't
    # define these as constructor args (kept clean for unit tests of the FS path);
    # we set them here as plain instance attributes.
    adapter.embedder = embedder
    adapter.store = store
```

- [ ] **Step 5: Run — pass**

Run: `pytest tests/ -v`
Expected: 32 tests pass (26 from Plan 1 + 4 embedder + 4 store + 5 reindex + 3 search tools = 42 actually; verify exact count from your run).

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/mcp/server.py tests/test_mcp_search_tools.py
git commit -m "feat: search_vault + find_similar MCP tools + main() wires embeddings stack"
```

---

## Task 8: Add `reindex` MCP tool — explicit re-index trigger

**Files:**
- Modify: `src/jkw_obs_mcp/mcp/server.py`
- Modify: `tests/test_mcp_search_tools.py`

- [ ] **Step 1: Failing test — append to `tests/test_mcp_search_tools.py`**

```python
@pytest.mark.asyncio
async def test_dispatch_reindex_runs_indexer(indexed_adapter, tmp_vault):
    # Add a new note that the existing index doesn't know about.
    (tmp_vault / "Arcadia").mkdir(exist_ok=True)
    (tmp_vault / "Arcadia" / "fresh.md").write_text("# fresh\n")

    # Need to attach an Indexer onto the adapter (same pattern as embedder/store).
    from jkw_obs_mcp.indexer.indexer import Indexer
    indexed_adapter.indexer = Indexer(
        vault_root=tmp_vault,
        store=indexed_adapter.store,
        embedder=indexed_adapter.embedder,
    )

    result = await dispatch_tool(
        indexed_adapter, "reindex", {"scope": "incremental"}
    )

    text = result[0].text
    assert "added=1" in text
    assert "Arcadia/fresh.md" in indexed_adapter.store.all_paths()
```

- [ ] **Step 2: Run — fail with "unknown tool: reindex"**

- [ ] **Step 3: Add reindex tool to `tools_for_adapter` and `dispatch_tool`**

In `tools_for_adapter`, append:
```python
        Tool(
            name="reindex",
            description="Re-walk the vault and update the embeddings index. "
            "Scope: 'incremental' (only changed files, default) or 'full' "
            "(re-embed everything).",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["incremental", "full"],
                        "default": "incremental",
                    },
                },
            },
        ),
```

In `dispatch_tool`, before `raise ValueError(...)`:
```python
    if name == "reindex":
        stats = adapter.indexer.reindex(scope=arguments.get("scope", "incremental"))
        return [TextContent(type="text", text=str(stats))]
```

- [ ] **Step 4: Update `main()` to attach Indexer on adapter**

Inside `main()`, add after `store.init_schema()`:
```python
    from jkw_obs_mcp.indexer.indexer import Indexer
    indexer = Indexer(vault_root=adapter.vault_root, store=store, embedder=embedder)
    adapter.indexer = indexer
```

- [ ] **Step 5: Run — pass**

- [ ] **Step 6: Commit**

```bash
git add src/jkw_obs_mcp/mcp/server.py tests/test_mcp_search_tools.py
git commit -m "feat: reindex MCP tool — explicit scope=incremental|full trigger"
```

---

## Task 9: Manual end-to-end smoke test on dreamingmachine

This task is non-TDD — exercises the real fastembed model against the actual jkw_obs vault.

- [ ] **Step 1: Pre-flight — confirm vault is non-empty**

Run: `ls "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs/" | head -5`
Expected: real folder names (Admin/, Arcadia/, etc.)

- [ ] **Step 2: First reindex (full) via Claude Code**

In a Claude Code session, ask:
> Use jkw-obs `reindex` with scope `full` to build the embeddings index over my vault.

Expected: tool returns `added=N updated=0 unchanged=0 removed=0` with N matching the number of .md files in your vault (probably 200+). First run downloads the fastembed model (~30MB) — may take 15-60 seconds.

- [ ] **Step 3: Verify db landed at the configured path**

Run: `ls -la /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp/data/embeddings.db*`
Expected: db file exists (probably 1-5MB).

- [ ] **Step 4: Search for a known topic**

In Claude Code:
> Use jkw-obs `search_vault` to find notes about "meningioma" — top 10.

Expected: meningioma-related notes rank at the top with low distance scores.

- [ ] **Step 5: Find similar to a Saiyan note**

> Use jkw-obs `find_similar` with the text from `Admin/Saiyan.md` — top 5.

Expected: training/workout-adjacent notes appear (whatever you have).

- [ ] **Step 6: Incremental reindex catches a new note**

In Claude Code:
> Use jkw-obs `write_kb_note` with filename `plan-2-smoke.md`, subdir `ad-hoc`, content `# Plan 2 smoke\n\nMeningioma WHO grading and methylation classification.`

Then:
> Use jkw-obs `reindex` with scope `incremental`.

Expected: `added=1 updated=0 unchanged=N removed=0`.

Then:
> Use jkw-obs `search_vault` with query "WHO grading meningioma" — top 5.

Expected: `kb/dreamingmachine/ad-hoc/plan-2-smoke.md` appears in the top results.

- [ ] **Step 7: Tag plan-2-complete**

```bash
cd /Users/jinchiwei/arcadia/臥龍/obsidian/jkw_obs-mcp
git tag plan-2-complete
git push origin main --tags
```

---

## Self-Review Checklist (run before declaring Plan 2 done)

- [ ] All 9 tasks committed
- [ ] `pytest -v` shows ~30+ tests passing (Plan 1 + new ones)
- [ ] First reindex on real vault completed; db file exists
- [ ] `search_vault` returns sensible results for at least 3 different queries
- [ ] Incremental reindex picks up new + modified + deleted files (verified manually)
- [ ] `git tag plan-2-complete` exists, pushed to origin
- [ ] No TODO / FIXME / placeholder strings in code or plan

When all boxes ticked, Plan 2 is done. Plan 3 (Compilers framework + papers/clips) is next.

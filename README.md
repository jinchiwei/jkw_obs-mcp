# jkw_obs-mcp

Personal second-brain MCP server over an Obsidian vault. Exposes 10 tools (7 cross-platform, 3 macOS-only) for reading, searching, and writing notes — plus daily-review generation, email/PDF compilation, and a kb-style learning recorder.

Cross-machine: every node runs its own MCP server but reads/writes through a shared `jkw_obs-brain` git repo, so a learning recorded on one machine surfaces in `search_vault` on another within ~5 minutes (cache window).

## Tools

All platforms (Darwin + Linux):

- `read_note(path)` — read any markdown file in the vault
- `list_notes(subdir="")` — list .md files (optionally scoped)
- `write_kb_note(filename, content, subdir="ad-hoc")` — write only to `kb/<this-machine>/`
- `search_vault(query, k=8)` — semantic search across the vault (FastEmbed + sqlite-vec)
- `find_similar(path, k=5)` — find notes similar to a given file
- `reindex(scope="incremental")` — rebuild the embedding index
- `record_learning(category, title, content, ...)` — kb-shaped learning note with frontmatter, auto-commit + push to brain repo

macOS-only (require Versa Bedrock, EventKit, or Gmail OAuth):

- `compile_raw(...)` — PDF/markdown → vault-formatted clip via Versa Bedrock
- `compile_email(...)` — Gmail thread → vault-formatted summary
- `generate_daily_review()` — daily review pulling Calendar, Mission Log, BRAIN Lab, CPH, CurieDx

The MCP server filters the tool list at startup based on `platform.system()` — Linux clusters get 7 tools, your Mac gets all 10.

## Install

### macOS (personal machine — uses the `deepdream` conda env)

```bash
git clone git@github.com:jinchiwei/jkw_obs-mcp.git ~/arcadia/jkw_obs-mcp
cd ~/arcadia/jkw_obs-mcp

source ~/miniconda3/etc/profile.d/conda.sh
conda activate deepdream
pip install -e ".[dev,mac,gmail]"

jkw-obs-mcp-setup   # walks through 6 steps: config dir, machines.toml,
                    # Gmail OAuth, launchd, brain repo, MCP registration
```

### Linux cluster (scs / fac / cph / teal / cdx)

One-shot bootstrap from a fresh login shell:

```bash
curl -fsSL https://raw.githubusercontent.com/jinchiwei/jkw_obs-mcp/main/scripts/bootstrap.sh | bash
```

What it does (idempotent — re-running is safe):

1. Verifies Python 3.11+ on PATH
2. Clones (or pulls) jkw_obs-mcp into `~/arcadia/jkw_obs-mcp`
3. Creates `.venv/` (uv if available, else stdlib `python3 -m venv`)
4. `pip install -e .` into the venv
5. Runs `jkw-obs-mcp-setup` — clones the brain repo, writes config, registers MCP

After bootstrap, source the venv (`source ~/arcadia/jkw_obs-mcp/.venv/bin/activate`) so the `jkw-obs-mcp` entrypoint is on PATH for Claude Code subprocesses.

### New machine? Register it in `machines.toml`

`machines.toml` maps hostnames to short machine IDs. Add an entry, commit + push, re-run setup on the new node:

```toml
[scs]
hostname_aliases = ["callosum"]
os = "linux"
```

Hostname matching is case-sensitive. The installer's machines-check step refuses to run if the current hostname isn't registered — deliberate human gate, not auto-detect, so kb writes don't land under a guessed machine ID.

## How it's wired into Claude Code

`jkw-obs-mcp-setup` Step 6 runs `claude mcp add` with absolute paths so Claude Code can spawn the server without activating any venv:

```bash
claude mcp add --scope user jkw-obs <abs-path-to-venv>/bin/jkw-obs-mcp
claude mcp list   # → "jkw-obs: ✓ Connected"
```

To remove later: `claude mcp remove jkw-obs -s user`.

## Cross-machine sync (brain repo)

`jkw_obs-brain` is a separate repo containing `kb/<machine>/` per-node sandboxes plus shared learnings. Every machine clones it; `search_vault` and `find_similar` pull-with-cache (max age 5 min) before serving, and `reindex` runs automatically when a pull moves HEAD (Plan 8.5). End-to-end: a `record_learning` call on machine A is searchable on machine B within ~5 minutes, no manual reindex.

`record_learning` writes the file, commits, and pushes (single retry on remote conflict). Offline: file is still written + committed locally, sync delayed.

## Daily review (macOS only)

A launchd agent fires `jkw-obs-mcp-daily-review` every 5 minutes while awake. The runner generates a daily review markdown into the vault (Mission Log, BRAIN Lab, CPH rotating, CurieDx focus areas).

Plist: `services/launchd/com.jinchiwei.jkw-obs-mcp.daily-review.plist` — installed by `jkw-obs-mcp-setup` Step 4 with the venv's Python path filled in.

UCSF live Calendar requires VPN/wifi; the runner degrades gracefully when off-VPN.

## Config

`~/.config/jkw-obs-mcp/config.toml`:

```toml
[paths]
vault_root = "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs"

[machine]
id = "dreamingmachine"

[generation]
daily_review_enabled = false
```

Written by Step 5 of `jkw-obs-mcp-setup`. The `id` field MUST match an entry in `machines.toml`.

## Develop

```bash
pytest -v                    # full test suite
pytest tests/test_mcp_*.py   # MCP server tests
```

Source layout under `src/jkw_obs_mcp/`: `mcp/` (server + tool dispatch), `adapter/` (vault, calendar, gmail readers), `compilers/` (papers, clips, email), `generators/` (daily review), `indexer/` (FastEmbed + sqlite-vec), `brain_sync/`, `learnings/`, `installer/`, `triggers/`.

Design docs and plan history: `docs/superpowers/{designs,plans}/`. Each plan is its own markdown file; together they describe Plans 1 through 8.5.

# jkw_obs-mcp

Personal second-brain MCP server over an Obsidian vault. See the design doc
at `docs/superpowers/plans/` for the full architecture.

## Install (Plan 1 manual setup; full install.sh ships in Plan 6)

This project uses the existing `deepdream` conda env on the user's Mac (per the
project's `feedback_conda_env` convention — never install into base/system Python).

```bash
# 1. Clone and enter
git clone git@github.com:jinchiwei/jkw_obs-mcp.git
cd jkw_obs-mcp

# 2. Install into the deepdream conda env
source ~/miniconda3/etc/profile.d/conda.sh
conda activate deepdream
pip install -e ".[dev]"

# 3. Run tests to confirm setup
pytest -v

# 4. Bootstrap config
mkdir -p ~/.config/jkw-obs-mcp
cat > ~/.config/jkw-obs-mcp/config.toml <<'EOF'
[paths]
vault_root = "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/jkw_obs"

[machine]
id = "dreamingmachine"

[generation]
daily_review_enabled = false
EOF

# 5. Smoke test the entry point
jkw-obs-mcp  # exits cleanly if config + machine_id match; runs stdio server otherwise.
```

## Wire into Claude Code

Use the `claude mcp add` CLI to register the server (Claude Code stores MCP
config in `~/.claude.json`, not a separate `mcp_servers.json`):

```bash
claude mcp add --scope user jkw-obs /Users/jinchiwei/miniconda3/envs/deepdream/bin/jkw-obs-mcp
claude mcp list   # should show "jkw-obs: ✓ Connected"
```

Restart Claude Code (or just `/mcp` again). The three tools (`read_note`,
`list_notes`, `write_kb_note`) should appear.

To remove later: `claude mcp remove jkw-obs -s user`.

## Tools (Plan 1)

- `read_note(path)` — read any markdown file in the vault
- `list_notes(subdir="")` — list all .md files (optionally scoped)
- `write_kb_note(filename, content, subdir="ad-hoc")` — write only to `kb/<this-machine>/`

Embeddings, semantic search, compilers, calendar, daily review — all in later plans.

## Status

Plan 1 of 7. See `docs/superpowers/plans/` for the full roadmap.

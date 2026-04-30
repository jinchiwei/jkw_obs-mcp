#!/usr/bin/env bash
# bootstrap.sh — single-command setup for jkw-obs-mcp on a fresh Linux cluster.
#
# Usage: curl -fsSL https://raw.githubusercontent.com/jinchiwei/jkw_obs-mcp/main/scripts/bootstrap.sh | bash
#
# What this does:
#   1. Verifies Python 3.11+ is on PATH
#   2. Ensures ~/arcadia/ exists
#   3. Clones jkw_obs-mcp to ~/arcadia/jkw_obs-mcp (or pulls if present)
#   4. Creates ~/arcadia/jkw_obs-mcp/.venv (via uv if available, else python3 -m venv)
#   5. pip install -e . into the venv
#   6. Execs jkw-obs-mcp-setup (which clones brain repo, writes config, registers MCP)
#
# Idempotent. Re-running is safe.

set -euo pipefail

REPO_URL="https://github.com/jinchiwei/jkw_obs-mcp.git"
ARCADIA_DIR="$HOME/arcadia"
REPO_DIR="$ARCADIA_DIR/jkw_obs-mcp"
VENV_DIR="$REPO_DIR/.venv"

echo "==> jkw-obs-mcp bootstrap"

# Step 1: Python 3.11+
echo "Step 1: checking Python version"
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found on PATH. Install Python 3.11+ and re-run." >&2
    exit 1
fi
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    echo "ERROR: Python $PY_VERSION found; need 3.11+. Install a newer Python and re-run." >&2
    exit 1
fi
echo "  -> Python $PY_VERSION"

# Step 2: ~/arcadia/
echo "Step 2: ensuring $ARCADIA_DIR exists"
mkdir -p "$ARCADIA_DIR"
echo "  -> $ARCADIA_DIR"

# Step 3: clone or pull jkw_obs-mcp
echo "Step 3: jkw_obs-mcp repo"
if [ -d "$REPO_DIR/.git" ]; then
    echo "  -> already cloned at $REPO_DIR; pulling latest"
    git -C "$REPO_DIR" pull --ff-only
else
    echo "  -> cloning $REPO_URL to $REPO_DIR"
    git clone "$REPO_URL" "$REPO_DIR"
fi

# Step 4: create venv
echo "Step 4: virtualenv at $VENV_DIR"
if [ -d "$VENV_DIR" ]; then
    echo "  -> already exists; reusing"
elif command -v uv >/dev/null 2>&1; then
    echo "  -> using uv to create venv"
    (cd "$REPO_DIR" && uv venv)
else
    echo "  -> using stdlib python3 -m venv"
    python3 -m venv "$VENV_DIR"
fi

# Step 5: install package
echo "Step 5: installing jkw_obs_mcp package"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
if command -v uv >/dev/null 2>&1; then
    (cd "$REPO_DIR" && uv pip install -e .)
else
    pip install --upgrade pip
    (cd "$REPO_DIR" && pip install -e .)
fi
echo "  -> installed"

# Step 6: run jkw-obs-mcp-setup
echo "Step 6: running jkw-obs-mcp-setup"
jkw-obs-mcp-setup

echo
echo "==> Bootstrap complete."
echo
echo "To use: in a new shell, run \`source $VENV_DIR/bin/activate\` to get jkw-obs-mcp on PATH."
echo "Or in Claude Code: the tool surface should now include jkw-obs (7 tools on Linux)."

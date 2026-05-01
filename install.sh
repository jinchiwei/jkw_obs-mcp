#!/usr/bin/env bash
# install.sh — entrypoint redirector. The actual install paths live elsewhere
# now that Plans 6 and 8 shipped:
#
#   - macOS:        pip install -e ".[dev,mac,gmail]" into the deepdream conda env,
#                   then run `jkw-obs-mcp-setup` (see README.md)
#   - Linux node:   curl ... scripts/bootstrap.sh | bash (see README.md)
#
# Kept as a stub so existing muscle memory (./install.sh) prints a useful pointer.

set -e

if [[ "$(uname)" == "Darwin" ]]; then
  cat <<'EOF'
==> macOS detected.

Run the steps in README.md → "Install / macOS":

  source ~/miniconda3/etc/profile.d/conda.sh
  conda activate deepdream
  pip install -e ".[dev,mac,gmail]"
  jkw-obs-mcp-setup

EOF
else
  cat <<'EOF'
==> Linux detected.

Use the cluster bootstrap (curlable, idempotent):

  curl -fsSL https://raw.githubusercontent.com/jinchiwei/jkw_obs-mcp/main/scripts/bootstrap.sh | bash

Or, if you've already cloned this repo, run scripts/bootstrap.sh directly:

  bash scripts/bootstrap.sh

EOF
fi

exit 0

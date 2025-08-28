#!/usr/bin/env bash
# Run a single provider review based on configuration
# Usage: run-provider-review.sh <provider> <timeout>
set -euo pipefail

PROVIDER="${1:-}"
TIMEOUT="${2:-120}"

if [ -z "$PROVIDER" ]; then
  echo "Usage: run-provider-review.sh <provider> [timeout]"
  exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PACKAGE_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

# Ensure Claude Code is in PATH if installed in non-standard location
if [[ "$PROVIDER" == "claude" ]] && [ -x "$HOME/.claude/local/claude" ]; then
  export PATH="$HOME/.claude/local:$PATH"
fi

# Generate provider command from configuration
CMD=$(node "$PACKAGE_DIR/lib/generate-provider-command.js" "$PROVIDER" --no-timeout 2>/dev/null)

if [ -z "$CMD" ]; then
  echo "Provider $PROVIDER is disabled or not configured"
  exit 0
fi

# Execute the command with timeout
export PACKAGE_DIR
cd "$PACKAGE_DIR/../"
timeout "$TIMEOUT" bash -c "$CMD"
#!/usr/bin/env bash
# Run a single provider review using secure command execution
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

# Unset sensitive environment variables before running providers
# Claude must use local Keychain auth, not API tokens
unset GH_TOKEN
unset GITHUB_TOKEN
unset ANTHROPIC_API_KEY
unset ANTHROPIC_AUTH_TOKEN

# Hint tool name to normalizer via env
case "$PROVIDER" in
  claude) export TOOL="claude-code" ;;
  codex)  export TOOL="codex-cli"  ;;
  gemini) export TOOL="gemini-cli"  ;;
esac

# Provide PR/run context to normalizer
export RUN_URL="https://github.com/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
export PR_REPO="${GITHUB_REPOSITORY#*/}"
export PR_NUMBER
export PR_BRANCH="${GITHUB_REF_NAME:-}"
export HEAD_SHA="${GITHUB_SHA:-}"

# Expose configured model for the provider
MODEL_FROM_CONFIG=$(node "$PACKAGE_DIR/lib/config-loader.js" show 2>/dev/null | jq -r \
  ".providers.${PROVIDER}.model // (\"gpt-5\")" 2>/dev/null || true)
if [ -n "$MODEL_FROM_CONFIG" ] && [ "$MODEL_FROM_CONFIG" != "null" ]; then
  export MODEL="$MODEL_FROM_CONFIG"
fi

# Export PACKAGE_DIR for the execute-provider script
export PACKAGE_DIR

# Use the new secure execution system
# This avoids shell injection vulnerabilities by:
# 1. Using structured commands instead of shell strings
# 2. Injecting context consistently for all providers
# 3. Executing binaries directly without bash -c
cd "$PACKAGE_DIR/../"

# Execute with built-in timeout handling
if command -v node >/dev/null 2>&1; then
  # Use the secure Node.js executor
  node "$PACKAGE_DIR/lib/execute-provider.js" "$PROVIDER" --timeout "$TIMEOUT" || {
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 124 ]; then
      echo "Provider $PROVIDER timed out after ${TIMEOUT} seconds"
    else
      echo "Provider $PROVIDER failed with exit code $EXIT_CODE"
    fi
    exit $EXIT_CODE
  }
else
  echo "Error: Node.js is required for secure provider execution" >&2
  exit 1
fi

#!/usr/bin/env bash
# Run the same review locally (outside Actions).
set -euo pipefail

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PACKAGE_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

# Check if we're in the right place
if [ ! -f "$PACKAGE_DIR/prompts/review.core.md" ]; then
  echo "Error: Cannot find review prompts. Expected location: $PACKAGE_DIR/prompts/"
  exit 1
fi

# Change to repository root (two levels up from scripts/)
cd "$PACKAGE_DIR/../"

# Ensure Claude Code is in PATH if installed in non-standard location
if [ -x "$HOME/.claude/local/claude" ]; then
  export PATH="$HOME/.claude/local:$PATH"
fi

bash "$PACKAGE_DIR/scripts/auth-check.sh"

mkdir -p "$PACKAGE_DIR/workspace/context" "$PACKAGE_DIR/workspace/reports"

# Minimal local context (assumes current branch is a PR branch tracking origin)
git diff --patch origin/$(git rev-parse --abbrev-ref --symbolic-full-name @{upstream} | cut -d'/' -f2-) > "$PACKAGE_DIR/workspace/context/diff.patch" || true
git diff --name-only > "$PACKAGE_DIR/workspace/context/files.txt" || true

cat > "$PACKAGE_DIR/workspace/context/pr.json" <<'JSON'
{"repo":"local","number":0,"head_sha":"LOCAL","branch":"LOCAL","link":"https://local/pr"}
JSON

# Optional tests
if [ -n "${TEST_CMD:-pytest tests/}" ]; then
  set +e
  echo "\$ ${TEST_CMD:-pytest tests/}" > "$PACKAGE_DIR/workspace/context/tests.txt"
  ${TEST_CMD:-pytest tests/} >> "$PACKAGE_DIR/workspace/context/tests.txt" 2>&1
  echo "== exit:$? ==" >> "$PACKAGE_DIR/workspace/context/tests.txt"
  set -e
fi

# Providers (read-only)
unset ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY

# Run all providers in parallel for speed
echo "Running all reviews in parallel..."

# Claude Code - use Sonnet 4 for speed, with --output-format json
(echo "Starting Claude Code review (Sonnet 4)..." && \
  claude -p "$(cat "$PACKAGE_DIR/prompts/review.claude.md"; echo; cat "$PACKAGE_DIR/prompts/review.core.md")" \
  --model sonnet \
  --permission-mode plan \
  --output-format json \
  2>/dev/null \
  | node "$PACKAGE_DIR/scripts/normalize-json.js" \
  > "$PACKAGE_DIR/workspace/reports/claude-code.json" || \
  echo '{"tool":"claude-code","model":"error","error":"Claude error","findings":[],"must_fix":[],"exit_criteria":{"ready_for_pr":false}}' > "$PACKAGE_DIR/workspace/reports/claude-code.json") &

# Codex CLI 0.25.0 - use fast reasoning effort for speed
(echo "Starting Codex CLI review (fast reasoning)..." && \
  codex exec --output-last-message "$PACKAGE_DIR/workspace/reports/codex-cli.raw.txt" \
  -s read-only \
  -C . \
  -c model_reasoning_effort="low" \
  "$(cat "$PACKAGE_DIR/prompts/review.codex.md"; echo; cat "$PACKAGE_DIR/prompts/review.core.md")" \
  >/dev/null 2>&1 && \
  cat "$PACKAGE_DIR/workspace/reports/codex-cli.raw.txt" | node "$PACKAGE_DIR/scripts/normalize-json.js" > "$PACKAGE_DIR/workspace/reports/codex-cli.json" && \
  rm -f "$PACKAGE_DIR/workspace/reports/codex-cli.raw.txt" || \
  echo '{"tool":"codex-cli","model":"error","error":"Codex error","findings":[],"must_fix":[],"exit_criteria":{"ready_for_pr":false}}' > "$PACKAGE_DIR/workspace/reports/codex-cli.json") &

# Gemini CLI - use 2.5 Pro for production quality
(echo "Starting Gemini CLI review (2.5 Pro)..." && \
  (echo "$(cat "$PACKAGE_DIR/prompts/review.gemini.md"; echo; \
    echo 'CRITICAL: Output ONLY the JSON object, no markdown code fences or other text.'; \
    cat "$PACKAGE_DIR/prompts/review.core.md")" | \
    GEMINI_API_KEY="" gemini -m gemini-2.5-pro -p) \
  2>/dev/null \
  | node "$PACKAGE_DIR/scripts/normalize-json.js" \
  > "$PACKAGE_DIR/workspace/reports/gemini-cli.json" || \
  echo '{"tool":"gemini-cli","model":"error","error":"Gemini error","findings":[],"must_fix":[],"exit_criteria":{"ready_for_pr":false}}' > "$PACKAGE_DIR/workspace/reports/gemini-cli.json") &

# Wait for all parallel jobs to complete
wait
echo "All reviews completed."

cd "$PACKAGE_DIR" && npm install --no-audit --no-fund
node "$PACKAGE_DIR/scripts/aggregate-reviews.mjs" || true
echo "Gate: $(cat "$PACKAGE_DIR/workspace/gate.txt")"
echo "See $PACKAGE_DIR/workspace/summary.md"
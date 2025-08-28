#!/usr/bin/env bash
# Test individual CLIs for debugging
set -euo pipefail

# Ensure Claude Code is in PATH if installed in non-standard location
if [ -x "$HOME/.claude/local/claude" ]; then
  export PATH="$HOME/.claude/local:$PATH"
fi

# Unset API keys
unset ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY

echo "Testing individual CLIs..."
echo "========================="

# Prepare context
mkdir -p .review-pipeline/workspace/context .review-pipeline/workspace/reports

# Build minimal context
echo "Building review context..."
git diff --staged --patch > .review-pipeline/workspace/context/diff.patch
git diff --staged --name-only > .review-pipeline/workspace/context/files.txt

cat > .review-pipeline/workspace/context/pr.json <<'JSON'
{"repo":"pyrepl3","number":0,"head_sha":"LOCAL","branch":"test-review-pipeline","link":"https://local/pr"}
JSON

echo "Context files created:"
ls -la .review-pipeline/workspace/context/

# Simple test prompt
TEST_PROMPT="Review this diff and output a simple JSON with findings:
$(cat .review-pipeline/workspace/context/diff.patch)

Output JSON like: {\"tool\":\"test\",\"findings\":[\"issue1\",\"issue2\"]}"

echo ""
echo "Testing Claude..."
echo "$TEST_PROMPT" | claude -p --permission-mode plan > .review-pipeline/workspace/reports/claude-test.txt 2>&1 &
CLAUDE_PID=$!

echo "Testing Codex..."
echo "$TEST_PROMPT" | codex exec > .review-pipeline/workspace/reports/codex-test.txt 2>&1 &
CODEX_PID=$!

echo "Testing Gemini..."
GEMINI_API_KEY="" echo "$TEST_PROMPT" | gemini -p > .review-pipeline/workspace/reports/gemini-test.txt 2>&1 &
GEMINI_PID=$!

echo ""
echo "Waiting for CLIs to complete (this may take a few minutes)..."
echo "PIDs: Claude=$CLAUDE_PID, Codex=$CODEX_PID, Gemini=$GEMINI_PID"

# Wait with timeout
TIMEOUT=300  # 5 minutes
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  if ! kill -0 $CLAUDE_PID 2>/dev/null && \
     ! kill -0 $CODEX_PID 2>/dev/null && \
     ! kill -0 $GEMINI_PID 2>/dev/null; then
    echo "All CLIs completed!"
    break
  fi
  sleep 5
  ELAPSED=$((ELAPSED + 5))
  echo "Waiting... ${ELAPSED}s elapsed"
done

echo ""
echo "Results:"
echo "--------"
for file in .review-pipeline/workspace/reports/*-test.txt; do
  if [ -f "$file" ]; then
    echo ""
    echo "$(basename $file):"
    head -20 "$file"
    echo "..."
  fi
done
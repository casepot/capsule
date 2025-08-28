#!/usr/bin/env bash
# Run the same review locally (outside Actions).
set -euo pipefail

if [ ! -f "prompts/review.core.md" ]; then
  echo "Run from repo root."
  exit 1
fi

# Ensure Claude Code is in PATH if installed in non-standard location
if [ -x "$HOME/.claude/local/claude" ]; then
  export PATH="$HOME/.claude/local:$PATH"
fi

bash scripts/auth-check.sh

mkdir -p review/context review/reports

# Minimal local context (assumes current branch is a PR branch tracking origin)
git diff --patch origin/$(git rev-parse --abbrev-ref --symbolic-full-name @{upstream} | cut -d'/' -f2-) > review/context/diff.patch || true
git diff --name-only > review/context/files.txt || true

cat > review/context/pr.json <<'JSON'
{"repo":"local","number":0,"head_sha":"LOCAL","branch":"LOCAL","link":"https://local/pr"}
JSON

# Optional tests
if [ -n "${TEST_CMD:-pytest tests/}" ]; then
  set +e
  echo "\$ ${TEST_CMD:-pytest tests/}" > review/context/tests.txt
  ${TEST_CMD:-pytest tests/} >> review/context/tests.txt 2>&1
  echo "== exit:$? ==" >> review/context/tests.txt
  set -e
fi

# Providers (read-only)
unset ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY

# Run all providers in parallel for speed
echo "Running all reviews in parallel..."

# Claude Code - use Sonnet 4 for speed, with --output-format json
(echo "Starting Claude Code review (Sonnet 4)..." && \
  claude -p "$(cat prompts/review.claude.md; echo; cat prompts/review.core.md)" \
  --model sonnet \
  --permission-mode plan \
  --output-format json \
  2>/dev/null \
  | node scripts/normalize-json.js \
  > review/reports/claude-code.json || \
  echo '{"tool":"claude-code","model":"error","error":"Claude error","findings":[],"must_fix":[],"exit_criteria":{"ready_for_pr":false}}' > review/reports/claude-code.json) &

# Codex CLI 0.25.0 - use fast reasoning effort for speed
(echo "Starting Codex CLI review (fast reasoning)..." && \
  codex exec --output-last-message review/reports/codex-cli.raw.txt \
  -s read-only \
  -C . \
  -c model_reasoning_effort="low" \
  "$(cat prompts/review.codex.md; echo; cat prompts/review.core.md)" \
  >/dev/null 2>&1 && \
  cat review/reports/codex-cli.raw.txt | node scripts/normalize-json.js > review/reports/codex-cli.json && \
  rm -f review/reports/codex-cli.raw.txt || \
  echo '{"tool":"codex-cli","model":"error","error":"Codex error","findings":[],"must_fix":[],"exit_criteria":{"ready_for_pr":false}}' > review/reports/codex-cli.json) &

# Gemini CLI - use 2.5 Pro for production quality
(echo "Starting Gemini CLI review (2.5 Pro)..." && \
  (echo "$(cat prompts/review.gemini.md; echo; \
    echo 'CRITICAL: Output ONLY the JSON object, no markdown code fences or other text.'; \
    cat prompts/review.core.md)" | \
    GEMINI_API_KEY="" gemini -m gemini-2.5-pro -p) \
  2>/dev/null \
  | node scripts/normalize-json.js \
  > review/reports/gemini-cli.json || \
  echo '{"tool":"gemini-cli","model":"error","error":"Gemini error","findings":[],"must_fix":[],"exit_criteria":{"ready_for_pr":false}}' > review/reports/gemini-cli.json) &

# Wait for all parallel jobs to complete
wait
echo "All reviews completed."

npm install --no-audit --no-fund ajv@8 ajv-formats@3
node scripts/aggregate-reviews.mjs || true
echo "Gate: $(cat review/gate.txt)"
echo "See review/summary.md"
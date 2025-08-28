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
claude -p "$(cat prompts/review.claude.md; echo; cat prompts/review.core.md)" \
  --permission-mode plan --output-format json \
  > review/reports/claude-code.json
codex exec "$(cat prompts/review.codex.md; echo; cat prompts/review.core.md)" \
  > review/reports/codex-cli.json
GEMINI_API_KEY="" gemini -p "$(cat prompts/review.gemini.md; echo; cat prompts/review.core.md)" \
  > review/reports/gemini-cli.json

npm install --no-audit --no-fund ajv@8 ajv-formats@3
node scripts/aggregate-reviews.mjs || true
echo "Gate: $(cat review/gate.txt)"
echo "See review/summary.md"
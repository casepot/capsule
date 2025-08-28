#!/usr/bin/env bash
set -euo pipefail

red()  { printf "\033[31m%s\033[0m\n" "$*" >&2; }
grn()  { printf "\033[32m%s\033[0m\n" "$*"; }
chk()  { printf "• %s\n" "$*"; }

# Handle Claude Code's non-standard installation
# Claude typically installs to ~/.claude/local/claude
if [ -x "$HOME/.claude/local/claude" ] && ! type claude >/dev/null 2>&1; then
  export PATH="$HOME/.claude/local:$PATH"
  chk "Added Claude Code to PATH from ~/.claude/local"
fi

# 1) Absolutely forbid API key usage (metered billing)
if [ -n "${ANTHROPIC_API_KEY-}" ] || [ -n "${OPENAI_API_KEY-}" ] || [ -n "${GEMINI_API_KEY-}" ]; then
  red "API key envs must NOT be set (ANTHROPIC_API_KEY/OPENAI_API_KEY/GEMINI_API_KEY). Unset them and use subscription/OAuth logins."
  exit 1
fi
chk "No API key envs detected."

# 2) Required CLIs + gh
# Use type instead of command to detect aliases too
missing_bins=""
for bin in claude codex gemini gh jq; do
  if ! type "$bin" >/dev/null 2>&1; then
    missing_bins="${missing_bins} $bin"
  fi
done

if [ -n "$missing_bins" ]; then
  red "Missing required binaries:$missing_bins"
  echo "Note: If CLIs are installed but not in PATH, ensure they're available"
  echo "      Claude Code can be installed from: https://docs.anthropic.com/en/docs/claude-code/setup"
  echo "      Codex CLI can be installed via: npm install -g @openai/codex"
  echo "      Gemini CLI can be installed from: https://github.com/google-gemini/gemini-cli"
  exit 1
fi
chk "All required CLIs present (claude, codex, gemini, gh, jq)."

# 3) Auth probes (headless, read-only)
auth_probe() {
  local name="$1"; shift
  local cmd=("$@")
  if ! "${cmd[@]}" >/dev/null 2>&1; then
    red "$name not authenticated. Please log in locally on this runner."
    case "$name" in
      "Claude Code") echo "  Login: run 'claude' then use your Claude.ai Pro/Max account (/login)";;
      "Codex CLI")   echo "  Login: run 'codex' and choose 'Sign in with ChatGPT'";;
      "Gemini CLI")  echo "  Login: run 'gemini' and choose OAuth with your Google account";;
    esac
    exit 1
  fi
  chk "$name auth probe OK."
}

# Claude Code: headless print; JSON ensures the CLI is fully operational
# Try claude command first, then fall back to direct path
if type claude >/dev/null 2>&1; then
  auth_probe "Claude Code" claude -p "ping" --output-format json
elif [ -x "$HOME/.claude/local/claude" ]; then
  auth_probe "Claude Code" "$HOME/.claude/local/claude" -p "ping" --output-format json
else
  red "Claude Code not found in PATH or at ~/.claude/local/claude"
  exit 1
fi
# Codex CLI: use exec mode for non-interactive test
auth_probe "Codex CLI" codex exec "echo test"
# Gemini CLI: non-interactive prompt
auth_probe "Gemini CLI" bash -lc 'GEMINI_API_KEY="" gemini -p "ping"'

grn "Auth checks passed."
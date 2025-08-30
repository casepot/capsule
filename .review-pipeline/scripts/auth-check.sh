#!/usr/bin/env bash
set -euo pipefail

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PACKAGE_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

red()  { printf "\033[31m%s\033[0m\n" "$*" >&2; }
grn()  { printf "\033[32m%s\033[0m\n" "$*"; }
ylw()  { printf "\033[33m%s\033[0m\n" "$*"; }
chk()  { printf "• %s\n" "$*"; }

# Load configuration to check which providers are enabled
load_config() {
  local config_file="$PACKAGE_DIR/config/pipeline.config.json"
  if [ ! -f "$config_file" ]; then
    ylw "Warning: No pipeline config found, checking all providers"
    echo "all"
    return
  fi
  
  # Get enabled providers using jq
  if type jq >/dev/null 2>&1; then
    local enabled=""
    for provider in claude codex gemini; do
      local is_enabled=$(jq -r ".providers.$provider.enabled // true" < "$config_file")
      if [ "$is_enabled" = "true" ]; then
        enabled="${enabled}${provider} "
      fi
    done
    echo "$enabled"
  else
    echo "all"
  fi
}

# Load provider manifest to get CLI detection info
get_provider_cli_path() {
  local provider="$1"
  local manifest="$PACKAGE_DIR/config/providers/${provider}.manifest.json"
  
  if [ ! -f "$manifest" ]; then
    return 1
  fi
  
  # Try standard command first
  local cmd=$(jq -r '.cli.command // empty' < "$manifest" 2>/dev/null)
  if [ -n "$cmd" ] && type "$cmd" >/dev/null 2>&1; then
    echo "$cmd"
    return 0
  fi
  
  # Try detection paths
  local detection_count=$(jq '.cli.detection | length' < "$manifest" 2>/dev/null || echo 0)
  for ((i=0; i<detection_count; i++)); do
    local detection_type=$(jq -r ".cli.detection[$i].type" < "$manifest" 2>/dev/null)
    local detection_value=$(jq -r ".cli.detection[$i].value" < "$manifest" 2>/dev/null)
    
    if [ "$detection_type" = "command" ]; then
      if type "$detection_value" >/dev/null 2>&1; then
        echo "$detection_value"
        return 0
      fi
    elif [ "$detection_type" = "path" ]; then
      # Expand ~ to home directory
      detection_value="${detection_value/#\~/$HOME}"
      if [ -x "$detection_value" ]; then
        echo "$detection_value"
        return 0
      fi
    fi
  done
  
  return 1
}

# Note: auth check commands are hardcoded in check_provider_auth() for security
# Never execute commands from manifest files to prevent command injection

# Get environment variables to unset from manifest
get_env_vars_to_unset() {
  local provider="$1"
  local manifest="$PACKAGE_DIR/config/providers/${provider}.manifest.json"
  
  if [ ! -f "$manifest" ]; then
    return
  fi
  
  jq -r '.authentication.env_vars_to_unset[]? // empty' < "$manifest" 2>/dev/null
}

# Check for jq availability
if ! type jq >/dev/null 2>&1; then
  red "jq is required but not installed. Please install it."
  echo "  macOS: brew install jq"
  echo "  Ubuntu: sudo apt install jq"
  exit 1
fi

# 1) Check for API key environment variables
api_key_vars=()
for provider in claude codex gemini; do
  vars_to_check=$(get_env_vars_to_unset "$provider")
  for var in $vars_to_check; do
    if [ -n "${!var:-}" ]; then
      api_key_vars+=("$var")
    fi
  done
done

# Also check common API key variables
for var in ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY; do
  if [ -n "${!var:-}" ]; then
    api_key_vars+=("$var")
  fi
done

if [ ${#api_key_vars[@]} -gt 0 ]; then
  red "API key environment variables must NOT be set:"
  for var in "${api_key_vars[@]}"; do
    red "  - $var is set"
  done
  echo ""
  echo "Please unset these variables and use subscription/OAuth authentication instead:"
  echo "  unset ${api_key_vars[*]}"
  exit 1
fi
chk "No API key environment variables detected."

# 2) Check which providers are enabled
enabled_providers=$(load_config)
if [ "$enabled_providers" = "all" ]; then
  enabled_providers="claude codex gemini"
fi

if [ -z "$enabled_providers" ]; then
  ylw "Warning: No providers enabled in configuration"
  exit 0
fi

chk "Checking enabled providers: $enabled_providers"

# 3) Check required binaries
missing_bins=""
for bin in gh jq node npm; do
  if ! type "$bin" >/dev/null 2>&1; then
    missing_bins="${missing_bins} $bin"
  fi
done

if [ -n "$missing_bins" ]; then
  red "Missing required system binaries:$missing_bins"
  echo "Please install missing binaries."
  exit 1
fi
chk "Required system binaries present (gh, jq, node, npm)."

# 4) Check provider CLIs and authentication
auth_failures=0

check_provider_auth() {
  local provider="$1"
  local display_name="$2"
  
  # Get CLI path from manifest
  local cli_path=$(get_provider_cli_path "$provider")
  if [ -z "$cli_path" ]; then
    red "$display_name CLI not found"
    
    # Get installation instructions from manifest
    local manifest="$PACKAGE_DIR/config/providers/${provider}.manifest.json"
    if [ -f "$manifest" ]; then
      local service=$(jq -r '.authentication.service // "subscription"' < "$manifest")
      local login_cmd=$(jq -r '.authentication.login_command // ""' < "$manifest")
      echo "  Installation: Check provider documentation"
      echo "  Service required: $service"
      if [ -n "$login_cmd" ]; then
        echo "  Login command: $login_cmd"
      fi
    fi
    return 1
  fi
  
  chk "$display_name CLI found: $cli_path"
  
  # Handle special case for Claude non-standard path
  if [[ "$provider" == "claude" && "$cli_path" == "$HOME/.claude/local/claude" ]]; then
    if ! echo "$PATH" | grep -q "$HOME/.claude/local"; then
      export PATH="$HOME/.claude/local:$PATH"
      chk "Added Claude Code to PATH from ~/.claude/local"
    fi
  fi
  
  # Run auth check using hardcoded commands for security
  # Never use eval with user-controlled input
  local auth_success=false
  
  case "$provider" in
    claude)
      # Hardcoded auth check for Claude
      # Must unset all tokens to force local Keychain auth
      if (unset GH_TOKEN GITHUB_TOKEN GITHUB_ACTIONS ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN; claude -p 'echo test' 2>/dev/null); then
        auth_success=true
      fi
      ;;
    codex)
      # Hardcoded auth check for Codex
      if codex exec -s read-only 'echo test' >/dev/null 2>&1; then
        auth_success=true
      fi
      ;;
    gemini)
      # Hardcoded auth check for Gemini
      # Set GEMINI_API_KEY to empty to force OAuth auth
      if GEMINI_API_KEY='' gemini -p 'ping' 2>/dev/null; then
        auth_success=true
      fi
      ;;
    *)
      ylw "Warning: Unknown provider '$provider' for auth check"
      return 0
      ;;
  esac
  
  if [ "$auth_success" = "true" ]; then
    grn "✓ $display_name authenticated"
    return 0
  else
    red "✗ $display_name not authenticated"
    
    # Get login instructions from manifest
    local manifest="$PACKAGE_DIR/config/providers/${provider}.manifest.json"
    if [ -f "$manifest" ]; then
      local service=$(jq -r '.authentication.service // "subscription"' < "$manifest")
      local login_cmd=$(jq -r '.authentication.login_command // ""' < "$manifest")
      echo "  Service required: $service"
      if [ -n "$login_cmd" ]; then
        echo "  To authenticate, run: $login_cmd"
      fi
    fi
    return 1
  fi
}

# Check each enabled provider
for provider_name in $enabled_providers; do
  case "$provider_name" in
    claude)
      check_provider_auth "claude" "Claude Code" || ((auth_failures++))
      ;;
    codex)
      check_provider_auth "codex" "Codex CLI" || ((auth_failures++))
      ;;
    gemini)
      check_provider_auth "gemini" "Gemini CLI" || ((auth_failures++))
      ;;
    *)
      ylw "Warning: Unknown provider '$provider_name'"
      ;;
  esac
done

# 5) Summary
echo ""
if [ $auth_failures -eq 0 ]; then
  grn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  grn "  Auth checks passed for all providers"
  grn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
  red "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  red "  Auth checks failed for $auth_failures provider(s)"
  red "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  exit 1
fi
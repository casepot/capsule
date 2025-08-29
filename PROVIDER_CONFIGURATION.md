# Multi-Model Review Pipeline: Provider Configuration Guide

## Overview
This document provides comprehensive configuration details for the three AI providers used in the multi-model PR review pipeline: Claude Code, OpenAI Codex CLI, and Google Gemini CLI.

## 1. Claude Code (Anthropic)

### Installation
```bash
# Standard installation (may vary by system)
brew install claude  # macOS

# Non-standard installation path (common issue)
# Claude often installs to: ~/.claude/local/claude
# Add to PATH if needed:
export PATH="$HOME/.claude/local:$PATH"
```

### Authentication
- **Method**: Subscription-based (Claude Pro/Max)
- **NO API KEY**: Keep `ANTHROPIC_API_KEY` unset. This pipeline uses Claude.ai OAuth stored in macOS Keychain.
- **Login**: Via OAuth in browser or CLI authentication

### Available Models
- `opus` - Claude Opus 4.1 (most powerful, slower)
- `sonnet` - Claude Sonnet 4 (balanced, **recommended for production**)
- `haiku` - Claude Haiku (fastest, less capable)
- Full model names: `claude-opus-4-1-20250805`, `claude-sonnet-4-20250514`, etc.

### Configuration Options

#### Basic Command Structure
```bash
claude [OPTIONS] PROMPT
```

#### Key Flags
- `-p, --print` - Non-interactive mode (headless)
- `--model <model>` - Select model (opus/sonnet/haiku)
- `--permission-mode <mode>` - Set permissions:
  - `plan` - Read-only analysis mode (for reviews)
  - `read` - Can read files
  - `write` - Can write/edit files
  - `exec` - Can execute commands
- `--output-format json` - Output as JSON envelope (metadata + result)
- `--continue` - Continue most recent conversation
- `--resume <id>` - Resume specific session
- `--settings <file>` - Load settings from JSON

#### Output Format
When using `--output-format json`, Claude returns an envelope:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "duration_ms": 30310,
  "result": "YOUR_ACTUAL_OUTPUT_HERE",  // String containing the response
  "session_id": "...",
  "total_cost_usd": 0.532,
  "usage": {...},
  "permission_denials": [...]
}
```

#### Production Configuration
```bash
claude -p "PROMPT" \
  --model sonnet \
  --permission-mode plan \
  --output-format json \
  2>/dev/null
```

### Common Issues & Solutions
1. **"Credit balance is too low"**: Caused by an API key env var conflicting with subscription auth. Unset `ANTHROPIC_API_KEY`.
2. **"Path /private/tmp/... was not found"**: Cached session state issue. Clear problematic cache files in `~/.claude/projects/`.
3. **Installation path**: Check `~/.claude/local/claude` if `claude` command not found.

---

## 2. OpenAI Codex CLI

### Installation
```bash
brew install codex  # Currently 0.25.0
```

### Authentication
- **Method**: Subscription-based (ChatGPT Plus/Team)  
- **NO API KEY**: Must unset `OPENAI_API_KEY` environment variable
- **Login**: `codex login` (OAuth via browser)

### Available Models
- **GPT-5** (default) - Most capable
- Configured via `-m, --model <MODEL>` or config file

### Configuration Options

#### Basic Command Structure
```bash
codex [COMMAND] [OPTIONS] [PROMPT]
codex exec [OPTIONS] [PROMPT]  # Non-interactive mode
```

#### Key Commands
- `exec` - Run non-interactively (for automation)
- `login` - Manage authentication
- `apply` - Apply diffs from agent

#### Key Flags for `exec`
- `-c, --config <key=value>` - Override config values:
  - `model_reasoning_effort` - Set reasoning level:
    - `"none"` - No reasoning
    - `"low"` - Fast, minimal reasoning (**recommended for speed**)
    - `"medium"` - Default balanced
    - `"high"` - Deep reasoning (slower)
- `-m, --model <MODEL>` - Select model
- `--json` - Output events as JSONL (newline-delimited JSON)
- `--output-last-message <FILE>` - Save only final message to file
- `-s, --sandbox <MODE>` - Sandbox policy:
  - `read-only` - Read files only
  - `workspace-write` - Write in workspace
  - `danger-full-access` - Full system access
- `-C, --cd <DIR>` - Set working directory
- `--color <always|never|auto>` - Color output control

#### JSONL Output Format
When using `--json`, outputs event stream:
```jsonl
{"type": "task_started", "model_context_window": 400000}
{"type": "agent_reasoning", "text": "..."}
{"type": "agent_message", "message": "..."}
{"type": "token_count", "input_tokens": 5845, "output_tokens": 938}
```

#### Production Configuration
```bash
codex exec --output-last-message output.txt \
  -s read-only \
  -C . \
  -c model_reasoning_effort="low" \
  "PROMPT" \
  >/dev/null 2>&1
```

### Common Issues & Solutions
1. **"Reading prompt from stdin..."**: Appears when piping. Pass prompt as argument instead.
2. **Verbose output with timestamps**: Use `--output-last-message` to get only the final response.
3. **No `-q/--quiet` or standalone `--json` flag**: Despite documentation, these don't exist in 0.25.0.

---

## 3. Google Gemini CLI

### Installation
```bash
brew install gemini-cli  # Currently 0.2.1
```

### Authentication
- **Method**: OAuth-based (Google account)
- **NO API KEY**: Must unset `GEMINI_API_KEY` or set to empty string
- **Login**: Automatic OAuth via browser on first run
- **Cached credentials**: `~/.gemini/oauth_creds.json`

### Available Models

#### Gemini 2.5 Series (Current)
- `gemini-2.5-pro` - Most capable, **recommended for production**
- `gemini-2.5-flash` - Faster, good balance (works well)
- `gemini-2.5-flash-lite` - Fastest/cheapest but **BROKEN** - has thinking mode issues

#### Gemini 2.0 Series (Outdated - DO NOT USE)
- `gemini-2.0-flash` - Deprecated
- `gemini-2.0-flash-exp` - Deprecated

### Configuration Options

#### Basic Command Structure
```bash
gemini [OPTIONS] [COMMAND]
```

#### Key Flags
- `-m, --model` - Select model (required for non-default)
- `-p, --prompt` - Non-interactive prompt (appended to stdin if any)
- `-i, --prompt-interactive` - Execute prompt then continue interactive
- `-s, --sandbox` - Run in sandbox
- `-d, --debug` - Debug mode
- `-a, --all-files` - Include all files in context
- `-y, --yolo` - Auto-accept all actions

#### Input Methods
1. **Stdin + prompt flag** (RECOMMENDED):
   ```bash
   echo "PROMPT" | gemini -m gemini-2.5-pro -p
   ```

2. **Prompt flag only** (may timeout):
   ```bash
   gemini -p "PROMPT" -m gemini-2.5-pro
   ```

#### Production Configuration
```bash
echo "PROMPT" | \
  GEMINI_API_KEY="" \
  gemini -m gemini-2.5-pro -p \
  2>/dev/null
```

### Model-Specific Issues

#### Gemini 2.5 Flash Lite Problem
**Error**: "Unable to submit request because Thinking_config.include_thoughts is only enabled when thinking is enabled"
- **Cause**: 2.5 Flash Lite has thinking mode OFF by default (optimized for speed/cost)
- **Solution**: Use `gemini-2.5-pro` or `gemini-2.5-flash` instead
- **Note**: No CLI flag currently exists to enable thinking mode

### Common Issues & Solutions
1. **"No input provided"**: Use echo to pipe prompt to stdin with `-p` flag
2. **Thinking mode errors**: Avoid `gemini-2.5-flash-lite`, use Pro or Flash
3. **Timeout on `-p` alone**: Combine stdin input with `-p` flag

---

## Pipeline Configuration Summary

### Optimal Production Settings

#### Claude Code (Sonnet 4)
```bash
claude -p "$(cat prompt.md)" \
  --model sonnet \
  --permission-mode plan \
  --output-format json \
  2>/dev/null \
  | node scripts/normalize-json.js
```
- **Speed**: ~30-60 seconds
- **Quality**: High
- **Stability**: Excellent

#### OpenAI Codex (GPT-5, Low Reasoning)
```bash
codex exec --output-last-message output.txt \
  -c model_reasoning_effort="low" \
  "$(cat prompt.md)" \
  >/dev/null 2>&1 && \
cat output.txt | node scripts/normalize-json.js
```
- **Speed**: ~45-90 seconds  
- **Quality**: Good (with low reasoning)
- **Stability**: Excellent

#### Google Gemini (2.5 Pro)
```bash
echo "$(cat prompt.md)" | \
  GEMINI_API_KEY="" \
  gemini -m gemini-2.5-pro -p \
  2>/dev/null \
  | node scripts/normalize-json.js
```
- **Speed**: ~20-40 seconds
- **Quality**: High
- **Stability**: Good (when using Pro/Flash, not Lite)

### Environment Setup

#### Required Environment Variables
```bash
# MUST be unset or empty for subscription auth to work
# Locally: keep ANTHROPIC_API_KEY unset
# In CI: set ANTHROPIC_API_KEY via GitHub Secret
unset OPENAI_API_KEY  
unset GEMINI_API_KEY  # or GEMINI_API_KEY=""
```

#### PATH Configuration
```bash
# Add Claude if installed in non-standard location
export PATH="$HOME/.claude/local:$PATH"

# Standard Homebrew paths (usually automatic)
export PATH="/opt/homebrew/bin:$PATH"  # Apple Silicon
export PATH="/usr/local/bin:$PATH"     # Intel Mac
```

### Parallel Execution
All three providers can run concurrently for faster total execution:
```bash
# Run all in parallel with & and wait
(claude_command) &
(codex_command) &  
(gemini_command) &
wait
```
**Total time**: ~60-90 seconds (limited by slowest provider)
**Sequential time**: ~150-200 seconds

---

## Troubleshooting Checklist

1. **All providers failing?**
   - Check API key environment variables are unset
   - Verify subscription/login status with `auth-check.sh`

2. **Claude issues?**
   - Check `~/.claude/local/` for binary
   - Clear cache: `rm -rf ~/.claude/projects/-Users-*`
   - Verify model name (sonnet, not sonnet-4)

3. **Codex issues?**  
   - Update to 0.25.0: `brew upgrade codex`
   - Use `exec` mode, not interactive
   - Use `--output-last-message` for clean output

4. **Gemini issues?**
   - Use 2.5 Pro or Flash, NOT Flash Lite
   - Pipe input via echo, don't rely on `-p` alone
   - Check OAuth: `~/.gemini/oauth_creds.json`

5. **JSON parsing issues?**
   - Ensure `normalize-json.js` is executable
   - Check for syntax errors in normalizer
   - Verify output format from each CLI

---

## Performance Optimization Tips

1. **Model Selection**:
   - Claude: Use `sonnet` over `opus` (2x faster, 90% quality)
   - Codex: Use `model_reasoning_effort="low"` (2-3x faster)
   - Gemini: Use `2.5-pro` or `2.5-flash` (avoid lite)

2. **Parallel Execution**: Always run providers in parallel

3. **Error Handling**: Use fallback JSON for failed providers to prevent gate failures

4. **Caching**: Leverage Claude's conversation caching for repeated reviews

5. **Resource Management**: Limit concurrent reviews on self-hosted runners

---

## Security Considerations

1. **NEVER commit API keys** to repository
2. **Use subscription authentication** exclusively
3. **Set read-only/plan permissions** for review tasks
4. **Redirect stderr** to prevent sensitive data leakage
5. **Validate JSON output** before processing
6. **Use sandboxed modes** where available

---

## Version Compatibility Matrix

| Provider | CLI Version | Models | Auth Method | JSON Output |
|----------|------------|--------|-------------|-------------|
| Claude | 1.0.95+ | Opus 4.1, Sonnet 4, Haiku | Subscription | ✅ Envelope |
| Codex | 0.25.0 | GPT-5 | Subscription | ✅ JSONL/Last |
| Gemini | 0.2.1 | 2.5 Pro/Flash | OAuth | ✅ Direct |

---

Last Updated: 2025-08-28
Tested Environment: macOS Darwin 25.0.0, Homebrew packages

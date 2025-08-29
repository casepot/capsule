# Multi-Model PR Review Pipeline - Runner Setup Guide

## Overview
This document provides instructions for setting up a self-hosted GitHub Actions runner to support the multi-model PR review pipeline using subscription-based authentication (NO API keys).

## Prerequisites

### System Requirements
- **OS**: Ubuntu 22.04+ or macOS 13+
- **CPU**: 4+ cores recommended
- **RAM**: 8GB minimum, 16GB recommended
- **Storage**: 20GB free space

### Required Software
1. **Node.js 20+**: For aggregation script
2. **Python 3.11+**: For PyREPL3 project
3. **Git**: Latest version
4. **GitHub CLI (`gh`)**: For PR operations
5. **jq**: For JSON processing

## Installation Steps

### 1. Install Base Dependencies

#### Ubuntu/Debian:
```bash
# Update package list
sudo apt update

# Install Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install Python 3.11+
sudo apt install -y python3.11 python3-pip python3-venv

# Install GitHub CLI
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /usr/share/keyrings/githubcli-archive-keyring.gpg > /dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh

# Install jq
sudo apt install -y jq
```

#### macOS:
```bash
# Install Homebrew if not present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install node@20 python@3.11 gh jq
```

### 2. Install AI CLI Tools

**IMPORTANT**: These tools must be authenticated with subscription/OAuth logins. DO NOT use API keys.

#### Claude Code
```bash
# macOS (Homebrew):
brew install claude

# Or download from https://claude.ai/download
# Note: Claude Code often installs to ~/.claude/local/ (non-standard path)
# Our scripts automatically detect and handle this location

# After installation, authenticate with Claude.ai Pro/Max subscription:
claude  # May need: ~/.claude/local/claude if not in PATH
# Choose: /login
# Sign in with your Claude.ai Pro/Max account (NOT API Console account)

# Verify installation:
claude --version  # or ~/.claude/local/claude --version

# IMPORTANT: Use Sonnet 4 model for optimal speed/quality balance:
# --model sonnet (not opus which is slower)
```

#### OpenAI Codex CLI
```bash
# Install via Homebrew (recommended):
brew install codex

# Current version: 0.25.0
codex --version

# Authenticate with ChatGPT Plus/Pro/Team subscription:
codex login
# Choose: "Sign in with ChatGPT" 
# Complete OAuth flow in browser with your ChatGPT subscription

# IMPORTANT Configuration:
# - Model: GPT-5 (default)
# - Reasoning effort: "low" for faster execution
# - Sandbox mode: read-only (-s read-only flag required)
# - Working directory: -C . flag to set correct path
```

#### Gemini CLI
```bash
# Install via Homebrew (recommended):
brew install gemini-cli

# Current version: 0.2.1
gemini --version

# Authenticate with Google OAuth (no API key):
gemini
# Complete OAuth flow in browser with your Google account
# DO NOT provide API key - use OAuth only

# IMPORTANT Model Selection:
# - Use: gemini-2.5-pro (production) or gemini-2.5-flash (faster)
# - AVOID: gemini-2.5-flash-lite (has thinking mode issues)
# - AVOID: gemini-2.0-* models (outdated)

# Input method: echo "prompt" | gemini -m gemini-2.5-pro -p
```

### 3. Register Self-Hosted Runner

1. Navigate to your repository on GitHub
2. Go to Settings → Actions → Runners
3. Click "New self-hosted runner"
4. Follow the provided instructions to download and configure the runner
5. Install as a service (recommended):
   ```bash
   sudo ./svc.sh install
   sudo ./svc.sh start
   ```

### 4. Verify Installation

Run the auth check script to verify all CLIs are installed and authenticated:
```bash
cd /path/to/your/repo
bash .review-pipeline/scripts/auth-check.sh
```

Expected output:
```
• No API key envs detected.
• All required CLIs present (claude, codex, gemini, gh, jq).
• Claude Code auth probe OK.
• Codex CLI auth probe OK.
• Gemini CLI auth probe OK.
Auth checks passed.
```

## Configuration

### Repository Variables
Set these in GitHub repository settings (Settings → Secrets and variables → Actions → Variables):

- `TEST_CMD`: Command to run tests (default: `pytest tests/`)
  - For Python: `pytest tests/`
  - For Node.js: `npm test`
  - For Go: `go test ./...`

### Critical Configuration Files

#### Prompt Files (prompts/ directory)
- **review.codex.md**: Must specify that Codex CAN read files:
  ```markdown
  - You CAN and SHOULD read files (using cat, head, etc.) but do NOT edit/write files.
  - You CAN run read-only shell commands (ls, cat, head, grep) but do NOT modify anything.
  ```
- **review.claude.md**: Use `--permission-mode plan` for read-only analysis
- **review.gemini.md**: Include explicit JSON output instructions

#### Workflow Configuration (.github/workflows/pr-multimodel-review.yml)
Ensure these flags are set:
- Claude: `--model sonnet --permission-mode plan --output-format json`
- Codex: `-s read-only -C . -c model_reasoning_effort="low"`  
- Gemini: `-m gemini-2.5-pro -p` (with echo piping)

### Branch Protection Rules
1. Go to Settings → Branches
2. Add rule for `main` (or your default branch)
3. Enable:
   - Require pull request reviews before merging
   - Require status checks to pass before merging
   - Add `review` job as required status check

## Troubleshooting

### CLI Authentication Issues

#### Claude Code
- Error: "Claude Code not authenticated"
- Solution: Run `claude` interactively and use `/login` with Claude.ai Pro/Max account

- Error: "Missing required binary: claude"
- Solution: Claude installs to `~/.claude/local/`. Either:
  1. Add to PATH: `export PATH="$HOME/.claude/local:$PATH"` in ~/.bashrc
  2. Create alias: `alias claude="$HOME/.claude/local/claude"` in ~/.bashrc
  3. Our scripts automatically detect Claude at ~/.claude/local/ if present

#### Codex CLI
- Error: "Codex CLI not authenticated"
- Solution: Run `codex` and choose "Sign in with ChatGPT"

#### Gemini CLI
- Error: "Gemini CLI not authenticated"
- Solution: Run `gemini` and complete OAuth flow (no API key)

### API Key Detection
- Error: "API key envs must NOT be set"
- Solution: Unset environment variables:
  ```bash
  unset ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY
  ```
  - Check your shell profile (~/.bashrc, ~/.zshrc) and remove any API key exports

### Missing Commands
If CLIs are installed but not found:
1. Check PATH: `echo $PATH`
2. Add installation directories to PATH in ~/.bashrc:
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   export PATH="/opt/homebrew/bin:$PATH"  # macOS with Homebrew
   ```
3. Reload shell: `source ~/.bashrc`

### Runner Permission Issues
- Ensure runner user has read access to repository
- For Docker-based setups, ensure proper volume mounts

## Security Best Practices

1. **NEVER commit API keys** to the repository
2. **Use subscription-based auth only** for AI tools
3. **Regularly update** CLI tools and dependencies
4. **Isolate runner** from production systems
5. **Monitor runner logs** for suspicious activity
6. **Rotate credentials** periodically

## Local Testing

Before pushing to GitHub, test locally:
```bash
# Set test command
export TEST_CMD="pytest tests/"

# Run local review
bash .review-pipeline/scripts/review-local.sh
```

## Maintenance

### Update CLIs
```bash
# Claude Code
brew upgrade claude  # or redownload from claude.ai/download

# Codex CLI  
brew upgrade codex

# Gemini CLI
brew upgrade gemini-cli
```

### Monitor Runner Health
```bash
# Check runner status
sudo ./svc.sh status

# View runner logs
journalctl -u actions.runner.*.service -f
```

## Support

- Claude Code: https://docs.anthropic.com/en/docs/claude-code
- Codex CLI: https://github.com/openai/codex
- Gemini CLI: https://github.com/google-gemini/gemini-cli
- GitHub Actions: https://docs.github.com/actions

## Acceptance Checklist

- [ ] Node.js 20+ installed
- [ ] Python 3.11+ installed (for PyREPL3)
- [ ] GitHub CLI (`gh`) installed
- [ ] jq installed
- [ ] Claude Code installed and authenticated (Pro/Max subscription)
  - [ ] Version check: `claude --version` or `~/.claude/local/claude --version`
  - [ ] Can run: `claude -p "test" --model sonnet --permission-mode plan`
- [ ] Codex CLI v0.25.0+ installed and authenticated (ChatGPT Plus subscription)
  - [ ] Version check: `codex --version`
  - [ ] Can run: `codex exec -s read-only "echo test"`
- [ ] Gemini CLI v0.2.1+ installed and authenticated (Google OAuth)
  - [ ] Version check: `gemini --version`
  - [ ] Can run: `echo "test" | gemini -m gemini-2.5-pro -p`
- [ ] NO API keys in environment (check ~/.bashrc, ~/.zshrc)
  - [ ] Locally: `echo $ANTHROPIC_API_KEY` returns empty
  - [ ] CI: `ANTHROPIC_API_KEY` configured as a GitHub Secret
  - [ ] `echo $OPENAI_API_KEY` returns empty
  - [ ] `echo $GEMINI_API_KEY` returns empty
- [ ] Runner registered and running
- [ ] `.review-pipeline/scripts/auth-check.sh` passes all checks
- [ ] `.review-pipeline/scripts/review-local.sh` completes without errors
- [ ] Test PR triggers workflow and posts review comment

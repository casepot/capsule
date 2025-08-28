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
# Follow official installation guide:
# https://docs.anthropic.com/en/docs/claude-code/setup

# Note: Claude Code sometimes installs to a non-standard location when migrated (~/.claude/local/)
# Our scripts automatically detect and handle this

# After installation, authenticate with Claude.ai Pro/Max:
claude  # May need: ~/.claude/local/claude if not aliased
# Choose: /login
# Sign in with your Claude.ai Pro/Max account (NOT Console account)

# Verify installation:
~/.claude/local/claude --version
```

#### OpenAI Codex CLI
```bash
# Install via npm
npm install -g @openai/codex

# Authenticate with ChatGPT Plus/Pro/Team:
codex
# Choose: "Sign in with ChatGPT"
# Complete OAuth flow with your ChatGPT subscription
```

#### Gemini CLI
```bash
# Install via homebrew (macOS)
brew install gemini-cli

# Clone and install from GitHub
git clone https://github.com/google-gemini/gemini-cli.git
cd gemini-cli
npm install -g .

# Authenticate with Google OAuth (no API key):
gemini
# Choose OAuth login with your Google account
# DO NOT provide API key
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
bash scripts/auth-check.sh
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
bash scripts/review-local.sh
```

## Maintenance

### Update CLIs
```bash
# Claude Code
claude --update  # If supported, or reinstall

# Codex CLI
npm update -g @openai/codex

# Gemini CLI
cd /path/to/gemini-cli
git pull
npm install -g .
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
- [ ] Claude Code installed and authenticated (Pro/Max)
- [ ] Codex CLI installed and authenticated (ChatGPT Plus)
- [ ] Gemini CLI installed and authenticated (OAuth)
- [ ] NO API keys in environment
- [ ] Runner registered and running
- [ ] `scripts/auth-check.sh` passes
- [ ] Local test with `scripts/review-local.sh` works
- [ ] Test PR triggers workflow successfully

# Multi-Model PR Review Pipeline

## Overview

This automated PR review system uses three AI providers (Claude, OpenAI Codex, Google Gemini) running in parallel to provide comprehensive code review feedback. The system uses **subscription-based authentication only** - no API keys are required or supported.

### Key Features
- **Parallel execution** of three AI reviewers (~2 minutes total)
- **Subscription-only authentication** (Claude Pro/Max, ChatGPT Plus, Google OAuth)
- **Schema-validated JSON output** with deterministic aggregation
- **Must-fix gating** to prevent merging critical issues
- **Self-hosted runner support** for security and control
- **Project-specific review criteria** via configuration
- **Automatic JSON normalization** handling various output formats

## Quick Start

### Prerequisites
1. **Active subscriptions:**
   - Claude Pro or Claude Max (claude.ai)
   - ChatGPT Plus or Team (chat.openai.com)
   - Google account (for Gemini OAuth)

2. **System requirements:**
   - macOS 13+ or Ubuntu 22.04+
   - Node.js 20+
   - Python 3.11+ (for test execution)
   - 8GB RAM minimum

### Installation

```bash
# Install CLI tools via Homebrew
brew install claude codex gemini-cli gh jq

# Authenticate CLIs (NO API KEYS)
claude        # Login with Claude.ai Pro/Max account
codex login   # Login with ChatGPT Plus account  
gemini        # OAuth with Google account

# Verify authentication
review-pipeline auth-check

# Test locally 
review-pipeline run --providers claude,codex,gemini
```

## Runner Setup

### Install Base Dependencies

#### Ubuntu/Debian
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
sudo apt install gh jq
```

#### macOS
```bash
# Install Homebrew if not present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install node@20 python@3.11 gh jq
```

### Install AI Provider CLIs

#### Claude Code (Anthropic)

```bash
# Install via Homebrew (recommended)
brew install claude

# Or download from https://claude.ai/download
# Note: Often installs to ~/.claude/local/ (non-standard path)

# Authenticate with Claude.ai Pro/Max subscription
claude  # May need: ~/.claude/local/claude if not in PATH
# Choose: /login
# Sign in with your Claude.ai Pro/Max account (NOT API Console)

# Verify installation
claude --version  # or ~/.claude/local/claude --version
```

**Available Models:**
- `opus` - Claude Opus 4.1 (most powerful, slower)
- `sonnet` - Claude Sonnet 4 (balanced, **recommended for production**)
- `haiku` - Claude Haiku (fastest, less capable)

**Common Issues:**
- **"Credit balance is too low"**: Unset `ANTHROPIC_API_KEY` environment variable
- **"Path not found"**: Clear cache with `rm -rf ~/.claude/projects/-Users-*`
- **Command not found**: Check `~/.claude/local/claude` path

#### OpenAI Codex CLI

```bash
# Install via Homebrew
brew install codex  # Currently v0.25.0

# Authenticate with ChatGPT Plus/Team subscription
codex login
# Choose: "Sign in with ChatGPT" 
# Complete OAuth flow in browser

# Verify
codex --version
```

**Configuration:**
- Model: GPT-5 (default)
- Reasoning effort: `"low"` for faster execution (recommended)
- Sandbox mode: `read-only` for reviews

**Common Issues:**
- **"Cannot read files"**: Add `-s read-only -C .` flags
- **Verbose output**: Use `--output-last-message` flag

#### Google Gemini CLI

```bash
# Install via Homebrew
brew install gemini-cli  # Currently v0.2.1

# Authenticate with Google OAuth (no API key)
gemini
# Complete OAuth flow in browser
# DO NOT provide API key - use OAuth only

# Verify
gemini --version
```

**Available Models:**
- `gemini-2.5-pro` - Most capable (**recommended**)
- `gemini-2.5-flash` - Faster, good balance
- `gemini-2.5-flash-lite` - **BROKEN** (thinking mode issues)

**Common Issues:**
- **"No input provided"**: Use `echo "prompt" | gemini -p` syntax
- **Thinking mode errors**: Use Pro or Flash, NOT Flash Lite

### Register GitHub Actions Runner

1. Navigate to your repository → Settings → Actions → Runners
2. Click "New self-hosted runner"
3. Follow the provided instructions
4. Install as a service:
   ```bash
   sudo ./svc.sh install
   sudo ./svc.sh start
   ```

### Verify Installation

```bash
cd /path/to/your/repo
review-pipeline auth-check
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

The review pipeline uses a layered configuration system that merges settings from multiple sources in priority order.

### Configuration Layers (highest to lowest priority)

1. **Runtime flags** - Command-line arguments
2. **Environment variables** - See npm package documentation for mappings
3. **Project config** - `.reviewrc.json` in project root
4. **Pipeline defaults** - Built into the npm package

### Basic Project Configuration

Create `.reviewrc.json` in your project root:

```json
{
  "testing": {
    "command": "npm test",
    "timeout_seconds": 120
  },
  "review_overrides": {
    "providers": {
      "claude": {"model": "opus"},
      "codex": {"reasoning_effort": "high"},
      "gemini": {"model": "gemini-2.5-pro"}
    }
  }
}
```

### Environment Variables

Common environment variable overrides:

```bash
# Execution settings
export REVIEW_TIMEOUT=180          # Global timeout per provider
export REVIEW_PARALLEL=true         # Run providers in parallel
export TEST_CMD="pytest tests/"     # Test command

# Provider settings
export CLAUDE_MODEL=sonnet          # Claude model selection
export CODEX_REASONING=low          # Codex reasoning effort
export GEMINI_MODEL=gemini-2.5-pro  # Gemini model selection

# Gate settings
export GATE_MUST_FIX_THRESHOLD=1    # Number of must-fix issues to fail
```

See the @multi-model/review-pipeline npm package documentation for complete list.

### Project-Specific Review Criteria

Add custom review criteria for your project:

#### Method 1: Markdown File (Recommended)
Create `.review-criteria.md` in your project root using the template from `.review-pipeline/templates/.review-criteria.example.md`:

```markdown
<project_context>
Financial services application handling payment processing
</project_context>

<critical_paths>
- `src/payments/**` - Payment processing (requires PCI compliance review)
- `src/auth/**` - Authentication system (zero tolerance for vulnerabilities)
</critical_paths>

<zero_tolerance_issues>
- Hardcoded passwords or API keys in code
- SQL injection vulnerabilities
- Logging of credit card numbers
</zero_tolerance_issues>
```

#### Method 2: JSON Configuration
Add to `.reviewrc.json`:

```json
{
  "review_criteria": {
    "project_context": "Healthcare system processing PHI data",
    "security_requirements": [
      "PHI must be encrypted at rest using AES-256",
      "All PHI access must be logged"
    ],
    "critical_paths": [
      {"pattern": "src/patient/**", "reason": "Contains PHI data"}
    ]
  }
}
```

### Provider Configuration

Provider capabilities and settings are defined in the @multi-model/review-pipeline npm package.
The package includes self-documenting manifest files for each provider that define available models, flags, authentication methods, and common issues.

### GitHub Actions Configuration

Set repository variables in Settings → Secrets and variables → Actions → Variables:

- `TEST_CMD`: Command to run tests (e.g., `pytest tests/`)
- `REVIEW_TIMEOUT`: Overall timeout in seconds
- Provider-specific overrides as needed

## Operation

### Local Testing

```bash
# Create test branch with changes
git checkout -b test-review
echo "# Test" >> README.md
git add README.md
git commit -m "Test review"

# Run review
./review-local

# Check results
cat .review-pipeline/workspace/summary.md
cat .review-pipeline/workspace/gate.txt  # Shows "pass" or "fail"
```

### GitHub Actions Workflow

The workflow automatically:
1. Runs on PR open/update
2. Executes all enabled providers in parallel
3. Aggregates results into a summary
4. Posts review comment on PR
5. Gates merge based on must-fix issues

### Model Recommendations

| Provider | Recommended | Speed | Quality | Configuration |
|----------|------------|-------|---------|---------------|
| Claude | Sonnet 4 | Fast | High | `providers.claude.model: "sonnet"` |
| Codex | GPT-5 (low) | Medium | Good | `providers.codex.reasoning_effort: "low"` |
| Gemini | 2.5 Pro | Fast | High | `providers.gemini.model: "gemini-2.5-pro"` |

### Performance

Typical execution times with parallel processing:
- Claude Sonnet 4: ~30-60 seconds
- Codex GPT-5 (low reasoning): ~45-90 seconds  
- Gemini 2.5 Pro: ~20-40 seconds
- **Total pipeline**: ~60-90 seconds (limited by slowest provider)

## Troubleshooting

### Authentication Issues

**All Providers:**
- Ensure NO API keys are set: `unset ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY`
- Check your shell profile (~/.bashrc, ~/.zshrc) for API key exports

**Claude:**
- Run `claude` interactively and use `/login` with Claude.ai Pro/Max account
- If command not found, check `~/.claude/local/claude`

**Codex:**
- Run `codex login` and choose "Sign in with ChatGPT"
- Ensure you have ChatGPT Plus/Team subscription

**Gemini:**
- Run `gemini` and complete OAuth flow (no API key)
- Check OAuth credentials at `~/.gemini/oauth_creds.json`

### Common Issues

**Missing CLIs:**
```bash
# Add to PATH in ~/.bashrc or ~/.zshrc
export PATH="$HOME/.claude/local:$PATH"      # Claude non-standard location
export PATH="/opt/homebrew/bin:$PATH"        # macOS with Homebrew
```

**JSON Parsing Errors:**
- Check output format flags for each provider
- Verify `normalize-json.js` is executable
- Check for schema violations (e.g., summary length > 500 chars)

**Provider Timeouts:**
- Increase timeout: `export REVIEW_TIMEOUT=300`
- Use faster models (Sonnet vs Opus, low reasoning vs high)
- Check network connectivity

**Gate Failures:**
- Review must-fix issues in summary
- Check test execution results
- Verify gating thresholds in configuration

### Maintenance

**Update CLIs:**
```bash
brew upgrade claude codex gemini-cli
```

**Monitor Runner:**
```bash
sudo ./svc.sh status
journalctl -u actions.runner.*.service -f
```

**Clear Caches:**
```bash
rm -rf ~/.claude/projects/-Users-*          # Claude session cache
rm -rf .review-pipeline/workspace/.cache    # Pipeline cache
```

## File Structure

```
# Project Root
.reviewrc.json                   # Project configuration (optional)
.review-criteria.md              # Project review criteria (optional)

# Commands (from npm package)
review-pipeline auth-check       # Check authentication
review-pipeline run              # Run review

# Runtime Directory (auto-generated, DO NOT COMMIT)
.review-pipeline/
└── workspace/                 # Created by npm package at runtime
    ├── context/              # PR metadata
    │   ├── pr.json          # Pull request information
    │   ├── diff.patch       # Git diff
    │   └── tests.txt        # Test results
    ├── reports/              # Provider outputs
    │   ├── raw/             # Raw CLI outputs
    │   ├── claude-code.json
    │   ├── codex-cli.json
    │   └── gemini-cli.json
    ├── summary.md            # Aggregated review
    └── gate.txt              # Pass/fail decision

# Note: The actual pipeline code lives in the npm package:
# @multi-model/review-pipeline (github:casepot/multi-model-review-pipeline)
```

## Security Best Practices

1. **NEVER commit API keys** to the repository
2. **Use subscription-based auth only** for AI tools
3. **Read-only execution** - providers cannot modify code during review
4. **Self-hosted runners** - maintain control over execution environment
5. **Regular updates** - Keep CLI tools and dependencies current
6. **Credential rotation** - Periodically re-authenticate services

## Technical Reference

> **Note**: This documentation provides an overview for convenience. The authoritative sources for configuration and capabilities are in the @multi-model/review-pipeline npm package:
> - Package repository: https://github.com/casepot/multi-model-review-pipeline
> - Installation: `npm install -g github:casepot/multi-model-review-pipeline`

### Provider Output Formats

#### Claude (JSON Envelope)
When using `--output-format json`, Claude CLI wraps the model's response in metadata:
```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "duration_ms": 30310,
  "result": "{\"tool\": \"claude-code\", \"summary\": \"...\", ...}",  // Model's JSON output as string
  "session_id": "...",
  "total_cost_usd": 0.532,
  "usage": {...}
}
```
The actual review JSON is inside the `result` field as a string.

#### Codex (JSONL Stream)
With `--json` flag, outputs newline-delimited JSON events:
```jsonl
{"type": "task_started", "model_context_window": 400000}
{"type": "agent_reasoning", "text": "..."}
{"type": "agent_message", "message": "..."}
{"type": "token_count", "input_tokens": 5845, "output_tokens": 938}
```

#### Gemini (Direct Output)
Returns response directly without wrapper, may include thinking tags.

### Production Command Examples

#### Claude Sonnet Review
```bash
claude -p "$(cat prompt.md)" \
  --model sonnet \
  --permission-mode plan \
  --output-format json \
  2>/dev/null \
  | node scripts/normalize-json.js
```

#### Codex GPT-5 with Low Reasoning
```bash
codex exec --output-last-message output.txt \
  -s read-only \
  -C . \
  -c model_reasoning_effort="low" \
  "$(cat prompt.md)" \
  >/dev/null 2>&1 && \
cat output.txt | node scripts/normalize-json.js
```

#### Gemini 2.5 Pro
```bash
echo "$(cat prompt.md)" | \
  GEMINI_API_KEY="" \
  gemini -m gemini-2.5-pro -p \
  2>/dev/null \
  | node scripts/normalize-json.js
```

### Configuration Flags Reference

#### Claude Permission Modes
- `plan` - Read-only analysis mode (recommended for reviews)
- `read` - Can read files
- `write` - Can read and write files  
- `exec` - Can execute commands

#### Codex Reasoning Effort
- `"none"` - No reasoning
- `"low"` - Fast, minimal reasoning (recommended for speed)
- `"medium"` - Default balanced
- `"high"` - Deep reasoning (slower)

#### Codex Sandbox Modes
- `read-only` - Read files only (required for reviews)
- `workspace-write` - Write in workspace
- `danger-full-access` - Full system access

### Version Compatibility

| Provider | CLI Version | Models | Auth Method | JSON Output |
|----------|------------|--------|-------------|-------------|
| Claude | 1.0.95+ | Opus 4.1, Sonnet 4, Haiku | Subscription | ✅ Envelope |
| Codex | 0.25.0 | GPT-5 | Subscription | ✅ JSONL/Last |
| Gemini | 0.2.1 | 2.5 Pro/Flash | OAuth | ✅ Direct |

## Support Resources

- Claude Code: https://docs.anthropic.com/en/docs/claude-code
- OpenAI Codex: https://platform.openai.com/docs
- Google Gemini: https://ai.google.dev/gemini-api/docs
- GitHub Actions: https://docs.github.com/actions
- Pipeline Issues: https://github.com/your-repo/issues

## Acceptance Checklist

- [ ] Node.js 20+ and Python 3.11+ installed
- [ ] GitHub CLI (`gh`) and jq installed
- [ ] Claude Code authenticated (Pro/Max subscription)
- [ ] Codex CLI authenticated (ChatGPT Plus subscription)
- [ ] Gemini CLI authenticated (Google OAuth)
- [ ] NO API keys in environment
- [ ] `./auth-check` passes all checks
- [ ] `./review-local` completes without errors
- [ ] Test PR triggers workflow and posts review comment
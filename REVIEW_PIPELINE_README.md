# Multi-Model PR Review Pipeline

## Overview
This repository includes an automated PR review system that uses three AI providers (Claude, OpenAI Codex, Gemini) running in parallel to provide comprehensive code review feedback. The system uses **subscription-based authentication only** - no API keys are required or supported.

## Key Features
- **Parallel execution** of three AI reviewers (~2 minutes total vs ~6 minutes sequential)
- **Subscription-only authentication** (Claude Pro/Max, ChatGPT Plus, Google OAuth)
- **Schema-validated JSON output** with deterministic aggregation
- **Must-fix gating** to prevent merging critical issues
- **Self-hosted runner support** for security and control
- **Automatic JSON normalization** handling various output formats

## Quick Start

### Prerequisites
1. Active subscriptions:
   - Claude Pro or Claude Max (claude.ai)
   - ChatGPT Plus or Team (chat.openai.com)
   - Google account (for Gemini OAuth)

2. Self-hosted runner with:
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
bash scripts/auth-check.sh

# Test locally
bash scripts/review-local.sh
```

## Documentation

| Document | Purpose |
|----------|---------|
| [RUNNER_SETUP.md](RUNNER_SETUP.md) | Complete runner installation and configuration guide |
| [PROVIDER_CONFIGURATION.md](PROVIDER_CONFIGURATION.md) | Detailed CLI configuration, models, and troubleshooting |
| [report.schema.json](report.schema.json) | JSON schema for provider outputs |

## Project Structure

```
.github/workflows/
├── pr-multimodel-review.yml    # GitHub Actions workflow

scripts/
├── auth-check.sh               # Verify CLI authentication
├── review-local.sh             # Local testing script
├── aggregate-reviews.mjs       # Aggregate and validate reports
└── normalize-json.js           # Extract JSON from various formats

prompts/
├── review.core.md              # Core review instructions (all providers)
├── review.claude.md            # Claude-specific overlay
├── review.codex.md             # Codex-specific overlay  
└── review.gemini.md            # Gemini-specific overlay

review/                         # Generated during review
├── context/                    # PR metadata and diffs
│   ├── pr.json
│   ├── diff.patch
│   ├── files.txt
│   └── tests.txt
├── reports/                    # Individual provider reports
│   ├── claude-code.json
│   ├── codex-cli.json
│   └── gemini-cli.json
├── summary.md                  # Aggregated summary
└── gate.txt                    # pass/fail decision
```

## Configuration

### Required CLI Flags

| Provider | Command | Required Flags |
|----------|---------|----------------|
| Claude | `claude` | `--model sonnet --permission-mode plan --output-format json` |
| Codex | `codex exec` | `-s read-only -C . -c model_reasoning_effort="low"` |
| Gemini | `gemini` | `-m gemini-2.5-pro -p` |

### Model Selection

| Provider | Recommended Model | Speed | Quality | Notes |
|----------|------------------|-------|---------|--------|
| Claude | Sonnet 4 | Fast | High | Avoid Opus (slower) |
| Codex | GPT-5 (low reasoning) | Medium | Good | Set `model_reasoning_effort="low"` |
| Gemini | 2.5 Pro | Fast | High | Avoid 2.5 Flash Lite (broken) |

## Common Issues

### Installation Problems
- **Claude not found**: Check `~/.claude/local/claude` (non-standard path)
- **API key conflicts**: Unset `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`
- **Auth failures**: Re-authenticate with subscription accounts, not API consoles

### Codex File Access Issues
- **"Cannot read files"**: Add `-s read-only -C .` flags
- **"No PR metadata"**: Update `prompts/review.codex.md` to clarify file reading is allowed

### Gemini Model Issues  
- **Thinking mode error**: Use `gemini-2.5-pro` or `gemini-2.5-flash`, NOT `gemini-2.5-flash-lite`
- **"No input provided"**: Use `echo "prompt" | gemini -p` syntax

### JSON Output Problems
- **Wrapped in markdown**: The `normalize-json.js` script handles this automatically
- **Schema violations**: Check `summary` length (<500 chars) and required fields

## Testing

### Local Testing
```bash
# Create test branch with changes
git checkout -b test-review
echo "# Test" >> README.md
git add README.md
git commit -m "Test review"

# Run review
bash scripts/review-local.sh

# Check results
cat review/summary.md
cat review/gate.txt  # Should show "pass" or "fail"
```

### GitHub Actions Testing
1. Create PR from test branch
2. Workflow runs automatically
3. Review comment posted with summary
4. Gate blocks merge if must-fix issues found

## Security Notes

- **NEVER commit API keys** - use subscription auth only
- **Read-only execution** - providers cannot modify code
- **Self-hosted runners** - maintain control over execution environment
- **No external dependencies** - all tools run locally

## Performance

Typical execution times with parallel processing:
- Claude Sonnet 4: ~30-60 seconds
- Codex GPT-5 (low reasoning): ~45-90 seconds  
- Gemini 2.5 Pro: ~20-40 seconds
- **Total pipeline**: ~60-90 seconds (limited by slowest provider)

## Support

- Claude Code: https://docs.anthropic.com/en/docs/claude-code
- OpenAI Codex: https://platform.openai.com/docs
- Google Gemini: https://ai.google.dev/gemini-api/docs
- GitHub Actions: https://docs.github.com/actions

## License

The multi-model review pipeline configuration is provided as-is for use with the PyREPL3 project.
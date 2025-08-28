# Multi-Model Review Pipeline Package

A self-contained, portable AI code review system using subscription-based authentication (no API keys) with Claude, OpenAI Codex, and Google Gemini.

## Quick Setup

```bash
# 1. Run the setup script
./setup.sh

# 2. Test your authentication
bash scripts/auth-check.sh

# 3. Run a local review
bash scripts/review-local.sh
```

## Package Structure

```
.review-pipeline/
├── config/          # Configuration files
│   ├── schema.json  # JSON Schema for validation
│   └── defaults.json # Default settings
├── prompts/         # Review prompts for each provider
├── scripts/         # Review and utility scripts
├── tests/           # Test files
└── workspace/       # Runtime files (gitignored)
    ├── context/     # PR metadata and diffs
    └── reports/     # Provider outputs
```

## Using in a New Project

### Method 1: Copy the Package

```bash
# Copy this directory to your project
cp -r /path/to/.review-pipeline your-project/
cd your-project/.review-pipeline
./setup.sh
```

### Method 2: Git Submodule

```bash
# Add as a submodule
git submodule add https://github.com/your-org/review-pipeline.git .review-pipeline
cd .review-pipeline
./setup.sh
```

## GitHub Actions Integration

1. Copy the workflow template:
```bash
cp templates/workflow.yml ../.github/workflows/pr-review.yml
```

2. Ensure your self-hosted runner has the CLI tools installed (see ../RUNNER_SETUP.md)

3. The workflow will automatically use this package

## Configuration

Edit `config/defaults.json` to customize:
- Timeout settings
- Model selections
- Test command

## Scripts

- `auth-check.sh` - Verify CLI authentication
- `review-local.sh` - Run review locally
- `aggregate-reviews.mjs` - Combine and validate reports
- `normalize-json.js` - Extract JSON from various formats
- `setup-claude-path.sh` - Handle Claude's non-standard installation

## Requirements

- Node.js 20+
- Claude Code (Pro/Max subscription)
- OpenAI Codex CLI (ChatGPT Plus)
- Google Gemini CLI (OAuth)
- GitHub CLI (`gh`)
- jq

## Troubleshooting

### Authentication Issues
```bash
# Check all CLI tools
bash scripts/auth-check.sh

# Individual checks
claude -p "test"
codex exec "echo test"
GEMINI_API_KEY="" gemini -p "test"
```

### Path Issues
- Claude may install to `~/.claude/local/`
- Scripts automatically detect this location

### Missing Dependencies
```bash
# Install Node packages
npm install

# Check Node version
node --version  # Should be 20+
```

## Output Files

All outputs are in `workspace/` (gitignored):
- `workspace/context/` - Input files (PR metadata, diff, etc.)
- `workspace/reports/` - Individual provider JSON reports
- `workspace/summary.md` - Aggregated summary
- `workspace/gate.txt` - Pass/fail decision

## Customization

To adapt for your project:
1. Update prompts in `prompts/` for your coding standards
2. Modify `config/defaults.json` for your test command
3. Adjust timeout values if needed
4. Add project-specific context to prompts

## License

This review pipeline is provided as-is for integration into your projects.
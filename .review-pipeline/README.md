# Review Pipeline Package - Technical Reference

## Overview

This package provides a self-contained, portable multi-model PR review pipeline implementation. It orchestrates three AI providers through a sophisticated configuration system with schema validation and automatic command generation.

For user documentation and setup instructions, see [REVIEW_PIPELINE.md](../REVIEW_PIPELINE.md) in the project root.

## Architecture

### Core Components

1. **Configuration System** (`lib/config-loader.js`)
   - Layered configuration merging (defaults → project → environment → runtime)
   - Schema validation using AJV
   - Environment variable mapping via `config/env.mapping.json`

2. **Provider Orchestration** (`lib/command-builder.js` & `lib/execute-provider.js`)
   - Dynamic command generation from provider manifests
   - Structured command building with security-focused design
   - Spawn-based execution avoiding shell injection risks

3. **Execution Pipeline** (`scripts/`)
   - Parallel provider execution with timeout management
   - JSON normalization from various output formats
   - Result aggregation with schema validation

### Self-Documenting Elements

The package leverages JSON files as authoritative sources:

- **Provider Manifests** (`config/providers/*.manifest.json`): Complete provider specifications including models, flags, authentication methods, and common issues
- **Environment Mappings** (`config/env.mapping.json`): All supported environment variables with types and paths
- **JSON Schemas** (`config/schemas/*.json`): Validation schemas for configuration, reports, and project settings

### Development Tools

```bash
# Validate configuration system
node .review-pipeline/lib/config-loader.js validate

# Show resolved configuration (merges all layers)
node .review-pipeline/lib/config-loader.js show

# Build provider command (useful for debugging)
node -e "import('./lib/command-builder.js').then(m => new m.default().buildCommand('claude').then(console.log))"

# Run single provider with custom timeout
bash .review-pipeline/scripts/run-provider-review.sh claude 120

# Test criteria builder
node .review-pipeline/lib/criteria-builder.js build
```

## Package Structure

```
config/
├── pipeline.config.json        # Default pipeline configuration
├── env.mapping.json           # Environment variable → config path mappings
├── schemas/                   # JSON schemas for validation
│   ├── pipeline.schema.json   # Pipeline configuration schema
│   ├── project.schema.json    # Project .reviewrc.json schema
│   └── report.schema.json     # Provider output report schema
└── providers/                 # Provider capability manifests
    ├── claude.manifest.json   # Claude models, flags, auth methods
    ├── codex.manifest.json    # Codex configuration specs
    └── gemini.manifest.json   # Gemini model specifications

lib/
├── config-loader.js           # Layered configuration system
├── generate-provider-command.js # Dynamic command generation
└── criteria-builder.js        # Project criteria processor

scripts/
├── auth-check.sh             # Verify provider authentication
├── review-local.sh           # Local review orchestrator
├── run-provider-review.sh    # Single provider executor
├── aggregate-reviews.mjs     # Multi-provider result merger
└── normalize-json.js         # Extract JSON from various formats

prompts/
├── review.core.md            # Base review instructions (all providers)
├── review.claude.md          # Claude-specific overlay
├── review.codex.md           # Codex-specific overlay  
└── review.gemini.md          # Gemini-specific overlay

templates/
└── .review-criteria.example.md # Project criteria template

workspace/                     # Runtime artifacts (gitignored)
├── context/                  # PR metadata cache
├── reports/                  # Individual provider outputs
├── .cache/                   # Criteria and prompt cache
├── summary.md                # Aggregated review
└── gate.txt                  # Pass/fail decision
```

## Configuration Architecture

See [CONFIGURATION.md](CONFIGURATION.md) for detailed architecture documentation.

### Configuration Resolution Order
1. Runtime flags (highest priority)
2. Environment variables (via `env.mapping.json`)
3. Project config (`.reviewrc.json`)
4. Pipeline defaults (`pipeline.config.json`)

### Provider Manifest Structure
Each provider manifest defines:
- CLI detection methods (command, paths)
- Authentication requirements and methods
- Available models with performance characteristics
- Required and optional flags
- Output format specifications
- Common issues and solutions

### Schema Validation
All configuration and output undergoes AJV schema validation:
- Pipeline configuration against `pipeline.schema.json`
- Project configuration against `project.schema.json`
- Provider reports against `report.schema.json`

## Extension Points

### Adding a New Provider
1. Create manifest: `config/providers/newprovider.manifest.json`
2. Add prompt overlay: `prompts/review.newprovider.md`
3. Update `config-loader.js` to recognize the provider
4. Test with: `node lib/generate-provider-command.js newprovider`

### Custom Project Criteria
Projects can extend review criteria via:
- `.review-criteria.md` (markdown with XML sections)
- `.reviewrc.json` `review_criteria` object
- Criteria are injected into prompts at runtime

### Environment Variable Mapping
Add new mappings to `config/env.mapping.json`:
```json
{
  "env": "YOUR_VAR",
  "path": "config.path.to.setting",
  "type": "string|boolean|integer",
  "description": "What this controls"
}
```

## Debugging

### Configuration Issues
```bash
# See fully resolved configuration
REVIEW_VERBOSE=true node lib/config-loader.js show

# Test specific provider command generation
node lib/generate-provider-command.js claude --verbose

# Check enabled providers
node -e "
  import('./lib/config-loader.js').then(async (m) => {
    const loader = new m.default();
    await loader.load();
    console.log(loader.getEnabledProviders());
  });
"
```

### Provider Execution
```bash
# Run single provider with debug output
DEBUG=* bash scripts/run-provider-review.sh claude 120

# Test JSON normalization
echo '```json\n{"test": true}\n```' | node scripts/normalize-json.js
```

### Criteria Building
```bash
# Test project criteria resolution
node lib/criteria-builder.js build --verbose

# View cached criteria
cat workspace/.cache/project-criteria-*.md
```

## Performance Considerations

- Provider manifests are loaded once and cached
- Configuration is resolved once per execution
- Parallel execution reduces total time to slowest provider
- JSON normalization handles streaming and buffered output
- Criteria are cached for 1 hour to reduce file I/O

## Contributing

When modifying the pipeline:
1. Update relevant JSON schemas if adding configuration options
2. Add environment mappings for new settings
3. Update provider manifests for new model capabilities
4. Ensure backward compatibility with existing projects
5. Test with all three providers before committing
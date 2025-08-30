# Review Pipeline Configuration Guide

## Overview

The review pipeline uses a sophisticated layered configuration system that provides flexibility while maintaining sensible defaults. Configuration flows through multiple layers with clear precedence rules, allowing customization at the project, environment, and runtime levels.

## Configuration Architecture

### Layered Configuration System

Configuration is loaded and merged from multiple sources in the following precedence order (highest to lowest):

1. **Runtime Arguments** - CLI flags and options passed directly to scripts
2. **Environment Variables** - Runtime overrides via environment
3. **Project Review Criteria** - `.review-criteria.md` or `review_criteria` in config
4. **Project Configuration** - Project-specific `.reviewrc.json` file
5. **Pipeline Configuration** - Package defaults in `pipeline.config.json`
6. **Provider Defaults** - Built-in defaults from provider manifests

### File Structure

```
.review-pipeline/
├── config/
│   ├── pipeline.config.json       # Main pipeline configuration
│   ├── env.mapping.json          # Environment variable mappings
│   ├── schemas/                  # JSON Schema definitions
│   │   ├── pipeline.schema.json  # Pipeline config validation
│   │   ├── project.schema.json   # Project config validation
│   │   └── report.schema.json    # Provider output validation
│   └── providers/                # Provider manifests
│       ├── claude.manifest.json  # Claude capabilities and detection
│       ├── codex.manifest.json   # Codex capabilities and detection
│       └── gemini.manifest.json  # Gemini capabilities and detection
├── lib/
│   ├── config-loader.js         # Configuration loading library
│   ├── criteria-builder.js      # Project criteria builder
│   └── generate-provider-command.js # Command generation from config
├── templates/
│   └── .review-criteria.example.md # Template for project criteria
└── [other directories...]
```

## Configuration Files

### Pipeline Configuration (`pipeline.config.json`)

The main configuration file that controls pipeline behavior. It defines:
- Execution settings (parallel/sequential, timeouts)
- Provider configurations and model selections
- Testing command and requirements
- Gating rules and severity thresholds

**Schema**: Validated against `config/schemas/pipeline.schema.json`
**Reference**: See the actual `config/pipeline.config.json` for current defaults

### Project Configuration (`.reviewrc.json`)

Optional project-specific configuration that overrides pipeline defaults:

```json
{
  "$schema": "./.review-pipeline/config/schemas/project.schema.json",
  
  "project": {
    "name": "my-project",
    "language": "python",
    "description": "Context for reviewers"
  },
  
  "testing": {
    // SECURITY: "command" field is IGNORED - TEST_CMD must come from repository variables only
    "timeout_seconds": 600,        // Timeout for test execution
    "coverage_threshold": 0.80    // Coverage threshold for gating
  },
  
  "review_overrides": {
    "providers": {
      "claude": {
        "model": "opus"           // Use more powerful model
      }
    },
    "custom_prompts": {
      "additional_context": "Focus on security and performance",
      "focus_areas": ["security", "performance"],
      "ignore_patterns": ["*.test.js"]
    }
  },
  
  "review_criteria": {
    "criteria_file": ".review-criteria.md",  // Path to criteria markdown
    "project_context": "E-commerce platform",
    "security_requirements": [...],
    "performance_requirements": {...},
    "custom_rules": [...]
  },
  
  "ci": {
    "github": {
      "comment_on_pr": true,
      "labels_on_pass": ["reviewed", "ready"],
      "labels_on_fail": ["needs-work"]
    }
  }
}
```

### Environment Variable Mappings

Environment variables can override any configuration setting. The complete mapping is defined in `config/env.mapping.json`, which documents:
- All available environment variables
- Their configuration paths
- Data types and validation
- Descriptions of their purpose

**Reference**: See `config/env.mapping.json` for the complete list of 30+ environment variables

### Provider Manifests

Provider manifests are self-documenting JSON files that define:
- CLI detection methods (command paths, fallback locations)
- Authentication requirements and verification commands
- Available models with performance characteristics
- Required and optional flags for different modes
- Output format specifications and normalization needs
- Common issues and their solutions

**Reference**: See `config/providers/*.manifest.json` for complete specifications

## Project-Specific Review Criteria

The review pipeline supports project-specific review criteria that augment the standard review process. There are two methods:

### Method 1: Review Criteria File (`.review-criteria.md`)

Best for complex, domain-specific requirements. Create `.review-criteria.md` in your project root:

```markdown
<project_context>
Financial services application handling payment processing.
All payment operations require PCI compliance review.
</project_context>

<critical_paths>
- `src/payments/**` - Payment processing (PCI compliance required)
- `src/auth/**` - Authentication system (zero tolerance for vulnerabilities)
- `database/migrations/**` - Schema changes (must be reversible)
</critical_paths>

<security_requirements>
- **Encryption**: All payment data must use AES-256 encryption
- **Authentication**: All endpoints require JWT authentication
- **Rate Limiting**: Public endpoints must implement rate limiting
</security_requirements>

<compliance_requirements>
- **PCI-DSS**: Credit card data must never be logged
- **SOC2**: All access must be logged with user and timestamp
</compliance_requirements>

<zero_tolerance_issues>
- Hardcoded credentials or API keys
- Unencrypted transmission of payment data
- SQL injection vulnerabilities
- Missing authentication checks
</zero_tolerance_issues>

<custom_checks>
- **Pattern**: `console\.log`
  **Severity**: high
  **Message**: Production code must not contain console.log statements
</custom_checks>
```

See `templates/.review-criteria.example.md` for a complete template with all available sections.

### Method 2: JSON Configuration

Add `review_criteria` section to `.reviewrc.json`:

```json
{
  "review_criteria": {
    "project_context": "E-commerce platform with high availability requirements",
    "security_requirements": [
      {
        "name": "PCI Compliance",
        "description": "All payment data must be encrypted",
        "paths": ["src/payments/**"],
        "severity_override": "critical"
      }
    ],
    "performance_requirements": {
      "response_time_ms": 200,
      "database_queries_per_request": 3,
      "memory_limit_mb": 512
    },
    "custom_rules": [
      {
        "pattern": "console\\.log",
        "severity": "high",
        "message": "Production code must not contain console.log"
      }
    ],
    "critical_paths": [
      "src/payments/**",
      {
        "path": "src/auth/**",
        "description": "Authentication system - security critical"
      }
    ],
    "zero_tolerance_issues": [
      "Hardcoded passwords",
      "Disabled authentication",
      "SQL injection"
    ]
  }
}
```

### Available Sections for Review Criteria

#### Markdown Format Sections:
- `<project_context>` - Project description and domain
- `<additional_review_dimensions>` - Custom review categories
- `<critical_paths>` - Paths requiring extra scrutiny
- `<project_standards>` - Coding standards and patterns
- `<compliance_requirements>` - HIPAA, PCI-DSS, GDPR, etc.
- `<security_requirements>` - Security-specific requirements
- `<performance_requirements>` - Performance thresholds
- `<zero_tolerance_issues>` - Critical issues that block merge
- `<custom_checks>` - Pattern-based checks

#### JSON Configuration Fields:
- `criteria_file` - Path to markdown criteria file
- `project_context` - Project description
- `security_requirements[]` - Security requirements with paths
- `performance_requirements{}` - Performance thresholds
- `custom_rules[]` - Pattern-based rules
- `critical_paths[]` - Paths needing extra review
- `compliance_requirements[]` - Compliance standards
- `zero_tolerance_issues[]` - Critical blocking issues

## Configuration Tools

### Config Loader CLI

Validate and inspect configuration:

```bash
# Validate configuration
node .review-pipeline/lib/config-loader.js validate

# Show resolved configuration
node .review-pipeline/lib/config-loader.js show

# Show configuration summary
node .review-pipeline/lib/config-loader.js summary
```

### Criteria Builder CLI

Test project criteria generation:

```bash
# Test criteria for current directory
node .review-pipeline/lib/criteria-builder.js

# Test for specific project
node .review-pipeline/lib/criteria-builder.js /path/to/project
```

### Generate Provider Commands

Generate CLI commands from configuration:

```bash
# Generate command for a provider
node .review-pipeline/lib/generate-provider-command.js claude

# Generate without timeout wrapper
node .review-pipeline/lib/generate-provider-command.js claude --no-timeout
```

## Common Configuration Scenarios

### 1. Disable a Provider

```json
{
  "providers": {
    "gemini": {
      "enabled": false
    }
  }
}
```

Or via environment variable:
```bash
export GEMINI_ENABLED=false
```

### 2. Use More Powerful Models

```json
{
  "providers": {
    "claude": {
      "model": "opus"
    },
    "codex": {
      "reasoning_effort": "high"
    }
  }
}
```

### 3. Sequential Execution (Debugging)

```json
{
  "execution": {
    "parallel": false,
    "timeout_seconds": 300
  }
}
```

Or via environment:
```bash
export REVIEW_PARALLEL=false
export REVIEW_TIMEOUT=300
```

### 4. Custom Test Command

**IMPORTANT SECURITY NOTE**: For security reasons, `TEST_CMD` can ONLY be configured via repository variables (GitHub Actions secrets/variables), never from `.reviewrc.json` or other project configuration files. This prevents arbitrary code execution from untrusted PR code.

To configure tests, set repository variables in GitHub:
```yaml
# In GitHub repository settings → Secrets and variables → Actions → Variables
TEST_CMD="make test"         # Required: The test command to run
TEST_TIMEOUT=600             # Optional: Timeout in seconds (default: 300)
```

In `.reviewrc.json`, you can only configure timeout (command will be ignored):
```json
{
  "testing": {
    // "command" field is IGNORED for security - use repository variables instead
    "timeout_seconds": 600   // Only timeout can be configured in project files
  }
}
```

### 5. Strict Gating Rules

```json
{
  "gating": {
    "must_fix_threshold": 0,
    "severity_thresholds": {
      "critical": 0,
      "high": 0,
      "medium": 0
    },
    "require_unanimous_pass": true
  }
}
```

### 6. Provider-Specific Timeouts

```json
{
  "providers": {
    "claude": {
      "timeout_override": 180
    },
    "codex": {
      "timeout_override": 240
    }
  }
}
```

### 7. Security-Focused Review

`.review-criteria.md`:
```markdown
<zero_tolerance_issues>
- Any use of eval() or exec()
- Hardcoded credentials
- SQL injection vulnerabilities
- Unvalidated user input
- Missing rate limiting on public endpoints
</zero_tolerance_issues>

<security_requirements>
- All endpoints must require authentication
- Input validation required on all user data
- Sensitive data must be encrypted at rest
</security_requirements>
```

## Configuration Validation

All configuration files are validated against JSON schemas:

- **Pipeline config**: Validated against `pipeline.schema.json`
- **Project config**: Validated against `project.schema.json`
- **Provider outputs**: Validated against `report.schema.json`

Validation runs automatically during:
- Auth check (`auth-check.sh`)
- Local review (`review-local.sh`)
- GitHub Actions workflow

## Best Practices

### 1. Use Project Configuration for Customization

Instead of modifying pipeline.config.json directly, create a `.reviewrc.json` in your project root:

```bash
# Create project config
cat > .reviewrc.json << EOF
{
  "testing": {
    // Note: "command" is ignored - TEST_CMD must be set via repository variables
    "timeout_seconds": 300
  },
  "review_overrides": {
    "providers": {
      "claude": {
        "model": "opus"
      }
    }
  }
}
EOF
```

### 2. Use Environment Variables for CI/CD

In GitHub Actions, use repository variables:

```yaml
env:
  CLAUDE_MODEL: ${{ vars.CLAUDE_MODEL }}
  TEST_CMD: ${{ vars.TEST_CMD }}
  REVIEW_TIMEOUT: ${{ vars.REVIEW_TIMEOUT }}
```

### 3. Validate Configuration Changes

Always validate after making changes:

```bash
node .review-pipeline/lib/config-loader.js validate
```

### 4. Check Resolved Configuration

View the final merged configuration:

```bash
node .review-pipeline/lib/config-loader.js show | jq .
```

### 5. Use Provider Manifests for Discovery

Provider manifests are the authoritative source for capabilities:

```bash
# View provider options
jq . .review-pipeline/config/providers/claude.manifest.json

# Check available models across providers
jq '.models[] | {id, name, speed, quality}' .review-pipeline/config/providers/*.manifest.json

# Find authentication requirements
jq '.authentication' .review-pipeline/config/providers/*.manifest.json
```

### 6. Start Simple with Review Criteria

Begin with basic criteria and expand as needed:

```markdown
<project_context>
Web application with user authentication
</project_context>

<critical_paths>
- `src/auth/**` - Authentication system
</critical_paths>

<zero_tolerance_issues>
- Hardcoded passwords
- SQL injection
</zero_tolerance_issues>
```

## Troubleshooting

### Configuration Not Loading

```bash
# Check for validation errors
node .review-pipeline/lib/config-loader.js validate

# View error details
node .review-pipeline/lib/config-loader.js show 2>&1
```

### Provider Not Running

```bash
# Check if provider is enabled
node -e "
  import('.review-pipeline/lib/config-loader.js').then(async (m) => {
    const loader = new m.default();
    await loader.load();
    console.log('Claude enabled:', loader.isProviderEnabled('claude'));
  });
"
```

### Environment Variables Not Working

```bash
# Check environment mapping
jq '.mappings[] | select(.env == "CLAUDE_MODEL")' .review-pipeline/config/env.mapping.json

# Verify environment variable is set
echo $CLAUDE_MODEL
```

### Command Generation Issues

```bash
# Test command generation
node .review-pipeline/lib/generate-provider-command.js claude

# Check provider manifest
jq '.required_flags.review' .review-pipeline/config/providers/claude.manifest.json
```

### Review Criteria Not Applied

```bash
# Test criteria generation
node .review-pipeline/lib/criteria-builder.js

# Check cache
ls -la .review-pipeline/workspace/.cache/

# Verify criteria file exists
cat .review-criteria.md
```

## Migration from Hardcoded Configuration

If you're upgrading from the previous hardcoded version:

1. **Review current settings**: Check your modified scripts for custom values
2. **Create project config**: Add customizations to `.reviewrc.json`
3. **Set environment variables**: Configure CI/CD variables
4. **Test locally**: Run `review-local.sh` to verify
5. **Update CI**: Ensure GitHub Actions variables are set

## Advanced Configuration

### Custom Provider Flags

Add additional CLI flags not covered by the standard configuration:

```json
{
  "providers": {
    "claude": {
      "additional_flags": ["--verbose", "--debug"]
    }
  }
}
```

### Additional Codex Configuration

Pass extra configuration to Codex:

```json
{
  "providers": {
    "codex": {
      "additional_config": {
        "custom_setting": "value"
      }
    }
  }
}
```

### Dynamic Configuration

Load configuration programmatically:

```javascript
import ConfigLoader from '.review-pipeline/lib/config-loader.js';

const loader = new ConfigLoader({
  projectConfigPath: './custom-config.json',
  verbose: true
});

await loader.load();

// Get provider config
const claudeConfig = loader.getProviderConfig('claude');

// Check if provider is enabled
if (loader.isProviderEnabled('claude')) {
  // Run Claude review
}

// Get all enabled providers
const providers = loader.getEnabledProviders();
```

### Build Project Criteria Programmatically

```javascript
import CriteriaBuilder from '.review-pipeline/lib/criteria-builder.js';

const builder = new CriteriaBuilder({
  projectRoot: '/path/to/project',
  criteriaFile: '.review-criteria.md'
});

const criteria = await builder.build();
if (criteria) {
  // Criteria will be automatically included in reviews
  const cachePath = await builder.saveToCache(criteria);
}
```

## Configuration Schema Reference

All configuration options are formally defined in JSON schemas with validation rules, types, and constraints:

- **Pipeline Schema** (`config/schemas/pipeline.schema.json`): Defines execution, provider, testing, and gating settings
- **Project Schema** (`config/schemas/project.schema.json`): Defines project configuration and review criteria options
- **Report Schema** (`config/schemas/report.schema.json`): Defines the structure of provider output reports

These schemas are the authoritative source for:
- Available configuration options
- Data types and validation rules
- Default values and constraints
- Required vs optional fields

To explore available options:
```bash
# View schema structure
jq '.properties | keys' .review-pipeline/config/schemas/pipeline.schema.json

# Check specific section
jq '.properties.execution' .review-pipeline/config/schemas/pipeline.schema.json
```

## Support

For issues or questions about configuration:
1. Check provider manifests for capabilities
2. Validate configuration with schemas
3. Review this documentation
4. Check error messages from config-loader
5. File issues with configuration details
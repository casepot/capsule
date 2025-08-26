# Troubleshooting Directory

This directory contains investigation logs and debugging resources for the exec-py project.

## Contents

### 📊 Investigation Logs
- **v0_1_investigation_log.json** - Detailed chronological log of v0.1 protocol incompatibility investigation
  - Documents the debugging process from initial symptoms to resolution
  - Includes hypotheses, falsification steps, and outcomes
  - Serves as a template for future investigations

### 📚 Documentation
- **log_maintenance_guide.md** - How to properly add entries to investigation logs
  - JSON structure and field requirements
  - Tagging conventions and best practices
  - Entry templates for common scenarios
  - Validation tools and scripts

- **development_insights.md** - Key learnings and patterns from investigations
  - Critical anti-patterns to avoid
  - Effective debugging strategies
  - Architecture patterns for reliability
  - Quick reference checklists

## Usage

### When Debugging Issues
1. Start by checking if similar issues are documented in existing logs
2. Create a new investigation log following the maintenance guide
3. Reference development insights for debugging strategies
4. Document your investigation for future reference

### Adding New Investigations
1. Create a new JSON file: `[issue_name]_investigation_log.json`
2. Follow the structure defined in `log_maintenance_guide.md`
3. Update insights document if you discover new patterns
4. Consider adding specific guides for recurring issue types

### Quick Start Commands

View investigation log:
```bash
python -m json.tool troubleshooting/v0_1_investigation_log.json | less
```

Validate JSON structure:
```bash
python -m json.tool troubleshooting/v0_1_investigation_log.json > /dev/null && echo "✓ Valid JSON"
```

Search for specific issues:
```bash
grep -l "protocol" troubleshooting/*.json
```

Extract all root causes:
```bash
jq '.[] | select(.tags | contains(["root_cause"])) | .summary' troubleshooting/*.json
```

## Contributing

When adding new troubleshooting resources:
1. Follow existing naming conventions
2. Update this README with new files
3. Ensure sensitive information is redacted
4. Include practical examples where possible
5. Test any provided scripts or commands

## Related Resources
- `/v0/streaming_issues/` - Documentation of v0 streaming problems
- `/v0_1/MIGRATION_v0_to_v0.1.0.md` - Migration guide between versions
- `/CRITICAL_FIXES_KNOWLEDGE.md` - Known critical issues and fixes
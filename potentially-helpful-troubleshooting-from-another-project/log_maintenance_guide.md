# Investigation Log Maintenance Guide

## Purpose
This guide explains how to properly add entries to investigation logs, ensuring consistency and traceability for debugging complex issues in the exec-py codebase.

## Log Structure

Each log entry is a JSON object with the following fields:

### Required Fields
- **timestamp** (string): ISO 8601 format (e.g., "2024-01-24T10:00:00Z")
- **tags** (array): Categorization tags (see Tag Convention below)
- **summary** (string): Concise one-line description (max 100 chars)
- **details** (string): Thorough explanation of the observation, action, or finding
- **outcome** (string): Immediate result or next steps

### Optional Fields (use `null` when not applicable)
- **hypothesis** (string|null): The theory being tested
- **falsification_steps** (string|null): How the hypothesis was investigated
- **notes** (string|null): Additional observations or insights

## Tag Convention

Use these standardized tags for consistency:

### Investigation Phase Tags
- `initial_symptom` - First observed problem
- `observation` - Data gathered without hypothesis
- `hypothesis` - Theory about cause
- `investigation` - Active testing/debugging
- `breakthrough` - Key discovery
- `root_cause` - Confirmed problem source

### Action Tags
- `fix_decision` - Rationale for a fix
- `implementation` - Code changes made
- `validation` - Testing/verification
- `testing` - Test execution results

### Meta Tags
- `reflection` - Process analysis
- `process_improvement` - Methodology insights
- `lessons_learned` - Knowledge for future
- `summary` - Synthesis of findings

## Adding New Entries

### Step 1: Determine Entry Type

```json
// Hypothesis Testing Entry
{
  "timestamp": "2024-01-24T15:00:00Z",
  "tags": ["hypothesis", "investigation"],
  "summary": "Testing if connection pooling causes timeout",
  "details": "Observed timeouts correlate with pool exhaustion. Testing theory that default pool size (10) is insufficient for concurrent requests.",
  "hypothesis": "Connection pool exhaustion causing timeouts",
  "falsification_steps": "1. Increased pool size to 50, 2. Ran load test with 30 concurrent requests, 3. Monitored pool metrics",
  "outcome": "Timeouts eliminated with larger pool",
  "notes": "Need to determine optimal pool size"
}

// Fix Implementation Entry
{
  "timestamp": "2024-01-24T15:30:00Z",
  "tags": ["fix_decision", "implementation"],
  "summary": "Increased connection pool size",
  "details": "Changed pool_size from 10 to 30 based on load testing. This provides headroom for burst traffic while avoiding resource waste.",
  "hypothesis": null,
  "falsification_steps": null,
  "outcome": "Deployed to staging for validation",
  "notes": "Monitor memory usage after deployment"
}

// Observation Entry
{
  "timestamp": "2024-01-24T16:00:00Z",
  "tags": ["observation", "testing"],
  "summary": "Staging environment performance metrics",
  "details": "After 2 hours with increased pool: 0 timeouts, avg response time 45ms (down from 250ms), memory usage +15MB",
  "hypothesis": null,
  "falsification_steps": null,
  "outcome": "Fix validated, ready for production",
  "notes": "Memory increase acceptable given performance gain"
}
```

### Step 2: Maintain Chronological Order

Always append new entries in chronological order. If adding historical context:
1. Use accurate timestamps when known
2. Use estimated timestamps with note when uncertain
3. Never reorder existing entries

### Step 3: Link Related Entries

Reference previous entries when building on them:

```json
{
  "timestamp": "2024-01-24T17:00:00Z",
  "tags": ["reflection", "summary"],
  "summary": "Resolution summary for timeout issue",
  "details": "Issue introduced at 10:00:00Z resolved by connection pool fix at 15:30:00Z. Root cause was insufficient concurrent connections, not the initially suspected memory leak (11:00:00Z entry).",
  "hypothesis": null,
  "falsification_steps": null,
  "outcome": "Issue closed, monitoring continues",
  "notes": "Initial hypothesis led us wrong direction - check resource limits before memory profiling"
}
```

## Best Practices

### DO:
1. **Be Specific**: Include exact error messages, file paths, line numbers
2. **Document Dead Ends**: Failed hypotheses are valuable learning
3. **Include Context**: Version numbers, environment details, configuration
4. **Time Everything**: Use actual timestamps, not relative times
5. **Cross-Reference**: Link to commits, PRs, issues when relevant
6. **Capture Insights**: Note what could have been done better

### DON'T:
1. **Skip Steps**: Don't omit failed attempts or wrong turns
2. **Assume Context**: Spell out acronyms and technical terms first use
3. **Combine Unrelated**: One entry per hypothesis/action/observation
4. **Edit History**: Add corrections as new entries, never modify old ones
5. **Use Vague Language**: Avoid "it seems", "maybe", "probably"

## Common Entry Templates

### Starting Investigation
```json
{
  "timestamp": "ISO_8601",
  "tags": ["initial_symptom", "observation"],
  "summary": "Brief problem description",
  "details": "Detailed symptoms, error messages, affected components, frequency",
  "hypothesis": null,
  "falsification_steps": null,
  "outcome": "Investigation started, checking [specific area]",
  "notes": "User impact: [description]"
}
```

### Testing Hypothesis
```json
{
  "timestamp": "ISO_8601",
  "tags": ["hypothesis", "investigation"],
  "summary": "Testing [specific theory]",
  "details": "Reason for hypothesis, expected vs actual behavior",
  "hypothesis": "Clear statement of theory",
  "falsification_steps": "1. Step one, 2. Step two, 3. Observations",
  "outcome": "Hypothesis [confirmed/falsified/partially correct]",
  "notes": "Next hypothesis to test or area to investigate"
}
```

### Implementing Fix
```json
{
  "timestamp": "ISO_8601",
  "tags": ["fix_decision", "implementation"],
  "summary": "Implementing [fix description]",
  "details": "What changed, why this approach, affected files/components",
  "hypothesis": null,
  "falsification_steps": null,
  "outcome": "Fix applied, testing in [environment]",
  "notes": "Potential side effects or areas to monitor"
}
```

## Validation Checklist

Before committing log updates:
- [ ] All timestamps are in ISO 8601 format
- [ ] Entries are in chronological order
- [ ] Required fields are present (not null unless optional)
- [ ] Tags accurately reflect entry content
- [ ] Hypotheses have corresponding falsification/validation
- [ ] File is valid JSON
- [ ] No sensitive information (passwords, keys, PII)

## Tools

### Validate JSON Structure
```bash
python -m json.tool troubleshooting/v0_1_investigation_log.json > /dev/null
echo "JSON is valid" || echo "JSON has errors"
```

### Add Timestamp
```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"  # Current UTC timestamp
```

### Check Chronological Order
```python
import json
from datetime import datetime

with open('troubleshooting/v0_1_investigation_log.json') as f:
    logs = json.load(f)
    
timestamps = [datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00')) 
              for log in logs]
              
if timestamps == sorted(timestamps):
    print("✓ Logs are in chronological order")
else:
    print("✗ Logs are not in chronological order")
```
# Environment Security and Hardening Issues

This document covers environment handling, security hardening, and data validation issues that affect the overall security posture.

## 1. Environment Sanitization Using Dirty Base

**Severity:** MEDIUM  
**File:** `.review-pipeline/lib/execute-provider.js`  
**Lines:** 77-89  
**Status:** Confirmed by Gemini review

### Current Implementation
```javascript
// Lines 77-89
const sanitizedEnv = { ...(cmd.env || {}) }; // Starts with dirty environment
const sensitiveKeys = [
  'GH_TOKEN', 
  'GITHUB_TOKEN', 
  'ANTHROPIC_API_KEY', 
  'OPENAI_API_KEY', 
  'GEMINI_API_KEY',
  'ANTHROPIC_AUTH_TOKEN'
];

for (const key of sensitiveKeys) {
  delete sanitizedEnv[key];
}
```

### Problem
- Starts with potentially dirty environment (`cmd.env` includes `process.env`)
- Only removes known sensitive variables
- New sensitive variables not in list will leak through
- Reactive approach instead of proactive

### Recommended Fix - Clean Room Approach
```javascript
// Build clean environment with only necessary variables
const cleanEnv = {
  // Core system variables
  PATH: process.env.PATH,
  HOME: process.env.HOME || process.env.USERPROFILE,
  TMPDIR: process.env.TMPDIR || '/tmp',
  USER: process.env.USER,
  
  // Tool-specific variables from cmd.env
  TOOL: cmd.env?.TOOL,
  MODEL: cmd.env?.MODEL,
  
  // CI-specific safe variables
  CI: process.env.CI,
  GITHUB_ACTIONS: process.env.GITHUB_ACTIONS,
  GITHUB_WORKSPACE: process.env.GITHUB_WORKSPACE,
  GITHUB_REPOSITORY: process.env.GITHUB_REPOSITORY,
  PR_NUMBER: process.env.PR_NUMBER
};

// Remove any undefined values
Object.keys(cleanEnv).forEach(key => {
  if (cleanEnv[key] === undefined) delete cleanEnv[key];
});

const proc = spawn(cmd.command, args, {
  cwd: cmd.workingDirectory,
  env: cleanEnv, // Use clean environment
  stdio: ['pipe', 'pipe', 'pipe']
});
```

---

## 2. Keychain Diagnostics Leaking in CI Logs

**Severity:** LOW  
**File:** `.github/workflows/pr-multimodel-review.yml`  
**Lines:** 88-93  
**Status:** Confirmed by Codex review

### Issue
Keychain information printed to CI logs:
```yaml
# Lines 88-93
- name: Debug keychain access (macOS)
  if: runner.os == 'macOS'
  run: |
    security show-keychain-info
    security find-generic-password -s "Anthropic" || echo "No Anthropic keychain entry"
    # Check for Claude Code OAuth token
```

### Security Concerns
- Reveals metadata about stored credentials
- Shows which services have keychain entries
- Could leak partial credential information in verbose mode

### Fix Required
```yaml
- name: Validate keychain access (macOS)
  if: runner.os == 'macOS' && vars.DEBUG_KEYCHAIN != 'true'
  run: |
    # Only check existence, don't print details
    if security find-generic-password -s "Anthropic" >/dev/null 2>&1; then
      echo "✓ Anthropic keychain entry found"
    else
      echo "✗ No Anthropic keychain entry"
    fi
```

Or remove entirely for production:
```yaml
# Remove keychain diagnostics in production
# Only enable via debug flag
- name: Debug keychain access (macOS)
  if: runner.os == 'macOS' && vars.DEBUG_MODE == 'true'
  run: |
    echo "::debug::Checking keychain entries"
    # ... diagnostic commands
```

---

## 3. Aggregation Continues on Invalid JSON

**Severity:** MEDIUM  
**File:** `.review-pipeline/scripts/aggregate-reviews.mjs`  
**Lines:** 80-95  
**Status:** Confirmed by Gemini review

### Current Behavior
```javascript
// Lines 80-85
if (!validate(json)) {
  // Log validation errors as warnings
  const validationErrors = ajv.errorsText(validate.errors, { separator: '\n- ' });
  errors.push(`Schema validation failed for ${tool}:\n- ${validationErrors}`);
  
  // Check if we have minimum required fields to proceed
  if (!json.findings && !json.summary) {
    errors.push(`CRITICAL: Skipping ${tool} - No usable content`);
    reportStatus[tool] = 'skipped-invalid';
    continue;
  }
  
  // Mark as having validation issues but still usable
  reportStatus[tool] = 'parsed-with-warnings';
  json._validation_warnings = validationErrors;
}
results.push(json); // Still includes invalid report
```

### Problems
- Invalid reports are included in aggregation
- Could lead to incomplete or misleading summary
- Gate might pass based on partial data

### Fix Required
```javascript
// Stricter validation with configuration option
const strictValidation = config.aggregation?.strict_validation ?? false;

if (!validate(json)) {
  const validationErrors = ajv.errorsText(validate.errors, { separator: '\n- ' });
  errors.push(`Schema validation failed for ${tool}:\n- ${validationErrors}`);
  
  if (strictValidation) {
    // In strict mode, skip invalid reports entirely
    errors.push(`CRITICAL: Skipping ${tool} in strict mode due to validation failure`);
    reportStatus[tool] = 'failed-validation';
    continue; // Don't include in results
  }
  
  // Non-strict mode: try to use if has minimum data
  if (!json.findings && !json.summary) {
    errors.push(`CRITICAL: Skipping ${tool} - No usable content`);
    reportStatus[tool] = 'skipped-invalid';
    continue;
  }
  
  // Include with warnings
  reportStatus[tool] = 'parsed-with-warnings';
  json._validation_warnings = validationErrors;
}
```

---

## 4. Missing Security Documentation Updates

**Severity:** LOW  
**File:** `.review-pipeline/SECURITY_NOTES.md`  
**Lines:** Various  
**Status:** Confirmed by Gemini review

### Issues in Documentation
1. Claims `eval "$TEST_CMD"` is fixed, but `sh -c` still vulnerable
2. Doesn't document the Gemini YOLO mode issue
3. Missing path traversal vulnerability documentation
4. No mention of environment sanitization approach

### Required Updates
```markdown
# SECURITY_NOTES.md updates needed

## Known Issues (Not Yet Fixed)

### 1. TEST_CMD Execution
- **Status:** PARTIALLY FIXED
- **Current:** Uses `sh -c "$TEST_CMD"` which still allows injection
- **Required:** Parse TEST_CMD into array or use fixed script
- **Severity:** HIGH in public repos, MEDIUM in private with trusted runners

### 2. Provider Path Traversal
- **Status:** KNOWN, TODO IN CODE
- **Location:** command-builder.js:100-103
- **Required:** Provider whitelist validation
- **Severity:** CRITICAL

### 3. Gemini Auto-Approve Mode
- **Status:** FORCED ON
- **Location:** command-builder.js:259-266
- **Required:** Respect configuration settings
- **Severity:** HIGH

## Security Best Practices

### Environment Variables
- Use clean-room approach: start with empty env, add only required
- Never rely solely on blacklist filtering
- Document all required environment variables

### Path Validation
- Always use `path.relative()` for validation, not `startsWith()`
- Validate against whitelist when possible
- Reject '..' in user-provided paths
```

---

## 5. Unit Test Misalignment

**Severity:** MEDIUM  
**File:** `.review-pipeline/tests/unit/provider-executor.test.js`  
**Lines:** 249-279  
**Status:** Confirmed by Gemini review

### Issue
Tests claim ProviderExecutor filters environment, but it actually doesn't:
```javascript
// Test expects filtering in executor
it('should filter sensitive environment variables', async () => {
  // Test asserts executor filters env
  expect(command.env.GITHUB_TOKEN).toBeUndefined();
});
```

But executor passes environment from CommandBuilder:
```javascript
// execute-provider.js
const sanitizedEnv = { ...(cmd.env || {}) }; // cmd.env from CommandBuilder
```

### Fix Options

Option 1: Move filtering to ProviderExecutor (recommended)
```javascript
// In ProviderExecutor.execute()
const cleanEnv = this.buildCleanEnvironment(cmd.env);
const proc = spawn(cmd.command, args, {
  env: cleanEnv
});
```

Option 2: Update tests to match reality
```javascript
// Fix test to check CommandBuilder filtering
it('should receive pre-filtered environment from CommandBuilder', async () => {
  // CommandBuilder should do the filtering
  const cmd = await commandBuilder.buildCommand('claude');
  expect(cmd.env.GITHUB_TOKEN).toBeUndefined();
});
```

---

## Summary of Security Hardening Tasks

### Priority 1 - Security Critical
1. Implement clean-room environment building
2. Fix aggregation to handle strict validation mode
3. Update security documentation with current issues

### Priority 2 - Data Integrity
1. Add configuration for strict JSON validation
2. Align unit tests with actual implementation
3. Remove or guard keychain diagnostics

### Priority 3 - Documentation
1. Update SECURITY_NOTES.md with all known issues
2. Document environment variable requirements
3. Add security testing guidelines

## Validation Commands

```bash
# Test environment filtering
node -e "
  const ProviderExecutor = require('./lib/execute-provider.js').default;
  process.env.GITHUB_TOKEN = 'secret';
  const executor = new ProviderExecutor();
  // Should not leak GITHUB_TOKEN
"

# Test aggregation strict mode
node scripts/aggregate-reviews.mjs --strict

# Verify no sensitive data in logs
npm test 2>&1 | grep -E "(API_KEY|TOKEN|PASSWORD|SECRET)"
```

## Configuration Additions

Add to `pipeline.config.json`:
```json
{
  "security": {
    "environment_mode": "clean_room", // or "blacklist"
    "strict_validation": true,
    "debug_keychain": false,
    "allowed_env_vars": [
      "PATH", "HOME", "USER", "TMPDIR",
      "CI", "GITHUB_*", "PR_NUMBER"
    ]
  },
  "aggregation": {
    "strict_validation": true,
    "continue_on_error": false
  }
}
```
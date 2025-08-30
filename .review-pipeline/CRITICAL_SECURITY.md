# Critical Security Issues - MUST FIX

This document contains critical security vulnerabilities that must be fixed before merging. All issues have been validated through code inspection and test failures.

## 1. Path Traversal Vulnerability in Provider Manifest Loading

**Severity:** CRITICAL  
**File:** `.review-pipeline/lib/command-builder.js`  
**Lines:** 100-103  
**Status:** Confirmed by all three reviews + TODO comment in code

### Issue
Provider names are used directly to construct file paths without validation, allowing directory traversal attacks:

```javascript
// Lines 100-103
// TODO: Add provider whitelist to prevent path traversal (only allow ['claude', 'codex', 'gemini'])
const manifestPath = path.join(this.packageDir, 'config', 'providers', `${provider}.manifest.json`);
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
```

### Attack Vector
An attacker could provide `provider = '../../../../../../etc/passwd'` to read arbitrary files on the system.

### Fix Required
```javascript
// Add before line 100
const ALLOWED_PROVIDERS = ['claude', 'codex', 'gemini'];
if (!ALLOWED_PROVIDERS.includes(provider)) {
  if (this.verbose) {
    console.error(`Unknown provider: ${provider}`);
  }
  return null; // Graceful handling for unknown providers
}
```

### Test Validation
- Test at `tests/integration/security.test.js:463-481` expects this to return null for malicious providers
- Currently fails with ENOENT error instead of graceful null return

---

## 2. Command Injection via TEST_CMD Shell Execution

**Severity:** CRITICAL  
**File:** `.github/workflows/pr-multimodel-review.yml`  
**Lines:** 172  
**Status:** Confirmed by all three reviews + TODO comment in workflow

### Issue
TEST_CMD is executed using `sh -c`, allowing shell injection even though it's limited to repository variables:

```yaml
# Line 172
timeout 300 sh -c "set -e; $TEST_CMD" >> .review-pipeline/workspace/context/tests.txt 2>&1
```

### Attack Vector
If TEST_CMD contains `npm test; rm -rf /`, the shell will execute both commands. While TEST_CMD comes from repository variables (not PR-controlled), this is still a significant risk on self-hosted runners.

### Fix Required
Option 1: Use a fixed test script
```yaml
# Replace line 172
timeout 300 .review-pipeline/scripts/run-tests.sh "$TEST_CMD"
```

Option 2: Parse TEST_CMD into array (more complex)
```yaml
# Use Node.js to safely execute
node -e "
  const { spawn } = require('child_process');
  const cmd = process.env.TEST_CMD.split(' ');
  spawn(cmd[0], cmd.slice(1), { stdio: 'inherit' });
"
```

### Evidence
- SECURITY_NOTES.md acknowledges this issue but incorrectly claims it's fixed
- TODO comment on line 171: "Parse TEST_CMD into array for fully safe execution"

---

## 3. Gemini Forced into Auto-Approve (YOLO) Mode

**Severity:** HIGH  
**File:** `.review-pipeline/lib/command-builder.js`  
**Lines:** 259-266  
**Status:** Confirmed by Codex review + code inspection

### Issue
Gemini CLI is unconditionally forced into auto-approve mode, ignoring configuration:

```javascript
// Lines 259-263
// Use YOLO approval mode to auto-approve all tool actions
// This allows Gemini to execute files and run commands without interaction
// NOTE: --approval-mode=yolo needs verification (may not be a valid flag)
// Security: Remove or sandbox this for public repos (auto-approves all actions)
args.push('--approval-mode=yolo');
```

Meanwhile, configuration explicitly sets `yolo: false`:
```json
// config/pipeline.config.json:40
"yolo": false,
```

### Attack Vector
Gemini can execute arbitrary commands and file operations on the runner without any approval, even when configuration explicitly disables this.

### Fix Required
```javascript
// Replace lines 259-266
// Only enable sandbox mode if configured
if (flags.sandbox !== false) {
  args.push('-s');
}

// Only enable YOLO mode if explicitly configured
if (flags.yolo === true) {
  args.push('-y'); // or '--approval-mode=yolo' if that's the correct flag
}
```

---

## 4. Weak Output Path Validation

**Severity:** MEDIUM  
**File:** `.review-pipeline/lib/execute-provider.js`  
**Lines:** 287-291  
**Status:** Confirmed by Codex review + TODO comment in code

### Issue
Output path validation uses `startsWith` which can be bypassed:

```javascript
// Lines 287-291
// TODO: Use path.relative instead of startsWith (can be bypassed with /reports-evil)
if (!resolvedPath.startsWith(expectedDir)) {
  throw new Error(`Output path outside allowed directory: ${outputPath}`);
}
```

### Attack Vector
A path like `/tmp/review-pipeline/workspace/reports-evil/../../etc/passwd` would pass the startsWith check but escape the intended directory.

### Fix Required
```javascript
// Replace lines 287-291
const relative = path.relative(expectedDir, resolvedPath);
if (relative.startsWith('..') || path.isAbsolute(relative)) {
  throw new Error(`Output path outside allowed directory: ${outputPath}`);
}
```

---

## Summary of Required Actions

1. **IMMEDIATE**: Add provider whitelist validation in command-builder.js
2. **IMMEDIATE**: Replace `sh -c` execution of TEST_CMD with safer alternative
3. **HIGH PRIORITY**: Remove forced YOLO mode for Gemini, respect configuration
4. **MEDIUM PRIORITY**: Fix output path validation to use path.relative

## Validation Steps

After fixes are applied, verify:
1. Run `npm test` in `.review-pipeline/` - all security tests should pass
2. Attempt path traversal with provider name `../../etc/passwd` - should return null
3. Set TEST_CMD with semicolon - should not execute multiple commands
4. Gemini should respect yolo:false configuration setting
5. Output paths with creative names shouldn't bypass validation
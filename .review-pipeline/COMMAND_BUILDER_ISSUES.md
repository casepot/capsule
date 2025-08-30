# Command Builder Implementation Issues

This document covers issues in the command building logic that affect correctness, security, and functionality.

## 1. Provider Error Handling Inconsistency

**Severity:** HIGH  
**File:** `.review-pipeline/lib/command-builder.js`  
**Lines:** 113-116  
**Status:** Confirmed by Claude review + TODO comment

### Issue
Unknown providers throw an error instead of returning null:
```javascript
// Lines 113-116
default:
  // TODO: Return null instead of throwing for unknown providers (tests expect graceful handling)
  throw new Error(`Unknown provider: ${provider}`);
```

### Expected Behavior
Tests expect graceful degradation - unknown providers should return null to allow fallback handling.

### Fix Required
```javascript
default:
  if (this.verbose) {
    console.error(`Unknown provider: ${provider}`);
  }
  return null; // Graceful handling for unknown providers
```

### Impact
- Breaks error handling flow
- Prevents graceful degradation
- Causes test failures

---

## 2. Missing Provider Whitelist Validation

**Severity:** CRITICAL (Security)  
**File:** `.review-pipeline/lib/command-builder.js`  
**Lines:** 100-103  
**Status:** Confirmed - TODO comment acknowledges issue

### Issue
No validation of provider parameter before using in path:
```javascript
// Line 101 - TODO comment
// TODO: Add provider whitelist to prevent path traversal (only allow ['claude', 'codex', 'gemini'])
const manifestPath = path.join(this.packageDir, 'config', 'providers', `${provider}.manifest.json`);
```

### Complete Fix Implementation
```javascript
// Add at the beginning of buildCommand method (line 85)
async buildCommand(provider, options = {}) {
  // Validate provider against whitelist
  const ALLOWED_PROVIDERS = ['claude', 'codex', 'gemini'];
  if (!ALLOWED_PROVIDERS.includes(provider)) {
    if (this.verbose) {
      console.error(`Invalid provider: ${provider}. Allowed providers: ${ALLOWED_PROVIDERS.join(', ')}`);
    }
    return null;
  }
  
  // Continue with existing logic...
  const config = await this.loadConfiguration();
  // ...
}
```

---

## 3. Options.prompt Not Included in Build

**Severity:** MEDIUM  
**File:** `.review-pipeline/lib/command-builder.js`  
**Lines:** 346-350  
**Status:** Confirmed by TODO comment

### Issue
The `options.prompt` parameter is ignored when building prompts:
```javascript
// Lines 346-350
// TODO: Add support for options.prompt - currently ignored (tests expect it to be included)
// if (options.prompt) {
//   sections.push('\n=== ADDITIONAL PROMPT ===');
//   sections.push(options.prompt);
// }
```

### Impact
- Custom prompts from options are ignored
- Tests expecting prompt injection fail
- Reduces flexibility of the command builder

### Fix Required
```javascript
// Uncomment and implement lines 347-350
if (options.prompt) {
  sections.push('\n=== ADDITIONAL PROMPT ===');
  sections.push(options.prompt);
  sections.push('=== END ADDITIONAL PROMPT ===\n');
}
```

---

## 4. Command Injection via jq in Shell Scripts

**Severity:** MEDIUM  
**File:** `.review-pipeline/scripts/run-provider-review.sh`  
**Lines:** 45-48  
**Status:** Confirmed by Claude review

### Issue
Model extraction using jq without validation:
```bash
# Lines 45-48
MODEL=$(echo "$CONFIG_JSON" | jq -r ".providers.${PROVIDER}.model // \"$DEFAULT_MODEL\"")
```

### Attack Vector
If CONFIG_JSON contains malicious values, they could be executed when interpolated.

### Fix Required
```bash
# Validate MODEL after extraction
MODEL=$(echo "$CONFIG_JSON" | jq -r ".providers.${PROVIDER}.model // \"$DEFAULT_MODEL\"")

# Validate against known models
case "$MODEL" in
  opus|sonnet|haiku|gpt-4|gpt-5|gemini-2.5-pro|gemini-pro)
    # Valid model
    ;;
  *)
    echo "Error: Invalid model '$MODEL' for provider $PROVIDER" >&2
    exit 1
    ;;
esac
```

---

## 5. Hardcoded YOLO Mode for Gemini

**Severity:** HIGH (Security)  
**File:** `.review-pipeline/lib/command-builder.js`  
**Lines:** 259-268  
**Status:** Confirmed - forces auto-approve regardless of config

### Current Implementation
```javascript
// Lines 259-263
// Use YOLO approval mode to auto-approve all tool actions
args.push('--approval-mode=yolo');

// Lines 266-268 - Redundant yolo flag
if (flags.yolo !== false) {
  args.push('-y');
}
```

### Configuration Says
```json
// config/pipeline.config.json
"gemini": {
  "flags": {
    "yolo": false  // Explicitly disabled!
  }
}
```

### Fix Required
```javascript
// Replace lines 255-268
// Enable sandbox mode if configured
if (flags.sandbox !== false) {
  args.push('-s');
}

// Only enable YOLO/auto-approve if explicitly requested
if (flags.yolo === true) {
  // Check which flag format Gemini actually uses
  args.push('-y'); // or '--approval-mode=yolo'
}
```

---

## 6. Command Detection Logic Issues

**Severity:** LOW  
**File:** `.review-pipeline/lib/command-builder.js`  
**Lines:** 38-80  
**Status:** Works but could be more robust

### Current Issues
1. Uses `which` command via execFileSync (line 46)
2. Doesn't cache detection results
3. No fallback for Windows systems

### Suggested Improvements
```javascript
async detectCommandPath(manifest) {
  // Cache detection results
  if (this._commandCache && this._commandCache[manifest.id]) {
    return this._commandCache[manifest.id];
  }
  
  // Platform-specific command detection
  const isWindows = process.platform === 'win32';
  const whichCmd = isWindows ? 'where' : 'which';
  
  // ... rest of detection logic
  
  // Cache the result
  if (!this._commandCache) this._commandCache = {};
  this._commandCache[manifest.id] = detectedPath;
  
  return detectedPath;
}
```

---

## Summary of Required Fixes

### Priority 1 - Breaking Issues
1. Add provider whitelist validation
2. Fix error handling to return null for unknown providers
3. Remove forced YOLO mode for Gemini

### Priority 2 - Functionality Issues
1. Include options.prompt in buildPrompt
2. Add model validation in shell scripts

### Priority 3 - Improvements
1. Cache command detection results
2. Add Windows compatibility for command detection

## Testing After Fixes

```bash
# Test provider validation
node -e "
  const CommandBuilder = require('./lib/command-builder.js').default;
  const builder = new CommandBuilder();
  builder.buildCommand('../../etc/passwd').then(console.log); // Should return null
"

# Test error handling
node -e "
  const CommandBuilder = require('./lib/command-builder.js').default;
  const builder = new CommandBuilder();
  builder.buildCommand('unknown-provider').then(console.log); // Should return null
"

# Test Gemini configuration
node -e "
  const CommandBuilder = require('./lib/command-builder.js').default;
  const builder = new CommandBuilder();
  builder.buildCommand('gemini').then(cmd => {
    console.log('Has YOLO:', cmd.args.includes('-y') || cmd.args.includes('--approval-mode=yolo'));
  });
"
```
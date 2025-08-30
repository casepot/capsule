#!/usr/bin/env bash
# Test script to verify security fixes

set -euo pipefail

echo "=== Testing Security Fixes ==="
echo

# Test 1: Verify auth-check.sh doesn't use eval
echo "Test 1: Checking auth-check.sh for eval usage..."
if grep -q "eval.*auth_cmd" scripts/auth-check.sh; then
  echo "❌ FAIL: auth-check.sh still contains eval with auth_cmd"
  exit 1
else
  echo "✅ PASS: auth-check.sh no longer uses eval with auth_cmd"
fi
echo

# Test 2: Verify hardcoded auth commands exist
echo "Test 2: Checking for hardcoded auth commands..."
if grep -q "case.*provider.*in" scripts/auth-check.sh && \
   grep -q "claude -p 'echo test'" scripts/auth-check.sh && \
   grep -q "codex exec -s read-only 'echo test'" scripts/auth-check.sh && \
   grep -q "gemini -p 'ping'" scripts/auth-check.sh; then
  echo "✅ PASS: Hardcoded auth commands found for all providers"
else
  echo "❌ FAIL: Missing hardcoded auth commands"
  exit 1
fi
echo

# Test 3: Verify TEST_CMD is not loaded from project config
echo "Test 3: Checking config-loader.js for TEST_CMD security..."
if grep -q "config.testing?.command" lib/config-loader.js; then
  echo "❌ FAIL: config-loader.js still loads TEST_CMD from project config"
  exit 1
else
  echo "✅ PASS: config-loader.js only uses TEST_CMD from environment"
fi
echo

# Test 4: Verify workflow doesn't use bash -c for TEST_CMD
echo "Test 4: Checking workflow for bash -c usage with TEST_CMD..."
if grep -q 'bash -c.*TEST_CMD' ../.github/workflows/pr-multimodel-review.yml; then
  echo "❌ FAIL: Workflow still uses bash -c with TEST_CMD"
  exit 1
else
  echo "✅ PASS: Workflow doesn't use bash -c with TEST_CMD"
fi
echo

# Test 5: Verify GH_TOKEN is unset before running tests
echo "Test 5: Checking for GH_TOKEN unsetting in workflow..."
if grep -q "unset GH_TOKEN" ../.github/workflows/pr-multimodel-review.yml; then
  echo "✅ PASS: Workflow unsets GH_TOKEN before running tests"
else
  echo "❌ FAIL: Workflow doesn't unset GH_TOKEN before tests"
  exit 1
fi
echo

# Test 6: Verify GH_TOKEN is unset before running providers
echo "Test 6: Checking for GH_TOKEN unsetting in run-provider-review.sh..."
if grep -q "unset GH_TOKEN" scripts/run-provider-review.sh; then
  echo "✅ PASS: run-provider-review.sh unsets GH_TOKEN before providers"
else
  echo "❌ FAIL: run-provider-review.sh doesn't unset GH_TOKEN"
  exit 1
fi
echo

echo

# Test 7: Verify TEST_CMD does NOT use dangerous eval pattern
echo "Test 7: Checking TEST_CMD execution avoids eval pattern..."
if ! grep -q 'eval "$TEST_CMD"' ../.github/workflows/pr-multimodel-review.yml; then
  echo "✅ PASS: TEST_CMD execution avoids dangerous eval pattern"
else
  echo "❌ FAIL: TEST_CMD uses dangerous eval pattern - security vulnerability!"
  exit 1
fi
echo

# Test 8: Verify command-builder.js uses execFileSync instead of execSync
echo "Test 8: Checking command-builder.js for safe command detection..."
if grep -q "execFileSync('which'" lib/command-builder.js && \
   ! grep -q "execSync(\`which" lib/command-builder.js; then
  echo "✅ PASS: command-builder.js uses execFileSync for safe command detection"
else
  echo "❌ FAIL: command-builder.js still uses unsafe execSync with interpolation"
  exit 1
fi
echo

# Test 9: Verify import.meta.url fix in normalize-json.js
echo "Test 9: Checking normalize-json.js for correct module detection..."
if grep -q "import.meta.url.endsWith(process.argv\[1\])" scripts/normalize-json.js; then
  echo "✅ PASS: normalize-json.js uses correct import.meta.url check"
else
  echo "❌ FAIL: normalize-json.js still has incorrect import.meta.url check"
  exit 1
fi
echo

# Test 10: Verify Jest tests exist
echo "Test 10: Checking for JavaScript test infrastructure..."
if [ -f "jest.config.js" ] && [ -d "tests/unit" ] && [ -f "package.json" ]; then
  if grep -q '"test":' package.json; then
    echo "✅ PASS: Jest testing infrastructure is set up"
  else
    echo "❌ FAIL: Jest test script not found in package.json"
    exit 1
  fi
else
  echo "❌ FAIL: Jest testing infrastructure not found"
  exit 1
fi
echo

echo "=== All Security Tests Passed ==="
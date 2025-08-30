# Security Notes for Review Pipeline

## Overview
This document outlines security considerations and improvements made to the review pipeline system. As this is a private repository with controlled access, some security measures are balanced with operational needs.

## Recent Security Improvements

### 1. Removed eval Command Execution (CRITICAL - FIXED)
**Issue**: The workflow previously used `eval "$TEST_CMD"` which could allow shell injection even with repository-controlled variables.
**Fix**: Changed to `bash -c "$TEST_CMD"` for safer execution (.github/workflows/pr-multimodel-review.yml:161)

### 2. Environment Variable Sanitization (FIXED)
**Issue**: Sensitive environment variables could potentially leak to provider processes.
**Fix**: Added defense-in-depth sanitization at executor boundary (.review-pipeline/lib/execute-provider.js:77-89)
- Removes: GH_TOKEN, GITHUB_TOKEN, ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_AUTH_TOKEN
- Note: Shell scripts also perform this sanitization, providing multiple layers of protection

### 3. TEST_CMD Security (FIXED)
**Issue**: Test commands could be injected via project configuration files.
**Fix**: TEST_CMD can ONLY be set via repository variables, never from .reviewrc.json
- Enforced in: .review-pipeline/lib/config-loader.js:268-270
- Documented in: .review-pipeline/CONFIGURATION.md

### 4. Removed Shell Command Building (FIXED)  
**Issue**: buildShellCommand() method constructed shell commands as strings, vulnerable to injection.
**Fix**: Completely removed buildShellCommand() method. All execution now uses structured spawn() commands.

## Known Considerations

### Authentication
- Currently using OAuth/subscription-based authentication for providers
- Keychain integration has been brittle (particularly with Claude)
- Decision: Maintain current auth approach until more stable solution available

### Private Repository Context
- This is a private repository with no external access
- Self-hosted runners are controlled and trusted
- No untrusted code execution from external PRs

### Output Buffer Limits
- MaxBuffer set to 10MB to handle large review outputs
- Could potentially cause memory issues with extremely large outputs
- Monitoring needed for very large PRs

### Timeout Settings
- Reduced default timeout from 1500s to 600s
- Per-provider overrides available for slower models
- Balance between allowing thorough reviews and preventing hung processes

## Future Hardening Opportunities

When authentication stabilizes, consider:
1. Implementing stricter process isolation
2. Adding resource limits (CPU, memory)
3. Implementing audit logging for all executions
4. Adding rate limiting for provider calls
5. Implementing stricter output validation

## Security Best Practices

1. **Never store secrets in code**: All sensitive values must come from GitHub secrets/variables
2. **Use structured commands**: Always use spawn() with argument arrays, never shell strings  
3. **Validate inputs**: Check all inputs from configuration files
4. **Defense in depth**: Multiple layers of environment sanitization
5. **Principle of least privilege**: Providers run without API key access

## Incident Response

If a security issue is discovered:
1. Immediately disable affected workflows
2. Review audit logs for any suspicious activity
3. Rotate all potentially affected credentials
4. Apply fixes and test thoroughly before re-enabling

## Review History

- 2025-08-30: Initial security review and fixes applied based on multi-model review feedback
- Fixed critical eval vulnerability, added env sanitization, clarified TEST_CMD security
- Removed deprecated shell command building in favor of structured execution
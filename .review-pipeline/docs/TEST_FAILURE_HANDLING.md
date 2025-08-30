# Test Failure Handling in Review Pipeline

## Design Decision

The review pipeline is designed to **continue running even when tests fail**. This is intentional behavior.

## Rationale

1. **Context for Reviewers**: When tests fail, AI reviewers can see the failures and provide insights about:
   - Whether the failures are related to the PR changes
   - Potential fixes for the issues
   - Whether the failures indicate broader problems

2. **Partial Functionality**: Even with some test failures, the review pipeline can still provide valuable feedback on:
   - Code quality
   - Security issues
   - Architecture concerns
   - Documentation needs

3. **Progressive Enhancement**: The pipeline should degrade gracefully, providing as much value as possible even when parts fail.

## Implementation

In `.github/workflows/pr-multimodel-review.yml`:

```yaml
- name: Run review pipeline tests
  run: |
    cd .review-pipeline
    # Continue on test failure - reviews should run to provide context
    npm test || echo "::warning::Review pipeline tests failed but continuing to run reviews"
```

Test failures are:
- Logged as GitHub Actions warnings (visible in the UI)
- Do not block the review process
- Can be addressed by reviewers in their feedback

## Future Considerations

If stricter test gating is needed:
1. Add a separate job that depends on test success
2. Use the test results as input to the final PR status check
3. Make the behavior configurable via workflow inputs

For now, the permissive approach maximizes the value of the review pipeline while clearly signaling any issues through warnings.
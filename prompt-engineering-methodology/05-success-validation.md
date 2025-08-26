# Phase 5: Success Validation

## Purpose
Define concrete, measurable criteria for success. Every requirement needs a specific test that proves it works.

## Validation Hierarchy

### 1. Functional Validation
**Does it do what it should?**

```markdown
## Functional Tests
| Requirement | Test Case | Expected Result | Pass Criteria |
|-------------|-----------|-----------------|---------------|
| Feature X works | Run operation Y | Output Z | Exact match |
| No regression | Run existing suite | All pass | 100% pass rate |
```

### 2. Performance Validation
**Does it meet performance requirements?**

```markdown
## Performance Metrics
| Operation | Baseline | Target | Acceptable |
|-----------|----------|--------|------------|
| Latency | 10ms | 10ms | <15ms |
| Memory | 100MB | 100MB | <120MB |
| CPU | 5% | 5% | <10% |
```

### 3. Stability Validation
**Does it remain stable under stress?**

```markdown
## Stability Tests
- Continuous operation: 1 hour minimum
- Concurrent requests: 100 parallel
- Resource limits: Memory constrained
- Error injection: Network failures
```

## Test Design Patterns

### The Proof Test
```python
# Proves the core functionality works
def test_core_feature():
    result = feature.execute()
    assert result == expected
    # If this passes, feature definitely works
```

### The Regression Guard
```python
# Ensures nothing broke
def test_no_regression():
    for test in all_existing_tests:
        assert test.passes()
    # If this passes, nothing regressed
```

### The Edge Explorer
```python
# Tests boundary conditions
def test_edges():
    test_empty_input()
    test_maximum_size()
    test_invalid_data()
    test_timeout_scenario()
```

### The Integration Validator
```python
# Verifies component interaction
def test_integration():
    component_a.start()
    component_b.connect()
    result = full_flow_test()
    assert result.success
```

## Validation Documentation Template

```markdown
## Success Criteria

### Must Pass (Blocking)
- [ ] Test: [Name] - [What it proves]
- [ ] Metric: [Name] < [Threshold]
- [ ] Validation: [Specific check]

### Should Pass (Important)
- [ ] Test: [Name] - [Nice to have]

### Bonus (Optional)
- [ ] Enhancement: [Name] - [If time permits]

## Test Implementation

### Critical Path Test
```python
# This test MUST pass
async def test_critical_feature():
    # Setup
    # Execute
    # Assert
```

### Performance Test
```python
# Measures key metrics
def test_performance():
    start = time.time()
    # Operation
    duration = time.time() - start
    assert duration < threshold
```
```

## Validation Strategies

### 1. Direct Validation
Test exactly what the requirement states:
- Requirement: "input() must work"
- Test: `result = input("test")` → No error

### 2. Indirect Validation
Test the implications:
- Requirement: "No deadlocks"
- Test: Operations after streaming succeed

### 3. Negative Validation
Test what shouldn't happen:
- Requirement: "Single-reader invariant"
- Test: Thread count doesn't increase

### 4. Comparative Validation
Test against baseline:
- Requirement: "No regression"
- Test: v0.2 results match v0.1 results

## Example Application

From v0.2 planning:

```markdown
## Success Criteria

### Must Pass
- [ ] input("prompt") returns user-provided value
- [ ] Multiple sequential inputs work
- [ ] All 29 v0.1 tests still pass
- [ ] Thread count remains at 2
- [ ] Checkpoint after streaming succeeds

### Should Pass  
- [ ] Input with timeout handling
- [ ] Input during exception handling
- [ ] Cancelled input operations

### Test Cases
```python
def test_basic_input():
    """Proves input() works"""
    result = exec("name = input('Name: ')")
    assert "EOFError" not in result
    
def test_no_deadlock():
    """Proves streaming didn't regress"""
    exec_stream("print('hi')")
    checkpoint()  # Must not timeout
```
```

## Validation Anti-Patterns

### 1. Vague Success
❌ "System should work better"
✅ "Response time < 100ms in 95% of requests"

### 2. Untestable Requirements
❌ "Code should be maintainable"
✅ "Cyclomatic complexity < 10"

### 3. Moving Targets
❌ "Performance should be acceptable"
✅ "Must match v0.1 baseline ±10%"

### 4. Hidden Dependencies
❌ "All tests pass" (which tests?)
✅ "Tests in /tests/v0_1/*.py pass"

## Validation Reporting

### Clear Results
```markdown
## Validation Results

✅ **Core Functionality**: 15/15 tests pass
✅ **Performance**: All metrics within bounds
✅ **Stability**: 1-hour stress test passed
❌ **Edge Case**: Unicode handling fails

## Verdict: READY with documented limitation
```

### Traceable Evidence
- Test output logs
- Performance graphs
- Coverage reports
- Error recordings

## Integration with Planning

Success validation provides:
1. **Definition of done**: Clear completion criteria
2. **Test requirements**: Specific validation needs
3. **Acceptance criteria**: What constitutes success
4. **Measurement framework**: How to prove it works

This ensures the planner knows exactly what success looks like and how to prove achievement.
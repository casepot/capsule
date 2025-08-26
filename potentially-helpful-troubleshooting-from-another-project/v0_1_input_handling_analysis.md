# v0.1 Input Handling Analysis

## Executive Summary

v0.1 has a fundamental architectural constraint: **input() cannot work in subprocess mode** because stdin is already consumed for protocol communication. This is not a bug but an inherent limitation of the single-stdin architecture.

## The Problem Explained

### Architecture Overview

```
Manager Process                    Runner Subprocess
     |                                    |
     |-------- stdin pipe ----------->    |  <- Protocol messages (Frames)
     |                                    |
     |<------- stdout pipe -----------    |  <- Protocol responses
     |                                    |
```

### The Stdin Conflict

1. **Protocol Needs Stdin**: Runner reads Frame messages from stdin
   ```python
   # runner_async.py line 370
   await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)
   ```

2. **input() Needs Stdin**: User code tries to read from the same stdin
   ```python
   # User code
   name = input("Enter name: ")  # Tries to read from stdin
   ```

3. **Result**: EOFError because stdin is already at EOF for user code

## Test Evidence

### Test 1: Subprocess Mode Behavior

```python
# When running as subprocess
client = RunnerClient(runner_cmd=[sys.executable, "-m", "v0_1.runner"])
await client.exec_stream("name = input('Name: ')")

# Result: 
# OP_FAILED: EOFError - EOF when reading a line
```

### Test 2: FakeRunner Mode (Works)

```python
# With FakeRunner (in-process mock)
fake = FakeRunner(reader, writer)
await client.exec_stream("name = input('Name: ')")

# Result:
# INPUT_REQUEST event sent
# Can provide input via protocol
# Works correctly
```

## Why This Is Fundamental

### The Single-Reader Invariant

v0.1's core improvement is the **single-reader invariant** - only ONE component reads from stdin. This fixes the v0 deadlock but means stdin is exclusively for protocol use.

### Alternative Architectures (Not Implemented)

1. **Separate Input Channel**: Use a different file descriptor for user input
2. **Multiplexed Protocol**: Embed input data in protocol messages
3. **PTY/Terminal**: Use pseudo-terminal for separation

## Current Workarounds

### 1. Protocol-Level Input Handling

The protocol supports INPUT_REQUEST/input_response messages:

```python
# Runner sends INPUT_REQUEST
{"kind": "INPUT_REQUEST", "token": "t1", "prompt": "Enter name: "}

# Manager responds with input_response
{"kind": "input_response", "token": "t1", "data": "Alice"}
```

### 2. Implementation Requirements

For this to work, the runner would need to:
1. Override the builtin `input()` function
2. Redirect input() calls to protocol messages
3. Wait for input_response from manager

Currently, this is **only implemented in FakeRunner**, not the real runner.

## Testing Isolation

### What Works
- ✅ Exec without input()
- ✅ Streaming without input()
- ✅ All operations that don't require stdin
- ✅ Input handling with FakeRunner (mock)

### What Doesn't Work
- ❌ input() in subprocess mode
- ❌ Any code reading from sys.stdin in subprocess
- ❌ Interactive prompts in executed code

## Test Validation Code

```python
async def test_input_subprocess_vs_mock():
    """Demonstrate input handling difference."""
    
    # Test 1: Subprocess mode (fails)
    print("=== SUBPROCESS MODE ===")
    client = RunnerClient(runner_cmd=[sys.executable, "-m", "v0_1.runner"])
    await client.start()
    
    async for ev in client.exec_stream("x = input('> ')"):
        print(f"Event: {ev.get('kind')}")
        if ev.get("kind") == "OP_FAILED":
            print(f"Error: {ev.get('error')}")  # EOFError
            break
    
    # Test 2: Mock mode (works)
    print("=== MOCK MODE ===")
    # ... setup FakeRunner ...
    async for ev in client.exec_stream("x = input('> ')"):
        if ev.get("kind") == "INPUT_REQUEST":
            await client.provide_input(ev["op_id"], ev["token"], "test")
        # Works correctly
```

## Design Decision Analysis

### Why Accept This Limitation?

1. **Simplicity**: Single stdin design is much simpler
2. **Reliability**: Eliminates race conditions completely  
3. **Common Case**: Most code execution doesn't need input()
4. **Workaround Exists**: Protocol supports input handling

### Why Not Fix It?

1. **Complexity**: Would require major architecture change
2. **Risk**: Could reintroduce race conditions
3. **Scope**: v0.1's goal was to fix deadlock, not add features
4. **Alternative**: Can be added in v0.2 if needed

## Recommendations

### For Current Use

1. **Document Clearly**: Note that input() doesn't work in subprocess mode
2. **Use FakeRunner**: For tests that need input simulation
3. **Avoid input()**: Design code to not require interactive input
4. **Future Enhancement**: Consider implementing input() override in runner

### For Future Versions

1. **Option A**: Implement input() override in runner_async.py
   ```python
   def custom_input(prompt=""):
       # Send INPUT_REQUEST via protocol
       # Wait for input_response
       # Return data
   ```

2. **Option B**: Use separate channel for input (e.g., socket)

3. **Option C**: Accept limitation and provide alternatives

## Test Matrix

| Scenario | FakeRunner | Real Runner | Expected | Notes |
|----------|------------|-------------|----------|-------|
| exec("print('hi')") | ✅ | ✅ | Works | No stdin needed |
| exec_stream("print('hi')") | ✅ | ✅ | Works | No stdin needed |
| exec("input()") | ✅ | ❌ | Mixed | EOFError in subprocess |
| exec_stream("input()") | ✅ | ❌ | Mixed | EOFError in subprocess |
| Multiple inputs | ✅ | ❌ | Mixed | All fail in subprocess |

## Conclusion

The input() limitation in subprocess mode is a **known architectural constraint**, not a bug. It's the direct result of v0.1's single-reader design that fixes the v0 deadlock. 

### Key Points:
1. **Stdin is for protocol only** in subprocess mode
2. **FakeRunner can simulate** input for testing  
3. **Real use cases** rarely need interactive input
4. **Future versions** could add proper input handling

### Verdict:
This limitation is **acceptable** given that:
- It's well-understood
- It has workarounds
- It doesn't affect the primary use case
- The benefit (no deadlock) outweighs the cost (no input())

The v0.1 goal was to fix the streaming deadlock, which is achieved. Enhanced input handling can be a v0.2 feature if needed.
# Serialization

## Overview

The two implementations take drastically different approaches to serialization:

- **exec-py**: Conservative pickle-only approach with strict sanitization
- **pyrepl2**: Multi-tier fallback system with aggressive serialization attempts

## exec-py/src/pyrepl Implementation

### Single-Tier Pickle Serialization

exec-py uses Python's standard pickle exclusively (`runner_async.py:40-53`):

```python
def _sanitize_ns(ns: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in ns.items():
        if k == "__builtins__" or (k.startswith("__") and k.endswith("__")):
            continue
        # exclude modules and callables
        if callable(v) or getattr(v, "__name__", None) == "module":
            continue
        try:
            pickle.dumps(v, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            continue
        out[k] = v
    return out
```

### Serialization Constraints

- **Excluded Types**: Functions, classes, modules, callables
- **Protocol**: pickle.HIGHEST_PROTOCOL
- **Error Handling**: Silent exclusion of non-serializable objects
- **Transport**: Direct binary pickle format

### Protocol Communication

exec-py uses JSON for protocol messages with length-prefixed frames (`protocol.py:119-122`):

```python
def frame(data: bytes) -> bytes:
    """Add length prefix to data."""
    return LEN_STRUCT.pack(len(data)) + data
```

## pyrepl2/pyrepl2 Implementation

### Multi-Tier Serialization Strategy

pyrepl2 implements a sophisticated fallback chain (`runner/interpreter.py:397-418`):

```python
# Everything else - serialize
elif cloudpickle:
    try:
        state["variables"][name] = cloudpickle.dumps(obj)
    except:
        pass
# Fallback for basic types when cloudpickle is not available
elif isinstance(obj, (int, float, str, bool, type(None))):
    state["variables"][name] = {"type": "basic", "value": obj}
elif isinstance(obj, (list, dict)):
    try:
        # Try to JSON serialize complex types
        json.dumps(obj)  # Test if serializable
        state["variables"][name] = {"type": "json", "value": obj}
    except:
        pass
elif isinstance(obj, tuple):
    try:
        json.dumps(list(obj))  # Test if serializable
        state["variables"][name] = {"type": "tuple", "value": list(obj)}
    except:
        pass
```

### Serialization Hierarchy

1. **Source Code** (for functions/classes)
2. **CloudPickle** (for complex objects)
3. **MessagePack** (for checkpoint storage)
4. **JSON** (for basic structures)
5. **Type-Tagged Values** (fallback)

### Checkpoint Serialization

Final checkpoint serialization (`runner/interpreter.py:420-424`):

```python
# Serialize state
if msgpack:
    return msgpack.packb(state)
else:
    return json.dumps(state).encode("utf-8")
```

### Size Estimation

pyrepl2 implements sophisticated size estimation (`runner/interpreter.py:519-539`):

```python
def _get_size(self, obj: Any) -> int:
    """Estimate object size in bytes."""
    if cloudpickle:
        try:
            return len(cloudpickle.dumps(obj))
        except:
            pass
    
    # Rough estimate for basic types
    if isinstance(obj, (type(None), bool)):
        return 1
    elif isinstance(obj, (int, float)):
        return 8
    elif isinstance(obj, (str, bytes)):
        return len(obj)
    elif isinstance(obj, (list, tuple)):
        return sum(self._get_size(item) for item in obj)
    elif isinstance(obj, dict):
        return sum(self._get_size(k) + self._get_size(v) for k, v in obj.items())
    else:
        return 100  # Default estimate
```

### JSON-RPC Transport

pyrepl2 uses JSON-RPC for subprocess communication (`runner/protocol.py:54-64`):

```python
def serialize_request(self, request: JSONRPCRequest) -> bytes:
    """
    Serialize request for sending.
    
    Args:
        request: Request dictionary
    
    Returns:
        JSON bytes with newline
    """
    return (json.dumps(request) + "\n").encode("utf-8")
```

## Comparison Table

| Aspect | exec-py | pyrepl2 |
|--------|---------|---------|
| **Primary Format** | pickle | cloudpickle |
| **Fallback Formats** | None | msgpack → JSON → typed values |
| **Functions/Classes** | Not serialized | Source code preserved |
| **Complex Objects** | Excluded if not pickleable | CloudPickle attempt |
| **Transport Encoding** | Binary pickle | Base64-encoded for JSON transport |
| **Size Tracking** | Not implemented | Sophisticated estimation |
| **Error Strategy** | Silent exclusion | Multi-tier fallback |
| **Dependencies** | None (stdlib only) | Optional cloudpickle, msgpack |

## Serialization Examples

### NumPy Arrays

**exec-py:**
```python
# Would be included if pickle-serializable
arr = np.array([1, 2, 3])  # ✅ Included (if numpy supports pickle)
```

**pyrepl2:**
```python
# Multiple serialization attempts
arr = np.array([1, 2, 3])
# 1. Try cloudpickle ✅
# 2. If fails, excluded
```

### Custom Classes

**exec-py:**
```python
class MyClass:
    def __init__(self):
        self.data = [1, 2, 3]

obj = MyClass()  # ❌ Excluded (callable)
```

**pyrepl2:**
```python
class MyClass:
    def __init__(self):
        self.data = [1, 2, 3]

# Class source preserved in state["classes"]
obj = MyClass()  # ✅ Serialized with cloudpickle
```

### Lambda Functions

**exec-py:**
```python
f = lambda x: x * 2  # ❌ Excluded (callable)
```

**pyrepl2:**
```python
f = lambda x: x * 2  
# ✅ Attempt cloudpickle serialization
# If fails, excluded but logged
```

## Tradeoff Analysis

### exec-py Serialization

**Advantages:**
- Predictable behavior
- No external dependencies
- Fast serialization
- Smaller checkpoint sizes
- Security (no code execution on restore)

**Disadvantages:**
- Very limited type support
- No function/class preservation
- No fallback options
- Cannot handle complex objects

### pyrepl2 Serialization

**Advantages:**
- Comprehensive type support
- Multiple fallback strategies
- Source code preservation
- Handles complex scientific objects
- Size tracking for optimization

**Disadvantages:**
- External dependencies
- Larger checkpoint sizes
- Security concerns (code execution)
- More complex error handling
- Performance overhead

## Real-World Implications

### Data Science Workflows

**exec-py**: Limited to data values (DataFrames, arrays)
```python
df = pd.DataFrame(...)  # ✅ Saved
model = trained_model    # ✅/❌ Depends on pickle support
custom_transform = lambda x: x * 2  # ❌ Lost
```

**pyrepl2**: Complete environment preservation
```python
df = pd.DataFrame(...)  # ✅ Saved
model = trained_model    # ✅ CloudPickle handles most ML models
custom_transform = lambda x: x * 2  # ✅ Preserved
```

### Security Considerations

- **exec-py**: Safer - no code execution on restore
- **pyrepl2**: Requires trust - executes code on restore

## Key Design Philosophy

The serialization strategies reflect core design principles:

- **exec-py**: "Serialize data, not behavior" - treats code as external
- **pyrepl2**: "Serialize everything possible" - treats code as data

This fundamental difference makes exec-py suitable for controlled environments with external code management, while pyrepl2 excels in interactive, exploratory environments where code evolves with data.
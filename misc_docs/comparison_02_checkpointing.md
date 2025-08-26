# Checkpointing/Snapshotting

## Overview

Both implementations provide state persistence mechanisms, but with different approaches:

- **exec-py**: Lightweight namespace snapshots with pickle-based serialization
- **pyrepl2**: Comprehensive checkpoint system with source code preservation and multi-tier serialization

## exec-py/src/pyrepl Implementation

### Checkpoint Mechanism

exec-py provides a simple checkpoint mechanism focused on namespace serialization:

```python
# exec-py/src/pyrepl/runner_async.py:377-395
async def _handle_checkpoint(self, id_: str, req: CheckpointRequest) -> None:
    # Serialize namespace snapshot, excluding unpickleable '__builtins__'
    try:
        snap = _sanitize_ns(self._global_ns)
        ns_bytes = pickle.dumps(snap, protocol=pickle.HIGHEST_PROTOCOL)
        state_id = str(abs(hash(ns_bytes)))
        await self._send_ok(
            id_, {"ok": True, "state_id": state_id, "bytes": len(ns_bytes), "label": req.get("label")}
        )
    except Exception as e:
        await self._send_error(
            id_,
            explain(
                ErrorCode.INTERNAL_ERROR,
                what="Failed to checkpoint namespace",
                why=str(e),
                how="Ensure objects in the namespace are pickleable or provide custom serialization.",
            ),
        )
```

### Namespace Sanitization

Before checkpointing, the namespace is sanitized (`runner_async.py:40-53`):

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

### Limitations

- Functions and classes are excluded from checkpoints
- Modules are not preserved
- Only pickle-serializable values are saved
- No source code preservation
- No incremental/differential checkpoints

## pyrepl2/pyrepl2 Implementation

### Comprehensive Checkpoint System

pyrepl2 implements a sophisticated checkpoint system with source preservation:

```python
# pyrepl2/pyrepl2/runner/interpreter.py:346-419
def create_checkpoint(self) -> bytes:
    """Create checkpoint of current state."""
    state = {
        "version": 1,
        "execution_count": self.execution_count,
        "total_execution_time_ms": self.total_execution_time_ms,
        "functions": {},
        "classes": {},
        "modules": [],
        "variables": {},
    }
```

### Source Code Preservation

pyrepl2 preserves function and class source code (`runner/interpreter.py:358-387`):

```python
# Functions - save source
if callable(obj) and not isinstance(obj, type):
    # First check if we have the source from exec
    if name in self._function_sources:
        state["functions"][name] = self._function_sources[name]
    else:
        try:
            state["functions"][name] = inspect.getsource(obj)
        except:
            # Try to serialize with cloudpickle
            if cloudpickle:
                try:
                    state["variables"][name] = cloudpickle.dumps(obj)
                except:
                    pass

# Classes - save source
elif isinstance(obj, type):
    # First check if we have the source from exec
    if name in self._class_sources:
        state["classes"][name] = self._class_sources[name]
    else:
        try:
            state["classes"][name] = inspect.getsource(obj)
        except:
            pass
```

### Source Extraction During Execution

pyrepl2 proactively extracts source during execution (`runner/interpreter.py:133-149`):

```python
def _extract_definitions(self, code: str) -> None:
    """Extract and store function/class definitions from code."""
    try:
        tree = ast.parse(code)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Store function source
                func_source = ast.unparse(node)
                self._function_sources[node.name] = func_source
            elif isinstance(node, ast.ClassDef):
                # Store class source
                class_source = ast.unparse(node)
                self._class_sources[node.name] = class_source
    except:
        # If parsing fails, we can't extract definitions
        pass
```

### Checkpoint Restoration

pyrepl2's restoration process (`runner/interpreter.py:426-488`):

```python
def restore_checkpoint(self, data: bytes) -> None:
    """Restore from checkpoint."""
    # Deserialize state
    if msgpack:
        state = msgpack.unpackb(data, raw=False)
    else:
        state = json.loads(data.decode("utf-8"))
    
    # Clear namespace (keep builtins)
    self.clear_namespace(keep_builtins=True)
    
    # Restore execution tracking
    self.execution_count = state.get("execution_count", 0)
    self.total_execution_time_ms = state.get("total_execution_time_ms", 0.0)
    
    # Restore imports
    for import_stmt in state.get("modules", []):
        try:
            exec(import_stmt, self.namespace)
        except:
            pass
    
    # Restore functions
    for name, source in state.get("functions", {}).items():
        try:
            exec(source, self.namespace)
            self._function_sources[name] = source
        except Exception as e:
            print(f"Failed to restore function {name}: {e}")
```

### Checkpoint Metadata

pyrepl2 tracks detailed checkpoint metadata (`types/execution.py:136-155`):

```python
@dataclass(slots=True, frozen=True)
class Checkpoint:
    checkpoint_id: CheckpointId
    session_id: SessionId
    created_at: datetime
    namespace_size_bytes: int
    compressed_size_bytes: int
    entry_count: int
    includes_source: bool
    parent_checkpoint: CheckpointId | None = None
    
    @property
    def compression_ratio(self) -> float:
        """Get compression ratio."""
        if self.namespace_size_bytes == 0:
            return 0.0
        return 1.0 - (self.compressed_size_bytes / self.namespace_size_bytes)
```

## Comparison Summary

| Feature | exec-py | pyrepl2 |
|---------|---------|---------|
| **Serialization** | Pickle only | Cloudpickle → msgpack → JSON fallback |
| **Function Preservation** | ❌ Excluded | ✅ Source code preserved |
| **Class Preservation** | ❌ Excluded | ✅ Source code preserved |
| **Module Handling** | ❌ Excluded | ✅ Import statements preserved |
| **Metadata** | Basic (size, ID) | Comprehensive (compression, timestamps, lineage) |
| **Restoration** | Not implemented | Full restoration with source replay |
| **Storage** | In-memory hash | Structured with IDs and tracking |
| **Incremental Support** | ❌ | Potential (parent_checkpoint field) |

## Tradeoffs Analysis

### exec-py Approach

**Advantages:**
- Lightweight and fast
- Simple implementation
- Minimal storage requirements
- No complex dependencies

**Disadvantages:**
- Limited to data values only
- No function/class preservation
- Cannot restore full working environment
- No module state preservation

### pyrepl2 Approach

**Advantages:**
- Complete environment preservation
- Source code retention
- Multi-tier serialization fallbacks
- Full restoration capability
- Checkpoint lineage tracking

**Disadvantages:**
- Higher storage requirements
- More complex implementation
- Dependency on cloudpickle/msgpack
- Slower checkpoint/restore operations

## Real-World Use Cases

### exec-py Checkpoints Best For:
- Data analysis workflows (preserving DataFrames, arrays)
- Simple state snapshots
- Rollback scenarios
- Memory-constrained environments

### pyrepl2 Checkpoints Best For:
- Complete notebook-like environments
- Educational platforms
- Development environments
- Long-running research computations
- Multi-stage pipelines with custom functions

## Key Architectural Insight

The checkpoint designs reflect fundamentally different philosophies:

- **exec-py**: Treats checkpoints as **data snapshots** - preserving values but not behavior
- **pyrepl2**: Treats checkpoints as **environment snapshots** - preserving the complete working context

This difference suggests exec-py targets scenarios where code is externally managed (e.g., version controlled), while pyrepl2 targets scenarios where the code itself is part of the persistent state (e.g., interactive notebooks).
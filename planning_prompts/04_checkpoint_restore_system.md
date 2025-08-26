# Checkpoint/Restore System Implementation Planning Prompt

## Your Mission

You are tasked with implementing a complete checkpoint and restore system that can save and reload the entire session state, including variables, functions, classes, and imports. This enables session persistence across restarts, sharing of computational states, and recovery from failures. The messages exist but handlers are empty stubs.

## Context Gathering Requirements

Before implementing, you MUST understand:

### 1. Problem History (Problem Archaeology)
- **Current State**: CheckpointMessage and RestoreMessage defined but handlers empty
- **pyrepl2 Success**: Preserves function/class source code during execution (interpreter.py:133-149)
- **exec-py Approach**: Simple pickle-based snapshots, excludes functions/modules
- **Lesson**: Source preservation is key to full environment restoration

### 2. Existing Infrastructure (Architecture Recognition)
- **Message Types**: CheckpointMessage, RestoreMessage already defined
- **Worker State**: `self._namespace`, `self._function_sources`, `self._class_sources`, `self._imports`
- **pyrepl2 Pattern**: Multi-tier serialization (cloudpickle → msgpack → JSON)
- **AST Available**: Can extract source from code before execution

### 3. Constraints That Cannot Be Violated (Risk Illumination)
- **Portability**: Checkpoints should work across Python versions when possible
- **Size Limits**: Large objects (GB-scale arrays) need special handling
- **Security**: Don't serialize sensitive data (passwords, tokens)
- **Compatibility**: Handle missing libraries gracefully on restore

## Planning Methodology

### Phase 1: Analysis (30% effort)
<context_gathering>
Goal: Understand what needs to be saved and how to extract it
Stop when: You know how to capture functions, classes, and module state
Depth: Study pyrepl2's interpreter.py checkpoint methods deeply
</context_gathering>

Investigate:
1. pyrepl2's source extraction during execution (interpreter.py:133-149)
2. pyrepl2's checkpoint creation (interpreter.py:346-419)
3. How to detect and save import statements
4. Serialization options and their tradeoffs

### Phase 2: Solution Design (50% effort)

Consider these approaches:

**Approach A: Source-Preserving Checkpoint (Recommended)**
- Extract and save function/class source code
- Track imports during execution
- Multi-tier serialization for compatibility
- Pros: Full restoration capability, readable format
- Cons: More complex, requires source tracking

**Approach B: Binary Serialization Only**
- Use cloudpickle for everything
- Simple but limited restoration
- Pros: Easy implementation
- Cons: Can't restore functions/classes properly, version-sensitive

**Approach C: Hybrid Approach**
- Source for functions/classes
- Binary for data values
- Import tracking for modules
- Pros: Best of both worlds
- Cons: Two serialization paths

### Phase 3: Risk Assessment (20% effort)
- **Risk**: Large objects cause OOM
  - Mitigation: Size limits, streaming serialization
- **Risk**: Platform-specific objects (file handles, threads)
  - Mitigation: Exclude non-serializable objects
- **Risk**: Version incompatibility
  - Mitigation: Fallback serialization tiers

## Output Requirements

Your plan must include:

### 1. Executive Summary (5 sentences max)
- What will be saved in checkpoints
- How source code will be preserved
- Serialization strategy (multi-tier)
- Storage mechanism (memory vs disk)

### 2. Technical Approach

**Part 1: Source Extraction During Execution**
```python
# In executor.py, during execute_code()
def _extract_definitions(self, code: str) -> None:
    """Extract function/class definitions from code."""
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
                
            elif isinstance(node, ast.Import):
                # Track imports
                for alias in node.names:
                    import_stmt = f"import {alias.name}"
                    if import_stmt not in self._imports:
                        self._imports.append(import_stmt)
    except:
        pass  # Best effort
```

**Part 2: Checkpoint Creation**
```python
async def handle_checkpoint(self, message: CheckpointMessage) -> None:
    """Create checkpoint with source preservation."""
    
    # Build checkpoint data
    checkpoint_data = {
        "version": 1,
        "created_at": time.time(),
        "namespace": self._serialize_namespace(),
        "function_sources": self._function_sources,
        "class_sources": self._class_sources,  
        "imports": self._imports,
        "metadata": {
            "python_version": sys.version,
            "execution_count": getattr(self, '_execution_count', 0)
        }
    }
    
    # Multi-tier serialization
    serialized = None
    method_used = None
    
    # Try cloudpickle first (best compatibility)
    try:
        import cloudpickle
        serialized = cloudpickle.dumps(checkpoint_data)
        method_used = "cloudpickle"
    except:
        # Fall back to msgpack
        try:
            import msgpack
            serialized = msgpack.packb(checkpoint_data, use_bin_type=True)
            method_used = "msgpack"
        except:
            # Final fallback to JSON
            import json
            serialized = json.dumps(checkpoint_data, default=str).encode('utf-8')
            method_used = "json"
    
    # Store checkpoint
    checkpoint_id = str(uuid.uuid4())
    
    # Save to disk or memory
    if message.save_to_disk:
        path = f"/tmp/pyrepl3_checkpoint_{checkpoint_id}.ckpt"
        with open(path, 'wb') as f:
            f.write(serialized)
    else:
        self._checkpoints[checkpoint_id] = serialized
    
    # Send response
    response = CheckpointCreatedMessage(
        checkpoint_id=checkpoint_id,
        size_bytes=len(serialized),
        serialization_method=method_used
    )
    await self._transport.send_message(response)
```

**Part 3: Restore Implementation**
```python
async def handle_restore(self, message: RestoreMessage) -> None:
    """Restore from checkpoint."""
    
    # Load checkpoint
    if message.checkpoint_id.startswith('/'):
        # Load from file path
        with open(message.checkpoint_id, 'rb') as f:
            checkpoint_data = f.read()
    else:
        # Load from memory
        checkpoint_data = self._checkpoints.get(message.checkpoint_id)
    
    # Deserialize (try methods in reverse order)
    data = None
    for method in ['cloudpickle', 'msgpack', 'json']:
        try:
            if method == 'cloudpickle':
                import cloudpickle
                data = cloudpickle.loads(checkpoint_data)
            elif method == 'msgpack':
                import msgpack
                data = msgpack.unpackb(checkpoint_data, raw=False)
            elif method == 'json':
                import json
                data = json.loads(checkpoint_data.decode('utf-8'))
            break
        except:
            continue
    
    # Clear current namespace
    self._namespace.clear()
    
    # Restore imports first
    for import_stmt in data.get('imports', []):
        try:
            exec(import_stmt, self._namespace)
        except:
            pass  # Missing library
    
    # Restore functions (re-execute source)
    for name, source in data.get('function_sources', {}).items():
        try:
            exec(source, self._namespace)
        except:
            pass
    
    # Restore classes
    for name, source in data.get('class_sources', {}).items():
        try:
            exec(source, self._namespace)
        except:
            pass
    
    # Restore variables
    self._namespace.update(data.get('namespace', {}))
    
    # Restore metadata
    self._function_sources = data.get('function_sources', {})
    self._class_sources = data.get('class_sources', {})
    self._imports = data.get('imports', [])
```

### 3. Storage Strategy
- In-memory for small checkpoints (<10MB)
- Filesystem for large checkpoints
- Configurable checkpoint directory
- Automatic cleanup of old checkpoints

### 4. Test Plan
```python
async def test_checkpoint_restore():
    """Test complete checkpoint/restore cycle."""
    session = Session()
    await session.start()
    
    # Create state
    await session.execute("""
import math

def calculate_area(r):
    return math.pi * r ** 2

class Circle:
    def __init__(self, radius):
        self.radius = radius
    
    def area(self):
        return calculate_area(self.radius)

my_circle = Circle(5)
result = my_circle.area()
""")
    
    # Create checkpoint
    checkpoint_id = await session.checkpoint()
    
    # Clear namespace (simulate restart)
    await session.execute("globals().clear()")
    
    # Restore
    await session.restore(checkpoint_id)
    
    # Verify everything restored
    result = await session.execute("""
[
    'math' in dir(),
    'calculate_area' in dir(),
    'Circle' in dir(),
    'my_circle' in dir(),
    my_circle.area() == result
]
""")
    assert all(result.value)  # All True
```

## Calibration

<context_gathering>
- Search depth: HIGH (complex feature)
- Maximum tool calls: 20-30
- Early stop: Never (need complete understanding)
</context_gathering>

## Non-Negotiables

1. **Source Preservation**: Functions and classes must be restorable
2. **Multi-tier Serialization**: Must have fallback options
3. **Best Effort**: Missing libraries shouldn't fail restore
4. **Size Safety**: Handle large objects gracefully

## Success Criteria

Before finalizing your plan, verify:
- [ ] Source extraction during execution is implemented
- [ ] Multi-tier serialization is specified
- [ ] Functions and classes can be restored
- [ ] Import tracking is included
- [ ] Test proves full restoration works

## Additional Guidance

- Study pyrepl2's implementation carefully (interpreter.py:346-488)
- Start with in-memory storage, add disk later
- Use ast.unparse() for source extraction
- Consider compression for large checkpoints (zlib)
- Handle __main__ namespace specially
- Document what cannot be checkpointed (threads, files, sockets)
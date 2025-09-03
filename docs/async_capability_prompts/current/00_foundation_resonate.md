# Resonate Foundation - Durability and Orchestration Layer

## Your Mission

You are tasked with integrating Resonate SDK as the foundational durability and orchestration layer for PyREPL3. Resonate will provide automatic recovery, distributed execution, and promise-based communication while maintaining our zero-dependency philosophy for local development.

## Why Resonate?

### Problems It Solves
1. **Durability**: Executions can recover from crashes without custom checkpointing
2. **Promise Management**: Replace our Protocol Bridge futures with durable promises
3. **Dependency Injection**: Clean capability management without global state
4. **HITL Workflows**: Native support for human-in-the-loop via promise resolution
5. **Distribution**: Scale from single-worker to multi-worker without code changes

### Architectural Fit
```
┌─────────────────────────────────────────┐
│            PyREPL3 Worker               │
├─────────────────────────────────────────┤
│         Resonate (Durability Layer)     │
│  ┌─────────────┬──────────┬──────────┐ │
│  │AsyncExecutor│ Protocol  │Capability│ │
│  │  (Durable)  │  Bridge   │  System  │ │
│  │             │(Promises) │  (Deps)  │ │
│  └─────────────┴──────────┴──────────┘ │
├─────────────────────────────────────────┤
│          Transport Layer                │
└─────────────────────────────────────────┘
```

## Integration Strategy

### Phase 1: Local Mode (Development)
```python
from resonate import Resonate

# Zero external dependencies - uses in-memory storage
resonate = Resonate.local()

# Everything works except crash recovery
@resonate.register
def execute_code(ctx, args):
    # Full functionality, no server required
    pass
```

### Phase 2: Remote Mode (Production)
```python
# Same code, just different initialization
resonate = Resonate.remote(host="resonate-server")

# Now supports:
# - Crash recovery
# - Multi-worker execution
# - Distributed promises
# - Cross-process coordination
```

## Core Components Integration

### 1. AsyncExecutor with Resonate

**Current Challenge**: Need durability for long-running executions with top-level await

**Resonate Solution**:
```python
@resonate.register
def durable_execute(ctx, args):
    """Execute code with automatic recovery."""
    code = args['code']
    execution_id = args['execution_id']
    namespace = args.get('namespace', {})
    
    # Analyze code to determine execution mode
    analysis = analyze_code(code)
    
    if analysis.has_top_level_await:
        # Resonate handles async context
        result = yield ctx.lfc(execute_async_with_await, {
            'code': code,
            'namespace': namespace,
            'flags': PyCF_ALLOW_TOP_LEVEL_AWAIT
        })
    elif analysis.needs_blocking_io:
        # Resonate automatically uses thread pool
        result = yield ctx.lfc(execute_in_thread, {
            'code': code,
            'namespace': namespace
        })
    else:
        # Simple sync execution
        result = execute_sync(code, namespace)
    
    return result

# Usage with automatic recovery
result = durable_execute.run(execution_id, {
    'code': code,
    'namespace': current_namespace
})
```

### 2. Protocol Bridge with Resonate Promises

**Current Challenge**: Managing request/response correlation with futures

**Resonate Solution**:
```python
class ResonateProtocolBridge:
    """Protocol Bridge using Resonate's durable promises."""
    
    def __init__(self, resonate: Resonate, transport: MessageTransport):
        self._resonate = resonate
        self._transport = transport
        
    async def send_request(
        self,
        capability_id: str,
        execution_id: str,
        message: Message,
        timeout: Optional[float] = None
    ) -> Promise:
        """Send request and return durable promise."""
        
        # Create durable promise that survives crashes
        promise_id = f"{execution_id}:{capability_id}:{message.id}"
        
        promise = self._resonate.promises.create(
            id=promise_id,
            timeout=int((time.time() + timeout) * 1000) if timeout else None,
            data=json.dumps({
                'capability_id': capability_id,
                'execution_id': execution_id,
                'message_type': message.type
            })
        )
        
        # Send the protocol message
        await self._transport.send_message(message)
        
        # Return promise that can be awaited
        return promise
    
    async def route_response(self, message: Message) -> bool:
        """Route response by resolving promise."""
        
        correlation_id = self._extract_correlation_id(message)
        if not correlation_id:
            return False
        
        try:
            # Resolve the durable promise
            self._resonate.promises.resolve(
                id=correlation_id,
                data=json.dumps(message.to_dict())
            )
            return True
        except PromiseNotFoundError:
            # No waiting promise
            return False
```

### 3. Capability System with Dependencies

**Current Challenge**: Managing capability lifecycle and injection

**Resonate Solution**:
```python
# Register capabilities as Resonate dependencies
def initialize_capabilities(resonate: Resonate, transport: MessageTransport):
    """Register all capabilities as dependencies."""
    
    # Core I/O capabilities
    resonate.set_dependency("input", InputCapability(transport))
    resonate.set_dependency("print", PrintCapability(transport))
    resonate.set_dependency("display", DisplayCapability(transport))
    
    # File capabilities
    resonate.set_dependency("read_file", FileReadCapability(transport))
    resonate.set_dependency("write_file", FileWriteCapability(transport))
    
    # Network capabilities (if allowed by security policy)
    if security_policy.allows("network"):
        resonate.set_dependency("fetch", FetchCapability(transport))
        resonate.set_dependency("websocket", WebSocketCapability(transport))

# Access in durable functions
@resonate.register
def execute_with_input(ctx, args):
    """Execute code that needs user input."""
    
    # Get capability from dependency injection
    input_cap = ctx.get_dependency("input")
    
    # Create HITL promise for user input
    promise = yield ctx.promise(
        id=f"input:{args['execution_id']}:{uuid.uuid4()}",
        data={"prompt": args['prompt'], "type": "user_input"}
    )
    
    # Wait for human to resolve the promise
    user_input = yield promise
    
    return user_input['data']
```

### 4. HITL (Human-In-The-Loop) Workflows

**Current Challenge**: Blocking for user input without freezing execution

**Resonate Solution**:
```python
class InputCapability:
    """Input capability using Resonate promises for HITL."""
    
    def __init__(self, resonate: Resonate, transport: MessageTransport):
        self._resonate = resonate
        self._transport = transport
    
    async def request_input(self, prompt: str, execution_id: str) -> str:
        """Request input from user via HITL promise."""
        
        # Create promise for this input request
        promise_id = f"input:{execution_id}:{uuid.uuid4()}"
        
        # Create promise that will be resolved by UI
        promise = self._resonate.promises.create(
            id=promise_id,
            timeout=int(time.time() * 1000) + 300000,  # 5 min timeout
            data=json.dumps({
                'prompt': prompt,
                'waiting_for': 'user_input',
                'execution_id': execution_id
            })
        )
        
        # Send prompt to UI
        await self._transport.send_message(InputMessage(
            id=promise_id,
            prompt=prompt,
            execution_id=execution_id
        ))
        
        # UI will call: resonate.promises.resolve(id=promise_id, data=user_input)
        # This can happen in a different process/machine
        
        # Wait for resolution
        result = await promise.result()
        return json.loads(result)['input']
```

## Configuration and Initialization

### Development Setup (Local)
```python
# src/subprocess/resonate_init.py

def initialize_resonate_local() -> Resonate:
    """Initialize Resonate in local mode for development."""
    
    resonate = Resonate.local()
    
    # Register all durable functions
    register_executor_functions(resonate)
    register_capability_functions(resonate)
    
    # Set up dependencies
    initialize_capabilities(resonate, transport)
    
    return resonate
```

### Production Setup (Remote)
```python
def initialize_resonate_remote(
    host: str = "http://localhost:8001",
    worker_group: str = "pyrepl3-workers"
) -> Resonate:
    """Initialize Resonate in remote mode for production."""
    
    resonate = Resonate.remote(
        host=host,
        group=worker_group,
        # Use poller for receiving tasks
        transport="poll"  
    )
    
    # Same registration as local
    register_executor_functions(resonate)
    register_capability_functions(resonate)
    initialize_capabilities(resonate, transport)
    
    return resonate
```

## Migration Path

### Step 1: Wrap Existing Code
```python
# Start by wrapping existing executor
@resonate.register
def wrapped_executor(ctx, args):
    # Call existing ThreadedExecutor or AsyncExecutor
    executor = AsyncExecutor(namespace, transport, args['execution_id'])
    result = asyncio.run(executor.execute(args['code']))
    return result
```

### Step 2: Gradually Adopt Features
```python
# Add durability to specific operations
@resonate.register  
def durable_file_operation(ctx, args):
    file_cap = ctx.get_dependency("file")
    
    # This operation can now recover from crashes
    content = yield ctx.lfc(file_cap.read, {'path': args['path']})
    processed = yield ctx.lfc(process_content, {'content': content})
    yield ctx.lfc(file_cap.write, {'path': args['output'], 'data': processed})
    
    return "Processing complete"
```

### Step 3: Full Integration
- Replace Protocol Bridge futures with Resonate promises
- Use Resonate dependencies for all capabilities
- Leverage HITL for all user interactions
- Enable distributed execution across workers

## Benefits Summary

1. **Incremental Adoption**: Start with `Resonate.local()`, no server required
2. **Durability**: Automatic recovery from crashes
3. **Simplified Code**: Remove custom promise tracking and correlation
4. **HITL Native**: Built-in support for human-in-the-loop workflows
5. **Distribution Ready**: Scale to multiple workers when needed
6. **Observability**: Built-in metrics and tracing

## Testing Strategy

### Local Mode Tests
```python
def test_local_execution():
    """Test that local mode works without server."""
    resonate = Resonate.local()
    
    @resonate.register
    def test_func(ctx, args):
        return args['value'] * 2
    
    result = test_func.run("test-1", {'value': 21})
    assert result == 42
```

### Recovery Tests
```python
def test_crash_recovery():
    """Test that execution recovers from crash."""
    resonate = Resonate.remote()
    
    @resonate.register
    def crashable_func(ctx, args):
        if args.get('crash'):
            raise Exception("Simulated crash")
        return "Success"
    
    # Start execution that will crash
    promise = crashable_func.rpc("test-2", {'crash': True})
    
    # Simulate recovery by retrying without crash flag
    # Resonate will resume from last checkpoint
    result = crashable_func.run("test-2", {'crash': False})
    assert result == "Success"
```

## Non-Negotiables

1. **Local Mode First**: Must work without any server for development
2. **Zero Breaking Changes**: Existing code continues to work
3. **Gradual Migration**: Can adopt Resonate incrementally
4. **Performance**: No significant overhead in local mode
5. **Simplicity**: Abstractions should reduce complexity, not add it

## Success Criteria

- [ ] AsyncExecutor wrapped in durable function
- [ ] Protocol Bridge uses Resonate promises
- [ ] Capabilities registered as dependencies
- [ ] HITL workflows use promise resolution
- [ ] Local mode works without server
- [ ] Remote mode enables crash recovery
- [ ] Tests pass in both local and remote modes
- [ ] Performance overhead < 5% in local mode
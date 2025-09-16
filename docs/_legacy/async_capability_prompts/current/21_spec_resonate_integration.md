# Resonate SDK Integration Specification

## Document Information
- **Version**: 1.0.0
- **Status**: Draft
- **Last Updated**: 2025-01-03
- **Classification**: Technical Specification

## Executive Summary

This specification defines the integration patterns, configurations, and implementation details for incorporating Resonate SDK as the foundational durability and orchestration layer in PyREPL3. Resonate provides automatic recovery, distributed execution, promise-based communication, and dependency injection while maintaining zero-dependency operation for local development.

> NOTE (Phase 1 action): The current dependency access example uses a “get + initialize()” pattern for `AsyncExecutor`. We will replace this with a factory pattern that returns fully initialized instances per execution to avoid temporal coupling and runtime errors. See FOUNDATION_FIX_PLAN.md “PR #11 Triage” for details.

## Integration Architecture

### Core Integration Points

```
┌────────────────────────────────────────────────────────────┐
│                    PyREPL3 Components                      │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  AsyncExecutor ──register──→ Resonate.functions           │
│                                    ↓                       │
│  Capabilities ──register───→ Resonate.dependencies        │
│                                    ↓                       │
│  Namespace ─────persist────→ Resonate.promises           │
│                                    ↓                       │
│  HITL ──────────resolve────→ Resonate.promises           │
│                                                            │
└────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────┐
│                     Resonate SDK                           │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   Local      │  │   Remote     │  │   Storage    │   │
│  │   Engine     │  │   Client     │  │   Backend    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   Promise    │  │  Dependency  │  │   Function   │   │
│  │   Manager    │  │   Injector   │  │   Registry   │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

## Initialization Patterns

### Local Mode Initialization (Current Code Wiring)

```python
from src.session.manager import Session
from src.integration.resonate_init import initialize_resonate_local

session = Session()
await session.start()
resonate = initialize_resonate_local(session)

# Session is the sole transport reader; the bridge is wired via a message
# interceptor so durable promises are resolved when Result/Error/InputResponse
# messages arrive.
```

Quickstart: Local‑mode durable execute

```python
from types import SimpleNamespace
from src.session.manager import Session
from src.integration.resonate_init import initialize_resonate_local
from src.integration.resonate_bridge import ResonateProtocolBridge
from src.protocol.messages import ExecuteMessage
import time

session = Session()
await session.start()
resonate = initialize_resonate_local(session)
bridge: ResonateProtocolBridge = resonate.dependencies["protocol_bridge"]

execution_id = "exec-123"
promise_id = f"exec:{execution_id}"
prom = resonate.promises.create(id=promise_id, timeout=30000, data="{}")
msg = ExecuteMessage(id=execution_id, timestamp=time.time(), code="2+2")
await bridge.send_request("execute", execution_id, msg, timeout=30.0, promise_id=promise_id)
payload = await prom.await_result()  # JSON payload for ResultMessage/ErrorMessage
```

### Remote Mode Initialization (Planned)

```python
def initialize_resonate_remote(
    host: str = "http://localhost:8001",
    api_key: Optional[str] = None,
    worker_group: str = "pyrepl3-workers",
    worker_id: Optional[str] = None
) -> Resonate:
    """
    Initialize Resonate in remote mode for production.
    Enables crash recovery and distributed execution.
    """
    # Create remote instance
    resonate = Resonate.remote(
        host=host,
        auth={"api_key": api_key} if api_key else None,
        config={
            "worker_group": worker_group,
            "worker_id": worker_id or _generate_worker_id(),
            "transport": "poll",  # Use polling for task reception
            "poll_interval": 1000,  # 1 second
            "promise_timeout_default": 300000,  # 5 minutes
            "max_retries": 5,
            "retry_backoff": "exponential",
            "checkpoint_interval": 10000,  # 10 seconds
            "heartbeat_interval": 5000,  # 5 seconds
        }
    )
    
    # Register functions and dependencies (same as local)
    _register_durable_functions(resonate)
    _initialize_dependencies(resonate)
    _configure_promise_handlers(resonate)
    
    # Additional remote configurations
    _setup_distributed_coordination(resonate)
    
    return resonate
```

## Durable Function Registration

### Function Registration Pattern

```python
def _register_durable_functions(resonate: Resonate):
    """Register all durable functions with Resonate."""
    
    @resonate.register(
        name="execute_code",
        version="1.0.0",
        timeout=300000,  # 5 minutes
        retries=3,
        tags=["execution", "core"]
    )
    def durable_execute(ctx, args):
        """
        Durable code execution with automatic recovery.
        
        Context provides:
        - ctx.resonate: Resonate instance
        - ctx.get_dependency(): Access registered dependencies
        - ctx.promise(): Create/wait for promises (preferred for async)
        - ctx.lfc(): Call other durable functions (sync callables only)
        """
        code = args['code']
        execution_id = args['execution_id']
        namespace = args.get('namespace', {})
        
        # Access dependencies
        executor = ctx.get_dependency("async_executor")
        namespace_manager = ctx.get_dependency("namespace_manager")
        
        # Promise-first execution (avoids loop-spinning in durable layer)
        bridge = ctx.get_dependency("protocol_bridge")
        # Phase 2: Promise‑first with deterministic id
        promise_id = f"exec:{execution_id}"
        promise = yield ctx.promise(id=promise_id)
        
        # Send execute request via protocol bridge
        yield bridge.send_request(
            capability_id="execute",
            execution_id=execution_id,
            message=ExecuteMessage(...),  # include code, ids per protocol
            timeout=ctx.config.get("tla_timeout", 30.0) if hasattr(ctx, "config") else 30.0,
            promise_id=promise_id,
        )
        
        # Wait for durable result
        result = yield promise
        return result

    @resonate.register(
        name="execute_with_capabilities",
        version="1.0.0"
    )
    def durable_execute_with_capabilities(ctx, args):
        """Execute code with capability access."""
        # Implementation details...
        pass
```

### Function Lifecycle Management

```python
class DurableFunctionLifecycle:
    """Manages durable function lifecycle."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        self.active_functions = {}
        
    def start_function(
        self,
        function_name: str,
        execution_id: str,
        args: dict,
        mode: str = "run"
    ):
        """
        Start a durable function execution.
        
        Modes:
        - "run": Execute and wait for result
        - "rpc": Start and return promise
        - "schedule": Schedule for later execution
        """
        function = self.resonate.functions.get(function_name)
        
        if mode == "run":
            # Synchronous execution (blocks until complete)
            return function.run(execution_id, args)
            
        elif mode == "rpc":
            # Asynchronous execution (returns promise)
            promise = function.rpc(execution_id, args)
            self.active_functions[execution_id] = promise
            return promise
            
        elif mode == "schedule":
            # Scheduled execution
            return function.schedule(
                execution_id,
                args,
                delay=args.get("delay", 0)
            )
```

## Dependency Injection System

### Dependency Registration

```python
from src.integration.resonate_wrapper import async_executor_factory

def _initialize_dependencies(resonate: Resonate):
    """Register all system dependencies with Resonate."""
    
    # Core execution dependencies (factory-based to avoid temporal coupling)
    resonate.set_dependency(
        "async_executor",
        lambda ctx: async_executor_factory(
            ctx=ctx,
            namespace_manager=ctx.get_dependency("namespace_manager"),
            transport=ctx.get_dependency("transport"),
            # Optional: override default TLA timeout (seconds)
            # tla_timeout=15.0,
        ),
        singleton=False  # New instance per execution
    )
    
    resonate.set_dependency(
        "namespace_manager",
        lambda: NamespaceManager(resonate),
        singleton=True
    )

## Correlation & Rejection Semantics (Phase 2)

- Single‑loop invariant: `Session` is the sole transport reader. The Resonate protocol bridge is wired via `Session` message interceptors and never reads the transport directly.
- Deterministic promise IDs:
  - Execute: `exec:{execution_id}` (created by `durable_execute` via `ctx.promise`).
  - Input: `{execution_id}:input:{message.id}` (created by the bridge).
- Correlation mapping:
  - Execute → Result/Error: request key is `ExecuteMessage.id`; response correlates on `ResultMessage.execution_id` or `ErrorMessage.execution_id` and resolves/rejects the durable promise `exec:{execution_id}`.
  - Input → InputResponse: request key is `InputMessage.id`; response correlates on `InputResponseMessage.input_id` and resolves the durable promise `{execution_id}:input:{message.id}`.
- Rejection policy:
  - On `ErrorMessage`, the bridge rejects (does not resolve) the durable promise with a structured JSON payload.
  - `durable_execute` expects rejection and raises a structured exception with `add_note` context (execution id, traceback excerpt if present).
- Timeout enrichment:
  - If `send_request(..., timeout=...)` expires before a response, the bridge rejects with a structured payload including `capability`, `execution_id`, `request_id`, and `timeout` seconds.
- Memory semantics:
  - Msgpack serialization uses Pydantic `model_dump(mode="python")` to preserve raw bytes for checkpoint payloads; JSON uses `mode="json"`.

    
    # Capability dependencies
    resonate.set_dependency(
        "input_capability",
        lambda: InputCapability(resonate),
        singleton=False  # New instance per execution
    )
    
    resonate.set_dependency(
        "file_capability",
        lambda: FileCapability(resonate),
        singleton=True,
        lazy=True
    )
    
    # Security dependencies
    resonate.set_dependency(
        "security_policy",
        SecurityPolicy,
        singleton=True,
        config={"level": "STANDARD"}
    )
```

### Dependency Access Pattern

```python
class DependencyAccessor:
    """Provides access to Resonate dependencies."""
    
    def __init__(self, context):
        self.context = context
        
    def get_executor(self) -> AsyncExecutor:
        """Get async executor instance."""
        # Factory returns fully initialized instance
        return self.context.get_dependency("async_executor")(self.context)
        
    def get_capability(self, name: str) -> Optional[Capability]:
        """Get capability if allowed by security policy."""
        policy = self.context.get_dependency("security_policy")
        
        if not policy.is_allowed(name):
            return None
            
        cap_name = f"{name}_capability"
        if self.context.has_dependency(cap_name):
            return self.context.get_dependency(cap_name)
            
        return None
```

## Promise Management

### Promise Creation and Resolution

```python
class PromiseManager:
    """Manages Resonate promises for async operations."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        self.active_promises = {}
        
    def create_promise(
        self,
        promise_id: str,
        promise_type: str,
        data: dict,
        timeout: Optional[int] = None
    ) -> Promise:
        """
        Create a durable promise.
        
        Args:
            promise_id: Unique identifier
            promise_type: Type for routing (input, file, network)
            data: Associated data
            timeout: Timeout in milliseconds
        """
        promise = self.resonate.promises.create(
            id=promise_id,
            timeout=timeout or self._default_timeout(promise_type),
            data=json.dumps({
                "type": promise_type,
                "created_at": time.time(),
                "data": data
            }),
            tags=[promise_type, "pyrepl3"]
        )
        
        self.active_promises[promise_id] = promise
        return promise
        
    def resolve_promise(
        self,
        promise_id: str,
        result: Any,
        error: Optional[Exception] = None
    ):
        """Resolve a promise with result or error."""
        if error:
            self.resonate.promises.reject(
                id=promise_id,
                error=str(error)
            )
        else:
            self.resonate.promises.resolve(
                id=promise_id,
                data=json.dumps(result) if not isinstance(result, str) else result
            )
            
        self.active_promises.pop(promise_id, None)
```

### Promise-Based Communication Pattern

```python
class PromiseBasedProtocol:
    """Implements promise-based request/response protocol."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        self.promise_manager = PromiseManager(resonate)
        
    async def send_request(
        self,
        request_type: str,
        payload: dict,
        timeout: float = 30.0
    ) -> Any:
        """Send request and await response via promise.
        
        Uses Python 3.11+ asyncio.timeout() for safer timeout handling.
        """
        # Create unique request ID
        request_id = f"{request_type}:{uuid.uuid4()}"
        
        # Create promise for response
        promise = self.promise_manager.create_promise(
            promise_id=request_id,
            promise_type=request_type,
            data=payload,
            timeout=int(timeout * 1000)
        )
        
        # Send request (external system will resolve promise)
        await self._dispatch_request(request_id, request_type, payload)
        
        # Wait for promise resolution with asyncio.timeout (Python 3.11+)
        try:
            async with asyncio.timeout(timeout):
                result = await promise.result()
                return json.loads(result) if isinstance(result, str) else result
        except asyncio.TimeoutError as e:
            # Add execution context using Python 3.11+ exception notes
            e.add_note(f"Request ID: {request_id}")
            e.add_note(f"Request type: {request_type}")
            e.add_note(f"Timeout: {timeout} seconds")
            raise TimeoutError(f"Request {request_id} timed out") from e
        except PromiseRejected as e:
            # Enrich error with context
            if hasattr(e, 'add_note'):
                e.add_note(f"Request ID: {request_id}")
                e.add_note(f"Request type: {request_type}")
            raise RuntimeError(f"Request {request_id} failed: {e}") from e
```

## HITL (Human-In-The-Loop) Integration

### HITL Workflow Implementation

```python
class HITLWorkflow:
    """Manages human-in-the-loop workflows via promises."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        
    def create_approval_request(
        self,
        execution_id: str,
        action: str,
        details: dict,
        approvers: List[str],
        timeout: int = 3600000  # 1 hour
    ) -> str:
        """Create approval request that waits for human response."""
        request_id = f"approval:{execution_id}:{uuid.uuid4()}"
        
        # Create promise for approval
        self.resonate.promises.create(
            id=request_id,
            timeout=timeout,
            data=json.dumps({
                "type": "approval",
                "execution_id": execution_id,
                "action": action,
                "details": details,
                "approvers": approvers,
                "status": "pending"
            })
        )
        
        # Notify approvers (external system)
        self._notify_approvers(request_id, approvers, action, details)
        
        return request_id
        
    def wait_for_approval(self, request_id: str) -> dict:
        """Wait for approval promise to be resolved."""
        promise = self.resonate.promises.get(request_id)
        result = promise.result()  # Blocks until resolved
        
        approval_data = json.loads(result)
        if approval_data.get("approved"):
            return approval_data
        else:
            raise RuntimeError(f"Approval denied: {approval_data.get('reason')}")
```

### Input Capability with HITL

```python
@resonate.register
def execute_with_user_input(ctx, args):
    """
    Durable function that requests user input.
    
    Demonstrates HITL pattern with promise resolution.
    """
    code = args['code']
    execution_id = args['execution_id']
    
    # Parse code to find input() calls
    input_points = _find_input_calls(code)
    
    for point in input_points:
        # Create HITL promise for each input
        promise_id = f"input:{execution_id}:{point['line']}"
        
        # Create promise that will be resolved by UI
        promise = yield ctx.promise(
            id=promise_id,
            timeout=300000,  # 5 minutes
            data={
                "prompt": point['prompt'],
                "type": "user_input",
                "execution_id": execution_id
            }
        )
        
        # Wait for user to provide input
        user_input = yield promise
        
        # Continue execution with input
        point['result'] = user_input
        
    # Execute code with collected inputs
    return _execute_with_inputs(code, input_points)
```

## State Persistence Patterns

### Namespace Persistence

```python
class DurableNamespacePersistence:
    """Persists namespace state using Resonate promises."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        
    def persist_namespace(
        self,
        execution_id: str,
        namespace: dict
    ) -> str:
        """Persist namespace as durable state."""
        namespace_id = f"namespace:{execution_id}"
        
        # Serialize only JSON-compatible values
        serializable = self._extract_serializable(namespace)
        
        # Store as resolved promise for durability
        self.resonate.promises.create(
            id=namespace_id,
            data=json.dumps(serializable),
            tags=["namespace", execution_id]
        )
        
        # Immediately resolve for storage
        self.resonate.promises.resolve(
            id=namespace_id,
            data=json.dumps(serializable)
        )
        
        return namespace_id
        
    def recover_namespace(self, execution_id: str) -> Optional[dict]:
        """Recover namespace from durable storage."""
        namespace_id = f"namespace:{execution_id}"
        
        try:
            promise = self.resonate.promises.get(namespace_id)
            if promise and promise.state == "resolved":
                data = promise.result()
                return json.loads(data)
        except PromiseNotFound:
            pass
            
        return None
```

### Checkpoint Management

```python
class CheckpointManager:
    """Manages execution checkpoints for recovery."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        
    def create_checkpoint(
        self,
        execution_id: str,
        checkpoint_name: str,
        state: dict
    ):
        """Create execution checkpoint."""
        checkpoint_id = f"checkpoint:{execution_id}:{checkpoint_name}"
        
        self.resonate.checkpoints.create(
            id=checkpoint_id,
            data={
                "execution_id": execution_id,
                "name": checkpoint_name,
                "state": state,
                "timestamp": time.time()
            }
        )
        
    def restore_from_checkpoint(
        self,
        execution_id: str,
        checkpoint_name: Optional[str] = None
    ) -> Optional[dict]:
        """Restore from checkpoint."""
        if checkpoint_name:
            checkpoint_id = f"checkpoint:{execution_id}:{checkpoint_name}"
            checkpoint = self.resonate.checkpoints.get(checkpoint_id)
        else:
            # Get latest checkpoint
            checkpoints = self.resonate.checkpoints.list(
                filter={"execution_id": execution_id}
            )
            checkpoint = max(checkpoints, key=lambda c: c.timestamp) if checkpoints else None
            
        return checkpoint.data if checkpoint else None
```

## Distributed Coordination

### Multi-Worker Configuration

```python
def _setup_distributed_coordination(resonate: Resonate):
    """Configure distributed execution coordination."""
    
    # Register worker with coordinator
    resonate.workers.register({
        "id": resonate.config["worker_id"],
        "group": resonate.config["worker_group"],
        "capabilities": [
            "python_execution",
            "async_support",
            "file_operations",
            "network_operations"
        ],
        "resources": {
            "cpu": os.cpu_count(),
            "memory": _get_available_memory(),
            "max_executions": 100
        }
    })
    
    # Set up task routing rules
    resonate.routing.add_rule(
        name="cpu_intensive",
        condition=lambda task: task.get("cpu_intensive", False),
        target_group="high_cpu_workers"
    )
    
    resonate.routing.add_rule(
        name="io_bound",
        condition=lambda task: task.get("io_bound", False),
        target_group="io_workers"
    )
    
    # Configure load balancing
    resonate.load_balancer.configure({
        "strategy": "least_loaded",
        "health_check_interval": 5000,
        "rebalance_interval": 30000
    })
```

### Cross-Worker Communication

```python
class CrossWorkerMessaging:
    """Enables communication between distributed workers."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        self.worker_id = resonate.config["worker_id"]
        
    def send_to_worker(
        self,
        target_worker: str,
        message_type: str,
        payload: dict
    ) -> str:
        """Send message to specific worker."""
        message_id = f"worker_msg:{uuid.uuid4()}"
        
        self.resonate.messages.send(
            id=message_id,
            target=target_worker,
            source=self.worker_id,
            type=message_type,
            payload=payload
        )
        
        return message_id
        
    def broadcast_to_group(
        self,
        group: str,
        message_type: str,
        payload: dict
    ):
        """Broadcast message to worker group."""
        self.resonate.messages.broadcast(
            group=group,
            source=self.worker_id,
            type=message_type,
            payload=payload
        )
```

## Error Handling and Recovery

### Error Recovery Strategies

```python
class ErrorRecoveryHandler:
    """Implements error recovery strategies with modern Python patterns."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        
    def configure_recovery(self):
        """Configure automatic recovery behaviors."""
        
        # Transient error recovery
        self.resonate.on_error(
            error_type="TransientError",
            strategy="retry",
            config={
                "max_retries": 3,
                "backoff": "exponential",
                "initial_delay": 1000,
                "max_delay": 30000
            }
        )
        
        # Network error recovery
        self.resonate.on_error(
            error_type="NetworkError",
            strategy="retry_with_backoff",
            config={
                "max_retries": 5,
                "backoff": "linear",
                "delay": 5000
            }
        )
        
        # Fatal error handling
        self.resonate.on_error(
            error_type="FatalError",
            strategy="checkpoint_and_alert",
            config={
                "alert_channel": "ops-team",
                "preserve_state": True
            }
        )
        
    async def execute_with_recovery(
        self,
        operation: Callable,
        context: dict,
        timeout: float = 30.0
    ) -> Any:
        """Execute operation with comprehensive error handling.
        
        Uses Python 3.11+ features for robust error management.
        """
        try:
            # Use asyncio.timeout for cleaner timeout handling
            async with asyncio.timeout(timeout):
                result = await operation()
                return result
        except asyncio.TimeoutError as e:
            # Enrich timeout error with context
            e.add_note(f"Operation: {operation.__name__}")
            e.add_note(f"Timeout: {timeout} seconds")
            e.add_note(f"Context: {context}")
            raise
        except Exception as e:
            # Add recovery context to any error
            if hasattr(e, 'add_note'):
                e.add_note(f"Recovery attempted for: {operation.__name__}")
                e.add_note(f"Execution context: {context}")
            
            # Attempt recovery based on error type
            if isinstance(e, (ConnectionError, OSError)):
                return await self._retry_with_backoff(operation, e)
            else:
                raise
```

### Crash Recovery Implementation

```python
@resonate.register(
    name="crash_resilient_execution",
    idempotent=True,
    recovery="auto"
)
def crash_resilient_execution(ctx, args):
    """
    Execution that automatically recovers from crashes.
    
    Demonstrates checkpoint-based recovery pattern.
    """
    execution_id = args['execution_id']
    
    # Check for existing checkpoint
    checkpoint = yield ctx.get_checkpoint(execution_id)
    
    if checkpoint:
        # Resume from checkpoint
        state = checkpoint['state']
        step = checkpoint['step']
    else:
        # Start fresh
        state = {}
        step = 0
        
    # Step 1: Initialize
    if step <= 0:
        state['initialized'] = True
        yield ctx.checkpoint("step_1", {"state": state, "step": 1})
        
    # Step 2: Process
    if step <= 1:
        state['processed'] = yield ctx.lfc(process_data, args['data'])
        yield ctx.checkpoint("step_2", {"state": state, "step": 2})
        
    # Step 3: Finalize
    if step <= 2:
        state['finalized'] = yield ctx.lfc(finalize, state['processed'])
        yield ctx.checkpoint("step_3", {"state": state, "step": 3})
        
    return state['finalized']
```

## Performance Optimization

### Connection Pooling

```python
class ResonateConnectionPool:
    """Manages connection pooling for remote mode."""
    
    def __init__(self, resonate: Resonate, pool_size: int = 10):
        self.resonate = resonate
        self.pool_size = pool_size
        self.connections = []
        self._initialize_pool()
        
    def _initialize_pool(self):
        """Initialize connection pool."""
        for _ in range(self.pool_size):
            conn = self.resonate.create_connection()
            self.connections.append(conn)
            
    def get_connection(self):
        """Get connection from pool."""
        # Implementation with proper locking
        pass
```

### Promise Batching

```python
class PromiseBatcher:
    """Batches promise operations for efficiency."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        self.batch = []
        self.batch_size = 100
        self.flush_interval = 100  # ms
        
    def add_promise(self, promise_config: dict):
        """Add promise to batch."""
        self.batch.append(promise_config)
        
        if len(self.batch) >= self.batch_size:
            self.flush()
            
    def flush(self):
        """Flush batched promises."""
        if self.batch:
            self.resonate.promises.create_batch(self.batch)
            self.batch = []
```

## Monitoring and Observability

### Metrics Collection

```python
def setup_metrics(resonate: Resonate):
    """Configure metrics collection."""
    
    resonate.metrics.register({
        "execution_duration": "histogram",
        "promise_resolution_time": "histogram",
        "active_executions": "gauge",
        "error_rate": "counter",
        "checkpoint_count": "counter"
    })
    
    # Add metric hooks
    resonate.on_function_start(lambda ctx: 
        resonate.metrics.increment("active_executions")
    )
    
    resonate.on_function_complete(lambda ctx, duration:
        resonate.metrics.record("execution_duration", duration)
    )
```

### Tracing Configuration

```python
def setup_tracing(resonate: Resonate):
    """Configure distributed tracing."""
    
    resonate.tracing.configure({
        "enabled": True,
        "sample_rate": 0.1,
        "export_endpoint": "http://jaeger:14268/api/traces"
    })
    
    # Add trace context propagation
    resonate.tracing.add_propagator("w3c_trace_context")
```

## Migration Guide

### Incremental Adoption Path

```python
class MigrationAdapter:
    """Facilitates gradual migration to Resonate."""
    
    def __init__(self, legacy_executor, resonate: Resonate):
        self.legacy = legacy_executor
        self.resonate = resonate
        
    def execute(self, code: str, mode: str = "auto"):
        """Execute with automatic mode selection."""
        
        if mode == "legacy":
            return self.legacy.execute(code)
            
        elif mode == "resonate":
            return self._execute_with_resonate(code)
            
        else:  # auto
            if self._should_use_resonate(code):
                return self._execute_with_resonate(code)
            else:
                return self.legacy.execute(code)
                
    def _should_use_resonate(self, code: str) -> bool:
        """Determine if code should use Resonate."""
        # Check for async patterns, HITL needs, etc.
        return "await" in code or "input(" in code
```

## Configuration Reference

### Environment Variables

```python
# Local Development
RESONATE_MODE=local
RESONATE_LOG_LEVEL=DEBUG

# Remote Production
RESONATE_MODE=remote
RESONATE_HOST=http://resonate-server:8001
RESONATE_API_KEY=secret-key
RESONATE_WORKER_GROUP=pyrepl3-workers
RESONATE_WORKER_ID=auto

# Performance Tuning
RESONATE_POOL_SIZE=10
RESONATE_BATCH_SIZE=100
RESONATE_CHECKPOINT_INTERVAL=10000

# Feature Flags
RESONATE_ENABLE_TRACING=true
RESONATE_ENABLE_METRICS=true
RESONATE_ENABLE_RECOVERY=true
```

### Configuration Schema

```yaml
resonate:
  mode: local|remote
  
  local:
    storage: memory|disk
    storage_path: /tmp/resonate
    
  remote:
    host: http://localhost:8001
    api_key: optional-api-key
    tls:
      enabled: false
      cert_file: /path/to/cert
      key_file: /path/to/key
      
  promises:
    default_timeout: 300000
    cleanup_interval: 60000
    max_active: 10000
    
  functions:
    max_retries: 3
    retry_backoff: exponential
    checkpoint_enabled: true
    
  dependencies:
    lazy_loading: true
    singleton_default: true
    
  monitoring:
    metrics_enabled: true
    metrics_port: 9090
    tracing_enabled: true
    trace_sample_rate: 0.1
```

## Testing Utilities

### Test Helpers

```python
class ResonateTestHelper:
    """Utilities for testing Resonate integration."""
    
    @staticmethod
    def create_test_resonate() -> Resonate:
        """Create test instance with mock backend."""
        return Resonate.test(config={
            "mock_promises": True,
            "mock_checkpoints": True,
            "deterministic": True
        })
        
    @staticmethod
    def mock_promise_resolution(
        resonate: Resonate,
        promise_id: str,
        result: Any,
        delay: float = 0
    ):
        """Mock promise resolution for testing."""
        if delay:
            time.sleep(delay)
        resonate.promises.resolve(promise_id, result)
```

## Security Considerations

### API Key Management

```python
class SecureAPIKeyProvider:
    """Secure API key management for Resonate."""
    
    def __init__(self):
        self.key_source = os.getenv("RESONATE_KEY_SOURCE", "env")
        
    def get_api_key(self) -> Optional[str]:
        """Retrieve API key from secure source."""
        if self.key_source == "env":
            return os.getenv("RESONATE_API_KEY")
        elif self.key_source == "vault":
            return self._get_from_vault()
        elif self.key_source == "kms":
            return self._get_from_kms()
```

### TLS Configuration

```python
def configure_tls(resonate: Resonate):
    """Configure TLS for secure communication."""
    
    resonate.transport.configure_tls({
        "enabled": True,
        "verify_mode": "CERT_REQUIRED",
        "ca_bundle": "/etc/ssl/certs/ca-certificates.crt",
        "client_cert": "/app/certs/client.crt",
        "client_key": "/app/certs/client.key",
        "min_version": "TLSv1.3"
    })
```

## Troubleshooting Guide

### Common Issues and Solutions

1. **Promise Timeout**
   - Increase timeout value
   - Check external system responsiveness
   - Verify network connectivity

2. **Checkpoint Recovery Failure**
   - Ensure checkpoint data is serializable
   - Check storage backend availability
   - Verify execution ID consistency

3. **Dependency Injection Errors**
   - Confirm dependency registration
   - Check circular dependencies
   - Verify singleton configuration

4. **Remote Connection Issues**
   - Validate host configuration
   - Check firewall rules
   - Verify API key validity

## Performance Benchmarks

### Expected Performance Metrics

| Operation | Local Mode | Remote Mode |
|-----------|------------|-------------|
| Promise Creation | < 1ms | < 10ms |
| Promise Resolution | < 1ms | < 20ms |
| Function Registration | < 5ms | < 15ms |
| Dependency Injection | < 0.1ms | < 0.1ms |
| Checkpoint Creation | < 5ms | < 50ms |
| Recovery Time | N/A | < 1s |

## Structured Concurrency Patterns (Python 3.11+)

### TaskGroup Integration

```python
class ResonateTaskGroup:
    """Integrates Python 3.11+ TaskGroup with Resonate promises."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        
    async def execute_parallel_promises(
        self,
        promises: List[Dict[str, Any]]
    ) -> List[Any]:
        """Execute multiple promises in parallel with structured concurrency.
        
        Uses TaskGroup to ensure all tasks complete or cancel together.
        If any promise fails, all others are cancelled automatically.
        """
        results = []
        
        async with asyncio.TaskGroup() as tg:
            # Create tasks for each promise
            tasks = []
            for promise_config in promises:
                task = tg.create_task(
                    self._execute_promise(promise_config)
                )
                tasks.append(task)
            
        # All tasks completed successfully if we get here
        # TaskGroup raises ExceptionGroup on any failure
        return [task.result() for task in tasks]
        
    async def execute_with_timeout_group(
        self,
        operations: List[Callable],
        timeout: float = 30.0
    ) -> List[Any]:
        """Execute operations with shared timeout and cancellation.
        
        Combines TaskGroup with asyncio.timeout for robust execution.
        """
        async with asyncio.timeout(timeout):
            async with asyncio.TaskGroup() as tg:
                tasks = []
                for op in operations:
                    task = tg.create_task(op())
                    tasks.append(task)
                    
        return [task.result() for task in tasks]
```

### Exception Group Handling

```python
def handle_execution_errors(eg: ExceptionGroup) -> None:
    """Handle grouped exceptions from concurrent execution.
    
    Python 3.11+ provides except* syntax for selective handling.
    """
    try:
        raise eg
    except* TimeoutError as timeout_group:
        # Handle all timeout errors
        for e in timeout_group.exceptions:
            logger.warning(f"Operation timed out: {e}")
    except* ValueError as value_group:
        # Handle validation errors
        for e in value_group.exceptions:
            logger.error(f"Validation failed: {e}")
    except* Exception as other_group:
        # Handle remaining errors
        for e in other_group.exceptions:
            logger.error(f"Unexpected error: {e}")
```

## Future Enhancements

### Planned Features

1. **Advanced Scheduling**
   - Cron-based execution
   - Rate limiting
   - Priority queues

2. **Enhanced Observability**
   - Real-time dashboards
   - Anomaly detection
   - Performance profiling

3. **Extended Integration**
   - GraphQL support
   - WebSocket promises
   - Stream processing

### Python 3.12+ Forward Compatibility

#### Subinterpreter Support (PEP 684)

```python
class SubinterpreterIntegration:
    """Forward compatibility for Python 3.12+ subinterpreters.
    
    When Python 3.12's per-interpreter GIL becomes available,
    we can use subinterpreters instead of subprocesses for
    better performance with maintained isolation.
    """
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        self.use_subinterpreters = self._check_subinterpreter_support()
        
    def _check_subinterpreter_support(self) -> bool:
        """Check if subinterpreters with per-interpreter GIL are available."""
        import sys
        if sys.version_info < (3, 12):
            return False
            
        try:
            # Check for PEP 684 support
            import _interpreters
            # Test if per-interpreter GIL is enabled
            return hasattr(_interpreters, 'create') and \
                   getattr(_interpreters, 'PER_INTERPRETER_GIL', False)
        except ImportError:
            return False
            
    async def execute_isolated(
        self,
        code: str,
        use_subinterpreter: Optional[bool] = None
    ) -> Any:
        """Execute code in isolated context.
        
        Uses subinterpreters if available, otherwise falls back
        to subprocess isolation.
        """
        if use_subinterpreter is None:
            use_subinterpreter = self.use_subinterpreters
            
        if use_subinterpreter:
            return await self._execute_in_subinterpreter(code)
        else:
            return await self._execute_in_subprocess(code)
```

#### Free-Threading Support (PEP 703)

```python
# Forward compatibility for no-GIL Python (experimental in 3.13+)
def check_nogil_support() -> bool:
    """Check if Python was compiled with --disable-gil."""
    import sys
    return getattr(sys, '_is_gil_disabled', lambda: False)()

if check_nogil_support():
    # Use thread-based parallelism for CPU-bound tasks
    executor_class = ThreadPoolExecutor
else:
    # Use process-based parallelism for CPU-bound tasks
    executor_class = ProcessPoolExecutor
```

## Appendices

### A. API Reference
See complete API documentation in 05_api_reference_specification.md

### B. Error Codes
- `RES001`: Promise timeout
- `RES002`: Checkpoint not found
- `RES003`: Dependency not registered
- `RES004`: Connection failed
- `RES005`: Authentication failed

### C. Glossary
- **Durable Function**: Function with automatic recovery support
- **Promise**: Durable future with correlation
- **Checkpoint**: Execution state snapshot
- **HITL**: Human-in-the-loop workflow
- **LFC**: Local function call within durable context

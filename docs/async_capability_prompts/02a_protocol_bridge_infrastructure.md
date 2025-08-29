# Protocol Bridge Infrastructure Planning Prompt (Superseded by Resonate)

## Important Note

**This prompt has been superseded by the Resonate integration (see `00_resonate_foundation.md`). Resonate's durable promises provide all the functionality originally planned for the Protocol Bridge, plus crash recovery and distributed execution support.**

## Original Mission (For Historical Context)

You were tasked with implementing the Protocol Bridge - a generic bidirectional communication infrastructure that enables capabilities to send protocol messages and receive correlated responses. This would have replaced the old polling-based input routing (Pattern 3) with a modern event-driven architecture that serves ALL protocol-bridged capabilities, not just input.

## How Resonate Replaces Protocol Bridge

Resonate's promise system provides superior functionality to what was planned for Protocol Bridge:

### Original Protocol Bridge Design vs Resonate Implementation

| Protocol Bridge (Original) | Resonate (Actual) |
|---------------------------|-------------------|
| In-memory futures | Durable promises |
| Process-local routing | Distributed routing |
| Manual cleanup on crash | Automatic recovery |
| Custom correlation logic | Built-in promise IDs |
| asyncio.Future based | yield ctx.promise() based |
| No HITL support | Native HITL via promise resolution |

### Migration from Protocol Bridge Concept to Resonate

Instead of implementing ProtocolBridge class:
```python
# ORIGINAL PLAN (Don't implement)
bridge = ProtocolBridge(transport)
future = await bridge.send_request(capability_id, execution_id, message, timeout)
response = await future
```

Use Resonate promises:
```python
# ACTUAL IMPLEMENTATION (Use this)
@resonate.register
def capability_function(ctx, args):
    # Create durable promise
    promise = yield ctx.promise(
        id=f"request:{args['execution_id']}:{uuid.uuid4()}",
        data={"type": "capability_request", "details": args}
    )
    
    # External service resolves: resonate.promises.resolve(id=promise_id, data=response)
    
    # Wait for resolution
    response = yield promise
    return response
```

## Original Context Gathering Requirements (Historical)

Before the Resonate integration, you would have needed to understand:

### 1. Current State
- **Legacy Pattern**: Worker routes INPUT_RESPONSE to single active executor
- **Limitation**: Tight coupling, assumes single execution, input-specific
- **What Works**: Basic message routing exists
- **Investigation**: See Pattern 3 in `05_polling_to_event_driven_investigation.md`

### 2. Target Architecture
- **Generic Infrastructure**: Not input-specific, serves all capabilities
- **Correlation-Based**: Uses correlation_id to match requests/responses
- **Future-Based**: Async capabilities await responses via futures
- **Multi-Execution**: Supports concurrent executions with proper isolation
- **Capability-Agnostic**: Any capability can use request/response pattern

### 3. Integration Points
- **With AsyncExecutor**: Register/cleanup on execution lifecycle
- **With Capabilities**: Provide send_request/await_response interface
- **With Worker**: Route messages through bridge, not direct to executor
- **With Transport**: Maintain message ordering guarantees

## Planning Methodology

### Phase 1: Analysis (30% effort)
<context_gathering>
Goal: Understand all capability communication patterns
Stop when: You know every type of response routing needed
Depth: Study existing INPUT_RESPONSE, plan for FILE_RESPONSE, QUERY_RESPONSE, etc.
</context_gathering>

Investigate:
1. Message correlation patterns in modern RPC systems
2. Future/promise patterns in Python asyncio
3. Resource cleanup and cancellation semantics
4. Performance implications of correlation lookups

### Phase 2: Solution Design (50% effort)

**Core Protocol Bridge Design:**

```python
# src/subprocess/protocol_bridge.py
from typing import Dict, Set, Optional, Any, Union
import asyncio
import weakref
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

@dataclass
class PendingRequest:
    """Tracks a pending request awaiting response."""
    request_id: str
    capability_id: str
    execution_id: str
    future: asyncio.Future
    created_at: float
    timeout: Optional[float] = None

class ProtocolBridge:
    """Routes protocol responses to waiting capabilities.
    
    This is the evolution of Pattern 3 - instead of routing just
    INPUT_RESPONSE to executors, it routes ANY response to ANY
    waiting capability via futures.
    """
    
    def __init__(self, transport: MessageTransport):
        self._transport = transport
        
        # Core routing tables
        self._pending_requests: Dict[str, PendingRequest] = {}
        self._execution_requests: Dict[str, Set[str]] = {}
        self._capability_requests: Dict[str, Set[str]] = {}
        
        # Metrics
        self._metrics = BridgeMetrics()
        
        # Cleanup tracking
        self._cleanup_tasks: weakref.WeakValueDictionary = {}
        
    async def send_request(
        self,
        capability_id: str,
        execution_id: str,
        message: Message,
        timeout: Optional[float] = None
    ) -> asyncio.Future:
        """Send a request expecting a correlated response.
        
        Args:
            capability_id: Which capability is sending
            execution_id: Which execution context
            message: Protocol message with unique id
            timeout: Optional timeout for response
            
        Returns:
            Future that will be completed with response
        """
        request_id = message.id
        
        # Create future for response
        future = asyncio.create_future()
        
        # Track pending request
        pending = PendingRequest(
            request_id=request_id,
            capability_id=capability_id,
            execution_id=execution_id,
            future=future,
            created_at=asyncio.get_event_loop().time(),
            timeout=timeout
        )
        
        self._pending_requests[request_id] = pending
        
        # Track by execution and capability for cleanup
        if execution_id not in self._execution_requests:
            self._execution_requests[execution_id] = set()
        self._execution_requests[execution_id].add(request_id)
        
        if capability_id not in self._capability_requests:
            self._capability_requests[capability_id] = set()
        self._capability_requests[capability_id].add(request_id)
        
        # Send the actual message
        await self._transport.send_message(message)
        
        # Start timeout if specified
        if timeout:
            asyncio.create_task(self._timeout_request(request_id, timeout))
        
        self._metrics.requests_sent += 1
        
        return future
    
    async def route_response(self, message: Message) -> bool:
        """Route a response message to waiting capability.
        
        Args:
            message: Response message with correlation_id
            
        Returns:
            True if routed successfully, False if no waiter
        """
        # Extract correlation ID (may vary by message type)
        correlation_id = self._extract_correlation_id(message)
        
        if not correlation_id:
            self._metrics.responses_uncorrelated += 1
            return False
            
        pending = self._pending_requests.pop(correlation_id, None)
        
        if not pending:
            self._metrics.responses_orphaned += 1
            return False
            
        # Complete the future
        if not pending.future.done():
            pending.future.set_result(message)
            
            # Update metrics
            elapsed = asyncio.get_event_loop().time() - pending.created_at
            self._metrics.responses_completed += 1
            self._metrics.total_response_time += elapsed
            
        # Cleanup tracking
        self._execution_requests[pending.execution_id].discard(correlation_id)
        self._capability_requests[pending.capability_id].discard(correlation_id)
        
        return True
    
    def cleanup_execution(self, execution_id: str) -> None:
        """Cancel all pending requests for an execution."""
        request_ids = self._execution_requests.pop(execution_id, set())
        
        for request_id in request_ids:
            pending = self._pending_requests.pop(request_id, None)
            if pending and not pending.future.done():
                pending.future.set_exception(
                    ExecutionCancelledError(f"Execution {execution_id} terminated")
                )
                self._metrics.requests_cancelled += 1
    
    def _extract_correlation_id(self, message: Message) -> Optional[str]:
        """Extract correlation ID from various message types."""
        # Pattern for different response types
        if hasattr(message, 'correlation_id'):
            return message.correlation_id
        elif hasattr(message, 'input_id'):  # Legacy INPUT_RESPONSE
            return message.input_id
        elif hasattr(message, 'request_id'):
            return message.request_id
        return None
    
    async def _timeout_request(self, request_id: str, timeout: float) -> None:
        """Cancel request after timeout."""
        await asyncio.sleep(timeout)
        
        pending = self._pending_requests.pop(request_id, None)
        if pending and not pending.future.done():
            pending.future.set_exception(
                asyncio.TimeoutError(f"Request {request_id} timed out")
            )
            self._metrics.requests_timeout += 1

@dataclass
class BridgeMetrics:
    """Metrics for protocol bridge performance."""
    requests_sent: int = 0
    responses_completed: int = 0
    responses_orphaned: int = 0
    responses_uncorrelated: int = 0
    requests_cancelled: int = 0
    requests_timeout: int = 0
    total_response_time: float = 0.0
    
    @property
    def avg_response_time(self) -> float:
        if self.responses_completed == 0:
            return 0.0
        return self.total_response_time / self.responses_completed
```

**Integration with Capabilities:**

```python
class ProtocolBridgedCapability(Capability):
    """Base class for capabilities that use request/response."""
    
    def __init__(
        self,
        bridge: ProtocolBridge,
        execution_id: str,
        capability_id: str
    ):
        self._bridge = bridge
        self._execution_id = execution_id
        self._capability_id = capability_id
    
    async def send_and_await(
        self,
        message: Message,
        timeout: Optional[float] = None
    ) -> Any:
        """Send message and await correlated response."""
        future = await self._bridge.send_request(
            capability_id=self._capability_id,
            execution_id=self._execution_id,
            message=message,
            timeout=timeout
        )
        return await future
```

### Phase 3: Migration Strategy (20% effort)

1. **Phase 1**: Implement ProtocolBridge alongside existing routing
2. **Phase 2**: Migrate InputCapability to use bridge
3. **Phase 3**: Remove old _active_executor routing
4. **Phase 4**: Add new capability types using bridge

## Output Requirements

### 1. Executive Summary
- How Protocol Bridge replaces polling Pattern 3
- Benefits over input-specific routing
- Performance implications
- Future capability enablement

### 2. Implementation Files

**File 1: protocol_bridge.py**
- Full ProtocolBridge implementation
- PendingRequest tracking
- Metrics collection
- Cleanup semantics

**File 2: Updated worker.py**
```python
class SubprocessWorker:
    def __init__(self, ...):
        self._protocol_bridge = ProtocolBridge(self._transport)
    
    async def execute(self, message: ExecuteMessage):
        # Register execution
        # ...
        try:
            # Create executor with bridge
            if use_async:
                executor = AsyncExecutor(
                    bridge=self._protocol_bridge,
                    ...
                )
            else:
                # Adapter for ThreadedExecutor
                executor = ThreadedExecutor(...)
        finally:
            self._protocol_bridge.cleanup_execution(execution_id)
    
    async def run(self):
        # Route responses through bridge
        if message.type in RESPONSE_TYPES:
            routed = await self._protocol_bridge.route_response(message)
            if not routed:
                logger.warning("Orphaned response", message_id=message.id)
```

**File 3: capability_examples.py**
Show how different capabilities use the bridge

### 3. Test Cases

```python
async def test_request_response_correlation():
    """Test correct response routing."""
    
async def test_concurrent_requests():
    """Test multiple pending requests."""
    
async def test_execution_cleanup():
    """Test cleanup cancels pending requests."""
    
async def test_timeout_handling():
    """Test request timeouts work correctly."""
    
async def test_orphaned_responses():
    """Test handling of responses with no waiter."""
```

## Calibration

<context_gathering>
- Search depth: MEDIUM (infrastructure change)
- Maximum tool calls: 15-20
- Early stop: When routing patterns clear
</context_gathering>

## Non-Negotiables

1. **Generic from day one**: Not input-specific
2. **Future-based**: Clean async/await interface
3. **Proper cleanup**: No leaked resources
4. **Metrics**: Observable performance
5. **Backward compatible**: ThreadedExecutor still works

## Success Criteria

Before finalizing:
- [ ] All capability types can use bridge
- [ ] Zero polling for response routing
- [ ] Clean execution cleanup
- [ ] Metrics show performance improvement
- [ ] Tests pass for concurrent operations

## Additional Guidance

- Study RPC correlation patterns (gRPC, JSON-RPC)
- Consider using weakrefs for cleanup tracking
- Plan for streaming responses (future)
- Document migration path clearly
- Look at how Jupyter handles comm messages for bidirectional communication
- Consider how this pattern extends to WebSocket-based capabilities

## Capability Communication Patterns

The Protocol Bridge supports multiple communication patterns:

### 1. Request-Response (Most Common)
```python
class QueryCapability(ProtocolBridgedCapability):
    async def query(self, sql: str) -> List[Dict]:
        response = await self.send_and_await(
            QueryMessage(id=uuid4(), sql=sql),
            timeout=30.0
        )
        return response.results
```

### 2. Multiple Responses (Future Extension)
```python
class WatchCapability(ProtocolBridgedCapability):
    async def watch_file(self, path: str) -> AsyncIterator[str]:
        # Bridge will support streaming in future
        pass
```

### 3. Fire-and-Forget (No Bridge Needed)
```python
class LogCapability(Capability):
    async def log(self, message: str) -> None:
        # Just send, no response needed
        await self._transport.send_message(LogMessage(...))
```

## Relationship to AsyncExecutor

The Protocol Bridge is a **peer component** to AsyncExecutor, not subordinate:

```
Worker
├── AsyncExecutor (handles execution)
├── ProtocolBridge (handles capability communication)
└── NamespaceManager (handles state)
```

This separation of concerns allows:
- AsyncExecutor to focus on code execution
- ProtocolBridge to handle all capability I/O
- Clean testing of each component
- Future extension to non-Python execution contexts
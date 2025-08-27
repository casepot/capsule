# Capability Injection System Planning Prompt (REFINED)

## Your Mission

You are tasked with extending the NamespaceManager to support a comprehensive capability injection system. Based on testing, capability injection works excellently - focus on handling async protocol messages correctly and avoiding security preprocessor limitations discovered during investigation.

## Context Gathering Requirements

### 1. Problem History (NEW INSIGHT)
- **Security Preprocessors**: IPython's string-level preprocessors are easily bypassed
- **Key Lesson**: Security must be enforced at capability level, not code level
- **Success Story**: Dynamic capability injection tested successfully with IPython

### 2. Protocol Message Complexity (CRITICAL DISCOVERY)
- **Event Loop Issue**: `RuntimeError: no running event loop` when sending messages from sync
- **Solution Pattern**: Queue messages, send when in async context
- **Invariant**: Never call `asyncio.create_task()` outside event loop

### 3. Existing Infrastructure (VALIDATED)
- **Capability Pattern**: Injection into namespace works perfectly
- **Dynamic Management**: Add/remove capabilities at runtime succeeded
- **Security Policies**: Can be enforced at injection time

## Planning Methodology

### Phase 1: Analysis (20% effort - REDUCED, pattern proven)
<context_gathering>
Goal: Focus on async/sync bridge for protocol messages
Stop when: Message queueing pattern is clear
Depth: Study asyncio event loop detection and queuing
</context_gathering>

### Phase 2: Solution Design (60% effort - INCREASED for robustness)

**Protocol-Aware Capability Base (REFINED):**

```python
# src/subprocess/capabilities.py
import asyncio
import threading
from typing import Any, Callable, Dict, List, Optional
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class PendingMessage:
    """Message waiting to be sent."""
    message: Any
    future: Optional[asyncio.Future] = None

class Capability(ABC):
    """Base class with proper async handling - REFINED."""
    
    def __init__(self, transport: MessageTransport):
        self.transport = transport
        self._pending_requests: Dict[str, asyncio.Future] = {}
        # CRITICAL: Queue for messages when not in async context
        self._message_queue: List[PendingMessage] = []
        self._queue_lock = threading.Lock()
    
    async def send_message_safe(self, message: Any) -> None:
        """Send message handling async context properly."""
        try:
            # Check if we're in async context
            loop = asyncio.get_running_loop()
            await self.transport.send_message(message)
        except RuntimeError:
            # Not in async context - queue it
            with self._queue_lock:
                self._message_queue.append(PendingMessage(message))
    
    async def flush_message_queue(self) -> None:
        """Flush queued messages when in async context."""
        with self._queue_lock:
            messages = self._message_queue[:]
            self._message_queue.clear()
        
        for pending in messages:
            await self.transport.send_message(pending.message)
            if pending.future:
                pending.future.set_result(None)
    
    def create_hybrid_implementation(self) -> Callable:
        """Create implementation that works in sync and async contexts."""
        async_impl = self.get_async_implementation()
        
        def hybrid_wrapper(*args, **kwargs):
            """Wrapper that handles both contexts."""
            try:
                # Try to get event loop
                loop = asyncio.get_running_loop()
                # We're in async context
                return async_impl(*args, **kwargs)
            except RuntimeError:
                # We're in sync context - return coroutine for later
                return self._create_deferred_coroutine(*args, **kwargs)
        
        return hybrid_wrapper
    
    def _create_deferred_coroutine(self, *args, **kwargs):
        """Create coroutine that queues messages for later."""
        async def deferred():
            # First flush any queued messages
            await self.flush_message_queue()
            # Then execute the actual capability
            return await self.get_async_implementation()(*args, **kwargs)
        return deferred()

class InputCapability(Capability):
    """Input with proper async handling - REFINED."""
    
    def get_name(self) -> str:
        return 'input'
    
    def get_async_implementation(self) -> Callable:
        """The actual async implementation."""
        async def async_input(prompt: str = "") -> str:
            request_id = str(uuid.uuid4())
            
            # Send request (now safe from any context)
            await self.send_message_safe(InputRequestMessage(
                id=request_id,
                prompt=prompt,
                execution_id=self.execution_id
            ))
            
            # Wait for response
            future = asyncio.Future()
            self._pending_requests[request_id] = future
            
            try:
                response = await asyncio.wait_for(future, timeout=30.0)
                return response
            finally:
                self._pending_requests.pop(request_id, None)
        
        return async_input
    
    def get_implementation(self) -> Callable:
        """Get the hybrid implementation."""
        return self.create_hybrid_implementation()
```

**Security Policy with Capability-Level Enforcement (REFINED):**

```python
# src/subprocess/security_policy.py
from enum import Enum
from typing import Set, Dict, Any, Callable

class SecurityLevel(Enum):
    """Security levels based on investigation."""
    SANDBOX = "sandbox"      # Minimal - no I/O
    RESTRICTED = "restricted" # Local I/O only
    STANDARD = "standard"    # Network + I/O
    TRUSTED = "trusted"      # Most capabilities
    UNRESTRICTED = "unrestricted"  # All capabilities

class SecurityPolicy:
    """Capability-level security (not code-level)."""
    
    # Capability sets refined from testing
    CAPABILITY_SETS = {
        SecurityLevel.SANDBOX: {
            'print',  # Output only
            'display', # Rich display
        },
        SecurityLevel.RESTRICTED: {
            'print', 'display', 'input',  # Basic I/O
            'read_file',  # Read only
        },
        SecurityLevel.STANDARD: {
            'print', 'display', 'input',
            'read_file', 'write_file',  # File I/O
            'fetch',  # Network read
        },
        SecurityLevel.TRUSTED: {
            'print', 'display', 'input',
            'read_file', 'write_file', 
            'fetch', 'websocket',  # Full network
            'query',  # Database
        },
        SecurityLevel.UNRESTRICTED: '*'  # Everything
    }
    
    def __init__(self, level: SecurityLevel = SecurityLevel.STANDARD):
        self.level = level
        self._allowed = self._compute_allowed()
        self._blocked = set()  # Explicitly blocked
        # CRITICAL: No code preprocessors - they don't work
        self._capability_validators: Dict[str, Callable] = {}
    
    def is_allowed(self, capability_name: str) -> bool:
        """Check at capability level, not code level."""
        if capability_name in self._blocked:
            return False
        if self._allowed == '*':
            return True
        return capability_name in self._allowed
    
    def add_capability_validator(self, cap_name: str, validator: Callable):
        """Add runtime validator for capability usage."""
        # This is more effective than code preprocessors
        self._capability_validators[cap_name] = validator
```

**Enhanced NamespaceManager with Async Awareness (REFINED):**

```python
# Extensions to src/subprocess/namespace.py
class NamespaceManager:
    
    def inject_capability(
        self,
        name: str,
        capability: Optional[Capability] = None,
        override: bool = False
    ):
        """Inject with async context awareness."""
        
        # Security check (capability-level, not code-level)
        if self._security_policy and not self._security_policy.is_allowed(name):
            raise SecurityError(f"Capability '{name}' blocked by policy")
        
        # Get or create capability
        if capability is None:
            capability = self._registry.create_instance(name, self.transport)
        
        # CRITICAL: Set execution context
        capability.execution_id = self.current_execution_id
        
        # Get implementation (hybrid sync/async)
        implementation = capability.get_implementation()
        
        # Check if we need to wrap for async detection
        if asyncio.iscoroutinefunction(implementation):
            # Pure async - create sync wrapper
            def sync_wrapper(*args, **kwargs):
                coro = implementation(*args, **kwargs)
                # Return coroutine for async context to handle
                return coro
            
            sync_wrapper._is_capability = True
            sync_wrapper._capability_instance = capability
            self._namespace[name] = sync_wrapper
        else:
            # Already hybrid or sync
            self._namespace[name] = implementation
        
        self._capabilities[name] = capability
        
        logger.info(
            "Injected capability",
            name=name,
            type=capability.__class__.__name__,
            async_aware=True
        )
    
    async def flush_capability_queues(self):
        """Flush all capability message queues."""
        for cap in self._capabilities.values():
            if hasattr(cap, 'flush_message_queue'):
                await cap.flush_message_queue()
```

### Phase 3: Risk Assessment (20% effort)

**Refined Risks from Investigation:**

1. **Event Loop Detection**
   - **Issue**: RuntimeError when no event loop
   - **Mitigation**: Queue messages, flush when async
   - **Test**: Call capability from both sync and async

2. **Security Bypass**
   - **Issue**: Code preprocessors easily bypassed
   - **Mitigation**: Enforce at capability injection only
   - **Test**: Try to bypass with eval/exec

3. **Message Correlation**
   - **Issue**: Responses arriving out of order
   - **Mitigation**: Request ID tracking with futures
   - **Test**: Concurrent capability calls

## Output Requirements

### 1. Executive Summary
- Capability injection works perfectly (proven in tests)
- Focus on async/sync context handling for protocol messages
- Security at capability level, not code level
- Message queueing prevents event loop errors

### 2. Implementation Checklist
- [ ] Queue messages when not in async context
- [ ] Flush queues when entering async context
- [ ] Security at injection time, not execution time
- [ ] Hybrid implementations for sync/async contexts
- [ ] Request ID correlation for concurrent calls

### 3. Critical Test Cases

```python
async def test_capability_from_sync_context():
    """Test capability works when called from sync code."""
    # This was failing with RuntimeError
    code = "result = input('test>')"
    await executor.execute(code)  # Should queue, not crash

async def test_capability_from_async_context():
    """Test capability works in async code."""
    code = "result = await fetch('http://example.com')"
    await executor.execute(code)  # Should work directly

async def test_security_bypass_prevention():
    """Test that security can't be bypassed."""
    policy = SecurityPolicy(SecurityLevel.SANDBOX)
    namespace.set_security_policy(policy)
    
    # Should fail at injection
    with pytest.raises(SecurityError):
        namespace.inject_capability('fetch')
    
    # Even with eval tricks
    code = "eval('fetch')('http://evil.com')"
    # fetch shouldn't exist in namespace
```

## Non-Negotiables (REFINED)

1. **Message Queueing**: Must handle non-async contexts
2. **Security at Capability Level**: Not code analysis
3. **Hybrid Implementations**: Work in any context
4. **No Code Preprocessors**: They don't work reliably

## Success Criteria

- [ ] No RuntimeError from event loop detection
- [ ] Capabilities work from sync and async code
- [ ] Security policies enforced at injection
- [ ] Messages queued and flushed properly
- [ ] Concurrent capability calls work correctly
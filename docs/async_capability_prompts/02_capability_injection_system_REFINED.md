# Capability Injection System Planning Prompt (REFINED with Resonate)

## Your Mission

You are tasked with extending the NamespaceManager to support a comprehensive capability injection system using Resonate's dependency injection. Based on testing, capability injection works excellently - focus on using Resonate promises for protocol communication and Resonate dependencies for capability management.

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

**Protocol-Aware Capability Base (REFINED with Resonate Promises):**

```python
# src/subprocess/capabilities.py
import json
import time
from typing import Any, Callable, Dict, Optional
import uuid
from abc import ABC, abstractmethod
from resonate_sdk import Resonate

class Capability(ABC):
    """Base class using Resonate promises for durability."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
    
    def create_promise_for_request(
        self,
        request_id: str,
        message_type: str,
        timeout: Optional[float] = None
    ):
        """Create durable promise for request/response."""
        promise_data = {
            'type': message_type,
            'created_at': time.time()
        }
        
        timeout_ms = None
        if timeout:
            timeout_ms = int((time.time() + timeout) * 1000)
        
        return self.resonate.promises.create(
            id=request_id,
            timeout=timeout_ms,
            data=json.dumps(promise_data)
        )
    
    @abstractmethod
    def get_name(self) -> str:
        """Get capability name for injection."""
        pass
    
    @abstractmethod
    def get_implementation(self) -> Callable:
        """Get the implementation function."""
        pass

class InputCapability(Capability):
    """Input using Resonate promises for HITL."""
    
    def __init__(self, resonate: Resonate, execution_id: str):
        super().__init__(resonate)
        self.execution_id = execution_id
    
    def get_name(self) -> str:
        return 'input'
    
    def get_implementation(self) -> Callable:
        """Return function that uses Resonate promises."""
        def input_with_promise(prompt: str = "") -> str:
            # This will be called from inside a durable function
            # so it needs to use yield for Resonate context
            request_id = f"input:{self.execution_id}:{uuid.uuid4()}"
            
            # Create promise for this input request
            promise = self.create_promise_for_request(
                request_id=request_id,
                message_type='input_request',
                timeout=300.0  # 5 minutes
            )
            
            # UI will resolve this promise
            # resonate.promises.resolve(id=request_id, data=user_input)
            
            # Return the promise ID so the durable function can wait
            return request_id
        
        return input_with_promise

# Usage in a durable function
@resonate.register
def execute_with_input(ctx, args):
    """Execute code that needs user input."""
    input_cap = ctx.get_dependency("input")
    
    # Create promise for input
    promise_id = input_cap("Enter your name: ")
    
    # Wait for promise resolution
    promise = yield ctx.promise(id=promise_id)
    user_input = yield promise
    
    return json.loads(user_input)['data']
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

**Enhanced NamespaceManager with Resonate Dependencies:**

```python
# Extensions to src/subprocess/namespace.py
from resonate_sdk import Resonate

class NamespaceManager:
    """Manages namespace with Resonate dependency injection."""
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        self._namespace = {}
        self._security_policy = None
    
    def register_capabilities(self, security_policy: SecurityPolicy):
        """Register all capabilities as Resonate dependencies."""
        self._security_policy = security_policy
        
        # Core I/O capabilities
        if security_policy.is_allowed("input"):
            self.resonate.set_dependency("input", InputCapability)
        if security_policy.is_allowed("print"):
            self.resonate.set_dependency("print", PrintCapability)
        if security_policy.is_allowed("display"):
            self.resonate.set_dependency("display", DisplayCapability)
        
        # File capabilities
        if security_policy.is_allowed("read_file"):
            self.resonate.set_dependency("read_file", FileReadCapability)
        if security_policy.is_allowed("write_file"):
            self.resonate.set_dependency("write_file", FileWriteCapability)
        
        # Network capabilities
        if security_policy.is_allowed("fetch"):
            self.resonate.set_dependency("fetch", FetchCapability)
        if security_policy.is_allowed("websocket"):
            self.resonate.set_dependency("websocket", WebSocketCapability)
    
    def inject_into_namespace(self, execution_id: str):
        """Inject capabilities into execution namespace."""
        # This is called from within a durable function
        # Capabilities are accessed via context.get_dependency()
        
        # For backward compatibility, create wrapper functions
        def create_capability_wrapper(cap_name: str):
            def wrapper(*args, **kwargs):
                # This will be resolved inside durable function
                return f"RESONATE_CAP:{cap_name}:{args}:{kwargs}"
            return wrapper
        
        # Inject wrappers for allowed capabilities
        for cap_name in ["input", "print", "display", "read_file", 
                         "write_file", "fetch", "websocket"]:
            if self._security_policy.is_allowed(cap_name):
                self._namespace[cap_name] = create_capability_wrapper(cap_name)

# Usage in durable function
@resonate.register
def execute_with_capabilities(ctx, args):
    """Execute with capability access via Resonate."""
    code = args['code']
    execution_id = args['execution_id']
    
    # Get capabilities from dependencies
    input_cap = ctx.get_dependency("input") if ctx.has_dependency("input") else None
    print_cap = ctx.get_dependency("print") if ctx.has_dependency("print") else None
    
    # Create namespace with capabilities
    namespace = {
        'input': input_cap.get_implementation() if input_cap else None,
        'print': print_cap.get_implementation() if print_cap else None,
        '__builtins__': __builtins__,
    }
    
    # Execute code with capabilities
    exec(code, namespace)
    
    return namespace.get('result')
```

### Resonate Promise Integration (Replaces Protocol Bridge)

With Resonate, the Protocol Bridge infrastructure is replaced by durable promises. Capabilities use Resonate's promise system for request/response patterns:

- **Durable promises**: Survive crashes and restarts
- **Built-in correlation**: Promise IDs serve as correlation IDs
- **Automatic cleanup**: Promises expire based on timeouts
- **HITL support**: External systems can resolve promises
- **Distributed by design**: Works across processes and machines

**Integration Pattern with Resonate:**

```python
class FileReadCapability(Capability):
    """File operations using Resonate promises."""
    
    def read_file_with_promise(self, path: str) -> str:
        """Create promise for file read operation."""
        request_id = f"file_read:{self.execution_id}:{uuid.uuid4()}"
        
        # Create durable promise
        self.resonate.promises.create(
            id=request_id,
            timeout=int((time.time() + 10) * 1000),
            data=json.dumps({'path': path, 'operation': 'read'})
        )
        
        # External file service will:
        # 1. Poll for pending file_read promises
        # 2. Perform the file operation
        # 3. Resolve: resonate.promises.resolve(id=request_id, data=content)
        
        return request_id  # Return promise ID for durable function to await

@resonate.register
def execute_with_file_read(ctx, args):
    """Durable function that reads a file."""
    file_cap = ctx.get_dependency("read_file")
    
    # Create promise for file read
    promise_id = file_cap.read_file_with_promise("/path/to/file.txt")
    
    # Wait for external resolution
    promise = yield ctx.promise(id=promise_id)
    content = yield promise
    
    return json.loads(content)['data']
```

This removes the need for custom routing logic. Resonate handles:
- Promise creation with unique IDs
- Durable storage of promise state
- External resolution from any process
- Automatic timeout and cleanup
- Recovery after crashes

**Capability Types and Promise Usage:**

| Capability Type | Uses Resonate Promises | Example |
|----------------|----------------------|---------|
| Send-only | No | `print`, `log`, `display` |
| Request-Response | **Yes** | `input`, `read_file`, `query` |
| HITL | **Yes** | `approve`, `review`, `input` |
| Scheduled | **Yes** | `cron`, `delayed`, `retry` |

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
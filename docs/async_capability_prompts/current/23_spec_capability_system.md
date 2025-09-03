# Capability System Specification

## Document Information
- **Version**: 1.0.0
- **Status**: Draft
- **Last Updated**: 2025-01-03
- **Classification**: Technical Specification

## Executive Summary

This specification defines the capability injection system for PyREPL3, implementing security enforcement at the capability level rather than through code analysis. The system leverages Resonate's dependency injection framework and promise-based communication to provide secure, dynamic access to external functionality while maintaining clear security boundaries and supporting human-in-the-loop workflows.

## Core Principles

### Security Philosophy

```
┌─────────────────────────────────────────┐
│        Traditional (Ineffective)         │
├─────────────────────────────────────────┤
│  Code Analysis → String Preprocessing   │
│  ↓                                      │
│  EASILY BYPASSED via eval(), exec()    │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│      Capability-Based (Effective)       │
├─────────────────────────────────────────┤
│  Security Policy → Capability Injection │
│  ↓                                      │
│  ENFORCED: If not injected, not available │
└─────────────────────────────────────────┘
```

### Key Design Decisions

1. **No Code Preprocessing**: String-level security is easily bypassed
2. **Injection-Time Enforcement**: Security decisions made at capability injection
3. **Promise-Based Communication**: All I/O through durable promises
4. **Async/Sync Bridge**: Queue messages when not in async context
5. **HITL Native**: Human interactions via promise resolution

## Capability Architecture

### Base Capability Interface

```python
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, List
from enum import Enum
import json
import uuid
import time
import asyncio
from resonate_sdk import Resonate, Promise

class CapabilityType(Enum):
    """Types of capabilities based on communication pattern."""
    SEND_ONLY = "send_only"           # Fire and forget (print, log)
    REQUEST_RESPONSE = "request_response"  # Wait for response (input, read)
    HITL = "human_in_the_loop"        # Human interaction required
    SCHEDULED = "scheduled"            # Delayed or periodic execution
    STREAMING = "streaming"            # Continuous data stream

class Capability(ABC):
    """
    Base class for all capabilities.
    
    Defines the interface that all capabilities must implement
    and provides common functionality for promise-based communication.
    """
    
    def __init__(
        self,
        resonate: Resonate,
        capability_type: CapabilityType,
        execution_id: str
    ):
        """
        Initialize capability.
        
        Args:
            resonate: Resonate instance for promises
            capability_type: Type of capability
            execution_id: Current execution context ID
        """
        self.resonate = resonate
        self.capability_type = capability_type
        self.execution_id = execution_id
        
        # Message queue for non-async contexts
        self._message_queue = []
        self._in_async_context = self._check_async_context()
        
        # Statistics
        self.stats = {
            "invocations": 0,
            "promises_created": 0,
            "promises_resolved": 0,
            "errors": 0
        }
    
    @abstractmethod
    def get_name(self) -> str:
        """Get capability name for injection."""
        pass
    
    @abstractmethod
    def get_implementation(self) -> Callable:
        """Get the callable implementation."""
        pass
    
    @abstractmethod
    def validate_arguments(self, *args, **kwargs) -> bool:
        """Validate arguments before execution."""
        pass
    
    def _check_async_context(self) -> bool:
        """Check if we're in an async context."""
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False
    
    def create_promise(
        self,
        operation: str,
        data: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> Promise:
        """
        Create a durable promise for this capability operation.
        
        Args:
            operation: Operation name
            data: Operation data
            timeout: Timeout in seconds
            
        Returns:
            Resonate promise
        """
        promise_id = f"{self.get_name()}:{self.execution_id}:{uuid.uuid4()}"
        
        promise_data = {
            "capability": self.get_name(),
            "operation": operation,
            "execution_id": self.execution_id,
            "timestamp": time.time(),
            "data": data
        }
        
        timeout_ms = int(timeout * 1000) if timeout else None
        
        promise = self.resonate.promises.create(
            id=promise_id,
            timeout=timeout_ms,
            data=json.dumps(promise_data),
            tags=[self.get_name(), operation, self.execution_id]
        )
        
        self.stats["promises_created"] += 1
        return promise
    
    def queue_if_needed(self, operation: Callable) -> Any:
        """
        Queue operation if not in async context.
        
        Prevents RuntimeError: no running event loop
        """
        if self._in_async_context:
            return operation()
        else:
            self._message_queue.append(operation)
            return None
    
    async def flush_queue(self) -> List[Any]:
        """Flush queued operations when entering async context."""
        if not self._message_queue:
            return []
            
        results = []
        for operation in self._message_queue:
            try:
                result = await operation() if asyncio.iscoroutinefunction(operation) else operation()
                results.append(result)
            except Exception as e:
                self.stats["errors"] += 1
                results.append(e)
                
        self._message_queue.clear()
        return results
```

## Core Capability Implementations

### Input Capability (HITL)

```python
class InputCapability(Capability):
    """
    Input capability using HITL promise pattern.
    
    Demonstrates human-in-the-loop workflow where
    external UI resolves the promise with user input.
    """
    
    def __init__(self, resonate: Resonate, execution_id: str):
        super().__init__(
            resonate=resonate,
            capability_type=CapabilityType.HITL,
            execution_id=execution_id
        )
        
    def get_name(self) -> str:
        return "input"
    
    def get_implementation(self) -> Callable:
        """Return the input function for namespace injection."""
        
        def input_impl(prompt: str = "") -> str:
            """
            Input implementation that creates HITL promise.
            
            This function is injected into the namespace and
            called from user code.
            """
            self.stats["invocations"] += 1
            
            # Validate prompt
            if not self.validate_arguments(prompt):
                raise ValueError("Invalid input prompt")
            
            # Create promise for input request
            promise = self.create_promise(
                operation="user_input",
                data={"prompt": prompt},
                timeout=300.0  # 5 minute timeout
            )
            
            # In a durable function context, this would return
            # the promise ID for the executor to await
            # For now, return a placeholder
            return f"PROMISE:{promise.id}"
        
        return input_impl
    
    def validate_arguments(self, prompt: str = "") -> bool:
        """Validate input arguments."""
        return isinstance(prompt, str) and len(prompt) < 1000
    
    async def resolve_input(self, promise_id: str, user_input: str):
        """
        Resolve input promise with user's response.
        
        Called by external UI when user provides input.
        """
        self.resonate.promises.resolve(
            id=promise_id,
            data=json.dumps({"input": user_input})
        )
        self.stats["promises_resolved"] += 1
```

### Print Capability (Send-Only)

```python
class PrintCapability(Capability):
    """
    Print capability for output display.
    
    Send-only pattern - no response expected.
    """
    
    def __init__(
        self,
        resonate: Resonate,
        execution_id: str,
        transport: 'MessageTransport'
    ):
        super().__init__(
            resonate=resonate,
            capability_type=CapabilityType.SEND_ONLY,
            execution_id=execution_id
        )
        self.transport = transport
        
    def get_name(self) -> str:
        return "print"
    
    def get_implementation(self) -> Callable:
        """Return print function for namespace injection."""
        
        def print_impl(*args, sep=' ', end='\n', file=None, flush=False):
            """
            Print implementation that sends to transport.
            
            Mimics built-in print() signature.
            """
            self.stats["invocations"] += 1
            
            # Convert args to string
            output = sep.join(str(arg) for arg in args) + end
            
            # Create message
            message = {
                "type": "output",
                "execution_id": self.execution_id,
                "data": output,
                "stream": "stdout" if file is None else str(file)
            }
            
            # Send or queue based on context
            def send_operation():
                return self.transport.send_message(message)
            
            self.queue_if_needed(send_operation)
            
        return print_impl
    
    def validate_arguments(self, *args, **kwargs) -> bool:
        """Validate print arguments."""
        return True  # Print accepts anything
```

### File Read Capability (Request-Response)

```python
class FileReadCapability(Capability):
    """
    File reading capability with promise-based response.
    
    Demonstrates request-response pattern where external
    file service resolves promise with file contents.
    """
    
    def __init__(self, resonate: Resonate, execution_id: str):
        super().__init__(
            resonate=resonate,
            capability_type=CapabilityType.REQUEST_RESPONSE,
            execution_id=execution_id
        )
        self.max_file_size = 10 * 1024 * 1024  # 10MB limit
        
    def get_name(self) -> str:
        return "read_file"
    
    def get_implementation(self) -> Callable:
        """Return file read function for namespace injection."""
        
        def read_file_impl(path: str, encoding: str = 'utf-8') -> str:
            """
            Read file implementation using promises.
            
            Creates promise that external service will resolve
            with file contents.
            """
            self.stats["invocations"] += 1
            
            # Validate arguments
            if not self.validate_arguments(path, encoding):
                raise ValueError("Invalid file path or encoding")
            
            # Create promise for file read
            promise = self.create_promise(
                operation="file_read",
                data={
                    "path": path,
                    "encoding": encoding
                },
                timeout=10.0  # 10 second timeout
            )
            
            # Return promise ID for resolution
            return f"PROMISE:{promise.id}"
        
        return read_file_impl
    
    def validate_arguments(self, path: str, encoding: str = 'utf-8') -> bool:
        """Validate file read arguments."""
        # Path validation
        if not isinstance(path, str) or not path:
            return False
            
        # Prevent directory traversal
        if ".." in path or path.startswith("/"):
            return False
            
        # Check encoding
        valid_encodings = {'utf-8', 'ascii', 'latin-1', 'utf-16'}
        if encoding not in valid_encodings:
            return False
            
        return True
```

### Network Fetch Capability

```python
class FetchCapability(Capability):
    """
    Network fetch capability for HTTP requests.
    
    Demonstrates async-aware capability with proper
    context handling.
    """
    
    def __init__(self, resonate: Resonate, execution_id: str):
        super().__init__(
            resonate=resonate,
            capability_type=CapabilityType.REQUEST_RESPONSE,
            execution_id=execution_id
        )
        self.allowed_schemes = {'http', 'https'}
        self.timeout = 30.0
        
    def get_name(self) -> str:
        return "fetch"
    
    def get_implementation(self) -> Callable:
        """Return fetch function for namespace injection."""
        
        async def fetch_impl(
            url: str,
            method: str = 'GET',
            headers: Optional[Dict] = None,
            body: Optional[str] = None
        ) -> Dict[str, Any]:
            """
            Async fetch implementation.
            
            Can be called with await in async code.
            """
            self.stats["invocations"] += 1
            
            # Validate URL
            if not self.validate_arguments(url, method):
                raise ValueError("Invalid URL or method")
            
            # Create promise for fetch
            promise = self.create_promise(
                operation="http_request",
                data={
                    "url": url,
                    "method": method,
                    "headers": headers or {},
                    "body": body
                },
                timeout=self.timeout
            )
            
            # In actual implementation, external service
            # performs request and resolves promise
            
            # For now, return promise ID
            return {"promise_id": promise.id}
        
        # Return async-aware wrapper
        return self._create_async_wrapper(fetch_impl)
    
    def _create_async_wrapper(self, async_func: Callable) -> Callable:
        """Create wrapper that works in both sync and async contexts."""
        
        def wrapper(*args, **kwargs):
            if self._in_async_context:
                # In async context, return coroutine
                return async_func(*args, **kwargs)
            else:
                # In sync context, queue for later
                self._message_queue.append(
                    lambda: async_func(*args, **kwargs)
                )
                return {"queued": True}
        
        wrapper.__name__ = async_func.__name__
        wrapper.__doc__ = async_func.__doc__
        return wrapper
    
    def validate_arguments(self, url: str, method: str = 'GET') -> bool:
        """Validate fetch arguments."""
        from urllib.parse import urlparse
        
        # Parse URL
        try:
            parsed = urlparse(url)
        except Exception:
            return False
            
        # Check scheme
        if parsed.scheme not in self.allowed_schemes:
            return False
            
        # Check method
        valid_methods = {'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD'}
        if method.upper() not in valid_methods:
            return False
            
        return True
```

## Capability Registry

### Registry Implementation

```python
class CapabilityRegistry:
    """
    Central registry for all capabilities.
    
    Manages capability lifecycle and provides
    lookup and injection services.
    """
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        self._capabilities: Dict[str, type] = {}
        self._instances: Dict[str, Capability] = {}
        self._security_policy: Optional['SecurityPolicy'] = None
        
    def register_capability(
        self,
        capability_class: type,
        name: Optional[str] = None
    ):
        """
        Register a capability class.
        
        Args:
            capability_class: Capability class to register
            name: Optional name override
        """
        if not issubclass(capability_class, Capability):
            raise TypeError("Must be a Capability subclass")
            
        name = name or capability_class.__name__.lower().replace('capability', '')
        self._capabilities[name] = capability_class
        
        # Register with Resonate as dependency
        self.resonate.set_dependency(
            f"capability_{name}",
            capability_class,
            singleton=False  # New instance per execution
        )
    
    def get_capability(
        self,
        name: str,
        execution_id: str
    ) -> Optional[Capability]:
        """
        Get capability instance if allowed by security policy.
        
        Args:
            name: Capability name
            execution_id: Execution context ID
            
        Returns:
            Capability instance or None if not allowed
        """
        # Check security policy
        if self._security_policy and not self._security_policy.is_allowed(name):
            return None
            
        # Check if registered
        if name not in self._capabilities:
            return None
            
        # Create or get instance
        instance_key = f"{name}:{execution_id}"
        if instance_key not in self._instances:
            capability_class = self._capabilities[name]
            self._instances[instance_key] = capability_class(
                resonate=self.resonate,
                execution_id=execution_id
            )
            
        return self._instances[instance_key]
    
    def inject_capabilities(
        self,
        namespace: Dict[str, Any],
        execution_id: str,
        security_policy: 'SecurityPolicy'
    ) -> Dict[str, Any]:
        """
        Inject allowed capabilities into namespace.
        
        Args:
            namespace: Target namespace
            execution_id: Execution context
            security_policy: Security policy to apply
            
        Returns:
            Updated namespace
        """
        self._security_policy = security_policy
        
        for name in self._capabilities:
            if security_policy.is_allowed(name):
                capability = self.get_capability(name, execution_id)
                if capability:
                    # Inject implementation into namespace
                    namespace[name] = capability.get_implementation()
                    
        return namespace
    
    def cleanup(self, execution_id: str):
        """Clean up capability instances for execution."""
        keys_to_remove = [
            key for key in self._instances
            if key.endswith(f":{execution_id}")
        ]
        
        for key in keys_to_remove:
            del self._instances[key]
```

### Standard Capability Set

```python
def register_standard_capabilities(registry: CapabilityRegistry):
    """Register the standard set of capabilities."""
    
    # I/O Capabilities
    registry.register_capability(InputCapability, "input")
    registry.register_capability(PrintCapability, "print")
    registry.register_capability(DisplayCapability, "display")
    
    # File Capabilities
    registry.register_capability(FileReadCapability, "read_file")
    registry.register_capability(FileWriteCapability, "write_file")
    registry.register_capability(FileListCapability, "list_files")
    
    # Network Capabilities
    registry.register_capability(FetchCapability, "fetch")
    registry.register_capability(WebSocketCapability, "websocket")
    
    # Data Capabilities
    registry.register_capability(QueryCapability, "query")
    registry.register_capability(StoreCapability, "store")
    
    # System Capabilities
    registry.register_capability(EnvironmentCapability, "env")
    registry.register_capability(TimeCapability, "time")
    
    # HITL Capabilities
    registry.register_capability(ApprovalCapability, "approve")
    registry.register_capability(ReviewCapability, "review")
```

## Security Policy System

### Security Policy Implementation

```python
from enum import Enum
from typing import Set, Dict, Any, Callable, Optional

class SecurityLevel(Enum):
    """Pre-defined security levels."""
    SANDBOX = "sandbox"           # Minimal capabilities
    RESTRICTED = "restricted"      # Local I/O only
    STANDARD = "standard"         # Network + I/O
    TRUSTED = "trusted"          # Most capabilities
    UNRESTRICTED = "unrestricted"  # All capabilities

class SecurityPolicy:
    """
    Capability-level security policy.
    
    Critical insight: Enforce at injection, not execution.
    Code-level preprocessing doesn't work.
    """
    
    # Pre-defined capability sets
    CAPABILITY_SETS = {
        SecurityLevel.SANDBOX: {
            'print',     # Output only
            'display',   # Rich display
        },
        SecurityLevel.RESTRICTED: {
            'print', 'display', 'input',  # Basic I/O
            'read_file',                   # Read only
            'time', 'env',                 # System info
        },
        SecurityLevel.STANDARD: {
            'print', 'display', 'input',
            'read_file', 'write_file',     # File I/O
            'fetch',                        # Network read
            'query',                        # Data query
            'time', 'env',
        },
        SecurityLevel.TRUSTED: {
            'print', 'display', 'input',
            'read_file', 'write_file',
            'fetch', 'websocket',           # Full network
            'query', 'store',               # Data operations
            'approve', 'review',            # HITL workflows
            'time', 'env',
        },
        SecurityLevel.UNRESTRICTED: '*'    # Everything
    }
    
    def __init__(
        self,
        level: SecurityLevel = SecurityLevel.STANDARD,
        custom_allowed: Optional[Set[str]] = None,
        custom_blocked: Optional[Set[str]] = None
    ):
        """
        Initialize security policy.
        
        Args:
            level: Base security level
            custom_allowed: Additional allowed capabilities
            custom_blocked: Explicitly blocked capabilities
        """
        self.level = level
        self._base_allowed = self._get_base_capabilities()
        self._custom_allowed = custom_allowed or set()
        self._blocked = custom_blocked or set()
        
        # Runtime validators for specific capabilities
        self._validators: Dict[str, Callable] = {}
        
        # Audit log
        self._audit_log = []
        
    def _get_base_capabilities(self) -> Set[str]:
        """Get base capability set for security level."""
        capabilities = self.CAPABILITY_SETS.get(self.level, set())
        
        if capabilities == '*':
            return {'*'}  # Special case for unrestricted
        else:
            return set(capabilities)
    
    def is_allowed(self, capability_name: str) -> bool:
        """
        Check if capability is allowed.
        
        Order of precedence:
        1. Explicitly blocked → False
        2. Unrestricted level → True
        3. In allowed set → True
        4. Default → False
        """
        # Log access attempt
        self._audit_log.append({
            "timestamp": time.time(),
            "capability": capability_name,
            "action": "access_check"
        })
        
        # Check explicit blocks
        if capability_name in self._blocked:
            return False
            
        # Check unrestricted
        if '*' in self._base_allowed:
            return True
            
        # Check allowed sets
        if capability_name in self._base_allowed:
            return True
            
        if capability_name in self._custom_allowed:
            return True
            
        return False
    
    def add_validator(
        self,
        capability_name: str,
        validator: Callable[[Any], bool]
    ):
        """
        Add runtime validator for capability.
        
        Validators are called when capability is invoked
        to provide additional runtime checks.
        """
        self._validators[capability_name] = validator
    
    def validate_invocation(
        self,
        capability_name: str,
        args: tuple,
        kwargs: dict
    ) -> bool:
        """
        Validate capability invocation at runtime.
        
        Returns True if invocation is allowed.
        """
        if capability_name in self._validators:
            validator = self._validators[capability_name]
            return validator(*args, **kwargs)
        return True
    
    def get_audit_log(self) -> List[Dict]:
        """Get audit log of capability access."""
        return list(self._audit_log)
```

### Dynamic Policy Updates

```python
class DynamicSecurityPolicy(SecurityPolicy):
    """
    Security policy that can be updated at runtime.
    
    Useful for adjusting permissions based on
    execution context or user actions.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._policy_versions = []
        self._save_version()
        
    def _save_version(self):
        """Save current policy state."""
        self._policy_versions.append({
            "timestamp": time.time(),
            "level": self.level,
            "allowed": set(self._base_allowed),
            "custom_allowed": set(self._custom_allowed),
            "blocked": set(self._blocked)
        })
    
    def elevate_temporarily(
        self,
        new_level: SecurityLevel,
        duration: float = 60.0
    ):
        """
        Temporarily elevate security level.
        
        Args:
            new_level: New security level
            duration: Duration in seconds
        """
        original_level = self.level
        self.level = new_level
        self._base_allowed = self._get_base_capabilities()
        self._save_version()
        
        # Schedule reversion
        def revert():
            self.level = original_level
            self._base_allowed = self._get_base_capabilities()
            self._save_version()
            
        # In production, use proper scheduling
        import threading
        timer = threading.Timer(duration, revert)
        timer.start()
    
    def grant_capability(self, capability_name: str):
        """Grant a specific capability."""
        self._custom_allowed.add(capability_name)
        self._blocked.discard(capability_name)
        self._save_version()
    
    def revoke_capability(self, capability_name: str):
        """Revoke a specific capability."""
        self._blocked.add(capability_name)
        self._custom_allowed.discard(capability_name)
        self._save_version()
```

## Message Transport Bridge

### Async/Sync Context Handling

```python
class MessageTransport:
    """
    Handles message transport with async/sync bridging.
    
    Critical requirement: Queue messages when not in async context
    to prevent RuntimeError: no running event loop
    """
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        self._message_queue = []
        self._in_async_context = False
        
    def send_message(self, message: Dict[str, Any]) -> Optional[str]:
        """
        Send or queue message based on context.
        
        Returns message ID if sent, None if queued.
        """
        try:
            # Check if we're in async context
            loop = asyncio.get_running_loop()
            self._in_async_context = True
            
            # Can send immediately
            return self._send_immediate(message)
            
        except RuntimeError:
            # No event loop, queue for later
            self._in_async_context = False
            self._message_queue.append(message)
            return None
    
    def _send_immediate(self, message: Dict[str, Any]) -> str:
        """Send message immediately."""
        message_id = str(uuid.uuid4())
        message["id"] = message_id
        message["timestamp"] = time.time()
        
        # In production, send to actual transport
        # For now, create a promise
        self.resonate.promises.create(
            id=f"message:{message_id}",
            data=json.dumps(message),
            tags=["message", message.get("type", "unknown")]
        )
        
        return message_id
    
    async def flush_queue(self) -> List[str]:
        """
        Flush queued messages when entering async context.
        
        Returns list of message IDs.
        """
        if not self._message_queue:
            return []
            
        self._in_async_context = True
        message_ids = []
        
        for message in self._message_queue:
            message_id = self._send_immediate(message)
            message_ids.append(message_id)
            
        self._message_queue.clear()
        return message_ids
```

## HITL Workflow Support

### HITL Workflow Manager

```python
class HITLWorkflowManager:
    """
    Manages human-in-the-loop workflows.
    
    Coordinates between capabilities and external UI
    for human interactions.
    """
    
    def __init__(self, resonate: Resonate):
        self.resonate = resonate
        self._active_workflows = {}
        
    def create_hitl_workflow(
        self,
        workflow_type: str,
        execution_id: str,
        data: Dict[str, Any],
        participants: List[str],
        timeout: float = 3600.0
    ) -> str:
        """
        Create a new HITL workflow.
        
        Args:
            workflow_type: Type of workflow (approval, review, input)
            execution_id: Execution context
            data: Workflow data
            participants: List of participants
            timeout: Timeout in seconds
            
        Returns:
            Workflow ID
        """
        workflow_id = f"hitl:{workflow_type}:{execution_id}:{uuid.uuid4()}"
        
        # Create promise for workflow
        promise = self.resonate.promises.create(
            id=workflow_id,
            timeout=int(timeout * 1000),
            data=json.dumps({
                "type": workflow_type,
                "execution_id": execution_id,
                "data": data,
                "participants": participants,
                "status": "pending",
                "created_at": time.time()
            }),
            tags=["hitl", workflow_type, execution_id]
        )
        
        # Track workflow
        self._active_workflows[workflow_id] = {
            "promise": promise,
            "type": workflow_type,
            "participants": participants,
            "responses": {}
        }
        
        # Notify participants (external system)
        self._notify_participants(workflow_id, participants, data)
        
        return workflow_id
    
    def _notify_participants(
        self,
        workflow_id: str,
        participants: List[str],
        data: Dict[str, Any]
    ):
        """Notify participants about workflow."""
        # In production, send notifications via email, Slack, etc.
        pass
    
    async def wait_for_response(
        self,
        workflow_id: str
    ) -> Dict[str, Any]:
        """
        Wait for workflow completion.
        
        Blocks until workflow is resolved or times out.
        """
        if workflow_id not in self._active_workflows:
            raise ValueError(f"Unknown workflow: {workflow_id}")
            
        workflow = self._active_workflows[workflow_id]
        promise = workflow["promise"]
        
        # Wait for promise resolution
        result = await promise.result()
        
        # Parse result
        response_data = json.loads(result)
        
        # Clean up
        del self._active_workflows[workflow_id]
        
        return response_data
    
    def submit_response(
        self,
        workflow_id: str,
        participant: str,
        response: Dict[str, Any]
    ):
        """
        Submit participant response to workflow.
        
        Called by external UI when participant responds.
        """
        if workflow_id not in self._active_workflows:
            raise ValueError(f"Unknown workflow: {workflow_id}")
            
        workflow = self._active_workflows[workflow_id]
        workflow["responses"][participant] = response
        
        # Check if all responses received
        if set(workflow["responses"].keys()) == set(workflow["participants"]):
            # All responses received, resolve promise
            self.resonate.promises.resolve(
                id=workflow_id,
                data=json.dumps({
                    "status": "completed",
                    "responses": workflow["responses"],
                    "completed_at": time.time()
                })
            )
```

## Testing Strategies

### Unit Tests

```python
import pytest
from unittest.mock import Mock, MagicMock

def test_capability_injection():
    """Test capability injection into namespace."""
    resonate = Resonate.local()
    registry = CapabilityRegistry(resonate)
    
    # Register test capability
    class TestCapability(Capability):
        def get_name(self):
            return "test"
        
        def get_implementation(self):
            return lambda: "test_result"
        
        def validate_arguments(self, *args, **kwargs):
            return True
    
    registry.register_capability(TestCapability)
    
    # Create namespace and inject
    namespace = {}
    policy = SecurityPolicy(SecurityLevel.UNRESTRICTED)
    registry.inject_capabilities(namespace, "test-exec", policy)
    
    # Verify injection
    assert "test" in namespace
    assert namespace["test"]() == "test_result"

def test_security_policy_enforcement():
    """Test security policy blocks capabilities."""
    resonate = Resonate.local()
    registry = CapabilityRegistry(resonate)
    
    # Register capabilities
    registry.register_capability(PrintCapability)
    registry.register_capability(FileWriteCapability)
    
    # Restrictive policy
    namespace = {}
    policy = SecurityPolicy(SecurityLevel.SANDBOX)
    registry.inject_capabilities(namespace, "test-exec", policy)
    
    # Print should be allowed
    assert "print" in namespace
    
    # File write should be blocked
    assert "write_file" not in namespace

@pytest.mark.asyncio
async def test_message_queue_flushing():
    """Test message queuing in non-async context."""
    resonate = Resonate.local()
    transport = MessageTransport(resonate)
    
    # Send message in non-async context (will queue)
    message_id = transport.send_message({"type": "test"})
    assert message_id is None  # Queued
    assert len(transport._message_queue) == 1
    
    # Flush in async context
    message_ids = await transport.flush_queue()
    assert len(message_ids) == 1
    assert len(transport._message_queue) == 0

def test_capability_validation():
    """Test capability argument validation."""
    resonate = Resonate.local()
    cap = FileReadCapability(resonate, "test-exec")
    
    # Valid arguments
    assert cap.validate_arguments("file.txt", "utf-8")
    
    # Invalid path (directory traversal)
    assert not cap.validate_arguments("../file.txt", "utf-8")
    
    # Invalid encoding
    assert not cap.validate_arguments("file.txt", "invalid-encoding")
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_hitl_workflow():
    """Test human-in-the-loop workflow."""
    resonate = Resonate.local()
    manager = HITLWorkflowManager(resonate)
    
    # Create approval workflow
    workflow_id = manager.create_hitl_workflow(
        workflow_type="approval",
        execution_id="test-exec",
        data={"action": "delete_file", "path": "important.txt"},
        participants=["user1", "user2"],
        timeout=60.0
    )
    
    # Simulate participant responses
    manager.submit_response(workflow_id, "user1", {"approved": True})
    manager.submit_response(workflow_id, "user2", {"approved": True})
    
    # Wait for completion
    result = await manager.wait_for_response(workflow_id)
    
    assert result["status"] == "completed"
    assert len(result["responses"]) == 2

@pytest.mark.asyncio
async def test_capability_promise_resolution():
    """Test capability using promise resolution."""
    resonate = Resonate.local()
    cap = InputCapability(resonate, "test-exec")
    
    # Get implementation
    input_func = cap.get_implementation()
    
    # Call input (creates promise)
    result = input_func("Enter name: ")
    assert result.startswith("PROMISE:")
    
    # Extract promise ID
    promise_id = result.replace("PROMISE:", "")
    
    # Simulate external resolution
    await cap.resolve_input(promise_id, "Test User")
    
    # Verify promise resolved
    promise = resonate.promises.get(promise_id)
    assert promise.state == "resolved"
```

## Performance Considerations

### Capability Caching

```python
class CachedCapabilityRegistry(CapabilityRegistry):
    """Registry with capability instance caching."""
    
    def __init__(self, resonate: Resonate):
        super().__init__(resonate)
        self._cache_ttl = 300  # 5 minutes
        self._cache_timestamps = {}
        
    def get_capability(
        self,
        name: str,
        execution_id: str
    ) -> Optional[Capability]:
        """Get capability with caching."""
        instance_key = f"{name}:{execution_id}"
        
        # Check cache validity
        if instance_key in self._instances:
            timestamp = self._cache_timestamps.get(instance_key, 0)
            if time.time() - timestamp < self._cache_ttl:
                # Cache hit
                return self._instances[instance_key]
            else:
                # Cache expired
                del self._instances[instance_key]
                del self._cache_timestamps[instance_key]
        
        # Cache miss, create new instance
        capability = super().get_capability(name, execution_id)
        if capability:
            self._cache_timestamps[instance_key] = time.time()
            
        return capability
```

### Promise Batching

```python
class BatchedPromiseCapability(Capability):
    """Capability that batches promise operations."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._promise_batch = []
        self._batch_size = 10
        self._flush_interval = 0.1  # 100ms
        self._last_flush = time.time()
        
    def create_promise(self, *args, **kwargs) -> Promise:
        """Create promise with batching."""
        promise_config = {
            "args": args,
            "kwargs": kwargs
        }
        
        self._promise_batch.append(promise_config)
        
        if self._should_flush():
            return self._flush_batch()[-1]
        else:
            # Return placeholder
            return Mock(id=f"pending_{len(self._promise_batch)}")
    
    def _should_flush(self) -> bool:
        """Check if batch should be flushed."""
        if len(self._promise_batch) >= self._batch_size:
            return True
        if time.time() - self._last_flush > self._flush_interval:
            return True
        return False
    
    def _flush_batch(self) -> List[Promise]:
        """Flush promise batch."""
        if not self._promise_batch:
            return []
            
        # Create all promises at once
        promises = []
        for config in self._promise_batch:
            promise = super().create_promise(
                *config["args"],
                **config["kwargs"]
            )
            promises.append(promise)
            
        self._promise_batch.clear()
        self._last_flush = time.time()
        
        return promises
```

## Security Best Practices

### Capability Sandboxing

```python
class SandboxedCapability(Capability):
    """Base class for sandboxed capabilities."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resource_limits = {
            "max_memory": 100 * 1024 * 1024,  # 100MB
            "max_cpu_time": 5.0,  # 5 seconds
            "max_operations": 1000
        }
        self._resource_usage = {
            "memory": 0,
            "cpu_time": 0,
            "operations": 0
        }
    
    def check_resource_limits(self):
        """Check if resource limits exceeded."""
        if self._resource_usage["memory"] > self._resource_limits["max_memory"]:
            raise ResourceError("Memory limit exceeded")
        if self._resource_usage["cpu_time"] > self._resource_limits["max_cpu_time"]:
            raise ResourceError("CPU time limit exceeded")
        if self._resource_usage["operations"] > self._resource_limits["max_operations"]:
            raise ResourceError("Operation limit exceeded")
    
    def track_operation(self):
        """Track resource usage for operation."""
        self._resource_usage["operations"] += 1
        self.check_resource_limits()
```

### Input Sanitization

```python
class InputSanitizer:
    """Sanitize inputs for capabilities."""
    
    @staticmethod
    def sanitize_path(path: str) -> str:
        """Sanitize file path."""
        # Remove dangerous characters
        path = path.replace("\0", "")
        path = path.replace("\n", "")
        path = path.replace("\r", "")
        
        # Normalize path
        import os
        path = os.path.normpath(path)
        
        # Check for directory traversal
        if ".." in path or path.startswith("/"):
            raise ValueError("Invalid path")
            
        return path
    
    @staticmethod
    def sanitize_url(url: str) -> str:
        """Sanitize URL."""
        from urllib.parse import urlparse, urlunparse
        
        parsed = urlparse(url)
        
        # Check scheme
        if parsed.scheme not in ['http', 'https']:
            raise ValueError("Invalid URL scheme")
            
        # Rebuild URL
        return urlunparse(parsed)
```

## Future Enhancements

### Planned Capabilities

1. **GraphQLCapability**: GraphQL query execution
2. **SQLCapability**: Database queries with parameterization
3. **StreamCapability**: Real-time data streaming
4. **NotificationCapability**: Send notifications
5. **ScheduleCapability**: Scheduled task execution

### Advanced Features

1. **Capability Composition**: Combine capabilities
2. **Capability Versioning**: Multiple versions coexist
3. **Capability Metrics**: Performance tracking
4. **Capability Discovery**: Runtime capability detection

## Appendices

### A. Capability Type Matrix

| Capability | Type | Uses Promises | HITL | Async-Aware |
|-----------|------|---------------|------|-------------|
| print | Send-Only | No | No | Yes |
| input | HITL | Yes | Yes | Yes |
| read_file | Request-Response | Yes | No | Yes |
| write_file | Request-Response | Yes | No | Yes |
| fetch | Request-Response | Yes | No | Yes |
| websocket | Streaming | Yes | No | Yes |
| approve | HITL | Yes | Yes | Yes |

### B. Security Level Comparison

| Level | File I/O | Network | HITL | Database |
|-------|----------|---------|------|----------|
| SANDBOX | No | No | No | No |
| RESTRICTED | Read Only | No | Input Only | No |
| STANDARD | Full | Read Only | Input Only | Read Only |
| TRUSTED | Full | Full | Full | Full |
| UNRESTRICTED | Full | Full | Full | Full |

### C. Promise Resolution Patterns

1. **Immediate**: Resolve synchronously if possible
2. **Deferred**: Queue for later resolution
3. **External**: Wait for external system
4. **Timeout**: Auto-reject after timeout
5. **Cascading**: Trigger other promise resolutions
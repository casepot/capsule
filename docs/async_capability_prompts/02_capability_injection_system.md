# Capability Injection System Planning Prompt

## Your Mission

You are tasked with extending the NamespaceManager to support a comprehensive capability injection system. This system will allow dynamic injection of protocol-bridged functions into the execution namespace, enabling controlled access to I/O, network, filesystem, and custom operations. The goal is to create a flexible, secure, and extensible platform where capabilities can be granted based on security policies.

## Context Gathering Requirements

Before implementing, you MUST understand:

### 1. Current State
- **NamespaceManager**: Located at `src/subprocess/namespace.py`
- **What It Has**: Basic namespace management, transactions, source tracking
- **What It Lacks**: No capability injection, no protocol bridging, no security policies
- **Fixed Pattern**: Currently only hardcoded input() override

### 2. Target Architecture
- **Dynamic Injection**: Register and inject capabilities at runtime
- **Protocol Bridging**: Capabilities communicate via message protocol
- **Security Policies**: Control which capabilities are available
- **Extensibility**: Plugin system for custom capabilities

### 3. Files to Create/Modify
- **EXTEND**: `src/subprocess/namespace.py` with capability methods
- **CREATE**: `src/subprocess/capabilities.py` for capability definitions
- **CREATE**: `src/subprocess/capability_registry.py` for management
- **CREATE**: `src/subprocess/security_policy.py` for access control

## Planning Methodology

### Phase 1: Analysis (30% effort)
<context_gathering>
Goal: Understand capability-based security models
Stop when: You understand how to bridge Python functions to protocol messages
Depth: Study dependency injection patterns, capability security models
</context_gathering>

Investigate:
1. How to create protocol-aware Python functions
2. Security implications of namespace injection
3. Async vs sync capability implementations
4. Plugin architectures for extensibility

### Phase 2: Solution Design (50% effort)

**Core Capability System Design:**

```python
# src/subprocess/capabilities.py
from typing import Any, Callable, Dict, List, Optional
import asyncio
import uuid
from abc import ABC, abstractmethod

class Capability(ABC):
    """Base class for all capabilities."""
    
    def __init__(self, transport: MessageTransport):
        self.transport = transport
        self._pending_requests: Dict[str, asyncio.Future] = {}
    
    @abstractmethod
    def get_name(self) -> str:
        """Return capability name for namespace injection."""
        pass
    
    @abstractmethod
    def get_implementation(self) -> Callable:
        """Return the callable to inject into namespace."""
        pass
    
    def get_metadata(self) -> Dict[str, Any]:
        """Return capability metadata."""
        return {
            'type': self.__class__.__name__,
            'async': asyncio.iscoroutinefunction(self.get_implementation()),
            'protocol_bridged': True
        }

class InputCapability(Capability):
    """Protocol-bridged input capability."""
    
    def get_name(self) -> str:
        return 'input'
    
    def get_implementation(self) -> Callable:
        async def async_input(prompt: str = "") -> str:
            """Async input via protocol."""
            request_id = str(uuid.uuid4())
            
            # Send INPUT_REQUEST
            await self.transport.send_message(InputRequestMessage(
                id=request_id,
                prompt=prompt,
                timeout=30.0
            ))
            
            # Create future for response
            future = asyncio.Future()
            self._pending_requests[request_id] = future
            
            try:
                # Wait for response
                response = await asyncio.wait_for(future, timeout=30.0)
                return response
            finally:
                self._pending_requests.pop(request_id, None)
        
        return async_input
    
    async def handle_response(self, message: InputResponseMessage):
        """Handle input response from protocol."""
        if message.request_id in self._pending_requests:
            self._pending_requests[message.request_id].set_result(message.value)

class DisplayCapability(Capability):
    """Rich display capability."""
    
    def get_name(self) -> str:
        return 'display'
    
    def get_implementation(self) -> Callable:
        async def display(obj: Any, **options) -> None:
            """Display object with rich formatting."""
            display_id = str(uuid.uuid4())
            
            # Auto-detect mime type
            mime_type, data = self._process_object(obj, options)
            
            # Send DISPLAY message
            await self.transport.send_message(DisplayMessage(
                id=display_id,
                mime_type=mime_type,
                data=data,
                metadata=options
            ))
        
        return display
    
    def _process_object(self, obj: Any, options: Dict) -> tuple[str, Any]:
        """Process object for display."""
        if hasattr(obj, '_repr_html_'):
            return 'text/html', obj._repr_html_()
        elif hasattr(obj, '_repr_png_'):
            return 'image/png', obj._repr_png_()
        elif hasattr(obj, '_repr_json_'):
            return 'application/json', obj._repr_json_()
        else:
            return 'text/plain', str(obj)

class FetchCapability(Capability):
    """Network fetch capability."""
    
    def get_name(self) -> str:
        return 'fetch'
    
    def get_implementation(self) -> Callable:
        async def fetch(url: str, **options) -> Dict:
            """Fetch URL via protocol (sandboxed)."""
            request_id = str(uuid.uuid4())
            
            # Send HTTP_REQUEST
            await self.transport.send_message(HttpRequestMessage(
                id=request_id,
                url=url,
                method=options.get('method', 'GET'),
                headers=options.get('headers'),
                body=options.get('body')
            ))
            
            # Wait for response
            future = asyncio.Future()
            self._pending_requests[request_id] = future
            
            try:
                response = await asyncio.wait_for(future, timeout=30.0)
                return {
                    'status': response.status,
                    'headers': response.headers,
                    'body': response.body,
                    'json': lambda: json.loads(response.body)
                }
            finally:
                self._pending_requests.pop(request_id, None)
        
        return fetch

class QueryCapability(Capability):
    """Database query capability."""
    
    def get_name(self) -> str:
        return 'query'
    
    def get_implementation(self) -> Callable:
        async def query(sql: str, params: Optional[List] = None) -> List[Dict]:
            """Execute SQL query via protocol."""
            request_id = str(uuid.uuid4())
            
            # Send QUERY_REQUEST
            await self.transport.send_message(QueryRequestMessage(
                id=request_id,
                sql=sql,
                params=params
            ))
            
            # Wait for results
            future = asyncio.Future()
            self._pending_requests[request_id] = future
            
            try:
                results = await asyncio.wait_for(future, timeout=60.0)
                return results
            finally:
                self._pending_requests.pop(request_id, None)
        
        return query
```

**Capability Registry:**

```python
# src/subprocess/capability_registry.py
class CapabilityRegistry:
    """Registry for managing capabilities."""
    
    def __init__(self):
        self._capabilities: Dict[str, Type[Capability]] = {}
        self._instances: Dict[str, Capability] = {}
        self._bundles: Dict[str, CapabilityBundle] = {}
    
    def register_capability(self, capability_class: Type[Capability]):
        """Register a capability class."""
        cap_name = capability_class().get_name()
        self._capabilities[cap_name] = capability_class
    
    def register_bundle(self, name: str, bundle: CapabilityBundle):
        """Register a bundle of related capabilities."""
        self._bundles[name] = bundle
    
    def create_instance(self, name: str, transport: MessageTransport) -> Capability:
        """Create capability instance."""
        if name not in self._capabilities:
            raise KeyError(f"Unknown capability: {name}")
        
        if name not in self._instances:
            self._instances[name] = self._capabilities[name](transport)
        
        return self._instances[name]
    
    def get_bundle_capabilities(self, bundle_name: str) -> List[str]:
        """Get capability names in a bundle."""
        if bundle_name not in self._bundles:
            raise KeyError(f"Unknown bundle: {bundle_name}")
        return self._bundles[bundle_name].capability_names

class CapabilityBundle:
    """Bundle of related capabilities."""
    
    def __init__(self, name: str, capabilities: List[str]):
        self.name = name
        self.capability_names = capabilities

# Pre-defined bundles
BASIC_IO_BUNDLE = CapabilityBundle('basic_io', ['input', 'display', 'print'])
NETWORK_BUNDLE = CapabilityBundle('network', ['fetch', 'websocket', 'tcp'])
FILE_BUNDLE = CapabilityBundle('files', ['read_file', 'write_file', 'list_dir'])
DATA_BUNDLE = CapabilityBundle('data', ['query', 'load_dataset', 'save_data'])
```

**Enhanced NamespaceManager:**

```python
# Extensions to src/subprocess/namespace.py
class NamespaceManager:
    # ... existing code ...
    
    def __init__(self):
        # ... existing init ...
        self._capabilities: Dict[str, Capability] = {}
        self._capability_registry = CapabilityRegistry()
        self._security_policy: Optional[SecurityPolicy] = None
    
    def set_security_policy(self, policy: SecurityPolicy):
        """Set security policy for capability control."""
        self._security_policy = policy
    
    def inject_capability(
        self, 
        name: str, 
        capability: Optional[Capability] = None,
        override: bool = False
    ):
        """Inject a capability into the namespace.
        
        Args:
            name: Name to bind in namespace
            capability: Capability instance (or create from registry)
            override: Whether to override existing binding
        """
        # Check security policy
        if self._security_policy and not self._security_policy.is_allowed(name):
            raise SecurityError(f"Capability '{name}' not allowed by security policy")
        
        # Check for existing binding
        if name in self._namespace and not override:
            raise ValueError(f"'{name}' already exists in namespace")
        
        # Get or create capability
        if capability is None:
            capability = self._capability_registry.create_instance(name, self.transport)
        
        # Store and inject
        self._capabilities[name] = capability
        self._namespace[name] = capability.get_implementation()
        
        logger.info(
            "Injected capability",
            name=name,
            type=capability.__class__.__name__,
            metadata=capability.get_metadata()
        )
    
    def inject_bundle(self, bundle_name: str):
        """Inject all capabilities in a bundle."""
        cap_names = self._capability_registry.get_bundle_capabilities(bundle_name)
        
        for cap_name in cap_names:
            try:
                self.inject_capability(cap_name)
            except SecurityError:
                logger.warning(f"Skipping {cap_name} due to security policy")
    
    def inject_standard_capabilities(self, transport: MessageTransport):
        """Inject standard set of capabilities based on security level."""
        self.transport = transport
        
        # Always inject basic I/O
        self.inject_capability('input', InputCapability(transport))
        self.inject_capability('display', DisplayCapability(transport))
        
        # Conditional injection based on security
        if self._security_policy:
            if self._security_policy.allow_network:
                self.inject_capability('fetch', FetchCapability(transport))
            
            if self._security_policy.allow_filesystem:
                self.inject_bundle('files')
            
            if self._security_policy.allow_database:
                self.inject_capability('query', QueryCapability(transport))
    
    def remove_capability(self, name: str):
        """Remove an injected capability."""
        if name in self._capabilities:
            del self._capabilities[name]
            del self._namespace[name]
            logger.info(f"Removed capability: {name}")
    
    def list_capabilities(self) -> List[Dict[str, Any]]:
        """List all injected capabilities."""
        return [
            {
                'name': name,
                'type': cap.__class__.__name__,
                'metadata': cap.get_metadata()
            }
            for name, cap in self._capabilities.items()
        ]
```

**Security Policy:**

```python
# src/subprocess/security_policy.py
from enum import Enum
from typing import Set, Optional

class SecurityLevel(Enum):
    SANDBOX = "sandbox"      # Minimal capabilities
    RESTRICTED = "restricted"  # Some I/O, no network
    STANDARD = "standard"     # Normal operations
    TRUSTED = "trusted"       # Most capabilities
    ADMIN = "admin"          # All capabilities

class SecurityPolicy:
    """Security policy for capability control."""
    
    # Capability sets by security level
    CAPABILITY_SETS = {
        SecurityLevel.SANDBOX: {'input', 'display', 'print'},
        SecurityLevel.RESTRICTED: {'input', 'display', 'print', 'read_file'},
        SecurityLevel.STANDARD: {'input', 'display', 'print', 'read_file', 'write_file', 'fetch'},
        SecurityLevel.TRUSTED: {'input', 'display', 'print', 'read_file', 'write_file', 'fetch', 'query'},
        SecurityLevel.ADMIN: '*'  # All capabilities
    }
    
    def __init__(self, level: SecurityLevel = SecurityLevel.STANDARD):
        self.level = level
        self._allowed_capabilities = self._compute_allowed()
        self._denied_capabilities: Set[str] = set()
        
    def _compute_allowed(self) -> Set[str]:
        """Compute allowed capabilities based on level."""
        cap_set = self.CAPABILITY_SETS.get(self.level, set())
        if cap_set == '*':
            return None  # All allowed
        return cap_set
    
    def is_allowed(self, capability_name: str) -> bool:
        """Check if capability is allowed."""
        if capability_name in self._denied_capabilities:
            return False
        if self._allowed_capabilities is None:  # Admin
            return True
        return capability_name in self._allowed_capabilities
    
    def deny(self, capability_name: str):
        """Explicitly deny a capability."""
        self._denied_capabilities.add(capability_name)
    
    def allow(self, capability_name: str):
        """Explicitly allow a capability."""
        if self._allowed_capabilities is not None:
            self._allowed_capabilities.add(capability_name)
```

### Phase 3: Risk Assessment (20% effort)

- **Risk**: Capability name conflicts
  - Mitigation: Override parameter, namespacing
  
- **Risk**: Security bypass via injection
  - Mitigation: Security policy enforcement
  
- **Risk**: Protocol message correlation
  - Mitigation: Request ID tracking

## Output Requirements

Your implementation must include:

### 1. Executive Summary
- Benefits of capability injection over hardcoded overrides
- Security model overview
- Extensibility patterns
- Migration from current input() override

### 2. Test Plan

```python
async def test_capability_injection():
    """Test basic capability injection."""
    namespace = NamespaceManager()
    transport = MockTransport()
    
    # Inject input capability
    namespace.inject_capability('input', InputCapability(transport))
    
    # Verify it's in namespace
    assert 'input' in namespace.namespace
    assert callable(namespace.namespace['input'])

async def test_security_policy():
    """Test security policy enforcement."""
    namespace = NamespaceManager()
    policy = SecurityPolicy(SecurityLevel.SANDBOX)
    namespace.set_security_policy(policy)
    
    # Should succeed (allowed in sandbox)
    namespace.inject_capability('input')
    
    # Should fail (not allowed in sandbox)
    with pytest.raises(SecurityError):
        namespace.inject_capability('fetch')

async def test_capability_bundle():
    """Test bundle injection."""
    namespace = NamespaceManager()
    namespace.inject_bundle('basic_io')
    
    assert 'input' in namespace.namespace
    assert 'display' in namespace.namespace
    assert 'print' in namespace.namespace
```

## Calibration

<context_gathering>
- Search depth: MEDIUM (architectural pattern)
- Maximum tool calls: 20-25
- Early stop: When capability pattern is clear
</context_gathering>

## Non-Negotiables

1. **Security enforcement**: Policies must be respected
2. **Protocol correlation**: Request/response matching must work
3. **Async support**: Capabilities can be async or sync
4. **Extensibility**: Easy to add new capabilities

## Success Criteria

- [ ] Capabilities can be dynamically injected
- [ ] Security policies control access
- [ ] Protocol bridging works correctly
- [ ] Bundles simplify common sets
- [ ] Plugin system allows extensions

## Additional Guidance

- Consider using decorators for capability definition
- Look at dependency injection frameworks for patterns
- Think about capability versioning
- Consider hot-reload of capabilities
- Document capability API for plugin developers
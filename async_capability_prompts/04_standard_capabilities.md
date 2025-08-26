# Standard Protocol-Bridged Capabilities Implementation Planning Prompt

## Your Mission

You are tasked with implementing a comprehensive set of standard capabilities that will be injected into the execution namespace. These capabilities bridge Python functions to the protocol message system, enabling controlled I/O, network access, rich display, filesystem operations, and inter-session communication. Each capability must work seamlessly in both async and sync contexts.

## Context Gathering Requirements

Before implementing, you MUST understand:

### 1. Capability Categories
- **Basic I/O**: input, print, display
- **Rich Display**: show, plot, table, markdown
- **Network**: fetch, websocket, stream
- **Filesystem**: read_file, write_file, list_dir, watch_file
- **Data**: query, load_dataset, save_data
- **Inter-session**: send_to, receive_from, broadcast
- **System**: shell, env, process

### 2. Protocol Bridge Pattern
- Each capability sends protocol messages
- Waits for responses when needed
- Handles timeouts and errors gracefully
- Correlates requests with responses via IDs

### 3. Design Requirements
- Must work in both async and sync execution contexts
- Should provide intuitive Python APIs
- Need proper error handling and timeouts
- Must respect security policies

## Planning Methodology

### Phase 1: Analysis (25% effort)
<context_gathering>
Goal: Understand protocol message patterns for each capability type
Stop when: You know how to bridge each operation type
Depth: Study request/response vs streaming vs fire-and-forget patterns
</context_gathering>

### Phase 2: Solution Design (60% effort)

**Core Capability Implementations:**

```python
# src/subprocess/standard_capabilities.py
from typing import Any, Dict, List, Optional, Union
import asyncio
import base64
import json
import uuid
from abc import ABC, abstractmethod

# ============= Basic I/O Capabilities =============

class PrintCapability(Capability):
    """Enhanced print with protocol streaming."""
    
    def get_name(self) -> str:
        return 'print'
    
    def get_implementation(self) -> Callable:
        async def protocol_print(*args, sep=' ', end='\n', file=None, flush=False):
            """Print via protocol output stream."""
            # Convert args to string
            output = sep.join(str(arg) for arg in args) + end
            
            # Determine stream
            stream_type = 'stderr' if file == 'stderr' else 'stdout'
            
            # Send output message
            await self.transport.send_message(OutputMessage(
                id=str(uuid.uuid4()),
                stream=stream_type,
                data=output,
                flush=flush
            ))
        
        # Return sync or async based on context
        if self.is_async_context():
            return protocol_print
        else:
            def sync_print(*args, **kwargs):
                asyncio.run(protocol_print(*args, **kwargs))
            return sync_print

# ============= Rich Display Capabilities =============

class ShowCapability(Capability):
    """Rich object display with automatic type detection."""
    
    def get_name(self) -> str:
        return 'show'
    
    def get_implementation(self) -> Callable:
        async def show(obj: Any, **options):
            """Display object with rich formatting."""
            display_id = str(uuid.uuid4())
            
            # Detect display type
            mime_type, data = self._prepare_display(obj, options)
            
            # Send display message
            await self.transport.send_message(DisplayMessage(
                id=display_id,
                mime_type=mime_type,
                data=data,
                metadata=options
            ))
            
            # Return display ID for updates
            return display_id
        
        return show
    
    def _prepare_display(self, obj: Any, options: Dict) -> tuple[str, Any]:
        """Prepare object for display."""
        import pandas as pd
        import matplotlib.pyplot as plt
        import numpy as np
        
        # Pandas DataFrame
        if isinstance(obj, pd.DataFrame):
            if options.get('format') == 'html':
                return 'text/html', obj.to_html()
            else:
                return 'application/json', obj.to_json(orient='records')
        
        # Matplotlib figure
        elif isinstance(obj, plt.Figure):
            import io
            buf = io.BytesIO()
            obj.savefig(buf, format='png')
            buf.seek(0)
            data = base64.b64encode(buf.read()).decode()
            return 'image/png', data
        
        # NumPy array
        elif isinstance(obj, np.ndarray):
            if obj.ndim == 2 and options.get('as_image'):
                # Treat as image
                from PIL import Image
                img = Image.fromarray(obj)
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                data = base64.b64encode(buf.getvalue()).decode()
                return 'image/png', data
            else:
                return 'application/json', obj.tolist()
        
        # Rich repr methods
        elif hasattr(obj, '_repr_html_'):
            return 'text/html', obj._repr_html_()
        elif hasattr(obj, '_repr_json_'):
            return 'application/json', obj._repr_json_()
        elif hasattr(obj, '_repr_markdown_'):
            return 'text/markdown', obj._repr_markdown_()
        
        # Default to string
        else:
            return 'text/plain', str(obj)

class PlotCapability(Capability):
    """Interactive plotting capability."""
    
    def get_name(self) -> str:
        return 'plot'
    
    def get_implementation(self) -> Callable:
        async def plot(x, y=None, **options):
            """Create interactive plot."""
            plot_id = str(uuid.uuid4())
            
            # Prepare plot data
            plot_data = self._prepare_plot_data(x, y, options)
            
            # Send plot message
            await self.transport.send_message(PlotMessage(
                id=plot_id,
                data=plot_data,
                plot_type=options.get('type', 'line'),
                options=options
            ))
            
            return plot_id
        
        return plot

# ============= Network Capabilities =============

class FetchCapability(Capability):
    """HTTP fetch with sandboxing."""
    
    def get_name(self) -> str:
        return 'fetch'
    
    def get_implementation(self) -> Callable:
        async def fetch(url: str, **options) -> Dict:
            """Fetch URL via protocol."""
            request_id = str(uuid.uuid4())
            
            # Send HTTP request
            await self.transport.send_message(HttpRequestMessage(
                id=request_id,
                url=url,
                method=options.get('method', 'GET'),
                headers=options.get('headers', {}),
                body=options.get('body'),
                timeout=options.get('timeout', 30)
            ))
            
            # Wait for response
            future = asyncio.Future()
            self._pending_requests[request_id] = future
            
            try:
                response = await asyncio.wait_for(future, timeout=options.get('timeout', 30))
                
                # Create response object
                class Response:
                    def __init__(self, data):
                        self.status = data['status']
                        self.headers = data['headers']
                        self._body = data['body']
                    
                    @property
                    def text(self):
                        return self._body
                    
                    def json(self):
                        return json.loads(self._body)
                    
                    async def read(self):
                        return self._body.encode()
                
                return Response(response)
                
            finally:
                self._pending_requests.pop(request_id, None)
        
        return fetch

class WebSocketCapability(Capability):
    """WebSocket client capability."""
    
    def get_name(self) -> str:
        return 'websocket'
    
    def get_implementation(self) -> Callable:
        async def websocket(url: str, **options):
            """Create WebSocket connection."""
            ws_id = str(uuid.uuid4())
            
            # Send WebSocket connect request
            await self.transport.send_message(WebSocketConnectMessage(
                id=ws_id,
                url=url,
                headers=options.get('headers', {})
            ))
            
            # Return WebSocket handle
            class WebSocketHandle:
                def __init__(self, ws_id, transport):
                    self.id = ws_id
                    self.transport = transport
                    self._message_queue = asyncio.Queue()
                
                async def send(self, data):
                    """Send data to WebSocket."""
                    await self.transport.send_message(WebSocketSendMessage(
                        ws_id=self.id,
                        data=data
                    ))
                
                async def receive(self):
                    """Receive data from WebSocket."""
                    return await self._message_queue.get()
                
                async def close(self):
                    """Close WebSocket connection."""
                    await self.transport.send_message(WebSocketCloseMessage(
                        ws_id=self.id
                    ))
            
            return WebSocketHandle(ws_id, self.transport)
        
        return websocket

# ============= Filesystem Capabilities =============

class ReadFileCapability(Capability):
    """Sandboxed file reading."""
    
    def get_name(self) -> str:
        return 'read_file'
    
    def get_implementation(self) -> Callable:
        async def read_file(path: str, encoding: str = 'utf-8', binary: bool = False):
            """Read file via protocol."""
            request_id = str(uuid.uuid4())
            
            # Send read request
            await self.transport.send_message(FileReadRequestMessage(
                id=request_id,
                path=path,
                encoding=None if binary else encoding,
                binary=binary
            ))
            
            # Wait for response
            future = asyncio.Future()
            self._pending_requests[request_id] = future
            
            try:
                response = await asyncio.wait_for(future, timeout=10)
                
                if binary:
                    return base64.b64decode(response['content'])
                else:
                    return response['content']
                    
            finally:
                self._pending_requests.pop(request_id, None)
        
        return read_file

class WriteFileCapability(Capability):
    """Sandboxed file writing."""
    
    def get_name(self) -> str:
        return 'write_file'
    
    def get_implementation(self) -> Callable:
        async def write_file(path: str, content: Union[str, bytes], encoding: str = 'utf-8'):
            """Write file via protocol."""
            request_id = str(uuid.uuid4())
            
            # Prepare content
            if isinstance(content, bytes):
                content = base64.b64encode(content).decode()
                binary = True
            else:
                binary = False
            
            # Send write request
            await self.transport.send_message(FileWriteRequestMessage(
                id=request_id,
                path=path,
                content=content,
                encoding=None if binary else encoding,
                binary=binary
            ))
            
            # Wait for confirmation
            future = asyncio.Future()
            self._pending_requests[request_id] = future
            
            try:
                response = await asyncio.wait_for(future, timeout=10)
                return response['bytes_written']
                
            finally:
                self._pending_requests.pop(request_id, None)
        
        return write_file

class WatchFileCapability(Capability):
    """File system watcher capability."""
    
    def get_name(self) -> str:
        return 'watch_file'
    
    def get_implementation(self) -> Callable:
        async def watch_file(path: str, callback: Callable):
            """Watch file for changes."""
            watch_id = str(uuid.uuid4())
            
            # Send watch request
            await self.transport.send_message(FileWatchRequestMessage(
                id=watch_id,
                path=path
            ))
            
            # Register callback
            self._file_watchers[watch_id] = callback
            
            # Return handle to stop watching
            class WatchHandle:
                def __init__(self, watch_id, capability):
                    self.id = watch_id
                    self.capability = capability
                
                async def stop(self):
                    await self.capability.stop_watch(self.id)
            
            return WatchHandle(watch_id, self)
        
        return watch_file

# ============= Data Capabilities =============

class QueryCapability(Capability):
    """Database query capability."""
    
    def get_name(self) -> str:
        return 'query'
    
    def get_implementation(self) -> Callable:
        async def query(sql: str, params: Optional[List] = None, database: str = 'default'):
            """Execute SQL query."""
            request_id = str(uuid.uuid4())
            
            # Send query request
            await self.transport.send_message(QueryRequestMessage(
                id=request_id,
                sql=sql,
                params=params or [],
                database=database
            ))
            
            # Wait for results
            future = asyncio.Future()
            self._pending_requests[request_id] = future
            
            try:
                response = await asyncio.wait_for(future, timeout=60)
                
                # Convert to DataFrame if pandas available
                try:
                    import pandas as pd
                    return pd.DataFrame(response['rows'])
                except ImportError:
                    return response['rows']
                    
            finally:
                self._pending_requests.pop(request_id, None)
        
        return query

# ============= Inter-Session Capabilities =============

class SendToCapability(Capability):
    """Send data to another session."""
    
    def get_name(self) -> str:
        return 'send_to'
    
    def get_implementation(self) -> Callable:
        async def send_to(session_id: str, data: Any, **metadata):
            """Send data to another session."""
            message_id = str(uuid.uuid4())
            
            # Serialize data
            serialized = self._serialize_data(data)
            
            # Send inter-session message
            await self.transport.send_message(InterSessionMessage(
                id=message_id,
                from_session=self.session_id,
                to_session=session_id,
                data=serialized,
                metadata=metadata
            ))
            
            return message_id
        
        return send_to

class BroadcastCapability(Capability):
    """Broadcast to multiple sessions."""
    
    def get_name(self) -> str:
        return 'broadcast'
    
    def get_implementation(self) -> Callable:
        async def broadcast(channel: str, data: Any, **metadata):
            """Broadcast data to a channel."""
            message_id = str(uuid.uuid4())
            
            # Serialize data
            serialized = self._serialize_data(data)
            
            # Send broadcast message
            await self.transport.send_message(BroadcastMessage(
                id=message_id,
                channel=channel,
                data=serialized,
                metadata=metadata
            ))
            
            return message_id
        
        return broadcast

# ============= System Capabilities =============

class ShellCapability(Capability):
    """Execute shell commands (sandboxed)."""
    
    def get_name(self) -> str:
        return 'shell'
    
    def get_implementation(self) -> Callable:
        async def shell(command: str, **options):
            """Execute shell command."""
            request_id = str(uuid.uuid4())
            
            # Send shell command request
            await self.transport.send_message(ShellCommandMessage(
                id=request_id,
                command=command,
                cwd=options.get('cwd'),
                env=options.get('env', {}),
                timeout=options.get('timeout', 30)
            ))
            
            # Wait for result
            future = asyncio.Future()
            self._pending_requests[request_id] = future
            
            try:
                response = await asyncio.wait_for(
                    future, 
                    timeout=options.get('timeout', 30)
                )
                
                return {
                    'stdout': response['stdout'],
                    'stderr': response['stderr'],
                    'returncode': response['returncode']
                }
                
            finally:
                self._pending_requests.pop(request_id, None)
        
        return shell
```

**Capability Bundle Definitions:**

```python
# src/subprocess/capability_bundles.py
from typing import List, Dict, Type

class CapabilityBundle:
    """Bundle of related capabilities."""
    
    def __init__(self, name: str, capabilities: Dict[str, Type[Capability]]):
        self.name = name
        self.capabilities = capabilities
    
    def create_instances(self, transport: MessageTransport) -> Dict[str, Capability]:
        """Create instances of all capabilities in bundle."""
        return {
            name: cap_class(transport)
            for name, cap_class in self.capabilities.items()
        }

# Standard bundles
BASIC_IO_BUNDLE = CapabilityBundle('basic_io', {
    'input': InputCapability,
    'print': PrintCapability,
    'display': ShowCapability,
})

RICH_DISPLAY_BUNDLE = CapabilityBundle('rich_display', {
    'show': ShowCapability,
    'plot': PlotCapability,
    'table': TableCapability,
    'markdown': MarkdownCapability,
})

NETWORK_BUNDLE = CapabilityBundle('network', {
    'fetch': FetchCapability,
    'websocket': WebSocketCapability,
    'stream': StreamCapability,
})

FILESYSTEM_BUNDLE = CapabilityBundle('filesystem', {
    'read_file': ReadFileCapability,
    'write_file': WriteFileCapability,
    'list_dir': ListDirCapability,
    'watch_file': WatchFileCapability,
})

DATA_BUNDLE = CapabilityBundle('data', {
    'query': QueryCapability,
    'load_dataset': LoadDatasetCapability,
    'save_data': SaveDataCapability,
})

COMMUNICATION_BUNDLE = CapabilityBundle('communication', {
    'send_to': SendToCapability,
    'receive_from': ReceiveFromCapability,
    'broadcast': BroadcastCapability,
    'subscribe': SubscribeCapability,
})

SYSTEM_BUNDLE = CapabilityBundle('system', {
    'shell': ShellCapability,
    'env': EnvCapability,
    'process': ProcessCapability,
})

# Security level bundles
SANDBOX_CAPABILITIES = ['input', 'print', 'display']
RESTRICTED_CAPABILITIES = SANDBOX_CAPABILITIES + ['show', 'plot']
STANDARD_CAPABILITIES = RESTRICTED_CAPABILITIES + ['fetch', 'read_file', 'write_file']
TRUSTED_CAPABILITIES = STANDARD_CAPABILITIES + ['query', 'shell']
ADMIN_CAPABILITIES = '*'  # All capabilities
```

### Phase 3: Risk Assessment (15% effort)

- **Risk**: Protocol message flooding
  - Mitigation: Rate limiting, batching
  
- **Risk**: Large data transfers
  - Mitigation: Streaming, chunking
  
- **Risk**: Security bypass via capabilities
  - Mitigation: Strict sandboxing, validation

## Output Requirements

Your implementation must include:

### 1. Executive Summary
- Overview of standard capability set
- Protocol bridging patterns
- Security considerations
- Usage examples

### 2. Test Suite

```python
async def test_display_capability():
    """Test rich display capability."""
    import pandas as pd
    
    namespace = AsyncNamespaceManager()
    show_cap = ShowCapability(mock_transport)
    namespace.inject_capability('show', show_cap)
    
    # Display DataFrame
    df = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})
    display_id = await namespace.namespace['show'](df, format='html')
    
    # Verify display message sent
    assert mock_transport.last_message.mime_type == 'text/html'

async def test_fetch_capability():
    """Test network fetch capability."""
    namespace = AsyncNamespaceManager()
    fetch_cap = FetchCapability(mock_transport)
    namespace.inject_capability('fetch', fetch_cap)
    
    # Mock response
    mock_transport.mock_response({
        'status': 200,
        'headers': {'content-type': 'application/json'},
        'body': '{"data": "test"}'
    })
    
    # Fetch URL
    response = await namespace.namespace['fetch']('https://api.example.com')
    assert response.status == 200
    assert response.json() == {'data': 'test'}
```

## Calibration

<context_gathering>
- Search depth: MEDIUM (implementation patterns)
- Maximum tool calls: 25-30
- Early stop: When core patterns are clear
</context_gathering>

## Non-Negotiables

1. **Protocol correlation**: Request/response matching must work
2. **Timeout handling**: All operations must timeout gracefully
3. **Error propagation**: Protocol errors surface properly
4. **Security enforcement**: Respect sandboxing

## Success Criteria

- [ ] All standard capabilities implemented
- [ ] Protocol bridging works correctly
- [ ] Async and sync contexts supported
- [ ] Rich display types handled
- [ ] Security policies enforced

## Additional Guidance

- Consider capability versioning for compatibility
- Think about capability discovery mechanisms
- Add telemetry/metrics for capability usage
- Document each capability's protocol messages
- Consider capability composition patterns
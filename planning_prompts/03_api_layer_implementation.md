# API Layer Implementation Planning Prompt

## Your Mission

You are tasked with designing and implementing a complete API layer for PyREPL3 that provides WebSocket and REST endpoints for network access to Python execution sessions, enabling language-agnostic clients to execute code, handle interactive input, and manage session lifecycles.

## Context

### Historical Context (Problem Archaeology)

#### Current Limitations
1. **Process-Local Only**
   - What: Must import Python modules directly
   - Impact: No network access, no remote execution
   - Evidence: All usage requires `from src.session.manager import Session`

2. **Language Lock-in**
   - What: Python-only interface
   - Impact: Cannot integrate with web frontends, other languages
   - Evidence: Direct Python object manipulation required

3. **No Session Discovery**
   - What: No way to list, find, or reconnect to sessions
   - Impact: Sessions orphaned on client disconnect
   - Evidence: No session registry or persistence

#### Comparison with Other Systems
- **Jupyter**: REST API + WebSocket for real-time updates
- **JupyterLab Server**: Tornado-based with session management
- **VS Code Python**: Language Server Protocol over JSON-RPC
- **exec-py API**: FastAPI with WebSocket streaming (partially implemented)
- **pyrepl2**: Protocol abstraction but no network layer

### Existing Infrastructure (Architecture Recognition)

#### Working Components to Leverage

1. **SessionPool** (src/session/pool.py)
   - Pre-warmed session management
   - Acquire/release lifecycle
   - Health monitoring
   - Perfect for multi-client support

2. **Protocol Messages** (src/protocol/messages.py)
   ```python
   ExecuteMessage      # Execute code request
   OutputMessage       # Streaming stdout/stderr
   InputMessage        # Request user input
   InputResponseMessage # Provide input response
   ResultMessage       # Execution result
   ErrorMessage        # Execution error
   HeartbeatMessage    # Keep-alive
   ```

3. **Session Manager** (src/session/manager.py)
   - Subprocess lifecycle management
   - Message routing via execution_id
   - Already async, perfect for WebSocket

4. **Async Architecture**
   - Everything already async/await
   - Natural fit for aiohttp/FastAPI
   - Streaming support built-in

#### Integration Points
```python
# Current internal flow:
Session.execute(ExecuteMessage) → AsyncIterator[Message]

# API will wrap this as:
WebSocket: {type: "execute", code: "..."} → Stream of {type: "output", data: "..."}
REST: POST /execute → Blocking result or job ID
```

### Required Capabilities (from test_api_missing.py)

#### WebSocket Requirements
1. Session creation and connection
2. Bidirectional message flow
3. Real-time output streaming
4. Interactive input handling
5. Session persistence across reconnect

#### REST Requirements
1. Session CRUD operations
2. Synchronous code execution
3. Async job submission
4. Health and metrics endpoints
5. Session state inspection

## Constraints

### Non-Negotiable Requirements
1. **No Breaking Changes**: Internal APIs must remain stable
2. **Pool Integration**: Must use SessionPool for resource management
3. **Message Compatibility**: Reuse existing protocol messages
4. **Concurrent Clients**: Support multiple clients per session (read-only observers)
5. **Security**: No arbitrary code execution without session context

### Risks to Avoid

#### Risk 1: Protocol Impedance Mismatch
- **Probability**: High without careful design
- **Impact**: Major (complex translation layer)
- **Scenario**: WebSocket JSON ↔ Internal MessagePack/Pydantic
- **Mitigation**: Thin adapter layer, preserve message structure

#### Risk 2: Session Lifecycle Confusion
- **Probability**: Medium
- **Impact**: Major (resource leaks)
- **Scenario**: Client disconnects, session orphaned
- **Mitigation**: Timeout-based cleanup, session ownership model

#### Risk 3: Input Response Routing
- **Probability**: Medium
- **Impact**: Critical (wrong session gets input)
- **Scenario**: Multiple sessions waiting for input
- **Mitigation**: Token-based correlation, session isolation

#### Risk 4: Backpressure Issues
- **Probability**: Low but impactful
- **Impact**: Major (memory exhaustion)
- **Scenario**: Slow client, fast output generation
- **Mitigation**: Output buffering limits, flow control

## Planning Approach

### Architecture Design

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Browser   │────▶│   API Layer  │────▶│SessionPool  │
│   Client    │◀────│   (aiohttp)  │◀────│             │
└─────────────┘     └──────────────┘     └─────────────┘
                            │                     │
                    ┌───────┴────────┐           │
                    │                │           │
              WebSocket          REST API        │
              Handler            Handler         │
                    │                │           │
                    └────────┬───────┘           │
                             │                   │
                      Protocol Adapter            │
                             │                   │
                             └───────────────────┘
```

### Implementation Approaches

#### Approach A: Unified aiohttp Server (Recommended)
**Philosophy**: Single server handles both WebSocket and REST
**Stack**: aiohttp + aiohttp-cors + pydantic
**Pros**: 
- Unified codebase
- Shared session management
- Native WebSocket support
- Already have aiohttp dependency
**Cons**: 
- Less REST sugar than FastAPI

#### Approach B: FastAPI + WebSockets
**Philosophy**: Modern API framework with automatic OpenAPI
**Stack**: FastAPI + uvicorn + websockets
**Pros**: 
- Automatic API documentation
- Pydantic integration (already using)
- Modern async/await
**Cons**: 
- Additional dependencies
- Separate WebSocket handling

#### Approach C: Dual Server
**Philosophy**: REST on FastAPI, WebSocket on separate port
**Pros**: Best tool for each job
**Cons**: Complex deployment, session sharing issues

### Calibration
<context_gathering>
Search depth: High (greenfield design needs exploration)
Tool budget: 20-30 (multiple files, comprehensive implementation)
Early stop: Never (complete implementation needed)
</context_gathering>

## Implementation Guide

### Phase 1: Core API Module Structure (15% effort)

Create directory structure:
```
src/api/
├── __init__.py
├── server.py           # Main aiohttp application
├── websocket.py        # WebSocket handler
├── rest.py            # REST endpoints
├── models.py          # API request/response models
├── session_manager.py # Session lifecycle management
└── protocol_adapter.py # Convert between API and internal protocol
```

### Phase 2: Models and Protocol Adapter (20% effort)

**File: src/api/models.py**
```python
from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
from enum import Enum

class APIMessageType(str, Enum):
    # Requests
    EXECUTE = "execute"
    INPUT_RESPONSE = "input_response"
    CREATE_SESSION = "create_session"
    CLOSE_SESSION = "close_session"
    
    # Responses
    SESSION_CREATED = "session_created"
    OUTPUT = "output"
    INPUT_REQUEST = "input_request"
    RESULT = "result"
    ERROR = "error"

class ExecuteRequest(BaseModel):
    type: Literal["execute"]
    code: str
    transaction_policy: str = "commit_always"

class InputResponseRequest(BaseModel):
    type: Literal["input_response"]
    token: str
    data: str

class OutputResponse(BaseModel):
    type: Literal["output"]
    stream: Literal["stdout", "stderr"]
    data: str

class ResultResponse(BaseModel):
    type: Literal["result"]
    value: Any
    repr: str
    execution_time: float
```

**File: src/api/protocol_adapter.py**
```python
from typing import Union
from ..protocol.messages import (
    ExecuteMessage, OutputMessage, ResultMessage, 
    ErrorMessage, InputMessage, InputResponseMessage
)
from .models import *
import time
import uuid

class ProtocolAdapter:
    """Converts between API models and internal protocol messages."""
    
    @staticmethod
    def api_to_internal(api_msg: dict) -> Union[ExecuteMessage, InputResponseMessage]:
        """Convert API request to internal protocol message."""
        msg_type = api_msg.get("type")
        
        if msg_type == "execute":
            return ExecuteMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                code=api_msg["code"],
                transaction_policy=api_msg.get("transaction_policy", "commit_always")
            )
        elif msg_type == "input_response":
            return InputResponseMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                input_id=api_msg["token"],
                data=api_msg["data"]
            )
        else:
            raise ValueError(f"Unknown message type: {msg_type}")
    
    @staticmethod
    def internal_to_api(internal_msg: Message) -> dict:
        """Convert internal protocol message to API response."""
        if isinstance(internal_msg, OutputMessage):
            return {
                "type": "output",
                "stream": internal_msg.stream.value,
                "data": internal_msg.data
            }
        elif isinstance(internal_msg, ResultMessage):
            return {
                "type": "result",
                "value": internal_msg.value,
                "repr": internal_msg.repr,
                "execution_time": internal_msg.execution_time
            }
        elif isinstance(internal_msg, ErrorMessage):
            return {
                "type": "error",
                "exception": internal_msg.exception_type,
                "message": internal_msg.exception_message,
                "traceback": internal_msg.traceback
            }
        elif isinstance(internal_msg, InputMessage):
            return {
                "type": "input_request",
                "token": internal_msg.id,
                "prompt": internal_msg.prompt
            }
        else:
            return {"type": "unknown", "data": str(internal_msg)}
```

### Phase 3: WebSocket Handler (30% effort)

**File: src/api/websocket.py**
```python
import asyncio
import json
import logging
from typing import Optional, Dict
from aiohttp import web, WSMsgType
import aiohttp

from ..session.pool import SessionPool
from ..session.manager import Session
from .protocol_adapter import ProtocolAdapter

logger = logging.getLogger(__name__)

class WebSocketHandler:
    def __init__(self, pool: SessionPool):
        self.pool = pool
        self.active_connections: Dict[str, Session] = {}
        self.adapter = ProtocolAdapter()
    
    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Main WebSocket connection handler."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        session = None
        session_id = None
        
        try:
            # Acquire session from pool
            session = await self.pool.acquire(timeout=5.0)
            session_id = session.session_id
            self.active_connections[session_id] = session
            
            # Send session created message
            await ws.send_json({
                "type": "session_created",
                "session_id": session_id
            })
            
            # Create task for handling execution responses
            response_task = None
            
            # Main message loop
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_client_message(ws, session, data, response_task)
                        
                    except json.JSONDecodeError as e:
                        await ws.send_json({
                            "type": "error",
                            "message": f"Invalid JSON: {e}"
                        })
                    except Exception as e:
                        logger.error(f"Message handling error: {e}")
                        await ws.send_json({
                            "type": "error",
                            "message": str(e)
                        })
                        
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f'WebSocket error: {ws.exception()}')
                    break
                    
        except asyncio.TimeoutError:
            await ws.send_json({
                "type": "error",
                "message": "Session acquisition timeout"
            })
        finally:
            # Cleanup
            if response_task and not response_task.done():
                response_task.cancel()
            
            if session and session_id:
                await self.pool.release(session)
                del self.active_connections[session_id]
            
            await ws.close()
        
        return ws
    
    async def _handle_client_message(self, ws, session, data, response_task):
        """Handle a message from the client."""
        msg_type = data.get("type")
        
        if msg_type == "execute":
            # Convert to internal message
            internal_msg = self.adapter.api_to_internal(data)
            
            # Cancel previous execution if running
            if response_task and not response_task.done():
                response_task.cancel()
            
            # Start execution and response streaming
            response_task = asyncio.create_task(
                self._stream_execution_results(ws, session, internal_msg)
            )
            
        elif msg_type == "input_response":
            # Handle input response
            # This needs to be routed to waiting input request
            internal_msg = self.adapter.api_to_internal(data)
            # TODO: Route to session's waiting input handler
            
        elif msg_type == "close_session":
            await ws.close()
    
    async def _stream_execution_results(self, ws, session, execute_msg):
        """Stream execution results to WebSocket."""
        try:
            async for result_msg in session.execute(execute_msg):
                api_msg = self.adapter.internal_to_api(result_msg)
                await ws.send_json(api_msg)
        except asyncio.CancelledError:
            logger.info("Execution cancelled")
            raise
        except Exception as e:
            logger.error(f"Execution streaming error: {e}")
            await ws.send_json({
                "type": "error",
                "message": f"Execution error: {e}"
            })
```

### Phase 4: REST Endpoints (20% effort)

**File: src/api/rest.py**
```python
from aiohttp import web
from typing import Optional
import asyncio
import uuid

from ..session.pool import SessionPool
from .protocol_adapter import ProtocolAdapter
from .models import ExecuteRequest

class RestAPI:
    def __init__(self, pool: SessionPool):
        self.pool = pool
        self.adapter = ProtocolAdapter()
        self.jobs = {}  # Job ID -> Future
    
    def setup_routes(self, app: web.Application):
        """Configure REST API routes."""
        app.router.add_post('/sessions', self.create_session)
        app.router.add_get('/sessions', self.list_sessions)
        app.router.add_get('/sessions/{session_id}', self.get_session)
        app.router.add_delete('/sessions/{session_id}', self.close_session)
        app.router.add_post('/sessions/{session_id}/execute', self.execute_code)
        app.router.add_post('/execute', self.execute_immediate)
        app.router.add_get('/health', self.health_check)
        app.router.add_get('/metrics', self.get_metrics)
    
    async def create_session(self, request: web.Request) -> web.Response:
        """POST /sessions - Create new session."""
        try:
            session = await self.pool.acquire(timeout=5.0)
            return web.json_response({
                "session_id": session.session_id,
                "state": session.state.value
            })
        except asyncio.TimeoutError:
            return web.json_response(
                {"error": "Session creation timeout"},
                status=503
            )
    
    async def execute_immediate(self, request: web.Request) -> web.Response:
        """POST /execute - Execute code immediately (session-less)."""
        data = await request.json()
        
        # Acquire temporary session
        session = await self.pool.acquire()
        
        try:
            # Execute code
            code = data.get("code")
            if not code:
                return web.json_response({"error": "No code provided"}, status=400)
            
            internal_msg = self.adapter.api_to_internal({"type": "execute", "code": code})
            
            # Collect all results
            outputs = []
            result = None
            error = None
            
            async for msg in session.execute(internal_msg):
                api_msg = self.adapter.internal_to_api(msg)
                if api_msg["type"] == "output":
                    outputs.append(api_msg["data"])
                elif api_msg["type"] == "result":
                    result = api_msg
                elif api_msg["type"] == "error":
                    error = api_msg
            
            return web.json_response({
                "outputs": outputs,
                "result": result,
                "error": error
            })
            
        finally:
            await self.pool.release(session)
    
    async def health_check(self, request: web.Request) -> web.Response:
        """GET /health - Health check endpoint."""
        # Get pool statistics
        idle = self.pool._idle_sessions.qsize()
        active = len(self.pool._active_sessions)
        total = len(self.pool._all_sessions)
        
        return web.json_response({
            "status": "healthy",
            "pool": {
                "idle": idle,
                "active": active,
                "total": total,
                "max": self.pool._config.max_sessions
            }
        })
```

### Phase 5: Main Server (15% effort)

**File: src/api/server.py**
```python
from aiohttp import web
import aiohttp_cors
import logging
from typing import Optional

from ..session.pool import SessionPool, PoolConfig
from .websocket import WebSocketHandler
from .rest import RestAPI

logger = logging.getLogger(__name__)

class APIServer:
    def __init__(
        self, 
        host: str = "0.0.0.0",
        port: int = 8080,
        pool_config: Optional[PoolConfig] = None
    ):
        self.host = host
        self.port = port
        
        # Create session pool
        if pool_config is None:
            pool_config = PoolConfig(
                min_idle=2,
                max_sessions=10,
                warmup_code="import sys\nimport json\n"
            )
        self.pool = SessionPool(pool_config)
        
        # Create handlers
        self.ws_handler = WebSocketHandler(self.pool)
        self.rest_api = RestAPI(self.pool)
        
        # Create application
        self.app = web.Application()
        self._setup_routes()
        self._setup_cors()
    
    def _setup_routes(self):
        """Configure all routes."""
        # WebSocket endpoint
        self.app.router.add_get('/ws', self.ws_handler.handle_websocket)
        self.app.router.add_get('/session', self.ws_handler.handle_websocket)  # Alternative path
        
        # REST endpoints
        self.rest_api.setup_routes(self.app)
        
        # Static welcome page
        self.app.router.add_get('/', self._welcome)
    
    def _setup_cors(self):
        """Configure CORS for browser clients."""
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*"
            )
        })
        
        # Configure CORS on all routes
        for route in list(self.app.router.routes()):
            cors.add(route)
    
    async def _welcome(self, request):
        """Welcome page with API documentation."""
        html = """
        <html>
        <head><title>PyREPL3 API</title></head>
        <body>
            <h1>PyREPL3 API Server</h1>
            <h2>Endpoints:</h2>
            <ul>
                <li>WebSocket: ws://localhost:8080/ws</li>
                <li>REST: http://localhost:8080/execute</li>
                <li>Health: http://localhost:8080/health</li>
            </ul>
            <h2>Example WebSocket Usage:</h2>
            <pre>
const ws = new WebSocket('ws://localhost:8080/ws');
ws.onmessage = (event) => console.log(JSON.parse(event.data));
ws.send(JSON.stringify({type: 'execute', code: 'print("Hello")'}));
            </pre>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
    
    async def start(self):
        """Start the API server."""
        # Start session pool
        await self.pool.start()
        
        # Start web server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        logger.info(f"API Server running on http://{self.host}:{self.port}")
        logger.info(f"WebSocket endpoint: ws://{self.host}:{self.port}/ws")

# Convenience function for main.py
async def run_api_server(host='0.0.0.0', port=8080):
    """Run the API server."""
    server = APIServer(host, port)
    await server.start()
    
    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down API server")
```

## Output Requirements

Your implementation plan must include:

1. **Architecture Diagram**: Clear visualization of component relationships
2. **API Specification**: 
   - WebSocket message protocol (all message types)
   - REST endpoint documentation
   - Error response formats
3. **Implementation Sequence**:
   - Order of file creation
   - Dependencies between components
   - Integration points
4. **Testing Strategy**:
   - Unit tests for protocol adapter
   - Integration tests for WebSocket flow
   - Client example code
5. **Deployment Guide**:
   - How to start server
   - Configuration options
   - Client connection examples

## Success Validation

### Functional Tests
| Requirement | Test Case | Expected Result | Pass Criteria |
|-------------|-----------|-----------------|---------------|
| WebSocket connection | Connect to /ws | Receive session_created | Has session_id |
| Execute via WS | Send execute message | Stream output messages | Output received |
| REST execution | POST /execute | Get result | 200 OK with output |
| Input handling | WS input_request | Client sends response | Execution continues |
| Session management | GET /sessions | List active sessions | JSON array |

### Integration Tests
```python
async def test_websocket_full_flow():
    """Test complete WebSocket interaction."""
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect('ws://localhost:8080/ws') as ws:
            # Wait for session creation
            msg = await ws.receive_json()
            assert msg['type'] == 'session_created'
            
            # Execute code
            await ws.send_json({
                'type': 'execute',
                'code': 'print("test"); 42'
            })
            
            # Collect responses
            outputs = []
            result = None
            
            async for msg in ws:
                data = json.loads(msg.data)
                if data['type'] == 'output':
                    outputs.append(data['data'])
                elif data['type'] == 'result':
                    result = data
                    break
            
            assert 'test' in ''.join(outputs)
            assert result['repr'] == '42'
```

### Client Examples
1. Python client using aiohttp
2. JavaScript browser client
3. curl examples for REST API
4. WebSocket test page

## Expected Outcome

After implementing this API layer:
1. ✅ Any language can execute Python code via HTTP/WebSocket
2. ✅ Web browsers can connect directly
3. ✅ Multiple clients can share sessions (observers)
4. ✅ Interactive input works over network
5. ✅ Session lifecycle properly managed
6. ✅ Production-ready with health checks and metrics
7. ✅ Fully documented with examples

The API layer transforms PyREPL3 from a library into a service, enabling integration with any system that can make HTTP requests or establish WebSocket connections.
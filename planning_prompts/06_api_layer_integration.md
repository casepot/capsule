# API Layer Integration Planning Prompt

## Your Mission

You are tasked with implementing the WebSocket and REST API layer that will expose PyREPL3's execution capabilities to network clients. This is the final piece that transforms PyREPL3 from a local execution service into a production-ready networked execution infrastructure. The API must integrate with all previously fixed components (input handling, transactions, checkpoints).

## Context Gathering Requirements

Before implementing, you MUST understand:

### 1. Problem History (Problem Archaeology)
- **Current State**: No API layer exists, only local Session/SessionPool classes
- **ROADMAP Vision**: WebSocket for streaming, REST for operations
- **Unified Plan**: Specified /execute, /checkpoint, /restore endpoints
- **Architecture**: 70% language-agnostic infrastructure, 30% Python-specific

### 2. Existing Infrastructure (Architecture Recognition)
- **Session Management**: Session and SessionPool classes work locally
- **Message Protocol**: Well-defined message types (ExecuteMessage, etc.)
- **Transport Layer**: PipeTransport for subprocess communication
- **Threading Model**: ThreadedExecutor handles blocking I/O
- **Input Protocol**: INPUT/INPUT_RESPONSE messages work

### 3. Constraints That Cannot Be Violated (Risk Illumination)
- **Backward Compatibility**: Local usage must continue working
- **Session Isolation**: Each client gets separate session/subprocess
- **Streaming Requirements**: Real-time output over WebSocket
- **Security**: No arbitrary code execution without session

## Planning Methodology

### Phase 1: Analysis (30% effort)
<context_gathering>
Goal: Understand how to bridge network layer with session management
Stop when: You have clear mapping from HTTP/WS to sessions
Depth: Study how Session class works, what adapters are needed
</context_gathering>

Investigate:
1. Session lifecycle and how to map to client connections
2. Message serialization for network transport
3. WebSocket vs REST responsibility split
4. Authentication/authorization requirements

### Phase 2: Solution Design (50% effort)

Consider these approaches:

**Approach A: FastAPI with WebSocket Support (Recommended)**
- FastAPI handles both REST and WebSocket
- Session pool shared across endpoints
- WebSocket for streaming, REST for operations
- Pros: Single framework, good async support, auto-docs
- Cons: Additional dependency

**Approach B: Pure ASGI with Starlette**
- Lower-level control
- Custom routing
- Pros: Minimal dependencies, full control
- Cons: More boilerplate, no auto-docs

**Approach C: Separate Servers**
- WebSocket server (websockets library)
- REST server (aiohttp or FastAPI)
- Pros: Separation of concerns
- Cons: Complex deployment, port management

### Phase 3: Risk Assessment (20% effort)
- **Risk**: Session leaks from disconnected clients
  - Mitigation: Timeout and cleanup handlers
- **Risk**: Resource exhaustion from too many sessions
  - Mitigation: Rate limiting, session limits per client
- **Risk**: Output flooding WebSocket
  - Mitigation: Backpressure, buffering limits

## Output Requirements

Your plan must include:

### 1. Executive Summary (5 sentences max)
- Framework choice and rationale
- Endpoint design philosophy
- Session lifecycle management
- Security model

### 2. Technical Approach

**API Structure:**
```python
# src/api/server.py
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import uuid

app = FastAPI(title="PyREPL3 API", version="0.3.0")

# Shared session pool
pool = SessionPool(PoolConfig(min_idle=5, max_sessions=100))

# Client session mapping
client_sessions: Dict[str, str] = {}  # client_id -> session_id

class ExecuteRequest(BaseModel):
    code: str
    transaction_policy: str = "commit_always"
    timeout: float = 30.0

class ExecuteResponse(BaseModel):
    execution_id: str
    status: str

@app.on_event("startup")
async def startup():
    await pool.start()

@app.on_event("shutdown")
async def shutdown():
    await pool.shutdown()

# REST Endpoints
@app.post("/api/v1/execute")
async def execute(request: ExecuteRequest, client_id: str = Header()):
    """Execute code and return execution ID."""
    session = await get_or_create_session(client_id)
    
    message = ExecuteMessage(
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        code=request.code,
        transaction_policy=request.transaction_policy,
        timeout=request.timeout
    )
    
    # Start execution (non-blocking)
    task = asyncio.create_task(session.execute(message))
    
    return ExecuteResponse(
        execution_id=message.id,
        status="running"
    )

@app.post("/api/v1/checkpoint")
async def create_checkpoint(client_id: str = Header()):
    """Create session checkpoint."""
    session = await get_or_create_session(client_id)
    checkpoint_id = await session.checkpoint()
    return {"checkpoint_id": checkpoint_id}

@app.post("/api/v1/restore/{checkpoint_id}")
async def restore_checkpoint(checkpoint_id: str, client_id: str = Header()):
    """Restore from checkpoint."""
    session = await get_or_create_session(client_id)
    await session.restore(checkpoint_id)
    return {"status": "restored"}

# WebSocket Endpoint
@app.websocket("/ws/v1/session")
async def websocket_session(websocket: WebSocket, client_id: str = None):
    """WebSocket for streaming execution."""
    await websocket.accept()
    
    if not client_id:
        client_id = str(uuid.uuid4())
    
    session = await get_or_create_session(client_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            if data["type"] == "execute":
                message = ExecuteMessage(
                    id=data.get("id", str(uuid.uuid4())),
                    timestamp=time.time(),
                    code=data["code"],
                    transaction_policy=data.get("transaction_policy", "commit_always")
                )
                
                # Stream results back
                async for msg in session.execute(message):
                    await websocket.send_json({
                        "type": msg.type.value,
                        "data": msg.to_dict()
                    })
                    
            elif data["type"] == "input_response":
                # Handle input response
                await session.input_response(
                    data["input_id"],
                    data["value"]
                )
                
            elif data["type"] == "checkpoint":
                checkpoint_id = await session.checkpoint()
                await websocket.send_json({
                    "type": "checkpoint_created",
                    "checkpoint_id": checkpoint_id
                })
                
    except WebSocketDisconnect:
        # Clean up session
        await cleanup_client_session(client_id)
```

**Session Management:**
```python
async def get_or_create_session(client_id: str) -> Session:
    """Get existing session or create new one for client."""
    if client_id in client_sessions:
        session_id = client_sessions[client_id]
        try:
            return await pool.get_session(session_id)
        except SessionNotFound:
            # Session died, create new one
            pass
    
    # Acquire new session
    session = await pool.acquire()
    client_sessions[client_id] = session.session_id
    return session

async def cleanup_client_session(client_id: str):
    """Release session back to pool."""
    if client_id in client_sessions:
        session_id = client_sessions.pop(client_id)
        try:
            session = await pool.get_session(session_id)
            await pool.release(session)
        except:
            pass  # Session already dead
```

**Client SDK Example:**
```python
# src/client/client.py
import asyncio
import aiohttp

class PyREPL3Client:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client_id = str(uuid.uuid4())
        self.session = None
    
    async def execute(self, code: str) -> Any:
        """Execute code via REST."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/execute",
                json={"code": code},
                headers={"client-id": self.client_id}
            ) as response:
                return await response.json()
    
    async def stream_execute(self, code: str):
        """Execute with streaming via WebSocket."""
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                f"{self.base_url}/ws/v1/session",
                headers={"client-id": self.client_id}
            ) as ws:
                # Send execute request
                await ws.send_json({
                    "type": "execute",
                    "code": code
                })
                
                # Stream responses
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = msg.json()
                        yield data
```

### 3. Security Model
- Client ID header for session tracking
- Optional JWT authentication
- Rate limiting per client
- Code execution timeouts
- Resource limits enforced

### 4. Test Plan
```python
async def test_websocket_execution():
    """Test WebSocket streaming execution."""
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect("ws://localhost:8000/ws/v1/session") as ws:
            # Send execute
            await ws.send_json({
                "type": "execute",
                "code": "print('Hello'); x = 42"
            })
            
            # Receive output
            msg = await ws.receive_json()
            assert msg["type"] == "output"
            assert "Hello" in msg["data"]["data"]
            
            # Execute again, using previous state
            await ws.send_json({
                "type": "execute",
                "code": "print(x * 2)"
            })
            
            msg = await ws.receive_json()
            assert msg["type"] == "output"
            assert "84" in msg["data"]["data"]

async def test_rest_checkpoint():
    """Test REST checkpoint/restore."""
    client_id = str(uuid.uuid4())
    
    # Execute code
    response = await client.post("/api/v1/execute", 
                                json={"code": "x = 100"},
                                headers={"client-id": client_id})
    
    # Create checkpoint
    response = await client.post("/api/v1/checkpoint",
                                headers={"client-id": client_id})
    checkpoint_id = response.json()["checkpoint_id"]
    
    # Restore
    response = await client.post(f"/api/v1/restore/{checkpoint_id}",
                                headers={"client-id": client_id})
    assert response.json()["status"] == "restored"
```

## Calibration

<context_gathering>
- Search depth: MEDIUM (need to understand integration points)
- Maximum tool calls: 15-20
- Early stop: When endpoint design is clear
</context_gathering>

## Non-Negotiables

1. **Session Isolation**: Each client gets separate subprocess
2. **Streaming Support**: WebSocket must stream output in real-time
3. **Backward Compatibility**: Local Session usage unchanged
4. **Resource Limits**: Enforce max sessions per client

## Success Criteria

Before finalizing your plan, verify:
- [ ] Framework choice justified
- [ ] REST and WebSocket endpoints specified
- [ ] Session lifecycle management clear
- [ ] Security considerations addressed
- [ ] Client SDK example provided

## Additional Guidance

- FastAPI provides the best balance of features and simplicity
- WebSocket for interactive execution, REST for operations
- Session pool is the bridge between API and execution
- Client ID tracking enables session persistence
- Consider adding OpenAPI/Swagger documentation
- Plan for horizontal scaling (multiple API servers)
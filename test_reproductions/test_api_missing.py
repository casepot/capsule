#!/usr/bin/env python3
"""
Test reproduction demonstrating that no API layer exists in pyrepl3.
Shows what's missing and what clients would need.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_websocket_api_missing():
    """Show that WebSocket API doesn't exist."""
    print("\n=== Test: WebSocket API missing ===")
    
    try:
        # Try to import WebSocket API
        from src.api import WebSocketAPI
        print("✓ WebSocketAPI found")
    except ImportError as e:
        print(f"❌ No WebSocketAPI: {e}")
    
    # Check if api module exists at all
    api_path = Path(__file__).parent.parent / "src" / "api"
    if api_path.exists():
        files = list(api_path.glob("*.py"))
        if len(files) == 1 and files[0].name == "__init__.py":
            print("❌ API module exists but is empty (only __init__.py)")
        else:
            print(f"API files: {[f.name for f in files]}")
    else:
        print("❌ No src/api directory at all")


async def test_rest_api_missing():
    """Show that REST API doesn't exist."""
    print("\n=== Test: REST API missing ===")
    
    try:
        from src.api import RestAPI
        print("✓ RestAPI found")
    except ImportError:
        print("❌ No RestAPI implementation")
    
    # Check for any HTTP server components
    try:
        from src.api import APIServer
        print("✓ APIServer found")
    except ImportError:
        print("❌ No APIServer implementation")


async def test_client_needs():
    """Demonstrate what a client would need from the API."""
    print("\n=== Test: Client API requirements ===")
    
    print("\nA WebSocket client needs:")
    print("1. Connection endpoint: ws://localhost:8080/session")
    print("2. Message protocol:")
    print("   → Send: {type: 'execute', code: 'print(1)'}")
    print("   ← Receive: {type: 'output', data: '1\\n'}")
    print("   ← Receive: {type: 'result', value: None}")
    print("3. Session management:")
    print("   → Send: {type: 'create_session'}")
    print("   ← Receive: {type: 'session_created', session_id: 'uuid'}")
    print("4. Input handling:")
    print("   ← Receive: {type: 'input_request', prompt: 'Name: '}")
    print("   → Send: {type: 'input_response', data: 'Alice'}")
    
    print("\nA REST client needs:")
    print("1. POST /sessions - Create new session")
    print("2. POST /sessions/{id}/execute - Execute code")
    print("3. GET /sessions/{id}/status - Get session status")
    print("4. DELETE /sessions/{id} - Shutdown session")
    print("5. GET /health - Server health check")


async def test_current_usage_pattern():
    """Show the current (non-API) usage pattern."""
    print("\n=== Test: Current usage without API ===")
    
    from src.session.manager import Session
    from src.protocol.messages import ExecuteMessage, MessageType
    import time
    
    print("\nCurrent usage requires direct Python imports:")
    print("```python")
    print("from src.session.manager import Session")
    print("from src.protocol.messages import ExecuteMessage")
    print("")
    print("# Must be in same process")
    print("session = Session()")
    print("await session.start()")
    print("")
    print("# Direct message creation")
    print("msg = ExecuteMessage(id='1', timestamp=0, code='print(1)')")
    print("")
    print("# Direct async iteration")
    print("async for result in session.execute(msg):")
    print("    print(result)")
    print("```")
    
    print("\n❌ Problems with current approach:")
    print("- No network access (must be same process)")
    print("- No language interoperability (Python only)")
    print("- No concurrent client support")
    print("- No standard protocol (uses internal messages)")
    print("- No session discovery/management")


async def test_api_components_needed():
    """List the components needed for a complete API."""
    print("\n=== Test: Required API components ===")
    
    print("\n📁 src/api/ should contain:")
    print("├── __init__.py")
    print("├── websocket_server.py  # WebSocket endpoint")
    print("├── rest_server.py       # REST endpoints")
    print("├── protocol_adapter.py  # Convert HTTP/WS to internal protocol")
    print("├── session_router.py    # Route requests to sessions")
    print("├── auth.py             # Authentication (optional)")
    print("└── models.py           # API request/response models")
    
    print("\n📦 Dependencies needed:")
    print("- aiohttp or fastapi (web framework)")
    print("- websockets (WebSocket support)")
    print("- pydantic (already have)")
    print("- uvicorn (ASGI server)")
    
    print("\n🔌 Integration points:")
    print("- SessionPool for session management")
    print("- ExecuteMessage for code execution")
    print("- MessageType for result streaming")
    print("- InputHandler for interactive input")


async def test_example_websocket_client():
    """Show what a WebSocket client would look like."""
    print("\n=== Example: WebSocket client code ===")
    
    code = '''
import asyncio
import json
import websockets

async def pyrepl_client():
    """Example WebSocket client for PyREPL3 API."""
    
    # Connect to server
    async with websockets.connect("ws://localhost:8080/session") as ws:
        
        # Wait for session ready
        msg = json.loads(await ws.recv())
        session_id = msg["session_id"]
        print(f"Connected to session {session_id}")
        
        # Execute code
        await ws.send(json.dumps({
            "type": "execute",
            "code": "name = input('Name: '); print(f'Hello {name}')"
        }))
        
        # Handle responses
        while True:
            msg = json.loads(await ws.recv())
            
            if msg["type"] == "input_request":
                # Respond to input request
                await ws.send(json.dumps({
                    "type": "input_response",
                    "data": "Alice"
                }))
                
            elif msg["type"] == "output":
                print(f"Output: {msg['data']}")
                
            elif msg["type"] == "result":
                print(f"Result: {msg['value']}")
                break
                
            elif msg["type"] == "error":
                print(f"Error: {msg['message']}")
                break

asyncio.run(pyrepl_client())
'''
    
    print("WebSocket client example:")
    print(code)


async def main():
    """Run all API missing test reproductions."""
    print("=" * 60)
    print("API LAYER MISSING REPRODUCTION")
    print("=" * 60)
    
    # Test 1: WebSocket API missing
    await test_websocket_api_missing()
    
    # Test 2: REST API missing
    await test_rest_api_missing()
    
    # Test 3: Client needs
    await test_client_needs()
    
    # Test 4: Current usage pattern
    await test_current_usage_pattern()
    
    # Test 5: Components needed
    await test_api_components_needed()
    
    # Test 6: Example client
    await test_example_websocket_client()
    
    print("\n" + "=" * 60)
    print("SUMMARY: No API layer exists at all")
    print("Need: WebSocket + REST endpoints for client access")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
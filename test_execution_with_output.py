#!/usr/bin/env python3
"""Test execution with output."""
import asyncio
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.session.manager import Session
from src.protocol.messages import ExecuteMessage

async def test():
    print("Testing execution with output...")
    session = Session()
    await session.start()
    
    # Create execute message
    msg = ExecuteMessage(
        type="execute",
        id="test-exec",
        timestamp=time.time(),
        code="print('Hello from PyREPL3!')\nresult = 2 + 2\nprint(f'Result: {result}')\nresult",
        capture_source=True
    )
    
    print("\nExecuting code:")
    print(msg.code)
    print("\nReceiving messages:")
    
    messages = []
    async for message in session.execute(msg):
        print(f"  {message.type}: {getattr(message, 'data', getattr(message, 'value', ''))}")
        messages.append(message)
    
    print(f"\nTotal messages: {len(messages)}")
    await session.terminate()

asyncio.run(test())

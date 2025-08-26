#!/usr/bin/env python3
"""Test simple session execution."""
import asyncio
from src.session.manager import Session
from src.protocol.messages import ExecuteMessage
import time

async def test():
    print("Creating session...")
    session = Session()
    
    print("Starting session...")
    await session.start()
    print("Session started!")
    
    print("Executing code...")
    msg = ExecuteMessage(
        type="execute",
        id="test",
        timestamp=time.time(),
        code="print('Test')",
        capture_source=False
    )
    
    messages = []
    async for message in session.execute(msg):
        print(f"  Received: {message.type}")
        messages.append(message)
    
    print(f"Total messages: {len(messages)}")
    
    print("Terminating session...")
    await session.terminate()
    print("Done!")

asyncio.run(test())

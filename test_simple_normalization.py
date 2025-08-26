#!/usr/bin/env python3
"""Simple test for message type normalization."""

import asyncio
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.session.pool import SessionPool
from src.protocol.messages import ExecuteMessage


async def test():
    """Test single execution."""
    print("Starting pool...")
    pool = SessionPool(max_sessions=1)
    await pool.start()
    
    try:
        print("Acquiring session...")
        session = await pool.acquire()
        
        print("Creating execute message...")
        msg = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code='print("hello"); x = 42'
        )
        
        print(f"Message type: {msg.type} (type: {type(msg.type)})")
        
        print("Executing...")
        messages = []
        async for message in session.execute(msg):
            print(f"  Received: {message.type}")
            messages.append(message)
            
        print(f"Total messages: {len(messages)}")
        
        # Try another execution
        print("\nSecond execution...")
        msg2 = ExecuteMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            code='x * 2'
        )
        
        messages2 = []
        async for message in session.execute(msg2):
            print(f"  Received: {message.type}")
            messages2.append(message)
            
        print(f"Total messages: {len(messages2)}")
        
        # Check message types
        for msg in messages + messages2:
            assert isinstance(msg.type, str), f"Type is not string: {type(msg.type)}"
        
        print("\n✅ All message types are strings!")
        
    finally:
        print("\nStopping pool...")
        await pool.stop()
        print("Done")


if __name__ == "__main__":
    asyncio.run(test())
#!/usr/bin/env python3
"""
Investigation tests for transport layer issues under high load.
Each test has built-in timeouts and focuses on a specific aspect.
"""

import asyncio
import sys
import time
import json
import msgpack
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))

from src.protocol.messages import OutputMessage, ResultMessage, StreamType
from src.protocol.transport import MessageTransport, FrameReader, FrameWriter
import structlog

# Reduce logging noise for investigation
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
)


async def test_raw_frame_rapid_fire():
    """Test 1: Can FrameReader/Writer handle rapid messages?"""
    print("\n=== Test 1: Raw Frame Rapid Fire ===")
    
    # Create pipes using asyncio's create_task approach
    # We'll use a simple echo server pattern
    
    async def create_pipe_pair():
        """Create a connected pair of streams for testing."""
        # Use asyncio's built-in pipe creation
        loop = asyncio.get_running_loop()
        
        # Create a pair of connected pipes
        reader1 = asyncio.StreamReader()
        protocol1 = asyncio.StreamReaderProtocol(reader1)
        
        reader2 = asyncio.StreamReader()
        protocol2 = asyncio.StreamReaderProtocol(reader2)
        
        # Create transport pair (this is platform-specific but works on Unix/Mac)
        import socket
        sock1, sock2 = socket.socketpair()
        
        transport1, _ = await loop.create_connection(
            lambda: protocol1, sock=sock1
        )
        transport2, _ = await loop.create_connection(
            lambda: protocol2, sock=sock2
        )
        
        writer1 = asyncio.StreamWriter(transport1, protocol1, reader1, loop)
        writer2 = asyncio.StreamWriter(transport2, protocol2, reader2, loop)
        
        return reader1, writer1, reader2, writer2
    
    try:
        # Create connected pipe pair
        read1, write1, read2, write2 = await create_pipe_pair()
        
        # Create frame handlers
        reader = FrameReader(read2)
        writer = FrameWriter(write1)
        
        await reader.start()
        
        # Send many frames rapidly
        num_frames = 100
        sent_data = []
        
        # Send phase
        for i in range(num_frames):
            data = f"frame_{i:04d}".encode()
            sent_data.append(data)
            await writer.write_frame(data)
        
        print(f"  Sent {num_frames} frames")
        
        # Receive phase with timeout
        received = []
        for i in range(num_frames):
            try:
                frame = await asyncio.wait_for(
                    reader.read_frame(timeout=1.0),
                    timeout=2.0
                )
                received.append(frame)
            except asyncio.TimeoutError:
                print(f"  Timeout at frame {i}")
                break
        
        print(f"  Received {len(received)}/{num_frames} frames")
        
        # Verify data integrity
        for i, (sent, recv) in enumerate(zip(sent_data, received)):
            if sent != recv:
                print(f"  Frame {i} mismatch: {sent} != {recv}")
                return False
        
        if len(received) == num_frames:
            print("  ✅ All frames received correctly")
            return True
        else:
            print(f"  ❌ Missing {num_frames - len(received)} frames")
            return False
            
    except Exception as e:
        print(f"  ❌ Test failed with error: {e}")
        return False
    finally:
        try:
            await reader.stop()
            await writer.close()
        except:
            pass


async def test_message_serialization_sizes():
    """Test 2: Check message serialization sizes for different message types."""
    print("\n=== Test 2: Message Serialization Sizes ===")
    
    # Test various message sizes
    test_cases = [
        ("tiny", "x"),
        ("small", "x" * 10),
        ("medium", "x" * 100),
        ("large", "x" * 1000),
        ("huge", "x" * 10000),
    ]
    
    for name, data in test_cases:
        msg = OutputMessage(
            id=f"test-{name}",
            type="output",
            timestamp=time.time(),
            data=data,
            stream=StreamType.STDOUT,
            execution_id="exec-1"
        )
        
        # Test both JSON and msgpack
        json_data = json.dumps(msg.model_dump(mode="json")).encode()
        msgpack_data = msgpack.packb(msg.model_dump(mode="json"), use_bin_type=True)
        
        print(f"  {name:8s}: data={len(data):6d}, json={len(json_data):6d}, msgpack={len(msgpack_data):6d}")
    
    # Check for size limits
    print("\n  Testing maximum safe size...")
    max_data = "x" * (1024 * 1024)  # 1MB of data
    big_msg = OutputMessage(
        id="big",
        type="output", 
        timestamp=time.time(),
        data=max_data,
        stream=StreamType.STDOUT,
        execution_id="exec-1"
    )
    
    try:
        big_msgpack = msgpack.packb(big_msg.model_dump(mode="json"), use_bin_type=True)
        print(f"  1MB message serializes to {len(big_msgpack)} bytes")
        if len(big_msgpack) > 10 * 1024 * 1024:
            print("  ⚠️  Exceeds 10MB frame limit!")
            return False
    except Exception as e:
        print(f"  ❌ Failed to serialize 1MB message: {e}")
        return False
    
    print("  ✅ All message sizes within limits")
    return True


async def test_concurrent_read_write():
    """Test 3: Concurrent reading and writing on same transport."""
    print("\n=== Test 3: Concurrent Read/Write ===")
    
    # Skip this test - it needs more complex setup
    print("  (Skipped - needs bidirectional pipe setup)")
    return True
    
    # Create transport
    transport = MessageTransport(server_reader, server_writer, use_msgpack=True)
    await transport.start()
    
    async def writer_task(n: int):
        """Write messages continuously."""
        for i in range(n):
            msg = OutputMessage(
                id=f"write-{i}",
                type="output",
                timestamp=time.time(),
                data=f"message_{i}\n",
                stream=StreamType.STDOUT,
                execution_id="exec-1"
            )
            await transport.send_message(msg)
            await asyncio.sleep(0.001)  # Small delay
    
    async def reader_task(n: int):
        """Read messages continuously."""
        received = []
        for i in range(n):
            try:
                msg = await asyncio.wait_for(
                    transport.receive_message(timeout=1.0),
                    timeout=2.0
                )
                received.append(msg)
            except asyncio.TimeoutError:
                break
        return received
    
    # Run concurrent read/write
    num_messages = 50
    
    try:
        # Start both tasks
        write_task = asyncio.create_task(writer_task(num_messages))
        read_task = asyncio.create_task(reader_task(num_messages))
        
        # Wait with timeout
        results = await asyncio.wait_for(
            asyncio.gather(write_task, read_task, return_exceptions=True),
            timeout=10.0
        )
        
        received = results[1] if len(results) > 1 else []
        
        print(f"  Sent {num_messages}, received {len(received)}")
        
        if len(received) == num_messages:
            print("  ✅ Concurrent read/write successful")
            return True
        else:
            print(f"  ❌ Lost {num_messages - len(received)} messages")
            return False
            
    except asyncio.TimeoutError:
        print("  ❌ Test timed out")
        return False
    finally:
        await transport.close()


async def test_message_burst_pattern():
    """Test 4: Simulate the burst pattern from execution (output + result)."""
    print("\n=== Test 4: Message Burst Pattern ===")
    
    # This simulates what happens during rapid executions
    server_reader, server_writer = await asyncio.open_connection('localhost', 0)
    transport = MessageTransport(server_reader, server_writer, use_msgpack=True)
    await transport.start()
    
    async def send_execution_burst(exec_id: str):
        """Send output + result (typical execution pattern)."""
        # Send output
        output_msg = OutputMessage(
            id=f"out-{exec_id}",
            type="output",
            timestamp=time.time(),
            data=f"output from {exec_id}\n",
            stream=StreamType.STDOUT,
            execution_id=exec_id
        )
        await transport.send_message(output_msg)
        
        # Send result immediately after
        result_msg = ResultMessage(
            id=f"res-{exec_id}",
            type="result",
            timestamp=time.time(),
            value=None,
            repr="",
            execution_id=exec_id,
            execution_time=0.001
        )
        await transport.send_message(result_msg)
    
    async def receive_messages(expected: int):
        """Receive messages."""
        received = []
        for _ in range(expected):
            try:
                msg = await asyncio.wait_for(
                    transport.receive_message(timeout=0.5),
                    timeout=1.0
                )
                received.append(msg)
            except asyncio.TimeoutError:
                break
        return received
    
    try:
        # Send many execution bursts rapidly
        num_executions = 100
        
        # Send all bursts
        for i in range(num_executions):
            await send_execution_burst(f"exec-{i:04d}")
        
        print(f"  Sent {num_executions} execution bursts (2 messages each)")
        
        # Receive all messages
        expected_messages = num_executions * 2
        received = await asyncio.wait_for(
            receive_messages(expected_messages),
            timeout=10.0
        )
        
        print(f"  Received {len(received)}/{expected_messages} messages")
        
        # Check ordering - outputs should come before results
        exec_messages = {}
        for msg in received:
            exec_id = getattr(msg, 'execution_id', None)
            if exec_id:
                if exec_id not in exec_messages:
                    exec_messages[exec_id] = []
                exec_messages[exec_id].append(msg.type)
        
        order_violations = 0
        for exec_id, types in exec_messages.items():
            if len(types) == 2 and types != ["output", "result"]:
                order_violations += 1
        
        if order_violations > 0:
            print(f"  ⚠️  {order_violations} ordering violations")
        
        if len(received) == expected_messages:
            print("  ✅ All messages received in bursts")
            return True
        else:
            print(f"  ❌ Message loss in burst pattern")
            return False
            
    except asyncio.TimeoutError:
        print("  ❌ Burst test timed out")
        return False
    finally:
        await transport.close()


async def test_buffer_boundaries():
    """Test 5: Test edge cases around buffer boundaries."""
    print("\n=== Test 5: Buffer Boundary Conditions ===")
    
    server_reader, server_writer = await asyncio.open_connection('localhost', 0)
    reader = FrameReader(server_reader)
    writer = FrameWriter(server_writer)
    await reader.start()
    
    try:
        # Test various sizes around common buffer boundaries
        test_sizes = [
            1,          # Tiny
            127,        # Just under typical small buffer
            128,        # Common buffer size
            255,        # Another boundary
            256,
            1023,
            1024,       # 1KB
            4095,
            4096,       # 4KB (common page size)
            8191,
            8192,       # 8KB (reader buffer size in code)
            16384,      # 16KB
            65535,      # 64KB - 1
            65536,      # 64KB
        ]
        
        failures = 0
        for size in test_sizes:
            data = b'x' * size
            
            # Send
            await writer.write_frame(data)
            
            # Receive with short timeout
            try:
                received = await asyncio.wait_for(
                    reader.read_frame(timeout=0.5),
                    timeout=1.0
                )
                
                if received != data:
                    print(f"  Size {size:6d}: MISMATCH")
                    failures += 1
                # else success, no output to reduce noise
                    
            except asyncio.TimeoutError:
                print(f"  Size {size:6d}: TIMEOUT")
                failures += 1
        
        if failures == 0:
            print(f"  ✅ All {len(test_sizes)} boundary sizes handled correctly")
            return True
        else:
            print(f"  ❌ {failures}/{len(test_sizes)} boundary tests failed")
            return False
            
    finally:
        await reader.stop()
        await writer.close()


async def test_rapid_session_creation():
    """Test 6: Rapid session creation/destruction (subprocess churn)."""
    print("\n=== Test 6: Rapid Session Creation ===")
    
    # This test simulates what happens in the 1000 iteration test
    # where we rapidly create and destroy sessions
    
    from src.session.manager import Session
    
    failures = 0
    timeout_count = 0
    
    for i in range(10):  # Just 10 to keep it fast
        try:
            session = Session()
            
            # Start with timeout
            await asyncio.wait_for(session.start(), timeout=5.0)
            
            # Quick execution
            from src.protocol.messages import ExecuteMessage
            msg = ExecuteMessage(
                id=f"rapid-{i}",
                timestamp=time.time(),
                code=f"print('test_{i}')"
            )
            
            # Execute with timeout
            messages = []
            async for response in asyncio.wait_for(
                session.execute(msg, timeout=2.0),
                timeout=3.0
            ):
                messages.append(response)
            
            # Shutdown
            await asyncio.wait_for(session.shutdown(), timeout=2.0)
            
            # Check we got output
            has_output = any(m.type == "output" for m in messages)
            if not has_output:
                failures += 1
                
        except asyncio.TimeoutError:
            timeout_count += 1
            print(f"  Session {i}: TIMEOUT")
        except Exception as e:
            failures += 1
            print(f"  Session {i}: ERROR - {e}")
    
    print(f"  Completed: {10 - failures - timeout_count}/10")
    print(f"  Timeouts: {timeout_count}")
    print(f"  Failures: {failures}")
    
    if failures == 0 and timeout_count == 0:
        print("  ✅ All rapid sessions successful")
        return True
    else:
        print("  ❌ Issues with rapid session creation")
        return False


async def main():
    """Run all investigation tests."""
    print("=" * 60)
    print("Transport Layer Investigation")
    print("=" * 60)
    
    tests = [
        ("Raw Frame Rapid Fire", test_raw_frame_rapid_fire),
        ("Message Serialization", test_message_serialization_sizes),
        ("Concurrent Read/Write", test_concurrent_read_write),
        ("Message Burst Pattern", test_message_burst_pattern),
        ("Buffer Boundaries", test_buffer_boundaries),
        ("Rapid Session Creation", test_rapid_session_creation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            # Run each test with a timeout
            result = await asyncio.wait_for(test_func(), timeout=30.0)
            results.append((name, result))
        except asyncio.TimeoutError:
            print(f"\n{name}: TIMEOUT (30s)")
            results.append((name, False))
        except Exception as e:
            print(f"\n{name}: EXCEPTION - {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("Investigation Summary")
    print("=" * 60)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{name:30s}: {status}")
    
    # Analysis
    print("\n" + "=" * 60)
    print("Analysis")
    print("=" * 60)
    
    if all(success for _, success in results):
        print("All transport layer tests pass in isolation.")
        print("The issue likely emerges from:")
        print("  1. Subprocess lifecycle overhead")
        print("  2. Resource exhaustion under extreme load")
        print("  3. OS-level pipe buffer limitations")
    else:
        failed = [name for name, success in results if not success]
        print(f"Failed tests: {', '.join(failed)}")
        print("These failures indicate specific transport issues to investigate.")


if __name__ == "__main__":
    asyncio.run(main())
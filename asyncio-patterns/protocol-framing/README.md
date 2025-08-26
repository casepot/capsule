# Protocol Framing: The Two-Phase Read Problem

## The Pattern

Length-prefixed protocols are ubiquitous in network programming:

```
[LENGTH: 4 bytes][DATA: N bytes]
```

Examples:
- HTTP with Content-Length
- MessagePack with length prefix
- Protocol Buffers with delimited messages
- Custom JSON protocols (like exec-py)

## The Two-Phase Read Requirement

Every frame requires **two sequential reads**:

1. **Phase 1: Read Header** (fixed size)
   - Read 4 bytes
   - Decode to get body length N
   - May need to wait for data

2. **Phase 2: Read Body** (variable size)
   - Read N bytes
   - Parse the actual message
   - May need to wait for data

## Why It Breaks With Event

For 4 frames, we have 8 sequential reads:

```
Read 1: Frame 1 header (may wait/clear event)
Read 2: Frame 1 body   (may wait/clear event)
Read 3: Frame 2 header (may wait/clear event) ← Often deadlocks here
Read 4: Frame 2 body   (may wait/clear event)
... continues ...
```

Each read is a "consumer" of write notifications. The problem:

- **Who clears the event?** Header reader or body reader?
- **If header clears:** Body reader might deadlock
- **If body clears:** Next header reader might deadlock
- **If nobody clears:** All future waits return immediately

## The Exact Failure Sequence

```python
# Writer dumps all frames at once
writer.write_frame(frame1)  # Buffer: [frame1]
writer.write_frame(frame2)  # Buffer: [frame1, frame2]
writer.write_frame(frame3)  # Buffer: [frame1, frame2, frame3]
writer.write_frame(frame4)  # Buffer: [frame1, frame2, frame3, frame4]

# Reader reads sequentially
read_header(4)  # Has data, no wait needed
read_body(N)    # Has data, no wait needed
# ... frames 2-4 read successfully ...

# Now reader waits for frame 5
read_header(4)  # No data, needs to wait
                # But event state is wrong!
                # DEADLOCK
```

## Demonstrations

### See Protocol Framing in Action

```bash
python framing_analysis.py
```

This shows:
- Buffer state visualization
- Two-phase read pattern
- Why single Event fails
- How Condition solves it

### Experience the Deadlock

```bash
python deadlock_scenarios.py
```

This demonstrates:
- The exact test_working_manager.py scenario
- How batch writes trigger deadlock
- Timing dependencies

## The Solution: Condition Variables

### Why Condition Works for Framing

```python
class ProtocolReader:
    def __init__(self):
        self.buffer = bytearray()
        self.read_pos = 0
        self.condition = asyncio.Condition()
    
    async def read_frame(self):
        # Phase 1: Read header
        header = await self.read_exact(4)
        length = struct.unpack(">I", header)[0]
        
        # Phase 2: Read body
        body = await self.read_exact(length)
        return json.loads(body)
    
    async def read_exact(self, n):
        async with self.condition:
            # Wait for enough data
            await self.condition.wait_for(
                lambda: len(self.buffer) >= self.read_pos + n
            )
        
        # Read outside lock
        data = self.buffer[self.read_pos:self.read_pos + n]
        self.read_pos += n
        return data
```

### Key Advantages

1. **No ownership ambiguity** - No explicit clear()
2. **State-based** - "Buffer has N bytes" not "bytes arrived"
3. **Independent predicates** - Each read checks its own requirement
4. **Composable** - Works for any number of sequential reads

## Common Protocol Patterns

### Pattern 1: Fixed Header + Variable Body
```
[4 bytes: length][N bytes: data]
```
**Reads:** 2 per message
**Synchronization:** Condition or real streams

### Pattern 2: Type-Length-Value (TLV)
```
[1 byte: type][2 bytes: length][N bytes: value]
```
**Reads:** 2 per message (header is 3 bytes)
**Synchronization:** Condition or real streams

### Pattern 3: Chunked Transfer
```
[4 bytes: chunk_size][N bytes: chunk][4 bytes: chunk_size]...
```
**Reads:** 2 per chunk, variable chunks
**Synchronization:** Definitely need Condition

## Testing Protocol Implementations

### Critical Test Cases

1. **Batch Write Test**
   ```python
   # Write all frames at once
   for frame in frames:
       writer.write_frame(frame)
   
   # Then read sequentially
   for _ in range(len(frames)):
       reader.read_frame()
   ```

2. **Interleaved Test**
   ```python
   # Write and read alternately
   writer.write_frame(frame1)
   reader.read_frame()
   writer.write_frame(frame2)
   reader.read_frame()
   ```

3. **Partial Write Test**
   ```python
   # Write only header
   writer.write(header)
   # Reader should wait
   # Write body
   writer.write(body)
   # Reader should proceed
   ```

## Alternative Solutions

### Real Streams (Recommended)
```python
# Use OS-provided synchronization
sock1, sock2 = socket.socketpair()
# Create asyncio streams
# OS handles all synchronization
```

### Queue-Based
```python
# Each frame is a complete message
frames_queue = asyncio.Queue()
await frames_queue.put(complete_frame)
frame = await frames_queue.get()
```

### Channel Pattern
```python
# Separate channel per direction
tx_channel = asyncio.Queue()
rx_channel = asyncio.Queue()
```

## Summary

**The Fundamental Theorem:**
> Protocol framing is about state (buffer has N bytes), not occurrence (bytes arrived). Therefore, use Condition for protocol framing.

**Key Rules:**
1. Never use Event with clear for protocol framing
2. Always test batch write scenarios
3. Consider socketpair over mocks when possible
4. Each read phase needs independent synchronization

---

*The two-phase read pattern is fundamental to network protocols. Understanding its synchronization requirements prevents entire classes of deadlock bugs.*
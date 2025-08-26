# Output Streaming Simplification Planning Prompt

## Your Mission

You are tasked with simplifying the over-engineered output streaming system. Currently, PyREPL3 uses complex async buffering with periodic flushing that causes reliability issues, especially with large outputs. Both pyrepl2 and exec-py use simpler approaches that work better. The goal is to maintain real-time streaming while reducing complexity.

## Context Gathering Requirements

Before implementing, you MUST understand:

### 1. Problem History (Problem Archaeology)
- **Current Issues**: Large outputs (>1MB) sometimes return 0 bytes
- **Complexity Source**: OutputCapture with async locks, periodic flushing, buffering
- **pyrepl2 Success**: Simple StringIO with redirect_stdout/redirect_stderr
- **exec-py Pattern**: Direct streaming without complex buffering
- **Lesson**: Simpler is often better for output handling

### 2. Existing Infrastructure (Architecture Recognition)
- **OutputCapture Class**: Complex async write with buffering (worker.py:28-115)
- **AsyncStdout/AsyncStderr**: Wrappers that create tasks for writes
- **ThreadSafeOutput**: In executor.py for thread-to-async bridging
- **Message Protocol**: OutputMessage for streaming data to client

### 3. Constraints That Cannot Be Violated (Risk Illumination)
- **Real-time Streaming**: Output must appear as it's generated
- **Thread Safety**: Must work from ThreadedExecutor threads
- **No Data Loss**: All output must be captured
- **Order Preservation**: Output order must match execution order

## Planning Methodology

### Phase 1: Analysis (30% effort)
<context_gathering>
Goal: Understand why current approach is complex and unreliable
Stop when: You identify the essential vs accidental complexity
Depth: Compare OutputCapture with pyrepl2's StringIO approach
</context_gathering>

Investigate:
1. Current OutputCapture buffering logic and flush timing
2. Why async tasks are created for each write
3. pyrepl2's redirect_stdout approach (simpler)
4. Thread-safe requirements from ThreadedExecutor

### Phase 2: Solution Design (50% effort)

Consider these approaches:

**Approach A: StringIO with Post-Execution Send**
- Use io.StringIO with redirect_stdout/redirect_stderr
- Send complete output after execution finishes
- Pros: Dead simple, proven by pyrepl2
- Cons: No real-time streaming

**Approach B: Direct Thread-Safe Streaming (Recommended)**
- Send each write directly without buffering
- Use asyncio.run_coroutine_threadsafe from threads
- Pros: Real-time, simple, no buffering complexity
- Cons: More messages, potential overhead

**Approach C: Simple Line Buffering**
- Buffer only until newline, then send
- Reduces message count while maintaining readability
- Pros: Balance between approaches
- Cons: Still some buffering logic

### Phase 3: Risk Assessment (20% effort)
- **Risk**: Message flooding with many small writes
  - Mitigation: Coalesce writes within same event loop iteration
- **Risk**: Thread safety issues
  - Mitigation: Use proven asyncio.run_coroutine_threadsafe
- **Risk**: Output interleaving from concurrent executions
  - Mitigation: Include execution_id in all messages

## Output Requirements

Your plan must include:

### 1. Executive Summary (5 sentences max)
- Why current approach is over-complex
- Which simplification approach to use
- How it maintains real-time streaming
- Expected reliability improvement

### 2. Technical Approach

**Option A: StringIO Approach (Like pyrepl2)**
```python
def execute_code(self, code: str) -> None:
    """Execute with simple output capture."""
    import io
    from contextlib import redirect_stdout, redirect_stderr
    
    # Create buffers
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    
    try:
        # Redirect and execute
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            exec(compile(code, "<session>", "exec"), self._namespace)
        
        # Send complete output after execution
        if stdout_data := stdout_buffer.getvalue():
            asyncio.run_coroutine_threadsafe(
                self._send_output(stdout_data, StreamType.STDOUT),
                self._loop
            ).result()  # Wait for send
            
        if stderr_data := stderr_buffer.getvalue():
            asyncio.run_coroutine_threadsafe(
                self._send_output(stderr_data, StreamType.STDERR),
                self._loop
            ).result()
            
    except Exception as e:
        # Capture exception to stderr
        with redirect_stderr(stderr_buffer):
            import traceback
            traceback.print_exc()
        
        if stderr_data := stderr_buffer.getvalue():
            asyncio.run_coroutine_threadsafe(
                self._send_output(stderr_data, StreamType.STDERR),
                self._loop
            ).result()
```

**Option B: Direct Streaming (Recommended)**
```python
class DirectStreamOutput:
    """Simple direct output streaming."""
    
    def __init__(self, transport, stream_type, execution_id, loop):
        self._transport = transport
        self._stream_type = stream_type
        self._execution_id = execution_id
        self._loop = loop
    
    def write(self, data: str) -> int:
        """Send output immediately."""
        if not data:
            return 0
            
        # Create message
        message = OutputMessage(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            data=data,
            stream=self._stream_type,
            execution_id=self._execution_id,
        )
        
        # Send from thread using thread-safe method
        future = asyncio.run_coroutine_threadsafe(
            self._transport.send_message(message),
            self._loop
        )
        
        # Don't wait (non-blocking)
        # future.result() would make it blocking
        
        return len(data)
    
    def flush(self) -> None:
        """No buffering, nothing to flush."""
        pass
```

**Option C: Line-Buffered Approach**
```python
class LineBufferedOutput:
    """Buffer until newline for efficiency."""
    
    def __init__(self, transport, stream_type, execution_id, loop):
        self._transport = transport
        self._stream_type = stream_type
        self._execution_id = execution_id
        self._loop = loop
        self._buffer = []
    
    def write(self, data: str) -> int:
        """Buffer and send on newlines."""
        if not data:
            return 0
        
        self._buffer.append(data)
        
        # Send if we have a newline
        if '\n' in data:
            full_data = ''.join(self._buffer)
            self._buffer = []
            
            # Send line
            message = OutputMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                data=full_data,
                stream=self._stream_type,
                execution_id=self._execution_id,
            )
            
            asyncio.run_coroutine_threadsafe(
                self._transport.send_message(message),
                self._loop
            )
        
        return len(data)
    
    def flush(self) -> None:
        """Send any buffered data."""
        if self._buffer:
            data = ''.join(self._buffer)
            self._buffer = []
            # Send remaining data...
```

### 3. Migration Strategy
1. Remove OutputCapture class entirely
2. Replace with chosen simpler approach
3. Update ThreadedExecutor to use new output class
4. Remove AsyncStdout/AsyncStderr wrappers
5. Test with various output patterns

### 4. Test Plan
```python
async def test_large_output_streaming():
    """Test that large outputs stream correctly."""
    session = Session()
    await session.start()
    
    # Generate large output
    code = """
for i in range(10000):
    print(f"Line {i}: " + "x" * 100)
"""
    
    output_received = []
    message = ExecuteMessage(id="large-1", timestamp=0, code=code)
    
    async for msg in session.execute(message):
        if msg.type == MessageType.OUTPUT:
            output_received.append(msg.data)
    
    # Verify all output received
    full_output = ''.join(output_received)
    assert full_output.count("Line") == 10000
    assert len(full_output) > 1_000_000  # Over 1MB
```

## Calibration

<context_gathering>
- Search depth: LOW (problem is well understood)
- Maximum tool calls: 5-10
- Early stop: Once you confirm complexity source
</context_gathering>

## Non-Negotiables

1. **No Data Loss**: All output must be captured
2. **Thread Safety**: Must work from executor threads
3. **Order Preservation**: Output order matches execution
4. **Execution ID**: All messages tagged with execution_id

## Success Criteria

Before finalizing your plan, verify:
- [ ] Simpler approach identified and justified
- [ ] Thread safety mechanism specified
- [ ] Large output handling tested
- [ ] Migration path from current system clear
- [ ] Performance implications understood

## Additional Guidance

- Start with the simplest approach that could work
- pyrepl2's StringIO approach is proven but lacks real-time
- Direct streaming is simple and real-time
- Don't recreate the complex buffering - it was the problem
- Test with print-heavy code, large outputs, and rapid outputs
- Remember: The current complexity wasn't necessary
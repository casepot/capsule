# Event-Driven Patterns in PyREPL3

## Pattern 2: Session Manager Event-Driven Cancellation

This document describes the event-driven cancellation pattern used in the Session Manager to eliminate polling and improve responsiveness.

### Architecture

The Session Manager uses an event-driven cancellable wait pattern with:
- Per-session cancel event (`asyncio.Event`)
- Monotonic deadline tracking  
- `asyncio.wait()` with FIRST_COMPLETED to wait on both queue.get() and cancel event

This approach eliminates the need for periodic wakeups to check for cancellation, resulting in:
- Zero idle CPU usage during message waits
- Immediate cancellation response (<50ms)
- Cleaner, more maintainable code

### How It Works

The core mechanism is the `_wait_for_message_cancellable()` method that:
1. Creates two async tasks: one for queue.get(), one for cancel event wait
2. Uses `asyncio.wait()` to wait for whichever completes first
3. Properly cleans up the other task when one completes

```python
async def _wait_for_message_cancellable(
    self,
    queue: asyncio.Queue[Message],
    timeout: Optional[float] = None,
) -> Message:
    cancel_ev = self._cancel_event
    deadline = (time.monotonic() + timeout) if timeout else None
    
    queue_get = asyncio.create_task(queue.get())
    cancel_wait = asyncio.create_task(cancel_ev.wait())
    
    try:
        # Wait for either message or cancellation
        done, _ = await asyncio.wait(
            {queue_get, cancel_wait},
            return_when=asyncio.FIRST_COMPLETED
        )
        
        if queue_get in done:
            return queue_get.result()
        else:
            raise asyncio.CancelledError("Session cancelled/terminating")
    finally:
        # Clean up tasks
        for t in (queue_get, cancel_wait):
            if not t.done():
                t.cancel()
```

### Metrics

Optional metrics can be enabled for monitoring:

```python
from src.session.config import SessionConfig
from src.session.manager import Session

config = SessionConfig(enable_metrics=True)
session = Session(config=config)

# Available metrics
session._metrics = {
    'cancel_event_triggers': 0,  # Number of times cancel event fired
    'executions_cancelled': 0,    # Number of executions cancelled
}
```

### Testing

Run the event-driven cancellation tests:

```bash
uv run pytest tests/test_event_driven_cancellation.py -v
```

Key test scenarios:
- Immediate cancellation response (<50ms)
- No message loss
- Proper timeout behavior
- Metrics collection

## Pattern 5: SessionPool Event-Driven Warmup

### Problem

The SessionPool used a fixed 10-second polling loop to maintain minimum idle sessions:
- 6 unnecessary wakeups per minute in idle state
- Up to 10s delay in replenishing sessions after demand
- CPU waste from polling when pool is at watermark

### Solution

Replaced polling with event-driven warmup that triggers on actual demand:

```python
async def _warmup_worker(self) -> None:
    """Event-driven background task to maintain minimum idle sessions."""
    self._warmup_needed.set()  # Initial trigger
    
    while not self._shutdown:
        # Wait for warmup signal (no polling!)
        await self._warmup_needed.wait()
        self._warmup_needed.clear()
        
        # Coalesce multiple triggers by looping until satisfied
        while not self._shutdown:
            if idle_count >= min_idle:
                break  # Watermark satisfied
            
            # Create sessions to reach watermark
            await create_sessions(needed)
            await asyncio.sleep(0)  # Yield control

def _check_warmup_needed(self) -> None:
    """Trigger warmup if below watermark."""
    if self._idle_sessions.qsize() < self._config.min_idle:
        self._warmup_needed.set()
```

### Trigger Points

Warmup is triggered when watermark violations occur:
- After `acquire()` takes from idle pool
- After `release()` removes a dead session  
- After health check removes timed-out sessions
- After recycle failure removes a session

### Metrics

New metrics track warmup efficiency:
```python
warmup_triggers: int           # Number of trigger events
warmup_loop_iterations: int     # Total iteration count
sessions_created_from_warmup: int  # Sessions created by warmup
warmup_efficiency: float        # iterations/triggers ratio
```

### Results

- **Idle wakeups**: 6/min → <0.1/min (60x reduction)
- **Response time**: 10s worst case → immediate (<100ms)
- **CPU usage**: Measurable reduction in idle state
- **Code clarity**: Event-driven is explicit about causality

### Testing

```bash
uv run pytest tests/test_pool_event_driven_warmup.py -v
```

Key test scenarios:
- Warmup triggers on low idle
- Event coalescing efficiency
- Health check integration
- Performance validation (<0.1 iterations/min idle)

### Future Improvements

This is part of a larger effort to replace polling patterns with event-driven mechanisms throughout PyREPL3:

1. ✅ **Pattern 2**: Session Manager message timeouts (COMPLETE)
2. ✅ **Pattern 5**: Session Pool warmup loop (COMPLETE)
3. 🔜 **Pattern 6**: Rate limiter token replenishment  
4. 🔜 **Pattern 1**: Session Pool health check (hybrid approach)
5. 🔜 **Pattern 4**: Frame reader buffer management
6. 🔜 **Pattern 3**: Worker input response routing

Each pattern follows the same principles:
- Zero polling in steady state
- Immediate response to events
- Clean task management
- Proper resource cleanup
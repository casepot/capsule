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

### Future Improvements

This is part of a larger effort to replace polling patterns with event-driven mechanisms throughout PyREPL3:

1. ✅ **Pattern 2**: Session Manager message timeouts (COMPLETE)
2. 🔜 **Pattern 5**: Session Pool warmup loop
3. 🔜 **Pattern 6**: Rate limiter token replenishment  
4. 🔜 **Pattern 1**: Session Pool health check (hybrid approach)
5. 🔜 **Pattern 4**: Frame reader buffer management
6. 🔜 **Pattern 3**: Worker input response routing

Each pattern follows the same principles:
- Zero polling in steady state
- Immediate response to events
- Clean task management
- Proper resource cleanup
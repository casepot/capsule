# Concurrency Patterns and Deadlocks

## The Third Task Problem

The test `test_reproductions/test_pool_blocking.py` shows that the third concurrent task blocks. Investigate:

- `src/session/pool.py:127-180` - acquire() method logic
- `src/session/pool.py:200-275` (if exists) - ensure_min_sessions() implementation

### Pattern to Look For

```python
# Deadlock pattern:
async with self._lock:
    # Check state
    if need_more_sessions:
        # Create session (BLOCKS waiting for same lock!)
        await create_session()
```

### Solution Pattern from Planning

```python
# Lock-free task creation:
async with self._lock:
    # Create tasks but don't await
    tasks = [create_task(create_session()) for _ in range(n)]

# Await outside lock
results = await gather(*tasks)

async with self._lock:
    # Update state with results
```

## Async Context Bridging

Study how sync thread code interacts with async infrastructure:

- `src/subprocess/executor.py:42-45` - asyncio.run_coroutine_threadsafe
- `src/subprocess/executor.py:96-103` - Thread→async for input

### Questions to Investigate

1. What happens to exceptions crossing the sync/async boundary?
2. How are threading.Event and asyncio.Event different?
3. Could asyncio.to_thread be used instead of manual threading?

## Event Loop Management

The worker runs in `asyncio.run(main())` but user code might create its own loops:

- `src/subprocess/worker.py:580` - Main event loop
- User code doing `asyncio.run()` inside execution

### Exploration Points

- What happens with nested event loops?
- Could we detect and reuse existing loops?
- How does this affect async library compatibility?

## Message Routing Concurrency

Trace concurrent message flow:

- `src/subprocess/worker.py:478-511` - Message receive loop
- Non-blocking execution via `asyncio.create_task` (line 493)

### Race Conditions to Consider

1. INPUT_RESPONSE arriving before INPUT request registers handler
2. Multiple executions with interleaved I/O
3. Shutdown during active execution
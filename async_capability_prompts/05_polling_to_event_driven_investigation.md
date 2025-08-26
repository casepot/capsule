# Polling-to-Event-Driven Pattern Investigation Prompt

## Your Mission

You are tasked with investigating and planning the systematic replacement of polling patterns with event-driven architectures throughout PyREPL3. This investigation must identify which patterns are appropriate for replacement, provide specific implementation guidance, and ensure no regressions in functionality or reliability.

## Context Gathering Requirements

Before planning replacements, you MUST thoroughly understand:

### 1. Problem History (Archaeology)
- **Previous Pattern**: Event-driven output handling was successfully implemented (Option B: asyncio.Queue with flush sentinels)
- **Key Lesson**: Event-driven patterns eliminate timing heuristics and provide deterministic guarantees
- **Success Story**: Replaced polling queue.Queue with event-driven asyncio.Queue, achieving 100% ordering guarantee
- **Invariant Discovered**: Event loops must remain responsive; blocking operations kill performance

### 2. Existing Infrastructure (Recognition)
The following polling patterns have been identified:

#### Pattern 1: Session Pool Health Check Loop
**Location**: `src/session/pool.py:400-404`
```python
async def _health_check_loop(self) -> None:
    while not self._shutdown:
        await asyncio.sleep(self._config.health_check_interval)  # Default 30s
        # Check idle sessions...
```
**Current Behavior**: Fixed 30-second interval health checks regardless of activity

#### Pattern 2: Session Manager Message Timeout Chunks  
**Location**: `src/session/manager.py:266`
```python
msg = await asyncio.wait_for(
    queue.get(),
    timeout=min(remaining, 1.0) if remaining else 1.0  # 1-second chunks
)
```
**Current Behavior**: Checks for messages in 1-second increments instead of waiting for exact timeout

#### Pattern 3: Worker Input Response Routing
**Location**: `src/subprocess/worker.py:494-499`
```python
elif message.type == MessageType.INPUT_RESPONSE:
    # Route input response to active executor
    if self._active_executor:
        self._active_executor.handle_input_response(...)
```
**Current Behavior**: Central message loop routes to executor; executor could be notified directly

#### Pattern 4: Frame Reader Buffer Management
**Location**: `src/protocol/transport.py:53`
```python
data = await asyncio.wait_for(self._reader.read(8192), timeout=1.0)
```
**Current Behavior**: 1-second polling timeout even when no data expected

#### Pattern 5: Session Pool Warmup Loop
**Location**: `src/session/pool.py:389-394`
```python
async def _warmup_loop(self) -> None:
    while not self._shutdown:
        await self.ensure_min_sessions()
        await asyncio.sleep(10.0)  # Check every 10 seconds
```
**Current Behavior**: Fixed 10-second intervals instead of demand-driven

#### Pattern 6: Rate Limiter Token Replenishment
**Location**: `src/protocol/framing.py:175`
```python
while self._tokens < 1:
    await asyncio.sleep(1.0 / self._max_rate)
    # Recalculate tokens...
```
**Current Behavior**: Polling sleep loop for token availability

### 3. Constraints That Cannot Be Violated
- **Message Ordering**: Event-driven changes must preserve strict message ordering guarantees
- **Backpressure**: Systems must handle overload gracefully without dropping messages
- **Shutdown Safety**: All patterns must support clean shutdown without hanging
- **Resource Limits**: Event-driven patterns must not create unbounded resource growth
- **Compatibility**: API contracts must remain unchanged

## Investigation Methodology

### Phase 1: Pattern Analysis (30% effort)
<context_gathering>
Goal: Understand WHY each polling pattern exists
Stop when: Root cause and original design intent are clear
Depth: Deep - trace git history if needed
</context_gathering>

For each pattern, determine:
- **Original Intent**: Why was polling chosen?
- **Hidden Dependencies**: What relies on the timing behavior?
- **Failure Modes**: What happens if timing changes?

### Phase 2: Event-Driven Alternatives (40% effort)

Consider these event-driven patterns:

#### For Health Checks (Pattern 1)
- **Option A: Activity-Based Triggers**: Check health after N operations or errors
- **Option B: Condition Variables**: Wake on state changes requiring health check
- **Option C: Hybrid**: Baseline interval with activity triggers

#### For Message Timeouts (Pattern 2)
- **Option A: Single Wait**: Use full timeout without chunking
- **Option B: Cancellable Tasks**: Create cancellable wait task
- **Option C: Event Notification**: Direct notification on message arrival

#### For Input Routing (Pattern 3)
- **Option A: Direct Futures**: Executor creates future, worker completes it
- **Option B: Condition Variables**: Worker signals specific condition
- **Option C: Dedicated Queues**: Per-executor response queues

#### For Frame Reader (Pattern 4)
- **Option A: No Timeout**: Read indefinitely until shutdown signal
- **Option B: Selective Timeout**: Only timeout when expecting data
- **Option C: Event-Driven EOF**: Use reader.at_eof() checks

#### For Warmup Loop (Pattern 5)
- **Option A: Demand-Driven**: Trigger warmup on acquisition attempts
- **Option B: Predictive**: Use usage patterns to predict needs
- **Option C: Watermark-Based**: Trigger when pool drops below threshold

#### For Rate Limiter (Pattern 6)
- **Option A: Timer Tasks**: Schedule replenishment tasks
- **Option B: Event Scheduling**: Use loop.call_later for precise timing
- **Option C: Continuous Flow**: Calculate tokens on demand

### Phase 3: Risk Assessment (20% effort)

For each replacement, identify:

#### Performance Risks
- Latency changes (better or worse?)
- CPU usage patterns
- Memory allocation differences
- Event loop congestion

#### Correctness Risks
- Race conditions from timing changes
- Starvation possibilities
- Deadlock scenarios
- Message ordering violations

#### Operational Risks
- Debugging complexity
- Monitoring/observability changes
- Error handling modifications
- Rollback complexity

### Phase 4: Implementation Planning (10% effort)

## Output Requirements

Your investigation must produce:

### 1. Pattern Prioritization Matrix
| Pattern | Impact | Difficulty | Risk | Priority | Recommendation |
|---------|--------|------------|------|----------|----------------|
| [Name]  | H/M/L  | H/M/L      | H/M/L| 1-6      | Replace/Keep/Hybrid |

### 2. For Each "Replace" Recommendation

#### Implementation Specification
```python
# Current Pattern
[Show current code]

# Proposed Replacement  
[Show new event-driven code]

# Key Changes
- [Change 1]: [Rationale]
- [Change 2]: [Rationale]
```

#### Migration Strategy
1. **Phase 1**: [What to do first]
2. **Phase 2**: [Next steps]
3. **Rollback Point**: [How to revert if needed]

### 3. Success Validation

#### Performance Metrics
- Metric: [Name] - Current: [Value] - Target: [Value]
- Test: [How to measure]

#### Correctness Tests
```python
async def test_[pattern]_correctness():
    # Specific test ensuring no regression
    pass
```

#### Monitoring Points
- Log: [What to log for observability]
- Metric: [What to measure in production]
- Alert: [What conditions warrant alerts]

## Calibration

<context_gathering>
- Search depth: HIGH (need deep understanding of timing dependencies)
- Tool calls: UNLIMITED (comprehensive investigation required)
- Early stop: When all 6 patterns have clear recommendations
</context_gathering>

## Non-Negotiables

1. **No Message Loss**: Every message must be delivered exactly once
2. **Clean Shutdown**: All patterns must support graceful termination
3. **Backward Compatibility**: External API behavior must not change
4. **Resource Bounds**: No unbounded growth in memory or handles
5. **Performance**: No degradation in latency or throughput

## Success Criteria

The investigation is complete when you can:
- [ ] Explain WHY each polling pattern currently exists
- [ ] Provide SPECIFIC event-driven alternatives
- [ ] Identify ALL risks of replacement
- [ ] Define MEASURABLE success metrics
- [ ] Create REVERSIBLE migration plans

## Additional Guidance

### Event-Driven Patterns Reference

**Condition Variables**: Best for waiting on state changes
```python
condition = asyncio.Condition()
async with condition:
    await condition.wait_for(lambda: state_changed)
```

**Futures**: Best for one-time results
```python
future = asyncio.Future()
# Producer: future.set_result(value)
# Consumer: result = await future
```

**Events**: Best for simple signaling
```python
event = asyncio.Event()
# Producer: event.set()
# Consumer: await event.wait()
```

**Queues**: Best for stream processing
```python
queue = asyncio.Queue()
# Producer: await queue.put(item)
# Consumer: item = await queue.get()
```

**Call Later**: Best for scheduled tasks
```python
loop.call_later(delay, callback)
loop.call_at(when, callback)
```

### Common Pitfalls to Avoid

1. **Event Loop Blocking**: Never block the event loop with CPU-intensive work
2. **Thundering Herd**: Avoid waking all waiters simultaneously
3. **Lost Wakeups**: Ensure signals aren't lost between check and wait
4. **Cleanup Leaks**: Always clean up scheduled tasks and futures
5. **Cancellation Safety**: Handle CancelledError appropriately

## Critical Cross-Cutting Concerns

Before investigating individual patterns, you MUST understand these system-wide implications:

### 1. Shutdown Coordination Cascade
**Issue**: All patterns use `while not self._shutdown` - converting to events creates complex cancellation dependencies
**Impact**: Frame Reader shutdown → Message receives → Session health checks → Pool cleanup
**Required Solution**: Unified shutdown signaling mechanism that works across all event patterns

### 2. Protocol Liveness Detection Chain  
**Issue**: The 1-second timeouts form a liveness detection chain, not just polling
```
Frame Reader (1s) → Detects dead connections
    ↓
Message Timeout (1s chunks) → Enables cancellation  
    ↓
Health Check (30s) → Identifies stuck sessions
```
**Impact**: Removing any timeout breaks downstream detection
**Required Solution**: Alternative liveness detection that preserves the chain

### 3. Resource Lifecycle Interdependencies
**Issue**: Components depend on each other's timing
- Warmup creates sessions → Health check monitors them
- Rate limiter controls flow → Frame reader consumes it
**Impact**: Demand-driven warmup could starve health checks; event-driven reader could overwhelm limiter
**Required Solution**: Coordination protocol between interdependent components

### 4. Event Loop Congestion Risk
**Issue**: Converting all 6 patterns means all callbacks compete for the same event loop
**Impact**: No natural throttling, thundering herd risk, single callback blocks all patterns
**Required Solution**: Priority scheduling or separate event loops for critical paths

### 5. Hidden Timing Contracts
**Issue**: 1-second chunks might provide hidden cancellation points
```python
# Current: Implicit cancellation check every second
timeout=min(remaining, 1.0)  # Hidden: check should_cancel() every iteration
```
**Impact**: Event-driven could lose cancellation responsiveness
**Required Solution**: Explicit cancellation mechanism in event-driven design

### 6. Observability and Debugging Collapse
**Issue**: Polling is predictable ("runs every 30s"), events are opaque ("runs when needed")
**Impact**: Cannot verify health checks are running, cannot debug timing issues
**Required Solution**: New observability framework with event metrics and tracing

### 7. Error Recovery Pattern Divergence
**Issue**: Polling has natural retry with backoff, events need explicit recovery
**Impact**: Missed events don't auto-retry, errors could cause permanent failure
**Required Solution**: Event replay mechanism or fallback to polling on errors

### 8. State Consistency Boundaries
**Issue**: Polling provides atomic iterations, events create race conditions
**Impact**: Concurrent health check + warmup + acquisition = inconsistent state
**Required Solution**: State machine or transaction boundaries for event handlers

### Interdependency Map
```
┌─────────────────────────────────────────────────────────────┐
│                     Event Loop (Shared)                      │
├──────────────┬──────────────┬───────────────┬──────────────┤
│Frame Reader  │Message Queue │Session Pool   │Rate Limiter  │
│   (1s)       │   (1s)       │               │              │
│     ↓        │      ↓       │      ↓        │      ↓       │
│ Liveness ────┼─> Timeout ───┼─> Health  <───┼─ Flow Ctrl   │
│     ↓        │      ↓       │      ↓        │      ↓       │
│   Data ──────┼─> Messages ──┼─> Sessions <──┼─ Throttle    │
│              │              │      ↑        │              │
│              │              │   Warmup      │              │
└──────────────┴──────────────┴───────────────┴──────────────┘

Dependencies:
- Frame Reader timeout enables message timeout cancellation
- Message routing depends on frame reading
- Health checks need warmed sessions
- Rate limiter prevents reader overwhelming system
- All share same event loop (congestion risk)
```

## Investigation Triggers

Start by examining these specific questions:

1. **Why does FrameReader need 1-second timeouts?** Is it for liveness detection? Can we use TCP keepalive instead?

2. **Why chunk message timeouts into 1-second intervals?** Is there a cancellation requirement we're missing?

3. **Why fixed intervals for health checks?** Could we check based on error rates or time since last use?

4. **Why centralized input routing?** Historical accident or deliberate design?

5. **Why poll for warmup needs?** Could acquisition attempts trigger warmup?

6. **Why sleep loop in rate limiter?** Could we schedule precise wakeup times?

## Patterns That May Need to Remain Polling-Based

Based on cross-cutting concerns, consider keeping these as polling:

### 1. Frame Reader (Pattern 4)
**Why Keep Polling**: Serves as connection liveness detection
**Alternative**: Only if TCP keepalive or heartbeat messages can replace it

### 2. Message Timeout Chunks (Pattern 2)  
**Why Keep Polling**: Provides cancellation points and progress indication
**Alternative**: Only with explicit cancellation tokens

### 3. Health Check Loop (Pattern 1)
**Why Keep Polling**: Predictable observability and debugging
**Alternative**: Hybrid approach with baseline polling + event triggers

## Expected Outcome

A comprehensive plan that:
1. Reduces unnecessary CPU wake-ups by 80%+
2. Eliminates timing-based race conditions  
3. Improves responsiveness (lower latency)
4. Simplifies debugging (deterministic behavior)
5. Maintains 100% backward compatibility
6. **Preserves all cross-cutting guarantees** (liveness, cancellation, observability)
7. **Provides rollback strategy** for each pattern
8. **Identifies patterns better left as polling**

Remember: Not all polling is bad. Some patterns may be optimal as-is. Your investigation must determine which patterns truly benefit from event-driven replacement and which should remain unchanged.

## Critical Success Factors

The investigation succeeds only if:
1. **No Degradation**: System remains as reliable as current polling-based design
2. **Preserve Contracts**: All hidden timing contracts are explicitly preserved  
3. **Maintain Observability**: New patterns are as debuggable as current ones
4. **Coordinate Changes**: Interdependent patterns are migrated together
5. **Enable Rollback**: Each change can be reverted independently
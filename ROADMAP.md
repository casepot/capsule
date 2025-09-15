# Capsule Development Roadmap

> Last Updated: 2025‑09‑15 | Version: 0.1.0‑dev

## State Snapshot (from src/)

### Protocol & Transport
- Framed transport with a Condition‑based FrameReader is implemented.
- FrameBuffer (framing.py) still uses a fixed‑interval polling loop; PROTO‑010 will replace it with an event‑driven Condition.

### Session
- Session.execute() yields messages via an event‑driven, cancellable wait. Passive message interceptors run before routing. cancel/interrupt/shutdown/restart are supported. Heartbeats update `Session.info()`.

### Worker & Executors
- Worker executes via ThreadedExecutor and strictly enforces output‑before‑result: it drains the output pump before emitting Result; on drain timeout it emits Error and no Result.
- ThreadedExecutor provides a protocol input() shim, an event‑driven output pump with flush sentinel and backpressure modes, and cooperative cancellation via `sys.settrace`. Its async wrapper is test‑only and suppresses drain timeouts with a warning.
- AsyncExecutor implements native TLA/async‑def/simple sync paths, a minimal AST fallback wrapper, bounded AST and linecache LRUs, coroutine tracking, and `cancel_current()`. It’s used via DI and unit tests; worker native routing remains to be wired (EW‑010).

### Session Pool
- Event‑driven warmup (signals, no polling) with watermark checks. Hybrid health check worker (timer baseline + event triggers). Pool metrics and `get_info()` are available.

### Integration
- ResonateProtocolBridge (local mode) correlates durable promises and returns structured timeout rejections; it tracks a pending high‑water mark. Surfacing lifecycle metrics via `Session.info()` is planned (BRIDGE‑010).

## Workstreams & Open Issues

### Executor & Worker (EW)
- EW‑012 (#49): Plumb timeouts/pump policy from `SessionConfig`.
- EW‑013 (#46): AsyncExecutor lifecycle + `cancel_current()` hardening (implemented; docs/tests finalize).
- EW‑011 (#48): Configurable drain‑timeout suppression knob for async wrapper.
- EW‑010 (#51): Worker native async route (flagged) with pump reuse and strict ordering.
- EW‑015/016 (#27/#28): DisplayMessage + ProgressMessage support.

### Protocol & Transport (PROTO)
- PROTO‑010 (#39): Event‑driven FrameBuffer using asyncio.Condition (remove polling).
- PROTO‑011 (#36): Protocol negotiation + fast Acks.
- PROTO‑012 (#37): Idempotency keys (depends on PROTO‑011).
- PROTO‑013 (#31): Durable streaming channels (open/data/close) with backpressure.

### Bridge & Capabilities (BRIDGE)
- BRIDGE‑010 (#35): Bridge lifecycle + metrics surfaced via `Session.info()`; idempotent close/cancel_all.
- BRIDGE‑011 (#38): Priority routing & interceptor quarantine with budgets and fairness.
- CAP‑010 (#30): CapabilityRegistry & SecurityPolicy.
- CAP‑011 (#52): Input EOF/timeout semantics (HITL); depends on BRIDGE‑010.

### Session Pool (POOL)
- POOL‑010 (#29): Finalize pre‑warm imports & memory budget.
- POOL‑011 (#50): Circuit breaker for create failures + metric safety.

### Providers (PROV)
- PROV‑020 (#42): Provider SDK & contract tests.
- PROV‑010/011/012 (#32/#33/#34): HTTP/Files/Shell providers with allowlists and caps.

### Observability (OBS)
- OBS‑010 (#40): Distributed execution trace.
- OBS‑011 (#41): Introspection (pending promises, namespace summary, pool status) with redaction.

## Sequencing & Rollout

- Enable First (low risk, unlocks downstream):
  - PROTO‑010 (FrameBuffer event‑driven), BRIDGE‑010 (lifecycle + metrics), EW‑012 (SessionConfig plumbing), EW‑013 (Async lifecycle finalize).
- Next:
  - EW‑011 (drain suppression knob), then EW‑010 (native async route behind a flag), which depends on EW‑012/013.
- Parallel Tracks:
  - POOL‑011 in parallel with EW. PROTO‑011 → PROTO‑012; PROTO‑013 after negotiation.
- Bridge/Capabilities:
  - CAP‑011 after BRIDGE‑010; BRIDGE‑011 after lifecycle with budgets and a P95 cancel latency SLO.
- Providers:
  - PROV‑020 (SDK/contracts) before provider implementations.

## Invariants & Risks

- Invariants: single‑reader transport; output‑before‑result; merge‑only namespace; event‑driven I/O.
- Risks:
  - Event loop complexity → loops owned by executor/transport; use `get_running_loop()`; no durable‑layer loop creation.
  - Ordering regressions → worker strict drain enforcement; pump remains event‑driven.
  - Protocol compatibility → additive schemas; negotiate/ack; staged rollouts.
  - Performance regressions → FrameBuffer refactor and pool breaker to avoid thundering herds.

## Testing & Quality

- Event‑driven tests; avoid sleeps; clear filenames/fixtures.
- Increase coverage around: AsyncExecutor routing, FrameBuffer refactor, bridge lifecycle surfacing, pool breaker.
- Use issue templates and conventions (`docs/PROCESS/ISSUE_CONVENTIONS.md`) to keep acceptance criteria testable.

## Medium/Long‑Term

- Capability registry & providers; remote/distributed mode; production hardening (limits/backpressure); observability (OTel, metrics, profiling); future multi‑language workers.

### Phase 5 Completion
- Remote mode functional
- Production deployment possible
- Performance targets met
- Recovery mechanisms tested

### Phase 6 Completion
- Full observability stack
- Performance benchmarks established
- <1% performance regression tolerance
- Production-ready certification

## Development Philosophy

1. **Correctness over features** - Get the foundation right
2. **Test everything** - Maintain high test coverage
3. **Document as you go** - Keep documentation current
4. **Incremental progress** - Small, reviewable changes
5. **Honest communication** - Be clear about limitations

## How to Contribute

### Current Needs
- Phase 3: Native AsyncExecutor implementation
- Test coverage improvements
- Documentation updates
- Bug fixes for failing integration tests

### Getting Started
1. Read [FOUNDATION_FIX_PLAN.md](FOUNDATION_FIX_PLAN.md)
2. Check current test status: `uv run pytest`
3. Pick an issue from Phase 3 deliverables
4. Submit small, focused PRs

## Revision History

- **2025-09-06**: Complete rewrite to reflect actual implementation status
- **Previous**: Original aspirational roadmap (archived)

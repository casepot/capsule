# Planning Prompt Examples

Real applications of the PARIS methodology across different problem domains.

## Example 1: Performance Optimization

### Problem
Database queries taking 10+ seconds, need sub-second response.

### PARIS Application

**Problem Archaeology**
- Previous: Added indexes → Helped briefly → Degraded again
- Lesson: Problem is query pattern, not missing indexes

**Architecture Recognition**  
- Existing: Query cache, connection pool, read replicas
- Unused: Read replicas at 5% utilization

**Risk Illumination**
- Risk: Cache invalidation errors → Stale data
- Risk: Replica lag → Consistency issues

**Implementation Scaffolding**
- Approach: Route reads to replicas, cache aggregations
- Specific: Lines 234-247 in query_router.py

**Success Validation**
- Metric: p95 latency < 1 second
- Test: Load test with production query patterns

## Example 2: Security Vulnerability

### Problem
Authentication bypass discovered in API endpoint.

### PARIS Application

**Problem Archaeology**
- Previous: Patched similar issue in v2.1 → Reappeared in v2.3
- Lesson: Pattern keeps recurring, need systematic fix

**Architecture Recognition**
- Existing: Auth middleware, permission decorators
- Gap: Inconsistent application across endpoints

**Risk Illumination**
- Risk: Breaking existing integrations
- Risk: Performance impact from additional checks

**Implementation Scaffolding**
- Approach: Mandatory middleware, no bypass possible
- Specific: app.py line 45: add required=True

**Success Validation**
- Test: Penetration test all endpoints
- Verify: No unauthenticated access possible

## Example 3: API Migration

### Problem
Migrate from REST to GraphQL while maintaining compatibility.

### PARIS Application

**Problem Archaeology**
- Previous: Big bang migration → Failed, rolled back
- Lesson: Need incremental approach

**Architecture Recognition**
- Existing: REST controllers, service layer, models
- Leverage: Service layer is already abstracted

**Risk Illumination**
- Risk: Client compatibility breaks
- Risk: Performance degradation from N+1 queries

**Implementation Scaffolding**
- Approach: Dual API with shared service layer
- Phases: Routes → Types → Resolvers → Deprecate REST

**Success Validation**
- Test: Both APIs return identical data
- Metric: GraphQL performance ≥ REST

## Example 4: Refactoring Legacy Code

### Problem
15-year-old module needs modernization without breaking dependencies.

### PARIS Application

**Problem Archaeology**
- Previous: Attempted rewrite → Subtle behavior changes → Reverted
- Lesson: Hidden business logic in implementation details

**Architecture Recognition**
- Existing: 47 consumers, 12 direct dependencies
- Contract: Poorly documented but discoverable via tests

**Risk Illumination**
- Risk: Behavior changes break downstream
- Risk: Performance characteristics change

**Implementation Scaffolding**
- Approach: Strangler fig pattern with feature flags
- Specific: Parallel implementation, gradual switchover

**Success Validation**
- Test: Differential testing (old vs new)
- Verify: Byte-identical outputs for all inputs

## Example 5: Scaling Challenge

### Problem
System handles 1K requests/sec, needs to handle 100K.

### PARIS Application

**Problem Archaeology**
- Previous: Vertical scaling → Hit hardware limits
- Previous: Simple sharding → Hot spots killed performance

**Architecture Recognition**
- Existing: Stateless services, database bottleneck
- Available: Message queue, cache layer, CDN

**Risk Illumination**
- Risk: Distributed system complexity
- Risk: Data consistency issues

**Implementation Scaffolding**
- Approach: Event-driven architecture with CQRS
- Steps: Decouple writes → Add read models → Scale horizontally

**Success Validation**
- Test: Load test at 120K requests/sec
- Verify: p99 latency acceptable
- Monitor: Error rate < 0.01%

## Pattern Recognition

Across all examples:
1. **History prevents repetition** - Every problem had failed attempts with lessons
2. **Infrastructure provides leverage** - Solutions built on existing components
3. **Risks guide design** - Early risk identification shaped approaches
4. **Specific beats vague** - Concrete implementation details ensure success
5. **Measurement proves achievement** - Clear metrics validate solutions

## Methodology Adaptability

The same PARIS framework applied to:
- Performance (technical)
- Security (critical)
- Migration (architectural)
- Refactoring (maintenance)
- Scaling (operational)

Each domain required different expertise, but the methodology remained constant: understand history, map infrastructure, identify risks, scaffold implementation, validate success.
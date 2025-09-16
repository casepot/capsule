Title: <Concise, actionable title>

Summary
- What: Briefly describe the change
- Why: Link to specs/docs/issues and the motivation
- How: Summarize approach at a high level

Scope
- In-scope: Key components/files touched
- Out-of-scope: What is explicitly not addressed

Checklist
- [ ] Tests updated/added where applicable
- [ ] Core invariants satisfied (see docs/issue-conventions.md#workstream-core-invariants)
- [ ] Protocol messages include required fields (if applicable)
- [ ] Performance guardrails observed (no pathological loops; bounded buffers)
- [ ] Type checks pass (mypy + basedpyright); see docs/typing-guidelines.md

References
- Link the relevant spec(s), ADRs, or docs you consulted (do not list them exhaustively here). For invariants see docs/issue-conventions.md; for typing policy see docs/typing-guidelines.md.

Risk & Mitigations
- Risk: <e.g., event loop conflicts>
  - Mitigation: <e.g., single-loop ownership + call_soon_threadsafe>
- Risk: <e.g., message ordering regressions>
  - Mitigation: <e.g., worker drains outputs before Result + tests>

Test Plan
- Unit: <list new/updated unit tests>
- Integration: <list scenarios>
- E2E/Features: <if any>

Acceptance Criteria
- List concrete, verifiable outcomes of this PR

Rollout/Backout
- Rollout steps (flags/env/migrations)
- Backout plan

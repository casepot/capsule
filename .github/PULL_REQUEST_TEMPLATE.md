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
- [ ] No namespace dict replacements (merge-only)
- [ ] Protocol messages include required fields
- [ ] Output ordering preserved (output before result)
- [ ] Single event loop ownership respected
- [ ] Performance guardrails observed

Design References
- AGENTS.md
- docs/async_capability_prompts/current/00_foundation_resonate.md
- docs/async_capability_prompts/current/21_spec_resonate_integration.md
- docs/async_capability_prompts/current/22_spec_async_execution.md
- docs/async_capability_prompts/current/24_spec_namespace_management.md
- docs/async_capability_prompts/current/25_spec_api_reference.md
- docs/async_capability_prompts/current/20_spec_architecture.md

Risk & Mitigations
- Risk: <e.g., event loop conflicts>
  - Mitigation: <e.g., single-loop invariant + interceptors>
- Risk: <e.g., message ordering regressions>
  - Mitigation: <e.g., drain_outputs validation + tests>

Test Plan
- Unit: <list new/updated unit tests>
- Integration: <list scenarios>
- E2E/Features: <if any>

Acceptance Criteria
- List concrete verifiable outcomes of this PR

Rollout/Backout
- Rollout steps
- Backout plan


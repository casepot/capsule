# Repository Housekeeping (Reorganization Map)

This repository keeps main (master) focused on production code, tests, and core reference docs. All development notes, planning files, large artifacts, and scratch materials are preserved on the long‑lived `workspace` branch. A pre‑cleanup snapshot tag was created to safeguard history.

- Snapshot tag: look for refs starting with `pre-cleanup-snapshot/` (most recent)
- Full archive branch: `workspace` (tracks all development docs and artifacts)

## Moved From Root
- FOUNDATION_FIX_PLAN.md → workspace
- PHASE_0_CHANGES_SUMMARY.md → workspace
- PHASE1_IMPLEMENTATION_SUMMARY.md → workspace
- PHASE_3_PR_PLANS.md → workspace
- ROADMAP.old.md → workspace (current ROADMAP.md stays)
- README.old.md → workspace
- resonate-sdk-docs.md → workspace
- phase1-prompt2.md → workspace
- REVIEWER_FEEDBACK_RESPONSE.md → workspace
- ROOT_CAUSE_ANALYSIS_AND_TRIAGE.md → workspace
- CLAUDE.md → workspace
- issues/ (issue body sources) → workspace
- Local artifacts/caches: `.venv/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `htmlcov/`, `.coverage`, `__pycache__/`, `.archive/`, `.claude/`, `completion-logs/`, `logs/` (no longer tracked on main)

## Moved From docs/
- docs/investigations/** → workspace
- docs/development/** → workspace
- docs/planning/** → workspace
- docs/context/** → workspace
- docs/async-patterns/** → workspace
- docs/async_capability_prompts/current/
  - 00_foundation_resonate.md → workspace
  - 10_prompt_async_executor.md → workspace
  - 11_prompt_capability_system.md → workspace
  - 12_prompt_namespace_persistence.md → workspace
  - PDFs → workspace

## Kept On main
- Code & tests: `src/`, `tests/`, `typings/`, `.github/`
- Tooling: `pyproject.toml`, `uv.lock` (tracked)
- Docs: `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CHANGELOG.md`
- Reference specs: `docs/async_capability_prompts/current/20_spec_architecture.md`, `21_spec_resonate_integration.md`, `22_spec_async_execution.md`, `23_spec_capability_system.md`, `24_spec_namespace_management.md`, `25_spec_api_reference.md`, `26_spec_security_model.md`, `27_spec_testing_validation.md`
- Architecture notes: `docs/architecture/*`
- Demo moved to `examples/demo.py`

For any missing file, check branch `workspace` or tag `pre-cleanup-snapshot/*`.

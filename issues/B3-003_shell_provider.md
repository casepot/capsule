TL;DR
- Provide a Shell provider for allowlisted commands with constrained environment, cwd, timeouts, and output truncation. Stream outputs line-wise when B2 is available.

Background / Problem
- Shell access is useful for tooling but dangerous; we need a minimal, controlled surface with strict allowlists.

Scope (In) / Non‑Goals (Out)
- In: run allowlisted commands; sanitize env; cwd restrictions; timeouts; output truncation; basic stderr/stdout separation.
- Out: interactive shells or TTY management (future); arbitrary command execution.

Contract (user space)
```py
res = await caps.shell.run("python", args=["--version"], timeout_ms=2000)
print(res.exit_code, res.stdout, res.stderr)
```

Policy & Config
- CAPS_SHELL_ALLOWED_CMDS: list[str]
- CAPS_SHELL_MAX_OUTPUT_BYTES: int (default 1 MiB)

Observability
- Metrics: execution latency, exit codes, truncation counts, timeouts
- Logs: command invocations (redacted), denials

Security
- Strict command allowlist; no shell parsing; sanitize env; restrict cwd; process timeouts; cap output size.

Compatibility
- Additive provider; wrappers via B1 registry; streaming later with B2.

Test Plan
- Disallowed commands are blocked; runaway process times out; outputs truncated at cap; stderr vs stdout separation verified.

Acceptance Criteria
- Allowed commands work; disallowed blocked; caps enforced; tests pass.

Implementation Notes (repo‑specific)
- New module: src/providers/shelld/*; Pydantic request/response models; simple spawn with asyncio subprocess.

Open Questions
- Do we support per-command env/cwd overrides or demand static provider config?


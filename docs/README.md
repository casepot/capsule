# Capsule Documentation Index

> Status: Draft scaffolding. Update this index once each focused guide is filled in.

## How to Use This Directory
- **Single-source references** live in the files listed below. Each guide should be updated whenever the corresponding subsystem changes.
- **Root-level project docs** (`README.md`, `ROADMAP.md`, `CHANGELOG.md`) stay alongside source; cross-link from the relevant sections here.
- **Legacy material** has been parked in `docs/_legacy/` pending archival. Replace citations that still point there.

## Top-Level Guides
1. [architecture-overview.md](architecture-overview.md)
2. [execution-engine.md](execution-engine.md)
3. [async-executor.md](async-executor.md)
4. [session-runtime.md](session-runtime.md)
5. [session-pool.md](session-pool.md)
6. [protocol.md](protocol.md)
7. [bridge-capabilities.md](bridge-capabilities.md)
8. [diagnostics-and-observability.md](diagnostics-and-observability.md)
9. [providers.md](providers.md)
10. [configuration-reference.md](configuration-reference.md)
11. [typing-guidelines.md](typing-guidelines.md)
12. [issue-conventions.md](issue-conventions.md)

## Status Note Convention
- Each guide opens with a status line referencing the commit hash it was
  validated against and a reminder to verify current sources. For example:
  `> Status: Authoritative reference … (sources referenced at commit <hash>; if
  code has drifted, double-check the current sources on your working commit…).`
  Readers should confirm the code on their commit, note task-relevant changes,
  and flag doc gaps while continuing with up-to-date information.
- See `architecture-overview.md` for a canonical example of this convention.

## TODO
- [ ] Replace this scaffolding once each guide is populated.
- [ ] Remove references to `_legacy` docs after migration.

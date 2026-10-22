# Phase 13 baseline — 2026-10-21

Workspace: `D:\CivicLens`, Windows, Python 3.13.2, Node 22.20.0, npm 10.9.3.
`git status --short` fails because this directory is not a Git repository. Existing
files, lockfiles, environment configuration and development data must be preserved.

Before implementation, the unmodified `scripts/verify.ps1` was started with its
output recorded in `%TEMP%\civiclens-phase13-baseline.log`. The existing isolated
13-test Playwright suite was also started. Final results are recorded below after
completion; a running command is not a PASS.

Initial checks: `pip check` passed. Frontend and infrastructure `npm audit --json`
both completed with zero reported advisories (313 and 117 dependencies respectively).
`pip-audit` is not installed; Python advisory verification is NOT_VERIFIED, not zero.
No dependency installation or lockfile replacement occurred.

Read-only development DB checks: schema 8, `integrity_check=ok`, zero foreign-key
violations. Baseline DB SHA256:
`F254663D7A0F6608CC0C96D34C6530E0A1C2AD57E296B85B963415C9A0980710`
(770048 bytes). No migration/startup was run against this database.

Audit findings before changes:

- Ordinary JSON API requests do not have a streamed application body bound;
  only complaint/repair/verification upload routes do.
- Evidence reconciliation only includes complaint photographs, omitting repair
  and feedback evidence. Its orphan suggestions can therefore be misleading.
- Research runners are separate and do not persist one versioned evaluation artifact.
- No general local API p95/error-rate benchmark or consolidated release gates exists.
- AWS Phase 12 domain binding, analytics projection bootstrap, Linux dependency
  packaging, real OAuth provisioning and frontend HTTPS hosting remain blockers.
- Coverage is not measured by the original verification entry point.

## Completed baseline results

- Original backend collection: **623 passed**, 437.93s, one existing Starlette/httpx deprecation.
- Original process integration: **4 passed, 1 failed**, 46.33s. The failing assignment
  POST received 409 while the active worker advanced routing. This is correct
  optimistic concurrency behavior; the test assumed no concurrent revision change.
  Its later bounded refresh/retry correction passed (43.15s standalone).
- Original browser collection: **13 passed**, 2.7min, including real role/lifecycle flows.
- The baseline script stopped on integration failure, correctly returning nonzero;
  it did not execute later stages. Those stages were run separately: frontend
  lint, application/browser TypeScript, 195 unit tests (23.80s), production build;
  infrastructure compilation, 58 assertions (124.15s), offline synthesis/template
  checks and local zero-stack validation all passed. Frontend notification type
  labels had been added by this separate run; it is not a pristine-source baseline.
- Backend lint/format were first run after adding Phase13 scaffolding, not claimed
  as pre-change lint. Initial new regression collection reproduced 11 failures for
  absent body/header protections; all passed after the hardening changes.

No original unit test was deleted, skipped or weakened. See the final readiness
report for separately measured verification and coverage of changed source.

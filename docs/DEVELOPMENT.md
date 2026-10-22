# Local Development

## Phase 14 frontend workflow (Windows)

```powershell
Set-Location D:\CivicLens
.\scripts\run-backend.ps1
# In another PowerShell terminal:
Set-Location D:\CivicLens
.\scripts\run-frontend.ps1
# Optional separate worker terminal, using the existing configuration:
.\scripts\run-worker.ps1
```

Open `http://localhost:5173`. Existing local accounts and SQLite data are retained. No Docker, WSL,
dependency reinstall, permanent policy change or AWS operation is required. The normal frontend
proxies `/api` to the existing backend. Use the established trusted staff-provisioning script;
public registration never grants staff roles.

```powershell
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run typecheck:browser
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
$env:CIVICLENS_BROWSER_CHANNEL = 'msedge' # Optional installed-browser override on Windows
.\scripts\verify.ps1
```

Browser tests own disposable UUID databases, evidence directories and ports 8002/5180/8003/5181;
they never use the normal database. `e2e/redesign.spec.ts` adds real local API route/layout,
keyboard, reduced-motion, file-drop and axe checks across four viewport widths. Screenshots are
saved to `build/phase14/screenshots`. The complete verification script still includes the existing
Phase 0–13 tests, coverage, offline infrastructure and contracts. Default verification does not
contact AWS and is not a deployment. See [current results](PHASE14_IMPLEMENTATION_REPORT.md).

Follow the [design system](FRONTEND_DESIGN_SYSTEM.md) when extending pages. Prefer native CSS motion
and the existing Lucide/Chart.js/Leaflet dependencies. Keep validation, privacy and operation IDs in
the existing service flows. Phase 15 is the future deployment phase; **NO AWS DEPLOYMENT PERFORMED**.


## Phase13 verification / preservation

`scripts/verify.ps1` now defaults to backend branch coverage plus isolated real browser
tests, and saves step status/log/research/API/contract/source-manifest artifacts under
`build/verification/<new-run>`. Missing categories are NOT_VERIFIED when explicit skip
switches are used. No dependency reinstall is required for Phase13.
Network advisories are opt-in; default verification does not contact AWS. Credential
environment is removed for tests/synth and restored afterwards, including absent vs
empty Windows profiles. [Results](PHASE13_READINESS_REPORT.md), [backup/diagnostics](BACKUP_AND_ROLLBACK.md),
[non-secret environment guide](ENVIRONMENT_CONFIGURATION.md). Never run fixtures on normal data.

## Phase12 Windows workflow

From `D:\CivicLens`, keep using `scripts/run-backend.ps1`, `scripts/run-frontend.ps1` and optional
foreground `scripts/run-worker.ps1`. Normal backend startup applies additive migrations; do not reset
the account DB or delete existing photographs. No Docker, WSL, permanent execution-policy change or
frontend dependency reinstall is required. Use existing trusted staff provisioning; public registration
never provisions ADMIN/OFFICER. New pages: citizen verification, officer incident repair, ADMIN repair
verification, recurrence and geographic service comparison.

```powershell
.\scripts\verify.ps1
npm.cmd --prefix frontend run test:browser
Set-Location D:\CivicLens\backend
.\.venv\Scripts\python.exe -m pytest tests/test_civic_intelligence.py tests/test_intelligence_security.py tests/test_intelligence_cloud.py
.\.venv\Scripts\python.exe -m app.scripts.evaluate_intelligence
.\.venv\Scripts\python.exe -m app.scripts.benchmark_intelligence
```

Evaluation is fixed labeled synthetic data; benchmark creates/deletes only its TemporaryDirectory.
Browser tests own isolated fixture databases and ports8002/5180/8003/5181 and clean their servers up.
They do not reuse or reset the developer's normal account database. No AWS command is required;
infrastructure verification clears credential/profile discovery for offline synthesis and restores
environment settings afterward. Cloud Phase12 source bindings remain gated; see AWS_SERVICES.md.

## Phase11 analytics workflow (current)

Existing accounts/.env/package locks are preserved. The new backend-only `tzdata` dependency is
installed by existing requirements/setup; no frontend dependency reinstall is needed. Configure
ANALYTICS_TIMEZONE (defaultUTC), ANALYTICS_SCOPE and optional named rectangular service areas in the
existing backend configuration. Start normal backend/frontend scripts in separate terminals.

```powershell
Set-Location D:\CivicLens
.\scripts\run-backend.ps1
# Separate terminal:
.\scripts\run-frontend.ps1
# Read-only after startup installs the analytics extensions:
.\scripts\rebuild-analytics.ps1 -Full -DryRun
.\scripts\rebuild-analytics.ps1 -Full
.\scripts\verify.ps1
npm.cmd --prefix frontend run test:browser
```

From backend: `.venv\Scripts\python.exe -m app.scripts.rebuild_analytics --diagnose --aggregation overview`
or `--start YYYY-MM-DD --end YYYY-MM-DD --batch-size 25`; hotspot view also needs
`--bounds SOUTH WEST NORTH EAST`. Rebuilds touch only analytics-owned snapshots and are restart-safe.
Dry-run/diagnose refuses absent/uninitialized stores without creating or migrating them. A disposable
1000-report/500-incident benchmark runs with `python -m app.scripts.benchmark_analytics` using the
project venv. No normal citizen database is a test fixture. No Docker/WSL/AWS credentials/deployment
or permanent PowerShell policy/task changes. Earlier per-phase commands below are historical.

## Phase10 local commands (Windows)

From D:\CivicLens, in an allowed PowerShell session:

```powershell
.\scripts\run-worker.ps1 -Once -BatchSize 20
.\scripts\process-pending-events.ps1 -BatchSize 20 -MaxBatches 20
.\scripts\run-worker.ps1 -Continuous
.\scripts\run-scheduled-checks.ps1 -Once -BatchSize 20
.\scripts\run-scheduled-checks.ps1 -Once -DryRun
.\scripts\verify.ps1
npm.cmd --prefix frontend run test:browser
```

Ctrl+C stops the foreground continuous worker; leases recover after expiry. Startup does not require
an external worker process. The existing local application-owned worker handles events when
MATCHING_WORKER_ENABLED=true; test mode does not auto-start it. Do not point tests/benchmarks at the
normal account database. run_scheduled_checks --dry-run uses read-only SQLite and does not migrate;
it reports a clear initialization error for absent or older-schema stores. Start the backend first
to apply the additive schema8 migration before previewing checks.
Benchmark: backend/.venv/Scripts/python.exe -m app.scripts.benchmark_events (run from backend).
No Docker, WSL, AWS credentials, Windows scheduled tasks or detached processes are required.
If Windows blocks script files, a one-process -ExecutionPolicy Bypass invocation is optional;
never change a machine/user-wide policy for this project. No AWS deployment commands are part of verify.
See [recovery](FAILURE_RECOVERY.md). Historical instructions below refer to earlier phases.

## Phase9 department/officer workflow

Run existing backend/frontend scripts in separate terminals from D:\CivicLens. Schema7 migration is
additive. No reinstall, Docker/WSL, AWS credentials or PowerShell policy change is required.

```powershell
Set-Location D:\CivicLens
.\scripts\run-backend.ps1
# Separate terminal:
.\scripts\run-frontend.ps1
# Trusted interactive staff provisioning, choose OFFICER or ADMIN:
.\scripts\create-local-user.ps1
# Explicit fictional defaults (or use the confirmed ADMIN seed dialog):
Set-Location D:\CivicLens\backend
.\.venv\Scripts\python.exe -m app.scripts.seed_departments --confirm-demo-configuration
.\.venv\Scripts\python.exe -m pytest tests/test_work_allocation.py tests/test_work_adapters.py -q
.\.venv\Scripts\python.exe -m app.scripts.benchmark_allocation
```

Login as ADMIN, open `/admin/departments`, add the trusted officer's membership/availability/capacity,
then use `/admin/assignments`. Default recommendations need manual approval. Login as OFFICER for
`/officer/dashboard`; only assigned eligible work is visible. Progress does not finalize resolution.
Do not change roles by browser requests or insert arbitrary officer emails into code. Deactivate/remove
memberships only after reassignment. No existing account is automatically promoted by this phase.

`scripts/verify.ps1` includes all backend/regression/process integration/frontend/offline infrastructure
checks and the disposable Phase9 benchmark. Browser tests run separately with
`npm.cmd --prefix frontend run test:browser`; dedicated8002/5180 fixture stores are isolated from normal
8000/5173 data. Trusted browser staff provisioning rejects paths outside that dedicated fixture pattern.
The additional allocation project uses its own8003/5181 API/frontend and separate disposable database,
so registration/login quotas do not leak between regression and Phase9 scenarios. Production limits
are unchanged; public registration remains exercised in both projects.
Workload weights and ASSIGNMENT_MODE are validated environment configuration. Do not enable auto mode
for real municipal work without independent policy/capacity validation. Phase10 now coordinates these
same durable services; see the current event/orchestration guides above.

## Current Phase 8

Preserve .env/accounts; scripts/run-backend.ps1 and scripts/run-frontend.ps1 remain native PowerShell
entry points. ADMIN /admin/priorities and existing incident details expose current ranking/controls.
Run backend `.venv\Scripts\python.exe -m app.scripts.recalculate_priorities --dry-run --batch-size 25`
before writing backfill; --stale-only and --after support bounded refresh/resume. --incident-id targets
one canonical incident. Commands refuse AWS and dry runs do not migrate/write. Full commands and
rubrics: [PRIORITY_SCORING](PRIORITY_SCORING.md). verify.ps1 includes all prior regressions plus priority
evaluation/sensitivity/benchmark; browser tests remain separate on isolated8002/5180 fixture stores.

## Current Phase 7

Preserve existing .env/accounts. Start `scripts\run-backend.ps1` and `scripts\run-frontend.ps1`
in separate PowerShell terminals from D:\CivicLens; visit
`http://localhost:5173/admin/incidents` as an existing trusted administrator. Never elevate public
registration through request data. Clustering defaults REVIEW_ONLY. Tests do not seed the normal store.
`scripts\verify.ps1` adds clustering evaluation/benchmark to all previous checks; browser tests run
with `npm.cmd --prefix frontend run test:browser` on isolated8002/5180. Read-only maintenance/resume
cursors: [incident guide](INCIDENT_CLUSTERING.md). No AWS setup/deploy is needed or permitted here.

## Phase 6 current workflow

Preserve existing .env files. Install only the new backend dependency if needed:

```powershell
Set-Location D:\CivicLens\backend
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
Set-Location D:\CivicLens
.\scripts\migrate-local.ps1
.\scripts\verify.ps1
npm.cmd --prefix frontend run test:browser
```

No frontend dependency reinstall was needed/performed. Keep package-lock.json; avoid reinstalling
locked native modules while Vite is running. Do not terminate unrelated Node/Codex processes or
change system-wide execution policy. No WSL, Docker, GPU, AWS credentials or paid API is needed.

Schema-v4 migration is additive and startup also applies it. Normal APP_ENV=local starts one bounded
matching worker unless MATCHING_WORKER_ENABLED=false; APP_ENV=test/AWS never starts the daemon.
Submission returns its established201 independently of subsequent matching success. Inspect local
matching_jobs state/error class or ADMIN per-complaint API when work fails; retry/lease state survives
restart. Do not reset the database to fix a matching error.

Provision ADMIN with the existing trusted create-local-user script (never public registration).
Visit /admin/duplicate-candidates, enter a complaint UUID to recheck, filter/open comparison, then
dismiss or mark reviewed. Photos remain pair-scoped/authorized; suggestions do not merge anything.

From backend:

```powershell
.\.venv\Scripts\python.exe -m app.scripts.recheck_duplicates --limit 25 --dry-run
.\.venv\Scripts\python.exe -m app.scripts.recheck_duplicates --limit 25 --only-outdated
# Resume another bounded batch using the last printed nextAfter/resumeAfter UUID:
.\.venv\Scripts\python.exe -m app.scripts.recheck_duplicates --limit 25 --after YOUR_LAST_UUID
.\.venv\Scripts\python.exe -m app.scripts.evaluate_matching
.\.venv\Scripts\python.exe -m app.scripts.benchmark_matching
```

Dry-run opens the existing database read-only and does not migrate/enqueue/compute/delete; outdated
filtering is deferred to execution. Execution supports config+text-model version checks. CLI refuses
cloud environments and prints progress/resume keys; candidates/review decisions remain persisted.
Use protected ADMIN APIs for inspection rather than copying private SQL dumps into shared logs.

verify.ps1 includes all backend/frontend/lint/type/build checks, three real HTTP process-restart
integrations, actual synthetic evaluation/benchmark, and offline infrastructure tests/synthesis.
Browser checks run separately on isolated8002/5180 servers, unique phase5-browser-UUID fixture paths
(historical prefix retained), and a trusted path-restricted provisioning helper. They never touch
the normal developer account store. Phase6 adds responsive/axe-tested private comparison/review.
See DUPLICATE_DETECTION.md for experimental MATCHING_* settings and MATCHING_EVALUATION.md for
measured results and limitations. Earlier Phase5/v3 sections below describe preserved workflows.

## Current Nearby Issues follow-up

Nearby Issues now combines only the authenticated citizen's eligible private reports with approved
public summaries. Select a center explicitly (map/manual/GPS/latest complaint), then use the 1–200km
radius (default 10km). A submission success action centers the search on its actual saved point.
Private owner labels, category SVG markers, radius circle, clusters, cards and pagination share the
same authorized dataset. No newly submitted complaint becomes public automatically. See
[the implementation and verification report](NEARBY_ISSUES_FIXES.md) and
[the API/geographic contract](GEOGRAPHIC_DISCOVERY.md). Startup adds two indexes without a reset;
restart an old non-reloading API process to load the new endpoints/configuration.

## Phase 5 historical workflow

Run scripts/migrate-local.ps1 for additive schema v3; startup also migrates without resetting users, sessions or reports. Existing native modules were retained while Chart.js was added with install scripts disabled. Avoid reinstalling node_modules while Vite/watchers lock native files. Never stop unrelated Node/Codex processes.

My Complaints now searches full owner history with URL filters. Dashboard charts use actual aggregates. Nearby Issues fetches only approved public projections; new complaints remain PRIVATE. For publication, request on the citizen detail screen, provision a separate ADMIN using scripts/create-local-user.ps1, then visit /admin/publication-review with the known complaint ID. Supply a manually reviewed non-sensitive summary/general location and explicit privacy confirmation. Withdraw as owner or unpublish as ADMIN. No public seeding occurs automatically.

Run scripts/verify.ps1 for backend/frontend/infrastructure and two actual process-restart integrations. Run npm.cmd --prefix frontend run test:browser for browser checks. Browser tests isolate phase5-browser-UUID databases/private roots on 8002/5180. A trusted test-only provisioning helper refuses other database paths; no HTTP admin-registration backdoor exists. Tests do not use normal 8000/5173 data.

From backend run `.\.venv\Scripts\python.exe -m app.scripts.benchmark_phase5` for the disposable 5,000-record synthetic benchmark/query plans. Its records are not municipal evidence. PUBLIC_QUERY_RATE_LIMIT, DISCOVERY_CANDIDATE_LIMIT, NEARBY_MAX_RADIUS_METERS and CLOUD_OWNER_QUERY_LIMIT are documented in .env.example. Existing .env files are not overwritten. No Docker/AWS credentials/deployment is required. Historical Phase 4 limitations below are superseded where Phase 5 adds search/publication/discovery.

## Phase 4 complaint application

Use the existing `scripts/run-backend.ps1` and `scripts/run-frontend.ps1` from separate PowerShell terminals at `D:\CivicLens`. The normal app stays on localhost:5173 with `/api` proxied to 127.0.0.1:8000. Register a citizen through `/register`, sign in, then visit `/citizen/dashboard`. No seeded passwords exist. The existing trusted CLI still provisions local officer/admin accounts.

Citizen navigation now covers actual private complaint submission, saved complaints/details/evidence, dashboard counts, nearby sample map/list, notifications, and the real account profile. **Show sample data** defaults off; it remains a separate fixture view and cannot submit real complaints. Normal complaint screens use real APIs without sample fallback on failure. Submit Complaint persists data; Preview locally remains explicitly non-submitting. Unsubmitted drafts are memory-only, while submitted data survives refresh/logout/restart. Coordinate entry works without geolocation/tiles; permission and third-party basemap access remain opt-in.

Backend dependencies now include Pillow, python-multipart and boto3. The application and trusted CLI run schema-v2 additive migration; existing users/passwords/sessions are preserved. Default evidence is private `backend/data/evidence/`, not public frontend assets. LOCAL_EVIDENCE_ROOT can override it. No SQLite image binaries or AWS local-mode calls are used.

```powershell
Set-Location D:\CivicLens\backend
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
Set-Location D:\CivicLens
.\scripts\migrate-local.ps1
# Or use scripts/setup.ps1 for a full clean dependency install after stopping dev servers.
```

```powershell
Set-Location D:\CivicLens
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run typecheck:browser
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
.\scripts\verify.ps1

# One-time browser binary installation, then browser/viewport/accessibility integration tests:
Set-Location D:\CivicLens\frontend
npx.cmd playwright install chromium
npm.cmd run test:browser
```

The browser suite starts its own API on 8002 and Vite on 5180, refuses busy ports, and writes only an ignored unique `backend/data/phase4-browser-*.db` and matching `phase4-browser-*-evidence` directory. It never uses `civiclens_local.db` or its private evidence root. Servers stop automatically. Screenshots/failure traces go to ignored `frontend/test-results/`; traces can contain test credentials/photos, so do not publish them. Disposable test databases/evidence can be removed **after** the API stops, using exact reviewed paths. Test credentials are randomly generated and apply only to the isolated database.

The runner prefers an installed Chrome on Windows when detected, otherwise Playwright Chromium. This workstation rejects the downloaded Chromium executable with `spawn UNKNOWN`; installed Chrome successfully runs the suite. A channel can also be selected explicitly for this command only:

```powershell
$env:CIVICLENS_BROWSER_CHANNEL = 'chrome' # or msedge
npm.cmd run test:browser
Remove-Item Env:CIVICLENS_BROWSER_CHANNEL
```

Viewport tests cover 375/768/1024/1440px, all citizen screens, overflow, mobile menus, dialogs and axe WCAG A/AA checks. Scenarios exercise actual complaint submission/private-photo display, persistence after refresh/logout/login, other-owner denial, real profile editing and sample-mode separation. All automated tile requests are intercepted. `verify.ps1` also runs `backend/.venv/Scripts/python.exe -m pytest tests/integration` from the appropriate working directory: the isolated process-restart test creates its own temporary database/evidence, starts/stops real Uvicorn processes, and verifies SQLite/files/API persistence. No AWS calls are needed, and SDK transport is forbidden in backend unit tests.

Read-only recovery diagnostics (stop writers first and keep database/evidence backups together):

```powershell
Set-Location D:\CivicLens\backend
.\.venv\Scripts\python.exe -m app.scripts.evidence_audit --minimum-age-hours 24
```

This does not delete or repair anything automatically. See EVIDENCE_STORAGE.md. The infrastructure verification script temporarily disables credential-file/environment/container/instance-metadata providers for offline synthesis and restores its process environment afterward; it never modifies saved AWS credentials.

## Windows prerequisites

- Windows PowerShell 5.1 or PowerShell 7+
- Python 3.12+
- Node.js 20.19+, 22.12+, or newer compatible LTS with npm
- No Docker, Java, database server, AWS account, or AWS credentials

From `D:\CivicLens`, run:

```powershell
.\scripts\setup.ps1
```

If script execution is restricted, use a process-scoped policy (it does not change machine policy):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

The scripts call `backend\.venv\Scripts\python.exe` directly; activating the virtual environment is optional.

## Environment variables

Frontend variables are defined in `frontend/.env.example`:

- `VITE_APP_NAME`: display name available to Vite
- `VITE_API_BASE_URL`: browser API base; `/api` uses the local proxy

Backend variables are defined in `backend/.env.example`:

- `APP_NAME`, `APP_ENV`, `DEBUG`, `HOST`, `PORT`, `LOG_LEVEL`
- `CORS_ORIGINS`: JSON array or comma-separated HTTP(S) origins

Allowed backend environments are `local`, `test`, `aws`, `demo`, and `production`. AWS/demo/production require Cognito configuration, reject local authentication and debug mode, and never fall back to SQLite. Wildcard CORS is forbidden; production requires HTTPS origins without loopback hosts. Optional `COMPLAINTS_TABLE_NAME`, `INCIDENTS_TABLE_NAME`, `AUDIT_EVENTS_TABLE_NAME`, and `EVIDENCE_BUCKET_NAME` are populated by CDK references for the future cloud function and remain unset locally. No AWS connection is made when these settings load. Local `.env` files are ignored by Git.

## Commands

```powershell
.\scripts\run-backend.ps1
.\scripts\run-frontend.ps1
.\scripts\verify.ps1
.\scripts\verify-infrastructure.ps1
```

Manual component checks:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m ruff format --check backend
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix infrastructure run build
npm --prefix infrastructure test
npm --prefix infrastructure run synth
npm --prefix infrastructure run check:templates
```

## Troubleshooting

### Local authentication

Setup now runs `python -m app.scripts.local_auth init` using the backend virtual environment. It creates `backend/data/civiclens_local.db` without dropping existing data. Startup repeats this safe initialization. `APP_ENV=local` and `AUTH_PROVIDER=local` select local credentials; both the CLI and setup refuse cloud provisioning.

Stop running development servers/test watchers before rerunning setup. Windows can lock Vite's native modules, causing npm ci to report EPERM while attempting replacement; close that project server and rerun setup without changing system permissions.

```powershell
Set-Location D:\CivicLens
.\scripts\setup.ps1
.\scripts\run-backend.ps1
# In another terminal:
.\scripts\run-frontend.ps1
# Trusted local account provisioning:
.\scripts\create-local-user.ps1
```

Open `/register` for a citizen, or select OFFICER/ADMIN in the terminal tool. Sign in at `/login`; use `/profile` to edit the display name or sign out. Passwords need 12–128 characters. No seeded account or master password exists. To test recovery, request a reset at `/forgot-password`, then retrieve its private outbox link with the terminal command in AUTHENTICATION.md. No email is sent.

If an API script gets 403 on a write, add the exact configured Origin header. Cookies are scoped to /api; use a cookie-aware HTTP client. If login is rate-limited, respect Retry-After. Missing tables indicate initialization was skipped or an alternate LOCAL_DB_PATH was selected. A stale session after password reset must sign in again.

For a deliberate local reset, stop the backend, move the database to a uniquely named backup inside `backend/data`, and rerun the init command. Preserve the backup and outbox until recovery data is no longer needed; do not delete source folders or reset users automatically. Schema version 1 is tracked with SQLite user_version; future migrations must be explicit.

The optional live integration runner is `tests/integration/auth_smoke.py`. Use a dedicated database named phase2-smoke-*.db and point a separate backend at that same LOCAL_DB_PATH; never point it at the normal account database. It supports --database, --backend-url, and --frontend-url. A second Vite instance can use server-only CIVICLENS_API_PROXY_TARGET to proxy to the isolated backend; normal defaults remain 8000/5173. Phase 2 verification used 8001/5174, exercised each role through real cookies/API calls, then stopped those servers and removed only its test database.

`APP_ENV=aws` requires AUTH_PROVIDER=cognito and complete Cognito issuer/client/domain settings. Never set a local provider as a workaround for a cloud configuration error. See COGNITO_SETUP.md for public frontend variables and deferred live checks.

- `python` not found: install Python from python.org and enable **Add Python to PATH**.
- Node version rejected: install the current Node.js LTS. Recent Vite releases require newer patch releases of Node 20/22.
- Port in use: stop the process using 5173 or 8000; the fixed ports make proxy behavior predictable.
- Backend unavailable in the status page: start the API, confirm `http://127.0.0.1:8000/api/health`, then use **Retry connection**.
- Stale dependencies: remove only the affected project's `.venv` or `node_modules`, then rerun setup. Preserve source files and lockfiles.
- CDK synth notices are informational. Do not run bootstrap or deploy during Phases 0–14.

## Infrastructure verification (Phase 1)

`verify.ps1` invokes `verify-infrastructure.ps1` after the existing backend/frontend checks. The infrastructure script compiles TypeScript, runs CDK assertions, synthesizes the demo stack with context lookups disabled, checks the current assembly's resource allowlist/IAM/deployment block, and verifies that local has no cloud stacks. All checks are local and fail on nonzero command exits.

Demo is the default CDK context. Use `npx.cmd cdk synth -c stage=production -o cdk.out/production` from `infrastructure` for production definitions, and `npm.cmd run check:templates -- cdk.out/production` to inspect them. `npm.cmd run check:local` verifies that the local assembly has zero cloud stacks; it is also part of the infrastructure verification script. The raw CDK CLI reports “This app contains no stacks” and exits 1 for the local stage, so use the dedicated check instead.

`npm.cmd --prefix infrastructure run check:deployment-readiness` intentionally exits 1 with the outstanding Phase 15 packaging/approval requirements; it is not part of passing local verification. Current source-only assets must never be deployed. See [INFRASTRUCTURE.md](INFRASTRUCTURE.md).


# CivicLens

CivicLens is an intelligent public-infrastructure complaint management system under local development. It helps citizens report problems such as road damage, broken streetlights, waste accumulation, drainage failures, and damaged public assets, while helping municipalities group related reports and prioritize work transparently.

Phases 0–12 provide local authentication, private reports/evidence, search, reviewed discovery, duplicate
analysis, canonical incidents, explainable priorities, **department routing and municipal officer work
allocation/progress**, durable automated triage, real private notifications and demonstration SLA alerts.
The municipal Command Center adds private citywide analytics, geographic grids and protected reports.
Phase12 adds officer repair attempts, protected completion evidence, eligible citizen verification,
audited administrator resolution/rework/reopening, reviewed recurrence and private geographic service
comparisons. No citizen majority automatically closes an incident; geography does not prove unfairness.
No AWS resources are deployed.

## Phase 14 — Complete frontend redesign and UI/UX optimization

The frontend now uses a shared navy/teal identity, role-aware collapsible workspace, responsive
navigation drawer, redesigned landing/authentication/citizen experiences and focused operational
pages. Actual API clients, private evidence, cursor pagination and role permissions are preserved.
Secondary analytics and filters stay accessible through disclosures. Native CSS motion respects
reduced-motion preferences; no new dependencies or lockfile changes were needed.

See [design system](docs/FRONTEND_DESIGN_SYSTEM.md),
[implementation and actual verification](docs/PHASE14_IMPLEMENTATION_REPORT.md), and
[current progress](PHASE_PROGRESS.md). Run Windows backend/frontend scripts in separate terminals.

Roadmap: **Phase 13 — Testing, Security, Performance, Research Evaluation, AWS Readiness**;
**Phase 14 — Complete Frontend Redesign and UI/UX Optimization**;
**Phase 15 — Final AWS Deployment**. Phase 15 has not begun.
**NO AWS DEPLOYMENT PERFORMED.** Existing deployment blocks remain in force.

## Phase13 validation and release hardening

Local security/reliability regressions, streamed API bounds, private evidence backup/
diagnostics, unified research evaluation, p95 benchmarks, backend branch coverage,
logged verification and offline CDK/API contracts are implemented. **AWS deployment
readiness remains BLOCKED**: cloud service/projection bindings, pinned Linux packaging,
trusted HTTPS/OAuth provisioning and frontend hosting need completion. No AWS
deployment or resource creation occurred.

Run `.\scripts\verify.ps1` from `D:\CivicLens`; it uses isolated fixtures, includes
real browser tests by default and saves `build/verification/<run>/summary.json` and
logs/coverage/research/benchmark/source-manifest artifacts. `-SkipBrowser` or
`-SkipCoverage` explicitly leaves a category NOT_VERIFIED, not fully verified.
Advisory network audits are separate opt-in checks, never AWS calls.

See [A–AL readiness/results](docs/PHASE13_READINESS_REPORT.md),
[security](docs/SECURITY_AUDIT.md), [integration](docs/INTEGRATION_TEST_REPORT.md),
[research](docs/RESEARCH_EVALUATION_REPORT.md), [performance](docs/PERFORMANCE_REPORT.md),
[known risks](docs/KNOWN_RISKS.md), [backup/rollback](docs/BACKUP_AND_ROLLBACK.md),
[AWS runbook](docs/AWS_DEPLOYMENT_RUNBOOK.md) and [release notes](RELEASE_NOTES.md).

## Advanced civic intelligence (Phase12)

Citizen `/citizen/verification`; officer assigned incident → repair submission;
ADMIN `/admin/repair-verification`, `/admin/recurrences`, `/admin/fairness` and five new protected CSV
report types. Restart the backend normally to install additive schema8 extensions without resetting
accounts, reports, incidents or photographs. No frontend package reinstall is required.

See [repair policy](docs/REPAIR_VERIFICATION.md), [recurrence](docs/RECURRENCE_DETECTION.md),
[service comparisons](docs/GEOGRAPHIC_FAIRNESS.md), [evaluation](docs/PHASE12_EVALUATION.md) and
[A–AA implementation/handoff](docs/PHASE12_IMPLEMENTATION_REPORT.md).
Cloud source plans/conditional persistence are stub-tested preparation, not an activated cloud repair
service. AWS-mode Phase12 HTTP workflows fail closed503 until controlled domain-adapter binding and
cloud source bootstrap are completed. Phase13 audits this limitation; Phase 14 provides the local frontend redesign.

## Municipal analytics (Phase11)

ADMIN `/admin/command-center` separates actual eligible complaint totals from canonical incidents,
current priorities, department/officer workload, response/SLA/backlog and real recorded trends.
`/admin/hotspots` provides bounded private spatial grids with distinct incident/report measures;
`/admin/reports` previews and exports audited, formula-protected CSV. Filters use configured reporting
time-zone days, not browser midnight. No fake operational sample data or automatic repair resolution.
Existing administrative management routes and citizen/officer permissions are preserved.

Startup installs additive analytics-owned schema8 extensions without resetting records. Native Windows
IANA reporting zones use the added tzdata backend dependency; no frontend dependency reinstall is needed.
From D:\CivicLens use `.\scripts\rebuild-analytics.ps1 -DryRun -Full` for read-only reconciliation after
starting the backend, and omit `-DryRun` for restart-safe replacement of derived snapshots only.
See [municipal definitions](docs/MUNICIPAL_ANALYTICS.md), [hotspots](docs/GEOGRAPHIC_HOTSPOTS.md),
[departments](docs/DEPARTMENT_PERFORMANCE.md), [officers](docs/OFFICER_WORKLOAD_ANALYTICS.md),
[reports](docs/ADMIN_REPORTING.md), [data model](docs/ANALYTICS_DATA_MODEL.md) and [progress](PHASE_PROGRESS.md).

## Event-driven workflows (Phase10)

Complaint creation commits an ID-only event atomically. Durable outbox/queue processing coordinates
existing matching, clustering, priority and routing services, with leases, bounded retries, stage
history and dead-letter recovery. ADMIN `/admin/workflows` monitors executions and demonstration SLA
alerts; all roles can use `/notifications` for their private inbox. No real email/SMS or AWS deployment.

Windows: `.\scripts\run-worker.ps1 -Once`, `.\scripts\process-pending-events.ps1`,
`.\scripts\run-scheduled-checks.ps1 -Once` (add `-DryRun` for read-only preview).
See [event architecture](docs/EVENT_DRIVEN_ARCHITECTURE.md),
[orchestration](docs/WORKFLOW_ORCHESTRATION.md), [notifications](docs/NOTIFICATION_SYSTEM.md),
[SLA](docs/SLA_ESCALATION.md), [recovery](docs/FAILURE_RECOVERY.md) and [verification](PHASE_PROGRESS.md).

## Municipal work allocation (Phase9)

ADMIN `/admin/departments` manages editable demonstration configuration, routing/rectangles and trusted
officer memberships. `/admin/assignments` routes master incidents, recommends available capacity-aware
officers and confirms audited assignment/reassignment. OFFICER `/officer/dashboard` shows only their
assigned work and authorized supporting photographs, start/progress/review controls and private history.
MANUAL_APPROVAL is default; urgency remains Phase8's responsibility. No automatic final resolution.

See [department routing](docs/DEPARTMENT_ASSIGNMENT.md), [officer allocation/benchmark](docs/OFFICER_ALLOCATION.md),
[assignment schema/cloud readiness](docs/ASSIGNMENT_DATA_MODEL.md), and [workflow states](docs/WORKFLOW_STATES.md).
From backend, explicitly seed using `.\.venv\Scripts\python.exe -m app.scripts.seed_departments --confirm-demo-configuration`.
Provision staff with `scripts/create-local-user.ps1`; public registration never creates officers.

## Explainable priorities (Phase 8)

ADMIN `/admin/priorities` ranks existing master incidents using assessed severity/public impact,
logarithmic eligible independent-account support and unresolved time. Unknown inputs remain
provisional. Verified hazard escalation and audited expiring overrides are separate from the formula.
Existing incident details provide contribution bars, controls and immutable history. Membership changes
invalidate prior assessments/overrides; current rankings exclude stale results. Citizen/public privacy
is preserved; high priority never automatically publishes private data.

See [scoring/Windows guide](docs/PRIORITY_SCORING.md), [data model](docs/PRIORITY_DATA_MODEL.md),
[measured evaluation](docs/PRIORITY_EVALUATION.md) and [progress](PHASE_PROGRESS.md).

```powershell
Set-Location D:\CivicLens\backend
.\.venv\Scripts\python.exe -m app.scripts.recalculate_priorities --dry-run --batch-size 25
.\.venv\Scripts\python.exe -m app.scripts.recalculate_priorities --stale-only --batch-size 25
```

No emergency dispatch is implemented. Phase9 adds work allocation; Phase10 adds durable event
processing and an offline, disabled-by-default cloud schedule definition.

## Master incidents (Phase 7)

Active verified administrators use `/admin/incidents` for membership/counts, private maps/evidence,
recommendations, merge/split/move/unlink and history. Citizens see only their own safe association.
`REVIEW_ONLY` is the default; experimental automatic linking has measured false positives. Original
complaints/photos/public links are preserved. See [clustering guide](docs/INCIDENT_CLUSTERING.md),
[data/transaction design](docs/INCIDENT_DATA_MODEL.md) and [actual evaluation](docs/CLUSTERING_EVALUATION.md).

```powershell
.\scripts\run-backend.ps1
# In a second PowerShell terminal:
.\scripts\run-frontend.ps1
.\scripts\verify.ps1
npm.cmd --prefix frontend run test:browser
```

Local read-only maintenance from `backend`: `python -m app.scripts.cluster_existing_complaints --limit 25 --dry-run`
and `python -m app.scripts.reconcile_incidents --limit 50 --dry-run` (use the project .venv Python).
No AWS deployment performed. Phase8 scoring, Phase9 work allocation and Phase10 workflows are
implemented locally; cloud execution remains unverified.

## Duplicate review (Phase 6)

New complaints enqueue durable local matching work with their persistence transaction. The CPU-only
engine combines indexed private geographic retrieval, explicit categories, fixed-corpus scikit-learn
word/character TF-IDF cosine and cached Pillow dHash image evidence. Missing images are unavailable,
not zero; safety gates keep nearby distinct objects/contradictions under manual review. Suggestions
never merge complaints or assign incident IDs/priorities. Similarity is not a calibrated probability.

Sign in as a separately provisioned ADMIN and visit `/admin/duplicate-candidates` for filters,
ranked scores, side-by-side private evidence, explanations, dismissal/review and bounded rechecks.
Citizen ownership/publication contracts are unchanged. Only active verified ADMIN receives this
narrow new pair-comparison/evidence permission; other citizens and officers remain denied.

Phase6 introduced additive schema v3→v4; current startup migrates additively through schema8.
Install backend dependencies with the existing editable
install below; no frontend dependencies changed. See [Detection architecture](docs/DUPLICATE_DETECTION.md),
[Measured synthetic evaluation/performance](docs/MATCHING_EVALUATION.md) and [API](docs/API.md).
From backend:

```powershell
.\.venv\Scripts\python.exe -m app.scripts.recheck_duplicates --limit 25 --dry-run
.\.venv\Scripts\python.exe -m app.scripts.recheck_duplicates --limit 25 --only-outdated
.\.venv\Scripts\python.exe -m app.scripts.evaluate_matching
.\.venv\Scripts\python.exe -m app.scripts.benchmark_matching
```

## Citizen experience (Phase 5)

The light-theme public site and responsive citizen workspace include:

| Route | Working behavior |
|---|---|
| `/` | Public landing page, categories, planned features, safe report/login return |
| `/citizen/dashboard` | Six real statistics cards, category/status/trend charts, selectable period, recent complaints and refresh |
| `/citizen/report` | Real multipart submission, manual/map coordinates, optional landmark, opt-in geolocation, up to 2 private photos, safe retries and success ID/details navigation |
| `/citizen/complaints` | Full-history server search, combined category/status/severity/date filters, URL state, sorting and cursor pagination |
| `/citizen/complaints/:complaintId` | Real private details/photos and publication request/withdrawal controls |
| `/citizen/nearby` | Owner-private overlay plus approved public summaries, 1–200km radius, category SVG markers/clusters, explicit center/GPS/latest complaint, synchronized cards and pagination |
| `/issues/:publicIssueId` | Anonymous reviewed public summary and approximate coordinates; no reporter identity or evidence |
| `/admin/publication-review` | ADMIN-only minimal audited approve/reject/unpublish form, not a municipal dashboard |
| `/citizen/notifications` | Real private notifications, unread/read state, filters and pagination; explicit isolated sample preview |
| `/citizen/profile` | Real Phase 2 profile read/edit/logout; `/profile` remains supported |

Citizen layout routes retain their Phase 2 CITIZEN/ADMIN matrix, but personal complaint APIs require an active, verified **CITIZEN** and enforce ownership. ADMIN publication and duplicate review are narrowly authorized; officers cannot approve/review. Private evidence remains owner-only on citizen routes; the ADMIN pair-scoped route is the explicit exception. New complaints stay private until an explicit request and administrator review. Authentication/recovery/profile APIs remain intact. **Show sample data** defaults off and never becomes an API-error fallback. Records survive logout, refresh and restart; drafts and sample interactions remain memory-only.

The additive schema-v3 migration preserves accounts, sessions, complaints and photo metadata, adding FTS5 search, selected indexes, publication metadata and audit records. Evidence defaults to private `backend/data/evidence/` and is never mounted publicly. Accepted JPEG/PNG/WebP inputs are limited to **2 × 1.5 MiB**, 4 megapixels and 4096px per dimension; server processing strips metadata and writes fresh JPEG pixels. Multipart requests remain bounded at 3.25 MiB. Persistent request idempotency is not intelligent duplicate detection.

Existing installations can install backend dependencies and migrate safely:

```powershell
Set-Location D:\CivicLens\backend
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
Set-Location D:\CivicLens
.\scripts\migrate-local.ps1
```

See [COMPLAINT_SYSTEM.md](docs/COMPLAINT_SYSTEM.md) and [EVIDENCE_STORAGE.md](docs/EVIDENCE_STORAGE.md) for ownership, API contracts, recovery and AWS adapter limitations.

Phase 5 guides: [Search](docs/COMPLAINT_SEARCH.md), [Analytics](docs/DASHBOARD_ANALYTICS.md), [Geographic discovery](docs/GEOGRAPHIC_DISCOVERY.md), [Publication and privacy](docs/PUBLICATION_AND_PRIVACY.md). Run the disposable 5,000-record benchmark from backend with `.\.venv\Scripts\python.exe -m app.scripts.benchmark_phase5`.

Read [FRONTEND_ARCHITECTURE.md](docs/FRONTEND_ARCHITECTURE.md) and [UI_DESIGN.md](docs/UI_DESIGN.md).

## Objectives and planned novelty

- Preserve each citizen report while clustering reports about the same physical incident.
- Detect likely duplicates using location, text, imagery, and category compatibility.
- Calculate explainable priorities using severity, impact, independent support, and time unresolved.
- Support repair workflows, escalation, notifications, maps, and municipal analytics.

Duplicate suggestions, bounded auditable clustering, priority scoring, department/officer allocation,
operational progress, durable triage and in-app notifications are implemented. Final repair verification
and recurring-failure/geographic-fairness intelligence remain roadmap items. Citywide operational
analytics is implemented in Phase11.

## Technology stack

- Frontend: React, TypeScript, Vite, Tailwind CSS, React Router, Lucide icons, lazy Chart.js analytics, Vitest, Testing Library
- Maps: Leaflet 1.9 / React Leaflet 5; optional OpenStreetMap tiles with visible attribution, normal browser caching, and no prefetch
- Browser verification: Playwright Chromium and axe-core accessibility checks
- Backend: Python 3.12+, FastAPI, SQLite, Pydantic Settings, Pillow, scikit-learn TF-IDF, python-multipart, Uvicorn, Mangum, HTTPX, boto3, pytest, Ruff
- Infrastructure: AWS CDK v2 and TypeScript (local definitions for DynamoDB, S3, Lambda, HTTP API, IAM, and CloudWatch)
- Developer environment: native Windows and PowerShell; Docker and AWS credentials are not required

## Authentication (Phase 2)

Local accounts use SQLite, Argon2id passwords, and expiring server-side HttpOnly cookie sessions. Registration creates citizens only. Sign-in, profile editing, logout, local password recovery, and CITIZEN/OFFICER/ADMIN dashboards work locally. Backend RBAC enforces access independently of UI guards. Cognito code/PKCE, verified access tokens, and HTTP API JWT authorization are prepared for future AWS mode.

After setup, open `/register` to create a citizen or use the trusted terminal tool for local roles:

```powershell
.\scripts\create-local-user.ps1
```

The CLI prompts for credentials without echo and refuses nonlocal environments. There are no default accounts/passwords. Read [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md), [docs/ROLES_AND_PERMISSIONS.md](docs/ROLES_AND_PERMISSIONS.md), and [docs/COGNITO_SETUP.md](docs/COGNITO_SETUP.md).

## Repository layout

```text
frontend/       React web application and UI tests
backend/        FastAPI application, Lambda adapter, and API tests
infrastructure/ modular AWS CDK foundation, assertions, and offline safety checks
scripts/        Windows setup, run, and verification commands
tests/          future cross-component integration fixtures/tests
docs/           architecture, API, roadmap, AWS, cost, and development notes
```

## Local installation on Windows

Prerequisites are Python 3.12 or newer and a Vite-compatible Node.js release (20.19+, 22.12+, or newer compatible LTS).

```powershell
Set-Location D:\CivicLens
.\scripts\setup.ps1
```

The setup script creates `backend/.venv`, installs all dependencies, and copies `.env.example` to ignored local `.env` files if needed. It uses the virtual environment's Python directly, so activation is unnecessary.

## Run locally

Open two PowerShell terminals:

```powershell
# Terminal 1 — API at http://127.0.0.1:8000 (Swagger at /docs)
.\scripts\run-backend.ps1

# Terminal 2 — web app at http://localhost:5173
.\scripts\run-frontend.ps1
```

Vite proxies browser requests from `/api` to the local FastAPI service.

## Verification

Run the complete local suite:

```powershell
.\scripts\verify.ps1
```

Individual commands are documented in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

Run browser tests separately (isolated API on 8002, Vite on 5180, separate test database):

```powershell
npm.cmd --prefix frontend exec -- playwright install chromium
npm.cmd --prefix frontend run test:browser
```

The suite blocks all tile requests and never contacts AWS. Browser binaries are a one-time download. The standard verification script remains usable without installed browsers.

## Infrastructure foundation (Phase 1)

The source-only demo/production stack defines three retained DynamoDB tables with seven GSIs (aggregate 10 RCU/10 WCU), a private SSE-S3 bucket, Python3.13 Lambda, Cognito, scoped IAM and seven-day logs. Phase6 adds InternalGeography/MatchingWork, exact Query permissions and seven ADMIN matching routes. Current template:88 resources,13 outputs,23 explicit routes; only health/approved-public discovery are anonymous. No extra table, queue or paid AI/search service. Native Linux dependencies/cloud execution remain unverified; local-stage synthesis creates zero cloud stacks and the unconditional deployment block remains.

```powershell
.\scripts\verify-infrastructure.ps1
```

The Lambda asset is explicitly **synthesis only**, with Python dependencies deferred to a verified Linux package in later phases. A CloudFormation rule blocks deployment, and `npm.cmd --prefix infrastructure run check:deployment-readiness` intentionally fails. Successful synthesis proves only local definition validity. See [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md), [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md), and [docs/AWS_COST_ESTIMATE.md](docs/AWS_COST_ESTIMATE.md).

## Development and deployment strategy

Phases 0–14 are implemented and tested locally. CDK definitions may be added locally in later phases, but cloud deployment is reserved for Phase 15 and must be initiated manually by the user. No setup, run, or verification command invokes AWS APIs, `cdk bootstrap`, or `cdk deploy`. AWS pricing and free-tier eligibility must be checked immediately before any eventual deployment.

See [docs/PHASES.md](docs/PHASES.md) for the roadmap and [docs/COST_SAFETY.md](docs/COST_SAFETY.md) for cost controls.


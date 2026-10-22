# Phase 7 — intelligent clustering and master incident management

Phase13 re-verifies transitive/cohesion/corrections/concurrency and reports actual
baseline trade-offs. Conservative grouping still has false pairs; REVIEW_ONLY remains
default. No source reports are deleted. [Research](RESEARCH_EVALUATION_REPORT.md),
[lifecycle/races](INTEGRATION_TEST_REPORT.md).

Implemented locally in D:\CivicLens. REVIEW_ONLY is the operational default. This guide describes
Phase7; Phase8 priority scoring is now implemented (see [priority scoring](PRIORITY_SCORING.md)).
Phase9 now adds [department/officer allocation](DEPARTMENT_ASSIGNMENT.md). No AWS deployment,
incident-resolution propagation or notification workflow is implemented.

## Submission and recovery

The complaint/evidence save remains its own transaction and still returns 201. SQLite's insertion
trigger atomically creates clustering work alongside Phase6 matching work. The local bounded worker
initializes an idempotent singleton, computes Phase6 comparisons, then runs cluster checks. The two
durable outboxes recover independently; failures never roll back an accepted complaint or photograph.
Temporary null membership is explicitly pending, not an unsaved complaint. Historical rows get pending
jobs during the additive schema5 migration; no all-city clustering runs inside that migration.

Worker leases last120s; failures retry after60s. Running-job rechecks retain a rerun request; stale
lease holders cannot finish a newer claim. APP_ENV=test/aws never starts the in-process daemon.
Private administrator rechecks queue audited, bounded work; the local worker completes it asynchronously.
In test fixtures use the trusted service/CLI explicitly. AWS has no enabled scheduler/worker in Phase7.

## Rules and false-positive safeguards

- REVIEW_ONLY creates singletons and stored recommendations, never consolidates automatically.
- CONSERVATIVE_AUTO_LINK must be explicitly configured. Only an OPEN, active, eligible singleton
  source can move into an OPEN target; established multi-report source clusters never auto-merge.
- Phase6 must have completed without truncation; matching model/config must be current. At most five
  target incidents are evaluated by default, and any omitted work/time exhaustion disables auto-link.
- Exactly one recommended target is required. Competing targets, including unqualified alternatives,
  cause review rather than arbitrary tie-breaking. Scores are similarity indices, not probabilities.
- Every bounded member pair, including target-to-target pairs, must pass exact category compatibility,
  Haversine span, fresh Phase6 comparison, contradiction/distinct-object and dismissed-pair checks.
  No connected-components or representative-only shortcut is used. An A–B–C bridge does not establish
  that A and C are the same physical defect.
- Automatic limits: maximum10m full-cluster span (also bounded by each category radius), STRONG
  classification, same known category, combined>=.90, text>=.85, image>=.90 by default. Missing photos
  do not become zero evidence; default image requirement blocks automatic consolidation. OTHER needs
  review. Identical text at15–20m is not enough for an automatic link.
- All operations cap resulting clusters at30 members. No silent sampling, multi-transaction merge or
  unbounded citywide pairwise comparison. Oversized clusters require controlled smaller corrections.
- Stored all-pair score snapshots have a200KB cumulative budget per run. Exhaustion marks work
  incomplete and disables automatic links. A dismissal made during CPU validation is checked again
  inside the membership transaction, not merely before it. Cloud atomic-envelope overflow becomes
  an explicit review decision rather than a partially applied link or unending oversized retry.
- Representative metadata stays pinned to the existing representative while it remains a member;
  otherwise the earliest original (createdAt,complaintId) member is selected. Coordinates are that
  actual report's coordinates, not a centroid drifting along a transitive chain.

These guards do NOT solve reused photos/text or sub10m separate defects. Held-out synthetic tests
produced8 false-positive pair relationships even in opt-in conservative mode. Keep REVIEW_ONLY for
operations; see [measured evaluation](CLUSTERING_EVALUATION.md). Human review is still necessary.

## Administrator corrections

Merge, move/link one report, split selected reports, unlink to singleton, and recheck require an
active verified ADMIN, trusted Origin for local cookie POSTs, durable UUID operationId, written
reason10–500 characters and explicit confirmation. Merge/link additionally require a physical-issue
confirmation and expected source AND target versions. Merge/link apply category/radius/full-member
cohesion checks; human confirmation can override weak text/photo scores, not spatial/category bounds.
Manual full-cluster span defaults75m but is also bounded by each category's Phase6 radius.

Split/unlink must leave at least one report in the original cluster. Removing the last report by a
move retires the source with a redirect; whole-cluster merge keeps the source as MERGED. Empty retired
records are history, never unexplained active incidents. Splits create a new UUID and preserve old
aliases pointing at the retained canonical master. Old aliases are not repointed to an arbitrary
split subset. Repeated identical operations replay their exact stored result, even after restart or
if a concurrent worker commits between replay-read and validation. Changed input with the same ID,
retired references or stale versions return409. The UI freezes failed requests for identical retry;
after a409, close, refresh and confirm a new operation.

SQLite commits membership, before/after metadata, reporter counts, operation receipt and audit rows
under BEGIN IMMEDIATE with optimistic incident versions and observed complaint/eligibility guards.
Busy locks get three bounded attempts (250ms SQLite wait plus short backoff), not process-only locks.
Private correction does not update original title/text/status/createdAt/updatedAt/evidence/publication.

## Reporter support

totalComplaintCount includes every authoritative member. uniqueReporterCount is DISTINCT citizen ID
among current active verified CITIZEN accounts and non-REJECTED reports. Multiple reports by one
citizen add one supporter, not multiple votes. Deactivated/unverified/non-citizen accounts and rejected
reports remain preserved but excluded. Every correction recomputes exact counts within its transaction;
explicit reconciliation repairs cached counts after trusted account/status changes. No Phase8 score
is invented. Dynamo readiness uses a guarded internal eligibility snapshot (see data model limits).

## Private UI and public compatibility

/admin/incidents lists real stored counts, review flags, filters/search, newest/oldest keyset pages and
summary metrics. Details include bounded member evidence, representative/report map markers, distances,
stored recommendations versus actual associations, actor/reason/history, merge/split/unlink/move/recheck.
The Leaflet map deliberately loads no external tiles, avoiding precise private coordinates in tile
requests. Candidate review links expose actual current memberships and explicit correction dialogs;
Keep separate records a dismissal, not an unlink of reports already associated.

Citizen complaint details request only their own safe {incidentId,category,status,processing}; no
other-member counts, identities, private canonical narrative or alias history. OFFICER has no global
incident-management permission. UUIDs are opaque. No public incident API was added. Existing reviewed
public complaint IDs, explicit publication, search/nearby endpoints and public links remain unchanged.
Incident grouping never publishes private reports or substitutes private IDs into public discovery.

## Local historical maintenance (PowerShell)

From D:\CivicLens\backend, preserve the existing .env and normal account database:

```powershell
.\.venv\Scripts\python.exe -m app.scripts.cluster_existing_complaints --limit 25 --dry-run
.\.venv\Scripts\python.exe -m app.scripts.reconcile_incidents --limit 50 --dry-run
# Explicit writes only after reviewing diagnostics:
.\.venv\Scripts\python.exe -m app.scripts.cluster_existing_complaints --limit 25 --mode REVIEW_ONLY
.\.venv\Scripts\python.exe -m app.scripts.reconcile_incidents --limit 50 --repair
```

Backfill prints nextAfter/resumeAfter; resume with --after UUID. Every execution uses fresh Phase6
evidence, not stale candidate acceptance, and does not duplicate singleton assignments. Auto mode is
an explicit experimental --mode CONSERVATIVE_AUTO_LINK option, never the CLI default.
Reconciliation prints four independent cursors: nextComplaintAfter (--after), nextIncidentAfter
(--incident-after), nextCandidateAfter (--candidate-after), nextEventAfter (--event-after). Resume each
separately until its checked batch is empty. Every batch checks at most500 complaints/incidents/
candidates/events; linked-member validation is capped30. A concurrent insert with an earlier UUID may
require a fresh sweep. These are maintenance snapshots, not online citywide consistency guarantees.

Dry-run opens SQLite URI mode=ro, does not initialize/migrate, hash photos, enqueue work, update counts
or create database/evidence files; it requires an existing schema5 DB. Commands reject cloud mode.
Reconciliation detects unassigned/invalid/retired references, cached count drift, active empties,
alias cycles/depth, lifecycle inconsistency, stale candidate references, duplicate events within its
bounded batch and retry/expired jobs. Schema UNIQUE(operation_id,complaint_id) also prevents normal
duplicate events globally. Explicit repairs create audited singletons for invalid references,
recalculate counts and retire empty OPEN records; ambiguous cycles, lifecycle corruption and stale
candidate references are escalated for manual review, never silently deleted. Repeated repair converges.

## Verification and file map

From D:\CivicLens:

```powershell
.\scripts\run-backend.ps1
# In a second terminal:
.\scripts\run-frontend.ps1
.\scripts\verify.ps1
npm.cmd --prefix frontend run test:browser
```

verify.ps1 includes all backend/frontend/integration/lint/type/build checks, both Phase6 and Phase7
evaluations/benchmarks, and credential-isolated offline CDK checks. Browser fixtures use dedicated
8002/5180 ports and unique disposable phase5-browser-UUID stores; the prefix is historical, not schema.

Main additions: backend/app/{models/incident.py,algorithms/incident_clustering.py,
repositories/phase7_migration.py,repositories/incident_repository.py,services/incident_service.py,
services/incident_reconciliation.py,api/routes/incidents.py,integrations/database/dynamodb_incidents.py};
scripts/{incident_cli,cluster_existing_complaints,reconcile_incidents,evaluate_clustering,
benchmark_incidents}.py; algorithms/clustering_evaluation_data.py. Frontend adds incidentService,
IncidentsPage and components/incidents; auth routes/navigation and candidate/citizen views integrate them.
Tests add test_incidents.py, test_incident_adapters.py, Incidents.test.tsx, incidents.spec.ts,
infrastructure/test/incidents.test.ts and extend the real-process restart scenario. Existing assertions
were updated only for schema5, singleton initialization and the expanded exact AWS transaction/routes.

Known limits: bounded30-member prototype; stale recommendations are labelled historical suggestions;
no live AWS verification, production throughput claim, city-scale calibration or account moderation
worker; resolved incident status is stored independently, not a report-wide resolution workflow.

NO AWS DEPLOYMENT PERFORMED.
Phases8/9 are implemented locally. Next: Phase10 — Automated Event-Driven AWS Workflows,
Notifications, and Escalation. Not started.

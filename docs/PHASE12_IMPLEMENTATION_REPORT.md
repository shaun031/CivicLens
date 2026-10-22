# Phase12 implementation and handoff — A–AA

## A–F. Repair workflow and architecture

Local SQLite implementation in CivicIntelligenceService/SQLiteCivicIntelligence. P9-assigned officers
submit completion with P4 sanitized evidence; persisted distinct-account requests allow current linked
citizens to confirm, dispute or answer unsure. One immutable response per attempt, private identities,
no automatic closure. ADMIN reviews current priority/hazards, evidence and all feedback, approves,
rejects, requests information/rework or reopens the current verified resolution. Reasons, optimistic
versions, idempotency receipts, transactions and audits apply. Rework retains old attempts and resets
progress; reopening retains the same incident and suspends allocation for review. See
[repair policy](REPAIR_VERIFICATION.md) and [states](WORKFLOW_STATES.md).

## G–J. Recurrence

Bounded geographic historical lookup requires a current genuinely verified previous repair and strict
temporal ordering. Reuses P6 distance, TF-IDF, contradiction and informative dHash utilities with a
separate versioned evidence score. Missing evidence and uncertain physical identity stay explicit.
Directional unique pair records preserve both incidents; no self-links/cycles/automatic merge. ADMIN
confirmation requires physical-identity review and a reason. `/admin/recurrences` provides filters,
comparison and distinct-incident chronological history; authorized repair/incident pages hold evidence.
See [recurrence policy](RECURRENCE_DETECTION.md).

## K–M. Geographic service comparisons

Creation-date cohorts, canonical incident counts, recorded current-cycle work-start median, known-SLA
overdue fraction, active backlog fraction, current verified-resolution fraction and distinct confirmed
recurrence concentration. Counts, missing values, sample sizes, priority/department mixes, filters,
period and calculation time are disclosed. Stable decimal grid cells, optional OSM, map/table and
side-by-side comparison. Default minimum10 observations; other-cell baselines, configurable descriptive
thresholds, insufficient-data warnings, audited administrative review records. Unadjusted: no invented
reference data, protected-characteristic inference, public fairness endpoint, officer penalties or
causal discrimination conclusion. See [definitions](GEOGRAPHIC_FAIRNESS.md).

## N–O. Events, priority and SLA

Original transactional P10 outbox, notify consumer, retry/receipt/DLQ system;14 added version1 ID-only
event types. Fairness review events use AREA_REVIEW aggregate; evidence bytes and private notes never
enter payloads. Notifications recheck eligible recipients and deduplicate retries. Officer completion
does not lower P8 severity. ADMIN resolution/reopen changes canonical state in the original transaction,
activates P8 cumulative age and P9 suspension/P10 SLA-cycle triggers, and retains raw priority/history.
Repair submitted, requested, responded, approved/rejected/rework/reopened timestamps are actual records,
not retroactively synthesized milestones. Existing response/resolution SLA targets are unchanged;
repair/verification milestones have no invented new deadline policy. No real email/SMS is sent.

## P–R. Interfaces and database

28 exact protected API routes listed in [API.md](API.md), including officer attempts, citizen requests,
private evidence, ADMIN repair decisions, recurrence and fairness/review endpoints. Existing13 report
endpoints remain; five report TYPES are added without duplicating export infrastructure. New React
pages: RepairPages, RecurrencesPage, FairnessPage; private evidence/upload/gallery, filters, reports
and role routes reused. Sidebar/admin/assigned-work links updated. Additive schema8 extension creates
seven P12 tables with FKs/unique indexes and retains all original operational records/images.
See [database](DATABASE_DESIGN.md).

## S. Cloud preparation and explicit activation gap

SDK-stub-tested DynamoIntelligence conditional change-plan port, sparse existing ByQueue access
pointers, canonical source guards and atomic event/receipt plans; existing S3Evidence private adapter
and processing pipeline. CDK28 routes/14 event types reuse all original resources. NO DEPLOYMENT.
This is NOT a bound AWS-mode repair domain service: controlled server command-planner binding,
canonical/eligibility/projection bootstrap, Linux packaging and live IAM/performance validation are
still needed before activation. Phase12 cloud HTTP fails closed503 without local fallback. These
limitations are intentionally visible; a successful local test/synth is not claimed as cloud execution.

## T–V. Actual verification, evaluation and benchmark

See [PHASE_PROGRESS.md](../PHASE_PROGRESS.md) for the final commands/counts/failures and reruns.
[PHASE12_EVALUATION.md](PHASE12_EVALUATION.md) records measured synthetic precision/recall/F1, noisy
repair-policy simulations, sample/grid sensitivity and reproducible actual local benchmark results.
No result is claimed as a calibrated probability, field effectiveness or AWS capacity estimate.

## W. Main changed source groups

- Backend: phase12_migration, civic_intelligence_repository, civic_intelligence_service,
  civic_intelligence schemas/routes, algorithms/recurrence, analytics/fairness,
  dynamodb_intelligence; main/config/body-limit/events/workflow/analytics-report integration.
- Frontend: RepairPages, RecurrencesPage, FairnessPage, FairnessMap, civicIntelligenceService,
  useCivicOperation; role routes/navigation, existing work/report/filter/evidence components reused.
- Infrastructure: intelligence-routes, API/event constructs and safety resource inventory/assertions.
- Tests: test_civic_intelligence, test_intelligence_security, test_intelligence_cloud,
  Intelligence.test.tsx, extended isolated browser assignment flow and network-aware duplicate check.
- Scripts: evaluate_intelligence, benchmark_intelligence, verify.ps1, verify-infrastructure.ps1.
- Documentation: repair, recurrence, geographic fairness, evaluation and this report; existing API,
  architecture, database, workflows, AWS, cost, development, README and progress updated.

## X. Known limits

Cloud domain binding is not activated. Historical legacy resolutions get no invented verification.
Only recorded current eligible accounts vote; identity uniqueness is not proven. No direct citizen
vote edits; historical feedback remains reviewable by ADMIN. Asset identities unavailable; near-neighbor
false-positive candidates and image-viewpoint failures remain. Bounded city scope may require explicit
projection partitioning at scale. Unknown/uncertain I/O commits may retain evidence orphans for safe
reconciliation. Fairness is unadjusted and descriptive; no protected-characteristic inference.
Existing upstream Starlette/CDK/browser notices remain visible rather than suppressed.

## Y–AA. Windows commands, deployment and next phase

Use normal run-backend/run-frontend/foreground run-worker scripts. `scripts/verify.ps1`,
`npm.cmd --prefix frontend run test:browser`, backend `python -m app.scripts.evaluate_intelligence`
and `python -m app.scripts.benchmark_intelligence` run without Docker/WSL or AWS credentials.
No normal database reset, photo deletion, dependency reinstall or unrelated process termination.

**NO AWS DEPLOYMENT PERFORMED.** Phase13 and Phase14 were not started. Next requested phase:
Phase13 — Comprehensive Integration Testing, Security Hardening, Performance Optimization, Research
Evaluation, and AWS Deployment Readiness. Do not confuse Phase12 regression verification with starting
that later phase.

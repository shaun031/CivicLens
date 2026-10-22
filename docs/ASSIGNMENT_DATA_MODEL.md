# Phase9 — additive schema7 and cloud preparation

SQLite user_version7 adds records without rebuilding/deleting users, sessions, complaints, evidence,
canonical incidents, memberships or priority controls/history. Six department defaults are an explicit
configuration seed, not a destructive migration. No assignment unit is created for each duplicate report.

| Record | Authority / fields |
|---|---|
| departments | UUID, unique code, name/description, activation, rectangles JSON, version, UTC created/updated actor/time |
| routing_rules | UUID, existing category, department FK, precedence, activation/version; unique(category,department) |
| officer_memberships | UUID, existing user and department FKs, activation, availability, nullable capacity, rectangles, version, trusted actor/time; unique(officer,department) |
| incident_assignments | Existing incident UUID PK/FK; single department/officer FKs; independent work state/method/rule hash/explanation, revision/source version, pending/retry fields, progress %, actor/time |
| work_history | Append-only application writes: opaque event ID/entity, optional existing operation receipt FK, kind, actor/type, reason, before/after snapshots, UTC time |
| work_meta | Global queue revision invalidating continuation cursors |

Reuses Phase7 incident_operations for exact request/actor-scoped idempotency receipts. Config changes
and progress use the same atomic receipt/audit protocol. Request hashes include operation type, target,
actor and full input; same ID/different input409. No plaintext session/password data is recorded.
Department/member/history records are preserved rather than deleted. Foreign keys are enforced on
every connection. Assignment/officer/department/pending/history/category indexes bound operational reads.

## Local concurrency and lifecycle

BEGIN IMMEDIATE serializes authoritative membership, capacity and source-version checks with state,
receipt and history writes. Incident version and assignment version must match. A failed audit write
rolls everything back. Lock retries are bounded3 attempts with250ms busy timeout and small backoff.
Exact receipt replay does not repeat history or workload. Officer authorization is rechecked before
receipt replay, so reassigned/deactivated officers cannot use an old accepted request to regain access.

Atomic SQLite triggers create sidecars, invalidate allocations on membership/lifecycle changes, clear
ineligible accounts and advance queue revisions on assignment or priority changes. Merge/split history
contains the actual previous allocation; original events are retained under their original IDs.
Local queues use keyset ordering and context-bound cursors, not offsets/full React datasets. Cursors
expire<=60s/next priority due time and conflict409 if assignment/priority revision changes. Fresh urgent
hazards sort first, then pending-priority review work, then effective score/unresolved time/stable UUID.
Band/hazard filters require fresh scores. Pending values are not presented as scored zero.

## DynamoDB adapter: offline readiness, not live validation

Existing Incidents/AuditEvents only; no additional table/GSI or provisioned capacity. Namespaces:

| Access | Record / index |
|---|---|
| Department ID/code | work-department#UUID / work-code#CODE, strong GetItem |
| Config/rules/directory | Strong bounded work-config/work-rules/work-officers manifests + item reloads |
| Membership by department | work-members#DEPT manifest + work-member#DEPT#SUB |
| Membership by user | work-officer-departments#SUB manifest; stable Cognito sub identity |
| Officer account projection | work-officer#SUB, trusted provisioning/lifecycle interface; never a public role grant |
| Canonical allocation | work#INCIDENT sidecar, independent revision and sourceVersion; original incident unchanged |
| Active work / unassigned discovery | Existing ByStatusPriority partition WORK#OPEN; strong reload/filter |
| Department queue | Existing ByDepartmentPriority partition WORK#DEPT#UUID |
| Officer queue | Existing ByCatalog partition WORK#OFFICER#SUB |
| Workload | Strong officer ledger, not eventually consistent GSI count |
| History | AuditEvents entity work#ID; strong Query, bounded continuation |

P7 commits atomically invalidate sourceVersion/rank/index membership and append work review events
alongside original membership transactions. Old allocation snapshots remain historical; stale source
revisions cannot authorize officers or contribute workload. Conservative cloud policy also requires
review after canonical version changes. P8 commits atomically refresh work queue keys and work-meta,
not assignment controls. Eventual GSI entries are strongly reloaded and stale rank/owner entries skipped.
Queue completeness is not a snapshot guarantee; empty filtered pages with continuation are possible.
Expired rank entries are excluded pending recalculation rather than placed at an obsolete rank.

Conditional bounded TransactWriteItems guards all read configuration/profile/membership/ledger,
canonical versions, priority generation/result revision and operation receipts. Namespaced global
work-meta revisions support coherent reads. Ambiguous outcomes replay a strongly read receipt or409
with SAME-ID retry. Never chunk a logical assignment/merge. Hard envelope:95 actions,380KB per action,
3MB total; snapshots<=200 strong items. Prototype manifests cap30 memberships per department/officer,
30 retained officer ledger entries and200 department entries; pruning/reconciliation is required before
exceeding bounds. Such oversized operations fail closed without partial writes. Local limits are100
departments/1000 rules/500 department memberships/2500 officer workload records/5000 department records.

Cloud fresh global/department aggregates are null/unavailable, not fabricated counts. Local aggregates
are real. Cognito account provisioning/revocation projection synchronization and ledger reconciliation
must be validated before Phase14. The trusted provision_officer_profile interface does not grant a
Cognito group and is deliberately not exposed over HTTP. Cloud process_one is disabled; no SQLite
fallback, scheduler, SQS/SNS/EventBridge/StepFunctions or import-time cloud request exists.

`WorkService.route_event({version:1,incidentId,action})` is a strict internal future event-processing
port using the same versioned/idempotent routing transaction. It is not an HTTP backdoor, event bus,
Lambda scheduler or Phase10 implementation. Producers must retain the exact action/UUID on retry.

Source-only Lambda packaging remains NON_DEPLOYABLE. Three tables/eight GSIs remain11RCU/11WCU;
write amplification, ledger/manifests, strong reads and audit storage require a later measured cost
review. CDK adds protected exact routes and Query permission only for the existing department index;
the unconditional Phase14 deployment block remains. NO AWS DEPLOYMENT PERFORMED.

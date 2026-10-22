# Event-driven architecture (Phase 10)

Phase13 preserves the same outbox/consumer boundaries and event schema1; real HTTP
lifecycle and synchronized notification races supplement existing worker-crash/
lease/retry/DLQ tests. Repair notification filter contracts are corrected. No cloud
transport was invoked. [Integration](INTEGRATION_TEST_REPORT.md), [readiness](AWS_DEPLOYMENT_READINESS.md).

Business producers → transactional outbox → dispatcher → durable consumers. Delivery is at least once, not exactly once.

## Private version 1 contract
Every envelope has eventId, eventType, eventVersion (integer1), occurredAt (aware UTC), aggregateType,
aggregateId, correlationId, nullable causationId, source=civiclens.domain, and payload. UUID references
only; maximum serialized envelope2KiB. Payload keys are officerId, previousOfficerId and escalationId.
Descriptions, evidence, coordinates, credentials and contact information never travel in events.
Consumers retrieve current authoritative data. Unsupported types/versions fail permanently.

| Producer | Events | Consumer |
| --- | --- | --- |
| Complaint insert | ComplaintSubmitted | IncidentTriageWorkflow |
| Membership change (both affected incidents) | IncidentMembershipChanged | Fresh canonical priority |
| Meaningful priority/hazard transition | IncidentPriorityChanged | Verified-hazard notification decision |
| Department/officer change | IncidentDepartmentAssigned, IncidentOfficerAssigned | Current authorized recipients |
| Officer progress | IncidentWorkStarted, IncidentProgressUpdated | Eligible current member citizens |
| Canonical lifecycle | IncidentStatusChanged | Current member citizens |
| SLA breach receipt | IncidentOverdue | Administrator operational alert |
| Triage review/failure | DuplicateReviewRequired, RoutingReviewRequired, WorkflowFailed | Administrator review |

IncidentOfficerReassigned is a supported version1 input; current assignment producers emit
IncidentOfficerAssigned for a changed officer. No consumer publishes its own input unconditionally.
Root SQL-trigger events correlate by aggregate UUID. Explicit workflow-generated follow-ups propagate
the root correlation and causation UUID. This is aggregate/root tracing, not an invented distributed span tree.

## SQLite
Schema8 adds event_outbox, event_queue, event_receipts, workflow_executions, workflow_steps,
notifications, sla_policies, sla_checks, escalations and workflow_audit. Original domain tables remain.
Complaint INSERT and outbox INSERT share one SQLite transaction through triggers. Assignment,
membership, status and priority triggers participate in their original transactions. Rollback removes both.
Pending Phase6/7 jobs are adopted on upgrade without clearing them; Phase8/9 due jobs remain intact.
A small idempotent revision adds the previous-membership invalidator to already migrated developer stores.

Dispatcher claims due records with BEGIN IMMEDIATE and a token/lease, then confirms queue acceptance
before marking dispatched. A crash after acceptance can redeliver: UNIQUE(event_id,consumer) protects
queue insertion. Consumers use durable (event,consumer,version1) receipts, stable workflow/operation
identities, existing domain concurrency guards and notification/escalation unique keys.
Claims are database-enforced across processes. No background task or Python set is the only record of work.

The existing application-owned local worker runs small event batches before servicing older Phase6–9
due work. Test mode does not start it. Explicit run-worker can drain bounded batches or run continuously
in the foreground; it does not detach processes or install Windows tasks. Scheduled checks are explicit.

## AWS preparation
One retained operations table (pk/sk, sparse KEYS_ONLY ByQueue queue/due) stores outbox, messages,
workflow steps, receipts, user notifications, escalation and control records. Strong GetItem + revision
conditions guard updates. Routine access uses bounded Query, never Scan. Business outbox Puts join
existing bounded DynamoDB transactions; existing95-action/3MB envelopes still reject oversized work
without chunking logical operations. Cloud HTTP business writes fail closed without WORKFLOW_TABLE_NAME.
Legacy low-level adapter fixtures can omit that optional table reference; that is not a production configuration.

An EventBridge custom bus routes explicit source/type/version patterns to two standard SQS queues.
Four queues include their processing DLQs; the same corresponding DLQs also catch exhausted
EventBridge target delivery. Consumer Lambda starts a deterministic Standard triage execution or handles
lightweight events with shared services. Malformed SQS records return partial failures until the native
DLQ; known permanent application failures remain inspectable in the operations-table dead-letter catalog.
A disabled hourly Lambda prepares bounded outbox dispatch, one recovered heavyweight workflow,
priority checks and SLA checks. Enabling the schedule is a Phase14 decision, not performed here.

Cloud indices are eventually consistent. Strong item rechecks protect correctness, not immediate
catalog completeness. Cloud summary is explicitly a sample of at most100 stored workflows; missing
global queue counts are unavailable, not zeros. User unread counts are bounded to100 retained records
and require controlled retention reconciliation beyond that bound. Trusted Cognito administrator/
officer lifecycle directory synchronization remains a Phase14 readiness prerequisite, as in Phase9.
No AWS mode constructs a SQLite fallback.

See [orchestration](WORKFLOW_ORCHESTRATION.md), [notifications](NOTIFICATION_SYSTEM.md),
[SLA](SLA_ESCALATION.md) and [recovery](FAILURE_RECOVERY.md).

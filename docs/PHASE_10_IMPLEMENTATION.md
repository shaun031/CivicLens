# Phase 10 implementation handoff

Historical completion record. Phase11 now supersedes its next-phase status;
see [current progress](../PHASE_PROGRESS.md) and [municipal analytics](MUNICIPAL_ANALYTICS.md).

Implementation is complete. Executed local/offline results are recorded below and in PHASE_PROGRESS.md.
Local verification is not a live AWS readiness claim.

## A. Implementation summary

Durable event-driven triage, real private inboxes, demonstration SLA escalation, workflow operations,
failure recovery and offline AWS definitions are implemented in D:\CivicLens. Phase11 is not started.

## B–C. Architecture, schema and mappings

Business transaction → outbox → accepted dispatch → durable queue → versioned idempotent consumers.
Envelopes are UUID/aware-UTC/version1/source/aggregate/correlation/causation plus ID-only payload,
bounded to2KiB. Registry rejects duplicate/unsupported consumer registrations; known causation chains
are bounded. ComplaintSubmitted starts triage; membership changes refresh canonical priority; band/
hazard, assignment, progress, lifecycle and overdue events drive appropriate notification decisions.
DuplicateReviewRequired and RoutingReviewRequired are distinct, valid review outcomes.
See [producer/consumer table](EVENT_DRIVEN_ARCHITECTURE.md).

## D. SQLite outbox and local queue

SQL triggers share original complaint/membership/priority/assignment transactions. Dispatcher and
queue claims use database tokens/leases; acceptance precedes dispatch acknowledgement. Unique keys,
receipts and original domain concurrency guards provide effectively-once side effects, not exactly-once
delivery. Source repair and controlled redrive are distinguished from blind invalid-payload replay.

## E. Incident triage workflow

ValidateComplaint → RunDuplicateDetection → EvaluateClustering → RecalculatePriority → RouteDepartment
→ EvaluateNotifications → CompleteWorkflow. Six required stages persist; previous results are reused.
Report receipt can be acknowledged before optional analysis. Review-only never force-merges or waits
indefinitely. Current manual allocation/review locks are preserved. Interrupted work resumes after leases.
See [state graph and local/cloud differences](WORKFLOW_ORCHESTRATION.md).

## F–H. EventBridge, SQS, Standard workflow and Lambda handlers

One source/type/version-filtered bus; two standard queues and two encrypted14-day DLQs, also used for
EventBridge target-exhaustion. Main visibility600seconds, receive count5, batch1, partial failures,
mapping concurrency2. Source-only consumer/starter90s, shared stage30s and scheduled90s functions
have reserved concurrency4/2/1, not provisioned capacity. Standard workflow has retry/catch/failure
recording, eligibility/review branches and a five-minute terminal bound. StartExecution names are
deterministic; retries do not imply completed processing. Scheduled recovery is bounded and disabled.

## I. SNS preparation

The boto3 adapter requires explicit enabled/eligible/opted-in operational use and returns acceptance
outcomes accurately. Topic ARN is configuration, not a hardcoded address. No subscriptions or real
email/SMS are created; normal delivery is in-app. SNS acceptance is not recipient delivery confirmation.

## J–K. Notifications and SLA

Authenticated inboxes enforce recipient ownership even for ADMIN, persist read state, support stable
pagination/filtering and expose conservative unread refresh. Notifications use safe fixed templates.
Demonstration targets separate response from resolution monitoring; current fresh priority selects
band/category/department/hazard policy. Historical on-time response is not erased by reassignment.
UTC cycles, resolved/retired exclusions, unique breach receipts and acknowledgement prevent flooding.
No legal-deadline, severity-override or completed-repair claim is made.

## L. Retry, dead-letter and idempotency design

Five attempts, exponential bounded delay and token fencing; three authorized redrives maximum.
Malformed/permanent work is retained safely. Stable workflow/operation/candidate/singleton identities,
completed-stage checkpoints, event/consumer/version receipts and notification/escalation uniqueness
prevent duplicate effects. Invalid source repair cannot be performed through an arbitrary payload editor.
See [safe recovery procedure](FAILURE_RECOVERY.md).

## M–N. Administrator UI and APIs

/admin/workflows shows execution counts, running/pending/review/failure/retry states, stage attempts,
elapsed time, safe DLQs and SLA alerts/policies. /notifications works for all roles; citizen workspace
retains its existing inbox route.15 new authenticated routes include notification list/count/read/all,
workflow list/detail/summary/retry, DLQ list/redrive/acknowledge and SLA policy/escalation controls.
Exact paths, schemas and permissions are in [API documentation](API.md).

## O. Migration

Additive schema8 adds outbox, queue, receipts, executions, steps, notifications, SLA policies/checks,
escalations and operational audit. Pending legacy jobs are adopted, not erased. Idempotent revisions
handle already migrated developer stores. Original accounts, reports, evidence and incident identity
remain intact. Cloud preparation uses one retained operations table with sparse ByQueue indexing.

## P. IAM and security

90 exact HTTP routes retain JWT scope protection except the existing public allowlist. Operational
controls require ADMIN; inbox ownership is not an administrator bypass. Unsafe local-cookie actions
require trusted Origin. Events/results/logs exclude private evidence, contacts, descriptions and tokens.
Queue policies scope specific rules; IAM scopes bus/queue/state-machine/Lambda/topic/table/index access.
Workers cannot delete evidence. No Scan, broad service grants, client AWS credentials, VPC/NAT, EC2,
RDS, GPUs, custom KMS, provisioned polling or provisioned concurrency is introduced.

## Q–S. Tests, recovery and measurements

Executed suites: backend535, isolated integration4, frontend164, offline CDK54 and browser13:
770 distinct passing cases. Targeted reruns are not counted again. Ruff lint/format, frontend lint,
application/browser TypeScript checks and the production build passed. Infrastructure build,
synthesis, template safety and zero-resource local-stage checks are recorded in
[PHASE_PROGRESS.md](../PHASE_PROGRESS.md). Existing Phase6–9 evaluations and disposable benchmarks
also ran successfully. The verification sequence initially stopped on a dry-run CLI import error;
it was fixed, the extended actual-worker restart test rerun, and remaining checks run separately.
There is no claim that that initial monolithic invocation exited successfully.

Failure/recovery assertions cover atomic rollback, database claim concurrency/token fencing, stale
leases, duplicate acceptance/delivery, malformed versions, transient retries, exhaustion/redrive,
private inbox ownership/read persistence, valid review branches and historical SLA response/reopen/
retired exclusions. SDK fixtures test partial failures and invalid outbox dead-letter persistence.
Integration kills an actual foreground worker during persisted RUNNING triage, explicitly expires only
test leases, restarts the worker and verifies one report, one open incident, six completed stages and
one receipt notification. Absent-store dry-run creates no file; initialized-store preview preserves its
SHA256 hash. An older normal store receives a migration-required message without a traceback/write.

Disposable local SQLite benchmark (100 normal workflows plus one controlled retry/recovery):

| Measurement | Observed result |
| --- | ---: |
| Dispatch median | 56.948ms |
| Normal triage median | 794.912ms |
| Normal triage-loop throughput | 1.181 workflows/s |
| SLA sweep,100 checks | 2034.186ms |
|100 duplicate enqueue attempts | 506.045ms |
| Notification insert median | 23.854ms |
| Injected failed attempt | 291.379ms |
| Recovery processing | 721.109ms |
| Invalid-message dead-letter processing | 37.544ms |

All101 workflows completed; pending outbox0; queue405 COMPLETE and one deliberately injected DEAD
invalid message. Retry time advanced explicitly by3seconds; it was not a wall-time wait. Measurements
are machine/test-load dependent, exclude cloud/auth/upload latency and are not AWS capacity forecasts.

## T. Principal files created and modified

- backend/app/events/{schema,registry}.py; repositories/{phase10_migration,event_repository}.py;
  services/{workflow_service,sla_service}.py; api/routes/workflows.py.
- backend/app/integrations/{events.py,database/dynamodb_events.py}; workflow_handlers.py;
  existing main/settings/auth-store, complaint/incident/priority/work adapters and worker hooks.
- backend/app/scripts/{run_worker,run_scheduled_checks,benchmark_events}.py; Windows worker,
  pending-event, scheduled-check and verification scripts; .env.example.
- frontend notification/workflow services/types, real inbox/bell, WorkflowsPage, protected routes,
  dashboard/navigation/status/footer/sample isolation and tests.
- infrastructure Workflows construct, Lambda options, exact route catalog, permissions/safety/capacity
  inventory, stack metadata and updated/new offline assertions.
- New backend event/SDK/dispatch-recovery tests, actual worker-process restart integration,
  notification/workflow component tests and extended responsive/Axe allocation browser scenario.
- README, PHASE_PROGRESS and event/orchestration/notification/SLA/recovery/API/database/architecture/
  development/frontend/UI/security/infrastructure/AWS-service/cost documentation.

## U. Known issues and limitations

AWS has not been run live. Source-only artifacts remain NON_DEPLOYABLE until Phase14 Linux packaging,
trusted Cognito lifecycle/directory synchronization, IAM/transport/timeouts/capacity/cost/retention review.
Cloud workflow counts are bounded samples; unavailable globals remain unavailable. Cloud unread count
is bounded to100 retained notifications pending reconciliation. Native DLQ redrive is an explicit future
AWS operational action, not a hidden cloud call from this dashboard. SNS is prepared, not normal email.
Existing upstream test-harness warnings are distinct from application failures. No zero-error guarantee
for every future environment or AWS deployment is implied by local/offline tests.

## V. Windows commands

From D:\CivicLens:

```powershell
.\scripts\run-worker.ps1 -Once -BatchSize 20
.\scripts\process-pending-events.ps1 -MaxBatches 20
.\scripts\run-worker.ps1 -Continuous
.\scripts\run-scheduled-checks.ps1 -Once
.\scripts\run-scheduled-checks.ps1 -Once -DryRun
.\scripts\verify.ps1
npm.cmd --prefix frontend run test:browser
```

Existing application-owned local worker also handles events; an external daemon is optional.
No permanent Windows task or system-wide execution-policy change is installed. Start the API with
`scripts/run-backend.ps1` and the UI with `scripts/run-frontend.ps1` in separate terminals. API startup
applies the additive schema8 migration; dry-run deliberately refuses an older/uninitialized store.
No persistent backend/frontend processes were left running by this implementation handoff.

## W. Costs

Current definitions: four tables/nine GSIs,13RCU/13WCU aggregate,321 resource definitions,90 routes,
13 outputs. Event/SQS/Lambda/Standard-transition/SNS/DynamoDB/logging usage and retries require
regional/account review; no permanent-free-tier, credits or zero-bill assumption. Hourly schedule is
disabled, SNS unsubscribed, logs7days, no custom metrics/alarms or always-on servers. Basic service
metric descriptors cover queue/DLQ backlog, Lambda errors/duration and workflow failures.
See [current assumptions and official pricing links](AWS_COST_ESTIMATE.md).

## X. Deployment status

**NO AWS DEPLOYMENT PERFORMED.** No real cloud resources, subscriptions, email, SMS or paid inference.
Only local execution, SDK stubs, offline synthesis/assertions and public documentation research.

## Y. Next phase

**Phase 11 — Advanced Municipal Administration Dashboard and Citywide Analytics. NOT STARTED.**

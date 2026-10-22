# AWS Services — definition and deployment status

Phase13 current:444 resources/131 routes, four tables/nine GSIs, no added service.
Offline assertions/synth/adapter contracts are tested, deployment remains BLOCKED.
Source-only Lambda, unbound cloud intelligence/projections and absent HTTPS frontend
hosting are source gaps, not just pending live smoke tests. [Complete inventory](AWS_DEPLOYMENT_READINESS.md),
[cost scenarios](AWS_COST_GUARDRAILS.md), [conditional runbook](AWS_DEPLOYMENT_RUNBOOK.md).

## Phase12 preparation (not deployed / not an activated cloud repair service)

The conditional DynamoIntelligence change-plan port uses existing Operations pk/sk records, strong
GetItem, bounded ByQueue index pointers, source ConditionChecks, optimistic versions and operation
receipts. Plans may include repair/request/response/resolution/recurrence/fairness-review/audit records
and original P10 outbox actions atomically; maximum100 transaction actions,30 changed records,
30 access pointers,10 events,100KB/record. No routine unrestricted Scan. SDK Stubber tests never send
AWS requests. Existing private S3Evidence port/key validation/sanitization handles repair photos without
public ACLs. No new bucket, table, bus, queue, Lambda or ML service was added.

CDK adds28 exact JWT-protected routes and14 small version1 repair/recurrence/review event types to the
existing notification rule. Four Dynamo tables, nine GSIs, four Lambdas, one private bucket, the original
bus/queues/SFN/SNS remain.131 API routes; local authorization still enforces roles beyond the shared
Cognito scope. Deployment remains blocked by the unsatisfiable Phase14 rule and source-only artifacts.

Remaining cloud activation prerequisite: bind the server-side domain command planner to these ports,
bootstrap scoped canonical/membership/analytics projections, package/test the Linux artifact and review
conditional capacity/read patterns under real IAM. AWS-mode Phase12 HTTP intentionally returns503;
it does NOT fall back to local SQLite or claim a cloud write. This work is not performed by Phase12.

## Phase11 analytics preparation — current

Reuses the Phase10 operations table and event workers: exact protected analytics/report routes,
explicit scope/reporting zone/source bounds in Lambda environment, bounded strong Query/GetItem
projection reads and conditional generation/receipt writes. No Scan, OpenSearch/Redshift/Kinesis,
new table/GSI, VPC/NAT or always-on analytics service. Same narrowly scoped operations-table IAM
permissions suffice; private evidence access is unchanged. Complete trusted cloud source extraction,
controlled bootstrap/reconciliation/retention, account lifecycle sync and actual IAM/latency/cost
verification remain Phase14 prerequisites. Cloud absence/staleness returns unavailable, not zero.
[Access patterns](ANALYTICS_DATA_MODEL.md). No AWS service API calls or deployment were performed.

## Phase10 current offline definitions — NO AWS DEPLOYMENT

EventBridge application bus: source civiclens.domain, explicit type/version rules. Two standard
SQS queues + two14-day DLQs, SQS-managed encryption, main retention4days/visibility600seconds,
maxReceiveCount5, partial-batch failure reporting, batch1, maximum mapping concurrency2.
DLQs also catch EventBridge target retry exhaustion. No customer-managed KMS/provisioned pollers.
Three additional source-only Lambdas: SQS consumer/starter90s, shared workflow-stage30s,
bounded scheduled dispatcher/recovery/SLA90s,512MB, no VPC/layers/provisioned concurrency.
Standard state machine terminates within5minutes with retry/catch/failure recording, no human callback.
SNS operational topic has no subscribers; adapter is explicitly opted-in and not normal citizen email.
One disabled hourly EventBridge schedule, no one-schedule-per-incident. Four seven-day log groups,
structured safe IDs/categories; basic service backlog/DLQ/Lambda/workflow failure metrics are available
for future operations. No new paid custom metrics/alarms/dashboards are provisioned.

One retained operations table + GSI brings aggregate capacity to13/13 (four tables/nine GSIs).
321 resource definitions,90 explicit HTTP routes,13 existing outputs. Source-only assets and the
unconditional Phase14 CloudFormation rule remain NON_DEPLOYABLE. Local stage has zero cloud stacks.
IAM scopes bus publication, queue consumption, state-machine start, designated Lambda invocation,
SNS publishing and table/index access to exact resources. Processing workers cannot delete evidence.
All account calls are offline SDK stubs or CDK synthesis; no AWS resources or email subscriptions exist.
See [cloud limitations](EVENT_DRIVEN_ARCHITECTURE.md); earlier inventory below is historical.

Phase9 prepares department/configuration/membership/assignment/history records on existing Incidents
and AuditEvents tables. Existing ByDepartmentPriority/ByCatalog/ByStatusPriority serve sparse work
queues, with strong revalidation and ledger-based capacity checks. Lambda retains MANUAL_APPROVAL,
workload weights1/2/3/4, no cloud worker, source-only/non-deployable packaging and the Phase14 block.
75 exact API routes total, including29 new JWT/scope-protected work routes. No new AWS service/table/GSI,
EventBridge/SQS/SNS/StepFunctions, scheduler or live account request was introduced. Trusted Cognito
subject/profile lifecycle synchronization still requires predeployment validation. See
[cloud protocols and bounds](ASSIGNMENT_DATA_MODEL.md). NO AWS DEPLOYMENT PERFORMED.

Phase8 prepares deterministic Lambda-friendly scoring, conditional Incidents priority sidecars,
AuditEvents history and existing ByStatusPriority/ByCatalog namespaced ranking. Ten extra JWT-protected
routes; no extra GSI/table or event orchestration. Aggregate11RCU/11WCU remains unchanged. Cloud daemon,
scheduler, deployment and native packaging validation remain disabled/unverified. [Details](PRIORITY_DATA_MODEL.md).

Phase7 remains offline only: existing Complaints/Incidents/AuditEvents, one additional sparse
Incidents.ByCatalog GSI,36 JWT/public routes in total, scoped conditional write/query permissions.
Three tables/eight GSIs,11/11 capacity; no queue/scheduler or deployed worker. Deployment remains
unconditionally blocked. [Transaction design and limitations](INCIDENT_DATA_MODEL.md).

Phases 1–5 define and extend the foundation locally. **No resources are deployed.** SQS, EventBridge, Step Functions, and SNS remain future work.

## Current Phase 6 responsibilities (supersedes earlier inventories)

No AWS resources exist from this work. Source-only Python3.13 x86_64 Lambda remains protected by
the unconditional Phase14 CloudFormation blocker; its artifact intentionally lacks dependencies.
Pillow/scikit-learn/NumPy/SciPy contain native code: Windows wheels cannot be copied into Lambda.
Phase14 must resolve/pin Linux-compatible Python3.13 dependencies, inspect licenses/supply chain,
measure compressed/uncompressed artifact limits, import/cold-start memory/CPU and the current
256MB/15s settings. Local success does not verify this future deployment. No Docker/GPU/model download
is required for local operation. The default fixed TF-IDF corpus is tiny Python source, not a large
embedding model. Optional embeddings are deliberately not packaged or required.

InternalGeography queries eligible private complaint cells independently of PublicGeography.
MatchingWork queries namespaced durable jobs/candidates; primary reads revalidate eventual index
results. Candidate completion uses bounded conditional transactions preserving review decisions.
The shared Complaints table also holds versioned fingerprint items, avoiding new tables/indexes
for each modality. There are now three tables/seven GSIs at aggregate10RCU/10WCU, 23 explicit HTTP
routes/integrations and one private S3 evidence bucket. Seven new routes require JWT/scope plus
backend ADMIN enforcement. IAM adds Query only on InternalGeography and MatchingWork, not Scan or
wildcard index permissions. S3 GetObject remains restricted to complaints/* through trusted storage.

Cloud submission persists an atomic outbox; a permanent Lambda worker is explicitly disabled.
Authorized admin recheck processes a bounded single source. Future SQS consumption can invoke the
same execution interface but is NOT implemented in Phase6: no queue, EventBridge rule, scheduler or
cloud daemon. GSI propagation, legacy geo-attribute backfill, high-latitude cell bounds and demo
candidate catalog caps need deployment review. No automatic cloud matching latency/SLA is promised.

## Preserved Phase 5 responsibilities

DynamoDB adds one sparse PublicGeography(publicGeoCell,publicGeoSortKey) GSI to the existing Complaints table. Five total GSIs and three tables each retain 1 RCU/1 WCU, aggregate 8/8. Sanitized public projection items are transactionally maintained; strong primary rechecks prevent stale withdrawn GSI records from exposing former public data. Owner search/analytics use a bounded ByCitizen catalog, not Scan; this limited demo strategy still needs cloud performance/index review.

The shared Lambda gains exact Query access to PublicGeography and PutItem-only access to the existing AuditEvents table. Existing owner-table, ByCitizen, private evidence prefix and own-log permissions remain. No DeleteItem, Scan, ListBucket or administrator service grant was added. API Gateway has 16 explicit routes: health and three public discovery GETs are anonymous, while existing private routes and two new publication PATCH routes require JWT/API scope. Backend enforces citizen ownership and administrator review independently. Current template is 67 resource definitions/13 outputs; local stage remains zero stacks. S3 evidence stays private and is not automatically published. No real SDK transport or AWS deployment occurred.

Cloud native packaging, trusted Cognito roles, IAM, consistency, abuse controls, quotas, read amplification, Lambda latency and regional pricing remain Phase 14 verification tasks. No paid location/geocoding/search engine or extra table was introduced.

## Phase 4 prepared integration

The local runtime uses SQLite/private filesystem only. Lazy boto3 adapters prepare DynamoDB conditional complaint creation, user-scoped idempotency, summary/rate records, owner GetItem, ByCitizen Query + BatchGet pagination and private S3 put/get/delete of sanitized evidence. Complaints and their image metadata form one DynamoDB item; no image binaries enter DynamoDB. No new AWS table/index/service was introduced. SDK stubs/mocks verify adapter calls while live SDK transport is forbidden in tests.

The existing Lambda role now has scoped item operations on Complaints, Query only on ByCitizen, and GetObject/PutObject/DeleteObject only on the retained evidence bucket's `complaints/*` prefix. It has no incident/audit access, Scan, ListBucket, public ACL or administrator grants. Five explicit JWT/API-scope complaint routes join the identity routes, including the owner summary and authenticated image path. Backend CITIZEN/ownership checks remain mandatory; gateway JWT authentication alone does not grant access to another user's data. All definitions are synthesis-only, deployment-blocked and unverified in a live account.

| Service | Phase 1 status and intended responsibility |
|---|---|
| API Gateway | Defined: public health plus JWT-protected profile/identity/portal routes and Lambda proxy integration |
| Lambda | Defined: shared Python 3.13 FastAPI/Mangum health handler; source-only asset is not deployable |
| DynamoDB | Defined: Complaints, Incidents, AuditEvents tables; four GSIs; no actual data access |
| S3 | Defined: private evidence bucket, SSE-S3, HTTPS-only policy; uploads deferred |
| Cognito | Defined in Phase 2: Lite email User Pool, public code-flow client, classic hosted domain, three groups, API scope, and HTTP API JWT authorizer; not deployed |
| SQS | Planned: background buffering/retries |
| EventBridge | Planned: domain-event routing |
| Step Functions | Planned: assignment, escalation, and repair workflows |
| SNS | Planned: approved notification fan-out |
| CloudWatch | Defined: seven-day Lambda log group; metrics/alarms/dashboards deferred |
| IAM | Defined: Lambda trust, scoped log writes, API invoke permission; data grants remain opt-in |
| CloudFormation | Locally synthesized stack, seven outputs, and unsatisfiable deployment-block rule |

Deployment occurs only in Phase 14 after explicit user initiation, packaging verification, and a cost review. See [INFRASTRUCTURE.md](INFRASTRUCTURE.md) and [AWS_COST_ESTIMATE.md](AWS_COST_ESTIMATE.md).


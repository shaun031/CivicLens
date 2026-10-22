# AWS deployment readiness — Phase 13

**Overall: BLOCKED.** This is an offline assessment, not authorization to deploy.
No AWS account, credential, resource, billing API, Cognito endpoint or storage service
was accessed. Public documentation/advisory websites are not AWS control-plane calls.

## Source inventory and controls

The demo template defines **444 resources,131 routes/integrations,132 Lambda invoke
permissions**, and28 resource types. Local stage defines zero stacks/resources.
All constructs are under `infrastructure/lib/constructs`; the stack composes them in
`lib/stacks/civiclens-stack.ts`. Names/ARNs are CloudFormation references, not embedded credentials.

| Resource / construct | Purpose/configuration | Access, persistence, logging and cost |
|---|---|---|
| Cognito UserPool, BrowserClient, LoginDomain, ApiResourceServer,3 groups / Authentication | Email verification, Lite, min12 password, code+PKCE-compatible public client, no secret/password/implicit flow;15min access/id and1day refresh | CITIZEN/OFFICER/ADMIN groups trusted-only; revocation enabled; retained pool, production deletion protection. MFA currently OFF. MAU/email and domain/TLS choices need pricing/provisioning review |
| HTTP API, JWT authorizer, default stage,131 integrations/routes / ApiGateway | Payload v2, exact origins, four public GETs;127 JWT+`civiclens/access` routes | Backend rechecks identity, group and object permissions. No unrestricted `$default` application route. API requests/transfer and abuse need quotas/throttling review; no frontend hosting here |
|4 Lambda functions / BackendLambda, Workflows | API Python3.13 x86_64 256MB/15s; Consumer512MB/90s, Step512MB/30s, Scheduled512MB/90s | Worker reserved limits4/2/1, API has no reserved cap in source. Source-only asset excludes data/.env/.venv/tests/caches/coverage; no dependencies bundled. Request/duration costs; live memory/cold-start UNKNOWN |
| Complaints, Incidents, AuditEvents / Database |3 tables plus8 GSIs; user/canonical/candidate/priority/work sidecars | Provisioned1RCU/1WCU per table/index; Dynamo-managed encryption, RETAIN; production deletion protection. PITR OFF. Strong base reads after eventual key-only indexes; no normal Scan |
| Operations / Workflows |4th table +9th GSI (`ByQueue`), pk/sk namespaces | Outbox/receipts/workflows/notifications/analytics and intelligence plans.1RCU/1WCU each; same encryption/retention/PITR controls; shared revision hot-key/capacity risk |
| Evidence bucket + policy / Storage | One PRIVATE evidence bucket, SSE-S3, all public blocks, TLS only, bucket-owner enforced | Only generated `complaints/*` objects; no public/list grant, scoped GET/PUT/cleanup DELETE. RETAIN, auto-delete OFF, versioning OFF. Retention/backup undecided; bytes/requests/transfer billable. This is NOT a hosting bucket |
| Domain EventBus +3 rules / Workflows | v1 source/type routing to processing/notification SQS; hourly rule DISABLED | PutEvents scoped to bus, minimal ID envelopes, bounded target retries/age. Scheduling and event/retry volume can cost at low activity |
|2 main SQS queues +2 DLQs +4 queue policies / Workflows | Managed encryption,600s visibility; main retention4days, DLQ14days, maxReceive5; batch1,2 event mappings with partial failure response | Rule-source policies scoped; consumer reserve4 across2 mappings(max2 each). Polling/duplicate/retry requests billable; live redrive requires explicit operator approval |
| Standard state machine / Workflows |5min execution limit, bounded retried Lambda stages, catch→record failure→Fail, no long human waits | Invoke only Step/version ARN, no direct public start. State/receipt idempotency, ID-only envelopes. Transition/retry cost; live behavior NOT_VERIFIED |
| SNS OperationalAlerts / Workflows | Unsubscribed topic, opt-in adapter OFF | Scoped publisher/approved operational types only, no hardcoded citizen recipients. No email/SMS promise; subscriptions/consent/cost not activated |
|5 roles +5 policies / permissions.ts | Lambda API/Consumer/Step/Scheduled and state-machine execution | No managed admin policy or normal Scan/DeleteItem. Explicit table/index/object/bus/queue/machine/topic grants; runtime least privilege asserted offline, not live IAM certification |
|4 log groups / Monitoring, Workflows |7day retention, RETAIN, tracing OFF | Scoped stream writes, safe category/correlation logging. Metrics descriptors only; zero alarms/dashboards. Ingestion/retained logs cost; owner must implement monitoring decision |
| CloudFormation rule / stack | Unconditional incompatible Phase14 approval assertion | Deliberately prevents deploying this source-only stack. Do not remove it just to make deployment succeed |

Exact logical IDs/properties are in the ignored synthesized template, not a fabricated
named-resource inventory. Environment dependencies are in [environment guide](ENVIRONMENT_CONFIGURATION.md).
CDK tests cover configuration, JWT route allowlists, indexes, storage/TLS, exact IAM,
native queue relationships, state-machine retry/catch/timeout, safe staging and the blocker.
131 expanded backend OpenAPI operations exactly match the131 synthesized routes.

## Adapter equivalence: implemented source is not activated infrastructure

| Local/cloud pair | Offline evidence | Readiness limitation |
|---|---|---|
| AuthStore/local cookies vs Cognito | Argon2/session tests; RSA/JWKS/userInfo fixtures; local password endpoints absent in cloud | Hosted login, trusted first/admin officer provisioning, citizen group assignment after verified signup, revocation and real HTTPS callbacks unverified |
| SQLiteComplaints vs DynamoComplaints/Discovery/Duplicates | Stubbed atomic record/receipt/outbox, bounded Query/BatchGet, pagination, private-owner authorization | Real transaction capacity, GSI delay, historical projection/bootstrap and cloud stage sizing need live validation |
| SQLiteIncidents vs DynamoIncidents | Conditional membership plans, max30-member envelope, idempotency/conflicts and race stubs | No unbounded cluster transaction or GSI-only uniqueness guarantee; real contention/readback unverified |
| SQLitePriority/Work vs DynamoPriority/Work | Version guards, workload ledger/plans, sidecars/query access tests | Scoped canonical catalogs, trusted officer directory/eligibility and controlled materialization need completion/reconciliation before operational cloud use |
| LocalEvidence vs S3Evidence | Private key/MIME/size/collision/read/cleanup Stubber tests; bucket assertions | Native binary encoding, uncertain writes, actual object ACL/policy and request envelope smoke tests unverified |
| SQLiteEvents/local worker vs DynamoEvents/EventBridge/SQS/SFN | Transactional outbox/receipts, partial publishing, batch failures, deterministic executions, leases/retries/DLQ fixtures | Actual transport delivery/IAM/visibility/timeouts and outbox dispatch schedule still require controlled cloud tests; hourly schedule is disabled |
| Private local inbox vs Dynamo in-app/SNS | Recipient/source recheck and dedup tests; SNS explicitly skips without eligibility+consent | No automatic citizen external notifications; subscriptions and operational ownership undecided |
| SQLiteAnalytics vs DynamoAnalytics | Bounded versioned scoped manifests/chunks, checksums, dirty/TTL fences, strong rehydration stubs | Trusted source projection bootstrap/publisher is not an end-to-end activated data pipeline; fail503 rather than fake zero counts |
| SQLite civic intelligence vs DynamoIntelligence | Generic guarded change-plan port, strong Get, ByQueue pointers, transactional outbox SDK tests | **BLOCKER:** domain planner/authorization/source projection integration is not bound in create_app; cloud service stays None and protected workflows503. No SQLite fallback |

## Deployment blockers (source work, not merely live validation)

1. Complete/authenticate/bind required cloud domain services and analytics/intelligence
   projection bootstrap; test actual supported workflow parity without local fallback.
2. Build a pinned, hash-verified Linux Python3.13 x86_64 deployment artifact, measure
   package size and import/native compatibility; use it in CDK. Windows `.venv` is invalid.
3. Implement an approved HTTPS frontend host and SPA fallback/headers. No hosting
   bucket/distribution/certificate/domain deployment exists; evidence bucket cannot be reused.
4. Replace placeholder/demo OAuth URLs, implement trusted citizen/staff group provisioning,
   choose staff MFA/revocation and exact production origin policy. Never grant public signup ADMIN.
5. Approve data protection/retention, region/account budget, API concurrency/throttling,
   workflow dispatch/schedule and operational owner decisions. Template resource headroom
   is56 below500; future hosting/monitoring changes require renewed exact resource/IAM review.

## Cloud-only validation, after blockers and explicit Phase14 approval

Validate deployed health and payload-v2 handling, Cognito code+PKCE/group/logout,
real-role IDOR tests, maximum bounded JPEG/multipart/base64 upload, Dynamo transaction
limits/GSI staleness/conditional replay, private S3 get/cleanup, outbox→bus→queue→SFN,
DLQ/visibility/redrive, notification ownership, repair workflow/recurrence/fairness,
HTTPS/static SPA routing, backup/rollback/restore and measured billing/monitoring.
No passing offline synth is presented as evidence that these live checks passed.

See [Lambda compatibility](LAMBDA_COMPATIBILITY.md), [cost guardrails](AWS_COST_GUARDRAILS.md),
[conditional deployment runbook](AWS_DEPLOYMENT_RUNBOOK.md) and [risks](KNOWN_RISKS.md).

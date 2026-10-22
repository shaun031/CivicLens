# AWS cost estimate and assumptions

## Current Phase13 release assessment

See [idle/demo/moderate/runaway-workflow usage worksheet and safeguards](AWS_COST_GUARDRAILS.md).
Four tables/nine indexes remain13RCU/13WCU provisioned in source, even at idle. No
currency quote/account entitlements/live billing verification or zero-cost guarantee.
Hosting/HTTPS, backups/retention and retry/polling/transfer costs must be included.
No AWS resources or Budget were created. Earlier phase inventories below are historical.

## Phase12 source-only implications

NO AWS DEPLOYMENT PERFORMED; this phase creates no billable cloud resources. Future costs depend on
region, pricing plan, usage and retention; a permanently zero bill is not guaranteed. No current unit
price is asserted here. Estimate using verified deployment-time rates:

- Repair photo storage = attempts × mean sanitized photos/attempt × mean bytes/photo × retention;
  citizen feedback photos add the same calculation. Example volume assumption only:1000 attempts ×
  two200KB photos ≈400MB before feedback/retention, NOT a measured production size or price.
- S3 PUT/GET and transfer count actual uploads/retries and authorized views; EXIF stripping does not
  eliminate storage/requests. Known failed staging cleanup can require DELETE requests.
- Dynamo costs include conditional record writes, request/response records, sparse access pointers,
  receipts/audits/outbox, strongly consistent authorization reads and bounded analytics projections.
  A response is not “one write” once audit/event/index work is included.
- P10 events use existing EventBridge/SQS/Lambda delivery, retry/DLQ and persistent in-app inbox records.
  No email/SMS is sent. More participants mean more notification records and processing work.
- Recurrence limits candidate reads to100 scoped historical incidents/check but may fetch two private
  photos per candidate; fairness uses scoped projections/revision cache, not an unbounded per-refresh
  scan. Retained evidence/audits/projections/logs continue costing after workflows complete.

No EC2/NAT/RDS/OpenSearch/paid ML or additional continuously provisioned service is introduced.

## Phase11 analytics delta — offline only

No new paid analytics service, table, GSI, provisioned capacity or always-on worker. Existing totals
remain four tables/nine GSIs at13RCU/13WCU aggregate.13 protected routes bring103 routes/360 resource
definitions. Strong projection reads, generation staging/replacement, transactional event receipts,
export audit and retained old generations consume read/write capacity and storage; they are not free
because no new table was added. Partial/empty queries, retries and UI refreshes also consume requests.
Local SQLite benchmark timings do not establish Lambda duration/GB-seconds or cloud throughput.

At most5MiB/500 bounded chunks per municipal generation,240KB per chunk, with <=1hour freshness;
actual configured refresh/retention/export/abuse volume must be reviewed before Phase14. No automated
unbounded backfill/polling or public exports. Use account/region-specific current prices and eligibility
at deployment review; no permanent free tier, credits or zero-bill guarantee. Prior pricing references
below are historical research, not a new Phase11 live pricing verification. No AWS was contacted.

## Phase10 current cost model — offline, no deployment or bill guarantee

Definitions add one operations table/GSI (total four/nine at13RCU/13WCU aggregate), three worker
Lambdas, one event bus/two routing rules, two queues/two DLQs, one Standard workflow, one unsubscribed
SNS topic and a DISABLED hourly rule. Seven-day logs; no new alarms/custom metrics, VPC/NAT, EC2,
RDS, GPUs, AI APIs, custom KMS keys, provisioned concurrency or provisioned polling.
Provisioned DynamoDB capacity is a recurring capacity budget even when empty; transactions, strong
reads, index writes, retained workflows/receipts/audits and private evidence add consumption/storage.

Illustrative planning volume (not a measured AWS forecast):100 new complaints/month, roughly4–8
meaningful internal events each, one triage execution each, about10–12 normal Standard transitions
per execution, under100 selected operational alert publications, and up to720 scheduled invocations
only if an hourly rule is explicitly enabled. Retries/duplicate delivery/rechecks/redrive increase all
of these. Native SQS polling can generate charged requests even without application reports.
Use actual regional/account prices, taxes and account-wide eligibility at Phase14; do not assume
permanent free tier or credits. Local SQLite timings are not Lambda GB-seconds estimates.

Budget formula: EventBridge billable event units + SQS send/receive/delete/poll/redrive requests +
Lambda requests and memory-GB×billed-seconds + Standard state transitions + selected SNS publications/
confirmed-channel deliveries + provisioned DynamoDB capacity/storage + CloudWatch ingestion/storage.
Count retries, partial batches, DLQs, empty polling and SDK reads, not just accepted complaints.
Long retention, internet abuse, excessive refreshes, native hash cold starts and undersized1WCU tables
are risks. Normal UI fetches on navigation/manual refresh; there is no high-frequency notification timer.

Public pricing documentation checked2026-10-20 (no account/credential API used):
[EventBridge](https://aws.amazon.com/eventbridge/pricing/), [SQS](https://aws.amazon.com/sqs/pricing/),
[Lambda](https://aws.amazon.com/lambda/pricing/),
[Standard workflows](https://aws.amazon.com/step-functions/pricing/),
[SNS](https://aws.amazon.com/sns/pricing/), [DynamoDB](https://aws.amazon.com/dynamodb/pricing/),
[CloudWatch](https://aws.amazon.com/cloudwatch/pricing/).
No fixed currency estimate is fabricated before a region/account/package and measured Lambda profile
are selected. Earlier per-phase inventory/cost statements below are historical, superseded here.

Phase9 adds no table/GSI/provisioned capacity: three tables/eight indexes remain11RCU/11WCU aggregate.
This is an offline provisioned definition, not a spend guarantee or deployed bill. P7 transactions now
write work invalidations/review audits; P8 updates work rank keys/revisions. Assignments write receipts,
history, ledgers/manifests and sparse department/officer index entries. Strong workload reads and
conditional transaction guards increase consumption/storage; candidate sets are bounded and may hit
safe atomic-envelope limits. No normal Scan or new paid API exists. Real cloud usage/cost is unmeasured.
Profile synchronization, ledger reconciliation and production materializations must be cost-reviewed
before Phase14. No live pricing query or AWS deployment was needed for this implementation.

## Current Phase 8 delta — NO DEPLOYMENT

No new base table/GSI:3 tables/8 GSIs retain11RCU/11WCU provisioned inventory.46 routes,157 resource
definitions,13 outputs; one source-only Lambda/private bucket. Priority sidecars/history/receipts add
storage and transactional writes/read guards; updating/removing ranking keys writes existing sparse
GSIs. P7 changes also invalidate priority sidecars/queue revision transactionally. Periodic aging can
increase work even without new reports, and the shared revision key is a future throughput hot spot.
Global cloud fresh priority summaries are unavailable pending controlled materialization. No monetary,
credit/free-tier or zero-cost guarantee is made; no account was contacted. EventBridge/SQS scheduling
is deferred to Phase10, not implemented. [Readiness/limits](PRIORITY_DATA_MODEL.md).

## Current Phase 7 inventory — NO DEPLOYMENT

Three tables plus EIGHT GSIs total11RCU/11WCU. One sparse KEYS_ONLY Incidents.ByCatalog adds1/1 beyond
Phase6.36 routes/integrations,127 resource definitions,13 outputs; one source-only Lambda/private
bucket, no scheduler/queue/AI service. Conditional membership writes, unchanged-member guards, receipt,
audit and summary updates increase transactional capacity/storage use. No free-tier/credit entitlement
or operating-cost guarantee. Review-only may increase human workload. [Limits](INCIDENT_DATA_MODEL.md).
Earlier cost/inventory sections below are historical.

## Phase 6 current inventory and cost delta — NO DEPLOYMENT

Two new sparse provisioned indexes at1RCU/1WCU each bring the total to **three tables + seven GSIs,
10RCU/10WCU**, versus Phase5's8/8. No new base table, queue, hosted AI service, GPU or semantic model.
There are23 routes/integrations (88 total resource definitions), one shared Lambda/private bucket.
Earlier inventory/cost sections below are historical. Sparse indexes still consume provisioned
capacity budget; no free-tier or credit entitlement is guaranteed.

Each comparison retains a bounded numeric/explanation/version record per canonical pair; growth is
O(retained candidate pairs), not free or automatically pruned. Durable jobs and cached fingerprints
also consume storage/writes. Submission adds one transactional outbox Put and internal-geo index
maintenance. Querying neighboring cells and strongly reloading items consumes index/base reads;
review catalogs (default cap2,000) and manual rechecks can repeat work. Transactions cost more than
ordinary writes and1WCU can throttle bursts; job retries must be included in a measured budget.

Image cache misses add private S3 GETs and local hash CPU; later matches reuse fingerprint items.
UI comparison photos independently add authorized GET/transfer. Max2 photos/report and4 comparisons
bound work, but reused-photo hashing does not avoid all storage reads. No photos become public.
Cold sklearn imports/native dependencies increase Lambda package size, memory and billed duration;
local cold/warm measurements are not Lambda estimates. Current256MB/15s settings are unverified for
this workload and must be profiled before Phase14. Optional embedding models would add packaging,
memory/cold-start cost and are not part of this phase.

All tests/benchmarks use disposable local data or SDK stubs; synthesis is offline. No AWS charges
were incurred by these operations. At Phase14, check actual account/region eligibility and shared
free-tier/credit usage, capacity, retention, transfer, abuse limits and current pricing. Do not treat
these prototype capacities as either production sizing or a zero-bill guarantee.

## Phase 5 current delta — no cloud charges from this work

Current definitions add exactly one provisioned sparse GSI at 1 RCU/1 WCU: **three tables + five GSIs, aggregate 8 RCU/8 WCU**, up from 7/7. A sparse index still has provisioned-capacity costs even with few public entries; no free-tier/credit entitlement is guaranteed. Approval/rejection/withdrawal add transactional writes and append-only AuditEvents storage. Retained public tombstones and audit events need an approved retention policy later.

There are 16 explicit HTTP routes/integrations (67 resource definitions), still one shared Lambda and private evidence bucket. Public geographic reads add hashed quota updates, neighboring-cell GSI Query calls and strongly consistent BatchGet rechecks; pagination can repeat candidate work. Owner cloud search/analytics may Query/BatchGet up to the 5,000-record demo cap per request and is not production-cost optimized. Rate limits bound individual identities, not aggregate internet traffic. Review Lambda duration/15-second timeout, hot-cell throughput, public abuse and transfer before any deployment.

No OpenSearch, Amazon Location, geocoding service, EC2, RDS, NAT or additional table was introduced. Local benchmarks/tests and source synthesis incur no AWS usage. Consult current [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/) and [HTTP API pricing](https://aws.amazon.com/api-gateway/pricing/) with the actual region/account before Phase 14; no numerical cloud quote or zero-bill guarantee is asserted. The Phase 1/4 inventory below is historical and its 4-GSI/7-unit/11-route counts are superseded by this section.

Phase 1 creates no cloud resources, so the project incurs no AWS usage from this implementation. This is a configuration inventory and cost model for a future low-traffic demonstration, not a quote or a guarantee of free deployment. Region, account plan, existing workloads, request counts, duration, item/image sizes, transfer, and retention must be measured before Phase 14.

## Phase 4 usage extension — no deployed cost incurred

Local SQLite/filesystem and mocked/stubbed AWS tests do not incur AWS service usage. The template now has 11 explicit HTTP routes/integrations, still one Lambda, the same three tables/four GSIs and one private bucket. No additional paid service, table or index was introduced. Existing provisioned capacity is unchanged; this does **not** imply that it can sustain uploads at arbitrary rates.

After an eventual approved deployment, each new complaint writes its metadata, durable idempotency mapping and owner summary transactionally, plus an atomic per-citizen quota counter. DynamoDB transactions perform prepare/commit work and consume more capacity than corresponding ordinary item writes; cost also depends on serialized item size and GSI updates. A table/index at 1 WCU can throttle even low-burst transaction traffic. Owner lists use a KEYS_ONLY Query followed by BatchGet, so budget both index/base reads. No unrestricted Scan is implemented. See [DynamoDB transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html) and [pricing](https://aws.amazon.com/dynamodb/pricing/).

Evidence is at most two sanitized 1.5-MiB files per complaint: 100 maximum-sized two-photo complaints retain up to 300 MiB of evidence before other objects/metadata. Actual sanitized sizes vary. Creation entails S3 PUTs, authenticated views entail S3 GETs and Lambda/API transfer, and failed staging may entail DELETE/extra requests. Repeated views/retries and retained orphans can increase requests/storage; public/private access settings do not waive billing. Native image decode/re-encode adds Lambda duration/memory usage, even though a 4-megapixel input cap bounds individual work. Review actual regional/account terms and [S3 pricing](https://aws.amazon.com/s3/pricing/) before Phase 14. No zero-bill guarantee is made.

| Service | Expected quantity per deployed stage | Why selected | Eligibility and possible charges |
|---|---|---|---|
| DynamoDB | 3 Standard tables + 4 GSIs; aggregate 7 RCU and 7 WCU | Small, explicit provisioned footprint | Current published allowance targets 25 provisioned RCU/WCU and 25 GB Standard storage, subject to eligibility/shared consumption. Excess provisioned capacity is billed even when idle; storage and other features can cost extra. Pay-per-request has a different billing model and does not consume the provisioned-capacity allowance. [Pricing](https://aws.amazon.com/dynamodb/pricing/) |
| Lambda | 1 function; 256 MB, 15-second ceiling, x86_64 | Runs only on requests | Requests and GB-seconds outside applicable allowances/credits can be billed. A timeout is a ceiling, not an expected duration; memory/cold starts must be profiled. No provisioned concurrency. [Pricing](https://aws.amazon.com/lambda/pricing/) |
| API Gateway | 1 HTTP API, 1 health route, 1 integration, 1 default stage | Simple Lambda proxy with explicit routes | HTTP request volume and outbound data transfer can cost money; do not assume permanent request credits. [Pricing](https://aws.amazon.com/api-gateway/pricing/) |
| S3 | 1 private evidence bucket plus bucket policy | Evidence storage with SSE-S3 | Stored GB-months, PUT/GET requests, and data transfer can exceed allowances/credits. Retained buckets keep accruing storage usage. No replication/version history/customer KMS key. CDK asset storage is a separate eventual bootstrap consideration. [Pricing](https://aws.amazon.com/s3/pricing/) |
| CloudWatch Logs | 1 log group, 7-day retention | Bounded diagnostic history | Ingested/stored log volume and queries may be billed outside applicable allowances. Retention does not limit ingestion rate. No custom metrics, alarms, dashboards, or tracing in this phase. [Pricing](https://aws.amazon.com/cloudwatch/pricing/) |
| IAM | 1 execution role, 1 scoped inline policy, Lambda invoke permission | Minimal runtime permissions | No standalone compute resource; permissions can enable chargeable usage of other services. No users or keys. |
| CloudFormation / CDK | 1 future stack; local synthesis and assertion tests | Repeatable definitions | The defined AWS resources drive the usage estimate; deployment tooling and artifact storage must also be reviewed. No third-party/private extensions are used. |

Three base tables contribute 3 RCU/3 WCU; two complaint GSIs add 2/2; two incident GSIs add 2/2. Total **7 RCU/7 WCU per stage**. Demo plus production would provision 14/14 and duplicate storage/other service usage; other workloads share allowances. Read/write capacity units depend on item size and consistency, and GSI writes consume their own capacity. A 1-WCU index can throttle writes. These are starting values, not a production sizing claim.

Credits are a finite, time-limited balance, distinct from recurring service allowances. Account eligibility and Free/Paid plan terms vary; confirm the actual account status and current [AWS Free Tier terms](https://aws.amazon.com/free/) before deployment. There is no promise that all services stay free.

## Deliberately excluded

### Phase 2 Cognito addition

One Lite User Pool, one browser client, one classic hosted-UI domain, three groups, one API resource server, and one HTTP API JWT authorizer are now defined locally. Identity/profile/portal routes add gateway requests and Lambda executions when eventually deployed. No Cognito usage is incurred by local authentication or mocked tests.

Cognito costs depend on monthly active users, plan, federation type, authentication/request quotas, messaging, and optional features. Lite/classic hosted UI is explicit to avoid inadvertently choosing Essentials/Plus features. SMS, premium managed-login branding, advanced threat protection, machine-to-machine grants, and extra authentication triggers are absent. Verification/recovery email and future SMS or SES integrations require separate delivery/quota/pricing review. Do not infer that every feature or message is free from a user allowance. Verify the selected account/region and current [Cognito pricing](https://aws.amazon.com/cognito/pricing/) before Phase 14; no permanent cost guarantee is made.

EC2/ECS/EKS, NAT gateways, VPCs, RDS, load balancers, custom domains/hosted zones, global tables, DAX, streams, automatic scaling, point-in-time recovery/paid backups, S3 replication/versioning, customer-managed KMS keys, provisioned Lambda concurrency, layers, tracing, custom monitoring dashboards, and unrelated AI services.

## Phase 14 pricing review

Select region/account; verify current Free Tier and credit expiry/eligibility; inventory shared allowances and existing spend; estimate realistic peak and monthly traffic; model Lambda duration, all table/index capacity, stored evidence and log ingestion, API/S3 request/transfer costs, and CDK bootstrap storage. Review backup/recovery needs before deciding to leave backups off. Configure approved budgets/alerts, throttling and abuse controls before exposure. All actual account operations are deferred.

Tables, evidence, and logs use RETAIN. Stack deletion alone will not clean up retained resources or stop associated charges. Plan an explicitly approved inventory/export/delete process; production DynamoDB deletion protection also needs deliberate removal. No cleanup/deletion is automated in Phase 1.

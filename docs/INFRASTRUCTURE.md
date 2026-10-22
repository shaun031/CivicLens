# AWS infrastructure foundation

## Phase11 current inventory and deployment boundary

13 analytics/report paths added to the exact JWT+scope route catalog; backend independently checks
verified ADMIN and export CSRF.103 HTTP routes,360 resource definitions,13 outputs; four tables/nine
GSIs at13RCU/13WCU unchanged. Analytics reuses operations-table IAM and Phase10 workers, with explicit
reporting/scope/bound environment values. No analytics cluster, new table/GSI, public map scope or
evidence permission expansion. Offline assertions preserve exact counts/ARN allowlists and the
unconditional Phase14 deployment blocker. Source-only assets remain NON_DEPLOYABLE. No AWS calls,
bootstrap or deployment. [Projection readiness/limits](ANALYTICS_DATA_MODEL.md).

## Phase10 current offline inventory

Four DynamoDB tables/nine GSIs (13RCU/13WCU), one private evidence bucket, four source-only Lambdas,
four seven-day log groups,90 exact HTTP routes, one EventBridge bus/three rules (hourly one disabled),
four encrypted SQS queues/four scoped queue policies, two partial-failure mappings, one Standard state
machine and one SNS topic without subscribers. Total321 resource definitions/13 outputs.
No NAT/EC2/RDS/VPC/GPU/custom KMS/provisioned concurrency or provisioned polling.
Synthesis/template assertions are offline; unconditional deployment blocker still applies. Trusted
Cognito profile synchronization, Linux native artifacts, real OAuth URLs, retention/materialization,
queue/SFN failure semantics, observed compute/capacity and cost limits require Phase14 review.
See [event architecture](EVENT_DRIVEN_ARCHITECTURE.md). Historical inventory below is superseded.

Phase9 offline inventory:75 exact routes (29 new municipal work routes), all new endpoints JWT/API-scope
protected; existing public health/reviewed public discovery policy unchanged. Existing department GSI
Query permission added with exact ARN, no Scan/DeleteItem/wildcard index grant. Three tables/eight GSIs
remain11RCU/11WCU. MANUAL_APPROVAL/workload settings prepared; no queue/event/notification orchestration.
Source-only Lambda artifact and unconditional Phase14 deployment block remain. See
[assignment model/readiness](ASSIGNMENT_DATA_MODEL.md). No real AWS resource was created or queried.

## Current Phase 8 — offline definitions only

46 routes/157 resources/13 outputs,3 tables/8 GSIs/11RCU/11WCU. Existing ByStatusPriority serves
namespaced priority sidecars; no department keys are populated. Scoped incident ConditionCheckItem
and exact-index Query are prepared. DELETE override has JWT scope and audited application semantics,
not Dynamo DeleteItem. No scheduler/queue added. Source-only Lambda and unconditional Phase14 block
remain. `scripts\verify-infrastructure.ps1` isolates credentials for offline build/tests/synth/checks.

## Current Phase 7 — source-only, not deployable

Offline definitions now contain36 routes,127 resource definitions,13 outputs, three tables/eight GSIs
at aggregate11RCU/11WCU. ByCatalog is KEYS_ONLY; future priority indexes are not populated. Least-scoped
incident conditional transactions and audit queries are prepared. Lambda mode remains REVIEW_ONLY;
daemon false. No bootstrap/deploy/live AWS calls. Run `scripts\verify-infrastructure.ps1` for
credential-isolated build/test/synth/template/local-stage checks. [Cloud protocol](INCIDENT_DATA_MODEL.md).

## Current Phase 6 extension — source-only, not deployable

Current inventory is **88 resource definitions,13 outputs,23 routes**, three retained tables/seven
GSIs with10RCU/10WCU total. New InternalGeography and MatchingWork sparse KEYS_ONLY indexes separate
private duplicate selection/work from PublicGeography; exact-index Query grants only, no Scan/new
table. Seven new matching routes require JWT/API scope and active verified ADMIN backend checks.
The shared private evidence prefix remains scoped. No queue, EventBridge or permanent Lambda worker.

Atomic cloud outbox/pair/fingerprint adapters are mocked, not live-validated. Lambda remains Python3.13
x86_64/256MB/15s source-only with native dependencies intentionally absent. Linux wheels/artifact size,
memory/cold starts, consistency/backfill/caps and cost/free-tier eligibility require Phase14 review.
Windows dependencies cannot be copied into Lambda. The unconditional deployment blocker and local
zero-stack stage remain. Earlier inventory sections below are historical; no AWS resource was created.

Phase 1 implements CDK definitions, not deployed resources. All operations in this phase are local; no AWS credentials, AWS APIs, Docker, or cloud resources are required. A successful synthesis is not proof of successful deployment or cloud execution.

## Current Phase 5 extension

Current template: **67 resource definitions, 13 outputs, 16 explicit routes**. Health plus three approved-public issue GET routes are anonymous. Existing identity/private complaint routes plus citizen publication-request and ADMIN publication-review PATCH routes require Cognito JWT and API scope; backend RBAC enforces the narrower resource policy. No catch-all route exists.

One sparse KEYS_ONLY PublicGeography GSI is added on the existing Complaints table: publicGeoCell/publicGeoSortKey, 1 RCU/1 WCU. Three tables/five GSIs total 8 RCU/8 WCU; no new table or managed geographic/search service. The role gains Query only on the exact new index and PutItem-only on the existing AuditEvents table. Existing table/ByCitizen, private evidence-prefix and own-log grants remain. Strong current public-item reads follow eventual GSI keys; no Scan/DeleteItem/ListBucket is added.

Radius/candidate/quota/owner-work settings are injected explicitly. Public visibility comes from atomic revision-conditional projection/audit writes, not anonymous private-record access. Tests assert authorizer assignments and reject accidental anonymous administrator access. Source-only staging, unconditional deployment blocker, retention, CORS and offline no-lookup synthesis remain. Real packaging, IAM/GSI/latency/abuse/cost behavior awaits Phase 14. No deployment occurred.

## Historical Phase 4 extension (counts/permissions superseded above)

The stack now has **52 CloudFormation resource definitions**, 13 outputs and 11 explicit routes/integrations/invoke permissions: public health, five protected identity/profile/portal routes and five protected complaint routes (POST/list/summary/detail/image). All non-health routes retain the Cognito JWT authorizer and civiclens/access scope. CORS adds POST and Idempotency-Key without enabling cloud cookies. Backend citizenship/ownership checks remain separate from gateway authentication.

Lambda receives explicit COMPLAINT_PROVIDER=dynamodb and EVIDENCE_PROVIDER=s3 and table/bucket references. Required IAM grants are GetItem/BatchGetItem/PutItem/UpdateItem on the existing Complaints table, Query only on its ByCitizen index, and s3:GetObject/PutObject/DeleteObject only on `complaints/*`, plus its own log streams. Conditional transaction Put/Update operations use the corresponding item-operation IAM actions; no Scan, table deletion, bucket listing, public ACL, incident/audit access or administrator grants were added. No extra tables/indexes/buckets or paid services were introduced. Legacy opt-in future-worker helpers remain unbound unless deliberately requested by a handler.

The real local flow is backend multipart → sanitize → private filesystem → SQLite transaction; the prepared cloud flow substitutes S3/DynamoDB using the same contracts. Presigned browser upload/download and repair evidence remain future work. Source staging excludes data/evidence and Windows dependencies. Packaging now also needs a verified Linux Pillow/WebP image-processing build, boto3 and python-multipart alongside authentication dependencies. Native runtime, IAM, quotas, binary overhead, latency/memory, GSI consistency and real Cognito checks remain Phase 14. Deployment is still unconditionally blocked.

The following Phase 1/2 descriptions are historical baseline notes, not claims that current complaint routes/permissions are absent.

### Historical Phase 2 state

The Phase 1 data/storage/compute/logging foundation remains intact. `constructs/authentication.ts` now defines the Cognito pool/client/domain/API scope/groups. The shared Lambda runs APP_ENV=aws with AUTH_PROVIDER=cognito and receives issuer/client/domain references. It gains no DynamoDB/S3/Cognito administrator IAM permissions. The HTTP API now has public health and five explicit protected identity/profile/portal routes, a JWT authorizer, and access-token scope enforcement. CORS adds PATCH and Authorization, without enabling cookies in the cloud API.

At Phase 2 the stack had 37 resource definitions (including six route-scoped invoke permissions/integrations). The Phase 4 count above supersedes it. Local still has zero stacks. `safety.ts` verifies the current allowlist and sensitive routes. The unsatisfiable deployment rule remains, with its Phase 1 marker retained for compatibility. SOURCE_ONLY_NON_DEPLOYABLE still applies. See [COGNITO_SETUP.md](COGNITO_SETUP.md) for deferred OAuth/group checks.

## Organization

`bin/civiclens.ts` synthesizes `lib/app.ts`. `lib/config/environment.ts` validates stage/origin/account/region settings. A single `lib/stacks/civiclens-stack.ts` composes `Database`, `Storage`, `Monitoring`, `BackendLambda`, and `ApiGateway` constructs. `lib/permissions.ts` exposes opt-in grants for future handlers. `lib/safety.ts` and `scripts/check-templates.ts` verify the actual synthesized assembly offline.

Stack names are `CivicLens-demo` and `CivicLens-production`. Tables, bucket, Lambda, API, and IAM receive generated physical names to avoid collisions. The explicit log group is `/civiclens/<stage>/backend`. All taggable resources receive `Project=CivicLens` and `Stage=<stage>`. Account and region are optional CDK context; no lookups are used.

## Stage configuration

| Stage | AWS definitions | Browser origins | Additional safeguards |
|---|---|---|---|
| local | No stacks/resources | Native local Vite/FastAPI configuration | No AWS dependencies |
| demo (default) | One foundation stack | localhost and 127.0.0.1 on port 5173 | Debug off; deployment blocked |
| production | One foundation stack | None until explicitly configured | HTTPS/non-loopback origins; table deletion protection; debug off; deployment blocked |

From the infrastructure directory:

```powershell
npm.cmd install
npm.cmd run build
npm.cmd test
npx.cmd cdk synth
npm.cmd run check:templates

# Separate output prevents confusing one stage with another.
npx.cmd cdk synth -c stage=production -o cdk.out/production
npm.cmd run check:templates -- cdk.out/production
npm.cmd run check:local
```

`-c frontendOrigins='["https://civic.example.org"]'` selects an explicit origin array. PowerShell argument quoting varies by version; when needed, use the CDK context object in `cdk.json` for the array rather than embedding JSON on the command line. Optional `-c account=<12-digit-ID> -c region=ap-south-1` sets future coordinates without checking an account. Invalid names, malformed JSON, wildcard/path origins, and unsafe production origins fail before stack creation. `npm.cmd run synth` disables context lookups explicitly. `check:local` checks the empty assembly directly because `cdk synth -c stage=local` exits 1 with “This app contains no stacks,” which is the intended local architecture, not a failed cloud stack.

## Definitions and IAM

- DynamoDB: three Standard provisioned tables and four GSIs, each 1 RCU/1 WCU; 7 RCU/7 WCU total per stage. RETAIN prevents accidental deletion; ordinary item attributes are not CDK columns. Details: [DATABASE_DESIGN.md](DATABASE_DESIGN.md).
- Evidence S3: generated bucket name, all public access blocked, SSE-S3, bucket-owner-enforced ownership, HTTPS-only bucket policy, RETAIN, no auto-delete, no replication/versioning/customer-managed KMS. CORS permits only GET and PUT, `content-type`, and configured exact origins; production CORS is omitted until configured.
- Lambda: Python 3.13, x86_64, 256 MB, 15 seconds, `app.lambda_handler.handler`, existing shared FastAPI application, no VPC/layers/function URL/provisioned concurrency/tracing.
- HTTP API: one `GET /api/health` route with Lambda proxy payload 2.0 and stage-specific CORS. The default API stage has no catch-all route. API Gateway may answer CORS preflight automatically, but only GET reaches Lambda. Phase 2 will add a Cognito JWT authorizer and per-route authorization scopes before adding sensitive routes; health remains public.
- CloudWatch: directly created seven-day log group, RETAIN, without a retention-helper Lambda, custom resource, dashboard, alarm, or paid tracing feature. Later work must add actionable errors/timeouts/backlog/latency metrics and alarms after cost review. Avoid sensitive payloads/tokens in logs.
- Health execution role: Lambda trust plus only `logs:CreateLogStream` and `logs:PutLogEvents` on this log group's streams. It cannot read/write any table or evidence. The stream suffix `:*` is necessary for dynamically named streams. API Gateway receives a source-ARN-scoped Lambda invoke permission.

Future opt-in helpers grant GetItem/BatchGetItem/Query and PutItem/UpdateItem on the relevant complaint or incident table/index ARNs, PutItem on AuditEvents, or GetObject/PutObject only on the evidence `complaints/*` prefix. They do not grant Scan, DeleteItem, ListBucket, or delete objects, and are not attached to the health role. Future handlers should further scope prefixes to the authorized entity where feasible. Audit append behavior also requires conditional writes. The S3 policy's wildcard principal/actions appear only in an explicit Deny of insecure transport; they never allow anonymous access.

## Evidence upload plan

Logical object keys: `complaints/{complaintId}/{imageId}.jpg` and `repairs/{incidentId}/{imageId}.jpg`. Prefixes are not pre-created directories.

Future flow: authenticate citizen → authorize complaint and validate size/type/key → issue short-lived presigned PUT → browser uploads → backend validates object ownership/type/size and records the key → authorize access and issue short-lived retrieval URLs. CORS does not grant permissions. Content validation, upload limits, and abuse controls must be implemented before enabling upload APIs. Repair prefix permissions will be added only with authorized repair handlers. No upload API exists now.

## Outputs

`ApiEndpointUrl`, `LambdaFunctionName`, `ComplaintsTableName`, `IncidentsTableName`, `AuditEventsTableName`, `EvidenceBucketName`, and `DeploymentStage` use CDK resource references. These resolve to real identifiers only after Phase 14. No output contains credentials.

## Lambda asset: synthesis only

The CDK asset intentionally contains only the existing `backend/app` Python source. It excludes tests, `.venv`, `.env*`, build outputs, caches, and development files. Tests inspect the staged asset. Lambda description, construct metadata, and template metadata label it **SOURCE_ONLY_NON_DEPLOYABLE**. FastAPI, Mangum, Pydantic, and their transitive dependencies are absent, so this asset cannot run on Lambda. There is no alternate stub API.

`npm.cmd run check:deployment-readiness` deliberately exits 1 in Phase 1. An unconditional, unsatisfiable CloudFormation rule also blocks stack creation. No context flag enables deployment. These controls are not a substitute for Phase 14 review; deliberate edits could remove them.

## Reproducible Windows-to-Linux packaging plan

AWS documents using platform-specific Linux wheels for Python dependencies and including them beside the application at the archive root. See [AWS Python packaging guidance](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html). Python 3.13 is selected from the [supported runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html) to match the current local interpreter.

Before Phase 14, implement a dedicated packaging command with these steps:

1. Resolve runtime dependencies from `backend/pyproject.toml` into a pinned, hash-checked Linux/Python-3.13 runtime lock; exclude dev dependencies. Do not copy the Windows virtual environment or install editable `requirements.txt` into Lambda.
2. Install runtime wheels into a new `backend/build/lambda/package` staging directory using the target below. Fail on missing wheels; never substitute Windows binaries or silently compile an incompatible source distribution.

```powershell
# Planned command; runtime lock and production build pipeline are not implemented yet.
backend\.venv\Scripts\python.exe -m pip install `
  --platform manylinux2014_x86_64 --implementation cp --python-version 3.13 `
  --only-binary=:all: --require-hashes `
  --target backend\build\lambda\package `
  -r backend\requirements-lambda.lock
```

3. Copy only `backend/app` beside the installed packages. Archive the directory's contents (not its parent) so `app/lambda_handler.py`, `fastapi/`, `mangum/`, `pydantic/`, `pydantic_core/`, and transitive dependencies sit at ZIP root. Produce deterministic file ordering/timestamps and POSIX permissions using a packaging script.
4. Reject `.pyd`, `.dll`, secrets, test caches, unpinned dependencies, and incompatible wheel tags; verify Pydantic's native module targets Linux x86_64/CPython 3.13. Record source/lock hashes, runtime, architecture, artifact digest, and build verification in a manifest. Check ZIP size and dependency completeness.
5. Verify imports and an HTTP API v2 health event in a matching Linux environment before declaring the package deployable. Docker is unnecessary: a compatible Linux machine/WSL or an explicitly approved CI runner can perform this check. Linux native modules cannot be import-tested by the Windows interpreter. Prefer Linux wheels; if required dependencies have none, arrange an appropriate Linux builder in a later phase.
6. Update CDK to consume the verified artifact. The future readiness checker must verify the manifest, source/lock/artifact hashes, required modules, platform tests, and phase-specific manual approval. Only then may Phase 14 replace the deployment block and prepare bootstrap/assets in the selected account under separate approval.

The current default CDK synthesizer stages local assets and emits future S3 asset destinations but does not upload them. Its bootstrap-version rule is disabled for offline Phase 1 synthesis. The actual bootstrap strategy and asset-publishing permissions still require review in Phase 14.

## Remaining deployment blockers

Phase 2 adds native Argon2/CFFI and cryptography dependencies. Before freezing the runtime lock, verify Linux wheel tags against Python 3.13 and Lambda's Amazon Linux runtime; newer wheels may require an appropriate manylinux_2_28/2_34 target instead of the baseline manylinux2014 example above. Never use a Windows wheel or remove dependency checks to force a package build.

Verified Linux dependency package, final origins/account/region, Phase 2 authorization and later application work, Phase 13 hardening, current pricing/free-tier review, recovery/retention decisions, manual Phase 14 approval, asset publishing, and post-deployment runtime/IAM/CORS checks remain outstanding. None prevents completing Phase 1's local definition/testing scope.

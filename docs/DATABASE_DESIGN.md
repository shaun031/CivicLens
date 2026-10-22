# Database design — through Phase 13

Phase13 adds no domain schema migration/index/rebuild: version8 and additive Phase12
tables remain. Read-only aggregate integrity and all-kind evidence-reference diagnostics
never repair data. Explicit quiesced backups use SQLite backup plus referenced photo
hashes, refuse overwrite and restore only to new fixture paths in tests.
[Backup/migration/rollback](BACKUP_AND_ROLLBACK.md), [data evidence](INTEGRATION_TEST_REPORT.md).

## Current civic intelligence extensions

Repeatable additive schema8 extension `app/repositories/phase12_migration.py`; old CLI schema-version
compatibility preserved. New tables: repair_attempts (incident/officer/department FKs, unique incident
cycle, partial unique active pending attempt); repair_evidence (attempt/owner FKs, unique private key,
bounded JPEG metadata, explicit citizen-approval flag); repair_verification_requests (unique attempt
and citizen); repair_verifications (unique request, immutable effective vote); incident_recurrences
(previous/new incident and verified-attempt FKs, unique directional pair, score/time/state/version);
fairness_review_records (stable grid area, bounded filter context, state/notes/version); and append-only
civic_intelligence_audit (operation FK, actor FK, snapshot/reason/time). Indexed incident histories,
citizen requests, pending states, evidence attempts, recurrence endpoints and area reviews. Source
changes increment P11 analytics revision. P7 incident_operations/outbox/P8/P9/P10 structures are reused.
Known rollback is atomic; no original operational table is rebuilt and no original image is moved.

The cloud preparation port reuses the Operations table and sparse ByQueue pointers. Access patterns
include incident-attempts, citizen-requests, attempt-responses, incident-recurrences,
scope-confirmed-recurrences, pending-repairs and area-reviews. Conditional source guards, versioned
records, receipt/audit/outbox actions share one bounded transaction. No unrestricted Scan. This is a
server change-plan persistence port; full cloud domain binding/bootstrap remains explicitly gated.

## Current analytics extensions

Startup idempotently adds analytics_meta, analytics_receipts, analytics_snapshots and
analytics_export_audit plus source-revision invalidation triggers/date/geographic indexes. Schema8
numbering is retained for existing maintenance compatibility; analytics CLI additionally checks for
analytics_meta before read-only diagnostics. No source tables are rebuilt, rows reset or memberships
changed. Current analytics uses bounded direct source snapshots, not mutable increment-only totals.
Derived snapshots have deterministic view/filter identities, projection version, source revision and
calculation time; replacement is transactionally revision-fenced. [Full model](ANALYTICS_DATA_MODEL.md).
Cloud reuses the retained Phase10 operations table; no new table/GSI or capacity is added in Phase11.

## Phase10 additive schema8 and operations persistence

New local tables: event_outbox (due/status/token/attempts), event_queue (unique event/consumer,
leases/retries/dead/redrive), event_receipts (event+consumer+handler-version), workflow_executions,
workflow_steps (bounded six-stage history), notifications (recipient/date and unread indexes,
unique event/recipient/type key), sla_policies, sla_checks (indexed next_due), escalations
(unique incident/cycle/milestone), workflow_audit. Existing domain tables are not rebuilt.
SQL triggers atomically publish complaint/membership/band/hazard/assignment/progress/lifecycle changes.
Pending Phase6/7 jobs are adopted, Phase8/9 due sidecars preserved. Schema8 initialization is idempotent.

Cloud definitions total four tables/nine GSIs, aggregate13RCU/13WCU at1/1 per base/index.
Operations(pk,sk) + sparse ByQueue(queue,due), retained/default AWS encryption, no Scan.
Namespaced keys outbox#, message#, workflow#, receipt#, notification#, sla#, escalation#, control#.
Strong conditional revisions and bounded transactions preserve receipts+acks and breach+events.
Outbox Puts join complaint/incident/priority/work transactions when configured; original95-action,
3MB transaction safeguards are retained. Cloud HTTP business writes fail closed without the table ref.
Cloud inbox count cap100 and eventual-index sample limits are explicit, not production analytics.
See [access patterns/limitations](EVENT_DRIVEN_ARCHITECTURE.md). Earlier sections are historical.

Current SQLite schema7 adds departments, routing_rules, officer_memberships, incident_assignments,
work_history and work_meta. No original table is rebuilt, report ownership changed or evidence deleted.
Single-assignment primary keys, foreign keys and unique codes/memberships/rules enforce identities.
Existing incident_operations provide durable receipts. Membership/lifecycle/account triggers invalidate
allocations atomically; indexed officer/department queues reuse Phase8 priorities and versioned cursors.
Full current schema and DynamoDB access protocols: [assignment data model](ASSIGNMENT_DATA_MODEL.md).
The Phase8 sections below describe retained priority structures; Phase9 adds independent work sidecars.

Current additive schema6 attaches incident_priority, priority_history and priority_meta to existing
incident UUIDs, reusing incident_operations for manual receipts. No original table rebuild/reset.
Generation/control/calculation revisions guard stale writes; membership epochs invalidate controls;
interval state freezes/resumes aging. Indexed server rankings exclude dirty/expired results.
[Complete priority schema and conditional Dynamo protocol](PRIORITY_DATA_MODEL.md).
Schema5/4 sections below describe the preserved earlier migrations, not the current startup target.

Current schema5 adds incidents, operation receipts, membership events, incident audit, clustering
outbox/jobs and validating membership triggers. No existing account/report/photo table rebuild.
One authoritative complaints.incident_id, exact eligible support and guarded atomic corrections.
See [full incident schema/Dynamo protocol](INCIDENT_DATA_MODEL.md). Schema4 details below are historical.

## Current additive schema v4

Startup/trusted migration accepts v0–v4, applies earlier migrations, then one non-destructive Phase6
transaction. No existing complaint columns, IDs, owners, categories, statuses, incidentIds or photos
change. Sections below v4 describe preserved historical schemas, not the current version number.

- `complaints_internal_geography(latitude,longitude,category,status,complaint_id)`: private internal
  latitude-range/bounding-box index, independent of publication consent/public index.
- `duplicate_candidates`: UUIDv5 canonical-pair PK; sorted source/duplicate FKs and UNIQUE pair;
  checked combined/distance/JSON component values; classification; three-state review metadata;
  created/last-checked times; method/model/config/explanation JSON. Score/UUID and reverse-side indexes
  support review. Upserts preserve human decisions and createdAt. No automatic candidate deletions.
- `image_fingerprints`: image UUID/algorithm-version composite key, dHash and informative flag, FK
  to immutable sanitized images. Missing/corrupt reads are not cached as score zero.
- `matching_jobs`: source FK primary key, PENDING/RUNNING/RETRY/COMPLETE/INCOMPLETE, attempts,
  availability/lease token, config version, report JSON with model version, timestamp/error class.
  State/availability index; token-checked finish and candidate upserts commit atomically. The cheap
  AFTER INSERT trigger creates durable work with submission; migration backfills existing sources.

Review metadata retains the latest reviewer/time/state, not an append-only review-history log.
Publication auditing remains unchanged. Candidates do not mutate complaints, incidents or priorities.

### AWS namespaced mapping — source only

Still THREE tables, with TWO added sparse KEYS_ONLY GSIs at 1RCU/1WCU each:
InternalGeography(internalGeoCell,internalGeoSortKey) for actual PRIVATE complaint items and
MatchingWork(matchingPartition,matchingSortKey) for namespaced candidate/job rows. Total seven GSIs,
aggregate10RCU/10WCU. PublicGeography stays exclusively on reviewed public projections.

Primary keys: `duplicate#<canonical-pair-UUID>`, `matching-job#<source-UUID>`,
`fingerprint#dhash64-v1#<image-UUID>`. CANDIDATES/JOBS partitions share the work GSI; completed jobs
remove its attributes. Complaint create atomically writes the job/complaint/idempotency/summary.
At most90 candidate upserts and conditional lease completion commit in one transaction, with stable
ClientRequestToken and if_not_exists review state. Fingerprint lookup needs no GSI.

Internal geo fields are stripped when hydrating citizen DTOs. Neighbor-cell Query results undergo
strong primary rechecks but remain subject to eventual index propagation. Legacy cloud records
would need a reviewed bounded geo-attribute backfill before deployment; no cloud records/resources
were created here. Candidate catalog Query has a default2,000-row work cap and fails explicitly on
overflow, not a production global search claim. No DynamoDB Scan/new public data path was added.

## Current additive schema v3 (supersedes v2 notes below)

Startup/trusted CLI migrate versions 0/1/2 to 3 without resetting users, hashes, sessions, complaints, idempotency or images. Existing v2 tables are not rebuilt. AuthStore registers deterministic search functions on every connection. Migration and FTS backfill/triggers commit together; unsupported future versions fail clearly.

New owner/category/date/UUID and owner/status/date/UUID indexes support combined filtering/sorts. FTS5 complaint_search indexes normalized title/description/landmark/address and synchronizes inserts/updates/deletes; an owner-scoped SQL-function fallback supports SQLite builds without FTS5. Counts/pages share a read transaction and metadata hydrates in bounded batches. Current page maximum is 100; filter/sort context joins owner/provider in validated keyset cursors.

complaint_publications has a complaint FK, explicit citizen consent, independent publication status, independent unique public UUID, reviewed summary/rounded coordinates, published timestamp, geographic cell and reviewer metadata. Its published-only partial cell/UUID index supports geographic equality lookups without private-table enumeration. Existing complaints without a row are PRIVATE. publication_audit is append-only through application operations, retaining actor/action/from/to/time per event; its entity/time index supports trusted audit inspection. Publication change and audit commit atomically. No public audit/evidence access exists.

DynamoDB retains the same three tables and adds one sparse KEYS_ONLY PublicGeography GSI. Only sanitized public projection items carry publicGeoCell/publicGeoSortKey; withdrawal replaces them with nonindexed tombstones. Revision-conditional transactions update private metadata/projection and append to the existing AuditEvents table. Strong primary reads recheck public status after eventual GSI results. Owner search/aggregation has an explicit demo work cap; see COMPLAINT_SEARCH.md. No global Scan or new table is used.

Detailed search, cell geometry and privacy contracts are in COMPLAINT_SEARCH.md, GEOGRAPHIC_DISCOVERY.md and PUBLICATION_AND_PRIVACY.md. The following v2 mapping is historical and its maximum-page/search/summary limitations are superseded.

## Shared local SQLite schema v2

The Phase 2 `AuthStore` connection helper remains the only local connection/transaction mechanism. It enables `PRAGMA foreign_keys=ON` on every short-lived connection. Startup and `scripts/migrate-local.ps1` run the additive version-2 migration. Users, password hashes, sessions, recovery records and existing complaints are never dropped or reset. Unsupported future schema versions fail rather than guessing. Back up the database and private evidence together before manual maintenance.

| Table | Primary key / relationships | Purpose |
|---|---|---|
| users / sessions / password_resets / rate_limits | Existing Phase 2 keys retained | Authentication and shared persistent submission quota buckets |
| complaints | complaint_id UUID; citizen_id references users.id | Title, description, canonical category/severity, coordinates, optional landmark/address, status, nullable incident, created/updated UTC |
| complaint_images | image_id UUID; complaint_id FK with metadata cascade; storage_key unique | Private storage key, safe JPEG MIME, sanitized byte size, UTC creation time; never image binaries |
| complaint_requests | composite citizen_id + request_key; complaint_id FK unique | Durable user-scoped idempotency fingerprint and committed complaint mapping |

`complaints_citizen_created(citizen_id, created_at DESC, complaint_id DESC)` supports owner-only listing and deterministic timestamp ties. `complaint_images_owner(complaint_id)` supports bounded metadata retrieval. Primary-key constraints enforce uniqueness and idempotency. Category/severity/status/range/size CHECK constraints supplement Pydantic input validation. All SQL values are parameterized. Creation, image metadata, request mapping and quota increments commit atomically under BEGIN IMMEDIATE. Original media bytes are stored privately outside the database.

An owner/provider-bound validated continuation cursor carries createdAt/complaintId; queries use a keyset predicate, not a growing OFFSET or unrestricted table scan. Limit defaults to 20, maximum 50. A separate owner summary aggregates exact local counts and three recent items, not an incomplete page count. Refresh, logout/login, fresh connections and an actual Uvicorn process restart are covered by integration tests.

## DynamoDB mapping implemented behind the future AWS adapter

Complaint JSON follows Phase 1 camelCase keys and includes a small embedded `images` metadata array with private storage keys (not exposed in API responses). This keeps a complaint plus its accepted image references in one DynamoDB item. The adapter uses transactional conditional writes for the complaint, a durable `request#hash(owner:key)` idempotency item and a `summary#owner` counter. A separate `rate#hash(owner)` item uses atomic conditional window counters. Sentinel items intentionally omit GSI citizenId/createdAt attributes, so they do not pollute complaint indexes. No new tables or indexes were added.

ByCitizen remains KEYS_ONLY: Query obtains keys and BatchGetItem retrieves full owner-checked records, retrying unprocessed keys at most three times. DynamoDB cursors carry the real LastEvaluatedKey; no Scan is used. Direct reads/idempotency reconciliation use consistent reads. The GSI is eventually consistent and does not guarantee a global UUID tie order across equal createdAt keys; pages are sorted locally and the cloud limitation is documented in COMPLAINT_SYSTEM.md. The AWS adapter is mocked/stub-tested only, never used by the local app.

## Preserved Phase 1 infrastructure baseline

These AWS tables still exist only in locally synthesized templates. The prepared Phase 4 repository has not contacted DynamoDB. CloudFormation will generate physical names and inject references only after an approved deployment.

## Keys and indexes

Every table/index key has DynamoDB String (`S`) type. Ordinary attributes are schemaless and are not declared as columns in CDK.

| Table | Partition key | Sort key | Global secondary indexes |
|---|---|---|---|
| Complaints | `complaintId` | none | `ByCitizen`: `citizenId` + `createdAt`; `ByIncident`: `incidentId` + `createdAt` |
| Incidents | `incidentId` | none | `ByStatusPriority`: `status` + `prioritySortKey`; `ByDepartmentPriority`: `departmentId` + `prioritySortKey` |
| AuditEvents | `entityId` | `timestampEventId` | none |

All four GSIs use `KEYS_ONLY` projection. Index queries return identifiers/key attributes; fetch full items with GetItem/BatchGetItem. This minimizes index storage and write size at the expense of additional reads. GSIs are eventually consistent; callers must tolerate delayed membership/order changes and paginate results. Missing index keys make an item absent from that GSI (for example, complaints without an incident).

## Item conventions and access patterns

Complaints will carry citizen/incident IDs, category, description, coordinates, image keys, status, `createdAt`, and `updatedAt`. Read by complaint ID; query `ByCitizen` or `ByIncident` with an optional creation-time range. Store timestamps in fixed UTC ISO 8601 form with millisecond precision.

Incidents will carry category, description, coordinates, status, numeric `priorityScore`, severity, public impact, unique reporter count, department, timestamps, and optional resolution time. Status/department queries use their GSIs and reverse traversal for highest priority first. `prioritySortKey` is a planned application-maintained String derived from a normalized nonnegative integer priority, creation timestamp, and incident ID, for example `000075#2026-10-19T10:00:00.000Z#<incidentId>`. Before the scoring phase, define the score's bounds, precision, tie ordering, and encoding width. Scores must be normalized and padded consistently; converting arbitrary floating scores to strings would sort incorrectly. Future writers must update the score and sort key atomically. Phase 1 implements neither encoding nor scoring. Global priority ranking across all status/department partitions is not supported by these indexes.

Audit events use a namespaced entity ID (`complaint#<id>` or `incident#<id>`) and `timestampEventId` such as `2026-10-19T10:00:00.000Z#<uuid>`. A unique suffix prevents events at the same timestamp from overwriting each other. Query by entity and timestamp range for chronological history. Future writes must use a conditional PutItem (`attribute_not_exists` on the target key) for append semantics. IAM PutItem alone does not make existing records immutable. There is no TTL because audit retention requires an explicit future policy.

## Capacity and protection

| Allocation | Quantity | RCU per allocation | WCU per allocation | Total RCU/WCU |
|---|---:|---:|---:|---:|
| Base tables | 3 | 1 | 1 | 3 / 3 |
| Complaint GSIs | 2 | 1 | 1 | 2 / 2 |
| Incident GSIs | 2 | 1 | 1 | 2 / 2 |
| **Aggregate, one stage** | **7** | | | **7 / 7** |

Demo and production use DynamoDB Standard, provisioned billing, service-default encryption with AWS-owned keys, and RETAIN on deletion/replacement. `SSEEnabled: false` in CloudFormation means the default AWS-owned encryption key, not plaintext storage. No customer-managed KMS key is created. Production also enables deletion protection. Point-in-time recovery is explicitly off pending a cost/recovery review. Streams, auto scaling, replicas, global tables, backups, and DAX are absent.

The current free-allowance target is 25 provisioned RCU and 25 WCU, subject to account/region eligibility and other workloads. This is not an on-demand/pay-per-request allowance. Multiple deployed stages consume separate capacity. See [AWS_COST_ESTIMATE.md](AWS_COST_ESTIMATE.md).

At 1 WCU a burst, large item, transaction, or index update can throttle; a GSI with inadequate write capacity can also throttle base-table writes. Add retries with jitter and idempotency in later application work. Provisioned capacity has an idle cost outside applicable allowances. No autoscaling conceals that tradeoff.

## Future changes

Geographic and duplicate-detection work will evaluate bounded geohash-cell queries, neighboring cells, category compatibility, and hot-partition mitigation. There is no geographic index or full-text/vector search engine yet. Status partitions can become hot, and additional sharding/indexes need measured access patterns and a cost review. Schema validation, migrations, repositories, scoring, and audit-writing logic belong to later phases.

# Phase 7 — incident data model and atomicity

This guide retains Phase7 schema history. Phase8/schema6 adds the priority sidecar/history described
in [priority data model](PRIORITY_DATA_MODEL.md); Phase9/schema7 adds
[assignment records](ASSIGNMENT_DATA_MODEL.md), and current Phase10/schema8 adds
[durable events and workflow records](EVENT_DRIVEN_ARCHITECTURE.md), without replacing existing
source records.

Complaint is the immutable original report/evidence record; Incident groups reports about a physical
issue. SQLite complaints.incident_id is the only current membership authority. It is nullable while a
durable outbox job is pending. A non-null membership must reference an OPEN/RESOLVED incident, enforced
by insert/update triggers without rebuilding or discarding the original complaints table.

## Additive local schema5

| Record | Purpose / invariant |
|---|---|
| incidents | UUID PK, private canonical title/description/category/representative coordinates/report ID; independent OPEN/RESOLVED/MERGED/SUPERSEDED state; total/unique counts; first/last/created/updated/resolved times; alias target; optimistic version |
| incident_operations | Durable UUID receipt + actor/input fingerprint/kind/reason/result/time; replay survives restart |
| incident_membership_events | Event UUID, operation, complaint, previous/new incident, actor ID/type, reason/kind, candidate ID and score snapshot, time; UNIQUE(operation_id,complaint_id) |
| incident_audit | One immutable before/after/change snapshot per affected incident/operation, indexed chronological original-ID history |
| clustering_jobs | Source complaint PK, durable pending/running/retry/complete state, lease token, attempts, availability, rerun flag, latest report/error/time |

Existing accounts/sessions/reports/photos/publication/search/matching remain intact. Counts are
nonnegative; unique<=total; retired records have zero active membership count; MERGED requires a
non-self alias. Canonical membership corrections update neither original content/status/timestamps nor
photo objects. SQL foreign keys retain provenance and prevent accidental deletion of referenced reports.
Phase7 fabricated no priority/department fields or later-phase scores. New indexed access paths cover
incident status/catalog, authoritative membership by(incident_id,created_at,complaint_id), original/new
membership history, incident audit pages and job state/availability.

The transaction validates every source/target version and observed membership/status/current eligible
reporter flag, writes incident snapshots, changes complaint membership conditionally, recomputes exact
authoritative total/distinct eligible reporters, persists the result receipt and appends events/audits.
Any mismatch rolls everything back. A failed audit write cannot leave a half-merge. Strong operation
replay before/after validation handles same-ID concurrent requests; different operations on stale
versions conflict. No process mutex pretends to protect multiple workers.

## Prepared DynamoDB protocol — offline only

Uses the EXISTING Complaints, Incidents and AuditEvents tables. No fourth table, Scan or wildcard-index
query is introduced. One sparse KEYS_ONLY Incidents.ByCatalog(catalogPartition,catalogSortKey) adds1/1
provisioned capacity; three tables/eight GSIs aggregate11RCU/11WCU. Priority indexes remained sparse
in Phase7. Phase8 now prepares real calculated priority keys on existing indexes; department
assignment remains unimplemented. See the priority data-model guide for current key protocols.

- Complaints.incidentId remains authoritative. Incidents.memberIds is a bounded transaction-maintained
  manifest, never an independently editable source of truth. Every listed member is strongly reread
  from Complaints and membership/counts verified; version conditions protect the full snapshot.
- One TransactWriteItems contains conditional incident puts, conditional complaint membership updates
  or ConditionChecks for unchanged members, immutable operation receipt, source/target before/after
  AuditEvents with every membership change and actor type, and exact additive summary deltas.
- RECHECK also conditionally queues both work types. Bounded envelope<=95 actions, serialized<3MB and
  each action<380KB; reject413 rather than chunking a logical merge. UUID ClientRequestToken plus
  durable receipt handles ambiguous response/retry beyond provider token retention.
- Whole-transaction conflicts/outcome uncertainty strongly reread the receipt; otherwise409 instructs
  identical retry. No partial stage is published. GSI reads discover candidates/catalog keys only;
  they never establish uniqueness, current membership, counts or version correctness.
- Automatic operations also condition-check each bounded member pair's current dismissal state
  in the same transaction; concurrent human dismissal cannot be overwritten by a stale CPU result.
  Combined pair guards still respect the action envelope, falling back to manual review on413.
- Complaint creation atomically writes the report, request receipt, owner summary, matching job AND
  clustering job. New internal reporterEligible is guarded and stripped from public/owner DTOs.
- Existing MatchingWork sparse GSI serves clustering queue discovery; strong conditional leases and
  rerun flags handle enqueue/finish races. P6 source job reports retain canonical candidateIds so a
  bounded recheck can find pairs without a citywide candidate Scan. Older jobs without adjacency are
  explicitly incomplete and require a fresh matching pass.
- Catalog Query is bounded (maximum200 visited keys/page); strongly reloads filters and returns an
  exact visited-key continuation, possibly an empty filtered page. Global pending-review total is
  honestly null/unavailable in AWS, not a fabricated0. Other summary counts change transactionally.
- IAM scopes Get/Put/Update/ConditionCheck to actual tables, Query to exact ByCatalog/ByCitizen/
  geography/work indexes and AuditEvents, private evidence object prefixes. No Scan or index/*.

Readiness is NOT production certification. No live SDK transport, credential lookup, AWS call,
bootstrap, deploy or cloud migration was performed. The Lambda is still blocked source-only packaging;
native sklearn/numpy/Pillow dependencies need later compatible packaging validation. Daemon/schedulers
are disabled in AWS. Full cloud reconciliation is not enabled. A manifest externally edited outside
this protocol cannot safely discover omitted complaint associations: fail closed and require controlled
cloud migration/reconciliation design, not a silent rebuild from an eventual GSI. Cloud eligibility is a
submission snapshot; a future trusted account/moderation sync must update/reconcile it before production.

Local and botocore-Stubber tests verify transaction construction/guards/replay/envelopes only. No claim
of deployed Dynamo capacity, live Cognito/S3 behavior or production throughput is made.

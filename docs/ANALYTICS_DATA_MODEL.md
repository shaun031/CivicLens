# Analytics data model, consistency and cloud preparation

## Local source strategy

SQLite source repositories fetch one BEGIN read transaction with fixed, bounded queries: canonical
incidents joined1:1 to priority/assignment/SLA sidecars; eligible reports; departments/memberships;
minimal work/membership/priority/status history; policies and escalations. No per-incident DB loop.
Private notes/descriptions/evidence/contact fields are not needed by calculations. Python pure
calculators handle cohorts, statistics, time buckets, SLA target states and decimal spatial cells.
Phase8 configuration/results, Phase9 weights and Phase10 target_states remain authoritative.

Default complete-source bounds:5000 canonical incidents,10000 eligible reports,100 departments,
1000 memberships,50000 work/status/priority events per history,20000 initial-link/escalation records
and100 policies. Bounds are explicit, with413 on overflow: no sampled subset is called a full total.
The bounded whole municipal source permits correct global officer workload and all-date membership
counts alongside selected creation-date cohorts. This is intentionally a low-volume demonstration,
not unrestricted SQL analytics over an arbitrarily large municipality. Filtered geographic outputs
have additional viewport/cell bounds. Partitioned production source extraction needs Phase14 review.

Additive schema8 extensions: analytics_meta (source revision/event checkpoint/version), analytics_receipts
(event-ID uniqueness), analytics_snapshots (deterministic view/filter identity, source revision/version,
time, derived JSON), analytics_export_audit (minimal export accountability). Schema8 numbering remains
compatible with existing read-only Phase7–10 maintenance. Startup installs extensions idempotently;
no source table is rebuilt or user data reset. Indexes cover complaint date, incident geography,
work/status/escalation event dates. Existing canonical/assignment/member indexes remain in place.

Source-changing triggers increment analytics revision transactionally. Successful Phase10 consumers
observe an event exactly once for analytics telemetry; late timestamps do not move the watermark
backward. Analytics errors are isolated from core complaint processing. Local direct queries remain
correct even with stopped workers or missing observer telemetry: they never use increment-only counts.
Merges/splits, lifecycle, assignments, priority changes and account eligibility are covered by source
revision invalidation. No analytics event republishes its own input or creates a circular pipeline.

## Rebuild and diagnostics

`python -m app.scripts.rebuild_analytics --full` upserts only analytics-owned derived snapshots.
`--dry-run`/`--diagnose` use mode=ro, do not migrate/create a database and compare previous metrics
with current sources. Selected view/date ranges, bounded detail pages and optional hotspot bounds
are supported. Each view is a restart-safe transaction guarded by source revision: concurrent changes
produce409 instead of overwriting a newer checkpoint. Repeated rebuilds reuse deterministic identities.
Wall-clock calculation metadata/continuous age values are excluded from comparison; genuine target
crossings/current-source differences remain mismatches. No incident, membership, score or assignment
is repaired by analytics. Missing previous snapshots are reported, not silently claimed consistent.

## DynamoDB design — offline preparation only

Reuses the existing retained operations table, no new table/GSI or event bus. Known bounded views
use a manifest at pk=`analytics#scope`, sk=`manifest`; an immutable generation uses
pk=`analytics#scope#generation`, sk=`chunk#000000` etc. Bounded strong Query (not Scan) reads at most
20 pages of25 chunks, complete cohort at most5MiB, chunk at most240KB. Current manifest must be
version1, reconciled/non-dirty, complete and no older than1hour. Checksums and a final strong manifest
recheck prevent partial/torn/stale-generation totals. Outputs label projection time/eventual consistency.

Trusted controlled rebuild stages minimal source collections, then conditionally publishes the
generation against expected revision. Immutable chunk identity/digest supports safe retries. Event
receipt + manifest dirty/revision update is atomic; duplicate events do not increment twice; delayed
events only invalidate, never decrement/replay arithmetic totals. A failed/late rebuild cannot replace
a newer invalidation. Stale/absent/oversized/incomplete projections fail explicitly, never fake zero.
Projection schema is not a client ingestion endpoint or an unbounded source-data dump.

The adapter supports SDK-injected offline fixtures. A complete trusted cloud municipal source reader,
controlled bootstrap/reconciliation cadence, generation/receipt retention, actual IAM/latency/capacity
and cost validation are Phase14 prerequisites. Arbitrary unbounded DynamoDB multi-filter queries are
not promised. No live AWS calls or deployment occurred; source artifacts remain NON_DEPLOYABLE.

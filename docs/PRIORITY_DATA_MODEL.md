# Phase 8 — priority data model and conditional persistence

Master incidents and authoritative Phase7 complaint memberships are reused. There is no second
incident or duplicate-detection system. Original text/evidence/publication/ownership are unchanged.

## Additive SQLite schema6

| Structure | Purpose |
|---|---|
| incident_priority | One FK sidecar per existing incident UUID; controls JSON, control and calculation revisions, membership epoch, generation, dirty/config/source versions, bounded current result/fingerprint, indexed ranking scalars, unresolved interval state, next refresh and retry/lease metadata |
| priority_history | Immutable event UUID, original incident FK, optional existing operation receipt FK, kind/admin/reason/time, meaningful fingerprint and bounded before/after/control/input snapshot |
| priority_meta | Single queue revision; membership/input/control/result changes invalidate pages |
| Existing incident_operations | Reused durable manual-operation receipts; priority-specific UUID namespace and full input fingerprint prevent cross-kind/body reuse |

Migration never rebuilds original tables, resets accounts, changes memberships or invents verified
assessments. Existing incidents receive empty controls and pending calculations only. A small additive
draft-compatibility step adds missing calculation revisions and transactionally replaces older draft
invalidation hooks without dropping data/history. Repeated initialization/backfill is safe.

Control snapshots contain score/status/reason/admin/time/evidence references/assessed membership epoch;
hazard and override are independent objects. Supporting UUIDs must reference current member complaints
or their stored photos. Scores/notes never originate from client-provided reporter counts. Controls
remain retained when their epoch becomes invalid, with effective usage disabled until reviewed.

Indexes: priority_rank(hazard DESC,effective DESC,unresolvedSeconds DESC,incidentId), pending availability,
time-based due and original-incident chronological history. API limits50; maintenance batches500;
per-incident inputs30 members. Bounded SQL snapshots load only the relevant reports and private metadata.

## Atomicity, audit and dynamic inputs

P7 incident creation/change and membership-audit triggers mark current priority dirty in the same
transaction. Membership events advance epoch. User eligibility and report status/severity changes
also invalidate the affected IDs. Trusted status changes maintain frozen/open interval state; no new
lifecycle HTTP mutation is introduced. Dirty source changes clear old lease tokens. Failed work
retries after60s; claims lease60s. Lambda/test environments never run this local daemon.

Scoring takes one coherent SQLite read snapshot and a guarded BEGIN IMMEDIATE write. Commit checks
canonical incident version, input generation, control revision and calculation revision, plus optional
lease identity. The separate calculation revision prevents older computations overwriting a newer
result even when controls/membership did not change. Busy locks retry at most3 times with250ms busy
wait/backoff. Manual receipt, assessment changes, score, history and ranking metadata commit together;
injected audit failure rolls everything back. Same-ID concurrent/manual retries return the exact stored
receipt, including stable JSON types. Reusing an ID for changed input returns409.

Current result snapshots include enough versioned factor/config/input/control facts to reproduce
meaningful decisions. Raw citizen identities are not copied into priority history: member complaint
UUID/eligibility/reported severity plus exact total/distinct support are sufficient. Identical inputs
and meaningful factors do not append duplicate history merely for a refreshed timestamp. Changed
controls are always audited, even if their numeric score happens to remain equal. Old score histories
on merged/retired incidents remain queryable by their original ID.

## DynamoDB readiness — offline only

Existing Incidents stores `priority#<canonicalUuid>` sidecars, existing AuditEvents uses
`priority#<canonicalUuid>` entity partitions, and existing operation records retain manual receipts.
Canonical incident items remain unchanged: P7 conditional puts cannot overwrite or lose score controls.
This is attached state, not duplicate incident records. It is never returned as a master catalog item.

No new table/GSI is required. Existing KEYS_ONLY ByStatusPriority indexes `status=PRIORITY#OPEN` or
PRIORITY#RESOLVED and a deterministic lexical key. Existing ByCatalog uses separate PRIORITY#STATUS
partitions for hazard-first/oldest-first queries; those keys prefix the UTC start with hazard0/ordinary1.
Department priority index remains unused; no assignment is added.
Rank key: hazard0/ordinary1, inverse five-digit effective-score cents, inverse fixed-width unresolved
milliseconds, canonical UUID. These exactly preserve the documented hazard/score/age/UUID ordering.

The same P7 transaction conditionally changes members/incident versions/audits AND marks every
affected priority sidecar dirty, advances membership epoch as needed, removes stale GSI queue keys
and increments queue revision. Replayed P7 operations cannot duplicate these deltas. Priority commit
uses one TransactWriteItems: canonical incident ConditionCheck, guarded current-sidecar Put with input/
control/calculation revisions, authoritative current complaint membership/status/eligibility guards,
optional durable receipt, meaningful priority AuditEvent and queue revision. Reject oversized action,
item or transaction envelopes (95 actions,380KB per serialized action,3MB total); never partially chunk.

Strong reads establish correctness; GSI keys only discover bounded candidate keys. Queue queries visit
at most200 keys/page, strongly reload current score/canonical incident, exclude dirty/outdated/expired
rows and reject old index keys that would misorder a new result. There may be empty filtered pages
with continuation. Revision/short-lived cursors reject changes/expiry; eventual GSI propagation still
means this is not a global snapshot/completeness guarantee. Filters apply to the same stored records,
not a frontend-sort of citywide complaints. No unrestricted Scan or index/* permission is added.

Current cloud active incident total comes from the existing exact incident summary. Other global fresh
priority aggregates honestly return unavailable/null until controlled cloud materialization exists;
local totals are fully implemented. Cloud account eligibility remains the guarded submission snapshot
described in Phase7: later moderation sync and cloud lifecycle interval producers need validation.
Cloud maintenance/schedulers are explicitly disabled; local commands refuse cloud mode. Historic
cloud intervals not observed between calculations use current-state approximation, not invented history.

IAM adds only existing Incidents ConditionCheckItem and exact ByStatusPriority Query to the prior
table/audit permissions. Ten new API Gateway routes remain JWT/application-scope protected. DELETE
removes an application override through an audited state update, not a DynamoDB DeleteItem grant.
Inventory remains3 tables/8 GSIs/11RCU/11WCU,46 routes,157 resources,13 outputs. No queues, EventBridge,
SNS, Step Functions, GPU, paid service or cloud worker. The unconditional Phase14 deployment block
remains. Lambda packaging is source-only and native Phase6 dependencies are not deployment-certified.

Botocore Stubber/mock tests cover transactions, strong guards, receipts/conflicts/envelopes and GSI
ranking/continuation. No actual DynamoDB/Cognito/S3 call, credentials lookup, deploy or bootstrap.

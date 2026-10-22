# Demonstration SLA monitoring

These are hypothetical operational targets for a college demonstration, not legal municipal deadlines.

| Band | Response/assignment hours | Resolution-monitoring hours |
| --- | ---: | ---: |
| CRITICAL | 24 | 72 |
| HIGH | 72 | 168 |
| MEDIUM | 168 | 336 |
| LOW | 336 | 672 |

ADMIN policies can specialize by category, optional department and verified urgent-hazard requirement.
Most-specific policy wins; stable policy ID breaks equal specificity deterministically. Priority band
always comes from a fresh canonical Phase8 result. Stale priority defers the SLA check rather than
assuming low risk. Policies validate finite positive durations and resolution>=response, use expected
versions, reason and confirmation. Current UI edits existing policies; PUT API can create specialized
policies using a bounded policy ID. No new repair verification lifecycle is introduced.

Initial baseline is first reported UTC time. Reopening creates a new response/resolution cycle at its
actual reopen timestamp, not the original closed interval. MERGED/SUPERSEDED/RESOLVED are excluded
from new active alerts; aliases are never treated as independent active incidents.
A confirmed department assignment at/before the response deadline satisfies response. NEEDS_REVIEW
does not. A late response can still be a historical breach. OPEN unresolved incidents monitor the
resolution target; existing resolved state is the available milestone, not newly invented verification.

At or beyond a deadline, the checker transactionally stores a stable breach receipt, outbox
IncidentOverdue and safe audit. Unique incident+cycle+milestone suppresses repeat alerts even if
a policy changes its deadline. Existing receipts remain historical; changed policies apply to future
checks without deleting them or restarting the unresolved baseline. New cycles can alert again.
Acknowledgement records actor/time; it is not resolution and does not alter severity or Phase8 controls.

Local due work uses sla_checks.next_due index, bounded batches and durable retry diagnostics.
run_scheduled_checks refreshes due priorities then SLA. --dry-run opens SQLite read-only and never
initializes/migrates the DB. No Windows scheduled task is installed. AWS uses a single disabled hourly
EventBridge rule and sparse operations-table sla-due queries, not one schedule per incident or scans.
Low provisioned capacity/batch size can create lag; production cadence, load and targets must be
jointly validated. Cloud policy migration/directory/retention and live timing remain Phase14 prerequisites.

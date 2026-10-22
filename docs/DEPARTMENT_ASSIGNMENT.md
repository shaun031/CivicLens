# Phase9 — municipal department routing

Phase13 current: routing/allocation are integrated with Phase10 durable workflows and
Phase12 repair verification locally; source-only cloud gaps remain explicit. Category/
fallback/eligibility and workload baselines/races are reverified, not optimized field
productivity claims. [Research](RESEARCH_EVALUATION_REPORT.md), [integration](INTEGRATION_TEST_REPORT.md).

Implemented locally; configuration describes a fictional demonstration, not an actual municipality.
No AWS deployment. Phase10 orchestration is now integrated locally. Routing uses canonical Phase7 incidents, never
individual duplicate complaints. Category determines responsibility; Phase8 determines urgency.

## Editable defaults

| Existing category | Demonstration department code |
|---|---|
| POTHOLE, DAMAGED_ROAD | ROAD_MAINTENANCE |
| BROKEN_STREETLIGHT | ELECTRICAL_MAINTENANCE |
| GARBAGE | SANITATION |
| DRAINAGE | DRAINAGE_MAINTENANCE |
| PUBLIC_PROPERTY_DAMAGE | PUBLIC_WORKS |
| OTHER | GENERAL_REVIEW, with NEEDS_REVIEW |

An ADMIN can explicitly seed defaults from `/admin/departments` or the trusted local seed CLI.
Seeding creates random UUIDs, resolves codes rather than hardcoding primary keys, and never overwrites
administrator-edited records. Repeating the seed does not create duplicate codes/rules or officers.
Default configuration is not silently inserted into existing user databases during migration.

Rules are ADMIN-configurable category/department/precedence/activation records with optimistic
versions. Lowest numeric precedence wins. Equal-precedence distinct departments require review;
duplicate rules for one category/department are prevented. Routing returns a deterministic hash of
current departments/rules, selected department, coverage mode and explanation. An inactive target,
unknown category, ambiguity or uncovered location enters General Review only if that department is
itself active and covered; otherwise no department is assigned. No fallback bypasses jurisdiction.

## Geography

Each department and membership supports up to10 named inclusive WGS84 rectangles:

```json
[{"name":"Demonstration ward","south":12.90,"north":13.10,"west":77.50,"east":77.70}]
```

Bounds must be finite, within latitude/longitude limits, strictly ordered, and cannot cross the
antimeridian. Multiple rectangles mean union. `[]` means category-only demonstration mode, explicitly
not geographically verified. Coordinates are not assumed survey-accurate. Officer rectangles further
restrict, never expand, department coverage. No GIS server, paid map or external geocoding is used.

## Assignment and recovery

An existing bounded local worker handles one pending routing unit after matching/clustering/priority
work. The migration queues historical canonical incidents without running an unbounded backfill.
Default MANUAL_APPROVAL permits clear department routing but never automatic officer allocation.
Manual ADMIN assignment/reassignment can choose a different covered active department with a reason;
this never changes category, original evidence, ownership, publication or priority weights.

Successful routing persists the real decision and audit atomically. Repeated worker deliveries see
route_pending=0; racing workers use incident/assignment versions so one wins. Failure retries after60s;
original incidents/reports survive. Explicit confirmed ADMIN routing remains available without a daemon.

Membership corrections invalidate active allocations in the same SQLite transaction as Phase7's
membership audit. Conflicting previous allocations are cleared, kept in immutable history and marked
REVIEW_LOCK/NEEDS_REVIEW; automatic routing cannot silently restore an officer. Splits start without
inherited officer work. Retired/resolved records leave active queues. Rule edits apply to future or
explicitly rerouted work; they do not silently redistribute accepted work.

Deactivation or boundary edits are rejected while the department owns active work. Reassign/return
that work to unassigned/review first. Historical departments are not deleted. Membership removal and
constraint changes likewise require reassignment first. See [officer allocation](OFFICER_ALLOCATION.md),
[data/transaction design](ASSIGNMENT_DATA_MODEL.md), and [workflow states](WORKFLOW_STATES.md).

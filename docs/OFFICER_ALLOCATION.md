# Phase9 — officer allocation and experimental workload

Application roles remain CITIZEN/OFFICER/ADMIN. Department membership is not a fourth role. Public
registration still creates only CITIZEN. A trusted operator provisions local OFFICER accounts using
`scripts/create-local-user.ps1`; an active verified ADMIN then grants department membership in the UI.
Neither an officer nor a citizen can grant their own role, memberships, capacity or availability.

Eligibility for new work requires an active verified OFFICER account, active target department and
membership, AVAILABLE status, compatible department/officer rectangles and sufficient configured
capacity. BUSY, UNAVAILABLE and ON_LEAVE are not new-work candidates, even with zero workload.
AVAILABLE/BUSY may progress existing assigned work if all other eligibility checks remain valid.
Active-work constraints cannot be edited/removed silently: reassign affected work first. Account
deactivation/role/verification changes revoke active officer allocations through transactional triggers.

## Workload and recommendations

Default configurable `WORKLOAD_WEIGHTS=[1,2,3,4]` map LOW/MEDIUM/HIGH/CRITICAL to experimental units.
Weights must be four finite positive nondecreasing values<=100. These are not labor-hour estimates.
Global officer workload sums each current canonical OPEN assigned incident once across all their
memberships. RESOLVED/MERGED/SUPERSEDED work contributes nothing. Pending, expired or stale priorities
are conservatively charged the CRITICAL weight, not zero. No second urgency formula is introduced.

Capacity is null/unknown or finite positive<=10000. Utilization=weighted workload/configured capacity.
Recommendation candidates with known capacity rank by utilization, then stable authenticated user ID.
Unknown-capacity candidates appear after known-capacity candidates, ordered by weighted workload/ID,
explicitly manual-only. New work must fit capacity after assignment. ADMIN can explicitly override
experimental capacity with recorded justification; availability, account eligibility and geography
cannot be overridden. The currently considered incident is excluded from candidate existing workload
to avoid charging it twice; the recommendation includes its projected total separately.

MANUAL_APPROVAL is default. A recommendation does not change assignment or create success in React.
CONSERVATIVE_AUTO_ASSIGN additionally requires explicit environment configuration and request/worker
mode, exactly one eligible officer, known reliable capacity, fresh incoming priority, no pending
candidate workloads, no review lock and no verified urgent hazard. No arbitrary automatic hazard
allocation. Every assignment re-reads current eligibility/workload inside BEGIN IMMEDIATE; recommendations
do not reserve a slot. Separate backend workers cannot overbook using stale recommendations.

Priority changes refresh queue order and derived workload immediately without changing assignment or
creating assignment-history noise. No cached counter can double-count a reassignment. Department
totals include unassigned work; each officer card explicitly shows their global workload. Advisory
rebalancing checks a bounded50 unstarted-work sample, known capacities, jurisdiction and availability.
It proposes moves only when normalized pairwise imbalance improves by>=.1 from an initial gap>=.5;
max20 suggestions. These are independent alternatives, not a batch plan. Nothing transfers automatically;
in-progress work is excluded and each proposal needs fresh ADMIN confirmation, preventing oscillation.

## Actual measured local benchmark

`python -m app.scripts.benchmark_allocation` uses300 real SQLite incidents, six departments and12 trusted
synthetic officers, including unavailable staff. Temporary stores are discarded without touching user
accounts/evidence. Captured medians (ms): routing20.018, recommendation12.940, assignment23.241,
officer queue11.364, department queue13.375, department workload23.072, reassignment27.533.
Measurements are serial Windows timings, not production-scale certification, work-duration prediction
or a Lambda SLA. Subsequent runs print their actual timings. The captured verification-script run
includes workload rebalancing analysis; different verification load changes observed timings.

## Privacy

Officer queue identity comes only from the authenticated principal, never a frontend-selected officerId.
Officers receive operational canonical fields, current department/assignment/progress and relevant
photo IDs. Every photo request rechecks assignment, membership and authoritative complaint ownership
within the incident. Other citizens' identities, private unrelated reports, administrator routing
justifications and other officers' progress notes are not included in officer history. No internal
note is published, and the original citizen-safe association endpoint remains unchanged.

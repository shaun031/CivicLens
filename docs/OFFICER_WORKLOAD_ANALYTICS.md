# Officer workload analytics

Only ADMIN can use `/admin/analytics/officers`. Eligibility reuses active verified OFFICER accounts,
active memberships and active departments. Current availability/capacity are configuration snapshots,
not inferred working hours or historical staffing. No privilege-management rules are added.

Phase9 workload weights remain authoritative. Fresh LOW/MEDIUM/HIGH/CRITICAL active assignments use
configured weights; missing/stale priority charges the maximum weight. Resolved/retired incidents
do not contribute. Global load includes all active assignments to the officer, not just the selected
creation-date cohort; selected work, selected overdue/high-priority counts, global stale-input count
and global assignment count are exposed separately. This prevents a narrow date filter falsely
making an overloaded officer appear free. Membership capacity applies as in Phase9.

Utilization = global weighted workload / configured positive capacity. Unknown capacity is null,
shown as Not configured, not0 or an invented utilization. One officer can have several department
memberships, so global workload repeats per membership: do not add membership rows to get citywide
load. Availability and workload-range filters are supported. Recorded assignment events and100%
work milestones are actual observations, not validated productivity or citizen repair verification.

The UI includes workload distribution, availability/capacity fields, department filtering and links
to existing trusted membership configuration. These are workload-distribution measures, not employee
disciplinary rankings. Work complexity, staffing and resource availability must be considered.

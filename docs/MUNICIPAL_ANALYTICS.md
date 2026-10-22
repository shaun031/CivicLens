# Municipal Command Center — Phase11

Phase13: real lifecycle/CSV/RBAC and snapshot-vs-merge consistency are exercised;
bounded local benchmarks retain index/snapshot/cache controls. Cloud trusted projection
bootstrap is not complete; never substitute fake zero aggregates. [Validation](INTEGRATION_TEST_REPORT.md),
[AWS limits](AWS_DEPLOYMENT_READINESS.md).

ADMIN `/admin/command-center` uses real persisted data: separate complaint/canonical-incident cards,
current priority distribution, category charts, complaint/incident creation trends, department active
work, top10 geographic cells, urgent incident links and recent recorded operations. Existing incident,
priority, assignment, publication, duplicate and workflow controls remain authoritative and unchanged.
Detailed analytics, officer workloads, SLA/backlog/timings, hotspots and reports have protected routes.
Tables, chart data alternatives, manual refresh, loading/empty/error states and URL filters are provided.
No operational sample fallback is used. Citizens retain only their personal and approved public views.

## Scope and time

`ANALYTICS_SCOPE` labels the single configured municipality. Optional `ANALYTICS_SERVICE_AREAS` is a
JSON map of named south/west/north/east rectangles; their union restricts incident/report metrics,
and selecting an area further restricts it. With no configured boundaries, the application's entire
single-municipality source is in scope; an example map viewport is not a municipal boundary.
Inventory counts represent current configuration, optionally department-filtered, not historical
staffing inferred from incident dates. Officer global workload follows Phase9 across all active work.

Creation-date filters default to the last30 reporting days. Start and end are inclusive municipality
calendar days, converted independently to an inclusive UTC instant and exclusive next-day UTC instant.
`ANALYTICS_TIMEZONE` defaults UTC and accepts installed IANA zones; tzdata supports native Windows.
Dates1970–2100, at most366 reporting days, are supported. Weekly buckets start Monday; monthly buckets
start on day1. Counts zero-fill reporting intervals. No browser-midnight assumption is made.

Complaint cohorts use complaint creation; incident cohorts use canonical incident creation. Current
membership counts per selected incident include its eligible reports from all dates. Consequently,
complaint totals and sums of selected-incident memberships need not match across a creation-date window.
Department/priority/lifecycle/assignment/hazard report filters use CURRENT linked incident attributes;
unlinked reports remain in unfiltered complaint totals and are excluded by incident-specific filters.

## Metric dictionary

| Metric | Formula / basis | Missing, lifecycle and history rules |
| --- | --- | --- |
| Total complaints | Count eligible persisted reports in complaint cohort | Active verified CITIZEN account; non-REJECTED report; includes resolved reports |
| Total incidents | Count distinct OPEN/RESOLVED canonical IDs in incident cohort | MERGED/SUPERSEDED aliases excluded; never count one report as a physical defect |
| Active incidents/backlog | Count canonical OPEN cohort IDs | Current snapshot; total is unique even though subgroups overlap |
| Recorded resolved state | Count RESOLVED cohort IDs | Distinct from valid recorded resolution transitions and verified repair |
| Resolved incidents | RESOLVED plus matching valid OPEN→RESOLVED audit timestamp in current cycle | Missing audit or invalid timestamp is not invented; no Phase12 verification claim |
| Reports per incident | Eligible current members / selected canonical incident | Mean denominator is selected incidents; zero-member canonical records remain visible |
| Unique reporters | Distinct eligible citizen IDs | Complaint cohort and per-incident/current membership measures labelled separately; IDs not exposed |
| Critical/high | Fresh authoritative Phase8 effective band among OPEN cohort | No new scoring formula; stale/missing results are UNAVAILABLE, not low/zero |
| Hazard | Fresh Phase8 verified hazard flag | Preserves hazard-first urgent ordering; not inferred from citizen reported severity |
| Mean/median score | Fresh calculated scores among active cohort | Sample size explicit; effective override score remains distinct; empty means null |
| Overdue | Distinct OPEN cohort IDs currently breaching an applicable Phase10 target | Re-evaluates pure Phase10 deadline logic without creating alerts; missing fresh inputs unavailable |
| Escalation count | Persisted alerts for selected incident IDs created in event window | Multiple milestone/cycle alerts are records, not extra overdue incidents |
| Workload | Phase9 LOW/MEDIUM/HIGH/CRITICAL configured weighted units for OPEN assignments | Stale/missing priority conservatively charges maximum; not a productivity ranking |
| Utilization | Global officer weighted units / configured membership capacity | Unknown capacity → null/Not configured; multiple memberships are not additive |
| Response timing | Current-cycle baseline to earliest valid recorded assignment | No valid milestone → null; summary includes n, mean, median, min, max hours |
| Work-start timing | Current-cycle baseline to first WORK_START event | Separate from assignment and resolution; no invented working hours |
| Recorded resolution timing | Current-cycle baseline to matching valid recorded resolution transition | Progress100% never implies resolution; no verified-repair data is fabricated |
| Response compliance | MET / (MET+MISSED) measurable incident outcomes | Pending/unavailable counts explicit; denominator is never all complaint submissions |
| Resolution compliance | Same target-outcome basis where valid completion data/current policy exists | Missing source/priority/policy remains unavailable; current policy, not retroactive legal compliance |

## Historical limitations

Current metrics use current canonical membership and assignments after merges/splits. They do not
reconstruct past citywide backlog or past rankings. Actual priority events/status transitions and
recorded work events are exposed as events, with bounded histories, not interpolated snapshots.
First durable linkage history distinguishes recorded initial singleton creation from recorded
initial existing-incident linking; unknown legacy cases remain unknown. This is not membership at
the exact form-submission instant or a retrospectively validated physical-defect count.

Each response includes calculation time, UTC window, reporting zone, source revision, read mode and
stale-priority count. Local reads are one consistent direct snapshot. Cloud projection responses
identify their generation time and eventual consistency; absent/dirty/expired/incomplete data fails
explicitly rather than producing fake zero KPIs. See [data model](ANALYTICS_DATA_MODEL.md).

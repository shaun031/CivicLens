# Private geographic service comparisons

Phase13 adds measured volume/missingness sensitivity and consistent merge/snapshot
testing, preserving descriptive n/missing/insufficiency labels and no causal claim.
[Evaluation](RESEARCH_EVALUATION_REPORT.md), [UI/API evidence](INTEGRATION_TEST_REPORT.md).

ADMIN-only `/admin/fairness` is descriptive decision support. Reporting volume is not infrastructure
need, and a disparity flag is not a legal finding of discrimination, officer performance, negligence
or contractor quality. No protected characteristic is inferred. No priority weights, assignment
penalties or public-data permissions change.

P11's date-window, category, fresh-priority, department, service-area and bounded viewport filters are
reused. Reporting days use configured IANA timezone; windows contain1–366 days. Canonical OPEN/RESOLVED
incidents are counted once in their creation-date cohort with CURRENT authoritative membership,
assignment and status. Decimal-floor non-overlapping grid cells use stable `grid:size:lat:lon` IDs.
Different grid sizes must not be compared as identical administrative units. Configured P11 service
areas restrict scope; they are not falsely represented as verified municipal wards.

## Definitions

- Work-start response: hours from the CURRENT SLA-cycle opening to a recorded WORK_START event;
  missing starts are unavailable, not zero. Show observation count and missing count.
- Overdue rate: overdue active canonical incidents / active incidents with known resolution SLA.
  P10's current policy and freshness rules apply; unknown SLA is excluded and counted as missing.
- Active backlog rate: current OPEN incidents / all canonical incidents in the creation-date cohort.
- Unresolved duration: median current-cycle active age in days, not a claim of lifetime defect age.
- Verified resolution rate: currently RESOLVED incidents with matching current ADMIN-verified repair
  cycle and resolution timestamp / all canonical incidents in the creation-date cohort. Officer claims
  and legacy unverified resolved states do not enter the numerator.
- Recurrence concentration: DISTINCT new canonical incidents with valid confirmed relationships,
  separately from potential candidates. It is not a report count or physical-asset count.
- Coverage: cohort incident count, work-start/SLA sample counts, missing data, priority and department
  distributions, reporting window and calculation time.

No credible population/road-length/inventory reference dataset exists here: all metrics are explicitly
UNADJUSTED. Fewer reports can reflect access barriers or missing observations, not better service.

## Review signals and uncertainty

Default minimum10 observations per compared metric, response median ratio2, overdue-rate gap0.20.
Thresholds are bounded configuration, not validated universal standards. A cell is compared with OTHER
selected cells, excluding its own contribution. Insufficient area/comparison observations produce
INSUFFICIENT_DATA; suitable data without a threshold crossing produces NO_FLAG; a crossing produces
POTENTIAL_SERVICE_DISPARITY. Reviewers see priority/department mix and missing data; comparisons are
not causally adjusted and must be investigated. No confident ranking is produced for one observation.
Unoccupied areas have no observations; the UI states this rather than displaying a fake zero score.

The private map uses gray insufficient-data cells, optional external OSM basemap (off by default),
metric selection and sample-size tooltips. At most500 map cells are rendered; a keyboard-accessible
table contains the bounded response (max2000 occupied cells). Side-by-side comparisons show counts,
rates, distributions, missingness, period and authorized incident drill-down. Creating/updating
UNDER_ADMIN_REVIEW / REVIEWED notes is versioned, audited and emits the existing durable event path;
read-only analytics GETs never manufacture workflow mutations.

P11 snapshots and P12 data join with a source-revision fence. Repeated identical queries reuse an
in-memory derived result for at most30 seconds; ANY source revision invalidates it. No operational
state is cached as authoritative. Bounds:5000 selected incidents,10000 repair/recurrence records,
2000 occupied cells. Oversized scopes fail explicitly; controlled partitioned projections are needed
for larger deployments. CSV uses P11 allowlists, audit/rate limits and formula-injection protection.

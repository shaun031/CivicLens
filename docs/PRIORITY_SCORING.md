# Phase 8 — dynamic incident priority scoring

Phase13 preserves40/25/20/15 weights, hazard/override/aging distinctions and adds
split-vs-recalculation race validation. Synthetic ranking/sensitivity is not expert
operational validation. [Measured baselines](RESEARCH_EVALUATION_REPORT.md).

Operational locally in D:\CivicLens. A transparent administrative rubric, **not** accident probability,
injury prediction, validated public-safety guidance, emergency dispatch or department allocation.
No paid model, traffic API, population inference or AWS execution. Phase9 now adds separate
[department/officer work allocation](DEPARTMENT_ASSIGNMENT.md), without changing this scoring rubric.

## Formula and verification

`P = 10 × (0.40S + 0.25I + 0.20R + 0.15A)`; factors0–10, calculated score0–100.

| Factor | Actual input and policy |
|---|---|
| Severity S | ADMIN assessment of the defect; unknown defaults3, clearly provisional |
| Public impact I | ADMIN assessment with reason/evidence; unknown defaults3, not zero exposure |
| Independent support R | `min(10,10 × ln(1+U)/ln(1+30))`, U distinct eligible CITIZEN accounts |
| Aging A | `min(10,10 × unresolvedDays/30)` using UTC and recorded unresolved intervals |

Defaults retain the supplied40/25/20/15 weights; the synthetic benchmark is not sufficient to select
globally optimal weights. PRIORITY_WEIGHTS accepts four finite nonnegative weights summing to1.
PRIORITY_REPORTER_SATURATION defaults30; PRIORITY_AGING_DAYS30; PRIORITY_REFRESH_SECONDS3600.
Configuration is validated at startup, normalized numerically and fingerprinted into priority-v1-HASH.
The engine accepts typed records/clock/config only, with no HTTP, database, SDK or filesystem coupling.

Each result contains raw and effective scores/bands, four raw/normalized values, weights/contributions,
assessment status, UTC calculation time, algorithm/config version, missing/review flags, hazard and
override status, and deterministic explanations. Decimal half-up rounds scores/contributions to2
decimal places; normalized factors to4. The exact weighted sum is rounded independently, so displayed
rounded contributions can differ from their sum by.01. Scores are never interpreted as probabilities.

## Severity and impact controls

UNASSESSED stores a null/unknown score; PROVISIONAL administrative scores are capped6; VERIFIED accepts
0–10 only with ADMIN identity, reason10–1000 characters, confirmation and current report/photo evidence
references. A verified zero is different from missing data. Scores9–10 represent the administrative
rubric's strongest verified concerns, not a scientific risk measurement. Citizens cannot set these
fields. Original citizen LOW/MEDIUM/HIGH remains intact, never converted to authoritative severity10.
Eligible HIGH reports and limited English danger-term matches can request review only. Once relevant
assessment/hazard verification is complete, these signals no longer perpetually mark it unreviewed.

Impact represents inspected disruption/exposure/essential access/accessibility, not invented traffic
counts or population. Being named near a school/hospital does not automatically increase impact.
Reasons and evidence remain private, with prior assessments retained in immutable priority history.

## Support, manipulation and uncertainty

The service uses authoritative Phase7 memberships and the same active, verified CITIZEN / non-REJECTED
eligibility policy, recomputing distinct eligible account IDs in one SQLite snapshot. Cached Phase7
support counts may await reconciliation after account changes; the priority calculation does not trust
a stale count or frontend-supplied number. Six reports from one account still contribute U=1.
Rejected/inactive/unverified reports do not contribute severity/danger review signals or support.

Repeated-account patterns are labelled for review, not an accusation of abuse. Distinct accounts do
not prove distinct people; no new intrusive identity collection was added. Low reporting can reflect
unequal adoption, not low importance. Default popularity+age cannot automatically create an urgent
hazard: even U>=30 and age>=30 days with default provisional S=I=3 produces54.5/MEDIUM. An explicit
verified hazard always sorts ahead of ordinary high/popular/overridden records.

AssessmentStatus is separate from priorityBand: PROVISIONAL, VERIFIED (both administrative factors
verified), or NEEDS_REVIEW. Unknown data is not evidence of no hazard. Source quality and approximate
historical aging remain explained even if both administrative assessments are verified.

## Aging and lifecycle policy

Phase7 master statuses are OPEN, RESOLVED, MERGED, SUPERSEDED. Only OPEN accumulates new unresolved
time. Initial baseline starts at firstReportedAt, the earliest retained original member timestamp.
New reports do not reset it to the latest submission. Continuous-open merges use the surviving
incident's recomputed earliest member start; new split groups start from their own original members.

SQLite records frozen unresolved seconds and an open-since timestamp. Trusted lifecycle updates freeze
elapsed time at resolvedAt/updatedAt; reopening starts a new open interval at updatedAt and retains
previous frozen seconds. The closed interval is not added. No new resolution/reopening workflow API
or complaint-status propagation was introduced in Phase8. Future trusted lifecycle producers must
update canonical status/version/timestamps correctly; tests exercise the database hooks directly.

Historical intervals before these hooks cannot be reconstructed: the baseline is explicitly
APPROXIMATE_BASELINE, never fabricated transitions. A reopened/previously resolved cluster with complex
merge history retains observed frozen/open intervals rather than inventing earlier closed/open periods.
Missing/naive/invalid/future dates request review; future open age clamps to zero, never negative age.
Cloud readiness uses strong current-state inputs and a documented approximation for unobserved cloud
transitions; no live cloud lifecycle producer is claimed.

## Bands, hazards and overrides

Central backend thresholds (configurable PRIORITY_BANDS): LOW<40, MEDIUM40–<60, HIGH60–<80,
CRITICAL80–100. These are prototype
classification boundaries, not safety standards. UI renders server labels/text, not color alone.

A verified hazard requires an ADMIN-confirmed flag, current evidence references and a written reason.
It sets effective operational priority100 and emergency-first ordering without changing calculated P.
An override cannot suppress this rule. Clearing a hazard requires another confirmed, reasoned action;
both states remain audited. No municipal emergency call or external notification is sent.

An override stores its own UUID, score0–100, reason/admin/time, optional timezone-aware future expiry,
membership epoch and status. It changes effective priority only. Removal or expiry returns to the
latest recomputed formula/hazard policy, not an old stored score. Membership changes invalidate all
old controls by epoch: severity/impact require reassessment, hazard needs renewed review, and an old
override becomes REVIEW_REQUIRED rather than silently transferring. New split incidents inherit no
controls. Old control reasons and historical scores are retained; nothing is silently deleted.

## Worked examples

- Unknown S/I, one eligible reporter, age0: S=I=3, R≈2.0185, A=0; P=23.54/LOW, provisional.
- Verified S8, I7, U3, age15d: contributions32 +17.50 +8.07 +7.50; P=65.07/HIGH.
- Ten reports by one account use U1, not10. Additional reports can request review but do not add votes.
- A verified urgent flag on the first example keeps raw23.54 but makes effective100/CRITICAL.
  An override to10 still cannot suppress that hazard; clearing/removing controls is audited.

## Dynamic processing and ranking

Existing Phase7 transactions/audits atomically mark affected incident priorities dirty. Membership,
account eligibility, complaint status/reported severity, lifecycle and scoring config changes are
detected. The existing local worker processes bounded priority work after matching/clustering. It
runs only in APP_ENV=local; tests/AWS have no daemon. Calculation failures retain incidents/evidence
and durable retry state. A changed generation/incident version/control/calculation revision rejects
stale writes; source changes invalidate old lease tokens. Same manual operation IDs replay their
exact receipt. Identical meaningful calculations do not create repeated score-history events.

Clock-driven refresh works without a permanent process through the local CLI. Scores refresh hourly
by default or at override expiry, whichever is earlier. Dirty, config-outdated, source-version-stale
or expired results are excluded from current ranked work and clearly marked in details. This avoids
presenting stale scores as live urgency. Pending incidents stay visible in master incident management.

Ranking is server-side: verified hazard first, effective score descending, stored unresolved time
descending, stable incident UUID. Optional oldest-first mode also keeps verified urgent hazards first.
Category/band/status/assessment/
override/hazard/factor/day/search filters operate on the same stored dataset. SQLite queue revision
changes invalidate continuation cursors with409. Cursors also expire within60s or the earliest stored
time-based refresh, whichever comes first; restart page1. They are not permanent snapshot handles.

## UI, privacy and Windows commands

/admin/priorities shows real local totals, fresh versus pending counts, bands, assessment/hazard/
override counts and ranked records. Existing incident details contain contribution bars, all factors,
explanations, assessments, hazard/override controls and history. Dialogs require explicit confirmation,
current versions and a reason; failed requests freeze for identical retry. Close/refresh after409.
375/1440px browser accessibility/overflow checks cover real operational flows.

Citizen details receive the unchanged owner-safe association contract and a plain-language rubric
explanation. No new public band is exposed because existing publication consent does not authorize
private incident priority/notes. High urgency never publishes an incident, evidence or linked report.

From D:\CivicLens\backend (use existing .env; never reset accounts):

```powershell
.\.venv\Scripts\python.exe -m app.scripts.recalculate_priorities --dry-run --batch-size 25
.\.venv\Scripts\python.exe -m app.scripts.recalculate_priorities --stale-only --batch-size 25
.\.venv\Scripts\python.exe -m app.scripts.recalculate_priorities --incident-id UUID
.\.venv\Scripts\python.exe -m app.scripts.evaluate_priority_model
.\.venv\Scripts\python.exe -m app.scripts.benchmark_priority
```

Backfill is the same recalculation command, not a second scoring system. --after resumes UUID batches;
the command prints config version, per-record results, nextAfter and failure IDs, and exits nonzero on
failure. Retry failed IDs explicitly or repeat a stale-only sweep. Limit1–500; interruption preserves
completed commits. Alias IDs resolve canonically for single-record calculation; bulk excludes retired
originals. Dry-run opens existing schema6 SQLite mode=ro; no migration/work/job/history/assessment
writes or evidence-file changes. Both maintenance paths refuse cloud mode.

From D:\CivicLens: run scripts\run-backend.ps1 and scripts\run-frontend.ps1 in separate terminals;
scripts\verify.ps1 runs all old/new checks/evaluations/benchmarks and offline infrastructure verification.
Run `npm.cmd --prefix frontend run test:browser` separately. Trusted local ADMIN provisioning remains
scripts\create-local-user.ps1; public registration never creates administrators.

See [data model](PRIORITY_DATA_MODEL.md), [measured evaluation](PRIORITY_EVALUATION.md) and [API](API.md).
NO AWS DEPLOYMENT PERFORMED. Phase9 — Intelligent Department Assignment and Municipal Work
Allocation and Phase10 event-driven workflows are implemented locally. Next: Phase11 citywide
administration and analytics, not started. See [event architecture](EVENT_DRIVEN_ARCHITECTURE.md).

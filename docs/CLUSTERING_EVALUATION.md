# Phase 7 — measured clustering evaluation and benchmark

Executed on the local Windows/Python3.13 SQLite runtime, CPU only, synthetic data. No AWS/paid model,
external image download, real citizen dataset, production calibration or zero-error claim.

## Dataset and protocol

61 labelled reports across16 synthetic scenario families. Four families/15 reports are tuning data;
twelve disjoint families/46 reports are held out. Prototype defaults were retained, not optimized on
held-out outcomes. Cases include one physical pothole, separate holes17–18m apart, numbered adjacent
streetlights, same-place incompatible categories,120m GPS outlier, absent photos, reused photos, vague
OTHER reports, resolved/returning issues,0–8–16–24m transitive chains,3m overlapping distinct defects,
and repeat submissions from the same citizen. Scenario families are geographically separated to avoid
accidental unrelated cross-family matches. Local immutable synthetic identities and image patterns only.

Three executed strategies:

A. Naive connected components: actual Phase6 fused scores>=.80, compatible category/radius/active
reports, no full-cluster guard or additional physical-object review. Used only as evaluation baseline.

B. Real CONSERVATIVE_AUTO_LINK service: sequential durable complaint/singleton/matching/clustering
pipeline and all-member checks, not a mocked ground-truth cluster assignment.

C. REVIEW_ONLY plus simulated administrator: actual manual merge service applies oracle ground-truth
approvals subject to category/spatial bounds. The oracle KNOWS truth that neither an ordinary admin nor
the automatic engine knows; it is an upper reference, not a fair autonomous competitor. The120m GPS
outlier is intentionally rejected by manual bounds, leaving two false-negative pairs.

Pairwise metrics use all unordered report pairs. Precision=TP/(TP+FP), recall=TP/(TP+FN), F1 harmonic
mean. Purity sums majority true labels per predicted cluster / report count. Review cases are sources
with suggestions not automatically accepted, not estimated human minutes or claimed workload savings.

| Split / strategy | TP | FP | FN | Precision | Recall | F1 | Purity | Clusters |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tuning A naive |13|4|0|.7647|1.0000|.8667|.8667|5|
| Tuning B guarded |9|0|4|1.0000|.6923|.8182|1.0000|9|
| Tuning C oracle review |13|0|0|1.0000|1.0000|1.0000|1.0000|6|
| Held-out A naive |37|22|2|.6271|.9487|.7551|.7609|15|
| Held-out B guarded |27|8|12|.7714|.6923|.7297|.9130|26|
| Held-out C oracle review |37|0|2|1.0000|.9487|.9737|1.0000|21|

Verification-script run:4 tuning /9 held-out review cases,0/1 oracle merges rejected. Median guarded
per-complaint pipeline131.661/128.111ms; median oracle merge17.428/15.444ms. These include local
persistence and depend on CPU/load. Re-running prints new timings; decisions/metrics are deterministic
for this fixture and configuration, not guaranteed real-city accuracy.

The guarded policy reduces naive FP pairs22→8, but sacrifices recall and has LOWER F1 on this held-out
fixture. Identical reused photos and generic text at overlapping nearby defects still produce false
automatic consolidation. This is NOT evidence that conservative auto-link is production-safe. Default
REVIEW_ONLY is retained. A no-human review-only deployment leaves separate singletons until real admin
approval; the oracle result must never be presented as achieved unattended accuracy.

## Actual600-report operation benchmark

Serial local run, mostly singleton records; not a cloud/concurrency capacity test or SLA:

| Operation | Measured time |
|---|---:|
|600 singleton assignments |7276.677ms total;11.695ms median|
|Manual merge |18.430ms median|
|Split |20.854ms|
|Member retrieval |8.256ms|
|Catalog20 |17.141ms|
|Reconciliation500 complaints + bounded metadata |2233.516ms;0 issues|
|Idempotent backfill500 |927.172ms|
|Actual matching pass,19 comparisons |1341.271ms|
|Clustering check |97.075ms; competing incidents held for review|

The merge/split workload includes multiple reports from one synthetic account; exact independent
support remains1. Successful auto-link behavior is covered by fixture tests; this benchmark's contested
candidate correctly does not auto-link. No unbounded all-city pairwise operation or misleading merge
speed is inferred from a one-record lookup. Reconciliation uses separate bounded candidate/event
cursors; re-run for current wall-clock timings. Other verification processes shared this machine.

```powershell
Set-Location D:\CivicLens\backend
.\.venv\Scripts\python.exe -m app.scripts.evaluate_clustering
.\.venv\Scripts\python.exe -m app.scripts.benchmark_incidents
```

Both commands create disposable temporary stores and close them; they never seed the developer account
database. Code/data: app/scripts/{evaluate_clustering,benchmark_incidents}.py and
app/algorithms/clustering_evaluation_data.py. Raw JSON includes denominators, FP/FN, review cases,
timings and limitations. No AWS deployment performed.

# Phase 8 — measured synthetic ranking, sensitivity and performance

Executed locally on Windows/Python3.13, SQLite, CPU only. Scores are an administrative prototype,
not validated accident risks or dispatch recommendations. No AWS or paid model was used.

## Data and reference rubric

120 fictional labelled incidents: twelve template cases across ten deterministic variants.36 tuning
cases (33 active) and84 held-out cases (77 active); resolved cases excluded from active ranking.
Variants share problem templates, so this split is not evidence of generalization to unseen cities or
defect types. No real expert labels are claimed. Reference labels are documented fictional rubric
judgments: verified immediate hazard4; severe defect/essential access3; significant/uncertain2;
minor1; resolved0. They necessarily correlate with the same assessment inputs and are not independent
scientific validation. The default weights were retained, not selected on held-out performance.

Cases: serious pothole/few reporters, minor streetlight/many reporters, dangerous drainage, old minor
damage, repeated same-account reports, essential access/high impact, unknown impact, resolved,
reopened, incorrectly merged/stale assessments, split subset and verified emergency-access hazard.
The real scoring engine is executed for every case, including provisional and hazard/epoch policies.

Baselines: oldest-first, valid assessed/provisional severity-only, raw complaint-count popularity.
Proposed method uses all four factors and verified hazard-first ordering. Severity baseline uses the
same validity/default policy, not stale verified scores from an invalidated membership epoch.

Metrics: Spearman correlation with tied ordinal reference ranks; NDCG@20 with `2^grade-1` gains;
pairwise reference agreement excluding equal labels; top20 recall of reference grade>=3 and missed
important count. There are28 important held-out incidents but only20 slots, so even perfect top20
precision cannot exceed20/28=.7143 recall. Missed count8 must not be misrepresented as zero misses.

| Held-out method | Spearman | NDCG@20 | Important recall@20 | Missed | Pairwise agreement |
|---|---:|---:|---:|---:|---:|
| First-come-first-served |-.6736|.1051|0|28|.1716|
| Severity-only |.8650|.9049|.7143|8|.9156|
| Raw complaint count |-.2807|.1138|0|28|.3312|
| Proposed rubric |.9362|1.0000|.7143|8|.9842|

Tuning proposed: Spearman.9301, NDCG.9865, important recall1.0 (12/12), agreement.9798.
Pure engine median time in the captured run:.0695ms tuning /.0679ms held-out; persistence is excluded.

## Weight and small-input sensitivity

| Configuration S/I/R/A | Held-out Spearman | NDCG@20 | Maximum rank shift versus default |
|---|---:|---:|---:|
| Default40/25/20/15 |.9362|1.0000|0|
| A50/25/15/10 |.9261|1.0000|14|
| B35/30/20/15 |.9261|1.0000|5|
| C40/20/20/20 |.9584|1.0000|9|

All alternatives total100% and retain20/28 important recall. Configuration C scores better on these
fictional references, but this does not establish superior field fairness/safety or justify changing
defaults automatically. More aging can elevate old low-severity issues; more support can favor areas
with more platform adoption; more severity emphasizes administrative assessment accuracy. Verified
hazards remain independently first. A+.1 severity perturbation changed held-out ranks by mean.5195,
maximum4 positions (tuning mean.0606/max1). The tool prints version hashes and largest changed IDs.

## Actual600-incident SQLite benchmark

Disposable stores use real Phase7 singleton creation and real Phase8 snapshot/transaction/ranked query/
history/merge/split/aging operations, not mocked return values. Captured run:

| Operation | Measured result |
|---|---:|
| Bulk calculate600 |17805.374ms;33.70 incidents/s|
| Median single persisted calculation |28.800ms|
| Ranked query20 |16.647ms;20 returned|
| Filtered ranked query |13.456ms;20 returned|
| History lookup20 limit |3.222ms|
| Merge + surviving priority recalculation |65.124ms|
| Split + both priority recalculations |111.343ms|
| One-day advancement /100 recalculations |2515.560ms|
| Peak traced Python allocation |328170 bytes|

Rank-plan verification uses covering index priority_rank. One score performs a bounded snapshot
transaction and guarded write transaction; it never loads all city complaints for each incident.
tracemalloc tracks Python allocations only, not total process/SQLite/OS memory, and affects timings.
Serial local measurements under other verification load are not cloud capacity, production throughput,
concurrency certification or an SLA. Later reruns print their own timings; this table is one actual run.

## Reproduce / limits

```powershell
Set-Location D:\CivicLens\backend
.\.venv\Scripts\python.exe -m app.scripts.evaluate_priority_model
.\.venv\Scripts\python.exe -m app.scripts.benchmark_priority
```

Data: app/algorithms/priority_scoring/evaluation_data.py. Both scripts use synthetic records only;
benchmark temporary stores do not touch existing accounts. Real scenarios need independent municipal
review, longitudinal assessment, reporting-adoption bias analysis and stronger multiple-account abuse
controls. Unknown impact and false/incorrect clusters reduce confidence; assessments must be renewed
after membership correction. No spatial/population/traffic inference, model training or automatic
weight selection occurs. NO AWS DEPLOYMENT PERFORMED.

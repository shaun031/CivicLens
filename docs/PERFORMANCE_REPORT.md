# Phase 13 local performance assessment

Windows11 build26200, Python3.13.2, SQLite3.45.3, Node22.20.0. All measurements use
temporary SQLite/evidence and CPU; no normal user-data load test or cloud endpoint.
Results vary with hardware/cache/background verification. They are not AWS latency,
labor productivity or production concurrency estimates.

## ASGI HTTP endpoint benchmark

Command: `python -m app.scripts.benchmark_api --output <new-file.json>`.
One standalone run:1000 synthetic reports/500 canonical incidents,6 departments/
officers,10 additional real HTTP submissions; one422-byte256×128PNG fixture.
Serial concurrency1; p95 uses nearest-rank sorted sample. Read n=15; login/submission
n=5; repair mutations n=1. Full response pipeline, cookies/validation/private
storage included; TCP/uvicorn/browser/network excluded. **Zero unexpected errors**.

| Operation | Median ms | p95 ms | n |
|---|---:|---:|---:|
| Login |92.255|101.588|5|
| Complaint, no image |19.152|24.239|5|
| Complaint, bounded PNG |23.589|25.696|5|
| Search |7.260|11.808|15|
| Complaint list |6.851|8.556|15|
| Citizen summary |6.722|9.109|15|
| Complaint details |6.794|9.551|15|
| Notification list |6.781|41.210|15|
| Nearby published issues |15.293|18.130|15|
| Duplicate candidate catalog |6.087|10.825|15|
| Canonical incident details |8.285|29.194|15|
| Priority queue |8.655|12.245|15|
| ADMIN overview |29.418|63.010|15|
| Geographic hotspots |29.070|30.163|15|
| Repair-review catalog |6.319|7.715|15|
| Recurrence catalog |6.022|7.264|15|
| Fairness, first cold then cache |6.815|32.778|15|
| Officer queue |9.818|14.592|15|
| Repair submission |26.287|26.287|1|
| Repair approval |26.200|26.200|1|

These exact values are one saved run in `build/phase13-api-benchmark.json`, not
promised repeat-run values. The complete verify script produces another separately
dated run. The n=1 mutation percentile is just that observation, not a stable p95.
The final logged run (`build/verification/20261021-011721-778ccd60/api-benchmark.json`)
also returned zero errors: list p95=17.342ms, summary14.423ms, incident65.690ms,
nearby30.801ms. All four provisional local targets passed again; differences are
run/hardware-load variation, not claimed optimization speedups.
Public/candidate/notification and initial repair/recurrence catalogs here are empty;
do not imply all requests searched1000 owner records or a dense historical graph.
Private citizen lists contain10 new reports. ADMIN analytics uses500 canonical rows.

Provisional acceptance: list/summary/incident-details p95<500ms and nearby<1000ms
passed on this fixture. This is a local demo target, not an arbitrary deployment SLA.
No production/cloud performance readiness follows from it.

## SQLite/index evidence

5000-report/3000-owner/500-published-point standalone query benchmark,5 warmed runs:
search median6.054/max7.177ms; combined filters7.607/7.934; cursor page3.524/4.227;
summary5.016/6.595; bounding box8.366/9.583; radius8.903/9.226. Bounded results20/50.
Query plan uses covering `complaints_owner_category` and partial `publications_geo`.

New API benchmark EXPLAIN results use `complaints_citizen_created`, `assignment_officer`,
`notification_owner`, `outbox_due`, `repair_incident`, not unindexed full-table scans
for those sampled access patterns. Analytics intentionally takes a bounded joined
snapshot; caps/413 are explicit, and fairness caches revision+filter+30s. Recurrence
bounded historical lookup and exports remain finite. No speculative index was added:
the measured paths did not justify another write/storage cost or destructive migration.

## Worker/research/repair benchmarks

`benchmark_events` executes100 real triage workflows plus one controlled failed/recovered
workflow,100 repeated enqueue attempts, notification writes, scheduled checks and one
invalid message/DLQ in a disposable store. No handler side effects are replaced with
mock success. Retry-clock advancement is disclosed, not real120s waiting. Final
measured throughput/latencies and queue counts are recorded in verification logs.
Final native `step-11.log`:100 normal workflows +1 recovered, workflow median580.153ms,
1.649 workflows/s for the measured processing section, controlled failed attempt236.191ms,
recovery622.827ms, expected invalid-message dead-letter33.278ms. Final summary:
101 COMPLETED workflows,405 COMPLETE messages,1 deliberately malformed DEAD message,
zero pending outbox events. Controlled failures are not unexplained application loss.
500/1000-workflow capacity/memory were not measured;100 is the selected controlled
demonstration workload, not a maximum supported rate.

Other default verification benchmarks measure matching cold/warm/photo/missing cases,
canonical mutations, priority calculation/ranking,300-incident allocation,1000-report
analytics and20 real repair/feedback/approval cycles with recurrence/fairness/cache/CSV.
They have different scopes; do not mix repository median times with ASGI p95.
See the saved log for all values and [research report](RESEARCH_EVALUATION_REPORT.md)
for reproducible pair/rank metrics rather than inferred accuracy from speed.

## Optimizations and remaining bottlenecks

Targeted changes: streamed bounds prevent unbounded JSON parsing/allocation; configured
logging level now suppresses unwanted hosted INFO output; safe CDK staging omits test/
coverage files. Existing indexes, consistent bulk snapshots, missing-modality behavior,
bounded requests and revision cache were retained. No database index/algorithm rewrite
was justified by this workload, and no before/after speedup is invented.

Native dependency import/image decode can dominate cold processing; synchronous
bounded recurrence can inspect up to100 candidates, unlike the one-candidate timing
fixture. Dynamo1WCU/hot shared counters and Lambda15s/256MB remain unprofiled.
Dense5000-incident fairness,100-candidate-photo recurrence, larger queues/concurrent
HTTP throughput, memory and independent field data require further testing. No high-
volume live deployment benchmark or effectively-free-cost claim is made.
Recurrence photo metadata/retrieval repeats per candidate (bounded100); the one-candidate
benchmark does not rule out a bounded N+1/I/O bottleneck at the maximum configuration.

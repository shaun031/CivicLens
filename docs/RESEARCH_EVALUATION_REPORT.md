# Phase 13 reproducible research evaluation

Date2026-10-21. Offline CPU-only synthetic experiments, **not** independent field,
expert, repair-inspection or causal-discrimination validation. No model/threshold
was tuned to improve reported held-out results. Defaults remain unchanged.

## Reproduction and provenance

From `D:\CivicLens\backend`:

```powershell
.\.venv\Scripts\python.exe -m app.scripts.evaluate_civiclens --output '..\build\evaluation-new-run'
```

Output must be a new directory. `results.json` records UTC time, seed13, Python,
actual metrics/elapsed times/config, evaluator/algorithm source SHA256 and dataset
digest. `datasets.json` snapshots144 matching pairs,61 clustering reports and120
priority rows. Recurrence/repair/fairness/routing fixtures are code-defined and
source-hashed. `report.md` provides readable results; `verify.ps1` saves a fresh run.
Earlier standalone artifacts in `build/phase13-evaluation` are retained as snapshots;
the final authoritative run (including the extra volume/missingness cases) is
`build/verification/20261021-011721-778ccd60/evaluation`. Generated results are ignored builds,
not silent replacements for missing evidence.

## Duplicate matching

Dataset `synthetic-families-v1`:24 scenario families ×6 variants; family-disjoint
tuning/evaluation. Binary held-out scoring uses54 pairs from9 families, excluding
explicit UNCERTAIN labels. All five baselines use the SAME category/lifecycle/radius
eligibility. Cutoff0.80; image-only missing/corrupt/low-information cases count as
negative, and image-available/missing strata are separately recorded.

| Held-out method | TP | FP | TN | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Geography only |24|12|18|0|0.6667|1|0.8000|
| TF-IDF text only |24|12|18|0|0.6667|1|0.8000|
| dHash image only |6|18|12|18|0.2500|0.2500|0.2500|
| Geography + text |24|12|18|0|0.6667|1|0.8000|
| Actual proposed engine/missing-modality safeguards |24|0|30|0|1|1|1|

The proposed engine includes safeguards, not just another unconstrained weighted
mean. Perfect performance on this tiny hand-authored split is **not** evidence of
real-city accuracy or an image benefit. It has no false positives on this split;
false-positive examples therefore correctly remain empty. Reused photos, nearby
distinct objects and uncertain viewpoint cases are explicitly included in fixtures.
At threshold0.85 recall drops to0.7917/F1.8837; at0.90 recall.75/F1.8571. The full
0.60–0.90 threshold/radius curves are saved, without selecting on held-out results.

Seeded500-draw family-cluster bootstrap yields proposed F1 interval[1,1] on these
nine families. This is a degenerate descriptive interval, NOT a credible real-world
uncertainty bound. Candidate Recall@K is **NOT_VERIFIED**: pair labels are not an
independently labelled retrieval corpus. Do not invent relevance across unrelated
pairs. Indexed retrieval and image decode are separately benchmarked, not included
in pair-engine latency. Similarity is not a calibrated duplicate probability.

## Clustering

Dataset `synthetic-physical-groups-v1`:61 reports, held-out46 reports/12 families;
pairwise evaluation includes all1035 held-out pairs. Review-only remains default.

| Method | TP / FP / TN / FN | Precision | Recall | F1 | Purity |
|---|---|---:|---:|---:|---:|
| Naive similarity connected components |37 /22 /974 /2|.6271|.9487|.7551|.7609|
| Conservative all-member cohesion |27 /8 /988 /12|.7714|.6923|.7297|.9130|
| Review-only simulated oracle |37 /0 /996 /2|1|.9487|.9737|1|

Conservative logic reduces false merged **pairs**22→8 but misses12 duplicate pairs
and has lower F1 than the naive baseline here. It is not universally superior.
Nine reports require review, one oracle action is refused by safety bounds. Oracle
review uses synthetic truth unavailable to automation; it is not measured municipal
staff performance. Runtime varies; one standalone run measured328.547ms/complaint
median including insertion/matching/grouping, not just graph logic.

Adversarial A–B–C transitive, close separate defects, same-account repeats,
category conflicts, merge/split, stale candidates, repeated and concurrent processing
have repository tests. Cohesion blocks unsafe transitive-only linking, but the eight
other false pairs demonstrate that a numeric score cannot establish physical identity.

## Priority ranking

`fictional-priority-rubric-v1`,120 rows, repeated synthetic templates with fixed
reference urgency grades, not expert field labels. Actual weights severity.40,
impact.25, distinct reporters.20, active unresolved time.15. Calculated score is
separate from operational override and verified urgent-hazard-first ordering.

| Held-out method | Spearman | NDCG@20 | Critical recall@20 | Important missed | Pairwise agreement |
|---|---:|---:|---:|---:|---:|
| First come first served |-.6736|.1051|0|28|.1716|
| Severity only |.8650|.9049|.7143|8|.9156|
| Raw complaint count |-.2807|.1138|0|28|.3312|
| CivicLens weights |.9362|1|.7143|8|.9842|

All cannot fit28 important incidents into top20; weighted scoring does not improve
critical recall over severity-only on this fixture. Alternate weight sets produce
maximum rank shifts14/5/9. Inputs+0.1 severity and full sensitivity metrics are saved.
Splits repeat urgency templates, so they are not independent out-of-template validation.
Repeat account reports do not count as independent reporters. Hazard/override/
merge/split/aging missing-data behavior is tested, not claimed learned-optimal.

## Department routing and officer allocation

Additional explicit10-case routing fixture includes six categories, OTHER fallback,
inactive department, ambiguous equal precedence and uncovered location. Actual router
selected expected department/review behavior in10/10 cases; constructed review rate.4.
Ten simulated weighted allocations only choose eligible officers a/b, rate1.0,
invalid count0, workload0/0→10/10 with stable tie-breaking. On-leave/inactive/full
candidates are excluded. No real assignment ground truth/productivity benefit is
claimed. Transactional history/capacity/global races and manual overrides are tested
separately in `test_work_allocation.py` and the real lifecycle.

## Recurrence, separate from active duplicates

48 synthetic pairs/12 scenario templates, no independent held-out set. Verified
history must precede the new report; missing history/unverified claims are not
verified repairs. Both the real HTTP later-cycle test and repository tests keep
new incidents distinct and require explicit physical-identity review.

| Method | TP / FP / TN / FN | Precision | Recall | F1 | False recurrence FP/(FP+TN) |
|---|---|---:|---:|---:|---:|
| Geographic history |16 /28 /4 /0|.3636|1|.5333|.8750|
| Geography + text |16 /28 /4 /0|.3636|1|.5333|.8750|
| Geography + text + image gate |12 /24 /8 /4|.3333|.75|.4615|.7500|
| Full verified-history logic |16 /4 /28 /0|.8000|1|.8889|.1250|

Full missed recurrence FN/(TP+FN)=0 on this fixture; image gate misses.25. Four full
false suggestions are nearby distinct potholes, not proven recurrences. No image
accuracy improvement claim is supported. Historical membership/cycle invalidation,
merge/split/version guards and review idempotency are distinct domain tests, not
inferred from a positive score. Candidate latency benchmark has one eligible
historical candidate, not a100-candidate stress or recall experiment.

## Repair verification policy experiment

40 claims =8 noisy synthetic cases repeated5times;15 disputed,20 labelled as needing
rework.30/40 have observed feedback (coverage.75), not a real citizen response rate.
Officer-claim-only simulation makes20 incorrect closures, agreement.50; citizen
majority makes10 false closures and10 false nonclosures, agreement.50; noisy ADMIN
review simulation makes5+5 errors, agreement.75. None guarantees repair quality.
The application does **not** implement automatic officer/majority closure. Actual
tests cover immutable feedback, mixed votes/disputes, approve/reject/rework/reopen
and synchronized decision races. Field decision-time/inspection accuracy is
NOT_VERIFIED; local transaction timing must not be called time-to-repair.

## Geographic service analysis

Baseline12 constructed comparisons use samples3/10/30, grids.01/.1 and same/different
priority/department mix. Fine-grid sample3 is insufficient;10/30 expose the
constructed24h vs96h and known-SLA difference. Coarse grid merges cells and cannot
compare them. Raw equal counts alone miss the known delay difference.

Phase13 adds six explicit volume/missingness cases (sample vs3×sample). An area
with all response/SLA observations missing has null medians/rates and insufficient
comparability, not zero delay or good service. Source tests cover n, missing-data
denominators, verified resolution, corrected membership, grids/edges and recurrence
dedup. Reporting bias cannot be inferred from these incident-volume simulations:
no population, asset inventory, actual defect prevalence or causal capacity/severity
adjustment exists. Different priority/department mix is disclosed, not controlled away.

## Remaining research work

Independent labelled retrieval/viewpoint/physical-asset data, field repair outcomes,
population/infrastructure denominators and operational capacity/time labels remain
unavailable. No paid ML/API/GPU, external images or citizen production data was used.
Perfect synthetic scores, noisy policy agreement and bootstrap intervals are not
deployment safety, causal fairness or calibrated-probability claims.

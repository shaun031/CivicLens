# Phase 6 — measured synthetic matching evaluation

Measured locally on Windows/Python 3.13.2, scikit-learn 1.9.1, Pillow 12.3.0, 2026-10-20.
Reproduce from `D:\CivicLens\backend`:

```powershell
.\.venv\Scripts\python.exe -m app.scripts.evaluate_matching
.\.venv\Scripts\python.exe -m app.scripts.benchmark_matching
```

## Dataset, truth and split

`app/algorithms/duplicate_detection/evaluation_data.py` is the versioned synthetic dataset source.
There are **144 labeled pairs, 24 hand-authored scenario families, six variants per family**.
Each family belongs wholly to tuning or evaluation: 12 families/72 pairs per split, each containing
24 DUPLICATE, 30 NOT_DUPLICATE and 18 UNCERTAIN pairs. Coordinate/case/spacing variants NEVER cross
the split. Effective diversity is 24 families, not 144 independent municipal observations. Groups
have distinct text/physical scenarios; shared ordinary infrastructure words are intentional.

Labels encode author-stated synthetic object identity, not engine predictions. Cases include synonymous
campus potholes, lamp terminology, identical distant descriptions, two potholes 17–18m apart, adjacent
first/second poles, opposite entrances, incompatible garbage/drainage and streetlight/garbage,
resolved historical reports, same/reused photographs, different synthetic views, missing/corrupt
images and vague OTHER descriptions. No real citizen/private data or fetched/training photographs
are used. Synthetic arithmetic pixel patterns stand in for image-signal conditions; they do NOT
validate different-angle object recognition. The fixed TF-IDF corpus is separate from these pairs.

## Protocol and baselines

Binary positive means STRONG_CANDIDATE, NOT a confirmed duplicate. Review-required predictions are
negative for binary metrics. UNCERTAIN labels are excluded from confusion/precision/recall/F1 and
their classifications are reported separately, not forced into positive/negative truth.

All four strategies have identical category, active-lifecycle and category-radius eligibility.
Ineligible labeled pairs count as negative predictions; this evaluation includes retrieval-gate
hard negatives. Baseline A thresholds L only; B thresholds T only within that SAME eligible candidate
policy; C thresholds `(L+T)/2` without the proposed safeguards. Proposed uses available-image fusion
and all safeguards. Thus text-only here is NOT unrestricted global text search. Image-available and
missing-image examples occur in both splits; score renormalization does not silently discard pairs.

These are pair-level diagnostics. Ranked retrieval Recall@K is not measured, nor is exhaustive recall
in a capped/dense global candidate pool. Unit/integration tests and benchmark separately exercise
private indexed retrieval, neighbor cells, caps and incompleteness. No statistical significance,
population error estimate or probability calibration is claimed.

Precision = TP/(TP+FP), recall = TP/(TP+FN), F1 = 2PR/(P+R); undefined zero denominators return zero.

## Actual default-threshold results (0.80)

Held-out evaluation, 54 binary pairs:

| Strategy | TP | FP | TN | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Geographic only | 24 | 12 | 18 | 0 | 0.6667 | 1.0000 | 0.8000 |
| Text only (shared candidate policy) | 24 | 12 | 18 | 0 | 0.6667 | 1.0000 | 0.8000 |
| Geographic + text | 24 | 12 | 18 | 0 | 0.6667 | 1.0000 | 0.8000 |
| Proposed, all available modalities + guards | 24 | 0 | 30 | 0 | 1.0000 | 1.0000 | 1.0000 |

Proposed confusion matrix, rows truth and columns predicted positive/negative:

| Truth | Positive | Negative |
|---|---:|---:|
| DUPLICATE | 24 | 0 |
| NOT_DUPLICATE | 0 | 30 |

Tuning split (also 54 binary pairs):

| Strategy | TP | FP | TN | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Geographic only | 24 | 0 | 30 | 0 | 1.0000 | 1.0000 | 1.0000 |
| Text only | 18 | 12 | 18 | 6 | 0.6000 | 0.7500 | 0.6667 |
| Geographic + text | 24 | 12 | 18 | 0 | 0.6667 | 1.0000 | 0.8000 |
| Proposed | 21 | 0 | 30 | 3 | 1.0000 | 0.8750 | 0.9333 |

**The proposed engine does not win every comparison:** geographic-only is better on this tuning split.
Three true synthetic paraphrases fail the strong-text guard. Both splits' 18 uncertain pairs produce
12 INSUFFICIENT_EVIDENCE and six REVIEW_REQUIRED predictions. None is represented as confirmed truth.
Perfect held-out synthetic results do not imply production accuracy; these small hand-constructed
groups intentionally exercise known failure mechanisms and cannot represent real-world ambiguity.

## Threshold and radius sensitivity

Initial 0.80 strong / 0.60 review thresholds and category radii were retained as conservative prototype
policy. No parameters were tuned on held-out labels. The tuning sweep does not identify a unique
optimal threshold: 0.60–0.85 tie on tuning F1; changing safeguards to recover three paraphrases would
need independent field evidence. Evaluation sweeps are diagnostic only, not a selection procedure.

| Strong threshold | Tuning TP/FP/TN/FN | Tuning P/R/F1 | Held-out TP/FP/TN/FN | Held-out P/R/F1 |
|---|---|---|---|---|
| 0.60 | 21/0/30/3 | 1/.875/.9333 | 24/0/30/0 | 1/1/1 |
| 0.65 | 21/0/30/3 | 1/.875/.9333 | 24/0/30/0 | 1/1/1 |
| 0.70 | 21/0/30/3 | 1/.875/.9333 | 24/0/30/0 | 1/1/1 |
| 0.75 | 21/0/30/3 | 1/.875/.9333 | 24/0/30/0 | 1/1/1 |
| 0.80 | 21/0/30/3 | 1/.875/.9333 | 24/0/30/0 | 1/1/1 |
| 0.85 | 21/0/30/3 | 1/.875/.9333 | 19/0/30/5 | 1/.7917/.8837 |
| 0.90 | 13/0/30/11 | 1/.5417/.7027 | 18/0/30/6 | 1/.75/.8571 |

Sensitivity also sets ALL category radii to 30m, 50m and 75m independently. Each yields proposed
held-out TP24/FP0/TN30/FN0 and P/R/F1 1/1/1. This flat response demonstrates the coarse/easy distance
distribution of this fixture, NOT radius robustness in a real city. Operational category-specific
radii remain 30/50/75m and require prospective validation with object identity and GPS uncertainty.

## Measured performance

Disposable database: 1,000 synthetic complaints, 200 in a deliberately dense eligible private region,
10 small synthetic JPEGs; six sequential source rechecks. Compare cap 100; actual compared 100,
queryTruncated=true and processing INCOMPLETE as expected. No developer/user database was opened.

One recorded Windows run (milliseconds; timings vary with CPU/cache/concurrent tests):

| Stage | Cold run | Median of five warm runs |
|---|---:|---:|
| Indexed retrieval/hydration | 7.334 | 7.383 |
| Image storage/fingerprint/cache | 75.548 | 7.027 |
| Geographic comparisons | 1.336 | 0.933 |
| Text (cold includes sklearn import/model fit) | 2136.772 | 35.536 |
| Fusion/explanation | 13.906 | 9.790 |
| Total before result commit | 2244.655 | 69.373 |

The query plan is `SEARCH complaints USING COVERING INDEX complaints_internal_geography
(latitude>? AND latitude<?)`. Total-stage timer excludes the final atomic persistence transaction;
stage sums also exclude some selection/bookkeeping overhead. This is a serial local microbenchmark,
not throughput, full-resolution photo, concurrent deployment, AWS cold-start or SLA evidence.
Existing Phase 5's independent 5,000-record benchmark remains available.

## Remaining validation

Prospective, consented object-labeled field data, independent human adjudication, realistic GPS error,
multilingual descriptions, actual photo viewpoints, hard-negative mining, calibrated review effort,
retrieval Recall@K in dense areas and production resource profiling are still needed. A stronger local
embedding adapter could improve paraphrases later but is not downloaded or required here. Do not
interpret any similarity index as statistical probability, nor use these fixtures to justify merging.

# Recurring infrastructure failures

Phase13 centrally reproduces baselines and tests a real later-report-after-approval
worker flow. Nearby distinct defects still cause false suggestions; never merge repair
cycles automatically. [Metrics/limits](RESEARCH_EVALUATION_REPORT.md).

Duplicate: multiple reports of a currently unresolved defect (P6/P7). Failed repair: the existing
defect was never adequately fixed; retain/reopen the same incident. Recurrence: a new occurrence after
a genuinely ADMIN-verified completed repair. These are not interchangeable, and recurrence never
automatically merges incidents or changes the P8 priority formula.

The existing P10 triage's final stage checks the canonical incident for historical repairs; ADMIN can
explicitly request a recheck. An indexed geographic envelope retrieves at most100 historical canonical
RESOLVED incidents of the same category with a current VERIFIED_RESOLVED attempt, matching resolution
timestamp and plausible temporal horizon. Overflow is an explicit bounded-query error, not a truncated
claim of completeness. Antimeridian envelopes use wrapping longitude predicates; actual distances use
the P6 haversine implementation. The earliest report must follow the previous verified completion.

Defaults (configurable):150 metres,730 days,0.65 suggestion threshold. Score without images:
0.40 geographic proximity +0.45 P6 word/character TF-IDF +0.15 exp(-days/365). With informative images:
0.30 geography +0.35 text +0.15 time +0.20 P6 dHash. Missing/corrupt/low-information photos contribute
no positive image signal. Category/time/radius safeguards and P6 contradictory-object/location
qualifiers constrain suggestions. No physical asset ID is invented. Algorithm/configuration version,
effective signals/weights, contradictions, missing-evidence limitations and deterministic explanation
are stored. This evidence score is NOT a calibrated probability or the P6 duplicate threshold.

Unique previous→new canonical pair records use POTENTIAL_RECURRENCE, INSUFFICIENT_EVIDENCE,
CONFIRMED_RECURRENCE or DISMISSED. Strict chronology and no self-links prevent cycles. Confirmation
requires ADMIN, explicit physical-identity review beyond location/text, reason, version and idempotency
receipt. Recalculation/review keeps audit history; dismissed suggestions are not automatically revived.
Confirmed links survive normal resolution of the newer occurrence, but membership-epoch changes,
retired aliases, historical reopening or invalidated repair require reassessment. Historical records
are retained rather than silently relinked across merge/split corrections.

`/admin/recurrences` provides bounded state/category/date pages, previous/new incident comparison,
distance, elapsed days, text/image signals, chronological distinct-incident history and review controls.
Protected incident/repair pages provide authorized evidence/history. Geographic reports count distinct
new canonical incidents with VALID CONFIRMED links; candidates and pair counts are separate. A repaired
location is represented by grid cells, not asserted to be a verified asset identity.

Known limitations: same-word different potholes20m apart can still be suggested. Only human review
confirms recurrence. English TF-IDF and dHash are not robust semantic/physical identity models. No paid
ML services, remote model calls or real-world accuracy claim is introduced. See PHASE12_EVALUATION.md.

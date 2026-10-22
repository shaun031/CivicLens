"""Reproducible fictional-reference ranking and weight sensitivity; no default optimization."""

import json
import math
from dataclasses import replace
from statistics import mean, median
from time import perf_counter

from app.algorithms.priority_scoring.config import PriorityConfig
from app.algorithms.priority_scoring.evaluation_data import dataset
from app.algorithms.priority_scoring.scoring_engine import calculate


def ranks(values):
    ordered = sorted(range(len(values)), key=lambda index: values[index], reverse=True)
    output, position = {}, 0
    while position < len(ordered):
        end = position + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[position]]:
            end += 1
        for index in ordered[position:end]:
            output[index] = (position + end - 1) / 2
        position = end
    return [output[index] for index in range(len(values))]


def metrics(order, rows, k=20):
    k = min(k, len(rows))
    labels = {row["id"]: row["label"] for row in rows}
    reference = [row["label"] for row in rows]
    positions = {identity: len(order) - index for index, identity in enumerate(order)}
    reference_ranks, predicted = ranks(reference), ranks([positions[row["id"]] for row in rows])
    a, b = mean(reference_ranks), mean(predicted)
    denominator = math.sqrt(
        sum((x - a) ** 2 for x in reference_ranks) * sum((y - b) ** 2 for y in predicted)
    )
    spearman = (
        sum((x - a) * (y - b) for x, y in zip(reference_ranks, predicted, strict=True))
        / denominator
        if denominator
        else 0
    )

    def dcg(grades):
        return sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades))

    ideal = dcg(sorted(reference, reverse=True)[:k])
    important = {row["id"] for row in rows if row["label"] >= 3}
    found = len(important & set(order[:k]))
    comparisons = [
        (labels[a], labels[b])
        for i, a in enumerate(order)
        for b in order[i + 1 :]
        if labels[a] != labels[b]
    ]
    return {
        "spearman": round(spearman, 4),
        "ndcgAtK": round(dcg([labels[i] for i in order[:k]]) / ideal, 4) if ideal else 0,
        "k": k,
        "importantCount": len(important),
        "importantInTopK": found,
        "criticalRecallAtK": round(found / len(important), 4) if important else 0,
        "importantMissed": len(important) - found,
        "pairwiseAgreement": round(sum(a > b for a, b in comparisons) / len(comparisons), 4)
        if comparisons
        else 1,
    }


DEFAULT_CONFIG = PriorityConfig()


def evaluate(rows, config=DEFAULT_CONFIG):
    active = [row for row in rows if row["data"].status == "OPEN"]
    times, computed = [], {}
    for row in active:
        start = perf_counter()
        computed[row["id"]] = calculate(row["data"], config)
        times.append((perf_counter() - start) * 1000)
    proposed = sorted(
        active,
        key=lambda row: (
            not computed[row["id"]].urgent_hazard,
            -computed[row["id"]].effective_score,
            -computed[row["id"]].unresolved_seconds,
            row["id"],
        ),
    )
    orders = {
        "firstComeFirstServed": sorted(
            active, key=lambda row: (row["data"].first_reported_at, row["id"])
        ),
        "severityOnly": sorted(
            active,
            key=lambda row: (
                -computed[row["id"]].factors["severity"]["normalizedValue"],
                row["id"],
            ),
        ),
        "rawComplaintCount": sorted(
            active, key=lambda row: (-row["data"].total_reports, row["id"])
        ),
        "proposed": proposed,
    }
    measured = {
        name: metrics([row["id"] for row in order], active) for name, order in orders.items()
    }
    return measured, [row["id"] for row in proposed], round(median(times), 4)


def main():
    rows = dataset()
    report = {
        "dataset": "fictional-priority-rubric-v1",
        "incidents": len(rows),
        "labelPolicy": "Fictional rubric: verified hazard=4; serious defect/essential access=3; "
        "significant or uncertain=2; minor=1; resolved=0 excluded. No real expert labels.",
        "selection": "Specified default weights retained; no held-out optimization",
        "splits": {},
    }
    for split in ("tuning", "heldOut"):
        selected = [row for row in rows if row["split"] == split]
        measured, baseline, duration = evaluate(selected)
        sensitivity = {}
        for name, weights in {
            "A": (0.5, 0.25, 0.15, 0.1),
            "B": (0.35, 0.30, 0.20, 0.15),
            "C": (0.4, 0.2, 0.2, 0.2),
        }.items():
            config = PriorityConfig(weights=weights)
            results, order, _ = evaluate(selected, config)
            previous = {identity: index for index, identity in enumerate(baseline)}
            changes = sorted(
                (
                    (identity, abs(previous[identity] - index))
                    for index, identity in enumerate(order)
                ),
                key=lambda row: -row[1],
            )
            sensitivity[name] = {
                "configVersion": config.version,
                "weights": weights,
                "metrics": results["proposed"],
                "maxRankShift": max(shift for _, shift in changes),
                "largestChanges": changes[:5],
            }
        perturbed = [
            row
            | {
                "data": replace(
                    row["data"],
                    severity=replace(
                        row["data"].severity, score=min(10, (row["data"].severity.score or 3) + 0.1)
                    ),
                )
            }
            for row in selected
        ]
        _, perturbed_order, _ = evaluate(perturbed)
        positions = {identity: index for index, identity in enumerate(baseline)}
        shifts = [
            abs(positions[identity] - index) for index, identity in enumerate(perturbed_order)
        ]
        report["splits"][split] = {
            "total": len(selected),
            "active": len(baseline),
            "baselines": measured,
            "medianEngineMs": duration,
            "weightSensitivity": sensitivity,
            "severityPlusPointOne": {
                "meanRankShift": round(mean(shifts), 4),
                "maxRankShift": max(shifts),
            },
        }
    report["limitations"] = (
        "Repeated synthetic templates/rubric references, not independent or city-scale validation. "
        "Low reporting is not low importance; distinct accounts may be one human. "
        "No weights changed automatically."
    )
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

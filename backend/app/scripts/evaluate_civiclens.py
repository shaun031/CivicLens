"""One offline, reproducible evaluation entry point. Writes only to a fresh output folder."""

import argparse
import hashlib
import json
import platform
import random
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter

from app.algorithms.clustering_evaluation_data import dataset as clustering_data
from app.algorithms.department_assignment.officer_allocator import recommend
from app.algorithms.department_assignment.routing_engine import route
from app.algorithms.duplicate_detection.candidate_selection import ACTIVE_STATUSES
from app.algorithms.duplicate_detection.config import MatchingConfig
from app.algorithms.duplicate_detection.evaluation_data import dataset
from app.algorithms.duplicate_detection.matching_engine import match
from app.algorithms.duplicate_detection.models import Classification
from app.algorithms.priority_scoring.config import PriorityConfig
from app.algorithms.priority_scoring.evaluation_data import dataset as priority_data
from app.scripts.evaluate_matching import image_signal, metrics

SEED = 13


def json_value(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported evaluation value: {type(value).__name__}")


def family_interval(rows, method, repeats=500):
    """Percentile cluster bootstrap: resample families, not dependent within-family variants."""
    families = sorted({r["group"] for r in rows})
    if not families:
        return None
    rng, samples = random.Random(SEED), []
    grouped = {family: [r for r in rows if r["group"] == family] for family in families}
    for _ in range(repeats):
        sample = [r for family in rng.choices(families, k=len(families)) for r in grouped[family]]
        samples.append(metrics([r["label"] for r in sample], [r[method] for r in sample])["f1"])
    samples.sort()
    return {
        "method": "500 seeded family-cluster bootstrap percentile draws, descriptive only",
        "f1Lower": samples[int(0.025 * repeats)],
        "f1Upper": samples[int(0.975 * repeats)],
        "families": len(families),
    }


def matching_supplement():
    config, rows, times = MatchingConfig(), [], []
    images = {key: image_signal(key) for key in {p.images for p in dataset()}}
    for pair in dataset():
        if pair.split != "evaluation" or pair.label == "UNCERTAIN":
            continue
        start = perf_counter()
        result = match(pair.first, pair.second, config, images[pair.images])
        times.append((perf_counter() - start) * 1000)
        eligible = (
            result.categoryCompatibility != "INCOMPATIBLE"
            and result.distanceMeters
            <= min(config.radius(pair.first.category), config.radius(pair.second.category))
            and pair.second.status in ACTIVE_STATUSES
        )
        image = images[pair.images].score
        rows.append(
            {
                "id": pair.id,
                "group": pair.group,
                "label": pair.label,
                "imageAvailable": image is not None,
                "geographic": eligible and result.geographicScore >= 0.8,
                "text": eligible and result.textScore >= 0.8,
                "image": eligible and image is not None and image >= 0.8,
                "geographicText": eligible
                and (result.geographicScore + result.textScore) / 2 >= 0.8,
                "proposed": result.classification == Classification.STRONG_CANDIDATE,
                "score": result.combinedScore,
            }
        )
    strategies = ("geographic", "text", "image", "geographicText", "proposed")
    strata = {}
    for name, selected in {
        "all": rows,
        "imageAvailable": [r for r in rows if r["imageAvailable"]],
        "imageMissing": [r for r in rows if not r["imageAvailable"]],
    }.items():
        strata[name] = {
            "pairs": len(selected),
            "methods": {
                m: metrics([r["label"] for r in selected], [r[m] for r in selected])
                for m in strategies
            },
        }
    return {
        "heldOutStrata": strata,
        "falsePositiveExamples": [r for r in rows if r["proposed"] and r["label"] != "DUPLICATE"],
        "proposedF1Interval": family_interval(rows, "proposed"),
        "medianPairEngineMs": round(median(times), 4),
        "candidateRecallAtK": {
            "status": "NOT_VERIFIED",
            "reason": "Pair-labelled families have no independently labelled retrieval corpus. "
            "Do not invent rank relevance for unrelated synthetic pairs.",
        },
        "policy": "All five baselines use the SAME category, lifecycle and radius gate. "
        "Image-only abstention on missing images is counted as negative; strata disclose it. "
        "This is pair-engine latency, not image decode or indexed retrieval latency.",
    }


def routing_experiment():
    """Explicit synthetic responsibilities, not learned ground truth or productivity claims."""
    categories = {
        "POTHOLE": "ROAD",
        "DAMAGED_ROAD": "ROAD",
        "GARBAGE": "SANITATION",
        "DRAINAGE": "DRAINAGE",
        "BROKEN_STREETLIGHT": "ELECTRICAL",
        "PUBLIC_PROPERTY_DAMAGE": "PUBLIC_WORKS",
    }
    departments = [
        {"id": v, "code": v, "active": True, "areas": []} for v in sorted(set(categories.values()))
    ]
    departments.append({"id": "REVIEW", "code": "GENERAL_REVIEW", "active": True, "areas": []})
    rules = [
        {"category": k, "departmentId": v, "active": True, "precedence": 10}
        for k, v in categories.items()
    ]
    cases = [(c, departments, rules, expected, False) for c, expected in categories.items()]
    cases += [
        ("OTHER", departments, rules, "REVIEW", True),
        (
            "POTHOLE",
            [d | {"active": False} if d["id"] == "ROAD" else d for d in departments],
            rules,
            "REVIEW",
            True,
        ),
        (
            "POTHOLE",
            departments,
            rules
            + [
                {
                    "category": "POTHOLE",
                    "departmentId": "SANITATION",
                    "active": True,
                    "precedence": 10,
                }
            ],
            "REVIEW",
            True,
        ),
        (
            "POTHOLE",
            [
                d | {"areas": [{"south": 0, "west": 0, "north": 1, "east": 1}]}
                if d["id"] == "ROAD"
                else d
                for d in departments
            ],
            rules,
            "REVIEW",
            True,
        ),
    ]
    outputs, timings = [], []
    for category, depts, selected_rules, expected, review in cases:
        start = perf_counter()
        value = route(category, 12.97, 77.59, depts, selected_rules)
        timings.append((perf_counter() - start) * 1000)
        outputs.append(
            {
                "category": category,
                "expected": expected,
                "selected": value["departmentId"],
                "review": value["review"],
                "correct": value["departmentId"] == expected and value["review"] == review,
                "ruleVersion": value["ruleVersion"],
            }
        )
    base = {
        "active": True,
        "eligibleAccount": True,
        "availability": "AVAILABLE",
        "areas": [],
        "capacity": 20,
        "workload": 0,
    }
    officers = [
        base | {"officerId": "a"},
        base | {"officerId": "b"},
        base | {"officerId": "inactive", "active": False},
        base | {"officerId": "leave", "availability": "ON_LEAVE"},
        base | {"officerId": "full", "workload": 20},
    ]
    allocated = []
    for _ in range(10):
        ranked = recommend(officers, 2, 12.97, 77.59)["ranked"]
        chosen = ranked[0]["officerId"]
        allocated.append(chosen)
        officers = [
            o | {"workload": o["workload"] + 2} if o["officerId"] == chosen else o for o in officers
        ]
    return {
        "datasetVersion": "explicit-routing-fixtures-v1",
        "cases": outputs,
        "routingAccuracy": sum(r["correct"] for r in outputs) / len(outputs),
        "manualReviewRate": sum(r["review"] for r in outputs) / len(outputs),
        "routingMedianMs": round(median(timings), 4),
        "allocationSimulation": {
            "assignments": allocated,
            "invalidAssignments": sum(v not in ("a", "b") for v in allocated),
            "eligibleRecommendationRate": sum(v in ("a", "b") for v in allocated) / 10,
            "beforeEligibleWorkload": {"a": 0, "b": 0},
            "afterEligibleWorkload": {
                o["officerId"]: o["workload"] for o in officers if o["officerId"] in ("a", "b")
            },
        },
        "limitations": "Constructed responsibilities and serial simulated allocation only; "
        "repository concurrency/history are tested separately, no field ground truth.",
    }


def run_module(name):
    started = perf_counter()
    process = subprocess.run(
        [sys.executable, "-m", "app.scripts." + name],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
    )
    return {
        "elapsedSeconds": round(perf_counter() - started, 3),
        "result": json.loads(process.stdout),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory; never overwritten"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    data = {"matching": dataset(), "clustering": clustering_data(), "priority": priority_data()}
    serialized = json.dumps(data, default=json_value, sort_keys=True, allow_nan=False)
    (args.output / "datasets.json").write_text(serialized, encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    sources = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in (root / "algorithms", root / "analytics", root / "scripts")
        for p in sorted(folder.rglob("*.py"))
    }
    report = {
        "evaluationDate": datetime.now(UTC).isoformat(),
        "version": "phase13-evaluation-v1",
        "seed": SEED,
        "python": platform.python_version(),
        "datasetSizes": {key: len(value) for key, value in data.items()},
        "datasetSha256": hashlib.sha256(serialized.encode()).hexdigest(),
        "sourceSha256": sources,
        "matchingConfig": asdict(MatchingConfig()),
        "priorityConfig": asdict(PriorityConfig()),
        "results": {},
    }
    for name in (
        "evaluate_matching",
        "evaluate_clustering",
        "evaluate_priority_model",
        "evaluate_intelligence",
    ):
        report["results"][name] = run_module(name)
    report["matchingSupplement"] = matching_supplement()
    report["routing"] = routing_experiment()
    report["limitations"] = [
        "Synthetic families/templates are dependent; no real independent expert or field labels.",
        "Specified defaults retained, no optimization on held-out families. Priority templates "
        "repeat across groups; their split is not independent out-of-template validation.",
        "Recurrence and repair policy simulations have no held-out split; not deployed decisions.",
        "Bootstrap only describes this small synthetic family collection; not city uncertainty.",
        "Image viewpoint robustness and retrieval Recall@K need a separate labelled corpus.",
        "Latencies vary by hardware; these are not AWS or citizen-service guarantees.",
    ]
    (args.output / "results.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    lines = [
        "# CivicLens reproducible evaluation",
        "",
        report["evaluationDate"],
        "",
        "Measured results: `results.json`; matching/clustering/priority inputs: `datasets.json`.",
        "Other synthetic fixtures are code-defined; evaluator source hashes are recorded.",
        "",
        "## Dataset sizes",
        "",
        json.dumps(report["datasetSizes"]),
        "",
        "## Matching held-out baselines",
        "",
        "```json",
        json.dumps(report["matchingSupplement"]["heldOutStrata"], indent=2),
        "```",
        "",
        "## Clustering held-out",
        "",
        "```json",
        json.dumps(report["results"]["evaluate_clustering"]["result"]["heldOut"], indent=2),
        "```",
        "",
        "## Priority held-out baselines",
        "",
        "```json",
        json.dumps(
            report["results"]["evaluate_priority_model"]["result"]["splits"]["heldOut"][
                "baselines"
            ],
            indent=2,
        ),
        "```",
        "",
        "## Routing and allocation",
        "",
        "```json",
        json.dumps(report["routing"], indent=2),
        "```",
        "",
        "## Recurrence, repair and fairness sensitivity",
        "",
        "```json",
        json.dumps(report["results"]["evaluate_intelligence"]["result"], indent=2),
        "```",
        "",
        "## Limitations",
        "",
        *["- " + v for v in report["limitations"]],
    ]
    (args.output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(args.output.resolve()),
                "datasetSizes": report["datasetSizes"],
            }
        )
    )


if __name__ == "__main__":
    main()

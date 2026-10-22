"""Reproducible offline synthetic evaluation. Numbers are measurements, not field validation."""

import io
import json
from collections import Counter
from dataclasses import replace

from PIL import Image

from app.algorithms.duplicate_detection.candidate_selection import ACTIVE_STATUSES
from app.algorithms.duplicate_detection.config import MatchingConfig
from app.algorithms.duplicate_detection.evaluation_data import dataset
from app.algorithms.duplicate_detection.image_similarity import compare, fingerprint
from app.algorithms.duplicate_detection.matching_engine import match
from app.algorithms.duplicate_detection.models import Classification


def synthetic_image(seed=0, size=(80, 60)) -> bytes:
    image = Image.new("RGB", size)
    image.putdata(
        [
            (
                (x * 17 + y * 7 + seed * 43) % 256,
                (x * 3 + y * 19 + seed * 17) % 256,
                (x * 11 + y * 5 + seed * 23) % 256,
            )
            for y in range(size[1])
            for x in range(size[0])
        ]
    )
    data = io.BytesIO()
    image.save(data, "JPEG")
    return data.getvalue()


def image_signal(scenario):
    if scenario == "missing":
        return compare([], [])
    first = fingerprint(synthetic_image())
    second = fingerprint(
        b"corrupt"
        if scenario == "corrupt"
        else synthetic_image(3 if scenario == "different" else 0)
    )
    if scenario == "resized":
        with Image.open(io.BytesIO(synthetic_image())) as image:
            output = io.BytesIO()
            image.resize((40, 30)).save(output, "JPEG")
            second = fingerprint(output.getvalue())
    return compare([first] if first else [], [second] if second else [])


def metrics(labels, predictions):
    counts = Counter()
    for label, prediction in zip(labels, predictions, strict=True):
        positive = label == "DUPLICATE"
        counts[
            "TP" if positive and prediction else "FN" if positive else "FP" if prediction else "TN"
        ] += 1
    tp, fp, fn = counts["TP"], counts["FP"], counts["FN"]
    precision, recall = tp / (tp + fp) if tp + fp else 0, tp / (tp + fn) if tp + fn else 0
    return {
        "TP": tp,
        "FP": fp,
        "TN": counts["TN"],
        "FN": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0,
    }


def evaluate(split, config=None, threshold=None):
    config = config or MatchingConfig()
    rows, uncertain = [], Counter()
    images = {
        key: image_signal(key) for key in ("missing", "same", "resized", "different", "corrupt")
    }
    if threshold is not None:
        config = replace(
            config, strong_threshold=threshold, review_threshold=min(0.59, threshold - 0.01)
        )
    for pair in dataset():
        if pair.split != split:
            continue
        result = match(pair.first, pair.second, config, images[pair.images])
        if pair.label == "UNCERTAIN":
            uncertain[result.classification] += 1
            continue
        eligible = (
            result.categoryCompatibility != "INCOMPATIBLE"
            and result.distanceMeters
            <= min(config.radius(pair.first.category), config.radius(pair.second.category))
            and pair.second.status in ACTIVE_STATUSES
        )
        cutoff = config.strong_threshold
        rows.append(
            (
                pair.label,
                {
                    "geographic_only": eligible and result.geographicScore >= cutoff,
                    "text_only": eligible and result.textScore >= cutoff,
                    "geographic_text": eligible
                    and (result.geographicScore + result.textScore) / 2 >= cutoff,
                    "proposed": result.classification == Classification.STRONG_CANDIDATE,
                },
            )
        )
    return {
        "labeledBinaryPairs": len(rows),
        "uncertainClassifications": dict(uncertain),
        "strategies": {
            name: metrics([row[0] for row in rows], [row[1][name] for row in rows])
            for name in ("geographic_only", "text_only", "geographic_text", "proposed")
        },
    }


def report():
    thresholds = [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
    sensitivity = {
        str(value): {
            split: evaluate(split, threshold=value)["strategies"]["proposed"]
            for split in ("tuning", "evaluation")
        }
        for value in thresholds
    }
    return {
        "datasetVersion": "synthetic-families-v1",
        "pairs": len(dataset()),
        "groups": 24,
        "configVersion": MatchingConfig().version,
        "chosenThreshold": 0.80,
        "selectionReason": "Retain conservative prototype defaults; synthetic family results "
        "are not sufficient to optimize real-world policy. No held-out tuning.",
        "tuning": evaluate("tuning"),
        "heldOut": evaluate("evaluation"),
        "thresholdSensitivity": sensitivity,
        "radiusSensitivity": {
            str(radius): evaluate(
                "evaluation",
                replace(
                    MatchingConfig(),
                    default_radius=radius,
                    streetlight_radius=radius,
                    pothole_radius=radius,
                    road_radius=radius,
                    drainage_radius=radius,
                ),
            )
            for radius in (30, 50, 75)
        },
        "limitations": "Synthetic pair evaluation; all baselines use identical category/lifecycle/"
        "radius eligibility. No production probability calibration, rank Recall@K or field claims.",
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2))

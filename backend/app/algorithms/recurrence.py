"""Uncalibrated recurrence evidence, deliberately separate from duplicate classification."""

import hashlib
import json
import math

from app.algorithms.duplicate_detection.category_compatibility import compatibility
from app.algorithms.duplicate_detection.geographic_similarity import proximity
from app.algorithms.duplicate_detection.models import TextRecord
from app.algorithms.duplicate_detection.text_similarity import TEXT_ENGINE, contradictions
from app.analytics.metrics import stamp


def evaluate(
    previous, current, verified_at, *, radius=150, horizon=730, threshold=0.65, image=None
):
    days = (
        stamp(current.get("first_reported_at", current["created_at"])) - stamp(verified_at)
    ).total_seconds() / 86400
    distance, geo = proximity(
        previous["latitude"],
        previous["longitude"],
        current["latitude"],
        current["longitude"],
        radius,
    )
    first = TextRecord(previous["canonical_title"], previous["canonical_description"])
    second = TextRecord(current["canonical_title"], current["canonical_description"])
    text = TEXT_ENGINE.compare(first, second)
    conflicts = list(contradictions(first, second))
    compatible = compatibility(previous["category"], current["category"], False) != "INCOMPATIBLE"
    valid = compatible and 0 < days <= horizon and distance <= radius
    signals = {"geographic": geo, "text": text, "time": math.exp(-max(0, days) / 365)}
    weights = {"geographic": 0.4, "text": 0.45, "time": 0.15}
    if image is not None:
        signals["image"] = image
        weights = {"geographic": 0.3, "text": 0.35, "time": 0.15, "image": 0.2}
    score = sum(weights[k] * v for k, v in signals.items()) if valid else 0
    version = hashlib.sha256(
        json.dumps([radius, horizon, threshold, TEXT_ENGINE.version], sort_keys=True).encode()
    ).hexdigest()[:16]
    return {
        "score": round(score, 6),
        "distance": distance,
        "days": days,
        "signals": signals,
        "weights": weights,
        "categoryCompatible": compatible,
        "state": "POTENTIAL_RECURRENCE"
        if valid and not conflicts and score >= threshold
        else "INSUFFICIENT_EVIDENCE",
        "eligible": valid,
        "algorithmVersion": f"recurrence-v1-{version}",
        "limitations": [
            "Evidence score is not a calibrated probability",
            (
                "Nearby defects may be different physical objects; "
                "administrator identity review required"
            ),
            "No verified asset identifier supplied",
            "Photographs are optional; viewpoint limits apply",
        ],
        "contradictions": conflicts,
    }

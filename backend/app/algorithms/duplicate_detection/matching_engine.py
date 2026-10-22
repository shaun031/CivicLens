from time import perf_counter

from app.algorithms.duplicate_detection.candidate_selection import ACTIVE_STATUSES
from app.algorithms.duplicate_detection.category_compatibility import compatibility
from app.algorithms.duplicate_detection.confidence_scoring import band, fuse
from app.algorithms.duplicate_detection.config import MatchingConfig
from app.algorithms.duplicate_detection.geographic_similarity import proximity
from app.algorithms.duplicate_detection.models import (
    Classification,
    ImageSignal,
    MatchInput,
    MatchResult,
    canonical_pair,
)
from app.algorithms.duplicate_detection.text_similarity import (
    TEXT_ENGINE,
    contradictions,
    meaningful,
)


def match(
    first: MatchInput,
    second: MatchInput,
    config: MatchingConfig,
    image: ImageSignal | None = None,
) -> MatchResult:
    image = image or ImageSignal()
    identity, left, right = canonical_pair(first.complaint_id, second.complaint_id)
    started = perf_counter()
    radius = min(config.radius(first.category), config.radius(second.category))
    distance, location = proximity(
        first.latitude, first.longitude, second.latitude, second.longitude, radius
    )
    geo_ms = (perf_counter() - started) * 1000
    relation = compatibility(first.category, second.category, config.allow_related_categories)
    started = perf_counter()
    text = TEXT_ENGINE.compare(first.text, second.text)
    text_ms = (perf_counter() - started) * 1000
    started = perf_counter()
    score, weights = fuse(location, text, image.score)
    classification = band(score, config.strong_threshold, config.review_threshold)
    indicators = list(image.indicators)
    conflict = contradictions(first.text, second.text)
    if relation == "INCOMPATIBLE":
        classification = Classification.CATEGORY_MISMATCH
    elif distance > radius + 1e-7:
        classification = Classification.OUTSIDE_SEARCH_RADIUS
    elif first.status not in ACTIVE_STATUSES or second.status not in ACTIVE_STATUSES:
        classification = Classification.INSUFFICIENT_EVIDENCE
        indicators.append(
            "Historical/resolved/rejected complaint: not an active duplicate recommendation"
        )
    elif not meaningful(first.text) or not meaningful(second.text) or text < config.minimum_text:
        classification = Classification.INSUFFICIENT_EVIDENCE
        indicators.append(
            "Insufficient meaningful text; proximity/photo alone cannot confirm a match"
        )
    elif conflict:
        classification = Classification.REVIEW_REQUIRED
        indicators.extend(conflict)
    elif classification == Classification.STRONG_CANDIDATE and (
        distance > config.distinct_object_distance
        or text < config.strong_text
        or relation != "SAME_CATEGORY"
    ):
        classification = Classification.REVIEW_REQUIRED
        indicators.append(
            "Distinct nearby objects or related/unknown categories require manual review"
        )
    explanation = (
        f"Category: {relation}; distance {distance:.2f} m / {radius:g} m radius.",
        f"Geographic {location:.3f}; TF-IDF text {text:.3f}; "
        + ("image unavailable." if image.score is None else f"dHash image {image.score:.3f}."),
        f"Weighted similarity index {score * 100:.1f}/100, not a probability; {classification}.",
        "Suggestion only: no merging, incident assignment or priority changes.",
    )
    return MatchResult(
        identity,
        left,
        right,
        distance,
        location,
        text,
        image.score,
        score,
        weights,
        relation,
        classification,
        explanation,
        tuple(indicators),
        "haversine+tfidf-word-char+dhash64",
        TEXT_ENGINE.version,
        config.version,
        {"geographicMs": geo_ms, "textMs": text_ms, "fusionMs": (perf_counter() - started) * 1000},
    )


def rank(results: list[MatchResult]) -> list[MatchResult]:
    return sorted(
        results,
        key=lambda row: (-row.combinedScore, -row.textScore, row.distanceMeters, row.candidateId),
    )

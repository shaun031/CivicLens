from app.algorithms.duplicate_detection.models import Classification


def fuse(location: float, text: float, image: float | None) -> tuple[float, dict[str, float]]:
    import math

    if any(
        not math.isfinite(score) or not 0 <= score <= 1
        for score in (location, text) + (() if image is None else (image,))
    ):
        raise ValueError("Scores must be finite values between zero and one")
    weights = {"geographic": 0.4, "text": 0.4, "image": 0.2 if image is not None else 0.0}
    total = sum(weights.values())
    weights = {key: value / total for key, value in weights.items()}
    return (
        weights["geographic"] * location + weights["text"] * text + weights["image"] * (image or 0)
    ), weights


def band(score: float, strong: float, review: float) -> Classification:
    if score >= strong:
        return Classification.STRONG_CANDIDATE
    if score >= review:
        return Classification.REVIEW_REQUIRED
    return Classification.WEAK_MATCH

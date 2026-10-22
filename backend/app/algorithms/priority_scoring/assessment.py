import math

from app.algorithms.priority_scoring.models import Assessment


def finite_score(value: float, maximum: float = 10) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValueError(f"Score must be finite and within 0–{maximum}")
    return float(value)


def assessed_factor(assessment: Assessment, epoch: int, default: float) -> tuple[float, str]:
    if assessment.status not in ("UNASSESSED", "PROVISIONAL", "VERIFIED"):
        raise ValueError("Invalid assessment status")
    if assessment.score is not None:
        finite_score(assessment.score)
    if assessment.epoch != epoch and assessment.status != "UNASSESSED":
        return default, "NEEDS_REVIEW"
    if assessment.status == "UNASSESSED" or assessment.score is None:
        return default, "PROVISIONAL"
    if assessment.status == "VERIFIED":
        if len(assessment.reason.strip()) < 10 or not assessment.evidence or not assessment.actor:
            raise ValueError("Verified assessment needs an actor, evidence and reason")
    elif assessment.score > 6:
        raise ValueError("Unverified administrative assessment is capped at six")
    return assessment.score, assessment.status

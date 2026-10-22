from dataclasses import dataclass

from app.algorithms.duplicate_detection.category_compatibility import compatibility
from app.algorithms.duplicate_detection.config import MatchingConfig
from app.algorithms.duplicate_detection.geographic_similarity import proximity
from app.algorithms.duplicate_detection.models import MatchInput

ACTIVE_STATUSES = ("SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "IN_PROGRESS")


@dataclass(frozen=True)
class Selection:
    items: tuple[MatchInput, ...]
    truncated: bool
    retrieved: int


def select(
    source: MatchInput,
    candidates: list[MatchInput],
    config: MatchingConfig,
    truncated: bool = False,
) -> Selection:
    if source.status not in ACTIVE_STATUSES:
        return Selection((), False, len(candidates))
    selected = []
    for item in candidates:
        if item.complaint_id == source.complaint_id or item.status not in ACTIVE_STATUSES:
            continue
        if (
            compatibility(source.category, item.category, config.allow_related_categories)
            == "INCOMPATIBLE"
        ):
            continue
        radius = min(config.radius(source.category), config.radius(item.category))
        distance, _ = proximity(
            source.latitude, source.longitude, item.latitude, item.longitude, radius
        )
        if distance <= radius + 1e-7:
            selected.append((distance, item.complaint_id, item))
    selected.sort(key=lambda row: (row[0], row[1]))
    return Selection(
        tuple(row[2] for row in selected[: config.candidate_limit]),
        truncated or len(selected) > config.candidate_limit,
        len(candidates),
    )

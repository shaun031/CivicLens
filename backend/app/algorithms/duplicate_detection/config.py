from dataclasses import asdict, dataclass
from hashlib import sha256
from json import dumps

from app.models.complaint import Category


@dataclass(frozen=True)
class MatchingConfig:
    default_radius: float = 50
    streetlight_radius: float = 30
    pothole_radius: float = 50
    road_radius: float = 75
    drainage_radius: float = 75
    candidate_limit: int = 100
    strong_threshold: float = 0.80
    review_threshold: float = 0.60
    minimum_text: float = 0.35
    strong_text: float = 0.75
    distinct_object_distance: float = 10
    allow_related_categories: bool = True
    algorithm_version: str = "matching-v1"

    def __post_init__(self) -> None:
        import math

        radii = (
            self.default_radius,
            self.streetlight_radius,
            self.pothole_radius,
            self.road_radius,
            self.drainage_radius,
        )
        if any(not math.isfinite(radius) or not 5 <= radius <= 500 for radius in radii):
            raise ValueError("Matching radii must be finite, between 5 and 500 metres")
        if not 1 <= self.candidate_limit <= 500:
            raise ValueError("Candidate limit must be between 1 and 500")
        if not 0 <= self.review_threshold < self.strong_threshold <= 1:
            raise ValueError("Invalid decision thresholds")
        if not 0 <= self.minimum_text <= self.strong_text <= 1:
            raise ValueError("Invalid minimum text evidence")

    def radius(self, category: Category) -> float:
        return {
            Category.BROKEN_STREETLIGHT: self.streetlight_radius,
            Category.POTHOLE: self.pothole_radius,
            Category.DAMAGED_ROAD: self.road_radius,
            Category.DRAINAGE: self.drainage_radius,
        }.get(category, self.default_radius)

    @property
    def version(self) -> str:
        values = {
            key: float(value) if type(value) in (int, float) else value
            for key, value in asdict(self).items()
        }
        digest = sha256(dumps(values, sort_keys=True).encode()).hexdigest()[:12]
        return f"{self.algorithm_version}-{digest}"

    @classmethod
    def from_settings(cls, settings):
        return cls(
            default_radius=settings.matching_radius_meters,
            streetlight_radius=settings.matching_streetlight_radius,
            pothole_radius=settings.matching_pothole_radius,
            road_radius=settings.matching_road_radius,
            drainage_radius=settings.matching_drainage_radius,
            candidate_limit=settings.matching_candidate_limit,
            strong_threshold=settings.matching_strong_threshold,
            review_threshold=settings.matching_review_threshold,
        )

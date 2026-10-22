"""Cluster-level checks reuse Phase 6 comparisons. No graph-component auto-merging."""

from dataclasses import dataclass

from app.algorithms.duplicate_detection.category_compatibility import compatibility
from app.algorithms.duplicate_detection.config import MatchingConfig
from app.algorithms.duplicate_detection.models import MatchResult
from app.models.complaint import Category
from app.models.incident import Member
from app.utils.geography import haversine


@dataclass(frozen=True)
class ClusteringConfig:
    mode: str = "REVIEW_ONLY"
    auto_threshold: float = 0.90
    auto_span: float = 10
    manual_span: float = 75
    max_members: int = 30
    target_limit: int = 5
    require_images: bool = True

    def __post_init__(self):
        import math

        if self.mode not in ("REVIEW_ONLY", "CONSERVATIVE_AUTO_LINK"):
            raise ValueError("Unknown clustering mode")
        if (
            not math.isfinite(self.auto_threshold)
            or not 0.90 <= self.auto_threshold <= 1
            or not math.isfinite(self.auto_span)
            or not 1 <= self.auto_span <= 10
            or not math.isfinite(self.manual_span)
            or not 10 <= self.manual_span <= 100
            or not 2 <= self.max_members <= 30
            or not 1 <= self.target_limit <= 10
        ):
            raise ValueError("Invalid bounded clustering configuration")

    @classmethod
    def from_settings(cls, settings):
        return cls(
            settings.clustering_mode,
            settings.clustering_auto_threshold,
            settings.clustering_auto_span_meters,
            settings.clustering_manual_span_meters,
            settings.clustering_max_members,
            settings.clustering_target_limit,
            settings.clustering_require_images,
        )


def physical_cohesion(
    members: list[Member],
    config: ClusteringConfig,
    matching: MatchingConfig,
    automatic: bool = False,
) -> tuple[bool, str]:
    if not members or len(members) > config.max_members:
        return False, "Cluster exceeds the bounded full-member validation limit"
    for index, first in enumerate(members):
        a = first.complaint
        for second in members[index + 1 :]:
            b = second.complaint
            if compatibility(a.category, b.category) == "INCOMPATIBLE":
                return False, "Incompatible infrastructure categories"
            span = min(
                matching.radius(a.category),
                matching.radius(b.category),
                config.auto_span if automatic else config.manual_span,
            )
            if haversine(a.latitude, a.longitude, b.latitude, b.longitude) > span + 1e-7:
                return False, "Full-cluster spatial span exceeded; no transitive bridge allowed"
    return True, "Every member pair passed category and bounded spatial checks"


def automatic_evidence(result: MatchResult, config: ClusteringConfig) -> tuple[bool, str]:
    if result.classification != "STRONG_CANDIDATE":
        return False, "Phase 6 did not classify the pair as a strong candidate"
    if result.categoryCompatibility != "SAME_CATEGORY":
        return False, "Automatic links require the same known infrastructure category"
    if result.combinedScore < config.auto_threshold or result.textScore < 0.85:
        return False, "Automatic similarity/text evidence floor not reached"
    if result.distanceMeters > config.auto_span:
        return False, "Nearby distinct objects need manual review"
    if config.require_images and (result.imageScore is None or result.imageScore < 0.90):
        return False, "Automatic policy requires supporting informative image evidence"
    return True, "Strict independent text/location/image checks passed; still not proof"


def eligible_category(category: Category) -> bool:
    return category != Category.OTHER

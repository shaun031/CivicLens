from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from uuid import UUID, uuid5

from app.models.complaint import Category


class Classification(StrEnum):
    STRONG_CANDIDATE = "STRONG_CANDIDATE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    WEAK_MATCH = "WEAK_MATCH"
    CATEGORY_MISMATCH = "CATEGORY_MISMATCH"
    OUTSIDE_SEARCH_RADIUS = "OUTSIDE_SEARCH_RADIUS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ReviewStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    DISMISSED = "DISMISSED"
    REVIEWED_POSSIBLE_DUPLICATE = "REVIEWED_POSSIBLE_DUPLICATE"


@dataclass(frozen=True)
class TextRecord:
    title: str
    description: str


@dataclass(frozen=True)
class MatchInput:
    complaint_id: str
    category: Category
    latitude: float
    longitude: float
    text: TextRecord
    status: str = "SUBMITTED"

    def __post_init__(self) -> None:
        UUID(self.complaint_id)
        if not isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise ValueError("Invalid latitude")
        if not isfinite(self.longitude) or not -180 <= self.longitude <= 180:
            raise ValueError("Invalid longitude")


@dataclass(frozen=True)
class ImageSignal:
    score: float | None = None
    indicators: tuple[str, ...] = ("Image evidence unavailable",)
    comparisons: int = 0

    def __post_init__(self) -> None:
        if self.score is not None and (not isfinite(self.score) or not 0 <= self.score <= 1):
            raise ValueError("Invalid image similarity")
        if not 0 <= self.comparisons <= 4:
            raise ValueError("Too many image comparisons")


@dataclass(frozen=True)
class MatchResult:
    candidateId: str
    sourceComplaintId: str
    possibleDuplicateId: str
    distanceMeters: float
    geographicScore: float
    textScore: float
    imageScore: float | None
    combinedScore: float
    effectiveWeights: dict[str, float]
    categoryCompatibility: str
    classification: Classification
    explanation: tuple[str, ...]
    indicators: tuple[str, ...]
    method: str
    modelVersion: str
    configVersion: str
    timings: dict[str, float] = field(default_factory=dict)


def canonical_pair(first: str, second: str) -> tuple[str, str, str]:
    first, second = sorted((str(UUID(first)), str(UUID(second))))
    if first == second:
        raise ValueError("Cannot compare a complaint with itself")
    identity = str(uuid5(UUID("b5dd0a5c-c915-41de-8de5-167bfc12c3fe"), f"{first}:{second}"))
    return identity, first, second

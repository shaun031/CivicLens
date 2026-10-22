from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Assessment:
    score: float | None = None
    status: str = "UNASSESSED"
    reason: str = ""
    evidence: tuple[str, ...] = ()
    actor: str | None = None
    assessed_at: str | None = None
    epoch: int = 0


@dataclass(frozen=True)
class PriorityInput:
    incident_id: str
    incident_version: int
    status: str
    first_reported_at: str
    unique_reporters: int
    total_reports: int
    now: datetime
    severity: Assessment = field(default_factory=Assessment)
    impact: Assessment = field(default_factory=Assessment)
    epoch: int = 0
    open_since: str | None = None
    frozen_seconds: float = 0
    age_quality: str = "APPROXIMATE_BASELINE"
    reported_high: bool = False
    danger_reported: bool = False
    hazard: dict = field(default_factory=dict)
    override: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PriorityResult:
    incident_id: str
    incident_version: int
    calculated_score: float
    calculated_band: str
    effective_score: float
    priority_band: str
    assessment_status: str
    factors: dict
    urgent_hazard: bool
    hazard_status: str
    override_status: str
    unresolved_seconds: float
    unresolved_days: float
    explanation: tuple[str, ...]
    review_flags: tuple[str, ...]
    calculated_at: str
    algorithm_version: str
    config: dict

import hashlib
import json
import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PriorityConfig:
    weights: tuple[float, float, float, float] = (0.40, 0.25, 0.20, 0.15)
    reporter_saturation: int = 30
    aging_days: float = 30
    bands: tuple[float, float, float] = (40, 60, 80)
    provisional_severity: float = 3
    provisional_impact: float = 3
    refresh_seconds: int = 3600
    algorithm: str = "priority-v1"

    def __post_init__(self):
        numbers = (
            *self.weights,
            *self.bands,
            self.aging_days,
            self.provisional_severity,
            self.provisional_impact,
        )
        if any(isinstance(v, bool) or not math.isfinite(v) for v in numbers):
            raise ValueError("Priority configuration must contain finite numbers")
        if (
            len(self.weights) != 4
            or any(w < 0 for w in self.weights)
            or not math.isclose(sum(self.weights), 1, abs_tol=1e-9)
        ):
            raise ValueError("Exactly four nonnegative priority weights must sum to one")
        if len(self.bands) != 3 or not 0 < self.bands[0] < self.bands[1] < self.bands[2] <= 100:
            raise ValueError("Priority thresholds must increase within (0,100]")
        if (
            type(self.reporter_saturation) is not int
            or self.reporter_saturation < 1
            or not 1 <= self.aging_days <= 3650
            or not 60 <= self.refresh_seconds <= 86400
            or not 0 <= self.provisional_severity <= 6
            or not 0 <= self.provisional_impact <= 6
        ):
            raise ValueError(
                "Invalid priority saturation, provisional defaults or refresh interval"
            )

        object.__setattr__(self, "weights", tuple(float(w) for w in self.weights))
        object.__setattr__(self, "bands", tuple(float(b) for b in self.bands))
        for name in ("aging_days", "provisional_severity", "provisional_impact"):
            object.__setattr__(self, name, float(getattr(self, name)))

    @property
    def version(self):
        digest = hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:12]
        return f"{self.algorithm}-{digest}"

    @classmethod
    def from_settings(cls, settings):
        return cls(
            weights=tuple(settings.priority_weights),
            bands=tuple(settings.priority_bands),
            reporter_saturation=settings.priority_reporter_saturation,
            aging_days=settings.priority_aging_days,
            refresh_seconds=settings.priority_refresh_seconds,
        )

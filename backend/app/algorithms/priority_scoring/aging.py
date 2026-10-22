import math
from datetime import UTC, datetime


def utc(value: str | datetime) -> datetime:
    parsed = (
        datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    )
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("A timezone-aware UTC-compatible timestamp is required")
    return parsed.astimezone(UTC)


def age_factor(status, now, open_since, frozen_seconds, saturation_days=30):
    now = utc(now)
    if (
        not math.isfinite(frozen_seconds)
        or frozen_seconds < 0
        or not math.isfinite(saturation_days)
        or saturation_days <= 0
    ):
        raise ValueError("Invalid unresolved interval")
    seconds, flags = frozen_seconds, []
    if status == "OPEN":
        try:
            elapsed = (now - utc(open_since)).total_seconds()
            if elapsed < 0:
                flags.append("Future unresolved start; age clamped to zero, review timestamps")
            seconds += max(0, elapsed)
        except (TypeError, ValueError, OverflowError):
            flags.append(
                "Missing or invalid unresolved start; age is unknown, not proof of no risk"
            )
    elif status not in ("RESOLVED", "MERGED", "SUPERSEDED"):
        raise ValueError("Unsupported incident lifecycle")
    return min(10, seconds / (86400 * saturation_days) * 10), seconds, flags

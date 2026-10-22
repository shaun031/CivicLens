from dataclasses import asdict
from decimal import ROUND_HALF_UP, Decimal

from app.algorithms.priority_scoring.aging import age_factor, utc
from app.algorithms.priority_scoring.assessment import assessed_factor, finite_score
from app.algorithms.priority_scoring.classification import classify
from app.algorithms.priority_scoring.config import PriorityConfig
from app.algorithms.priority_scoring.models import PriorityInput, PriorityResult
from app.algorithms.priority_scoring.reporter_weight import reporter_factor
from app.algorithms.priority_scoring.safety_rules import verified_hazard


def rounded(value, digits=2):
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


DEFAULT_CONFIG = PriorityConfig()


def calculate(data: PriorityInput, config: PriorityConfig = DEFAULT_CONFIG) -> PriorityResult:
    now = utc(data.now)
    if type(data.total_reports) is not int or data.total_reports < data.unique_reporters:
        raise ValueError("Total reports cannot be less than eligible unique reporters")
    severity, severity_status = assessed_factor(
        data.severity, data.epoch, config.provisional_severity
    )
    impact, impact_status = assessed_factor(data.impact, data.epoch, config.provisional_impact)
    reporter = reporter_factor(data.unique_reporters, config.reporter_saturation)
    aging, seconds, flags = age_factor(
        data.status, now, data.open_since, data.frozen_seconds, config.aging_days
    )
    raw_values = (severity, impact, reporter, aging)
    names = ("severity", "publicImpact", "reporters", "aging")
    statuses = (severity_status, impact_status, "ELIGIBLE_ACCOUNTS", data.age_quality)
    factors = {}
    for name, raw, weight, status in zip(names, raw_values, config.weights, statuses, strict=True):
        finite_score(raw)
        factors[name] = {
            "rawValue": data.unique_reporters
            if name == "reporters"
            else rounded(seconds / 86400, 4)
            if name == "aging"
            else data.severity.score
            if name == "severity"
            else data.impact.score,
            "normalizedValue": rounded(raw, 4),
            "weight": weight,
            "contribution": rounded(10 * weight * raw),
            "status": status,
        }
    score = rounded(
        sum(10 * w * value for w, value in zip(config.weights, raw_values, strict=True))
    )
    urgent = verified_hazard(data.hazard, data.epoch)
    if data.reported_high and severity_status != "VERIFIED":
        flags.append("Citizen HIGH reports require assessment; they do not set verified severity")
    if data.danger_reported and not urgent:
        flags.append("Possible danger reported; administrator hazard review required, not verified")
    if data.total_reports >= 3 and data.total_reports > 2 * max(1, data.unique_reporters):
        flags.append("Repeated-account reporting deduplicated; review pattern, not proof of abuse")
    if "NEEDS_REVIEW" in (severity_status, impact_status):
        flags.append("Membership changed; prior assessments require renewed review")
    if data.age_quality == "INVALID":
        flags.append("Lifecycle timestamp metadata needs review")
    if data.total_reports and not data.unique_reporters:
        flags.append(
            "No current eligible reporter support; review retained reports, not assumed unimportant"
        )
    if data.hazard.get("flag") and not urgent:
        flags.append("Prior or unverified hazard flag requires renewed administrative review")
    verified = severity_status == impact_status == "VERIFIED"
    assessment_status = "NEEDS_REVIEW" if flags else "VERIFIED" if verified else "PROVISIONAL"
    hazard = data.hazard
    hazard_status = "VERIFIED" if urgent else "NEEDS_REVIEW" if hazard.get("flag") else "NONE"
    override, effective, override_status = data.override, score, "NONE"
    if override:
        override_status = override.get("status", "NONE")
        if override_status == "ACTIVE":
            if override.get("epoch") != data.epoch:
                override_status = "REVIEW_REQUIRED"
            elif override.get("expiresAt") and utc(override["expiresAt"]) <= now:
                override_status = "EXPIRED"
            elif len(override.get("reason", "").strip()) < 10 or not override.get("createdBy"):
                raise ValueError("Override requires an administrator and reason")
            else:
                effective = rounded(finite_score(override["score"], 100))
    if urgent:
        effective = (
            100.0  # Never replace the raw formula score or let an override suppress a hazard.
        )
    explanation = (
        "Prototype operational urgency rubric, not accident probability or emergency dispatch.",
        f"Severity {severity_status.lower()}: {severity:g}/10; "
        f"public impact {impact_status.lower()}: {impact:g}/10.",
        f"{data.unique_reporters} eligible accounts among {data.total_reports} reports; "
        "accounts are not verified distinct humans.",
        f"Unresolved time {rounded(seconds / 86400, 4)} days; "
        f"scoring cap {config.aging_days:g} days; historical baseline approximate.",
        "Unknown assessments use conservative defaults, not a finding of zero risk.",
        f"Calculated {score:g}/100; effective {effective:g}/100. "
        f"Hazard: {hazard_status}; override: {override_status}.",
    )
    return PriorityResult(
        data.incident_id,
        data.incident_version,
        score,
        classify(score, config.bands),
        effective,
        classify(effective, config.bands),
        assessment_status,
        factors,
        urgent,
        hazard_status,
        override_status,
        rounded(seconds, 3),
        rounded(seconds / 86400, 4),
        explanation,
        tuple(flags),
        now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        config.version,
        asdict(config),
    )

import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.algorithms.priority_scoring.aging import age_factor
from app.algorithms.priority_scoring.assessment import finite_score
from app.algorithms.priority_scoring.classification import classify
from app.algorithms.priority_scoring.config import PriorityConfig
from app.algorithms.priority_scoring.models import Assessment, PriorityInput
from app.algorithms.priority_scoring.reporter_weight import reporter_factor
from app.algorithms.priority_scoring.scoring_engine import calculate

NOW = datetime(2026, 10, 20, tzinfo=UTC)
VERIFIED = Assessment(
    10, "VERIFIED", "Administrator verified the reported physical evidence", ("report",), "admin"
)


def data(**kwargs):
    return replace(
        PriorityInput(
            "incident", 1, "OPEN", NOW.isoformat(), 1, 1, NOW, open_since=NOW.isoformat()
        ),
        **kwargs,
    )


def test_formula_bounds_deterministic_provisional_and_contributions():
    result = calculate(data())
    assert result.calculated_score == 23.54 and result.assessment_status == "PROVISIONAL"
    assert result.factors["severity"]["rawValue"] is None
    assert result.factors["severity"]["normalizedValue"] == 3
    assert calculate(data()) == result
    assert result.algorithm_version == PriorityConfig().version
    maximum = calculate(
        data(
            severity=VERIFIED,
            impact=VERIFIED,
            unique_reporters=30,
            total_reports=30,
            open_since=(NOW - timedelta(days=30)).isoformat(),
        )
    )
    assert maximum.calculated_score == 100 and maximum.priority_band == "CRITICAL"
    assert maximum.assessment_status == "VERIFIED"
    assert sum(f["contribution"] for f in maximum.factors.values()) == 100


@pytest.mark.parametrize(
    "weights",
    [
        (1, 1, 0, 0),
        (-0.1, 0.5, 0.3, 0.3),
        (0.5, 0.5),
        (math.nan, 0.25, 0.2, 0.15),
        (math.inf, 0, 0, 0),
    ],
)
def test_invalid_weight_configuration(weights):
    with pytest.raises(ValueError):
        PriorityConfig(weights=weights)


@pytest.mark.parametrize("value", [-1, 11, math.nan, math.inf, -math.inf, True])
def test_invalid_factors(value):
    with pytest.raises(ValueError):
        finite_score(value)


@pytest.mark.parametrize(
    "score,band",
    [
        (0, "LOW"),
        (39, "LOW"),
        (39.99, "LOW"),
        (40, "MEDIUM"),
        (59, "MEDIUM"),
        (59.99, "MEDIUM"),
        (60, "HIGH"),
        (79, "HIGH"),
        (79.99, "HIGH"),
        (80, "CRITICAL"),
        (100, "CRITICAL"),
    ],
)
def test_classification_boundaries(score, band):
    assert classify(score) == band


def test_custom_thresholds_and_configuration_version():
    config = PriorityConfig(bands=(20, 50, 90))
    assert classify(80, config.bands) == "HIGH"
    assert config.version != PriorityConfig().version


@pytest.mark.parametrize("count", [0, 1, 3, 5, 15, 30, 1000, 10**1000])
def test_reporter_log_factor_and_saturation(count):
    value = reporter_factor(count)
    assert 0 <= value <= 10
    assert value == (10 if count >= 30 else 10 * math.log1p(count) / math.log1p(30))


@pytest.mark.parametrize("count", [-1, 1.5, True])
def test_invalid_reporter_count(count):
    with pytest.raises(ValueError):
        reporter_factor(count)


@pytest.mark.parametrize("days,expected", [(0, 0), (1, 1 / 3), (15, 5), (30, 10), (60, 10)])
def test_aging_days(days, expected):
    factor, seconds, flags = age_factor("OPEN", NOW, (NOW - timedelta(days=days)).isoformat(), 0)
    assert factor == pytest.approx(expected) and seconds == days * 86400 and not flags


def test_resolved_reopened_future_missing_and_timezone():
    assert age_factor("RESOLVED", NOW, None, 15 * 86400)[0] == 5
    assert age_factor("OPEN", NOW, (NOW - timedelta(days=3)).isoformat(), 2 * 86400)[
        0
    ] == pytest.approx(5 / 3)
    factor, _, flags = age_factor("OPEN", NOW, (NOW + timedelta(days=1)).isoformat(), 0)
    assert factor == 0 and flags
    for invalid in (None, "invalid", "2026-10-20T00:00:00"):
        assert age_factor("OPEN", NOW, invalid, 0)[2]
    assert age_factor("OPEN", NOW, "2026-10-20T05:30:00+05:30", 0)[0] == 0
    with pytest.raises(ValueError):
        age_factor("OPEN", datetime(2026, 10, 20), NOW.isoformat(), 0)


def test_citizen_high_is_not_authoritative_and_stale_assessment_not_inherited():
    reported = calculate(data(reported_high=True, danger_reported=True))
    assert reported.factors["severity"]["normalizedValue"] == 3
    assert reported.assessment_status == "NEEDS_REVIEW" and not reported.urgent_hazard
    stale = calculate(data(severity=VERIFIED, impact=VERIFIED, epoch=1))
    assert (
        stale.factors["severity"]["normalizedValue"] == 3
        and stale.assessment_status == "NEEDS_REVIEW"
    )


@pytest.mark.parametrize(
    "assessment",
    [
        Assessment(9, "PROVISIONAL"),
        Assessment(9, "VERIFIED"),
        Assessment(9, "VERIFIED", "reason sufficient", (), "admin"),
        Assessment(3, "invalid"),
    ],
)
def test_missing_evidence_or_invalid_verification_rejected(assessment):
    with pytest.raises(ValueError):
        calculate(data(severity=assessment))


def test_hazard_separate_from_formula_cannot_be_lowered_by_override():
    hazard = {
        "flag": True,
        "status": "VERIFIED",
        "epoch": 0,
        "evidenceReferences": ["report"],
        "assessedBy": "admin",
        "reason": "Verified exposed wire danger",
    }
    override = {
        "status": "ACTIVE",
        "epoch": 0,
        "score": 0,
        "createdBy": "admin",
        "reason": "Operational exception reviewed",
    }
    result = calculate(data(hazard=hazard, override=override))
    assert result.calculated_score == 23.54 and result.effective_score == 100
    assert (
        result.urgent_hazard
        and result.priority_band == "CRITICAL"
        and result.override_status == "ACTIVE"
    )
    assert not calculate(data(hazard=hazard | {"epoch": 1})).urgent_hazard


def test_override_expiration_removal_and_epoch_use_latest_raw_score():
    control = {
        "status": "ACTIVE",
        "epoch": 0,
        "score": 90,
        "createdBy": "admin",
        "reason": "Reviewed operational exception",
    }
    assert calculate(data(override=control)).effective_score == 90
    for candidate, status in (
        (control | {"epoch": 1}, "REVIEW_REQUIRED"),
        (control | {"expiresAt": NOW.isoformat()}, "EXPIRED"),
        (control | {"status": "REMOVED"}, "REMOVED"),
    ):
        result = calculate(
            data(override=candidate, open_since=(NOW - timedelta(days=15)).isoformat())
        )
        assert (
            result.effective_score == result.calculated_score and result.override_status == status
        )

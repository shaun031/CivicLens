"""Offline, labeled synthetic evaluation. Candidate retrieval is NOT confirmed recurrence."""

import json
from datetime import UTC, datetime, timedelta

from app.algorithms.recurrence import evaluate
from app.analytics.fairness import compare_areas
from app.scripts.evaluate_matching import image_signal, metrics


def recurrence_experiment():
    at = datetime(2026, 1, 1, tzinfo=UTC)
    original = {
        "canonical_title": "Pothole near college entrance",
        "canonical_description": "Large dangerous road surface pothole at college entrance",
        "latitude": 12.97,
        "longitude": 77.59,
        "category": "POTHOLE",
    }
    scenarios = [
        ("verified-repeat", True, True, 30, 0, "POTHOLE", "same", False),
        ("failed-unverified-repair", False, False, 30, 0, "POTHOLE", "same", False),
        ("simultaneously-unresolved", False, True, -2, 0, "POTHOLE", "same", False),
        ("different-nearby-pothole-20m", False, True, 30, 0.00018, "POTHOLE", "different", False),
        ("explicit-distinct-object", False, True, 30, 0.00018, "POTHOLE", "same", True),
        ("missing-photo-repeat", True, True, 45, 0, "POTHOLE", "missing", False),
        ("different-angle-repeat", True, True, 90, 0, "POTHOLE", "different", False),
        ("far-same-words", False, True, 30, 0.05, "POTHOLE", "same", False),
        ("different-category", False, True, 30, 0, "DRAINAGE", "same", False),
        ("outside-historical-horizon", False, True, 900, 0, "POTHOLE", "same", False),
        ("at-repair-timestamp", False, True, 0, 0, "POTHOLE", "same", False),
        ("later-verified-repeat", True, True, 180, 0, "POTHOLE", "resized", False),
    ]
    labels, predictions = (
        [],
        {
            key: []
            for key in (
                "location-only",
                "location-text",
                "location-text-image",
                "verified-history-full",
            )
        },
    )
    for seed in range(4):
        for _name, label, verified, days, offset, category, photo, distinct in scenarios:
            current = original | {
                "latitude": original["latitude"] + offset + seed * 0.000001,
                "category": category,
                "created_at": (at + timedelta(days=days)).isoformat(),
            }
            if distinct:
                current["canonical_description"] += (
                    " Another separate pothole on the opposite side."
                )
            image = image_signal(photo).score
            score = evaluate(original, current, at.isoformat(), image=image)
            near = score["distance"] <= 150
            text = score["signals"]["text"] >= 0.65
            predictions["location-only"].append(near)
            predictions["location-text"].append(near and text)
            predictions["location-text-image"].append(
                near and text and (image is None or image >= 0.7)
            )
            predictions["verified-history-full"].append(
                verified and score["state"] == "POTENTIAL_RECURRENCE"
            )
            labels.append("DUPLICATE" if label else "DISTINCT")
    return {
        "pairs": len(labels),
        "scenarioNames": [s[0] for s in scenarios],
        "methods": {key: metrics(labels, value) for key, value in predictions.items()},
        "interpretation": "Measures candidate suggestions against synthetic recurrence labels, "
        "not automatic confirmations; nearby distinct defects remain a false-positive challenge.",
    }


def repair_experiment():
    # Fixed synthetic reference and independently specified observed feedback/reviewer outcomes.
    cases = [
        {"fixed": True, "confirm": 3, "dispute": 0, "reviewed": True},
        {"fixed": False, "confirm": 2, "dispute": 1, "reviewed": False},
        {"fixed": False, "confirm": 0, "dispute": 2, "reviewed": False},
        {"fixed": True, "confirm": 0, "dispute": 0, "reviewed": True},
        {"fixed": False, "confirm": 0, "dispute": 0, "reviewed": False},
        {"fixed": True, "confirm": 1, "dispute": 1, "reviewed": False},
        {"fixed": False, "confirm": 2, "dispute": 0, "reviewed": True},
        {"fixed": True, "confirm": 2, "dispute": 0, "reviewed": True},
    ] * 5
    decisions = {
        "officer-claim-only": [True for _ in cases],
        "simulated-citizen-majority": [c["confirm"] > c["dispute"] for c in cases],
        "simulated-admin-review": [c["reviewed"] for c in cases],
    }
    return {
        "claims": len(cases),
        "claimsWithAnyResponse": sum(c["confirm"] + c["dispute"] > 0 for c in cases),
        "verificationResponseCoverage": sum(c["confirm"] + c["dispute"] > 0 for c in cases)
        / len(cases),
        "decisionLatency": {"status": "NOT_VERIFIED", "reason": "No field decision-time labels"},
        "disputedClaims": sum(c["dispute"] > 0 for c in cases),
        "referenceReworkNeeded": sum(not c["fixed"] for c in cases),
        "policies": {
            key: {
                "incorrectClosures": sum(
                    pred and not c["fixed"] for pred, c in zip(values, cases, strict=True)
                ),
                "incorrectNonclosures": sum(
                    not pred and c["fixed"] for pred, c in zip(values, cases, strict=True)
                ),
                "agreement": sum(pred == c["fixed"] for pred, c in zip(values, cases, strict=True))
                / len(cases),
            }
            for key, values in decisions.items()
        },
        "interpretation": "SIMULATED policies and noisy synthetic reviewer decisions, "
        "not field performance. CivicLens never implements citizen majority closure.",
    }


def fairness_experiment():
    results = []
    for sample in (3, 10, 30):
        for grid in (0.01, 0.1):
            for different_mix in (False, True):
                rows = []
                for area in range(2):
                    for index in range(sample):
                        rows.append(
                            {
                                "incident_id": f"{area}-{index}",
                                "latitude": 12.971 + area * 0.02,
                                "longitude": 77.59,
                                "status": "OPEN",
                                "sla": {"RESOLUTION": "MISSED" if area else "MET"},
                                "workStartHours": 96 if area else 24,
                                "ageDays": 10,
                                "overdue": bool(area),
                                "band": "CRITICAL" if different_mix and area else "LOW",
                                "department_id": f"dept-{area}" if different_mix else "dept",
                                "resolved_at": None,
                            }
                        )
                value = compare_areas(rows, {"repairs": [], "recurrences": []}, grid)
                results.append(
                    {
                        "incidentsPerUnderlyingArea": sample,
                        "grid": grid,
                        "differentPriorityDepartmentMix": different_mix,
                        "occupiedCells": len(value["areas"]),
                        "reviewFlags": sum(
                            a["status"] == "POTENTIAL_SERVICE_DISPARITY" for a in value["areas"]
                        ),
                        "insufficientAreas": sum(not a["dataSufficient"] for a in value["areas"]),
                        "rawCountBaseline": "Equal incident counts cannot detect "
                        "the constructed delay/SLA difference",
                        "reportingBiasSensitivity": "Canonical service denominators are "
                        "independent of reporting volume",
                    }
                )
    return {
        "experiments": results,
        "missingAndVolumeSensitivity": fairness_quality_experiment(),
        "interpretation": "Constructed delay differences only. Grid coarsening can hide "
        "differences; severity/department mix is disclosed, not causally adjusted.",
    }


def fairness_quality_experiment():
    """Extra Phase13 cases: volume and missing data, not inferred causal reporting bias."""
    results = []
    for sample in (3, 10, 30):
        for missing in (False, True):
            rows = []
            for area, volume in ((0, sample), (1, sample * 3)):
                for index in range(volume):
                    unknown = missing and area == 1
                    rows.append(
                        {
                            "incident_id": f"{area}-{index}",
                            "latitude": 12.971 + area * 0.02,
                            "longitude": 77.59,
                            "status": "OPEN",
                            "sla": {
                                "RESOLUTION": "UNAVAILABLE"
                                if unknown
                                else "MISSED"
                                if area
                                else "MET"
                            },
                            "workStartHours": None if unknown else 96 if area else 24,
                            "ageDays": 10,
                            "overdue": bool(area) and not unknown,
                            "band": "HIGH" if area else "LOW",
                            "department_id": f"dept-{area}",
                            "resolved_at": None,
                        }
                    )
            result = compare_areas(rows, {"repairs": [], "recurrences": []}, 0.01)
            results.append(
                {
                    "underlyingVolumes": [sample, sample * 3],
                    "secondAreaMissingResponseAndSla": missing,
                    "areas": [
                        {
                            key: area[key]
                            for key in (
                                "incidentCount",
                                "responseObservations",
                                "missingWorkStart",
                                "medianWorkStartHours",
                                "slaObservations",
                                "missingSla",
                                "overdueRate",
                                "dataSufficient",
                                "status",
                            )
                        }
                        for area in result["areas"]
                    ],
                }
            )
    return {
        "cases": results,
        "limitation": "Incident-volume/missingness sensitivity only. "
        "Unknown real defect/reporting rates cannot be estimated without population/asset data.",
    }


def main():
    print(
        json.dumps(
            {
                "recurrence": recurrence_experiment(),
                "repairVerification": repair_experiment(),
                "fairnessSensitivity": fairness_experiment(),
                "limitations": "Synthetic English descriptions, dHash viewpoint limits, "
                "no real-world validation or discrimination inference",
            },
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()

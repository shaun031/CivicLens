"""120 fictional rubric-labelled cases, not real incidents or independent expert judgements."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.algorithms.priority_scoring.models import Assessment, PriorityInput


def dataset():
    now = datetime(2026, 10, 20, tzinfo=UTC)
    # label is ordinal operational urgency from a stated synthetic administrative rubric.
    templates = [
        ("severe_pothole_few", 9, 6, 1, 2, 4, 3),
        ("minor_streetlight_many", 2, 3, 30, 30, 3, 1),
        ("dangerous_drainage", 9, 7, 2, 2, 1, 4),
        ("old_cosmetic_damage", 2, 2, 1, 1, 60, 1),
        ("same_account_repeats", 3, 3, 1, 10, 5, 1),
        ("essential_access", 7, 10, 2, 2, 3, 3),
        ("unknown_impact", 7, None, 3, 3, 8, 2),
        ("resolved", 8, 7, 5, 5, 30, 0),
        ("reopened", 7, 6, 4, 4, 6, 2),
        ("incorrect_merge_review", 8, 8, 8, 10, 9, 2),
        ("split_subset", 4, 4, 1, 1, 12, 1),
        ("verified_emergency_access", 8, 9, 1, 1, 0, 4),
    ]
    rows = []
    for group in range(10):
        for name, severity, impact, unique, total, days, label in templates:
            identity = f"priority-synthetic-{group:02d}-{name}"

            def assessed(score, identity=identity):
                return Assessment(
                    score,
                    "VERIFIED" if score is not None else "UNASSESSED",
                    "Synthetic rubric assessment of the fictional infrastructure defect",
                    (identity,),
                    "synthetic-admin",
                )

            status = "RESOLVED" if name == "resolved" else "OPEN"
            start = now - timedelta(days=days + group * 0.2)
            data = PriorityInput(
                identity,
                1,
                status,
                start.isoformat(),
                unique,
                total,
                now,
                assessed(severity),
                assessed(impact),
                open_since=start.isoformat(),
                frozen_seconds=days * 86400 if status == "RESOLVED" else 0,
            )
            if label == 4:
                data = replace(
                    data,
                    hazard={
                        "flag": True,
                        "status": "VERIFIED",
                        "epoch": 0,
                        "evidenceReferences": [identity],
                        "assessedBy": "synthetic-admin",
                        "reason": "Verified fictional immediate safety concern",
                    },
                )
            if name == "reopened":
                data = replace(
                    data,
                    frozen_seconds=2 * 86400,
                    open_since=(now - timedelta(days=4 + group * 0.2)).isoformat(),
                )
            if name == "incorrect_merge_review":
                data = replace(
                    data, epoch=1
                )  # Assessments belong to old membership, cannot be inherited.
            rows.append(
                {
                    "id": identity,
                    "case": name,
                    "split": "tuning" if group < 3 else "heldOut",
                    "label": label,
                    "data": data,
                }
            )
    return rows

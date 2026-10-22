"""Synthetic physical-identity groups, not municipal ground truth or model training data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SyntheticReport:
    id: str
    family: str
    split: str
    truth: str
    reporter: str
    title: str
    category: str
    meters: float
    image: int | None
    status: str = "SUBMITTED"


def dataset() -> list[SyntheticReport]:
    families = (
        ("same-pothole", "tuning", "POTHOLE", [0, 1, 2, 3], [0, 0, 0, 0], [0, 0, 0, 0]),
        ("distinct-potholes", "tuning", "POTHOLE", [0, 1, 18, 19], [0, 0, 1, 1], [0, 0, 1, 1]),
        ("no-images", "tuning", "POTHOLE", [0, 1, 2], [0, 0, 0], [None, None, None]),
        ("distant-copy", "tuning", "DAMAGED_ROAD", [0, 1, 300, 301], [0, 0, 1, 1], [0, 0, 0, 0]),
        ("school-pothole", "evaluation", "POTHOLE", [0, 1, 2, 3], [0, 0, 0, 0], [1, 1, 1, 1]),
        ("two-nearby-holes", "evaluation", "POTHOLE", [0, 1, 17, 18], [0, 0, 1, 1], [0, 0, 0, 0]),
        (
            "streetlight-row",
            "evaluation",
            "BROKEN_STREETLIGHT",
            [0, 1, 8, 9],
            [0, 0, 1, 1],
            [0, 0, 0, 0],
        ),
        (
            "same-place-categories",
            "evaluation",
            "POTHOLE",
            [0, 0, 1, 1],
            [0, 1, 0, 1],
            [0, 0, 0, 0],
        ),
        ("gps-outlier", "evaluation", "POTHOLE", [0, 1, 120], [0, 0, 0], [0, 0, 0]),
        (
            "optional-photos",
            "evaluation",
            "DRAINAGE",
            [0, 1, 2, 3],
            [0, 0, 0, 0],
            [None, None, None, None],
        ),
        ("reused-photo", "evaluation", "POTHOLE", [0, 1, 4, 5], [0, 0, 1, 1], [0, 0, 0, 0]),
        ("vague-reports", "evaluation", "OTHER", [0, 1, 2], [0, 0, 1], [None, None, None]),
        ("resolved-return", "evaluation", "DAMAGED_ROAD", [0, 0, 1], [0, 1, 1], [0, 0, 0]),
        ("transitive-bridge", "evaluation", "POTHOLE", [0, 8, 16, 24], [0, 0, 1, 1], [0, 0, 0, 0]),
        ("overlap-ambiguity", "evaluation", "POTHOLE", [0, 3, 1.5, 4], [0, 1, 0, 1], [0, 0, 0, 0]),
        (
            "repeated-reporter",
            "evaluation",
            "GARBAGE",
            [0, 1, 2, 3, 4],
            [0, 0, 0, 0, 0],
            [1, 1, 1, 1, 1],
        ),
    )
    reports = []
    titles = {
        "POTHOLE": "Large deep pothole near school entrance dangerous road traffic",
        "DAMAGED_ROAD": "Damaged road surface beside junction needs urgent repair",
        "BROKEN_STREETLIGHT": "Streetlight not working beside school entrance dark night",
        "DRAINAGE": "Blocked drain overflowing water near hospital entrance",
        "OTHER": "Please help with the problem here urgently",
        "GARBAGE": "Large garbage pile beside market pavement collection needed",
    }
    for family, split, category, meters, truth, photos in families:
        for index, distance in enumerate(meters):
            actual_category = (
                "GARBAGE" if family == "same-place-categories" and index % 2 else category
            )
            title = titles[actual_category]
            if family == "streetlight-row":
                title += f" pole {truth[index] + 10}"
            reporter = (
                f"r-{index}" if family != "repeated-reporter" else f"r-{0 if index < 3 else index}"
            )
            reports.append(
                SyntheticReport(
                    f"{family}/{index}",
                    family,
                    split,
                    f"{family}/physical-{truth[index]}",
                    f"{family}/{reporter}",
                    title,
                    actual_category,
                    distance,
                    photos[index],
                    "RESOLVED" if family == "resolved-return" and index == 0 else "SUBMITTED",
                )
            )
    return reports

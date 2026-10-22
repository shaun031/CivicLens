import io
import math
from dataclasses import asdict, replace
from itertools import product
from uuid import uuid4

import pytest
from PIL import Image

from app.algorithms.duplicate_detection.candidate_selection import select
from app.algorithms.duplicate_detection.category_compatibility import compatibility
from app.algorithms.duplicate_detection.confidence_scoring import band, fuse
from app.algorithms.duplicate_detection.config import MatchingConfig
from app.algorithms.duplicate_detection.evaluation_data import dataset
from app.algorithms.duplicate_detection.geographic_similarity import envelope, proximity
from app.algorithms.duplicate_detection.image_similarity import Fingerprint, compare, fingerprint
from app.algorithms.duplicate_detection.matching_engine import match, rank
from app.algorithms.duplicate_detection.models import (
    Classification,
    ImageSignal,
    MatchInput,
    TextRecord,
    canonical_pair,
)
from app.algorithms.duplicate_detection.text_similarity import TEXT_ENGINE, meaningful, preprocess
from app.models.complaint import Category
from app.scripts.evaluate_matching import evaluate, image_signal, metrics, synthetic_image


def record(**changes):
    return MatchInput(
        complaint_id=str(uuid4()),
        category=changes.pop("category", Category.POTHOLE),
        latitude=changes.pop("latitude", 12.97),
        longitude=changes.pop("longitude", 77.59),
        text=changes.pop(
            "text",
            TextRecord(
                "Large pothole near school entrance",
                "Large deep pothole near school entrance dangerous road traffic",
            ),
        ),
        **changes,
    )


@pytest.mark.parametrize("first,second", list(product(Category, repeat=2)))
def test_all_49_category_combinations(first, second):
    relation = compatibility(first, second)
    assert relation == compatibility(second, first)
    if first == second:
        assert relation == ("CONSERVATIVE_OTHER" if first == Category.OTHER else "SAME_CATEGORY")
    elif {first, second} == {Category.POTHOLE, Category.DAMAGED_ROAD}:
        assert relation == "RELATED_CATEGORY"
        assert compatibility(first, second, False) == "INCOMPATIBLE"
    else:
        assert relation == "INCOMPATIBLE"


@pytest.mark.parametrize("latitude,longitude", [(0, 0), (90, 180), (-90, -180), (12.97, 77.59)])
def test_coordinate_edges_and_identical_points(latitude, longitude):
    assert proximity(latitude, longitude, latitude, longitude, 50) == (0, 1)
    bounds = envelope(latitude, longitude, 50)
    assert -90 <= bounds.south <= bounds.north <= 90


@pytest.mark.parametrize(
    "lat,lon,radius",
    [
        (91, 0, 50),
        (0, 181, 50),
        (math.nan, 0, 50),
        (0, math.inf, 50),
        (0, 0, 0),
        (0, 0, -5),
        (0, 0, math.nan),
    ],
)
def test_reject_invalid_geographic_values(lat, lon, radius):
    with pytest.raises(ValueError):
        proximity(lat, lon, 0, 0, radius)


def test_exact_boundary_decreasing_distance_antimeridian():
    from app.utils.geography import EARTH_METERS

    delta = math.degrees(50 / EARTH_METERS)
    assert proximity(0, 0, delta, 0, 50)[0] == pytest.approx(50)
    assert proximity(0, 0, delta, 0, 50)[1] == pytest.approx(0, abs=1e-10)
    assert proximity(0, 0, delta / 2, 0, 50)[1] == pytest.approx(0.5)
    assert proximity(0, 179.9999, 0, -179.9999, 50)[0] < 25
    assert envelope(0, 179.9999, 50).west > envelope(0, 179.9999, 50).east


def test_category_radii_and_symmetric_related_radius():
    config = MatchingConfig()
    assert [
        config.radius(cat)
        for cat in (
            Category.BROKEN_STREETLIGHT,
            Category.POTHOLE,
            Category.DAMAGED_ROAD,
            Category.DRAINAGE,
        )
    ] == [30, 50, 75, 75]
    first, second = record(), record(category=Category.DAMAGED_ROAD, latitude=12.9705)
    assert match(first, second, config).classification == Classification.OUTSIDE_SEARCH_RADIUS
    assert not select(first, [second], config).items
    assert not select(second, [first], config).items


@pytest.mark.parametrize(
    "bad",
    [
        {"default_radius": 0},
        {"default_radius": math.nan},
        {"candidate_limit": 0},
        {"strong_threshold": 0.5},
        {"minimum_text": 2},
    ],
)
def test_invalid_config(bad):
    with pytest.raises(ValueError):
        MatchingConfig(**bad)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "a",
        "NOT working north gate",
        "  LARGE!!!   pothole  ",
        "தமிழ் सड़क café 🚧",
        "x" * 20000,
        "noooo!! garbage",
        "Road road ROAD",
    ],
)
def test_text_unicode_empty_short_long_and_deterministic(text):
    value = TextRecord(text, text)
    score = TEXT_ENGINE.compare(value, value)
    assert math.isfinite(score) and 0 <= score <= 1
    assert TEXT_ENGINE.compare(value, value) == score
    assert preprocess(preprocess(text)) == preprocess(text)


def test_synonyms_negation_and_fixed_corpus():
    a = TextRecord(
        "Street light not working beside hospital gate", "Dark night at hospital entrance"
    )
    b = TextRecord(
        "Lamp post stopped functioning beside hospital entrance", "Dark night at hospital gate"
    )
    assert TEXT_ENGINE.compare(a, b) > 0.95
    assert "not" in preprocess(a.title) and "north" in preprocess("north gate")
    assert "tfidf-word-char-v1" in TEXT_ENGINE.version
    assert not meaningful(TextRecord("issue", "issue"))
    before = TEXT_ENGINE.compare(a, b)
    TEXT_ENGINE.compare(TextRecord("unrelated", "words"), TextRecord("foobar", "other"))
    assert TEXT_ENGINE.compare(a, b) == before


@pytest.mark.parametrize("scenario", ["same", "resized", "different", "missing", "corrupt"])
def test_image_scenarios_and_bounded_comparisons(scenario):
    result = image_signal(scenario)
    assert 0 <= result.comparisons <= 4
    if scenario in ("missing", "corrupt"):
        assert result.score is None
    elif scenario in ("same", "resized"):
        assert result.score >= 0.9
    else:
        assert result.score < 0.95


def test_multiple_images_corruption_uniform_and_invalid_hash():
    a, b = fingerprint(synthetic_image()), fingerprint(synthetic_image(3))
    result = compare([a, b, a], [b, a, b])
    assert result.score == 1 and result.comparisons == 4
    assert fingerprint(b"not an image") is None
    assert fingerprint(b"x" * 1572865) is None
    stream = io.BytesIO()
    Image.new("RGB", (50, 50), "black").save(stream, "JPEG")
    uniform = fingerprint(stream.getvalue())
    assert not uniform.informative
    assert compare([uniform], [uniform]).score is None
    with pytest.raises(ValueError):
        Fingerprint("not a hash", True)


@pytest.mark.parametrize("image", [None, 0, 0.5, 1])
def test_fusion_renormalizes_missing_not_zero(image):
    score, weights = fuse(0.8, 0.6, image)
    assert sum(weights.values()) == pytest.approx(1)
    assert score == pytest.approx(0.7 if image is None else 0.56 + 0.2 * image)
    assert weights["image"] == (0 if image is None else 0.2)


@pytest.mark.parametrize("value", [math.nan, math.inf, -0.1, 1.1])
def test_fusion_rejects_invalid_scores(value):
    with pytest.raises(ValueError):
        fuse(value, 0.5, None)


@pytest.mark.parametrize(
    "score,expected",
    [
        (1, "STRONG_CANDIDATE"),
        (0.8, "STRONG_CANDIDATE"),
        (0.79, "REVIEW_REQUIRED"),
        (0.6, "REVIEW_REQUIRED"),
        (0.59, "WEAK_MATCH"),
    ],
)
def test_decision_bands(score, expected):
    assert band(score, 0.8, 0.6) == expected


def test_strong_missing_images_same_photo_not_conclusive_and_contradictions():
    first, second = record(), record()
    config = MatchingConfig()
    result = match(first, second, config)
    assert result.classification == "STRONG_CANDIDATE"
    assert result.imageScore is None and result.effectiveWeights["geographic"] == 0.5
    assert (
        match(
            first, replace(second, latitude=12.97016), config, ImageSignal(1, (), 1)
        ).classification
        == "REVIEW_REQUIRED"
    )
    assert (
        match(
            first, replace(second, category=Category.GARBAGE), config, ImageSignal(1, (), 1)
        ).classification
        == "CATEGORY_MISMATCH"
    )
    assert (
        match(
            first,
            replace(second, text=TextRecord("Issue", "Problem")),
            config,
            ImageSignal(1, (), 1),
        ).classification
        == "INSUFFICIENT_EVIDENCE"
    )
    assert (
        match(first, replace(second, status="RESOLVED"), config).classification
        == "INSUFFICIENT_EVIDENCE"
    )
    north, south = (
        replace(first, text=TextRecord("Pothole north entrance", first.text.description)),
        replace(second, text=TextRecord("Pothole south entrance", second.text.description)),
    )
    assert match(north, south, config).classification == "REVIEW_REQUIRED"


def test_canonical_pair_reruns_deterministic_explanation_and_rank():
    first, second = record(), record()
    assert canonical_pair(first.complaint_id, second.complaint_id) == canonical_pair(
        second.complaint_id, first.complaint_id
    )
    with pytest.raises(ValueError):
        canonical_pair(first.complaint_id, first.complaint_id)
    a, b = match(first, second, MatchingConfig()), match(second, first, MatchingConfig())
    assert asdict(a) | {"timings": {}} == asdict(b) | {"timings": {}}
    assert rank([a, b]) == [a, b]


def test_selection_lifecycle_exclusion_limits_and_stable_ties():
    first, second = record(), record()
    third = record()
    selection = select(
        first,
        [first, second, third, record(status="REJECTED"), record(category=Category.GARBAGE)],
        MatchingConfig(candidate_limit=1),
    )
    assert selection.truncated and len(selection.items) == 1
    assert selection.items[0].complaint_id == min(second.complaint_id, third.complaint_id)
    assert not select(replace(first, status="RESOLVED"), [second], MatchingConfig()).items


def test_evaluation_dataset_group_disjoint_metrics_and_honest_uncertain():
    pairs = dataset()
    assert len(pairs) == 144 and len({row.id for row in pairs}) == 144
    groups = {
        split: {row.group for row in pairs if row.split == split}
        for split in ("tuning", "evaluation")
    }
    assert not groups["tuning"] & groups["evaluation"]
    assert {row.label for row in pairs} == {"DUPLICATE", "NOT_DUPLICATE", "UNCERTAIN"}
    assert metrics(["DUPLICATE", "NOT_DUPLICATE"], [True, False])["f1"] == 1
    assert metrics(["DUPLICATE", "NOT_DUPLICATE"], [False, True])["FP"] == 1
    result = evaluate("evaluation")
    assert result["labeledBinaryPairs"] == 54
    assert sum(result["uncertainClassifications"].values()) == 18


def test_vague_repeated_help_and_numeric_pole_contradiction():
    first, second = record(), record()
    vague = TextRecord("Please fix the issue", "Please help with the issue here urgently")
    assert not meaningful(vague)
    assert (
        match(
            replace(first, text=vague), replace(second, text=vague), MatchingConfig()
        ).classification
        == "INSUFFICIENT_EVIDENCE"
    )
    a = TextRecord("Streetlight pole 17 not working", "Broken streetlight near school entrance")
    b = TextRecord("Streetlight pole 18 not working", "Broken streetlight near school entrance")
    assert (
        match(replace(first, text=a), replace(second, text=b), MatchingConfig()).classification
        == "REVIEW_REQUIRED"
    )

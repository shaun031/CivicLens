import re
import threading
import unicodedata
from functools import lru_cache
from hashlib import sha256

from app.algorithms.duplicate_detection.models import TextRecord

# Fixed infrastructure vocabulary, independent of users and held-out evaluation pairs.
CORPUS = (
    "pothole road damaged gate entrance campus university large deep dangerous traffic",
    "streetlight lamp pole light not working broken dark night bus stop entrance",
    "garbage rubbish waste trash pile collection pavement smell public street",
    "drain drainage blocked water flooding sewage rain gutter overflow",
    "road surface damaged cracks junction vehicle traffic repair asphalt",
    "public bench fence park property damaged broken sign shelter",
    "pipe leaking burst water flow roadside repair pavement",
    "north south east west opposite beside outside inside near left right",
    "first second another different separate not no working repaired resolved",
    "small large deep shallow school hospital market library gate crossing corner",
    "pothole near entrance large hole road dangerous vehicles pedestrian",
    "streetlight not working beside entrance road dark lamp pole broken",
    "garbage near bus stop rubbish waste pavement collection needed",
    "drain blocked outside gate water overflow flooding road",
)
STOP = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "has",
        "have",
        "on",
        "in",
        "at",
        "of",
        "to",
        "and",
        "for",
        "this",
        "that",
        "there",
        "it",
    ]
)
REPLACEMENTS = (
    (r"\bstreet\s+lights?\b|\blamp\s+posts?\b|\blamps?\b", "streetlight"),
    (r"\bbig\b|\bhuge\b", "large"),
    (r"\bcollege\b|\buniversity\b", "campus"),
    (r"\bgates?\b", "entrance"),
    (r"\bhole (?:in|on) (?:the )?road\b", "pothole"),
    (r"\brubbish\b|\btrash\b|\bwaste\b", "garbage"),
    (r"\bstopped functioning\b|\bnot functioning\b", "not working"),
)
PREPROCESS_VERSION = "unicode-en-v1"
ASSET_WORDS = frozenset(
    (
        "pothole",
        "road",
        "streetlight",
        "pole",
        "garbage",
        "drain",
        "drainage",
        "sewage",
        "pipe",
        "fence",
        "bench",
        "shelter",
        "pavement",
        "cracks",
        "water",
        "flooding",
        "asphalt",
        "property",
        "sign",
    )
)


def preprocess(text: str) -> str:
    return _preprocess(text[:4300])


@lru_cache(maxsize=4096)
def _preprocess(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"\b(is|was|does|do|can|could|would|should)n['’]t\b", r"\1 not", text)
    text = re.sub(r"(\w)\1{3,}", r"\1\1", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    for pattern, replacement in REPLACEMENTS:
        text = re.sub(pattern, replacement, text)
    return " ".join(text.split())


def document(record: TextRecord) -> str:
    return preprocess(f"{record.title} {record.description}")


def meaningful(record: TextRecord) -> bool:
    tokens = set(document(record).split())
    return len(tokens - STOP) >= 4 and bool(tokens & ASSET_WORDS)


def contradictions(first: TextRecord, second: TextRecord) -> tuple[str, ...]:
    left, right = set(document(first).split()), set(document(second).split())
    result = []
    for a, b in (
        ("north", "south"),
        ("east", "west"),
        ("left", "right"),
        ("inside", "outside"),
        ("first", "second"),
    ):
        if (a in left and b in right and a not in right) or (
            b in left and a in right and b not in right
        ):
            result.append(f"Conflicting location/object qualifiers: {a}/{b}")
    if ("not" in left) != ("not" in right) and "working" in left & right:
        result.append("Conflicting working/not working descriptions")
    if any(word in left | right for word in ("another", "separate", "different")):
        result.append("Text mentions a potentially distinct object")
    pattern = r"\b(?:pole|streetlight|entrance|pothole|hole)\s+(?:number\s+|no\s+|id\s+)?(\d+)\b"
    first_ids = set(re.findall(pattern, document(first)))
    second_ids = set(re.findall(pattern, document(second)))
    if first_ids and second_ids and first_ids != second_ids:
        result.append("Conflicting numeric infrastructure identifiers")
    return tuple(result)


class TextSimilarity:
    """One reproducible corpus fit per process, bounded cache; never fit on a pair."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._models = None

    def _initialize(self):
        with self._lock:
            if self._models is None:
                import sklearn
                from sklearn.feature_extraction.text import TfidfVectorizer

                word = TfidfVectorizer(
                    ngram_range=(1, 2),
                    max_features=8000,
                    token_pattern=r"(?u)\b\w+\b",
                    sublinear_tf=True,
                )
                char = TfidfVectorizer(
                    analyzer="char_wb", ngram_range=(3, 5), max_features=12000, sublinear_tf=True
                )
                corpus = [preprocess(item) for item in CORPUS]
                word.fit(corpus)
                char.fit(corpus)
                version = sha256(
                    (
                        "text-v1"
                        + PREPROCESS_VERSION
                        + repr(CORPUS)
                        + repr(REPLACEMENTS)
                        + sklearn.__version__
                    ).encode()
                ).hexdigest()[:16]
                self._models = word, char, f"tfidf-word-char-v1-{version}"
        return self._models

    @lru_cache(maxsize=2048)  # noqa: B019 -- process singleton; bounded retained vectors
    def _vector(self, value: str):
        word, char, _ = self._initialize()
        return word.transform([value]), char.transform([value])

    @property
    def version(self) -> str:
        return self._initialize()[2]

    def compare(self, first: TextRecord, second: TextRecord) -> float:
        left, right = document(first), document(second)
        if not left or not right:
            return 0.0
        a, b = self._vector(left), self._vector(right)
        value = 0.7 * float((a[0] @ b[0].T)[0, 0]) + 0.3 * float((a[1] @ b[1].T)[0, 0])
        return max(0.0, min(1.0, value))


TEXT_ENGINE = TextSimilarity()

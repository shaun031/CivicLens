import io
from dataclasses import dataclass

from PIL import Image, ImageStat, UnidentifiedImageError

from app.algorithms.duplicate_detection.models import ImageSignal

FINGERPRINT_VERSION = "dhash64-v1"


@dataclass(frozen=True)
class Fingerprint:
    bits: str
    informative: bool
    version: str = FINGERPRINT_VERSION

    def __post_init__(self) -> None:
        if len(self.bits) != 16 or any(char not in "0123456789abcdef" for char in self.bits):
            raise ValueError("Invalid dHash fingerprint")
        if self.version != FINGERPRINT_VERSION:
            raise ValueError("Unsupported fingerprint version")


def fingerprint(content: bytes) -> Fingerprint | None:
    if not content or len(content) > 1572864:
        return None
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > 4000000 or max(image.size) > 4096:
                return None
            image.load()
            gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            pixels = list(gray.get_flattened_data())
            bits = 0
            for row in range(8):
                for col in range(8):
                    bits = (bits << 1) | (pixels[row * 9 + col] > pixels[row * 9 + col + 1])
            return Fingerprint(f"{bits:016x}", ImageStat.Stat(gray).stddev[0] >= 8)
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return None


def compare(first: list[Fingerprint], second: list[Fingerprint]) -> ImageSignal:
    left, right = [f for f in first[:2] if f.informative], [f for f in second[:2] if f.informative]
    if not left or not right:
        return ImageSignal(indicators=("Missing, corrupt or low-information image evidence",))
    scores = [1 - (int(a.bits, 16) ^ int(b.bits, 16)).bit_count() / 64 for a in left for b in right]
    score = max(scores)
    indicators = ["Best informative image-pair dHash; different viewpoints may not match"]
    if score >= 0.98:
        indicators.append("Identical/reused photograph is not proof of the same object")
    return ImageSignal(score, tuple(indicators), len(scores))

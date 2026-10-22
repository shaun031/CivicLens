import io
import warnings
from dataclasses import dataclass

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings


@dataclass(frozen=True)
class Upload:
    content: bytes
    filename: str
    content_type: str


class EvidenceService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def sanitize(self, upload: Upload) -> bytes:
        if (
            any(char in upload.filename for char in ("/", "\\", ":", "\x00"))
            or ".." in upload.filename
        ):
            raise HTTPException(422, "Unsafe image filename.")
        if not upload.content or len(upload.content) > self.settings.max_upload_bytes:
            raise HTTPException(413, "Each image must be non-empty and at most 1.5 MiB.")
        mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
        if upload.content_type not in mime.values():
            raise HTTPException(415, "Only JPEG, PNG and WebP images are accepted.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(upload.content)) as source:
                    if source.format not in mime or mime[source.format] != upload.content_type:
                        raise HTTPException(
                            415, "Image content does not match an accepted MIME type."
                        )
                    if (
                        max(source.size) > self.settings.max_image_dimension
                        or source.width * source.height > self.settings.max_image_pixels
                    ):
                        raise HTTPException(413, "Image exceeds the dimension or pixel limit.")
                    if getattr(source, "n_frames", 1) != 1:
                        raise HTTPException(
                            422, "Animated or multi-frame evidence is not supported."
                        )
                    source.verify()
                with Image.open(io.BytesIO(upload.content)) as source:
                    source.load()
                    oriented = ImageOps.exif_transpose(source)
                    oriented.thumbnail((2048, 2048))
                    # Fresh pixels only: no EXIF/GPS, ICC, comments, or source metadata.
                    pixels = Image.new("RGB", oriented.size, "white")
                    if "A" in oriented.getbands() or oriented.mode == "P":
                        rgba = oriented.convert("RGBA")
                        pixels.paste(rgba, mask=rgba.getchannel("A"))
                    else:
                        pixels.paste(oriented.convert("RGB"))
                    output = io.BytesIO()
                    pixels.save(output, format="JPEG", quality=85)
                    if output.tell() > self.settings.max_upload_bytes:
                        output = io.BytesIO()
                        pixels.save(output, format="JPEG", quality=65)
                    if output.tell() > self.settings.max_upload_bytes:
                        raise HTTPException(413, "Sanitized image exceeds the evidence size limit.")
                    return output.getvalue()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise HTTPException(413, "Image exceeds the safe pixel limit.") from error
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as error:
            raise HTTPException(422, "Image is corrupt or cannot be decoded safely.") from error

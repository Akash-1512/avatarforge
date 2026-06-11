"""Source-image validation.

Light checks only (format, size, dimensions) using Pillow. Actual face
detection is the model server's job — SadTalker fails cleanly when no
face is present, and duplicating a face detector here would bloat the
API image with CV dependencies for marginal benefit.
"""

import io

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MIN_DIMENSION = 256
ALLOWED_FORMATS = {"PNG", "JPEG"}


class ImageValidationError(Exception):
    pass


def validate_source_image(data: bytes) -> str:
    """Validate and return the normalized extension ('png' or 'jpg')."""
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageValidationError(f"Image exceeds {MAX_IMAGE_BYTES // (1024 * 1024)}MB limit")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))  # verify() invalidates; reopen for size
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageValidationError(f"Not a valid image file: {exc}") from exc

    if img.format not in ALLOWED_FORMATS:
        raise ImageValidationError(f"Unsupported format {img.format}; use PNG or JPEG")
    if min(img.size) < MIN_DIMENSION:
        raise ImageValidationError(
            f"Image too small ({img.size[0]}x{img.size[1]}); minimum {MIN_DIMENSION}px per side"
        )
    return "png" if img.format == "PNG" else "jpg"

"""Image validation — real Pillow, generated images."""

import io

import pytest
from PIL import Image

from backend.services.avatar.validation import ImageValidationError, validate_source_image


def _img_bytes(size=(512, 512), fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(120, 90, 60)).save(buf, format=fmt)
    return buf.getvalue()


def test_valid_png():
    assert validate_source_image(_img_bytes(fmt="PNG")) == "png"


def test_valid_jpeg():
    assert validate_source_image(_img_bytes(fmt="JPEG")) == "jpg"


def test_rejects_non_image():
    with pytest.raises(ImageValidationError, match="Not a valid image"):
        validate_source_image(b"definitely not an image")


def test_rejects_too_small():
    with pytest.raises(ImageValidationError, match="too small"):
        validate_source_image(_img_bytes(size=(100, 100)))


def test_rejects_unsupported_format():
    buf = io.BytesIO()
    Image.new("RGB", (512, 512)).save(buf, format="BMP")
    with pytest.raises(ImageValidationError, match="Unsupported format"):
        validate_source_image(buf.getvalue())


def test_rejects_oversize():
    with pytest.raises(ImageValidationError, match="exceeds"):
        validate_source_image(b"\x89PNG" + b"0" * (11 * 1024 * 1024))

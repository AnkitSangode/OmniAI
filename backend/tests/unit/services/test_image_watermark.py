from io import BytesIO

import pytest
from PIL import Image, ImageChops

from app.services.images.watermark import ImageWatermarkService


def make_png(color=(120, 140, 160), size=(256, 256)) -> bytes:
    image = Image.new("RGB", size, color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_watermark_returns_valid_png():
    service = ImageWatermarkService()

    result = service.apply(make_png())

    with Image.open(BytesIO(result)) as image:
        assert image.format == "PNG"
        assert image.size == (256, 256)
        assert image.mode == "RGBA"


def test_watermark_changes_image_pixels():
    service = ImageWatermarkService()
    original_bytes = make_png()

    result = service.apply(original_bytes)

    with Image.open(BytesIO(original_bytes)) as original:
        original_rgba = original.convert("RGBA")
    with Image.open(BytesIO(result)) as watermarked:
        difference = ImageChops.difference(
            original_rgba,
            watermarked.convert("RGBA"),
        )

    assert difference.convert("RGB").getbbox() is not None


def test_watermark_handles_small_images():
    service = ImageWatermarkService()

    result = service.apply(make_png(size=(64, 64)))

    with Image.open(BytesIO(result)) as image:
        assert image.size == (64, 64)


def test_watermark_rejects_empty_bytes():
    service = ImageWatermarkService()

    with pytest.raises(ValueError, match="empty image"):
        service.apply(b"")


def test_watermark_rejects_invalid_image_bytes():
    service = ImageWatermarkService()

    with pytest.raises(ValueError, match="valid image"):
        service.apply(b"not-an-image")

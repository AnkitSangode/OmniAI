from unittest.mock import AsyncMock

import pytest

from app.services.images.image_safety import (
    ImageSafetyResult,
    ImageSafetyService,
    ImageSafetyStatus,
    ImageSafetyUnavailable,
    UnsafeGeneratedImageError,
)


@pytest.mark.asyncio
async def test_missing_checker_reports_not_checked_not_approved():
    service = ImageSafetyService(checker=None)

    result = await service.check(b"generated-image-bytes")

    assert result.status is ImageSafetyStatus.NOT_CHECKED
    assert result.status is not ImageSafetyStatus.APPROVED


@pytest.mark.asyncio
async def test_checker_approved_image():
    checker = AsyncMock()
    checker.check.return_value = ImageSafetyResult(
        status=ImageSafetyStatus.APPROVED
    )
    service = ImageSafetyService(checker=checker)

    result = await service.check(b"generated-image-bytes")

    assert result.status is ImageSafetyStatus.APPROVED
    checker.check.assert_awaited_once_with(b"generated-image-bytes")


@pytest.mark.asyncio
async def test_checker_rejected_image_with_categories():
    checker = AsyncMock()
    checker.check.return_value = ImageSafetyResult(
        status=ImageSafetyStatus.REJECTED,
        categories=("sexual_content",),
    )
    service = ImageSafetyService(checker=checker)

    with pytest.raises(UnsafeGeneratedImageError) as exc_info:
        await service.check(b"generated-image-bytes")

    assert exc_info.value.categories == ("sexual_content",)


@pytest.mark.asyncio
async def test_checker_failure_fails_closed():
    checker = AsyncMock()
    checker.check.side_effect = TimeoutError("provider timed out")
    service = ImageSafetyService(checker=checker)

    with pytest.raises(ImageSafetyUnavailable):
        await service.check(b"generated-image-bytes")


@pytest.mark.asyncio
async def test_configured_checker_cannot_return_not_checked():
    checker = AsyncMock()
    checker.check.return_value = ImageSafetyResult(
        status=ImageSafetyStatus.NOT_CHECKED
    )
    service = ImageSafetyService(checker=checker)

    with pytest.raises(ImageSafetyUnavailable):
        await service.check(b"generated-image-bytes")


@pytest.mark.asyncio
async def test_empty_image_bytes_are_rejected():
    checker = AsyncMock()
    service = ImageSafetyService(checker=checker)

    with pytest.raises(ValueError, match="cannot be empty"):
        await service.check(b"")

    checker.check.assert_not_awaited()

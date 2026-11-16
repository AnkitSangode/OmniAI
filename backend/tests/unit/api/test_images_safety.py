from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.images import moderate_image_prompt
from app.services.safety.schemas import (
    SafetyServiceUnavailable,
    UnsafeContentError,
)


@pytest.mark.asyncio
async def test_safe_image_prompt_is_accepted():
    safety_service = AsyncMock()

    await moderate_image_prompt(safety_service, "A mountain landscape")

    safety_service.check_input.assert_awaited_once_with(
        "A mountain landscape"
    )


@pytest.mark.asyncio
async def test_unsafe_image_prompt_is_rejected():
    safety_service = AsyncMock()
    safety_service.check_input.side_effect = UnsafeContentError(
        categories=("S1",)
    )

    with pytest.raises(HTTPException) as exc_info:
        await moderate_image_prompt(
            safety_service,
            "An unsafe image prompt",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {
        "code": "unsafe_input",
        "message": "Your image prompt was blocked by safety moderation.",
        "categories": ["S1"],
    }


@pytest.mark.asyncio
async def test_moderation_unavailable_blocks_image_generation():
    safety_service = AsyncMock()
    safety_service.check_input.side_effect = SafetyServiceUnavailable(
        "Moderation provider unavailable"
    )

    with pytest.raises(HTTPException) as exc_info:
        await moderate_image_prompt(
            safety_service,
            "A mountain landscape",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == (
        "Safety moderation is temporarily unavailable."
    )


@pytest.mark.asyncio
async def test_disabled_moderation_allows_prompt_without_provider_call():
    await moderate_image_prompt(None, "A mountain landscape")

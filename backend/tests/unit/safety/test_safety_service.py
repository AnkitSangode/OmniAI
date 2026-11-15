from unittest.mock import AsyncMock

import pytest

from app.services.safety.safety_service import SafetyService
from app.services.safety.schemas import (
    ModerationResult,
    SafetyServiceUnavailable,
    UnsafeContentError,
)


@pytest.mark.asyncio
async def test_safe_input_is_accepted():
    moderator = AsyncMock()
    moderator.moderate.return_value = ModerationResult(
        is_safe=True
    )

    service = SafetyService(moderator)

    result = await service.check_input("Hello OmniAI")

    assert result.is_safe is True
    moderator.moderate.assert_awaited_once_with(
        "Hello OmniAI",
        role="user",
    )


@pytest.mark.asyncio
async def test_unsafe_input_is_rejected():
    moderator = AsyncMock()
    moderator.moderate.return_value = ModerationResult(
        is_safe=False,
        categories=("S1",),
    )

    service = SafetyService(moderator)

    with pytest.raises(UnsafeContentError) as exc_info:
        await service.check_input("Unsafe prompt")

    assert exc_info.value.categories == ("S1",)


@pytest.mark.asyncio
async def test_unsafe_output_is_rejected():
    moderator = AsyncMock()
    moderator.moderate.return_value = ModerationResult(
        is_safe=False,
        categories=("S2",),
    )

    service = SafetyService(moderator)

    with pytest.raises(UnsafeContentError):
        await service.check_output("Unsafe response")

    moderator.moderate.assert_awaited_once_with(
        "Unsafe response",
        role="assistant",
    )


@pytest.mark.asyncio
async def test_moderation_failure_fails_closed():
    moderator = AsyncMock()
    moderator.moderate.side_effect = TimeoutError(
        "Provider timed out"
    )

    service = SafetyService(moderator)

    with pytest.raises(SafetyServiceUnavailable):
        await service.check_input("Hello")


@pytest.mark.asyncio
async def test_empty_text_does_not_call_provider():
    moderator = AsyncMock()
    service = SafetyService(moderator)

    result = await service.check_input("   ")

    assert result.is_safe is True
    moderator.moderate.assert_not_awaited()
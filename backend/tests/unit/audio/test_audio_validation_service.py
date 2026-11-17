
import pytest

from app.services.audio.audio_validation_service import (
    AudioValidationService,
)


@pytest.mark.asyncio
async def test_rejects_empty_audio():
    validator = AudioValidationService()

    with pytest.raises(ValueError, match="empty"):
        await validator.validate(b"", "wav")


@pytest.mark.asyncio
async def test_rejects_unsupported_extension():
    validator = AudioValidationService()

    with pytest.raises(ValueError, match="extension"):
        await validator.validate(b"some-bytes", "txt")


@pytest.mark.asyncio
async def test_rejects_invalid_audio_bytes():
    validator = AudioValidationService()

    with pytest.raises(ValueError, match="valid audio"):
        await validator.validate(b"this is not audio", "wav")

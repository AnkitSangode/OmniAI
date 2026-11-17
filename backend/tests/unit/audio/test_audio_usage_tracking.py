from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.audio import audio_service as module


class FakeRepository:
    def __init__(self, session):
        self.session = session
        self.task = None

    async def create(self, task):
        task.id = uuid4()
        self.task = task

    async def get_by_id(self, task_id, user_id):
        return self.task


class FakeStorage:
    async def save(self, **kwargs):
        return "stored-audio.wav"


@pytest.mark.asyncio
async def test_transcribe_records_audio_usage(monkeypatch):
    monkeypatch.setattr(module, "AudioRepository", FakeRepository)
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()

    stt = MagicMock()
    stt.transcribe = AsyncMock(
        return_value=SimpleNamespace(
            text="hello world", provider="openai", model="whisper-1"
        )
    )
    usage = MagicMock()
    usage.record_request = AsyncMock()

    validator = MagicMock()
    validator.validate = AsyncMock()

    service = module.AudioService(
        session,
        stt,
        MagicMock(),
        FakeStorage(),
        usage,
        audio_validator=validator,
    )
    user_id = uuid4()

    task = await service.transcribe(user_id, b"audio-bytes", "sample.wav", "audio/wav")

    assert task.status == "completed"
    usage.record_request.assert_awaited_once()
    recorded = usage.record_request.await_args.kwargs
    assert recorded["request_type"] == "audio"
    assert recorded["request_id"] == str(task.id)
    assert recorded["model"] == "openai/whisper-1"
    assert recorded["status"] == "success"
    validator.validate.assert_awaited_once_with(
        audio_bytes=b"audio-bytes",
        extension="wav",
    )


@pytest.mark.asyncio
async def test_generate_speech_records_audio_usage(monkeypatch):
    monkeypatch.setattr(module, "AudioRepository", FakeRepository)
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()

    tts = MagicMock()
    tts.synthesize = AsyncMock(
        return_value=SimpleNamespace(
            audio_bytes=b"generated",
            extension="mp3",
            provider="coqui",
            model="xtts-v2",
            content_type="audio/mpeg",
            duration_seconds=2.5,
        )
    )
    usage = MagicMock()
    usage.record_request = AsyncMock()

    service = module.AudioService(session, MagicMock(), tts, FakeStorage(), usage)
    task = await service.generate_speech(uuid4(), "Hello there")

    assert task.status == "completed"
    usage.record_request.assert_awaited_once()
    recorded = usage.record_request.await_args.kwargs
    assert recorded["request_type"] == "audio"
    assert recorded["request_id"] == str(task.id)
    assert recorded["model"] == "coqui/xtts-v2"
    assert recorded["status"] == "success"


@pytest.mark.asyncio
async def test_transcribe_rejects_empty_audio_before_tracking(monkeypatch):
    monkeypatch.setattr(module, "AudioRepository", FakeRepository)
    usage = MagicMock()
    usage.record_request = AsyncMock()
    service = module.AudioService(
        MagicMock(), MagicMock(), MagicMock(), FakeStorage(), usage
    )

    with pytest.raises(ValueError, match="cannot be empty"):
        await service.transcribe(uuid4(), b"", "sample.wav")

    usage.record_request.assert_not_awaited()

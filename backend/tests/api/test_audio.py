
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.audio import (
    download_audio_file,
    get_audio_history,
    get_audio_read_service,
    get_audio_task,
)
from app.services.audio.audio_read_service import AudioReadService


def make_audio_task(**overrides):
    """Create a lightweight audio task for endpoint tests."""

    task = {
        "id": uuid4(),
        "task_type": "speech_generation",
        "input_text": "Hello world",
        "transcript": None,
        "provider": "replicate",
        "model": "xtts",
        "status": "completed",
        "audio_path": "audio-test.wav",
        "source_filename": None,
        "content_type": "audio/wav",
        "duration_seconds": 2.5,
        "created_at": datetime.now(timezone.utc),
    }

    task.update(overrides)
    return SimpleNamespace(**task)


@pytest.mark.asyncio
async def test_get_audio_history_returns_tasks_and_total():
    user_id = uuid4()
    current_user = SimpleNamespace(id=user_id)

    task = make_audio_task()

    service = SimpleNamespace(
        get_history=AsyncMock(return_value=([task], 1))
    )

    response = await get_audio_history(
        offset=0,
        limit=20,
        current_user=current_user,
        service=service,
    )

    assert response.total == 1
    assert len(response.items) == 1
    assert response.items[0].id == task.id
    assert response.items[0].task_type == task.task_type

    service.get_history.assert_awaited_once_with(
        user_id=user_id,
        offset=0,
        limit=20,
    )


@pytest.mark.asyncio
async def test_get_audio_history_passes_pagination_parameters():
    user_id = uuid4()
    current_user = SimpleNamespace(id=user_id)

    service = SimpleNamespace(
        get_history=AsyncMock(return_value=([], 0))
    )

    response = await get_audio_history(
        offset=10,
        limit=5,
        current_user=current_user,
        service=service,
    )

    assert response.total == 0
    assert response.items == []

    service.get_history.assert_awaited_once_with(
        user_id=user_id,
        offset=10,
        limit=5,
    )


@pytest.mark.asyncio
async def test_get_audio_task_returns_task():
    user_id = uuid4()
    task = make_audio_task()
    current_user = SimpleNamespace(id=user_id)

    service = SimpleNamespace(
        get_task=AsyncMock(return_value=task)
    )

    response = await get_audio_task(
        task_id=task.id,
        current_user=current_user,
        service=service,
    )

    assert response.id == task.id
    assert response.status == "completed"
    assert response.audio_url == f"/api/v1/audio/{task.id}/file"

    service.get_task.assert_awaited_once_with(
        task_id=task.id,
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_get_audio_task_returns_404_for_unknown_or_other_user_task():
    user_id = uuid4()
    task_id = uuid4()
    current_user = SimpleNamespace(id=user_id)

    service = SimpleNamespace(
        get_task=AsyncMock(return_value=None)
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_audio_task(
            task_id=task_id,
            current_user=current_user,
            service=service,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Audio task not found."

    # The authenticated user's ID must always scope the lookup.
    service.get_task.assert_awaited_once_with(
        task_id=task_id,
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_download_audio_file_returns_file_response(tmp_path):
    user_id = uuid4()
    task = make_audio_task()
    current_user = SimpleNamespace(id=user_id)

    audio_file = tmp_path / task.audio_path
    audio_file.write_bytes(b"fake audio content")

    storage = SimpleNamespace(
        get_file_path=MagicMock(return_value=audio_file)
    )

    service = SimpleNamespace(
        get_task=AsyncMock(return_value=task),
        storage=storage,
    )

    response = await download_audio_file(
        task_id=task.id,
        current_user=current_user,
        service=service,
    )

    assert Path(response.path) == audio_file
    assert response.media_type == "audio/wav"

    storage.get_file_path.assert_called_once_with(task.audio_path)

    service.get_task.assert_awaited_once_with(
        task_id=task.id,
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_download_audio_file_returns_404_when_task_does_not_exist():
    user_id = uuid4()
    task_id = uuid4()
    current_user = SimpleNamespace(id=user_id)

    service = SimpleNamespace(
        get_task=AsyncMock(return_value=None),
        storage=SimpleNamespace(
            get_file_path=MagicMock()
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await download_audio_file(
            task_id=task_id,
            current_user=current_user,
            service=service,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Audio file not found."


@pytest.mark.asyncio
async def test_download_audio_file_returns_404_when_task_has_no_audio_path():
    user_id = uuid4()
    task = make_audio_task(audio_path=None)
    current_user = SimpleNamespace(id=user_id)

    service = SimpleNamespace(
        get_task=AsyncMock(return_value=task),
        storage=SimpleNamespace(
            get_file_path=MagicMock()
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await download_audio_file(
            task_id=task.id,
            current_user=current_user,
            service=service,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Audio file not found."


@pytest.mark.asyncio
async def test_download_audio_file_returns_404_when_file_is_missing():
    user_id = uuid4()
    task = make_audio_task()
    current_user = SimpleNamespace(id=user_id)

    missing_file = Path("nonexistent-audio-file.wav")

    storage = SimpleNamespace(
        get_file_path=MagicMock(return_value=missing_file)
    )

    service = SimpleNamespace(
        get_task=AsyncMock(return_value=task),
        storage=storage,
    )

    with pytest.raises(HTTPException) as exc_info:
        await download_audio_file(
            task_id=task.id,
            current_user=current_user,
            service=service,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == (
        "Audio file is missing from storage."
    )


def test_audio_read_dependency_does_not_initialize_ai_providers(
    monkeypatch,
):
    from app.api.v1.endpoints import audio

    storage = MagicMock()

    monkeypatch.setattr(
        audio,
        "AudioStorageService",
        lambda: storage,
    )

    db = MagicMock()

    service = get_audio_read_service(db=db)

    assert isinstance(service, AudioReadService)
    assert service.storage is storage

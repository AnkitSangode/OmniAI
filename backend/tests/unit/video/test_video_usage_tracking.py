from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.video import video_service as module


class FakeRepository:
    def __init__(self, session):
        self.session = session
        self.task = None

    async def create(self, task):
        self.task = task

    async def get_by_id(self, task_id, user_id):
        return self.task


class FakeStorage:
    ALLOWED_EXTENSIONS = {"mp4", "mov", "webm"}

    def __init__(self, storage_dir):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, video_bytes, task_id, extension):
        path = self.storage_dir / f"{task_id}.{extension}"
        path.write_bytes(video_bytes)
        return path.name

    def get_file_path(self, filename):
        return self.storage_dir / filename


class FakeFFmpeg:
    async def extract_metadata(self, video_path):
        return {
            "duration_seconds": 3.0, "width": 640, "height": 360,
            "frame_rate": 30.0, "video_codec": "h264", "audio_codec": "aac",
            "has_audio": False,
        }


@pytest.mark.asyncio
async def test_video_processing_records_usage(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "VideoRepository", FakeRepository)
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    usage = MagicMock()
    usage.record_request = AsyncMock()

    service = module.VideoService(
        session=session,
        whisper_provider=MagicMock(),
        llm_client=MagicMock(),
        ffmpeg_service=FakeFFmpeg(),
        storage=FakeStorage(tmp_path),
        usage_service=usage,
    )

    task = await service.process_video(uuid4(), b"video-bytes", "sample.mp4", "video/mp4")

    assert task.status == "completed"
    usage.record_request.assert_awaited_once()
    recorded = usage.record_request.await_args.kwargs
    assert recorded["request_type"] == "video"
    assert recorded["request_id"] == str(task.id)
    assert recorded["model"] == "ffmpeg/video-processing"
    assert recorded["status"] == "success"

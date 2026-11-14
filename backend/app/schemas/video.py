
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VideoTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_filename: str
    content_type: str | None
    duration_seconds: float | None
    width: int | None
    height: int | None
    frame_rate: float | None
    video_codec: str | None
    audio_codec: str | None
    metadata_json: dict | None
    transcript: str | None
    summary: str | None
    captions: str | None
    transcription_provider: str | None
    transcription_model: str | None
    status: str
    error_message: str | None
    video_url: str | None = None
    created_at: datetime


class VideoHistoryResponse(BaseModel):
    items: list[VideoTaskResponse]
    total: int

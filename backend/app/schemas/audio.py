
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TextToSpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class AudioTaskResponse(BaseModel):
    id: UUID
    task_type: str
    input_text: str | None = None
    transcript: str | None = None
    provider: str
    model: str
    status: str
    audio_url: str | None = None
    source_filename: str | None = None
    content_type: str | None = None
    duration_seconds: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AudioHistoryResponse(BaseModel):
    items: list[AudioTaskResponse]
    total: int

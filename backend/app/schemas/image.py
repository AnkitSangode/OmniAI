
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    width: int = Field(default=512, ge=256, le=1024)
    height: int = Field(default=512, ge=256, le=1024)


class ImageGenerationResponse(BaseModel):
    id: UUID
    prompt: str
    provider: str
    model: str
    status: str
    image_url: str | None = None
    width: int
    height: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ImageGenerationHistoryResponse(BaseModel):
    items: list[ImageGenerationResponse]
    total: int

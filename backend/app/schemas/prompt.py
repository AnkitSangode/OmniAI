
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PromptCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    content: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Prompt name cannot be empty.")
        return value

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Prompt content cannot be empty.")
        return value


class PromptUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    content: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Prompt name cannot be empty.")
        return value

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Prompt content cannot be empty.")
        return value


class PromptResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    current_version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PromptVersionResponse(BaseModel):
    id: UUID
    prompt_id: UUID
    version_number: int
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PromptDetailResponse(PromptResponse):
    latest_version: PromptVersionResponse


class PromptListResponse(BaseModel):
    items: list[PromptResponse]
    total: int
    limit: int
    offset: int

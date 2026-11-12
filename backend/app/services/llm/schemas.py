
from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: str = Field(pattern=r"^(system|user|assistant)$")
    content: str = Field(min_length=1)


class TextGenerationRequest(BaseModel):
    messages: list[LLMMessage] = Field(min_length=1)
    model: str | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=1024, ge=1, le=8192)


class TextGenerationResponse(BaseModel):
    request_id: str
    model: str
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

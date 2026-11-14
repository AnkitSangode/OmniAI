import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import Settings
from app.services.llm.schemas import (
    TextGenerationRequest,
    TextGenerationResponse,
)

logger = logging.getLogger(__name__)


class LiteLLMError(Exception):
    """Base exception for LiteLLM gateway failures."""


class LiteLLMTimeoutError(LiteLLMError):
    """Raised when the gateway request times out."""


class LiteLLMRequestError(LiteLLMError):
    """Raised when the gateway returns an unsuccessful response."""


class LiteLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = str(settings.LITELLM_BASE_URL).rstrip("/")
        self.api_key = settings.LITELLM_API_KEY
        self.timeout = settings.LITELLM_TIMEOUT_SECONDS
        self.default_model = settings.LITELLM_DEFAULT_MODEL

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    async def generate(
        self,
        request: TextGenerationRequest,
    ) -> TextGenerationResponse:
        payload: dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        try:
            response = await self._client.post(
                "/chat/completions",
                json=payload,
            )
            response.raise_for_status()

        except httpx.TimeoutException as exc:
            logger.warning("LiteLLM request timed out")
            raise LiteLLMTimeoutError(
                "The AI provider took too long to respond."
            ) from exc

        except httpx.HTTPStatusError as exc:
            logger.error(
                "LiteLLM returned HTTP %s",
                exc.response.status_code,
            )
            raise LiteLLMRequestError(
                "The AI gateway could not process the request."
            ) from exc

        except httpx.RequestError as exc:
            logger.error("Could not connect to LiteLLM: %s", exc)
            raise LiteLLMRequestError(
                "The AI gateway is currently unavailable."
            ) from exc

        data = response.json()

        try:
            choice = data["choices"][0]
            usage = data.get("usage") or {}

            content = choice["message"]["content"]

            if not isinstance(content, str):
                raise ValueError("Unexpected response content format")

            return TextGenerationResponse(
                request_id=data["id"],
                model=data.get("model", payload["model"]),
                content=content,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )

        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.exception("Invalid response received from LiteLLM")
            raise LiteLLMRequestError(
                "The AI gateway returned an invalid response."
            ) from exc

    async def close(self) -> None:
        await self._client.aclose()

    async def stream(
        self,
        request: TextGenerationRequest,
    ) -> AsyncIterator[dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        try:
            async with self._client.stream(
                "POST",
                "/chat/completions",
                json=payload,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    data = line[len("data:") :].strip()

                    if data == "[DONE]":
                        yield {"type": "done"}
                        return

                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise LiteLLMRequestError(
                            "Invalid streaming response from gateway."
                        ) from exc

                    usage = chunk.get("usage")

                    if usage:
                        yield {
                            "type": "usage",
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                            "total_tokens": usage.get("total_tokens", 0),
                        }

                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        content = delta.get("content")

                        if isinstance(content, str) and content:
                            yield {
                                "type": "content",
                                "content": content,
                            }

                        if choice.get("finish_reason"):
                            yield {
                                "type": "finish",
                                "reason": choice["finish_reason"],
                            }

        except httpx.TimeoutException as exc:
            raise LiteLLMTimeoutError("The AI provider timed out.") from exc

        except httpx.HTTPStatusError as exc:
            logger.error(
                "LiteLLM streaming request failed with HTTP %s",
                exc.response.status_code,
            )
            raise LiteLLMRequestError(
                "The AI gateway could not process the streaming request."
            ) from exc

        except httpx.RequestError as exc:
            raise LiteLLMRequestError(
                "The AI gateway is currently unavailable."
            ) from exc

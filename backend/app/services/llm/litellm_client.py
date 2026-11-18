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

# Keep diagnostic response bodies bounded. Provider errors should be useful
# for debugging, but we should not dump arbitrary large responses into logs.
_MAX_ERROR_BODY_LENGTH = 2000


class LiteLLMError(Exception):
    """Base exception for LiteLLM gateway failures."""


class LiteLLMTimeoutError(LiteLLMError):
    """Raised when the gateway request times out."""


class LiteLLMRequestError(LiteLLMError):
    """Raised when the gateway returns an unsuccessful response."""


def _get_error_body(response: httpx.Response) -> str:
    """Return a bounded response body for diagnostics."""
    try:
        body = response.text.strip()
    except Exception:
        return "<response body unavailable>"

    if not body:
        return "<empty response body>"

    if len(body) > _MAX_ERROR_BODY_LENGTH:
        return body[:_MAX_ERROR_BODY_LENGTH] + "...<truncated>"

    return body


class LiteLLMClient:
    def __init__(self, settings: Settings) -> None:
        # Keep /v1 (or any configured API prefix) in the base URL.
        # Requests below use relative paths without a leading slash.
        self.base_url = str(settings.LITELLM_BASE_URL).rstrip("/") + "/"
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

    def _build_payload(
        self,
        request: TextGenerationRequest,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": [
                message.model_dump() for message in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}

        return payload

    async def generate(
        self,
        request: TextGenerationRequest,
    ) -> TextGenerationResponse:
        payload = self._build_payload(request)

        try:
            response = await self._client.post(
                "chat/completions",
                json=payload,
            )
            response.raise_for_status()

        except httpx.TimeoutException as exc:
            logger.exception(
                "LiteLLM request timed out. Base URL: %s | Model: %s",
                self.base_url,
                payload["model"],
            )
            raise LiteLLMTimeoutError(
                "The AI provider took too long to respond."
            ) from exc

        except httpx.HTTPStatusError as exc:
            error_body = _get_error_body(exc.response)
            logger.error(
                "LiteLLM request failed. Status: %s | URL: %s | Model: %s "
                "| Response: %s",
                exc.response.status_code,
                exc.request.url,
                payload["model"],
                error_body,
            )
            raise LiteLLMRequestError(
                "The AI gateway could not process the request."
            ) from exc

        except httpx.RequestError as exc:
            logger.exception(
                "Could not connect to LiteLLM. Base URL: %s | Model: %s",
                self.base_url,
                payload["model"],
            )
            raise LiteLLMRequestError(
                "The AI gateway is currently unavailable."
            ) from exc

        try:
            data = response.json()
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

        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
            logger.exception(
                "Invalid response received from LiteLLM. Model: %s | "
                "Status: %s | Response: %s",
                payload["model"],
                response.status_code,
                _get_error_body(response),
            )
            raise LiteLLMRequestError(
                "The AI gateway returned an invalid response."
            ) from exc

    async def stream(
        self,
        request: TextGenerationRequest,
    ) -> AsyncIterator[dict[str, Any]]:
        payload = self._build_payload(request, stream=True)

        try:
            async with self._client.stream(
                "POST",
                "chat/completions",
                json=payload,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    data = line[len("data:"):].strip()

                    if data == "[DONE]":
                        yield {"type": "done"}
                        return

                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError as exc:
                        logger.error(
                            "Invalid JSON in LiteLLM stream. Model: %s | "
                            "Data: %s",
                            payload["model"],
                            data[:_MAX_ERROR_BODY_LENGTH],
                        )
                        raise LiteLLMRequestError(
                            "Invalid streaming response from gateway."
                        ) from exc

                    # Some OpenAI-compatible providers may send an error
                    # object inside an otherwise HTTP-200 SSE response.
                    if chunk.get("error"):
                        error = chunk["error"]
                        logger.error(
                            "LiteLLM returned an in-stream error. Model: %s "
                            "| Error: %s",
                            payload["model"],
                            str(error)[:_MAX_ERROR_BODY_LENGTH],
                        )
                        raise LiteLLMRequestError(
                            "The AI gateway returned a streaming error."
                        )

                    usage = chunk.get("usage")
                    if usage:
                        yield {
                            "type": "usage",
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get(
                                "completion_tokens", 0
                            ),
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

                        finish_reason = choice.get("finish_reason")
                        if finish_reason:
                            yield {
                                "type": "finish",
                                "finish_reason": finish_reason,
                            }

        except httpx.TimeoutException as exc:
            logger.exception(
                "LiteLLM streaming request timed out. Base URL: %s | "
                "Model: %s",
                self.base_url,
                payload["model"],
            )
            raise LiteLLMTimeoutError(
                "The AI provider timed out."
            ) from exc

        except httpx.HTTPStatusError as exc:
            error_body = _get_error_body(exc.response)
            logger.error(
                "LiteLLM streaming request failed. Status: %s | URL: %s "
                "| Model: %s | Response: %s",
                exc.response.status_code,
                exc.request.url,
                payload["model"],
                error_body,
            )
            raise LiteLLMRequestError(
                "The AI gateway could not process the streaming request."
            ) from exc

        except httpx.RequestError as exc:
            logger.exception(
                "Could not connect to LiteLLM for streaming. "
                "Base URL: %s | Model: %s",
                self.base_url,
                payload["model"],
            )
            raise LiteLLMRequestError(
                "The AI gateway is currently unavailable."
            ) from exc

    async def close(self) -> None:
        await self._client.aclose()

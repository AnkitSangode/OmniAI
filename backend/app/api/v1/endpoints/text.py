
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.core.config import get_settings
from app.models.user import User
from app.repositories.usage_repository import UsageRepository
from app.services.llm.litellm_client import (
    LiteLLMClient,
    LiteLLMError,
    LiteLLMTimeoutError,
)
from app.services.llm.schemas import (
    TextGenerationRequest,
    TextGenerationResponse,
)
from app.services.usage_service import UsageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/text", tags=["Text AI"])


def get_usage_service(
    db: AsyncSession = Depends(get_db),
) -> UsageService:
    settings = get_settings()

    repository = UsageRepository(db)

    return UsageService(
        repository=repository,
        model_pricing=settings.LLM_MODEL_PRICING,
    )


async def record_usage_safely(
    service: UsageService,
    **kwargs,
) -> None:
    """
    Usage logging must never break the primary AI request.
    """
    try:
        await service.record_request(**kwargs)

    except Exception:
        logger.exception(
            "Usage recording failed for request %s",
            kwargs.get("request_id"),
        )


@router.post(
    "/generate",
    response_model=TextGenerationResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_text(
    payload: TextGenerationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    usage_service: UsageService = Depends(get_usage_service),
):
    client: LiteLLMClient = request.app.state.litellm_client

    application_request_id = str(uuid.uuid4())
    requested_model = payload.model or client.default_model

    start_time = time.perf_counter()

    try:
        result = await client.generate(payload)

        latency_ms = int(
            (time.perf_counter() - start_time) * 1000
        )

        await record_usage_safely(
            usage_service,
            user_id=current_user.id,
            request_id=application_request_id,
            provider_request_id=result.request_id,
            request_type="generate",
            model=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            latency_ms=latency_ms,
            status="success",
        )

        return result

    except LiteLLMTimeoutError:
        latency_ms = int(
            (time.perf_counter() - start_time) * 1000
        )

        await record_usage_safely(
            usage_service,
            user_id=current_user.id,
            request_id=application_request_id,
            request_type="generate",
            model=requested_model,
            latency_ms=latency_ms,
            status="failed",
            error_code="timeout",
        )

        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI generation timed out. Please try again.",
        )

    except LiteLLMError:
        latency_ms = int(
            (time.perf_counter() - start_time) * 1000
        )

        await record_usage_safely(
            usage_service,
            user_id=current_user.id,
            request_id=application_request_id,
            request_type="generate",
            model=requested_model,
            latency_ms=latency_ms,
            status="failed",
            error_code="gateway_error",
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI generation service is currently unavailable.",
        )


@router.post("/stream")
async def stream_text(
    payload: TextGenerationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    usage_service: UsageService = Depends(get_usage_service),
):
    client: LiteLLMClient = request.app.state.litellm_client

    application_request_id = str(uuid.uuid4())
    requested_model = payload.model or client.default_model

    async def event_generator():
        start_time = time.perf_counter()

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        request_status = "failed"
        error_code = "incomplete_stream"
        stream_completed = False

        try:
            async for event in client.stream(payload):
                if await request.is_disconnected():
                    request_status = "cancelled"
                    error_code = "client_disconnected"
                    break

                if event.get("type") == "usage":
                    prompt_tokens = event.get(
                        "prompt_tokens", 0
                    )
                    completion_tokens = event.get(
                        "completion_tokens", 0
                    )
                    total_tokens = event.get(
                        "total_tokens", 0
                    )

                if event.get("type") == "done":
                    request_status = "success"
                    error_code = None
                    stream_completed = True

                yield f"data: {json.dumps(event)}\n\n"

        except LiteLLMTimeoutError:
            request_status = "failed"
            error_code = "timeout"

            error_event = {
                "type": "error",
                "message": "AI generation timed out.",
            }

            yield f"data: {json.dumps(error_event)}\n\n"

        except LiteLLMError:
            request_status = "failed"
            error_code = "gateway_error"

            error_event = {
                "type": "error",
                "message": "AI generation service is unavailable.",
            }

            yield f"data: {json.dumps(error_event)}\n\n"

        finally:
            latency_ms = int(
                (time.perf_counter() - start_time) * 1000
            )

            await record_usage_safely(
                usage_service,
                user_id=current_user.id,
                request_id=application_request_id,
                request_type="stream",
                model=requested_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms,
                status=request_status,
                error_code=error_code,
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

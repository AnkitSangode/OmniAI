
import json
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.repositories.usage_repository import UsageRepository
from app.services.llm.litellm_client import (
    LiteLLMClient,
    LiteLLMError,
    LiteLLMRequestError,
    LiteLLMTimeoutError,
)
from app.services.llm.schemas import (
    TextGenerationRequest,
    TextGenerationResponse,
)
from app.services.observability.langfuse_service import (
    LangfuseService,
    get_langfuse_service,
)
from app.services.safety.llama_guard import LlamaGuardModerator
from app.services.safety.safety_service import SafetyService
from app.services.safety.schemas import (
    SafetyServiceUnavailable,
    UnsafeContentError,
)
from app.services.usage_service import UsageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/text", tags=["Text AI"])


def get_llm_client(request: Request) -> LiteLLMClient:
    return request.app.state.litellm_client


def get_usage_service(
    db: AsyncSession = Depends(get_db),
) -> UsageService:
    settings = get_settings()
    repository = UsageRepository(session=db)

    return UsageService(
        repository=repository,
        model_pricing=settings.LLM_MODEL_PRICING,
    )


def get_observability_service() -> LangfuseService:
    return get_langfuse_service()


def get_safety_service() -> SafetyService | None:
    settings = get_settings()

    if not settings.SAFETY_ENABLED:
        return None

    if settings.SAFETY_PROVIDER != "llama_guard":
        raise RuntimeError(
            f"Unsupported safety provider: {settings.SAFETY_PROVIDER}"
        )

    moderator = LlamaGuardModerator(
        base_url=settings.SAFETY_BASE_URL,
        model=settings.SAFETY_MODEL,
        api_key=settings.SAFETY_API_KEY,
        timeout_seconds=settings.SAFETY_TIMEOUT_SECONDS,
    )

    return SafetyService(moderator=moderator)


def create_sse_event(event: dict) -> str:
    """Convert an event dictionary into an SSE message."""
    return f"data: {json.dumps(event)}\n\n"


def calculate_cost_safely(
    usage_service: UsageService,
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
):
    try:
        return usage_service.calculate_cost(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except Exception:
        logger.exception("Failed to calculate estimated LLM cost.")
        return None


def update_observability_safely(
    observability: LangfuseService,
    *,
    generation,
    status_value: str,
    request_type: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    estimated_cost=None,
    error_code: str | None = None,
) -> None:
    """Observability failures must not break the AI request."""
    try:
        observability.update_generation(
            generation=generation,
            status=status_value,
            request_type=request_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            actual_model=model,
            estimated_cost=estimated_cost,
            error_code=error_code,
        )
    except Exception:
        logger.exception("Failed to update Langfuse generation.")


async def record_usage_safely(
    usage_service: UsageService,
    *,
    request_id: str,
    user_id,
    request_type: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    latency_ms: int = 0,
    status_value: str = "success",
    provider_request_id: str | None = None,
    error_code: str | None = None,
) -> None:
    """Usage tracking must never break an otherwise successful request."""
    try:
        await usage_service.record_request(
            request_id=request_id,
            provider_request_id=provider_request_id,
            user_id=user_id,
            request_type=request_type,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            status=status_value,
            error_code=error_code,
        )
    except Exception:
        logger.exception(
            "Failed to record usage for request %s",
            request_id,
        )


async def moderate_input(
    safety_service: SafetyService | None,
    payload: TextGenerationRequest,
) -> None:
    """Moderate user messages before they reach the LLM."""
    if safety_service is None:
        return

    for message in payload.messages:
        if message.role == "user":
            await safety_service.check_input(message.content)


def raise_safety_http_exception(exc: Exception) -> None:
    """Translate safety exceptions into appropriate HTTP responses."""
    if isinstance(exc, UnsafeContentError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "unsafe_input",
                "message": "Your prompt was blocked by safety moderation.",
                "categories": list(exc.categories),
            },
        ) from exc

    if isinstance(exc, SafetyServiceUnavailable):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Safety moderation is temporarily unavailable.",
        ) from exc

    raise exc


@router.post(
    "/generate",
    response_model=TextGenerationResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_text(
    payload: TextGenerationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    llm_client: LiteLLMClient = Depends(get_llm_client),
    usage_service: UsageService = Depends(get_usage_service),
    observability: LangfuseService = Depends(get_observability_service),
    safety_service: SafetyService | None = Depends(get_safety_service),
):
    request_id = str(uuid4())
    model = payload.model or llm_client.default_model
    started_at = perf_counter()
    generation = None

    # Input moderation must happen before calling LiteLLM.
    try:
        await moderate_input(safety_service, payload)
    except (UnsafeContentError, SafetyServiceUnavailable) as exc:
        raise_safety_http_exception(exc)

    try:
        with observability.trace_generation(
            request_id=request_id,
            user_id=str(current_user.id),
            request_type="generate",
            model=model,
        ) as generation:
            response = await llm_client.generate(payload)

            # Moderate the newly generated response before returning it.
            if safety_service is not None:
                try:
                    await safety_service.check_output(response.content)
                except UnsafeContentError:
                    latency_ms = int(
                        (perf_counter() - started_at) * 1000
                    )

                    estimated_cost = calculate_cost_safely(
                        usage_service,
                        model=response.model,
                        prompt_tokens=response.prompt_tokens,
                        completion_tokens=response.completion_tokens,
                    )

                    update_observability_safely(
                        observability,
                        generation=generation,
                        status_value="error",
                        request_type="generate",
                        model=response.model,
                        prompt_tokens=response.prompt_tokens,
                        completion_tokens=response.completion_tokens,
                        total_tokens=response.total_tokens,
                        estimated_cost=estimated_cost,
                        error_code="unsafe_model_output",
                    )

                    await record_usage_safely(
                        usage_service,
                        request_id=request_id,
                        provider_request_id=response.request_id,
                        user_id=current_user.id,
                        request_type="generate",
                        model=response.model,
                        prompt_tokens=response.prompt_tokens,
                        completion_tokens=response.completion_tokens,
                        total_tokens=response.total_tokens,
                        latency_ms=latency_ms,
                        status_value="failed",
                        error_code="unsafe_model_output",
                    )

                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail={
                            "code": "unsafe_model_output",
                            "message": (
                                "The generated response was blocked "
                                "by safety moderation."
                            ),
                        },
                    )

                except SafetyServiceUnavailable as exc:
                    latency_ms = int(
                        (perf_counter() - started_at) * 1000
                    )

                    update_observability_safely(
                        observability,
                        generation=generation,
                        status_value="error",
                        request_type="generate",
                        model=response.model,
                        prompt_tokens=response.prompt_tokens,
                        completion_tokens=response.completion_tokens,
                        total_tokens=response.total_tokens,
                        error_code="safety_unavailable",
                    )

                    await record_usage_safely(
                        usage_service,
                        request_id=request_id,
                        provider_request_id=response.request_id,
                        user_id=current_user.id,
                        request_type="generate",
                        model=response.model,
                        prompt_tokens=response.prompt_tokens,
                        completion_tokens=response.completion_tokens,
                        total_tokens=response.total_tokens,
                        latency_ms=latency_ms,
                        status_value="failed",
                        error_code="safety_unavailable",
                    )

                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=(
                            "Safety moderation is temporarily unavailable."
                        ),
                    ) from exc

            latency_ms = int(
                (perf_counter() - started_at) * 1000
            )

            estimated_cost = calculate_cost_safely(
                usage_service,
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
            )

            update_observability_safely(
                observability,
                generation=generation,
                status_value="success",
                request_type="generate",
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                estimated_cost=estimated_cost,
            )

            await record_usage_safely(
                usage_service,
                request_id=request_id,
                provider_request_id=response.request_id,
                user_id=current_user.id,
                request_type="generate",
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                latency_ms=latency_ms,
                status_value="success",
            )

            return response

    except HTTPException:
        raise

    except LiteLLMTimeoutError as exc:
        latency_ms = int((perf_counter() - started_at) * 1000)

        update_observability_safely(
            observability,
            generation=generation,
            status_value="error",
            request_type="generate",
            model=model,
            error_code="llm_timeout",
        )

        await record_usage_safely(
            usage_service,
            request_id=request_id,
            user_id=current_user.id,
            request_type="generate",
            model=model,
            latency_ms=latency_ms,
            status_value="failed",
            error_code="llm_timeout",
        )

        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI generation request timed out.",
        ) from exc

    except LiteLLMRequestError as exc:
        latency_ms = int((perf_counter() - started_at) * 1000)

        update_observability_safely(
            observability,
            generation=generation,
            status_value="error",
            request_type="generate",
            model=model,
            error_code="llm_gateway_error",
        )

        await record_usage_safely(
            usage_service,
            request_id=request_id,
            user_id=current_user.id,
            request_type="generate",
            model=model,
            latency_ms=latency_ms,
            status_value="failed",
            error_code="llm_gateway_error",
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI generation service is unavailable.",
        ) from exc

    except LiteLLMError as exc:
        latency_ms = int((perf_counter() - started_at) * 1000)

        update_observability_safely(
            observability,
            generation=generation,
            status_value="error",
            request_type="generate",
            model=model,
            error_code="llm_gateway_error",
        )

        await record_usage_safely(
            usage_service,
            request_id=request_id,
            user_id=current_user.id,
            request_type="generate",
            model=model,
            latency_ms=latency_ms,
            status_value="failed",
            error_code="llm_gateway_error",
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI generation service is unavailable.",
        ) from exc


@router.post("/stream")
async def stream_text(
    payload: TextGenerationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    llm_client: LiteLLMClient = Depends(get_llm_client),
    usage_service: UsageService = Depends(get_usage_service),
    observability: LangfuseService = Depends(get_observability_service),
    safety_service: SafetyService | None = Depends(get_safety_service),
):
    request_id = str(uuid4())
    model = payload.model or llm_client.default_model

    async def event_generator():
        started_at = perf_counter()

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        request_status = "success"
        error_code = None
        generation = None

        buffered_content: list[str] = []
        pending_events: list[dict] = []

        with observability.trace_generation(
            request_id=request_id,
            user_id=str(current_user.id),
            request_type="stream",
            model=model,
        ) as generation:
            try:
                # Reject unsafe prompts before starting generation.
                await moderate_input(safety_service, payload)

                async for event in llm_client.stream(payload):
                    if await request.is_disconnected():
                        request_status = "cancelled"
                        error_code = "client_disconnected"
                        break

                    event_type = event.get("type")

                    if event_type == "content":
                        content = event.get("content", "")

                        if safety_service is not None:
                            # Do not expose unmoderated output.
                            buffered_content.append(content)
                        else:
                            yield create_sse_event({
                                "type": "content",
                                "content": content,
                            })

                    elif event_type == "usage":
                        prompt_tokens = event.get("prompt_tokens", 0)
                        completion_tokens = event.get(
                            "completion_tokens", 0
                        )
                        total_tokens = event.get("total_tokens", 0)

                        usage_event = {
                            "type": "usage",
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": total_tokens,
                        }

                        if safety_service is not None:
                            pending_events.append(usage_event)
                        else:
                            yield create_sse_event(usage_event)

                    elif event_type == "finish":
                        finish_event = {
                            "type": "finish",
                            "finish_reason": event.get("finish_reason"),
                        }

                        if safety_service is not None:
                            pending_events.append(finish_event)
                        else:
                            yield create_sse_event(finish_event)

                    elif event_type == "done":
                        if safety_service is not None:
                            complete_content = "".join(buffered_content)

                            await safety_service.check_output(
                                complete_content
                            )

                            if complete_content:
                                yield create_sse_event({
                                    "type": "content",
                                    "content": complete_content,
                                })

                            for pending_event in pending_events:
                                yield create_sse_event(pending_event)

                        yield create_sse_event({
                            "type": "done",
                            "request_id": request_id,
                        })

            except UnsafeContentError as exc:
                request_status = "failed"

                if buffered_content:
                    error_code = "unsafe_model_output"
                    message = (
                        "The generated response was blocked "
                        "by safety moderation."
                    )
                else:
                    error_code = "unsafe_input"
                    message = (
                        "Your prompt was blocked by safety moderation."
                    )

                yield create_sse_event({
                    "type": "error",
                    "message": message,
                    "code": error_code,
                    "categories": list(exc.categories),
                })

            except SafetyServiceUnavailable:
                request_status = "failed"
                error_code = "safety_unavailable"

                yield create_sse_event({
                    "type": "error",
                    "message": (
                        "Safety moderation is temporarily unavailable."
                    ),
                    "code": error_code,
                })

            except LiteLLMTimeoutError:
                request_status = "failed"
                error_code = "llm_timeout"

                yield create_sse_event({
                    "type": "error",
                    "message": "AI generation request timed out.",
                    "code": error_code,
                })

            except LiteLLMRequestError:
                request_status = "failed"
                error_code = "llm_gateway_error"

                yield create_sse_event({
                    "type": "error",
                    "message": "AI generation service is unavailable.",
                    "code": error_code,
                })

            except LiteLLMError:
                request_status = "failed"
                error_code = "llm_gateway_error"

                yield create_sse_event({
                    "type": "error",
                    "message": "AI generation service is unavailable.",
                    "code": error_code,
                })

            except Exception:
                request_status = "failed"
                error_code = "internal_stream_error"

                logger.exception(
                    "Unexpected streaming error. Request ID: %s",
                    request_id,
                )

                yield create_sse_event({
                    "type": "error",
                    "message": "An unexpected error occurred.",
                    "code": error_code,
                })

            finally:
                latency_ms = int(
                    (perf_counter() - started_at) * 1000
                )

                estimated_cost = calculate_cost_safely(
                    usage_service,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

                update_observability_safely(
                    observability,
                    generation=generation,
                    status_value=request_status,
                    request_type="stream",
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    estimated_cost=estimated_cost,
                    error_code=error_code,
                )

                await record_usage_safely(
                    usage_service,
                    request_id=request_id,
                    user_id=current_user.id,
                    request_type="stream",
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency_ms,
                    status_value=request_status,
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


"""Best-effort usage tracking shared by non-text AI services."""

import logging
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.usage_repository import UsageRepository
from app.services.usage_service import UsageService

logger = logging.getLogger(__name__)


def build_usage_service(session: AsyncSession) -> UsageService:
    """Create a UsageService using the application's configured pricing."""
    settings = get_settings()

    return UsageService(
        repository=UsageRepository(session=session),
        model_pricing=settings.LLM_MODEL_PRICING,
    )


async def record_usage_safely(
    usage_service: UsageService | None,
    *,
    user_id,
    request_type: str,
    model: str,
    latency_ms: int,
    status: str,
    request_id: str | None = None,
    error_code: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    provider_request_id: str | None = None,
    estimated_cost_override: Decimal | None = None,
) -> None:
    """Persist analytics without allowing telemetry to break user work.

    Call this only after the task's own transaction has been committed.
    The UsageService owns its commit/rollback for the usage record.
    """

    if usage_service is None:
        return

    try:
        await usage_service.record_request(
            user_id=user_id,
            request_id=request_id or str(uuid4()),
            request_type=request_type,
            model=model or "unknown",
            latency_ms=max(0, latency_ms),
            status=status,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            provider_request_id=provider_request_id,
            error_code=error_code,
            estimated_cost_override=estimated_cost_override,
        )

    except Exception:
        logger.exception(
            "Usage tracking failed for request %s; "
            "application operation remains unaffected.",
            request_id,
        )

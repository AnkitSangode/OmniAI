
"""Usage analytics and cost calculation service."""

import logging
import uuid
from decimal import Decimal
from typing import Any

from app.models.usage import UsageRecord
from app.repositories.usage_repository import UsageRepository

logger = logging.getLogger(__name__)


class UsageService:
    def __init__(
        self,
        repository: UsageRepository,
        model_pricing: dict[str, dict[str, Any]],
    ) -> None:
        self.repository = repository
        self.model_pricing = model_pricing

    def calculate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> Decimal | None:
        """Calculate LLM cost using configured per-million-token rates."""
        pricing = self.model_pricing.get(model)

        if not pricing:
            return None

        input_rate = pricing.get("input_per_1m")
        output_rate = pricing.get("output_per_1m")

        if input_rate is None or output_rate is None:
            return None

        input_cost = (
            Decimal(prompt_tokens)
            * Decimal(str(input_rate))
            / Decimal(1_000_000)
        )

        output_cost = (
            Decimal(completion_tokens)
            * Decimal(str(output_rate))
            / Decimal(1_000_000)
        )

        return input_cost + output_cost

    async def record_request(
        self,
        *,
        user_id: uuid.UUID,
        request_id: str,
        request_type: str,
        model: str,
        latency_ms: int,
        status: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        provider_request_id: str | None = None,
        error_code: str | None = None,
        estimated_cost_override: Decimal | None = None,
    ) -> UsageRecord:
        """Persist usage metrics and an optional externally calculated cost."""

        estimated_cost = None

        if status == "success":
            if estimated_cost_override is not None:
                # Used by services with non-token pricing, such as image generation.
                estimated_cost = estimated_cost_override
            else:
                # Default behavior remains token-based LLM pricing.
                estimated_cost = self.calculate_cost(
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

        record = UsageRecord(
            request_id=request_id,
            provider_request_id=provider_request_id,
            user_id=user_id,
            request_type=request_type,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
            latency_ms=max(0, latency_ms),
            status=status,
            error_code=error_code,
        )

        try:
            await self.repository.create(record)
            await self.repository.session.commit()
            return record

        except Exception:
            await self.repository.session.rollback()
            logger.exception(
                "Failed to persist usage record %s",
                request_id,
            )
            raise

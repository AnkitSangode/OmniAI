from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.analytics_service import AnalyticsService


class FakeAnalyticsRepository:
    async def get_summary(self, **kwargs):
        return {
            "total_requests": 4,
            "successful_requests": 3,
            "failed_requests": 1,
            "total_tokens": 120,
            "estimated_cost_usd": Decimal("0.0125"),
            "requests_without_cost": 1,
            "average_latency_ms": 250.0,
            "success_rate": 75.0,
        }

    async def get_modality_breakdown(self, **kwargs):
        return [{
            "modality": "text",
            "requests": 4,
            "successful_requests": 3,
            "failed_requests": 1,
            "total_tokens": 120,
            "estimated_cost_usd": Decimal("0.0125"),
            "average_latency_ms": 250.0,
        }]

    async def get_model_breakdown(self, **kwargs):
        return [{
            "model": "omni-primary",
            "requests": 4,
            "total_tokens": 120,
            "estimated_cost_usd": Decimal("0.0125"),
            "average_latency_ms": 250.0,
        }]

    async def get_daily_usage(self, **kwargs):
        return [{
            "day": date(2026, 11, 16),
            "requests": 4,
            "total_tokens": 120,
            "estimated_cost_usd": Decimal("0.0125"),
        }]


@pytest.mark.asyncio
async def test_overview_builds_typed_analytics_response():
    service = AnalyticsService(FakeAnalyticsRepository())
    user_id = uuid4()

    result = await service.get_overview(
        user_id=user_id,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 30),
    )

    assert result.summary.total_requests == 4
    assert result.summary.success_rate == 75.0
    assert result.summary.total_tokens == 120
    assert result.summary.estimated_cost_usd == pytest.approx(0.0125)
    assert result.by_modality[0].modality == "text"
    assert result.by_model[0].model == "omni-primary"
    assert result.daily[0].day == date(2026, 11, 16)

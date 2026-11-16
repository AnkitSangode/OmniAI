from datetime import date
from uuid import UUID

from app.repositories.analytics_repository import AnalyticsRepository
from app.schemas.analytics import (
    AnalyticsOverviewResponse,
    AnalyticsSummary,
    DailyUsage,
    ModelBreakdown,
    ModalityBreakdown,
)


class AnalyticsService:
    def __init__(self, repository: AnalyticsRepository) -> None:
        self.repository = repository

    async def get_overview(
        self, *, user_id: UUID, start_date: date, end_date: date
    ) -> AnalyticsOverviewResponse:
        summary = await self.repository.get_summary(
            user_id=user_id, start_date=start_date, end_date=end_date
        )
        modalities = await self.repository.get_modality_breakdown(
            user_id=user_id, start_date=start_date, end_date=end_date
        )
        models = await self.repository.get_model_breakdown(
            user_id=user_id, start_date=start_date, end_date=end_date
        )
        daily = await self.repository.get_daily_usage(
            user_id=user_id, start_date=start_date, end_date=end_date
        )

        return AnalyticsOverviewResponse(
            start_date=start_date,
            end_date=end_date,
            summary=AnalyticsSummary(**summary),
            by_modality=[ModalityBreakdown(**row) for row in modalities],
            by_model=[ModelBreakdown(**row) for row in models],
            daily=[DailyUsage(**row) for row in daily],
        )

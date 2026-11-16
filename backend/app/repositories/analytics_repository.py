from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import UsageRecord


class AnalyticsRepository:
    """Read-only, user-scoped aggregate queries over usage_records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _date_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
        start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        end_exclusive = datetime.combine(
            end_date + timedelta(days=1), time.min, tzinfo=timezone.utc
        )
        return start, end_exclusive

    @staticmethod
    def _modality_expression():
        # Existing text tracking stores "generate" and "stream".
        return case(
            (UsageRecord.request_type.in_(("generate", "stream", "text")), "text"),
            (UsageRecord.request_type.in_(("image", "audio", "video")), UsageRecord.request_type),
            else_="other",
        ).label("modality")

    def _filters(self, user_id: UUID, start: datetime, end: datetime):
        return (
            UsageRecord.user_id == user_id,
            UsageRecord.created_at >= start,
            UsageRecord.created_at < end,
        )

    async def get_summary(
        self, *, user_id: UUID, start_date: date, end_date: date
    ) -> dict:
        start, end = self._date_bounds(start_date, end_date)
        success_count = func.count().filter(UsageRecord.status == "success")
        failed_count = func.count().filter(UsageRecord.status != "success")
        statement = select(
            func.count().label("total_requests"),
            success_count.label("successful_requests"),
            failed_count.label("failed_requests"),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
            func.sum(UsageRecord.estimated_cost).label("estimated_cost_usd"),
            func.count().filter(
                (UsageRecord.status == "success")
                & UsageRecord.estimated_cost.is_(None)
            ).label("requests_without_cost"),
            func.coalesce(func.avg(UsageRecord.latency_ms), 0).label("average_latency_ms"),
        ).where(*self._filters(user_id, start, end))
        row = (await self.session.execute(statement)).mappings().one()
        data = dict(row)
        total = int(data["total_requests"] or 0)
        successful = int(data["successful_requests"] or 0)
        data["success_rate"] = (successful / total * 100) if total else 0.0
        return data

    async def get_modality_breakdown(
        self, *, user_id: UUID, start_date: date, end_date: date
    ) -> list[dict]:
        start, end = self._date_bounds(start_date, end_date)
        modality = self._modality_expression()
        statement = (
            select(
                modality,
                func.count().label("requests"),
                func.count().filter(UsageRecord.status == "success").label("successful_requests"),
                func.count().filter(UsageRecord.status != "success").label("failed_requests"),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
                func.sum(UsageRecord.estimated_cost).label("estimated_cost_usd"),
                func.coalesce(func.avg(UsageRecord.latency_ms), 0).label("average_latency_ms"),
            )
            .where(*self._filters(user_id, start, end))
            .group_by(modality)
            .order_by(func.count().desc())
        )
        rows = (await self.session.execute(statement)).mappings().all()
        return [dict(row) for row in rows]

    async def get_model_breakdown(
        self, *, user_id: UUID, start_date: date, end_date: date
    ) -> list[dict]:
        start, end = self._date_bounds(start_date, end_date)
        statement = (
            select(
                UsageRecord.model,
                func.count().label("requests"),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
                func.sum(UsageRecord.estimated_cost).label("estimated_cost_usd"),
                func.coalesce(func.avg(UsageRecord.latency_ms), 0).label("average_latency_ms"),
            )
            .where(*self._filters(user_id, start, end))
            .group_by(UsageRecord.model)
            .order_by(func.count().desc())
        )
        rows = (await self.session.execute(statement)).mappings().all()
        return [dict(row) for row in rows]

    async def get_daily_usage(
        self, *, user_id: UUID, start_date: date, end_date: date
    ) -> list[dict]:
        start, end = self._date_bounds(start_date, end_date)
        day = cast(UsageRecord.created_at, Date).label("day")
        statement = (
            select(
                day,
                func.count().label("requests"),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
                func.sum(UsageRecord.estimated_cost).label("estimated_cost_usd"),
            )
            .where(*self._filters(user_id, start, end))
            .group_by(day)
            .order_by(day)
        )
        rows = (await self.session.execute(statement)).mappings().all()
        return [dict(row) for row in rows]

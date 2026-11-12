
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import UsageRecord


class UsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        record: UsageRecord,
    ) -> UsageRecord:
        self.session.add(record)
        await self.session.flush()
        return record

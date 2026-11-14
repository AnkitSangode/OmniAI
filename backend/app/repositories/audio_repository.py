from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio_task import AudioTask


class AudioRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, task: AudioTask) -> AudioTask:
        self.session.add(task)
        await self.session.flush()
        return task

    async def get_by_id(
        self,
        task_id: UUID,
        user_id: UUID,
    ) -> AudioTask | None:
        result = await self.session.execute(
            select(AudioTask).where(
                AudioTask.id == task_id,
                AudioTask.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> list[AudioTask]:
        result = await self.session.execute(
            select(AudioTask)
            .where(AudioTask.user_id == user_id)
            .order_by(AudioTask.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_user(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(AudioTask)
            .where(AudioTask.user_id == user_id)
        )
        return result.scalar_one()
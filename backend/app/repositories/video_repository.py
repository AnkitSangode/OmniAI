
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.video_task import VideoTask


class VideoRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, task: VideoTask) -> VideoTask:
        self.session.add(task)
        await self.session.flush()
        return task

    async def get_by_id(
        self,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> VideoTask | None:
        statement = select(VideoTask).where(
            VideoTask.id == task_id,
            VideoTask.user_id == user_id,
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[VideoTask]:
        statement = (
            select(VideoTask)
            .where(VideoTask.user_id == user_id)
            .order_by(VideoTask.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_by_user(
        self,
        user_id: uuid.UUID,
    ) -> int:
        statement = (
            select(func.count(VideoTask.id))
            .where(VideoTask.user_id == user_id)
        )

        result = await self.session.execute(statement)
        return result.scalar_one()

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio_task import AudioTask
from app.repositories.audio_repository import AudioRepository
from app.storage.audio_storage import AudioStorageService


class AudioReadService:
    """Handles read-only audio operations."""

    def __init__(
        self,
        session: AsyncSession,
        storage: AudioStorageService,
    ):
        self.repository = AudioRepository(session)
        self.storage = storage

    async def get_task(
        self,
        task_id: UUID,
        user_id: UUID,
    ) -> AudioTask | None:
        return await self.repository.get_by_id(
            task_id=task_id,
            user_id=user_id,
        )

    async def get_history(
        self,
        user_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[AudioTask], int]:
        tasks = await self.repository.list_by_user(
            user_id=user_id,
            offset=offset,
            limit=limit,
        )

        total = await self.repository.count_by_user(user_id)

        return tasks, total
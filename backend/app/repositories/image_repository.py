
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_generation import ImageGeneration


class ImageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        generation: ImageGeneration,
    ) -> ImageGeneration:
        self.db.add(generation)

        await self.db.flush()

        return generation

    async def get_by_id(
        self,
        generation_id: UUID,
        user_id: UUID,
    ) -> ImageGeneration | None:

        statement = select(ImageGeneration).where(
            ImageGeneration.id == generation_id,
            ImageGeneration.user_id == user_id,
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ImageGeneration]:

        statement = (
            select(ImageGeneration)
            .where(ImageGeneration.user_id == user_id)
            .order_by(ImageGeneration.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(statement)

        return list(result.scalars().all())

    async def count_by_user(
        self,
        user_id: UUID,
    ) -> int:

        statement = (
            select(func.count())
            .select_from(ImageGeneration)
            .where(ImageGeneration.user_id == user_id)
        )

        result = await self.db.execute(statement)

        return result.scalar_one()

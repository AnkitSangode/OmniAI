
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_generation import ImageGeneration
from app.repositories.image_repository import ImageRepository
from app.schemas.image import (
    ImageGenerationHistoryResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
)
from app.services.images.base import ImageProvider
from app.storage.image_storage import ImageStorageService


class ImageService:
    def __init__(
        self,
        db: AsyncSession,
        provider: ImageProvider,
        storage: ImageStorageService,
    ):
        self.db = db
        self.repository = ImageRepository(db)
        self.provider = provider
        self.storage = storage

    async def generate(
        self,
        request: ImageGenerationRequest,
        user_id: UUID,
    ) -> ImageGenerationResponse:

        generation_id = uuid4()

        generation = ImageGeneration(
            id=generation_id,
            user_id=user_id,
            prompt=request.prompt,
            provider="mock",
            model="omniai-mock-v1",
            status="pending",
            width=request.width,
            height=request.height,
        )

        await self.repository.create(generation)
        await self.db.commit()

        try:
            generated = await self.provider.generate(
                prompt=request.prompt,
                width=request.width,
                height=request.height,
            )

            filename = await self.storage.save(
                generated.image_bytes,
                generation_id,
            )

            generation.image_path = filename
            generation.provider = generated.provider
            generation.model = generated.model
            generation.status = "completed"

            await self.db.commit()
            await self.db.refresh(generation)

            return self._to_response(generation)

        except Exception as exc:
            await self.db.rollback()

            failed_generation = await self.repository.get_by_id(
                generation_id,
                user_id,
            )

            if failed_generation is not None:
                failed_generation.status = "failed"
                failed_generation.error_message = str(exc)[:1000]
                await self.db.commit()

            raise

    async def get_generation(
        self,
        generation_id: UUID,
        user_id: UUID,
    ) -> ImageGenerationResponse | None:

        generation = await self.repository.get_by_id(
            generation_id,
            user_id,
        )

        if generation is None:
            return None

        return self._to_response(generation)

    async def get_history(
        self,
        user_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> ImageGenerationHistoryResponse:

        generations = await self.repository.list_by_user(
            user_id,
            offset,
            limit,
        )

        total = await self.repository.count_by_user(user_id)

        return ImageGenerationHistoryResponse(
            items=[
                self._to_response(item)
                for item in generations
            ],
            total=total,
        )

    @staticmethod
    def _to_response(
        generation: ImageGeneration,
    ) -> ImageGenerationResponse:

        return ImageGenerationResponse(
            id=generation.id,
            prompt=generation.prompt,
            provider=generation.provider,
            model=generation.model,
            status=generation.status,
            image_url=(
                f"/api/v1/images/{generation.id}/file"
                if generation.image_path
                else None
            ),
            width=generation.width,
            height=generation.height,
            created_at=generation.created_at,
        )

from time import perf_counter
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
from app.services.images.image_safety import (
    ImageSafetyResult,
    ImageSafetyService,
    ImageSafetyStatus,
    ImageSafetyUnavailable,
    UnsafeGeneratedImageError,
)
from app.services.images.watermark import ImageWatermarkService
from app.services.usage_service import UsageService
from app.services.usage_tracking import record_usage_safely
from app.storage.image_storage import ImageStorageService


class ImageService:
    def __init__(
        self,
        db: AsyncSession,
        provider: ImageProvider,
        storage: ImageStorageService,
        watermark: ImageWatermarkService | None = None,
        image_safety: ImageSafetyService | None = None,
        usage_service: UsageService | None = None,
    ):
        self.db = db
        self.repository = ImageRepository(db)
        self.provider = provider
        self.storage = storage
        self.watermark = watermark or ImageWatermarkService()
        # With no configured vision checker this returns NOT_CHECKED,
        # never APPROVED. Existing image generation remains usable.
        self.image_safety = image_safety or ImageSafetyService()
        self.usage_service = usage_service

    async def generate(
        self,
        request: ImageGenerationRequest,
        user_id: UUID,
    ) -> ImageGenerationResponse:
        generation_id = uuid4()
        started_at = perf_counter()

        generation = ImageGeneration(
            id=generation_id,
            user_id=user_id,
            prompt=request.prompt,
            provider="mock",
            model="omniai-mock-v1",
            status="pending",
            moderation_status=ImageSafetyStatus.NOT_CHECKED.value,
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

            # Inspect actual image bytes before watermarking or storage.
            safety_result: ImageSafetyResult = await self.image_safety.check(
                generated.image_bytes
            )
            generation.moderation_status = safety_result.status.value

            # NOT_CHECKED is allowed by the current V1 policy but remains explicit.
            watermarked_bytes = self.watermark.apply(generated.image_bytes)
            filename = await self.storage.save(watermarked_bytes, generation_id)

            generation.image_path = filename
            generation.provider = generated.provider
            generation.model = generated.model
            generation.status = "completed"

            await self.db.commit()
            await self.db.refresh(generation)

            await self._record_usage(
                generation=generation,
                user_id=user_id,
                started_at=started_at,
                status="success",
            )
            return self._to_response(generation)

        except UnsafeGeneratedImageError as exc:
            await self.db.rollback()
            rejected_generation = await self.repository.get_by_id(generation_id, user_id)
            if rejected_generation is not None:
                rejected_generation.status = "rejected"
                rejected_generation.moderation_status = ImageSafetyStatus.REJECTED.value
                rejected_generation.error_message = str(exc)[:1000]
                await self.db.commit()
                await self._record_usage(
                    generation=rejected_generation,
                    user_id=user_id,
                    started_at=started_at,
                    status="failed",
                    error_code=type(exc).__name__,
                )
            raise

        except ImageSafetyUnavailable as exc:
            await self._mark_generation_failed(generation_id, user_id, str(exc))
            failed_generation = await self.repository.get_by_id(generation_id, user_id)
            if failed_generation is not None:
                await self._record_usage(
                    generation=failed_generation,
                    user_id=user_id,
                    started_at=started_at,
                    status="failed",
                    error_code=type(exc).__name__,
                )
            raise

        except Exception as exc:
            await self._mark_generation_failed(generation_id, user_id, str(exc)[:1000])
            failed_generation = await self.repository.get_by_id(generation_id, user_id)
            if failed_generation is not None:
                await self._record_usage(
                    generation=failed_generation,
                    user_id=user_id,
                    started_at=started_at,
                    status="failed",
                    error_code=type(exc).__name__,
                )
            raise

    async def _record_usage(
        self,
        *,
        generation: ImageGeneration,
        user_id: UUID,
        started_at: float,
        status: str,
        error_code: str | None = None,
    ) -> None:
        await record_usage_safely(
            self.usage_service,
            user_id=user_id,
            request_id=str(generation.id),
            request_type="image",
            # Prefix provider so image models never accidentally match LLM token pricing.
            model=f"{generation.provider}/{generation.model}",
            latency_ms=int((perf_counter() - started_at) * 1000),
            status=status,
            error_code=error_code,
        )

    async def _mark_generation_failed(
        self,
        generation_id: UUID,
        user_id: UUID,
        error_message: str,
    ) -> None:
        await self.db.rollback()
        failed_generation = await self.repository.get_by_id(generation_id, user_id)
        if failed_generation is not None:
            failed_generation.status = "failed"
            failed_generation.error_message = error_message[:1000]
            await self.db.commit()

    async def get_generation(
        self,
        generation_id: UUID,
        user_id: UUID,
    ) -> ImageGenerationResponse | None:
        generation = await self.repository.get_by_id(generation_id, user_id)
        if generation is None:
            return None
        return self._to_response(generation)

    async def get_history(
        self,
        user_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> ImageGenerationHistoryResponse:
        generations = await self.repository.list_by_user(user_id, offset, limit)
        total = await self.repository.count_by_user(user_id)
        return ImageGenerationHistoryResponse(
            items=[self._to_response(item) for item in generations],
            total=total,
        )

    @staticmethod
    def _to_response(generation: ImageGeneration) -> ImageGenerationResponse:
        return ImageGenerationResponse(
            id=generation.id,
            prompt=generation.prompt,
            provider=generation.provider,
            model=generation.model,
            status=generation.status,
            moderation_status=generation.moderation_status,
            image_url=(f"/api/v1/images/{generation.id}/file" if generation.image_path else None),
            width=generation.width,
            height=generation.height,
            created_at=generation.created_at,
        )


from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.usage_tracking import build_usage_service

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.image import (
    ImageGenerationHistoryResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
)
from app.services.images.huggingface_provider import (
    HuggingFaceImageProvider,
)
from app.services.images.image_service import ImageService
from app.services.images.image_safety import (
    ImageSafetyService,
    ImageSafetyUnavailable,
    UnsafeGeneratedImageError,
)
from app.services.images.mock_provider import MockImageProvider
from app.services.safety.llama_guard import LlamaGuardModerator
from app.services.safety.safety_service import SafetyService
from app.services.safety.schemas import (
    SafetyServiceUnavailable,
    UnsafeContentError,
)
from app.storage.image_storage import ImageStorageService

router = APIRouter(prefix="/images", tags=["Image AI"])


def get_image_safety_service() -> SafetyService | None:
    """Build the configured text moderator for image prompts."""
    settings = get_settings()

    if not settings.SAFETY_ENABLED:
        return None

    if settings.SAFETY_PROVIDER != "llama_guard":
        raise RuntimeError(
            f"Unsupported safety provider: {settings.SAFETY_PROVIDER}"
        )

    moderator = LlamaGuardModerator(
        base_url=settings.SAFETY_BASE_URL,
        model=settings.SAFETY_MODEL,
        api_key=settings.SAFETY_API_KEY,
        timeout_seconds=settings.SAFETY_TIMEOUT_SECONDS,
    )

    return SafetyService(moderator=moderator)


async def moderate_image_prompt(
    safety_service: SafetyService | None,
    prompt: str,
) -> None:
    """Block unsafe image prompts before invoking the image provider."""
    if safety_service is None:
        return

    try:
        await safety_service.check_input(prompt)
    except UnsafeContentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "unsafe_input",
                "message": "Your image prompt was blocked by safety moderation.",
                "categories": list(exc.categories),
            },
        ) from exc
    except SafetyServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Safety moderation is temporarily unavailable.",
        ) from exc



def get_image_service(
    db: AsyncSession = Depends(get_db),
) -> ImageService:
    settings = get_settings()
    backend = settings.IMAGE_BACKEND.lower()

    if backend == "mock":
        provider = MockImageProvider()

    elif backend == "huggingface":
        if not settings.HF_TOKEN:
            raise HTTPException(
                status_code=503,
                detail="Hugging Face token is not configured.",
            )
        provider = HuggingFaceImageProvider()

    else:
        raise HTTPException(
            status_code=500,
            detail=f"Unsupported image backend: {backend}",
        )

    return ImageService(
        db=db,
        provider=provider,
        storage=ImageStorageService(),
        image_safety=ImageSafetyService(),
        usage_service=build_usage_service(db),
    )



@router.post(
    "/generate",
    response_model=ImageGenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_image(
    request: ImageGenerationRequest,
    current_user: User = Depends(get_current_user),
    service: ImageService = Depends(get_image_service),
    safety_service: SafetyService | None = Depends(get_image_safety_service),
):
    # Moderate before calling ImageService so unsafe prompts never reach
    # the image provider or create a generation record.
    await moderate_image_prompt(safety_service, request.prompt)

    try:
        return await service.generate(
            request=request,
            user_id=current_user.id,
        )
    except UnsafeGeneratedImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "unsafe_generated_image",
                "message": "Generated image was blocked by safety moderation.",
                "categories": list(exc.categories),
            },
        ) from exc
    except ImageSafetyUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Generated-image safety moderation is unavailable.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Image generation failed.",
        ) from exc


@router.get(
    "/history",
    response_model=ImageGenerationHistoryResponse,
)
async def get_image_history(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: ImageService = Depends(get_image_service),
):
    return await service.get_history(
        user_id=current_user.id,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{generation_id}/file",
)
async def get_generated_image_file(
    generation_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ImageService = Depends(get_image_service),
):
    generation = await service.get_generation(
        generation_id=generation_id,
        user_id=current_user.id,
    )

    if generation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image generation not found.",
        )

    if generation.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated image is not available.",
        )

    storage = ImageStorageService()
    file_path = storage.get_file_path(f"{generation_id}.png")

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file not found.",
        )

    return FileResponse(
        path=file_path,
        media_type="image/png",
        filename=f"{generation_id}.png",
    )


@router.get(
    "/{generation_id}",
    response_model=ImageGenerationResponse,
)
async def get_image_generation(
    generation_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ImageService = Depends(get_image_service),
):
    generation = await service.get_generation(
        generation_id=generation_id,
        user_id=current_user.id,
    )

    if generation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image generation not found.",
        )

    return generation

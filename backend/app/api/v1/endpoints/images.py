
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services.images.mock_provider import MockImageProvider
from app.storage.image_storage import ImageStorageService

router = APIRouter(prefix="/images", tags=["Image AI"])


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
):
    try:
        return await service.generate(
            request=request,
            user_id=current_user.id,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Image generation failed.",
        )


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

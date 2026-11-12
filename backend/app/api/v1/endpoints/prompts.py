
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.prompt_repository import PromptRepository
from app.schemas.prompt import (
    PromptCreateRequest,
    PromptDetailResponse,
    PromptListResponse,
    PromptResponse,
    PromptUpdateRequest,
    PromptVersionResponse,
)
from app.services.prompt_service import (
    PromptNotFoundError,
    PromptService,
    PromptVersionNotFoundError,
)


router = APIRouter(prefix="/prompts", tags=["Prompt Library"])


def get_prompt_service(
    db: AsyncSession = Depends(get_db),
) -> PromptService:
    repository = PromptRepository(db)
    return PromptService(repository)


def build_prompt_detail(
    prompt,
    version,
) -> PromptDetailResponse:
    prompt_data = PromptResponse.model_validate(prompt)

    return PromptDetailResponse(
        **prompt_data.model_dump(),
        latest_version=PromptVersionResponse.model_validate(version),
    )


@router.post(
    "",
    response_model=PromptDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_prompt(
    payload: PromptCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    try:
        prompt, version = await service.create_prompt(
            user_id=current_user.id,
            name=payload.name,
            description=payload.description,
            content=payload.content,
        )

        response_data = build_prompt_detail(prompt, version)

        await db.commit()
        return response_data

    except Exception:
        await db.rollback()
        raise


@router.get(
    "",
    response_model=PromptListResponse,
)
async def list_prompts(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    prompts = await service.list_prompts(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )

    total = await service.count_prompts(
        user_id=current_user.id,
    )

    return PromptListResponse(
        items=[
            PromptResponse.model_validate(prompt)
            for prompt in prompts
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{prompt_id}",
    response_model=PromptDetailResponse,
)
async def get_prompt(
    prompt_id: UUID,
    current_user: User = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    try:
        prompt = await service.get_prompt(
            prompt_id=prompt_id,
            user_id=current_user.id,
        )

        version = await service.get_version(
            prompt_id=prompt.id,
            user_id=current_user.id,
            version_number=prompt.current_version,
        )

        return build_prompt_detail(prompt, version)

    except (PromptNotFoundError, PromptVersionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found.",
        )


@router.put(
    "/{prompt_id}",
    response_model=PromptDetailResponse,
)
async def update_prompt(
    prompt_id: UUID,
    payload: PromptUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    try:
        prompt, version = await service.update_prompt(
            prompt_id=prompt_id,
            user_id=current_user.id,
            name=payload.name,
            description=payload.description,
            content=payload.content,
        )

        response_data = build_prompt_detail(prompt, version)

        await db.commit()
        return response_data

    except PromptNotFoundError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found.",
        )

    except Exception:
        await db.rollback()
        raise


@router.get(
    "/{prompt_id}/versions",
    response_model=list[PromptVersionResponse],
)
async def list_prompt_versions(
    prompt_id: UUID,
    current_user: User = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    try:
        versions = await service.list_versions(
            prompt_id=prompt_id,
            user_id=current_user.id,
        )

        return [
            PromptVersionResponse.model_validate(version)
            for version in versions
        ]

    except PromptNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found.",
        )


@router.get(
    "/{prompt_id}/versions/{version_number}",
    response_model=PromptVersionResponse,
)
async def get_prompt_version(
    prompt_id: UUID,
    version_number: int,
    current_user: User = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    if version_number < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Version number must be greater than zero.",
        )

    try:
        version = await service.get_version(
            prompt_id=prompt_id,
            user_id=current_user.id,
            version_number=version_number,
        )

        return PromptVersionResponse.model_validate(version)

    except (PromptNotFoundError, PromptVersionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt or version not found.",
        )


# ruff: noqa: B008

from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.video import (
    VideoHistoryResponse,
    VideoTaskResponse,
)
from app.services.audio.local_whisper_provider import LocalWhisperProvider
from app.services.audio.mock_provider import MockSpeechToTextProvider
from app.services.audio.whisper_provider import HuggingFaceWhisperProvider
from app.services.video.providers import get_video_whisper_provider
from app.services.video.video_service import (
    VideoService,
    VideoServiceError,
)
from app.storage.video_storage import VideoStorageService

router = APIRouter(prefix="/video", tags=["Video"])

MAX_VIDEO_SIZE = 100 * 1024 * 1024

ALLOWED_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
    "video/x-m4v",
}


def get_video_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> VideoService:
    settings = get_settings()

    # Reuse the provider configured for the application.
    if settings.WHISPER_PROVIDER == "local":
        whisper_provider = get_video_whisper_provider()

    elif settings.WHISPER_PROVIDER == "huggingface":
        if not settings.HF_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Hugging Face credentials are not configured.",
            )

        whisper_provider = HuggingFaceWhisperProvider(
            token=settings.HF_TOKEN,
            model=settings.WHISPER_MODEL_ID,
            timeout=settings.AUDIO_INFERENCE_TIMEOUT_SECONDS,
        )

    elif settings.WHISPER_PROVIDER == "mock":
        whisper_provider = MockSpeechToTextProvider()

    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unsupported speech-to-text provider.",
        )

    llm_client = getattr(
        request.app.state,
        "litellm_client",
        None,
    )

    if llm_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI gateway is not initialized.",
        )

    return VideoService(
        session=db,
        whisper_provider=whisper_provider,
        llm_client=llm_client,
        storage=VideoStorageService(),
    )


def build_video_response(task) -> VideoTaskResponse:
    return VideoTaskResponse(
        id=task.id,
        source_filename=task.source_filename,
        content_type=task.content_type,
        duration_seconds=task.duration_seconds,
        width=task.width,
        height=task.height,
        frame_rate=task.frame_rate,
        video_codec=task.video_codec,
        audio_codec=task.audio_codec,
        metadata_json=task.metadata_json,
        transcript=task.transcript,
        summary=task.summary,
        captions=task.captions,
        transcription_provider=task.transcription_provider,
        transcription_model=task.transcription_model,
        status=task.status,
        error_message=task.error_message,
        video_url=(
            f"/api/v1/video/{task.id}/file"
            if task.video_path
            else None
        ),
        created_at=task.created_at,
    )


@router.post(
    "/process",
    response_model=VideoTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def process_video(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    service: VideoService = Depends(get_video_service),
):
    filename = file.filename or ""

    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A video filename is required.",
        )

    extension = Path(filename).suffix.lower()

    if not extension:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file must have a video extension.",
        )

    if (
        file.content_type
        and file.content_type not in ALLOWED_CONTENT_TYPES
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported video content type.",
        )

    video_bytes = await file.read(MAX_VIDEO_SIZE + 1)

    if not video_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded video file is empty.",
        )

    if len(video_bytes) > MAX_VIDEO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Video files must be 100 MB or smaller.",
        )

    try:
        task = await service.process_video(
            user_id=current_user.id,
            video_bytes=video_bytes,
            filename=filename,
            content_type=file.content_type,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except VideoServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return build_video_response(task)


@router.get(
    "/history",
    response_model=VideoHistoryResponse,
)
async def get_video_history(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: VideoService = Depends(get_video_service),
):
    tasks, total = await service.get_history(
        user_id=current_user.id,
        offset=offset,
        limit=limit,
    )

    return VideoHistoryResponse(
        items=[build_video_response(task) for task in tasks],
        total=total,
    )


@router.get(
    "/{task_id}",
    response_model=VideoTaskResponse,
)
async def get_video_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    service: VideoService = Depends(get_video_service),
):
    task = await service.get_task(
        task_id=task_id,
        user_id=current_user.id,
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video task not found.",
        )

    return build_video_response(task)


@router.get("/{task_id}/file")
async def download_video_file(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    service: VideoService = Depends(get_video_service),
):
    task = await service.get_task(
        task_id=task_id,
        user_id=current_user.id,
    )

    if task is None or not task.video_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found.",
        )

    try:
        file_path = service.storage.get_file_path(task.video_path)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found.",
        ) from exc

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file is missing from storage.",
        )

    return FileResponse(
        path=file_path,
        media_type=task.content_type or "application/octet-stream",
        filename=Path(task.video_path).name,
    )

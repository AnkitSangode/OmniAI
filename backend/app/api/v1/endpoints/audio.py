# ruff: noqa: B008
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.audio.kokoro_tts_provider import KokoroTTSProvider
from app.services.audio.mock_provider import MockTextToSpeechProvider
from app.services.usage_tracking import build_usage_service

from app.services.safety.safety_service import SafetyService
from app.services.safety.llama_guard import LlamaGuardModerator
from app.services.safety.schemas import (
    UnsafeContentError,
    SafetyServiceUnavailable,
)
from app.services.audio.audio_read_service import AudioReadService

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.audio import (
    AudioHistoryResponse,
    AudioTaskResponse,
    TextToSpeechRequest,
)
from app.services.audio.audio_service import AudioService
from app.services.audio.local_whisper_provider import LocalWhisperProvider
from app.services.audio.mock_provider import (
    MockSpeechToTextProvider,
)
from app.services.audio.whisper_provider import HuggingFaceWhisperProvider
from app.storage.audio_storage import AudioStorageService

router = APIRouter(prefix="/audio", tags=["Audio"])

MAX_AUDIO_SIZE = 25 * 1024 * 1024




def get_audio_service(
    db: AsyncSession = Depends(get_db),
) -> AudioService:

    settings = get_settings()

    # 1. Configure Speech-to-Text provider.
    if settings.WHISPER_PROVIDER == "huggingface":
        if not settings.HF_TOKEN:
            raise HTTPException(
                status_code=503,
                detail="Hugging Face credentials are not configured.",
            )

        stt_provider = HuggingFaceWhisperProvider(
            token=settings.HF_TOKEN,
            model=settings.WHISPER_MODEL_ID,
            timeout=settings.AUDIO_INFERENCE_TIMEOUT_SECONDS,
        )

    elif settings.WHISPER_PROVIDER == "local":
        stt_provider = LocalWhisperProvider(
            model_size=settings.LOCAL_WHISPER_MODEL,
            device=settings.LOCAL_WHISPER_DEVICE,
            compute_type=settings.LOCAL_WHISPER_COMPUTE_TYPE,
            cpu_threads=settings.LOCAL_WHISPER_CPU_THREADS,
            timeout=settings.AUDIO_INFERENCE_TIMEOUT_SECONDS,
        )

    elif settings.WHISPER_PROVIDER == "mock":
        stt_provider = MockSpeechToTextProvider()

    else:
        raise HTTPException(
            status_code=503,
            detail=(
                "Unsupported speech-to-text provider: "
                f"{settings.WHISPER_PROVIDER}"
            ),
        )

    # 2. Configure Text-to-Speech provider.
    if settings.TTS_PROVIDER == "kokoro":
        tts_provider = KokoroTTSProvider(
            model=settings.TTS_MODEL_ID,
            language=settings.TTS_LANGUAGE,
            voice=settings.TTS_VOICE,
            speed=settings.TTS_SPEED,
            device=settings.TTS_DEVICE,
            timeout=settings.TTS_TIMEOUT_SECONDS,
        )

    elif settings.TTS_PROVIDER == "mock":
        tts_provider = MockTextToSpeechProvider()

    else:
        raise HTTPException(
            status_code=503,
            detail=(
                "Unsupported text-to-speech provider: "
                f"{settings.TTS_PROVIDER}"
            ),
        )

    # 3. Configure safety moderation only when enabled.
    safety_service = None

    if settings.SAFETY_ENABLED:
        if settings.SAFETY_PROVIDER != "llama_guard":
            raise HTTPException(
                status_code=503,
                detail="Unsupported safety provider.",
            )

        moderator = LlamaGuardModerator(
            base_url=settings.SAFETY_BASE_URL,
            model=settings.SAFETY_MODEL,
            api_key=settings.SAFETY_API_KEY,
            timeout_seconds=settings.SAFETY_TIMEOUT_SECONDS,
        )

        safety_service = SafetyService(moderator=moderator)

    # 4. Configure audio storage.
    storage = AudioStorageService()

    # 5. Construct AudioService.
    return AudioService(
        db,
        stt_provider,
        tts_provider,
        storage,
        usage_service=build_usage_service(db),
        safety_service=safety_service,
    )


def get_audio_read_service(
    db: AsyncSession = Depends(get_db),
) -> AudioReadService:
    storage = AudioStorageService()

    return AudioReadService(
        session=db,
        storage=storage,
    )

def build_audio_response(task) -> AudioTaskResponse:
    return AudioTaskResponse(
        id=task.id,
        task_type=task.task_type,
        input_text=task.input_text,
        transcript=task.transcript,
        provider=task.provider,
        model=task.model,
        status=task.status,
        audio_url=(f"/api/v1/audio/{task.id}/file" if task.audio_path else None),
        source_filename=task.source_filename,
        content_type=task.content_type,
        duration_seconds=task.duration_seconds,
        created_at=task.created_at,
    )


@router.post(
    "/transcribe",
    response_model=AudioTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def transcribe_audio(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    service: AudioService = Depends(get_audio_service),
):
    audio_bytes = await file.read(MAX_AUDIO_SIZE + 1)

    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded audio file is empty.",
        )

    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio files must be 25 MB or smaller.",
        )

    
    try:
        task = await service.transcribe(
            user_id=current_user.id,
            audio_bytes=audio_bytes,
            filename=file.filename or "audio.wav",
            content_type=file.content_type,
        )

    except UnsafeContentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": str(exc),
                "categories": list(exc.categories),
            },
        ) from exc

    except SafetyServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


    return build_audio_response(task)


@router.post(
    "/speech",
    response_model=AudioTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_speech(
    payload: TextToSpeechRequest,
    current_user: User = Depends(get_current_user),
    service: AudioService = Depends(get_audio_service),
):
    
    try:
        task = await service.generate_speech(
            user_id=current_user.id,
            text=payload.text,
        )

    except UnsafeContentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": str(exc),
                "categories": list(exc.categories),
            },
        ) from exc

    except SafetyServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


    return build_audio_response(task)


@router.get(
    "/history",
    response_model=AudioHistoryResponse,
)
async def get_audio_history(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: AudioReadService = Depends(get_audio_read_service),
):
    tasks, total = await service.get_history(
        user_id=current_user.id,
        offset=offset,
        limit=limit,
    )

    return AudioHistoryResponse(
        items=[build_audio_response(task) for task in tasks],
        total=total,
    )


@router.get("/{task_id}", response_model=AudioTaskResponse)
async def get_audio_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AudioReadService = Depends(get_audio_read_service),
):
    task = await service.get_task(
        task_id=task_id,
        user_id=current_user.id,
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio task not found.",
        )

    return build_audio_response(task)


@router.get("/{task_id}/file")
async def download_audio_file(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AudioReadService = Depends(get_audio_read_service),
):
    task = await service.get_task(
        task_id=task_id,
        user_id=current_user.id,
    )

    if task is None or not task.audio_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found.",
        )

    file_path = service.storage.get_file_path(task.audio_path)

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file is missing from storage.",
        )

    return FileResponse(
        path=file_path,
        media_type=task.content_type or "audio/wav",
        filename=Path(task.audio_path).name,
    )

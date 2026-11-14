# ruff: noqa: B008
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.audio.replicate_tts_provider import ReplicateXTTSProvider
from app.services.audio.mock_provider import MockTextToSpeechProvider

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

    # 1. Configure Speech-to-Text (STT) provider
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
        )

    elif settings.WHISPER_PROVIDER == "mock":
        stt_provider = MockSpeechToTextProvider()

    else:
        raise HTTPException(
            status_code=503,
            detail=f"Unsupported speech-to-text provider: {settings.WHISPER_PROVIDER}",
        )

    # 2. Configure Text-to-Speech (TTS) provider
    if settings.TTS_PROVIDER == "replicate":
        if not settings.REPLICATE_API_TOKEN:
            raise HTTPException(
                status_code=503,
                detail="Replicate API token is not configured.",
            )

        tts_provider = ReplicateXTTSProvider(
            token=settings.REPLICATE_API_TOKEN,
            model=settings.TTS_MODEL_ID,
            speaker_url=settings.TTS_SPEAKER_URL,
            language=settings.TTS_LANGUAGE,
            cleanup_voice=settings.TTS_CLEANUP_VOICE,
            timeout=settings.AUDIO_INFERENCE_TIMEOUT_SECONDS,
        )

    elif settings.TTS_PROVIDER == "mock":
        tts_provider = MockTextToSpeechProvider()

    else:
        raise HTTPException(
            status_code=503,
            detail=f"Unsupported text-to-speech provider: {settings.TTS_PROVIDER}",
        )

    # 3. Create storage service
    storage = AudioStorageService()

    # 4. Construct and return AudioService
    return AudioService(
        db,
        stt_provider,
        tts_provider,
        storage,
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
    service: AudioService = Depends(get_audio_service),
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
    service: AudioService = Depends(get_audio_service),
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
    service: AudioService = Depends(get_audio_service),
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

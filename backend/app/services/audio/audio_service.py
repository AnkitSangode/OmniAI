
import logging
import time
from pathlib import Path
from typing import ClassVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio_task import AudioTask
from app.repositories.audio_repository import AudioRepository
from app.services.audio.base import (
    SpeechToTextProvider,
    TextToSpeechProvider,
)
from app.services.audio.audio_validation_service import (
    AudioValidationService,
)
from app.services.safety.safety_service import SafetyService
from app.services.usage_service import UsageService
from app.services.usage_tracking import record_usage_safely
from app.storage.audio_storage import AudioStorageService


logger = logging.getLogger(__name__)


class AudioService:
    ALLOWED_EXTENSIONS: ClassVar[set[str]] = {
        "wav",
        "mp3",
        "m4a",
        "ogg",
        "webm",
    }

    def __init__(
        self,
        session: AsyncSession,
        stt_provider: SpeechToTextProvider,
        tts_provider: TextToSpeechProvider,
        storage: AudioStorageService,
        usage_service: UsageService | None = None,
        audio_validator: AudioValidationService | None = None,
        safety_service: SafetyService | None = None,
    ):
        self.session = session
        self.repository = AudioRepository(session)
        self.stt_provider = stt_provider
        self.tts_provider = tts_provider
        self.storage = storage
        self.usage_service = usage_service
        self.audio_validator = audio_validator
        self.safety_service = safety_service

    async def transcribe(
        self,
        user_id: UUID,
        audio_bytes: bytes,
        filename: str,
        content_type: str | None = None,
    ) -> AudioTask:

        logger.info("Audio transcription request received.")

        if not audio_bytes:
            raise ValueError("Audio file cannot be empty.")

        safe_filename = Path(filename).name
        extension = Path(safe_filename).suffix.lower().lstrip(".")

        if extension not in self.ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported audio format. Allowed formats: "
                f"{', '.join(sorted(self.ALLOWED_EXTENSIONS))}"
            )

        # Validate actual audio content before creating a task.
        validator = self.audio_validator or AudioValidationService()

        await validator.validate(
            audio_bytes=audio_bytes,
            extension=extension,
        )

        started_at = time.perf_counter()

        task = AudioTask(
            user_id=user_id,
            task_type="transcription",
            provider="pending",
            model="pending",
            source_filename=safe_filename,
            content_type=content_type,
            status="processing",
        )

        await self.repository.create(task)
        await self.session.commit()

        logger.info(
            "Audio transcription task created. Task ID: %s",
            task.id,
        )

        stored_filename: str | None = None

        try:
            # Step 1: Convert audio into text.
            result = await self.stt_provider.transcribe(
                audio_bytes=audio_bytes,
                filename=safe_filename,
                content_type=content_type,
            )

            logger.info(
                "Transcription completed. Provider=%s Model=%s",
                result.provider,
                result.model,
            )

            # Step 2: Moderate the transcript before storing audio
            # or marking the task as completed.
            if self.safety_service is not None:
                await self.safety_service.check_input(result.text)

            # Step 3: Save the original audio only after moderation.
            stored_filename = await self.storage.save(
                audio_bytes=audio_bytes,
                task_id=task.id,
                extension=extension,
            )

            # Step 4: Update the task.
            task.transcript = result.text
            task.provider = result.provider
            task.model = result.model
            task.audio_path = stored_filename
            task.status = "completed"

            # Critical persistence boundary.
            await self.session.commit()

        except Exception as exc:
            logger.exception(
                "Audio transcription failed. Task ID=%s",
                task.id,
            )

            if stored_filename is not None:
                await self._cleanup_saved_file(stored_filename)

            await self._mark_failed(
                task.id,
                user_id,
                exc,
            )

            await record_usage_safely(
                self.usage_service,
                user_id=user_id,
                request_id=str(task.id),
                request_type="audio",
                model=(
                    f"{task.provider}/{task.model}"
                    if task.model != "pending"
                    else "audio-transcription/unknown"
                ),
                latency_ms=int(
                    (time.perf_counter() - started_at) * 1000
                ),
                status="failed",
                error_code=type(exc).__name__,
            )

            raise

        # The database commit succeeded. Preserve the file.
        await record_usage_safely(
            self.usage_service,
            user_id=user_id,
            request_id=str(task.id),
            request_type="audio",
            model=f"{task.provider}/{task.model}",
            latency_ms=int(
                (time.perf_counter() - started_at) * 1000
            ),
            status="success",
        )

        await self.session.refresh(task)

        logger.info(
            "Transcription task completed. Task ID=%s",
            task.id,
        )

        return task

    async def generate_speech(
        self,
        user_id: UUID,
        text: str,
    ) -> AudioTask:

        cleaned_text = text.strip()

        if not cleaned_text:
            raise ValueError("Text cannot be empty.")

        if len(cleaned_text) > 5000:
            raise ValueError(
                "Text cannot exceed 5000 characters."
            )

        started_at = time.perf_counter()

        # Moderate before task creation. Rejected input is therefore
        # not persisted in the audio_tasks table.
        if self.safety_service is not None:
            await self.safety_service.check_input(cleaned_text)

        task = AudioTask(
            user_id=user_id,
            task_type="speech_generation",
            input_text=cleaned_text,
            provider="pending",
            model="pending",
            status="processing",
        )

        await self.repository.create(task)
        await self.session.commit()

        stored_filename: str | None = None

        try:
            result = await self.tts_provider.synthesize(
                cleaned_text
            )

            stored_filename = await self.storage.save(
                audio_bytes=result.audio_bytes,
                task_id=task.id,
                extension=result.extension,
            )

            task.provider = result.provider
            task.model = result.model
            task.audio_path = stored_filename
            task.content_type = result.content_type
            task.duration_seconds = result.duration_seconds
            task.status = "completed"

            await self.session.commit()

        except Exception as exc:
            logger.exception(
                "Speech generation failed. Task ID=%s",
                task.id,
            )

            if stored_filename is not None:
                await self._cleanup_saved_file(stored_filename)

            await self._mark_failed(
                task.id,
                user_id,
                exc,
            )

            await record_usage_safely(
                self.usage_service,
                user_id=user_id,
                request_id=str(task.id),
                request_type="audio",
                model=(
                    f"{task.provider}/{task.model}"
                    if task.model != "pending"
                    else "audio-speech-generation/unknown"
                ),
                latency_ms=int(
                    (time.perf_counter() - started_at) * 1000
                ),
                status="failed",
                error_code=type(exc).__name__,
            )

            raise

        await record_usage_safely(
            self.usage_service,
            user_id=user_id,
            request_id=str(task.id),
            request_type="audio",
            model=f"{task.provider}/{task.model}",
            latency_ms=int(
                (time.perf_counter() - started_at) * 1000
            ),
            status="success",
        )

        await self.session.refresh(task)

        return task

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

    async def _cleanup_saved_file(
        self,
        filename: str,
    ) -> None:
        """Best-effort cleanup of a file without a committed DB reference."""
        try:
            await self.storage.delete(filename)

            logger.info(
                "Cleaned up uncommitted audio file: %s",
                filename,
            )

        except Exception:
            logger.exception(
                "Could not clean up audio file: %s",
                filename,
            )

    async def _mark_failed(
        self,
        task_id: UUID,
        user_id: UUID,
        error: Exception,
    ) -> None:
        """Best-effort task failure update that preserves the original error."""
        try:
            await self.session.rollback()

            task = await self.repository.get_by_id(
                task_id=task_id,
                user_id=user_id,
            )

            if task is None:
                logger.error(
                    "Could not find audio task %s to mark as failed.",
                    task_id,
                )
                return

            task.status = "failed"
            task.error_message = str(error)[:2000]

            await self.session.commit()

            logger.info(
                "Audio task %s marked as failed.",
                task_id,
            )

        except Exception:
            await self.session.rollback()

            logger.exception(
                "Could not mark audio task %s as failed.",
                task_id,
            )

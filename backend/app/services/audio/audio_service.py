
import logging
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
    ):
        self.session = session
        self.repository = AudioRepository(session)
        self.stt_provider = stt_provider
        self.tts_provider = tts_provider
        self.storage = storage

    async def transcribe(
        self,
        user_id: UUID,
        audio_bytes: bytes,
        filename: str,
        content_type: str | None = None,
    ) -> AudioTask:

        logger.warning("AUDIO SERVICE: Transcription request received")

        if not audio_bytes:
            raise ValueError("Audio file cannot be empty.")

        safe_filename = Path(filename).name
        extension = Path(safe_filename).suffix.lower().lstrip(".")

        if extension not in self.ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported audio format. Allowed formats: "
                f"{', '.join(sorted(self.ALLOWED_EXTENSIONS))}"
            )

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

        logger.warning(
            "AUDIO SERVICE: Task created and committed. Task ID: %s",
            task.id,
        )

        try:
            logger.warning("AUDIO SERVICE: Calling STT provider")

            result = await self.stt_provider.transcribe(
                audio_bytes=audio_bytes,
                filename=safe_filename,
                content_type=content_type,
            )

            logger.warning(
                "AUDIO SERVICE: STT provider returned successfully. "
                "Provider=%s Model=%s Transcript length=%s",
                result.provider,
                result.model,
                len(result.text),
            )

            logger.warning("AUDIO SERVICE: Saving original audio")

            stored_filename = await self.storage.save(
                audio_bytes=audio_bytes,
                task_id=task.id,
                extension=extension,
            )

            logger.warning(
                "AUDIO SERVICE: Audio saved: %s",
                stored_filename,
            )

            task.transcript = result.text
            task.provider = result.provider
            task.model = result.model
            task.audio_path = stored_filename
            task.status = "completed"

            logger.warning("AUDIO SERVICE: Committing completed task")

            await self.session.commit()

            logger.warning("AUDIO SERVICE: Completed task committed")

            await self.session.refresh(task)

            logger.warning(
                "AUDIO SERVICE: Task refreshed. Final status=%s",
                task.status,
            )

            return task

        except Exception as exc:
            logger.exception(
                "AUDIO SERVICE: Transcription failed. Task ID=%s",
                task.id,
            )

            await self._mark_failed(task.id, user_id, exc)
            raise

    async def generate_speech(
        self,
        user_id: UUID,
        text: str,
    ) -> AudioTask:

        cleaned_text = text.strip()

        if not cleaned_text:
            raise ValueError("Text cannot be empty.")

        if len(cleaned_text) > 5000:
            raise ValueError("Text cannot exceed 5000 characters.")

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

        try:
            result = await self.tts_provider.synthesize(cleaned_text)

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
            await self.session.refresh(task)

            return task

        except Exception as exc:
            logger.exception(
                "AUDIO SERVICE: Speech generation failed. Task ID=%s",
                task.id,
            )

            await self._mark_failed(task.id, user_id, exc)
            raise

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

    async def _mark_failed(
        self,
        task_id: UUID,
        user_id: UUID,
        error: Exception,
    ) -> None:

        await self.session.rollback()

        task = await self.repository.get_by_id(
            task_id=task_id,
            user_id=user_id,
        )

        if task is None:
            logger.error(
                "AUDIO SERVICE: Could not find task %s to mark failed",
                task_id,
            )
            return

        task.status = "failed"
        task.error_message = str(error)[:2000]

        await self.session.commit()

        logger.warning(
            "AUDIO SERVICE: Task %s marked as failed",
            task_id,
        )

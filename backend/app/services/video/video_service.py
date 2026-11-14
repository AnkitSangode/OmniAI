
import asyncio
import logging
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.video_task import VideoTask
from app.repositories.video_repository import VideoRepository
from app.services.audio.base import SpeechToTextProvider
from app.services.llm.litellm_client import LiteLLMClient
from app.services.llm.schemas import (
    LLMMessage,
    TextGenerationRequest,
)
from app.services.video.ffmpeg_service import FFmpegService
from app.storage.video_storage import VideoStorageService

logger = logging.getLogger(__name__)


class VideoServiceError(Exception):
    """Raised when required video processing fails."""


class VideoService:
    def __init__(
        self,
        session: AsyncSession,
        whisper_provider: SpeechToTextProvider,
        llm_client: LiteLLMClient,
        ffmpeg_service: FFmpegService | None = None,
        storage: VideoStorageService | None = None,
    ):
        self.session = session
        self.repository = VideoRepository(session)

        self.whisper_provider = whisper_provider
        self.llm_client = llm_client

        self.ffmpeg = ffmpeg_service or FFmpegService()
        self.storage = storage or VideoStorageService()

        self.settings = get_settings()

    async def process_video(
        self,
        user_id: UUID,
        video_bytes: bytes,
        filename: str,
        content_type: str | None = None,
    ) -> VideoTask:
        """
        Process an uploaded video.

        Required stages:
            1. Save video
            2. Extract metadata
            3. Extract audio
            4. Transcribe audio

        Optional stages:
            5. Generate summary
            6. Generate captions

        LLM failures do not invalidate successful
        video processing or Whisper transcription.
        """

        if not video_bytes:
            raise ValueError("Video file cannot be empty.")

        original_path = Path(filename)
        extension = original_path.suffix.lower().lstrip(".")

        if extension not in self.storage.ALLOWED_EXTENSIONS:
            raise ValueError("Unsupported video format.")

        if not original_path.name or original_path.name != filename:
            raise ValueError("Invalid video filename.")

        task_id = uuid4()

        task = VideoTask(
            id=task_id,
            user_id=user_id,
            source_filename=original_path.name,
            content_type=content_type,
            status="processing",
        )

        audio_path: Path | None = None
        video_filename: str | None = None
        video_path: Path | None = None

        optional_errors: list[str] = []

        try:
            # --------------------------------------------------
            # 1. Save uploaded video
            # --------------------------------------------------

            video_filename = await self.storage.save(
                video_bytes=video_bytes,
                task_id=task_id,
                extension=extension,
            )

            video_path = self.storage.get_file_path(video_filename)

            task.video_path = video_filename

            # --------------------------------------------------
            # 2. Register processing task
            # --------------------------------------------------

            await self.repository.create(task)
            await self.session.commit()

            logger.info(
                "Video task %s created successfully.",
                task_id,
            )

            # --------------------------------------------------
            # 3. Extract video metadata
            # --------------------------------------------------

            metadata = await self.ffmpeg.extract_metadata(video_path)

            task.duration_seconds = metadata["duration_seconds"]
            task.width = metadata["width"]
            task.height = metadata["height"]
            task.frame_rate = metadata["frame_rate"]
            task.video_codec = metadata["video_codec"]
            task.audio_codec = metadata["audio_codec"]
            task.metadata_json = metadata

            logger.info(
                "Metadata extraction completed for task %s.",
                task_id,
            )

            # --------------------------------------------------
            # 4. Extract audio and transcribe using Whisper
            # --------------------------------------------------

            if metadata["has_audio"]:

                audio_path = (
                    self.storage.storage_dir / f"{task_id}.wav"
                )

                await self.ffmpeg.extract_audio(
                    video_path=video_path,
                    output_path=audio_path,
                )

                audio_bytes = await self._read_file(audio_path)

                transcription = await self.whisper_provider.transcribe(
                    audio_bytes=audio_bytes,
                    filename=audio_path.name,
                    content_type="audio/wav",
                )

                task.transcript = transcription.text
                task.transcription_provider = transcription.provider
                task.transcription_model = transcription.model

                # The extracted WAV is temporary.
                # Do not store a reference to a deleted file.
                task.extracted_audio_path = None

                logger.info(
                    "Transcription completed for task %s using %s.",
                    task_id,
                    transcription.provider,
                )

            else:
                logger.info(
                    "Video %s has no audio stream. "
                    "Skipping transcription and text generation.",
                    task_id,
                )

            # --------------------------------------------------
            # 5. Commit all required processing results
            # --------------------------------------------------

            # This is an important transaction boundary.
            # Metadata and transcript are now safe even if
            # the external LLM provider becomes unavailable.

            await self.session.commit()

            logger.info(
                "Core video processing results committed for task %s.",
                task_id,
            )

            # --------------------------------------------------
            # 6. Generate optional summary
            # --------------------------------------------------

            if task.transcript and task.transcript.strip():

                try:
                    task.summary = await self._generate_summary(
                        task.transcript
                    )

                    logger.info(
                        "Summary generation completed for task %s.",
                        task_id,
                    )

                except Exception as exc:
                    logger.exception(
                        "Summary generation failed for task %s.",
                        task_id,
                    )

                    optional_errors.append(
                        f"Summary generation failed: {str(exc)[:500]}"
                    )

                # --------------------------------------------------
                # 7. Generate optional captions
                # --------------------------------------------------

                try:
                    task.captions = await self._generate_captions(
                        task.transcript
                    )

                    logger.info(
                        "Caption generation completed for task %s.",
                        task_id,
                    )

                except Exception as exc:
                    logger.exception(
                        "Caption generation failed for task %s.",
                        task_id,
                    )

                    optional_errors.append(
                        f"Caption generation failed: {str(exc)[:500]}"
                    )

            # --------------------------------------------------
            # 8. Determine final processing status
            # --------------------------------------------------

            if optional_errors:
                task.status = "partially_completed"
                task.error_message = "; ".join(optional_errors)[:2000]

                logger.warning(
                    "Video task %s partially completed. "
                    "Optional stages failed: %s",
                    task_id,
                    task.error_message,
                )

            else:
                task.status = "completed"
                task.error_message = None

                logger.info(
                    "Video task %s completed successfully.",
                    task_id,
                )

            # --------------------------------------------------
            # 9. Persist final results
            # --------------------------------------------------

            await self.session.commit()
            await self.session.refresh(task)

            return task

        except Exception as exc:
            logger.exception(
                "Required video processing failed for task %s.",
                task_id,
            )

            await self.session.rollback()

            # Retrieve the task again after rollback.
            existing_task = await self.repository.get_by_id(
                task_id=task_id,
                user_id=user_id,
            )

            if existing_task:
                existing_task.status = "failed"
                existing_task.error_message = str(exc)[:2000]

                await self.session.commit()

                logger.error(
                    "Video task %s marked as failed.",
                    task_id,
                )

            else:
                # If task creation failed, remove the uploaded
                # video to avoid leaving an orphaned file.
                logger.error(
                    "Video task %s could not be retrieved "
                    "after processing failure.",
                    task_id,
                )

                if video_path and video_path.exists():
                    await self._delete_file(video_path)

            raise VideoServiceError(
                "Video processing failed."
            ) from exc

        finally:
            # --------------------------------------------------
            # 10. Clean up temporary extracted audio
            # --------------------------------------------------

            if audio_path:
                await self._delete_file(audio_path)

    async def _generate_summary(self, transcript: str) -> str:
        request = TextGenerationRequest(
            messages=[
                LLMMessage(
                    role="system",
                    content=(
                        "You are a professional video content analyst. "
                        "Create accurate, concise summaries based only "
                        "on the supplied transcript. Do not invent details."
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=(
                        "Summarize the following video transcript. "
                        "Include the main topic, key points, and conclusion.\n\n"
                        f"Transcript:\n{transcript}"
                    ),
                ),
            ],
            temperature=0.3,
            max_tokens=1024,
        )

        response = await self.llm_client.generate(request)

        return response.content.strip()

    async def _generate_captions(self, transcript: str) -> str:
        request = TextGenerationRequest(
            messages=[
                LLMMessage(
                    role="system",
                    content=(
                        "You are a professional social media content writer. "
                        "Create engaging but accurate video post captions. "
                        "Do not invent facts or events."
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=(
                        "Create three alternative captions for this video. "
                        "Keep them concise and relevant to the transcript. "
                        "Return them as a numbered list.\n\n"
                        f"Transcript:\n{transcript}"
                    ),
                ),
            ],
            temperature=0.7,
            max_tokens=600,
        )

        response = await self.llm_client.generate(request)

        return response.content.strip()

    @staticmethod
    async def _read_file(file_path: Path) -> bytes:
        return await asyncio.to_thread(file_path.read_bytes)

    @staticmethod
    async def _delete_file(file_path: Path) -> None:
        await asyncio.to_thread(
            file_path.unlink,
            missing_ok=True,
        )

    async def get_task(
        self,
        task_id: UUID,
        user_id: UUID,
    ) -> VideoTask | None:
        return await self.repository.get_by_id(
            task_id=task_id,
            user_id=user_id,
        )

    async def get_history(
        self,
        user_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[VideoTask], int]:

        tasks = await self.repository.list_by_user(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

        total = await self.repository.count_by_user(user_id)

        return tasks, total

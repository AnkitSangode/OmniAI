
import asyncio
import logging

from huggingface_hub import InferenceClient

from app.services.audio.base import (
    SpeechToTextProvider,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)


class HuggingFaceWhisperProvider(SpeechToTextProvider):
    """Speech-to-text provider backed by Hugging Face Inference Providers."""

    def __init__(
        self,
        token: str,
        model: str = "openai/whisper-large-v3",
        timeout: int = 180,
    ):
        if not token:
            raise ValueError("Hugging Face token is required.")

        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        self.token = token
        self.model = model
        self.timeout = timeout

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str | None,
    ) -> TranscriptionResult:
        if not audio_bytes:
            raise ValueError("Audio file cannot be empty.")

        try:
            output = await asyncio.wait_for(
                asyncio.to_thread(
                    self._transcribe_sync,
                    audio_bytes,
                ),
                timeout=self.timeout,
            )

        except TimeoutError as exc:
            logger.error(
                "Hugging Face transcription timed out after %s seconds.",
                self.timeout,
            )
            raise RuntimeError(
                "Hugging Face Whisper transcription timed out."
            ) from exc

        except asyncio.CancelledError:
            logger.info("Hugging Face transcription was cancelled.")
            raise

        except Exception as exc:
            logger.exception(
                "Hugging Face Whisper transcription failed."
            )
            raise RuntimeError(
                "Hugging Face Whisper transcription failed."
            ) from exc

        transcript = (output.text or "").strip()

        if not transcript:
            raise RuntimeError(
                "Whisper returned an empty transcription."
            )

        return TranscriptionResult(
            text=transcript,
            provider="huggingface",
            model=self.model,
        )

    def _transcribe_sync(self, audio_bytes: bytes):
        client = InferenceClient(
            provider="auto",
            token=self.token,
            timeout=self.timeout,
        )

        return client.automatic_speech_recognition(
            audio=audio_bytes,
            model=self.model,
        )

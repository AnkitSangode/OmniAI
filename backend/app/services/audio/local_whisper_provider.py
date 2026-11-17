
import asyncio
import logging
import threading
from io import BytesIO

from faster_whisper import WhisperModel

from app.services.audio.base import (
    SpeechToTextProvider,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)


class LocalWhisperProvider(SpeechToTextProvider):
    def __init__(
        self,
        model_size="base",
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
        timeout=300,
    ):
        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.timeout = timeout

        self._model = None

        # Protect model initialization.
        self._model_lock = threading.Lock()

        # Serialize inference on this model instance.
        self._inference_lock = threading.Lock()

        logger.info(
            "LocalWhisperProvider initialized: model=%s, device=%s",
            model_size,
            device,
        )

    def _get_model(self):
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    logger.info(
                        "Loading local Whisper model: %s",
                        self.model_size,
                    )

                    self._model = WhisperModel(
                        self.model_size,
                        device=self.device,
                        compute_type=self.compute_type,
                        cpu_threads=self.cpu_threads,
                    )

                    logger.info("Local Whisper model loaded.")

        return self._model

    async def transcribe(
        self,
        audio_bytes,
        filename,
        content_type,
    ):
        if not audio_bytes:
            raise ValueError("Audio file cannot be empty.")

        logger.info(
            "Local transcription started. File=%s Size=%s bytes",
            filename,
            len(audio_bytes),
        )

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self._transcribe_sync,
                    audio_bytes,
                ),
                timeout=self.timeout,
            )

            logger.info("Local transcription completed.")

            return result

        except TimeoutError as exc:
            logger.error(
                "Local Whisper timed out after %s seconds.",
                self.timeout,
            )
            raise RuntimeError(
                "Local Whisper transcription timed out."
            ) from exc

        except asyncio.CancelledError:
            logger.info("Local Whisper transcription was cancelled.")
            raise

        except Exception:
            logger.exception("Local Whisper transcription failed.")
            raise

    def _transcribe_sync(self, audio_bytes):
        model = self._get_model()
        audio_stream = BytesIO(audio_bytes)

        # Only one inference at a time per provider instance.
        with self._inference_lock:
            segments, info = model.transcribe(
                audio_stream,
                beam_size=5,
                vad_filter=True,
            )

            # faster-whisper generates segments lazily.
            # Consume them while holding the inference lock.
            transcript_parts = [
                segment.text.strip()
                for segment in segments
                if segment.text.strip()
            ]

        transcript = " ".join(transcript_parts).strip()

        if not transcript:
            raise RuntimeError(
                "No speech could be detected in the audio."
            )

        return TranscriptionResult(
            text=transcript,
            provider="local",
            model=f"faster-whisper-{self.model_size}",
        )

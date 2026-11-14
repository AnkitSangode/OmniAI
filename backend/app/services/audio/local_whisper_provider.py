
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
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads

        self._model = None
        self._model_lock = threading.Lock()

        logger.warning(
            "LocalWhisperProvider initialized: model=%s, device=%s",
            model_size,
            device,
        )

    def _get_model(self):
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    logger.warning("WHISPER STEP 1: Starting model loading")

                    self._model = WhisperModel(
                        self.model_size,
                        device=self.device,
                        compute_type=self.compute_type,
                        cpu_threads=self.cpu_threads,
                    )

                    logger.warning("WHISPER STEP 2: Model loaded successfully")

        return self._model

    async def transcribe(self, audio_bytes, filename, content_type):
        logger.warning("WHISPER STEP 3: Transcribe method entered")

        if not audio_bytes:
            raise ValueError("Audio file cannot be empty.")

        logger.warning(
            "WHISPER STEP 4: Received %s bytes from %s",
            len(audio_bytes),
            filename,
        )

        try:
            result = await asyncio.to_thread(
                self._transcribe_sync,
                audio_bytes,
            )

            logger.warning("WHISPER STEP 7: Transcription completed")
            return result

        except Exception:
            logger.exception("WHISPER ERROR: Transcription failed")
            raise

    def _transcribe_sync(self, audio_bytes):
        logger.warning("WHISPER STEP 5: Starting inference")

        model = self._get_model()

        audio_stream = BytesIO(audio_bytes)

        segments, info = model.transcribe(
            audio_stream,
            beam_size=5,
            vad_filter=True,
        )

        logger.warning("WHISPER STEP 6: Reading transcription segments")

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

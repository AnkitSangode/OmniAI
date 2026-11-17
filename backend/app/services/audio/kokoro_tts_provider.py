
import asyncio
import io
import logging
import threading

import numpy as np
import soundfile as sf
from kokoro import KPipeline

from app.services.audio.base import (
    SynthesizedAudio,
    TextToSpeechProvider,
)

logger = logging.getLogger(__name__)


class KokoroTTSProvider(TextToSpeechProvider):
    SAMPLE_RATE = 24000

    LANGUAGE_CODES = {
        "en": "a",
        "en-us": "a",
        "en-gb": "b",
        "es": "e",
        "fr": "f",
        "fr-fr": "f",
        "hi": "h",
        "it": "i",
        "ja": "j",
        "pt": "p",
        "pt-br": "p",
        "zh": "z",
    }

    def __init__(
        self,
        model: str = "hexgrad/Kokoro-82M",
        language: str = "en-us",
        voice: str = "af_heart",
        speed: float = 1.0,
        device: str = "cpu",
        timeout: int = 300,
    ):
        language = language.lower().strip()
        device = device.lower().strip()

        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        if speed <= 0:
            raise ValueError("Speed must be greater than zero.")

        if language not in self.LANGUAGE_CODES:
            raise ValueError(
                f"Unsupported Kokoro language: {language}"
            )

        if not voice:
            raise ValueError("Voice cannot be empty.")

        if device not in {"cpu", "cuda", "mps"}:
            raise ValueError(
                f"Unsupported inference device: {device}"
            )

        self.model = model
        self.language = language
        self.lang_code = self.LANGUAGE_CODES[language]
        self.voice = voice
        self.speed = speed
        self.device = device
        self.timeout = timeout

        # Model is loaded only when the first request arrives.
        self._pipeline: KPipeline | None = None

        # Protect model initialization and inference.
        self._lock = threading.Lock()

    def _get_pipeline(self) -> KPipeline:
        if self._pipeline is None:
            logger.info(
                "Loading Kokoro model %s on %s",
                self.model,
                self.device,
            )

            self._pipeline = KPipeline(
                lang_code=self.lang_code,
                repo_id=self.model,
                device=self.device,
            )

            logger.info("Kokoro model loaded successfully.")

        return self._pipeline

    async def synthesize(
        self,
        text: str,
    ) -> SynthesizedAudio:
        cleaned_text = text.strip()

        if not cleaned_text:
            raise ValueError("Text cannot be empty.")

        try:
            audio_bytes, duration = await asyncio.wait_for(
                asyncio.to_thread(
                    self._synthesize_sync,
                    cleaned_text,
                ),
                timeout=self.timeout,
            )

            if not audio_bytes:
                raise RuntimeError(
                    "Kokoro generated empty audio."
                )

            return SynthesizedAudio(
                audio_bytes=audio_bytes,
                content_type="audio/wav",
                extension="wav",
                provider="kokoro",
                model=self.model,
                duration_seconds=duration,
            )

        except TimeoutError as exc:
            logger.error(
                "Kokoro generation timed out after %s seconds.",
                self.timeout,
            )
            raise RuntimeError(
                "Kokoro speech generation timed out."
            ) from exc

        except asyncio.CancelledError:
            logger.info("Kokoro generation cancelled.")
            raise

        except Exception as exc:
            logger.exception(
                "Kokoro speech generation failed."
            )
            raise RuntimeError(
                "Kokoro speech generation failed."
            ) from exc

    def _synthesize_sync(
        self,
        text: str,
    ) -> tuple[bytes, float]:

        with self._lock:
            pipeline = self._get_pipeline()

            chunks = []

            generator = pipeline(
                text,
                voice=self.voice,
                speed=self.speed,
            )

            for _, _, audio in generator:
                if hasattr(audio, "detach"):
                    audio = audio.detach().cpu().numpy()
                else:
                    audio = np.asarray(audio)

                if audio.size:
                    chunks.append(
                        np.asarray(audio, dtype=np.float32)
                    )

            if not chunks:
                raise RuntimeError(
                    "Kokoro produced no audio chunks."
                )

            waveform = np.concatenate(chunks)

            duration = len(waveform) / self.SAMPLE_RATE

            buffer = io.BytesIO()

            sf.write(
                buffer,
                waveform,
                self.SAMPLE_RATE,
                format="WAV",
                subtype="PCM_16",
            )

            return buffer.getvalue(), duration

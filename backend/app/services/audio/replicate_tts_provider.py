
import asyncio
import logging

import replicate

from app.services.audio.base import (
    SynthesizedAudio,
    TextToSpeechProvider,
)

logger = logging.getLogger(__name__)


class ReplicateXTTSProvider(TextToSpeechProvider):
    def __init__(
        self,
        token: str,
        model: str,
        speaker_url: str,
        language: str = "en",
        cleanup_voice: bool = False,
        timeout: int = 180,
    ):
        if not token:
            raise ValueError("Replicate API token is required.")

        if not speaker_url:
            raise ValueError("XTTS speaker reference URL is required.")

        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        self.client = replicate.Client(api_token=token)
        self.model = model
        self.speaker_url = speaker_url
        self.language = language
        self.cleanup_voice = cleanup_voice
        self.timeout = timeout

    async def synthesize(self, text: str) -> SynthesizedAudio:
        cleaned_text = text.strip()

        if not cleaned_text:
            raise ValueError("Text cannot be empty.")

        try:
            # One deadline covers remote generation and output reading.
            audio_bytes = await asyncio.wait_for(
                asyncio.to_thread(
                    self._synthesize_sync,
                    cleaned_text,
                ),
                timeout=self.timeout,
            )

            if not audio_bytes:
                raise RuntimeError(
                    "Replicate returned an empty audio file."
                )

            return SynthesizedAudio(
                audio_bytes=audio_bytes,
                content_type="audio/wav",
                extension="wav",
                provider="replicate",
                model=self.model,
            )

        except TimeoutError as exc:
            logger.error(
                "Replicate XTTS timed out after %s seconds.",
                self.timeout,
            )
            raise RuntimeError(
                "Replicate XTTS request timed out."
            ) from exc

        except asyncio.CancelledError:
            logger.info("Replicate XTTS request was cancelled.")
            raise

        except Exception as exc:
            logger.exception("Replicate XTTS generation failed.")

            raise RuntimeError(
                "Replicate XTTS generation failed."
            ) from exc

    def _synthesize_sync(self, text: str) -> bytes:
        output = self.client.run(
            self.model,
            input={
                "text": text,
                "speaker": self.speaker_url,
                "language": self.language,
                "cleanup_voice": self.cleanup_voice,
            },
        )

        # Output reading is included in the same worker operation.
        audio_bytes = output.read()

        if not isinstance(audio_bytes, bytes):
            raise RuntimeError(
                "Replicate returned an unexpected audio output."
            )

        return audio_bytes

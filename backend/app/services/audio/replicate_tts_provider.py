import asyncio

import replicate

from app.services.audio.base import (
    SynthesizedAudio,
    TextToSpeechProvider,
)


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

        self.client = replicate.Client(api_token=token)
        self.model = model
        self.speaker_url = speaker_url
        self.language = language
        self.cleanup_voice = cleanup_voice
        self.timeout = timeout

    
    async def synthesize(self, text: str) -> SynthesizedAudio:
        text = text.strip()

        if not text:
            raise ValueError("Text cannot be empty.")

        try:
            output = await asyncio.wait_for(
                asyncio.to_thread(self._synthesize_sync, text),
                timeout=self.timeout,
            )

            audio_bytes = await asyncio.to_thread(output.read)

            if not audio_bytes:
                raise RuntimeError("Replicate returned an empty audio file.")

            return SynthesizedAudio(
                audio_bytes=audio_bytes,
                content_type="audio/wav",
                extension="wav",
                provider="replicate",
                model=self.model,
            )

        except TimeoutError as exc:
            raise RuntimeError(
                "Replicate XTTS request timed out."
            ) from exc

        except Exception as exc:
            import logging

            logging.exception("Replicate XTTS generation failed")

            raise RuntimeError(
                f"Replicate XTTS failed: {type(exc).__name__}: {exc}"
            ) from exc


    def _synthesize_sync(self, text: str):
        return self.client.run(
            self.model,
            input={
                "text": text,
                "speaker": self.speaker_url,
                "language": self.language,
                "cleanup_voice": self.cleanup_voice,
            },
        )
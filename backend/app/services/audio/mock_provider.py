
import asyncio
import io
import math
import struct
import wave

from app.services.audio.base import (
    SpeechToTextProvider,
    SynthesizedAudio,
    TextToSpeechProvider,
    TranscriptionResult,
)


class MockSpeechToTextProvider(SpeechToTextProvider):
    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str | None,
    ) -> TranscriptionResult:
        # Simulates the transcription workflow.
        # This does NOT perform actual speech recognition.
        await asyncio.sleep(0.5)

        return TranscriptionResult(
            text=(
                f"[MOCK TRANSCRIPTION] Audio file '{filename}' "
                "was successfully received. Actual speech recognition "
                "is not enabled in mock mode."
            ),
            provider="mock",
            model="omniai-mock-stt-v1",
        )


class MockTextToSpeechProvider(TextToSpeechProvider):
    async def synthesize(self, text: str) -> SynthesizedAudio:
        # Generate a short valid WAV tone as a placeholder.
        # This is NOT synthesized speech.
        sample_rate = 16000
        duration = 1.0
        frequency = 440.0

        buffer = io.BytesIO()

        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)

            frames = bytearray()

            for index in range(int(sample_rate * duration)):
                sample = int(
                    5000 * math.sin(
                        2 * math.pi * frequency * index / sample_rate
                    )
                )
                frames.extend(struct.pack("<h", sample))

            wav.writeframes(bytes(frames))

        return SynthesizedAudio(
            audio_bytes=buffer.getvalue(),
            content_type="audio/wav",
            extension="wav",
            provider="mock",
            model="omniai-mock-tts-v1",
            duration_seconds=duration,
        )

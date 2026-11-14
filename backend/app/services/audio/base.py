
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TranscriptionResult:
    text: str
    provider: str
    model: str


@dataclass
class SynthesizedAudio:
    audio_bytes: bytes
    content_type: str
    extension: str
    provider: str
    model: str
    duration_seconds: float | None = None


class SpeechToTextProvider(ABC):
    @abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str | None,
    ) -> TranscriptionResult:
        raise NotImplementedError


class TextToSpeechProvider(ABC):
    @abstractmethod
    async def synthesize(
        self,
        text: str,
    ) -> SynthesizedAudio:
        raise NotImplementedError

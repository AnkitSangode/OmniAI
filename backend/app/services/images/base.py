
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GeneratedImage:
    image_bytes: bytes
    provider: str
    model: str
    provider_elapsed_seconds: float | None = None


class ImageProvider(ABC):

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        width: int,
        height: int,
    ) -> GeneratedImage:
        """Generate an image from a text prompt."""
        raise NotImplementedError

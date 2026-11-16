from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class ImageSafetyStatus(str, Enum):
    """Describes whether generated-image content was actually inspected."""

    NOT_CHECKED = "not_checked"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ImageSafetyResult:
    """Structured result returned by a concrete image safety provider."""

    status: ImageSafetyStatus
    categories: tuple[str, ...] = ()


class ImageSafetyError(Exception):
    """Base exception for generated-image safety failures."""


class UnsafeGeneratedImageError(ImageSafetyError):
    """Raised when an image checker rejects generated image content."""

    def __init__(self, categories: tuple[str, ...] = ()):
        self.categories = categories
        super().__init__("Generated image was rejected by safety moderation.")


class ImageSafetyUnavailable(ImageSafetyError):
    """Raised when a configured image checker cannot complete moderation."""


@runtime_checkable
class ImageSafetyChecker(Protocol):
    """Contract implemented by local or hosted vision safety providers.

    Implementations must inspect the image bytes themselves. Prompt text
    moderation is not a substitute for this operation.
    """

    async def check(self, image_bytes: bytes) -> ImageSafetyResult:
        """Return whether the image is approved or rejected."""
        ...


class ImageSafetyService:
    """Provider-independent orchestration for generated-image moderation."""

    def __init__(self, checker: ImageSafetyChecker | None = None):
        self.checker = checker

    async def check(self, image_bytes: bytes) -> ImageSafetyResult:
        if not image_bytes:
            raise ValueError("Image bytes cannot be empty.")

        # No vision checker is configured in this deployment. Explicitly
        # report NOT_CHECKED; never represent this state as APPROVED.
        if self.checker is None:
            return ImageSafetyResult(
                status=ImageSafetyStatus.NOT_CHECKED
            )

        try:
            result = await self.checker.check(image_bytes)
        except Exception as exc:
            raise ImageSafetyUnavailable(
                "Generated-image moderation could not be completed."
            ) from exc

        if not isinstance(result, ImageSafetyResult):
            raise ImageSafetyUnavailable(
                "Image safety provider returned an invalid result."
            )

        if result.status == ImageSafetyStatus.NOT_CHECKED:
            # A configured checker must not silently skip the inspection.
            raise ImageSafetyUnavailable(
                "Configured image safety provider did not inspect the image."
            )

        if result.status == ImageSafetyStatus.REJECTED:
            raise UnsafeGeneratedImageError(result.categories)

        if result.status != ImageSafetyStatus.APPROVED:
            raise ImageSafetyUnavailable(
                "Image safety provider returned an unknown status."
            )

        return result

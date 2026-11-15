from dataclasses import dataclass


@dataclass(frozen=True)
class ModerationResult:
    is_safe: bool
    categories: tuple[str, ...] = ()


class SafetyError(Exception):
    """Base exception for safety-related failures."""


class UnsafeContentError(SafetyError):
    """Raised when content violates safety policy."""

    def __init__(self, categories: tuple[str, ...] = ()):
        self.categories = categories
        super().__init__("Content was blocked by safety moderation.")


class SafetyServiceUnavailable(SafetyError):
    """Raised when moderation cannot be completed."""
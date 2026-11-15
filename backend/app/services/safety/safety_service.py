from typing import Protocol

from app.services.safety.schemas import (
    ModerationResult,
    SafetyServiceUnavailable,
    UnsafeContentError,
)


class Moderator(Protocol):
    async def moderate(
        self,
        text: str,
        *,
        role: str,
    ) -> ModerationResult:
        """Classify text as safe or unsafe."""
        ...


class SafetyService:
    def __init__(self, moderator: Moderator):
        self.moderator = moderator

    async def check_input(self, text: str) -> ModerationResult:
        return await self._check(text, role="user")

    async def check_output(self, text: str) -> ModerationResult:
        return await self._check(text, role="assistant")

    async def _check(
        self,
        text: str,
        *,
        role: str,
    ) -> ModerationResult:
        if not text or not text.strip():
            return ModerationResult(is_safe=True)

        try:
            result = await self.moderator.moderate(
                text,
                role=role,
            )
        except Exception as exc:
            raise SafetyServiceUnavailable(
                "Safety moderation could not be completed."
            ) from exc

        if not result.is_safe:
            raise UnsafeContentError(result.categories)

        return result

from uuid import UUID

from app.models.prompt import Prompt, PromptVersion
from app.repositories.prompt_repository import PromptRepository


class PromptNotFoundError(Exception):
    """Raised when a prompt does not exist or is not owned by the user."""


class PromptVersionNotFoundError(Exception):
    """Raised when a requested prompt version does not exist."""


class PromptService:
    def __init__(self, repository: PromptRepository):
        self.repository = repository

    async def create_prompt(
        self,
        *,
        user_id: UUID,
        name: str,
        description: str | None,
        content: str,
    ) -> tuple[Prompt, PromptVersion]:
        # Create the prompt identity.
        prompt = await self.repository.create(
            user_id=user_id,
            name=name,
            description=description,
        )

        # Every new prompt starts at version 1.
        version = await self.repository.create_version(
            prompt_id=prompt.id,
            version_number=1,
            content=content,
        )

        return prompt, version

    async def list_prompts(
        self,
        *,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Prompt]:
        return await self.repository.list_by_user(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    async def get_prompt(
        self,
        *,
        prompt_id: UUID,
        user_id: UUID,
    ) -> Prompt:
        prompt = await self.repository.get_by_id(
            prompt_id=prompt_id,
            user_id=user_id,
        )

        if prompt is None:
            raise PromptNotFoundError("Prompt not found.")

        return prompt

    async def update_prompt(
        self,
        *,
        prompt_id: UUID,
        user_id: UUID,
        name: str,
        description: str | None,
        content: str,
    ) -> tuple[Prompt, PromptVersion]:
        # Lock the prompt row to prevent concurrent version conflicts.
        prompt = await self.repository.get_by_id_for_update(
            prompt_id=prompt_id,
            user_id=user_id,
        )

        if prompt is None:
            raise PromptNotFoundError("Prompt not found.")

        # Calculate the next version number.
        next_version = prompt.current_version + 1

        # Insert the new immutable version.
        version = await self.repository.create_version(
            prompt_id=prompt.id,
            version_number=next_version,
            content=content,
        )

        # Update prompt metadata and current version.
        await self.repository.update(
            prompt,
            name=name,
            description=description,
            current_version=next_version,
        )

        return prompt, version

    async def list_versions(
        self,
        *,
        prompt_id: UUID,
        user_id: UUID,
    ) -> list[PromptVersion]:
        # Verify ownership before exposing version history.
        prompt = await self.repository.get_by_id(
            prompt_id=prompt_id,
            user_id=user_id,
        )

        if prompt is None:
            raise PromptNotFoundError("Prompt not found.")

        return await self.repository.list_versions(
            prompt_id=prompt.id,
        )

    async def get_version(
        self,
        *,
        prompt_id: UUID,
        user_id: UUID,
        version_number: int,
    ) -> PromptVersion:
        # Verify ownership before retrieving a version.
        prompt = await self.repository.get_by_id(
            prompt_id=prompt_id,
            user_id=user_id,
        )

        if prompt is None:
            raise PromptNotFoundError("Prompt not found.")

        version = await self.repository.get_version(
            prompt_id=prompt.id,
            version_number=version_number,
        )

        if version is None:
            raise PromptVersionNotFoundError(
                f"Prompt version {version_number} not found."
            )

        return version
    async def count_prompts(self, *, user_id: UUID) -> int:
       return await self.repository.count_by_user(user_id=user_id)


from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt, PromptVersion
from sqlalchemy import desc, func, select


class PromptRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        user_id: UUID,
        name: str,
        description: str | None,
    ) -> Prompt:
        prompt = Prompt(
            user_id=user_id,
            name=name,
            description=description,
            current_version=1,
        )

        self.session.add(prompt)
        await self.session.flush()
        await self.session.refresh(prompt)

        return prompt

    async def get_by_id(
        self,
        *,
        prompt_id: UUID,
        user_id: UUID,
    ) -> Prompt | None:
        statement = select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.user_id == user_id,
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(
        self,
        *,
        prompt_id: UUID,
        user_id: UUID,
    ) -> Prompt | None:
        statement = (
            select(Prompt)
            .where(
                Prompt.id == prompt_id,
                Prompt.user_id == user_id,
            )
            .with_for_update()
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        *,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Prompt]:
        statement = (
            select(Prompt)
            .where(Prompt.user_id == user_id)
            .order_by(desc(Prompt.updated_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def create_version(
        self,
        *,
        prompt_id: UUID,
        version_number: int,
        content: str,
    ) -> PromptVersion:
        version = PromptVersion(
            prompt_id=prompt_id,
            version_number=version_number,
            content=content,
        )

        self.session.add(version)
        await self.session.flush()
        await self.session.refresh(version)

        return version

    async def get_version(
        self,
        *,
        prompt_id: UUID,
        version_number: int,
    ) -> PromptVersion | None:
        statement = select(PromptVersion).where(
            PromptVersion.prompt_id == prompt_id,
            PromptVersion.version_number == version_number,
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_versions(
        self,
        *,
        prompt_id: UUID,
    ) -> list[PromptVersion]:
        statement = (
            select(PromptVersion)
            .where(PromptVersion.prompt_id == prompt_id)
            .order_by(desc(PromptVersion.version_number))
        )

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def update(
        self,
        prompt: Prompt,
        *,
        name: str,
        description: str | None,
        current_version: int,
    ) -> Prompt:
        prompt.name = name
        prompt.description = description
        prompt.current_version = current_version

        await self.session.flush()
        await self.session.refresh(prompt)

        return prompt

    async def count_by_user(self, *, user_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(Prompt)
            .where(Prompt.user_id == user_id)
        )

        result = await self.session.execute(statement)
        return result.scalar_one()

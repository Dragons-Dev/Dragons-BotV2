from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager

import discord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..enums import SettingsEnum
from .models import Settings

__all__ = ["BaseRepository", "SettingsRepository"]


class BaseRepository:
    """Base class for all domain database repositories."""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self._session_maker = session_maker

    @property
    def session_maker(self) -> async_sessionmaker[AsyncSession]:
        return self._session_maker

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provides a transactional asynchronous database session."""
        async with self._session_maker() as session:
            async with session.begin():
                yield session


class SettingsRepository(BaseRepository):
    """Repository for global guild settings."""

    async def get_setting(self, setting: SettingsEnum, guild: discord.Guild) -> Settings | None:
        async with self.session() as session:
            query = select(Settings).where(Settings.setting == setting.value, Settings.guild == guild.id)
            response = await session.execute(query)
            result = response.scalars().first()
        if not result:
            return None
        return result

    async def get_all_settings(self, setting: SettingsEnum) -> Sequence[Settings] | None:
        async with self.session() as session:
            query = select(Settings).where(Settings.setting == setting.value)
            response = await session.execute(query)
            results = response.scalars().fetchall()
        if not results:
            return None
        return results

    async def update_setting(self, setting: SettingsEnum, value: int, guild: discord.Guild) -> None:
        """
        Updates a setting in the database.

        Args:
            setting (SettingsEnum): The setting to update.
            value (int): The new value of the setting.
            guild (discord.Guild): The guild associated with the setting.
        """
        async with self._session_maker() as session:
            async with session.begin():
                query = select(Settings).where(Settings.setting == setting.value, Settings.guild == guild.id)
                db_setting = (await session.execute(query)).scalar_one_or_none()
                if db_setting is None:
                    session.add(Settings(setting=setting.value, value=value, guild=guild.id))
                else:
                    db_setting.value = value
            await session.commit()

    async def delete_setting(self, setting: SettingsEnum, guild: discord.Guild) -> None:
        """
        Deletes a setting from the database.

        Args:
            setting (SettingsEnum): The setting to delete.
            guild (discord.Guild): The guild associated with the setting.
        """
        async with self._session_maker() as session:
            async with session.begin():
                query = select(Settings).where(Settings.setting == setting.value, Settings.guild == guild.id)
                db_setting = (await session.execute(query)).scalar_one_or_none()
                if db_setting is None:
                    return None
                await session.delete(db_setting)
                await session.commit()

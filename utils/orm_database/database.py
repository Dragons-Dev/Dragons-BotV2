from collections.abc import Sequence
from datetime import datetime
import importlib
from pathlib import Path

import discord
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import DATABASE_URL
from migrations import run_migrations

from ..enums import SettingsEnum
from ..logger import CustomLogger
from ..utils import VersionInfo
from .models import Base, Settings
from .repository import SettingsRepository


class ORMDataBase:
    """
    ORMDataBase class handles the asynchronous database connection, lifecycle, and core settings using SQLAlchemy.
    """

    def __init__(self):
        """
        Initializes the ORMDataBase instance with an async engine and session maker.
        """
        self.logger: CustomLogger = None  # type: ignore
        self.engine: AsyncEngine = create_async_engine(DATABASE_URL)
        self.AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False
        )
        self.settings: SettingsRepository = SettingsRepository(self.AsyncSessionLocal)

    @property
    def session_maker(self) -> async_sessionmaker[AsyncSession]:
        """Returns the async session maker factory."""
        return self.AsyncSessionLocal

    @staticmethod
    def _discover_models() -> None:
        """Imports all extension model modules so they register with Base.metadata."""
        extensions_dir = Path("extensions")
        if not extensions_dir.exists():
            return
        for model_file in extensions_dir.rglob("models.py"):
            module_name = ".".join(model_file.with_suffix("").parts)
            importlib.import_module(module_name)

    async def setup(self, boot: datetime, version: VersionInfo | None = None):
        """
        Sets up the database by running migrations and creating new tables if they don't already exist.

        Args:
            boot (datetime): The boot time of the application.
            version (VersionInfo | None): Current bot version for migration execution.
        """
        self.logger = CustomLogger("database", boot)  # type: ignore
        self._discover_models()
        if version is not None:
            await run_migrations(self.engine, boot, version)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            self.logger.info("ContentDB tables created and ready to use!")

    async def close(self):
        """
        Closes the database connection and disposes of the engine.
        """
        self.logger.warning("Closing database connection")
        await self.engine.dispose()

    async def get_setting(self, setting: SettingsEnum, guild: discord.Guild) -> Settings | None:
        return await self.settings.get_setting(setting, guild)

    async def get_all_settings(self, setting: SettingsEnum) -> Sequence[Settings] | None:
        return await self.settings.get_all_settings(setting)

    async def update_setting(self, setting: SettingsEnum, value: int, guild: discord.Guild) -> None:
        await self.settings.update_setting(setting, value, guild)

    async def delete_setting(self, setting: SettingsEnum, guild: discord.Guild) -> None:
        await self.settings.delete_setting(setting, guild)

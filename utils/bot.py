from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
from discord.ext import commands, ipc
from pycord.multicog import Bot as MulticogBot

from config import IPC_SECRET

from .database import ShortTermStorage
from .logger import CustomLogger
from .orm_database import ORMDataBase

if TYPE_CHECKING:
    from .utils import VersionInfo


class Bot(
    MulticogBot, commands.Bot
):  # subclass of both MulticogBot and commands.Bot to allow slash commands across multiple cogs
    def __init__(self, version, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.version: VersionInfo = version
        self.api: aiohttp.ClientSession = None  # type: ignore
        self.boot_time = datetime.now()
        self.db: ORMDataBase = ORMDataBase()
        self.sts: ShortTermStorage = ShortTermStorage(path="data/sts.sqlite")
        self._db_initialized: bool = False
        self.ipc = ipc.Server(self, secret_key=IPC_SECRET)
        self.logger = CustomLogger(name="core", start_stamp=self.boot_time)
        self._app_emojis: dict[str, str] = {}

    @property  # type: ignore[override]
    def app_emojis(self) -> dict[str, str]:
        return self._app_emojis

    @app_emojis.setter
    def app_emojis(self, value: dict[str, str]) -> None:
        self._app_emojis = value

    async def ensure_application_emoji(self, name: str, icon_path: str | Path) -> str | None:
        if name in self._app_emojis:
            return self._app_emojis[name]

        try:
            existing_emojis = await self.fetch_emojis()
            for emoji in existing_emojis:
                self._app_emojis[emoji.name] = str(emoji)

            if name in self._app_emojis:
                self.logger.debug(f"Found existing application emoji '{name}': {self._app_emojis[name]}")
                return self._app_emojis[name]

            path = Path(icon_path)
            if not path.is_file():
                self.logger.warning(f"Application emoji asset not found at '{path}'.")
                return None

            created_emoji = await self.create_emoji(name=name, image=path.read_bytes())
            self._app_emojis[name] = str(created_emoji)
            self.logger.info(f"Created application emoji '{name}': {self._app_emojis[name]}")
            return self._app_emojis[name]
        except Exception as e:
            self.logger.warning(f"Failed to ensure application emoji '{name}': {e}")
            return None

    async def setup_databases(self) -> None:
        if self._db_initialized:
            return
        await self.sts.setup(self.boot_time)
        self.logger.debug("Initialized sts db")
        await self.db.setup(self.boot_time, self.version)
        self.logger.debug("Initialized content db")
        self._db_initialized = True

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        await self.setup_databases()
        await super().start(token, reconnect=reconnect)

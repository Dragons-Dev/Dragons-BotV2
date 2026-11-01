from datetime import datetime
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

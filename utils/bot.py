from datetime import datetime
from typing import TYPE_CHECKING

import aiohttp
from discord.ext import commands, ipc
from pycord.multicog import Bot as MulticogBot

from config import IPC_SECRET

from .logger import CustomLogger

if TYPE_CHECKING:
    from .database import ShortTermStorage
    from .orm_database import ORMDataBase
    from .utils import VersionInfo


class Bot(
    MulticogBot, commands.Bot
):  # subclass of both MulticogBot and commands.Bot to allow slash commands across multiple cogs
    def __init__(self, version, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client_version: VersionInfo = version
        self.api: aiohttp.ClientSession = None  # type: ignore
        self.boot_time = datetime.now()
        self.db: ORMDataBase = None  # type: ignore
        self.sts: ShortTermStorage = None  # type: ignore
        self.ipc = ipc.Server(self, secret_key=IPC_SECRET)
        self.logger = CustomLogger(name="core", start_stamp=self.boot_time)

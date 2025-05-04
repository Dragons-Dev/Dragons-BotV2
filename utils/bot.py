from datetime import datetime

import aiohttp
from discord.ext import commands, ipc
from pycord.multicog import Bot as MulticogBot

from config import IPC_SECRET

from .database import ShortTermStorage
from .logger import CustomLogger
from .orm_database import *
from .utils import VersionInfo


class Bot(MulticogBot, commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client_version = VersionInfo(1, 6, 0, "")
        self.api: aiohttp.ClientSession = None  # type: ignore
        self.boot_time = datetime.now()
        self.db: ORMDataBase = None  # type: ignore
        self.sts: ShortTermStorage = None  # type: ignore
        self.ipc = ipc.Server(self, secret_key=IPC_SECRET)
        self.logger = CustomLogger(name="core", start_stamp=self.boot_time)

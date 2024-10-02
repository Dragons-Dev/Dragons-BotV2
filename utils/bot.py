from datetime import datetime

import aiohttp
from discord.ext import commands, ipc
from pycord.multicog import Bot as multicogBot

from config import IPC_SECRET

from .database import ContentDB, ShortTermStorage
from .logger import CustomLogger
from .utils import VersionInfo


class Bot(multicogBot, commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client_version = VersionInfo(1, 3, 3, "")
        self.api: aiohttp.ClientSession = None  # type: ignore
        self.boot_time = datetime.now()  # Ignoring because it's dynamically allocated
        self.db: ContentDB = None  # type: ignore
        self.sts: ShortTermStorage = None  # type: ignore
        self.ipc = ipc.Server(self, secret_key=IPC_SECRET)
        self.logger = CustomLogger(name="core", start_stamp=self.boot_time)

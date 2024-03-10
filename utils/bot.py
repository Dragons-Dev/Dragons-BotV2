from datetime import datetime

from aiohttp import ClientSession
from discord.ext import commands, ipc

from config import DISCORD_API_KEY, IPC_SECRET, client_version

from .database import ContentDB, ShortTermStorage
from .logger import CustomLogger


class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api = ClientSession("https://discord.com", headers={"Authorization": "Bot " + DISCORD_API_KEY})
        self.boot_time = datetime.now()  # Ignoring because it's dynamically allocated
        self.db: ContentDB = None  # type: ignore
        self.sts: ShortTermStorage = None  # type: ignore
        self.ipc = ipc.Server(self, secret_key=IPC_SECRET)
        self.logger = CustomLogger(name="bot.core", start_stamp=self.boot_time)
        self.version = client_version

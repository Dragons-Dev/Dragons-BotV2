from datetime import datetime

from aiohttp import ClientSession
from discord.ext import commands, ipc

from config import DISCORD_TOKEN, IPC_SECRET

from .logger import CustomLogger


class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.boot = datetime.now()
        self.api = ClientSession("https://discord.com", headers={"Authorization": "Bot " + DISCORD_TOKEN})
        self.ipc = ipc.Server(self, secret_key=IPC_SECRET)
        self.logger = CustomLogger(name="bot.core", start_stamp=self.boot)

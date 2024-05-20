import discord
from discord.ext import commands, tasks

from utils import Bot, CustomLogger


class BotStatus(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @commands.Cog.listener("on_start_done")
    async def start_status(self):
        while True:
            await self.client.change_presence(
                activity=discord.Activity(type=discord.ActivityType.listening), status=discord.Status.online
            )


def setup(client):
    client.add_cog(BotStatus(client))

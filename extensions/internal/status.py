from asyncio import sleep

import discord
from discord.ext import commands, tasks

from utils import Bot, BotActivity, CustomLogger


class BotStatus(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.statuses: list[BotActivity] = [
            BotActivity(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="you",
                ),
                status=discord.Status.idle,
            ),
            BotActivity(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name="your commands",
                ),
                status=discord.Status.do_not_disturb,
            ),
            BotActivity(
                activity=discord.Activity(
                    type=discord.ActivityType.playing,
                    name="in a test environment!",
                ),
                status=discord.Status.online,
            ),
        ]

    @commands.Cog.listener("on_start_done")
    async def start_status(self):
        while self.client.loop.is_running():
            for status in self.statuses:
                await self.client.change_presence(
                    activity=status.activity,
                    status=status.status,
                )
                await sleep(30)


def setup(client):
    client.add_cog(BotStatus(client))

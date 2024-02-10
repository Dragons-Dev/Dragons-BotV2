from datetime import datetime

import discord
from discord.ext import commands, tasks

from utils import Bot, CustomLogger
from utils.enums import SettingsEnum


class STSClear(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.to_delete = []

    @tasks.loop(hours=1)
    async def delete_expired(self):
        response = await self.client.sts.get_tagesschau_rows()
        print(response)
        for row in response:
            if row["expires"] < datetime.now():
                print(f"{row} is expired")
                await self.client.sts.delete_tagesschau_id(row["id"])

    @commands.Cog.listener("on_start_done")
    async def start_done(self):
        self.delete_expired.start()


def setup(client):
    client.add_cog(STSClear(client))

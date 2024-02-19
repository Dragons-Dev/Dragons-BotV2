from datetime import datetime

from discord.ext import commands, tasks

from utils import Bot, CustomLogger


class STSClear(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @tasks.loop(hours=1)
    async def delete_expired(self):
        response = await self.client.sts.get_tagesschau_rows()
        for row in response:
            if row["expires"] < datetime.now():
                await self.client.sts.delete_tagesschau_id(row["id"])

    @commands.Cog.listener("on_start_done")
    async def start_done(self):
        self.delete_expired.start()


def setup(client):
    client.add_cog(STSClear(client))

import discord
import aiohttp
from discord.ext import commands, tasks
from utils import Bot, CustomLogger, VersionInfo
from datetime import time
from config import SERVER_TZ


class ReleaseAnnouncer(commands.Cog):
    def __init__(self, client: Bot):
        self.client = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.repo = "Dragons-Dev/Dragons-BotV2"
        self.github_api = f"https://api.github.com/repos/{self.repo}"

    @commands.Cog.listener("on_start_done")
    async def start_done(self):
        self.reminder_loop.start()

    @tasks.loop(time=time(hour=12, tzinfo=SERVER_TZ))
    async def reminder_loop(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.github_api}/releases/latest") as response:
                new_latest = await response.json()
                github_version = VersionInfo.from_str(new_latest["tag_name"])
                try:
                    if self.client.client_version >= github_version:
                        pass
                    else:
                        self.logger.info(f"Newer release on github. Pls update. Version: {github_version}")
                        owner = (await self.client.application_info()).owner
                        if owner is None:
                            self.logger.critical(
                                "Fuck something is terible wrong pls nuke everything and begin from the start."
                            )
                            return
                        em = discord.Embed(title="🚨 UPDATE YOUR BOT", color=discord.Color.brand_red())
                        em.add_field(
                            name="",
                            value=f"Your bot is no longer on the newest verion `{github_version}`.\nYour bot is on version `{self.client.client_version}`.",
                        )
                        await owner.send(embed=em)
                except Exception as e:
                    self.logger.warning(f"{e}")


def setup(client):
    client.add_cog(ReleaseAnnouncer(client))

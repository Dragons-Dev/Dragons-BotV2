import discord
from discord.ext import commands, tasks

from utils import Bot, CustomLogger
from utils.enums import SettingsEnum


class InternalHooks(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.news = []
        self.news_webhooks = {}

    @tasks.loop(minutes=1)
    async def send_news(self):
        resp = await self.client.db.get_global_setting(SettingsEnum.TagesschauChannel)
        for channel, guild in resp:
            try:
                webhook = self.news_webhooks[f"{guild}"]
            except KeyError:
                g = self.client.get_guild(guild)
                if g is None:
                    g = await self.client.fetch_guild(guild)
                c: discord.TextChannel = g.get_channel(channel)
                if c is None:
                    c: discord.TextChannel = await self.client.fetch_channel(channel)  # type: ignore #type is inherited
                webhooks = await c.webhooks()
                for webhook in webhooks:
                    if webhook.name == "Tagesschau":
                        self.news_webhooks[f"{guild}"] = webhook
                        break
                else:
                    webhook = await c.create_webhook(name="Tagesschau")
                    self.news_webhooks[f"{guild}"] = webhook
            if len(self.news) == 0:
                return
            if len(self.news) > 10:
                sub = []
                for _ in range(10):
                    sub.append(self.news.pop())
                await webhook.send(
                    username="Tagesschau Feed",
                    avatar_url="https://www.ard.de/static/media/appIcon.ts.b846aebc4c4b299d0fbd.jpg",
                    embeds=sub,
                )
            else:
                await webhook.send(
                    username="Tagesschau Feed",
                    avatar_url="https://www.ard.de/static/media/appIcon.ts.b846aebc4c4b299d0fbd.jpg",
                    embeds=self.news,
                )
                self.news.clear()

    @commands.Cog.listener("on_tagesschau_entry")
    async def on_tagesschau_entry(self, entries: list[discord.Embed]):
        for entry in entries:
            self.news.append(entry)
        self.logger.debug(f"{len(entries)} new tagesschau-entries to send")
        self.logger.debug(f"{len(self.news)} tagesschau-entries to send")

    @commands.Cog.listener("on_start_done")
    async def start_done(self):
        self.send_news.start()


def setup(client):
    client.add_cog(InternalHooks(client))

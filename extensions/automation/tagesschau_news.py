import discord
import feedparser
from discord.ext import commands, tasks

from utils import Bot, CustomLogger, SettingsEnum


def parse_tagesschau_feed(entry: dict) -> dict:
    return {
        "title": entry["title_detail"]["value"],
        "summary": entry["summary_detail"]["value"],
        "link": entry["link"],
        "published": entry["published_parsed"],
        "updated": entry["updated_parsed"],
        "id": entry["id"][-36:],
    }


class TagesschauFeed(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot)
        self.url = "https://www.tagesschau.de/infoservices/alle-meldungen-100.html"

    @tasks.loop(minutes=1)
    async def gather_news(self):
        news = feedparser.parse(self.url)


def setup(client):
    client.add_cog(TagesschauFeed(client))

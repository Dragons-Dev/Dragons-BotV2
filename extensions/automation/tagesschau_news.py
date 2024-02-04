import re

import discord
import feedparser
from discord.ext import commands, tasks

from utils import Bot, CustomLogger, SettingsEnum

regex = r"https:\/\/images\.tagesschau\.de\/image\/[a-zA-Z0-9-]*/[a-zA-Z0-9-_]*/[a-zA-Z0-9-]*/[a-zA-Z0-9-]*-[a-zA-Z0-9-]*/[a-zA-Z0-9-]*.jpg"


def parse_tagesschau_feed(entry: dict) -> dict:
    return {
        "title": entry["title_detail"]["value"],
        "summary": entry["summary_detail"]["value"],
        "link": entry["link"],
        "published": entry["published_parsed"],
        "updated": entry["updated_parsed"],
        "id": entry["id"][-36:],
        "image": re.match(regex, str(entry), re.MULTILINE),
    }


class TagesschauFeed(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot)
        self.url = "https://www.tagesschau.de/infoservices/alle-meldungen-100~rss2.xml"
        self.gather_news.start()

    @tasks.loop(minutes=1)
    async def gather_news(self):
        news = feedparser.parse(self.url)
        new = list[discord.Embed]
        for entry in news["entries"]:
            ent = parse_tagesschau_feed(entry)
            ...
        self.client.dispatch("tagesschau_entry", new)


def setup(client):
    client.add_cog(TagesschauFeed(client))

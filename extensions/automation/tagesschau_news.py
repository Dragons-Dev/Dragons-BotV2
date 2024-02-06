import re
from datetime import datetime

import discord
import feedparser
from discord.ext import commands, tasks

from utils import Bot, CustomLogger, SettingsEnum

regex = r"https:\/\/images\.tagesschau\.de\/image\/[a-zA-Z0-9-]*/[a-zA-Z0-9-_]*/[a-zA-Z0-9-]*/[a-zA-Z0-9-]*-[a-zA-Z0-9-]*/[a-zA-Z0-9-]*.jpg"


def parse_tagesschau_feed(entry: dict) -> dict:
    published = datetime(
        entry["published_parsed"][0],
        entry["published_parsed"][1],
        entry["published_parsed"][2],
        entry["published_parsed"][3],
        entry["published_parsed"][4],
        entry["published_parsed"][5],
    )
    updated = datetime(
        entry["updated_parsed"][0],
        entry["updated_parsed"][1],
        entry["updated_parsed"][2],
        entry["updated_parsed"][3],
        entry["updated_parsed"][4],
        entry["updated_parsed"][5],
    )
    return {
        "title": entry["title_detail"]["value"],
        "summary": entry["summary_detail"]["value"],
        "link": entry["link"],
        "published": published,
        "updated": updated,
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
        await self.client.wait_until_ready()
        news = feedparser.parse(self.url)
        new = []
        for entry in news["entries"]:
            ent = parse_tagesschau_feed(entry)
            em = discord.Embed(
                title=ent["title"],
                url=ent["link"],
                description=ent["summary"]
                + f"\n\nPublished: {discord.utils.format_dt(ent['published'])}"
                + f"\n Updated: {discord.utils.format_dt(ent['updated'])}",
                image=discord.EmbedMedia(ent["image"]),
                color=discord.Color.from_rgb(60, 87, 141),
            )
            new.append(em)
        self.client.dispatch("tagesschau_entry", new)


def setup(client):
    client.add_cog(TagesschauFeed(client))

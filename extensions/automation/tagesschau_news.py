import re
from datetime import datetime, timedelta

import discord
import feedparser
from discord.ext import commands, tasks

from utils import Bot, CustomLogger

regex = r"https://images.tagesschau.de/image/[a-zA-Z0-9-_]*/[a-zA-Z0-9-_]*/[a-zA-Z0-9-_]*/[a-zA-Z0-9-]*-[a-zA-Z0-9-]*/[a-zA-Z0-9-]*.jpg"


def parse_tagesschau_feed(entry: dict) -> dict:
    """Parses an entry from feedparser to values that are important

    Args:
        entry (dict): feedparser.entry

    Returns:
        dict: Python standart dict
    """
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
    image_link = re.finditer(regex, str(entry), re.MULTILINE)
    image = None
    for match in image_link:
        image = match.group()
    return {
        "title": entry["title_detail"]["value"],
        "summary": entry["summary_detail"]["value"],
        "link": entry["link"],
        "published": published,
        "updated": updated,
        "id": entry["id"][-36:],
        "image": image,
    }


class TagesschauFeed(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.url = "https://www.tagesschau.de/infoservices/alle-meldungen-100~rss2.xml"

    @tasks.loop(minutes=1)
    async def gather_news(self):
        await self.client.wait_until_ready()
        news = feedparser.parse(self.url)
        self.logger.debug(f"Requested {self.url}")
        new = []
        for entry in news["entries"]:
            ent = parse_tagesschau_feed(entry)
            resp = await self.client.sts.get_tagesschau_id(ent["id"])
            if resp is not None:
                if resp["updated"] == ent["updated"]:
                    return
                else:
                    em = discord.Embed(
                        title=ent["title"],
                        url=ent["link"],
                        description=ent["summary"]
                        + f"\n\nPublished: {discord.utils.format_dt(ent['published'])}"
                        + f"\n Updated: {discord.utils.format_dt(ent['updated'])}",
                        image=discord.EmbedMedia(ent["image"]),
                        color=discord.Color.from_rgb(60, 87, 141),
                        footer=discord.EmbedFooter(
                            text="Distributed in compliance with the Creative Commons license\n(CC BY-SA)",
                            icon_url="https://raw.githubusercontent.com/github/explore/"
                            "48db34428146b2d62f0b7079fa6c12c711e2322f/topics/creative-commons/"
                            "creative-commons.png",
                        ),
                        author=discord.EmbedAuthor(
                            name="Source: Tagesschau.de",
                            url="https://www.tagesschau.de",
                            icon_url="https://www.ard.de/static/media/appIcon.ts.b846aebc4c4b299d0fbd.jpg",
                        ),
                    )
            else:
                em = discord.Embed(
                    title=ent["title"],
                    url=ent["link"],
                    description=ent["summary"]
                    + f"\n\nPublished: {discord.utils.format_dt(ent['published'])}"
                    + f"\n Updated: {discord.utils.format_dt(ent['updated'])}",
                    image=discord.EmbedMedia(ent["image"]),
                    color=discord.Color.from_rgb(60, 87, 141),
                    footer=discord.EmbedFooter(
                        text="Distributed in compliance with the Creative Commons license\n(CC BY-SA)",
                        icon_url="https://raw.githubusercontent.com/github/explore/"
                        "48db34428146b2d62f0b7079fa6c12c711e2322f/topics/creative-commons/creative-commons.png",
                    ),
                    author=discord.EmbedAuthor(
                        name="Source: Tagesschau.de",
                        url="https://www.tagesschau.de",
                        icon_url="https://www.ard.de/static/media/appIcon.ts.b846aebc4c4b299d0fbd.jpg",
                    ),
                )
                await self.client.sts.enter_tagesschau_id(
                    uuid=ent["id"], updated=ent["updated"], expires=datetime.now() + timedelta(5)
                )
            new.append(em)
        self.logger.debug(f"Sent {len(new)} entries to `on_tagesschau_entry`")
        self.client.dispatch("tagesschau_entry", new)  # rest is handled by /extensions/internal/webhooks.py

    @commands.Cog.listener("on_start_done")
    async def on_start_done(self):
        self.gather_news.start()


def setup(client):
    client.add_cog(TagesschauFeed(client))

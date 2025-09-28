import html
from datetime import datetime, timedelta

import aiohttp
import discord
import feedparser
from bs4 import BeautifulSoup
from discord.ext import commands, tasks

from utils import Bot, CustomLogger, WebhookType

regex = r"https://images\.tagesschau\.de/image/(?:[A-Za-z0-9_-]+/)+[A-Za-z0-9_-]+\.jpg(?:\?width=\d+)?"


def parse_tagesschau_feed(entry: dict) -> dict:
    """Parses an entry from feedparser to values that are important"""

    published = datetime(*entry["published_parsed"][:6])
    updated = datetime(*entry["updated_parsed"][:6])

    # HTML aus content:encoded holen
    html_content = ""
    if "content" in entry:
        for c in entry["content"]:
            if "value" in c:
                html_content = c["value"]
                break

    # HTML-Entities dekodieren
    html_content = html.unescape(html_content)

    # Bild-URL extrahieren
    image = None
    soup = BeautifulSoup(html_content, "html.parser")
    img_tag = soup.find("img")
    if img_tag and img_tag.has_attr("src"):
        image = img_tag["src"]

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
        self.session: aiohttp.ClientSession = None  # type: ignore

    @tasks.loop(seconds=90)
    async def gather_news(self):
        """fetches news from tagesschau.de, parses them and checks for already sent news"""
        await self.client.wait_until_ready()
        request = await self.session.get(self.url)
        data = await request.text()
        news = feedparser.parse(data)
        if request.status == 200:
            self.logger.debug(f"Requested {self.url}; {request.status}")
        else:
            self.logger.critical(f"Requested {self.url}; {request.status}")
        new = []
        for entry in news["entries"]:
            ent = parse_tagesschau_feed(entry)
            resp = await self.client.sts.get_tagesschau_id(ent["id"])
            em = None
            if resp is not None:  # if the post id is in the database
                if resp["updated"] == ent["updated"]:
                    pass
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
                    await self.client.sts.delete_tagesschau_id(ent["id"])
                    await self.client.sts.enter_tagesschau_id(
                        uuid=ent["id"], updated=ent["updated"], expires=datetime.now() + timedelta(5)
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
            if em is None:
                pass
            elif "Liveblog" in em.title:
                pass
            else:
                new.append((em, WebhookType.Tagesschau))
        self.logger.debug(f"Sent {len(new)} entries to `on_webhook_entry`")
        self.client.dispatch("webhook_entry", new)  # rest is handled by /extensions/internal/webhooks.py

    @commands.Cog.listener("on_start_done")
    async def on_start_done(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": f"Dragons BotV{self.client.client_version}"})
        self.gather_news.start()


def setup(client):
    client.add_cog(TagesschauFeed(client))

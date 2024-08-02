# type: ignore

import aiohttp
import discord
import feedparser
from bs4 import BeautifulSoup
from discord.ext import commands

from utils import Bot, CustomLogger


class FefeBlog(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.url = "https://blog.fefe.de/rss.xml?html"
        self.session = aiohttp.ClientSession(headers={"User-Agent": f"Dragons BotV{self.client.client_version}"})

    async def _get_news(self) -> str | None:
        async with self.session.get(self.url) as response:
            if response.status == 200:
                self.logger.debug(f"Requested {self.url}; {response.status}")
                return await response.text()
            else:
                self.logger.critical(f"Requested {self.url}; {response.status}")
                return None

    async def parse_news(self, text: str) -> str:
        news = await self._get_news()
        parsed = feedparser.parse(news)
        embeds = []
        for entry in parsed["entries"]:
            summary = BeautifulSoup(entry["summary"], features="html.parser")
            try:
                replacement = f"[<{summary.a.contents[0]}>]({summary.a["href"]})"
            except (TypeError, AttributeError):
                replacement = None
            if replacement:
                summary.a.replace_with(replacement)
            embed = discord.Embed(title=entry["title"], url=entry["link"], description=summary)
            embeds.append(embed)
        return parsed


if __name__ == "__main__":
    test = False
    if test:
        x = requests.get("https://blog.fefe.de/rss.xml?html")
        print(x.status_code)
        print(x.text)
    else:
        news = _get_news("https://blog.fefe.de/rss.xml")
        print(news)
        print(parse_news(news))
        embeds = []
        for entry in parse_news(news)["entries"]:
            print(entry)
            print(entry["title"])
            print(entry["link"])
            summary = BeautifulSoup(entry["summary"], features="html.parser")
            print(summary)
            try:
                replacement = f"[<{summary.a.contents[0]}>]({summary.a["href"]})"
            except (TypeError, AttributeError):
                replacement = None
            if replacement:
                summary.a.replace_with(replacement)
            embed = Embed(title=entry["title"], url=entry["link"], description=summary)
            embeds.append(embed)


def setup(client: Bot):
    client.add_cog(FefeBlog(client))

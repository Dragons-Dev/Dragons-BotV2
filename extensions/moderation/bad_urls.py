import json
import re
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands
from discord.utils import format_dt, get_or_fetch

from config import GOOGLE_API_KEY
from utils import Bot, CustomLogger, InfractionsEnum, SettingsEnum


class BadURL(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.bad_hashes = []
        self.detect_session = None
        self.reg_url = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-&?=%.]+"

    async def bad_url(self, listed_urls: list) -> dict | bool:
        if GOOGLE_API_KEY == "":
            return False  # since no api key is given, we can't check for bad urls
        else:
            try:
                headers = {
                    "Content-type": "application/json",
                }
                data = {
                    "client": {"clientId": "private", "clientVersion": self.client.client_version.__str__()},
                    "threatInfo": {
                        "threatTypes": [
                            "MALWARE",
                            "SOCIAL_ENGINEERING",
                            "THREAT_TYPE_UNSPECIFIED",
                            "POTENTIALLY_HARMFUL_APPLICATION",
                        ],
                        "platformTypes": ["ANY_PLATFORM"],
                        "threatEntryTypes": ["URL"],
                        "threatEntries": [{"url": url} for url in listed_urls],
                    },
                }
                request = await self.detect_session.post(
                    f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={GOOGLE_API_KEY}",
                    headers=headers,
                    data=json.dumps(data),
                )
                response = await request.json()
                self.logger.debug(f"{request.status}: Requested safebrowsing api -> {json.dumps(data)}")
                return response
            except Exception as e:
                self.logger.critical(f"Fatal error", exc_info=e)
                return False

    @commands.Cog.listener("on_message")
    async def message_event(self, msg: discord.Message) -> None:
        if msg.author.id == self.client.user.id:
            return
        matches = re.finditer(self.reg_url, msg.content, re.MULTILINE)
        urls = []
        for match in matches:
            if match is not None:
                urls.append(match.group())
        if len(urls) == 0:
            return
        else:
            is_bad_store = await self.bad_url(urls)
            if is_bad_store:  # false wont get to the for loop
                await msg.delete(reason="Detected as bad url")  # First delete the bad urls
                case = await self.client.db.create_infraction(
                    user=msg.author, infraction=InfractionsEnum.Ban, reason="Bad URL sent", guild=msg.guild
                )

                em = discord.Embed(title="Message delete", color=discord.Color.yellow())
                em.add_field(name="User", value=msg.author.mention, inline=False)
                em.add_field(name="Moderator", value=self.client.user.mention, inline=False)
                em.add_field(name="Reason", value="Sending a malicious link", inline=False)
                em.add_field(name="Date", value=format_dt(datetime.now(), "F"), inline=False)
                em.set_footer(text=f"Case ID: {case}")

                setting = await self.client.db.get_setting(setting=SettingsEnum.ModLogChannel, guild=msg.guild)
                log_channel: discord.TextChannel = await get_or_fetch(msg.guild, "channel", setting, default=None)
                await log_channel.send(embed=em)

    @commands.Cog.listener("on_start_done")
    async def bad_urls_done(self):
        self.detect_session = aiohttp.ClientSession(headers={"User-Agent": f"Dragons BotV{self.client.client_version}"})


def setup(client):
    client.add_cog(BadURL(client))

import json
import re

import aiohttp
import discord
from discord.ext import commands
from discord.utils import get_or_fetch

from config import GOOGLE_API_KEY
from utils import Bot, CustomLogger, SettingsEnum


class BadURL(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.bad_hashes = []
        self.detect_session = aiohttp.ClientSession()
        self.reg_url = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-&?=%.]+"

    async def bad_url(self, listed_urls: list) -> dict | bool:
        if GOOGLE_API_KEY == "":
            return False  # since no api key is given, we can't check for bad urls
        else:
            try:
                headers = {"Content-type": "application/json"}
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
            self.client.dispatch("stat_counter", "URLs checked", len(urls), msg.guild)
            is_bad_store = await self.bad_url(urls)
            if is_bad_store:  # false wont get to the for loop
                modmail_channel = await self.client.db.get_setting(SettingsEnum.ModmailChannel, msg.guild)
                channel = await get_or_fetch(msg.guild, "channel", modmail_channel, default=None)
                link_reason = []
                for entry in is_bad_store["matches"]:  # type: ignore
                    link_reason.append(f'{entry["threat"]["url"]} - {entry["threatType"]}')
                if channel is None:
                    try:
                        await msg.guild.owner.send(
                            "Your modmail channel is not set up correctly. "
                            "I need this to inform you about rule breaker!"
                            f"User: {msg.author.mention}({msg.author.id})"
                            f"Channel: {msg.channel.mention}\n" + "\n".join(link_reason)
                        )
                    except discord.HTTPException or discord.Forbidden:
                        pass
                else:
                    await msg.delete(reason="Detected as bad url")
                    if channel.type == discord.ChannelType.forum:
                        await channel.create_thread(
                            ":warning: Bad Link :warning:",
                            f"""
User: {msg.author.mention} ({msg.author.id})
Channel: {msg.channel.mention}\n
"""
                            + "\n".join(link_reason),
                        )
                    else:
                        await channel.send(
                            f"""
User: {msg.author.mention} ({msg.author.id})
Channel: {msg.channel.mention}\n
"""
                            + "\n".join(link_reason)
                        )


def setup(client):
    client.add_cog(BadURL(client))

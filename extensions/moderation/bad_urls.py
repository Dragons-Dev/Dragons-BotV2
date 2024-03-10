import hashlib
import json
import re

import aiohttp
import discord
from discord.ext import commands, tasks

from config import GOOGLE_API_KEY, VersionInfo
from utils import Bot, CustomLogger


class BadURL(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.bad_hashes = []
        self.detect_session = aiohttp.ClientSession()
        self.update_discord_domains.start()
        self.reg_url = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-&?=%.]+"

    async def bad_url(self, listed_urls: list) -> bool:
        if GOOGLE_API_KEY == "":
            return False
        else:
            try:
                headers = {"Content-type": "application/json"}
                data = {
                    "client": {"clientId": "private", "clientVersion": self.client.version.__str__()},
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
                self.logger.debug(f"{request.status}: Requested safebrowsing api {json.dumps(data)}")
                print(response)
                if response == "":
                    return False
                else:
                    return True
            except Exception as e:
                self.logger.critical(f"Fatal error", exc_info=e)
                return False

    @commands.Cog.listener("on_message")
    async def message_event(self, msg: discord.Message) -> None:
        matches = re.finditer(self.reg_url, msg.content, re.MULTILINE)
        if len([match.group() for match in matches]) == 0:
            return
        else:
            is_bad = await self.bad_url([match.group() for match in matches])
            if is_bad:
                await msg.delete()


def setup(client):
    client.add_cog(BadURL(client))

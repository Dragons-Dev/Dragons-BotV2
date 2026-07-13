import re
import typing as t
from datetime import datetime
from urllib.parse import urlsplit

from aiocache import caches, SimpleMemoryCache
import aiohttp
import discord
from discord.ext import commands
from discord.utils import format_dt, get_or_fetch

from config import GOOGLE_API_KEY
from utils import Bot, CustomLogger, InfractionsEnum, SettingsEnum, ButtonInfo


GOOGLE_API_KEY_REGEX = r"AIza[0-9A-Za-z-_]{35}"


THREAT_TYPES = {
    0: "THREAT_TYPE_UNSPECIFIED",
    1: "MALWARE",
    2: "SOCIAL_ENGINEERING",
    3: "UNWANTED_SOFTWARE",
    4: "POTENTIALLY_HARMFUL_APPLICATION",
}


# these functions were entirely written by AI but still reviewed by human.
def read_varint(data: bytes, index: int) -> tuple[int, int]:
    """Read a protobuf varint starting at `index`.

    A varint is a variable-length integer encoding where each byte stores 7 bits of
    payload and the top bit indicates whether more bytes follow.

    Args:
        data: Raw byte buffer to read from.
        index: Current read position in `data`.

    Returns:
        A tuple of `(value, next_index)` where `value` is the decoded integer and
        `next_index` is the first byte after the varint.
    """
    value = 0
    shift = 0
    while True:
        byte = data[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return value, index


def parse_protobuf(data: bytes) -> list[tuple[int, int, bytes | int]]:
    """Parse a protobuf message into a list of generic field tuples.

    This is a low-level parser that understands the protobuf wire format, not any
    specific message schema. Each field is returned as:

        (field_number, wire_type, value)

    Supported wire types:
        - 0: varint
        - 1: 64-bit fixed-width value
        - 2: length-delimited value
        - 5: 32-bit fixed-width value

    Args:
        data: Raw protobuf-encoded bytes.

    Returns:
        A list of parsed fields, where `value` is either `bytes` or `int`
        depending on the wire type.

    Raises:
        ValueError: If an unknown wire type is encountered.
    """
    index = 0
    length = len(data)
    fields = []
    while index < length:
        key, index = read_varint(data, index)
        wire_type = key & 0x7
        field_num = key >> 3
        if wire_type == 0:
            value, index = read_varint(data, index)
            fields.append((field_num, wire_type, value))
        elif wire_type == 1:
            value = data[index : index + 8]
            index += 8
            fields.append((field_num, wire_type, value))
        elif wire_type == 2:
            field_len, index = read_varint(data, index)
            value = data[index : index + field_len]
            index += field_len
            fields.append((field_num, wire_type, value))
        elif wire_type == 5:
            value = data[index : index + 4]
            index += 4
            fields.append((field_num, wire_type, value))
        else:
            raise ValueError(f"Unknown wire type {wire_type}")
    return fields


def parse_search_urls_response(data: bytes) -> dict:
    """Parse a Safe Browsing `urls:search` response.

    The response is parsed as a protobuf message and then interpreted according to
    the expected Safe Browsing schema. The function extracts:

    - matched threat URLs
    - threat types for each match
    - cache duration from the response metadata

    Args:
        data: Raw response bytes returned by the Safe Browsing API.

    Returns:
        A dictionary with:
            - `matches`: list of dictionaries with `url` and `threat_types`
            - `cache_duration_sec`: cache duration in seconds, or `None` if absent
    """
    fields = parse_protobuf(data)
    matches = []
    cache_duration_sec = None

    for field_num, wire_type, value in fields:
        if field_num == 1 and wire_type == 2:
            # Parse ThreatUrl message.
            threat_fields = parse_protobuf(value)
            threat_url = ""
            threat_types = []
            for t_num, t_wire, t_val in threat_fields:
                if t_num == 1 and t_wire == 2:
                    # URL is stored as a UTF-8 string.
                    threat_url = t_val.decode("utf-8", errors="ignore")
                elif t_num == 2:
                    # Threat type can be encoded as a single enum value...
                    if t_wire == 0:
                        threat_types.append(t_val)
                    # ...or as packed repeated enum values in a length-delimited field.
                    elif t_wire == 2:
                        p_idx = 0
                        while p_idx < len(t_val):
                            p_val, p_idx = read_varint(t_val, p_idx)
                            threat_types.append(p_val)
            matches.append(
                {
                    "url": threat_url,
                    "threat_types": [THREAT_TYPES.get(t, f"UNKNOWN({t})") for t in threat_types],
                }
            )
        elif field_num == 2 and wire_type == 2:
            # Parse google.protobuf.Duration message.
            duration_fields = parse_protobuf(value)
            for d_num, d_wire, d_val in duration_fields:
                if d_num == 1 and d_wire == 0:
                    cache_duration_sec = d_val

    return {"matches": matches, "cache_duration_sec": cache_duration_sec}


async def fetch_safebrowsing(urls: list[str], cog_logger: CustomLogger) -> dict | None:
    """Query the Google Safe Browsing API for a list of URLs.

    The function limits the request to the first 50 URLs because that is the
    recommended maximum for a single request. It then sends the URLs as query
    parameters, reads the binary protobuf response, and parses it into a
    Python dictionary.

    Args:
        urls: List of URLs to check against Safe Browsing.
        cog_logger: Logger used to emit debug information about the request.

    Returns:
        The parsed response dictionary on HTTP 200, or `None` on failure.
    """
    # Limit to 50 URLs per request as per API guidelines.
    urls_to_check = urls[:50]
    params = [("key", GOOGLE_API_KEY)]
    for url in urls_to_check:
        params.append(("urls", url))

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://safebrowsing.googleapis.com/v5/urls:search",
            params=params,
        ) as request:
            cog_logger.debug(f"Checking URLs: {urls_to_check} | API Response Status: {request.status}")
            if request.status == 200:
                body = await request.read()
                return parse_search_urls_response(body)
            else:
                return None


class SafebrowsingCog(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.url_cache: SimpleMemoryCache = caches.get("default")
        self.detect_session: aiohttp.ClientSession = None  # type: ignore
        self.reg_url = r"(?:(?:https?):\/\/)?[\w/\-?=%.]+\.[\w/\-&?=%.]+"

    @commands.Cog.listener("on_message")
    async def message_event(self, msg: discord.Message) -> None:
        if not self.client.user:
            return
        if msg.author.id == self.client.user.id:
            return
        if not msg.guild:
            return

        matches = re.finditer(self.reg_url, msg.content, re.MULTILINE)
        removed_protocolls = []
        for match in matches:
            if match is None:
                continue
            url_fragments = urlsplit(match.group().lower())
            hostname = f"{url_fragments.hostname}{url_fragments.path}"
            removed_protocolls.append(hostname[4:] if hostname.startswith("None") else hostname)
        urls = set(removed_protocolls)
        # insert all regex matches into this list

        if len(urls) > 0:  # if there are no messages in the message don't continue
            filtered_urls = []
            urls_to_fetch = []  # prepare lists to fetch urls or get cached data
            for url in urls:
                cached_result = await self.url_cache.get(url)
                if cached_result is not None:
                    if cached_result == "True":  # seems to be that the cache only has strings as value
                        filtered_urls.append(url)  # url is in cache
                    else:
                        pass  # if not true, the url is checked against safebrowsing and returned as safe
                else:
                    urls_to_fetch.append(url)  # url needs to be fetched

            if len(urls_to_fetch) > 0:
                api_result = await fetch_safebrowsing(urls_to_fetch, self.logger)  # urls not cached need to be fetched
                if api_result is not None:
                    if api_result["matches"]:
                        for match in api_result["matches"]:
                            await self.url_cache.set(match["url"], True, ttl=3600)  # add returned bad urls to cache
                            if match["url"] in urls_to_fetch:
                                urls_to_fetch.remove(match["url"])  # remove bad urls, we use this list to cache as safe
                            filtered_urls.append(match["url"])  # append returned urls to the filter which are bad
                        for url in urls_to_fetch:
                            await self.url_cache.set(url, False, ttl=3600)  # every url which was not returned is safe
                else:
                    self.logger.warning(
                        f"Failed to fetch Safe Browsing results for URLs: {urls_to_fetch} | API Result: {api_result}"
                    )
                    return

            if len(filtered_urls) > 0:
                await msg.delete(reason="Detected as bad url")  # First delete the bad urls
                case_id = await self.client.db.create_infraction(
                    user=msg.author, infraction=InfractionsEnum.Warn, reason="Bad URL sent", guild=msg.guild
                )  # create infraction in db to get an infraction id

                em = discord.Embed(title="Message delete", color=discord.Color.yellow())
                em.add_field(name="User", value=msg.author.mention, inline=False)
                em.add_field(name="Moderator", value=self.client.user.mention, inline=False)
                em.add_field(name="Reason", value="Sending a malicious link", inline=False)
                em.add_field(name="Date", value=format_dt(datetime.now(), "F"), inline=False)
                em.set_footer(text=f"Case ID: {case_id}")

                link_bed = discord.Embed(
                    title="Message context",
                    description=f"{msg.content}\n\nYou were warned due to these links.\n"
                    f"{'\n'.join(f'- `{url}`' for url in filtered_urls)}",
                    color=discord.Color.green(),
                )
                link_bed.set_author(name=msg.author.display_name, icon_url=msg.author.display_avatar.url)
                link_bed.set_footer(text="If you believe this is a mistake, please contact an moderator.")
                try:
                    await msg.author.send(
                        embeds=[em, link_bed],
                        view=ButtonInfo("You were warned due to the message above."),
                    )
                except discord.Forbidden:
                    pass  # ignore closed dms
                except discord.HTTPException:
                    self.logger.warning(f"Couldn't send a message to {msg.author} due to HTTPException.")

                setting = await self.client.db.get_setting(setting=SettingsEnum.ModLogChannel, guild=msg.guild)
                # logic to get modmail channel
                if setting:
                    if isinstance(setting, (tuple, list, t.Sequence)):
                        log_channel: discord.TextChannel | None = await get_or_fetch(
                            msg.guild, discord.TextChannel, setting[0].value, default=None
                        )
                    else:
                        log_channel: discord.TextChannel | None = await get_or_fetch(
                            msg.guild, discord.TextChannel, setting.value, default=None
                        )

                    if log_channel:
                        await log_channel.send(embed=em)

    @commands.Cog.listener("on_start_done")
    async def bad_urls_done(self):
        self.detect_session = aiohttp.ClientSession(headers={"User-Agent": f"Dragons BotV{self.client.version}"})


def setup(client: Bot):
    if re.match(GOOGLE_API_KEY_REGEX, GOOGLE_API_KEY) is None:
        client.logger.error("No Google API key provided, skipping bad url detection")
        return
    client.add_cog(SafebrowsingCog(client))

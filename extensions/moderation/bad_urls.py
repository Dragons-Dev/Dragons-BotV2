import re
from urllib.parse import urlsplit

import aiohttp
from aiocache import SimpleMemoryCache
import discord
from discord.ext import commands

from config import GOOGLE_API_KEY
from utils import Bot, CustomLogger, InfractionsEnum

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


def _parse_threat_types(t_wire: int, t_val: bytes | int) -> list[int]:
    if t_wire == 0:
        return [int(t_val)]
    if t_wire == 2 and isinstance(t_val, bytes):
        types = []
        p_idx = 0
        while p_idx < len(t_val):
            p_val, p_idx = read_varint(t_val, p_idx)
            types.append(p_val)
        return types
    return []


def _parse_threat_fields(threat_fields: list[tuple[int, int, bytes | int]]) -> dict:
    threat_url = ""
    threat_types = []
    for t_num, t_wire, t_val in threat_fields:
        if t_num == 1 and t_wire == 2 and isinstance(t_val, bytes):
            threat_url = t_val.decode("utf-8", errors="ignore")
        elif t_num == 2:
            threat_types.extend(_parse_threat_types(t_wire, t_val))
    return {
        "url": threat_url,
        "threat_types": [THREAT_TYPES.get(t, f"UNKNOWN({t})") for t in threat_types],
    }


def _parse_duration_fields(duration_fields: list[tuple[int, int, bytes | int]]) -> int | None:
    for d_num, d_wire, d_val in duration_fields:
        if d_num == 1 and d_wire == 0 and isinstance(d_val, int):
            return d_val
    return None


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
        if field_num == 1 and wire_type == 2 and isinstance(value, bytes):
            matches.append(_parse_threat_fields(parse_protobuf(value)))
        elif field_num == 2 and wire_type == 2 and isinstance(value, bytes):
            cache_duration_sec = _parse_duration_fields(parse_protobuf(value))

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
        self.url_cache: SimpleMemoryCache = SimpleMemoryCache()
        self.reg_url = r"(?:(?:https?):\/\/)?[\w/\-?=%.]+\.[\w/\-&?=%.]+"

    def _extract_urls(self, content: str) -> set[str]:
        matches = re.finditer(self.reg_url, content, re.MULTILINE)
        removed_protocols = []
        for match in matches:
            if match is None:
                continue
            url_fragments = urlsplit(match.group().lower())
            hostname = f"{url_fragments.hostname}{url_fragments.path}"
            removed_protocols.append(hostname[4:] if hostname.startswith("None") else hostname)
        return set(removed_protocols)

    async def _check_cache(self, urls: set[str]) -> tuple[list[str], list[str]]:
        filtered_urls = []
        urls_to_fetch = []
        for url in urls:
            cached_result = await self.url_cache.get(url)
            if cached_result is True:
                filtered_urls.append(url)
            elif cached_result is None:
                urls_to_fetch.append(url)
        return filtered_urls, urls_to_fetch

    async def _fetch_and_cache(self, urls_to_fetch: list[str]) -> list[str] | None:
        api_result = await fetch_safebrowsing(urls_to_fetch, self.logger)
        if api_result is None:
            self.logger.warning(
                f"Failed to fetch Safe Browsing results for URLs: {urls_to_fetch} | API Result: {api_result}"
            )
            return None
        new_bad_urls = []
        if api_result.get("matches"):
            for match in api_result["matches"]:
                await self.url_cache.set(match["url"], True, ttl=3600)
                if match["url"] in urls_to_fetch:
                    urls_to_fetch.remove(match["url"])
                new_bad_urls.append(match["url"])
        for url in urls_to_fetch:
            await self.url_cache.set(url, False, ttl=3600)
        return new_bad_urls

    async def _filter_urls(self, urls: set[str]) -> list[str] | None:
        filtered_urls, urls_to_fetch = await self._check_cache(urls)
        if not urls_to_fetch:
            return filtered_urls

        new_bad = await self._fetch_and_cache(urls_to_fetch)
        if new_bad is None:
            return None
        filtered_urls.extend(new_bad)
        return filtered_urls

    @commands.Cog.listener("on_message")
    async def message_event(self, msg: discord.Message) -> None:
        if not self.client.user or msg.author.id == self.client.user.id or not msg.guild:
            return

        urls = self._extract_urls(msg.content)
        if not urls:
            return

        filtered_urls = await self._filter_urls(urls)
        if not filtered_urls:
            return

        await msg.delete(reason="Detected as bad url")
        link_bed = discord.Embed(
            title="Message context",
            description=f"{msg.content}\n\nYou were warned due to these links.\n"
            f"{'\n'.join(f'- `{url}`' for url in filtered_urls)}",
            color=discord.Color.green(),
        )
        link_bed.set_author(name=msg.author.display_name, icon_url=msg.author.display_avatar.url)
        link_bed.set_footer(text="If you believe this is a mistake, please contact a moderator.")

        self.client.dispatch(
            "moderation_action",
            InfractionsEnum.Warn,
            msg.author,
            msg.guild,
            "Bad URL sent",
            self.client.user,
            log_reason="Sending a malicious link",
            embed_title="Message delete",
            extra_embeds=[link_bed],
            dm_info_text="You were warned due to the message above.",
        )


def setup(client: Bot):
    if re.match(GOOGLE_API_KEY_REGEX, GOOGLE_API_KEY) is None:
        client.logger.error("No Google API key provided, skipping bad url detection")
        return
    client.add_cog(SafebrowsingCog(client))

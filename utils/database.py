import os
from pathlib import Path

import aiosqlite
import discord

from .enums import SettingsEnum


class ContentDB:
    def __init__(self, path: str | Path):
        self.db: aiosqlite.Connection = None
        if not type(path) == Path:
            path = Path(path)
        self.path: Path = path

    async def setup(self):
        """Create new tables in the database if they don't already exist'"""
        if not self.path.exists():
            self.path.parent.mkdir(exist_ok=True)
            self.path.touch()
        self.db = await aiosqlite.connect(self.path)
        async with self.db.cursor() as cursor:
            await cursor.execute("CREATE TABLE IF NOT EXISTS settings " "(setting TEXT, value INTEGER, guild INTEGER)")
            await cursor.execute(
                "CREATE TABLE IF NOT EXISTS join2create "
                "(channel INTEGER, owner INTEGER, locked INTEGER, ghosted INTEGER, guild INTEGER)"
            )

    async def _add_setting(self, setting: SettingsEnum, value: int, guild: discord.Guild) -> None:
        await self.db.execute(
            "INSERT INTO settings (setting, value, guild) VALUES (?,?,?)", (setting.value, value, guild.id)
        )
        await self.db.commit()

    async def get_setting(self, setting: SettingsEnum, guild: discord.Guild) -> int | None:
        """Returns the raw setting from database or None if not found"""
        async with self.db.cursor() as cursor:
            resp = await cursor.execute(
                "SELECT value FROM settings WHERE setting = ? AND guild = ?", (setting.value, guild.id)
            )
            data = await resp.fetchone()
        if data is None:
            return None
        return data[0]

    async def update_setting(self, setting: SettingsEnum, value: int, guild: discord.Guild) -> None:
        """Function requests current setting if not exists create it, else update it"""
        resp = await self.get_setting(setting, guild)
        if resp is None:
            await self._add_setting(setting=setting, value=value, guild=guild)
            return
        async with self.db.cursor() as cursor:
            await cursor.execute(
                "UPDATE settings SET value = ? WHERE setting = ? AND guild = ?", (value, setting.value, guild.id)
            )
            await self.db.commit()

    async def join2create(self, new_channel: discord.VoiceChannel, owner: discord.Member):
        await self.db.execute(
            "INSERT INTO join2create (channel, owner, locked, ghosted, guild) VALUES (?, ?, 0, 0, ?)",
            (new_channel.id, owner.id, new_channel.guild.id),
        )
        await self.db.commit()

    async def join2delete(self, channel: discord.VoiceChannel):
        await self.db.execute("DELETE FROM join2delete WHERE channel = ? AND guild = ?", (channel.id, channel.guild.id))

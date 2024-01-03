import aiosqlite
import discord

from .enums import SettingsEnum


class ContentDB:
    def __init__(self, path: str):
        self.db: aiosqlite.Connection = None
        self.path = path

    async def setup(self):
        self.db = await aiosqlite.connect(self.path)
        async with self.db.cursor() as cursor:
            await cursor.execute(
                "CREATE TABLE IF NOT EXISTS settings " "(setting INTEGER, value INTEGER, guild INTEGER)"
            )
            await cursor.execute(
                "CREATE TABLE IF NOT EXISTS join2create "
                "(channel INTEGER, owner INTEGER, locked INTEGER, ghosted INTEGER, guild INTEGER)"
            )

    async def _add_setting(self, setting: SettingsEnum, value: int, guild: discord.Guild) -> None:
        await self.db.execute(
            "INSERT INTO settings (setting, value, guild) VALUES (?,?,?)", (setting.value, value, guild.id)
        )

    async def get_setting(self, setting: SettingsEnum, guild: discord.Guild) -> int | None:
        async with self.db.cursor() as cursor:
            resp = await cursor.execute(
                "SELECT * FROM settings WHERE setting = ? AND guild = ?", (setting.value, guild.id)
            )
            data = await resp.fetchone()
        if data is None:
            return None
        return data[0]

    async def update_setting(self, setting: SettingsEnum, value: int, guild: discord.Guild) -> None:
        resp = await self.get_setting(setting, guild)
        if resp is None:
            await self._add_setting(setting=setting, value=value, guild=guild)
            return
        async with self.db.cursor() as cursor:
            await cursor.execute(
                "UPDATE settings SET value = ? WHERE setting = ? AND guild = ?", (setting.value, guild.id)
            )

    async def onjoin2create(self, new_channel: discord.VoiceChannel, owner: discord.Member):
        await self.db.execute(
            "INSERT INTO join2create " "(channel, owner, locked, ghosted, guild) " "VALUES " "(?, ?, 0, 0, ?)",
            (new_channel.id, owner.id, new_channel.guild.id),
        )

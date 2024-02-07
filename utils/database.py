from datetime import datetime
from pathlib import Path

import aiosqlite
import discord

from .enums import SettingsEnum
from .logger import CustomLogger


def datetime_to_db(val):
    """Adapt datetime.datetime to timezone-naive ISO 8601 date."""
    return val.isoformat()


def db_to_datetime(val):
    """Convert ISO 8601 datetime to datetime.datetime object."""
    return datetime.fromisoformat(val.decode())


aiosqlite.register_adapter(datetime, datetime_to_db)
aiosqlite.register_converter("DATETIME", db_to_datetime)


class ContentDB:
    def __init__(self, path: str | Path):
        self.db: aiosqlite.Connection = None  # type: ignore
        self.logger: CustomLogger = None  # type: ignore
        if not isinstance(path, Path):
            path = Path(path)
        self.path: Path = path

    async def setup(self, boot: datetime):
        """Create new tables in the database if they don't already exist"""
        self.logger = CustomLogger("database", boot)
        if not self.path.exists():
            self.path.parent.mkdir(exist_ok=True)
            self.path.touch()
            self.logger.info("Created database path/file")
        self.db = await aiosqlite.connect(self.path)
        async with self.db.cursor() as cursor:
            await cursor.execute("CREATE TABLE IF NOT EXISTS settings (setting TEXT, value INTEGER, guild INTEGER)")
            await cursor.execute(
                "CREATE TABLE IF NOT EXISTS join2create "
                "(channel INTEGER, owner INTEGER, locked INTEGER, ghosted INTEGER)"
            )
        self.logger.debug("Database set up!")

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
            self.logger.debug(f"{setting} for {guild} is {data}")
        if data is None:
            return None
        return data[0]

    async def get_global_setting(self, setting: SettingsEnum) -> list[(int, int)]:  # type: ignore
        """Returns the setting for every guild in the database"""
        async with self.db.cursor() as cursor:
            resp = await cursor.execute("SELECT value, guild FROM settings WHERE setting = ?", (setting.value,))
            data = await resp.fetchall()
        return data

    async def update_setting(self, setting: SettingsEnum, value: int, guild: discord.Guild) -> None:
        """Function requests current setting if not exists create it, else update it"""
        resp = await self.get_setting(setting, guild)
        if resp is None:
            await self._add_setting(setting=setting, value=value, guild=guild)
            self.logger.debug(f"{setting} was added with {value} at {guild}")
            return
        async with self.db.cursor() as cursor:
            await cursor.execute(
                "UPDATE settings SET value = ? WHERE setting = ? AND guild = ?", (value, setting.value, guild.id)
            )
            await self.db.commit()
            self.logger.debug(f"{setting} was updated with {value} at {guild}")

    async def join2create(self, new_channel: discord.VoiceChannel, owner: discord.Member):
        """saves the channel id, member id into the db, sets locked and ghost to 0"""
        await self.db.execute(
            "INSERT INTO join2create (channel, owner, locked, ghosted) VALUES (?, ?, 0, 0)",
            (new_channel.id, owner.id),
        )
        await self.db.commit()
        self.logger.debug(f"{new_channel.name} was created for {owner.name}")

    async def join2get(self, channel: discord.VoiceChannel) -> bool:
        """Returns `True` if the channel id is in the database"""
        resp: aiosqlite.Cursor = await self.db.execute("SELECT * FROM join2create WHERE channel = ?", (channel.id,))
        resp = await resp.fetchone()  # type: ignore
        self.logger.debug(f"join2get returned {resp}")  # ignored because first resp returns Cursor not Row
        if resp is not None:
            return True
        return False

    async def join2delete(self, channel: discord.VoiceChannel):
        """deletes the row using the channel id"""
        await self.db.execute("DELETE FROM join2create WHERE channel = ?", (channel.id,))
        await self.db.commit()
        self.logger.debug(f"Deleted {channel.name}|{channel.id} from the database")


class ShortTermStorage:
    def __init__(self, path: str | Path):
        self.db: aiosqlite.Connection = None  # type: ignore
        self.logger: CustomLogger = None  # type: ignore
        if not isinstance(path, Path):
            path = Path(path)
        self.path: Path = path

    async def setup(self, boot: datetime):
        """Create new tables in the database if they don't already exist"""
        self.logger = CustomLogger("shortstore", boot)
        if not self.path.exists():
            self.path.parent.mkdir(exist_ok=True)
            self.path.touch()
            self.logger.info("Created database path/file")
        self.db = await aiosqlite.connect(self.path, detect_types=1)
        async with self.db.cursor() as cursor:
            await cursor.execute("CREATE TABLE IF NOT EXISTS tagesschau (id TEXT, updated DATETIME, expires DATETIME)")
        self.logger.debug("Database set up!")

    # TODO Insert, Get, Delete functions

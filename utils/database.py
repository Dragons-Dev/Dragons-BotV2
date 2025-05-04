from datetime import datetime
from pathlib import Path

import aiosqlite
import discord
from discord.utils import warn_deprecated

from .enums import InfractionsEnum, SettingsEnum, StatTypeEnum
from .logger import CustomLogger


def datetime_to_db(val):
    """Adapt datetime.datetime to timezone-naive ISO 8601 date."""
    return val.isoformat()


def db_to_datetime(val):
    """Convert ISO 8601 datetime to datetime.datetime object."""
    return datetime.fromisoformat(val.decode())


aiosqlite.register_adapter(datetime, datetime_to_db)
aiosqlite.register_converter("DATETIME", db_to_datetime)

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
        self.logger.debug("ShortTermStorage set up!")

    async def close(self):
        await self.db.close()

    async def enter_tagesschau_id(self, uuid: str, updated: datetime, expires: datetime):
        async with self.db.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO tagesschau (id, updated, expires) VALUES (?, ?, ?)", (uuid, updated, expires)
            )
        await self.db.commit()

    async def get_tagesschau_id(self, uuid: str):
        """Returns ID, Updated and Expires"""
        async with self.db.cursor() as cursor:
            await cursor.execute("SELECT * FROM tagesschau WHERE id = ?", (uuid,))
            resp = await cursor.fetchone()
        if resp is None:
            return None
        else:
            return {"id": uuid, "updated": resp[1], "expires": resp[2]}

    async def get_tagesschau_rows(self):
        """Returns first 50 entries ordered by expires: ID, Updated and Expires"""
        response = []
        async with self.db.cursor() as cursor:
            await cursor.execute("SELECT * FROM tagesschau ORDER BY expires LIMIT 50")
            rows = await cursor.fetchall()
        if rows is None:
            return None
        else:
            for resp in rows:
                response.append({"id": resp[0], "updated": resp[1], "expires": resp[2]})
            return response

    async def delete_tagesschau_id(self, uuid: str):
        async with self.db.cursor() as cursor:
            await cursor.execute("DELETE FROM tagesschau WHERE id = ?", (uuid,))
        await self.db.commit()

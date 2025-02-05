from datetime import datetime
from pathlib import Path

import aiosqlite
import discord

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
            await cursor.execute(
                "CREATE TABLE IF NOT EXISTS infractions "
                "(case_id INTEGER PRIMARY KEY AUTOINCREMENT, user INTEGER, infraction TEXT, "
                "reason TEXT, date DATETIME, guild INTEGER)"
            )
            await cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS modmail_link
            (user_id INTEGER PRIMARY KEY, guild_id INTEGER, uuid TEXT, anon INTEGER)
            """
            )
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_stats
                (user_id INTEGER, stat_type TEXT, value INTEGER, guild_id INTEGER)
                """
            )
        self.logger.debug("ContentDB set up!")

    async def close(self):
        await self.db.close()

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

    async def delete_setting(self, setting: SettingsEnum, guild: discord.Guild) -> None:
        """Deletes the currently set setting for the guild"""
        async with self.db.cursor() as cursor:
            await cursor.execute("DELETE FROM settings WHERE setting = ? AND guild = ?", (setting.value, guild.id))

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
        if resp is not None:
            return True
        return False

    async def join2delete(self, channel: discord.VoiceChannel):
        """deletes the row using the channel id"""
        await self.db.execute("DELETE FROM join2create WHERE channel = ?", (channel.id,))
        await self.db.commit()
        self.logger.debug(f"Deleted {channel.name}|{channel.id} from the database")

    async def create_infraction(
        self, user: discord.User | discord.Member, infraction: InfractionsEnum, reason: str, guild: discord.Guild
    ):
        """Creates a new infraction entry for a user"""
        cursor: aiosqlite.Cursor = await self.db.execute(
            "INSERT INTO infractions (user, infraction, reason, date, guild) VALUES (?, ?, ?, ?, ?)",
            (user.id, infraction.value, reason, datetime.now(), guild.id),
        )
        await self.db.commit()
        self.logger.debug(f"Inserted {user.name}|{infraction.value}|{guild.name} to infractions.")
        return cursor.lastrowid

    async def modify_infraction(
        self,
        case_id: int,
        *,
        user: discord.User | discord.Member = None,
        infraction: InfractionsEnum = None,
        reason: str = None,
        guild: discord.Guild = None,
    ):
        """Modifies a new infraction entry for a user"""
        if user is not None:
            await self.db.execute("UPDATE infractions SET user = ? WHERE case_id = ?", (user.id, case_id))
        elif infraction is not None:
            await self.db.execute(
                "UPDATE infractions SET infraction = ? WHERE case_id = ?", (infraction.value, case_id)
            )
        elif reason is not None:
            await self.db.execute("UPDATE infractions SET reason = ? WHERE case_id = ?", (reason, case_id))
        elif guild is not None:
            await self.db.execute("UPDATE infractions SET guild = ? WHERE case_id = ?", (guild.id, case_id))
        else:
            pass
        await self.db.commit()

    async def get_infraction(
            self, case_id: int | None = None, user: discord.User | discord.Member | None = None
    ) -> aiosqlite.Row | list[aiosqlite.Row]:
        """Gets an infraction by id or all infractions from a user"""
        if case_id is not None:
            resp = await self.db.execute("SELECT * FROM infractions WHERE case_id = ?", (case_id,))
            resp = await resp.fetchone()
        else:
            resp = await self.db.execute("SELECT * FROM infractions WHERE user = ?", (user.id,))  # type: ignore
            resp = await resp.fetchall()
        return resp

    async def delete_infraction(self, case_id: int):
        """Gets an infraction by id"""
        await self.db.execute("DELETE FROM infractions WHERE case_id = ?", (case_id,))
        await self.db.commit()

    async def add_modmail_link(self, author: discord.User, guild: discord.Guild, uuid: str, anon: bool):
        await self.db.execute(
            "INSERT INTO modmail_link (user_id, guild_id, uuid, anon) VALUES (?, ?, ?, ?)",
            (author.id, guild.id, uuid, int(anon)),
        )
        await self.db.commit()

    async def get_modmail_link(self, author: discord.User | None = None, uuid: str | None = None):
        if author:
            resp = await self.db.execute("SELECT * FROM modmail_link WHERE user_id = ?", (author.id,))
        elif uuid:
            resp = await self.db.execute("SELECT * FROM modmail_link WHERE uuid = ?", (uuid,))
        else:
            self.logger.critical("No author or uuid specified!")
            raise LookupError("No author or uuid specified!")
        resp = await resp.fetchone()
        if resp is None:
            return None, None, None, None
        return resp[0], resp[1], resp[2], bool(resp[3])

    async def remove_modmail_link(self, author: discord.User):
        await self.db.execute("DELETE FROM modmail_link WHERE user_id = ?", (author.id,))
        await self.db.commit()

    async def _add_user_stat(self, user: discord.Member, stat_type: StatTypeEnum, value: int, guild: discord.Guild):
        await self.db.execute(
            "INSERT INTO user_stats (user_id, stat_type, value, guild_id) VALUES (?, ?, ?, ?)",
            (user.id, stat_type.value, value, guild.id),
        )
        await self.db.commit()

    async def update_user_stat(self, user: discord.Member, stat_type: StatTypeEnum, value: int, guild: discord.Guild):
        """
        Updates a user stat by the value that you input. The value can either be positive or negative.
        Args:
            user: ``discord.Member``
            stat_type: ``utils.StatTypeEnum``
            value: ``int``
            guild: ``discord.Guild``

        Returns:
            ``None``
        """
        before_val = await self.get_user_stat(user, stat_type, guild)
        if before_val is None:
            await self._add_user_stat(user, stat_type, value, guild)
            return
        else:
            after_val = sum([before_val[0][2], value])
        cursor: aiosqlite.Cursor = await self.db.execute(
            "UPDATE user_stats SET value = ? WHERE user_id = ? AND guild_id = ? AND stat_type = ?",
            (after_val, user.id, guild.id, stat_type.value),
        )
        await self.db.commit()

    async def get_user_stat(
            self, user: discord.User | discord.Member | None, stat_type: StatTypeEnum, guild: discord.Guild | None
    ):
        """
        Gets the requested stat from the database
        Args:
            user: ``discord.Member`` or ``discord.User`` or ``None``
            stat_type: ``utils.StatTypeEnum``
            guild: ``discord.Guild``

        Returns:
            ``None`` if no entry is there else ``list[tuple[int,str,int,int]`` inside the tuple it's ordered as ``user_id``, ``stat_type``, ``value``, ``guild_id``
        """
        if user and guild:
            resp = await self.db.execute(
                "SELECT * FROM user_stats WHERE user_id = ? AND stat_type = ? AND guild_id = ?",
                (user.id, stat_type.value, guild.id),
            )
        elif user:
            resp = await self.db.execute(
                "SELECT * FROM user_stats WHERE user_id = ? AND stat_type = ?", (user.id, stat_type.value)
            )
        elif guild:
            resp = await self.db.execute(
                "SELECT * FROM user_stats WHERE guild_id = ? AND stat_type = ?", (guild.id, stat_type.value)
            )
        else:
            self.logger.critical("Neither User nor Guild specified!")
            raise LookupError("Neither User nor Guild specified!")
        resp = await resp.fetchall()
        if len(resp) == 0:
            return None
        return resp

    async def delete_user_stat(self, user: discord.User | None, guild: discord.Guild | None):
        """
        Deletes all stats it finds filtered by either user and guild, only user or only guild.
        Args:
            user: ``discord.User`` or ``None``
            guild: ``discord.Guild`` or ``None``

        Returns:
            ``None``
        """
        if user and guild:
            await self.db.execute("DELETE FROM user_stats WHERE user_id = ? AND guild_id = ?", (user.id, guild.id))
        elif user:
            await self.db.execute("DELETE FROM user_stats WHERE user_id = ?", (user.id,))
        elif guild:
            await self.db.execute("DELETE FROM user_stats WHERE guild_id = ?", (guild.id,))
        else:
            self.logger.critical("Neither User nor Guild specified!")
            raise LookupError("Neither User nor Guild specified!")


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

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from utils.utils import VersionInfo

TARGET_VERSION = VersionInfo(3, 2, 0, "")


async def migrate(conn: AsyncConnection) -> None:
    """
    Safely adds thread_id column to existing modmail table if present,
    or creates the modmail table with the updated schema.
    """
    try:
        await conn.execute(text("ALTER TABLE modmail ADD COLUMN thread_id BIGINT NULL"))
    except (OperationalError, DBAPIError):
        # Column already exists, or table doesn't exist yet
        pass

    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS modmail (
                uuid VARCHAR NOT NULL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                thread_id BIGINT NULL,
                anon BOOLEAN NOT NULL DEFAULT 0
            )
            """
        )
    )

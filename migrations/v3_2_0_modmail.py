from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from utils.utils import VersionInfo

TARGET_VERSION = VersionInfo(3, 2, 0, "")


async def migrate(conn: AsyncConnection) -> None:
    """
    Drops the legacy modmail table so ORMDataBase.setup recreates it
    with the updated schema (thread_id).
    """
    await conn.execute(text("DROP TABLE IF EXISTS modmail"))

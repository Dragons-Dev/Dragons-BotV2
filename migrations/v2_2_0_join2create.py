from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from utils.utils import VersionInfo

TARGET_VERSION = VersionInfo(2, 2, 0, "")


async def migrate(conn: AsyncConnection) -> None:
    """
    Drops the legacy join2create table so ORMDataBase.setup recreates it
    with the updated schema (channel, owner_id, derived_channel).
    """
    await conn.execute(text("DROP TABLE IF EXISTS join2create"))

from collections.abc import Sequence

import discord
from sqlalchemy import select

from utils.orm_database.repository import BaseRepository

from .models import BotStatus

__all__ = ["BotStatusRepository"]


class BotStatusRepository(BaseRepository):
    """Repository for BotStatus operations."""

    async def create_bot_status(
        self, activity_type: discord.ActivityType, status: discord.Status, activity_name: str
    ) -> None:
        async with self.session() as session:
            session.add(
                BotStatus(activity_type=int(activity_type), status=str(status), activity_name=activity_name)
            )

    async def edit_bot_status(
        self,
        id_: int,
        activity_type: discord.ActivityType | None = None,
        status: discord.Status | None = None,
        activity_name: str | None = None,
    ) -> None:
        async with self.session() as session:
            query = select(BotStatus).where(BotStatus.id == id_)
            result = (await session.execute(query)).scalar_one_or_none()
            if result is None:
                return None
            if activity_type is not None:
                result.activity_type = int(activity_type)
            if status is not None:
                result.status = str(status)
            if activity_name is not None:
                result.activity_name = activity_name

    async def get_bot_status(self, id_: int | None) -> BotStatus | Sequence[BotStatus] | None:
        """
        Gets the bot status from the database.
        Args:
            id_:

        Returns:
            A BotStatus object, a list of it or None. The BotStatus object uses py-cords enums for activity_type and
            status. You will have to convert them to the correct type, to use them effectively.
        """
        async with self.session() as session:
            if id_:
                query = select(BotStatus).where(BotStatus.id == id_)
            else:
                query = select(BotStatus)
            bot_status = (await session.execute(query)).scalars().all()
        if len(bot_status) == 0:
            return None
        if len(bot_status) == 1:
            return bot_status[0]
        return bot_status

    async def delete_bot_status(self, id_: int) -> None:
        async with self.session() as session:
            query = select(BotStatus).where(BotStatus.id == id_)
            result = (await session.execute(query)).scalar_one_or_none()
            if result is None:
                return
            await session.delete(result)

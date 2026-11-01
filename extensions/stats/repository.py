from collections.abc import Sequence
from datetime import date, timedelta

import discord
from sqlalchemy import and_, func, select

from utils.enums import StatTypeEnum
from utils.orm_database.repository import BaseRepository

from .models import UserStats

__all__ = ["UserStatsRepository"]


class UserStatsRepository(BaseRepository):
    """Repository for user statistics operations."""

    async def update_user_stat(
        self, user: discord.User | discord.Member, stat_type: StatTypeEnum, value: int, guild: discord.Guild
    ) -> None:
        """
        Upsert a stat for the user. Automatically creates a new date if necessary.
        :param user: the user to upsert the stat for
        :param stat_type: the Stat type to update
        :param value: the value to update
        :param guild: the guild associated with the stat
        :return: ``None``
        """
        today = date.today()
        async with self.session() as session:
            query = select(UserStats).where(
                and_(
                    UserStats.user_id == user.id,
                    UserStats.stat_type == stat_type.value,
                    UserStats.guild_id == guild.id,
                    UserStats.day == today,
                )
            )
            result: UserStats | None = (await session.execute(query)).scalar_one_or_none()
            if result is None:
                new_stat = UserStats(
                    user_id=user.id,
                    stat_type=stat_type.value,
                    value=value,
                    guild_id=guild.id,
                    day=today,
                )
                session.add(new_stat)
            else:
                result.value += value

    async def get_user_stat_days(
        self, user: discord.User | discord.Member, stat_type: StatTypeEnum, guild: discord.Guild, days_back: int
    ) -> Sequence[UserStats]:
        """
        Returns the stats for the specified date range
        :param user: the User to retrieve the stats for
        :param stat_type: the type of stat to return
        :param guild: the specific guild to retrieve the stats for
        :param days_back: ``int`` the date range to retrieve stats for
        :return: ``Sequence[UserStats]`` an iterable with ``UserStats`` objects
        """
        start_date = date.today() - timedelta(days=days_back)
        async with self.session() as session:
            query = (
                select(UserStats)
                .where(
                    and_(
                        UserStats.user_id == user.id,
                        UserStats.stat_type == stat_type.value,
                        UserStats.guild_id == guild.id,
                        UserStats.day >= start_date,
                    )
                )
                .order_by(UserStats.day.desc())
            )
            result = (await session.execute(query)).scalars().all()
            return result

    async def get_user_stat_total(
        self, user: discord.User | discord.Member, stat_type: StatTypeEnum, guild: discord.Guild
    ) -> int:
        """
        Returns an int consisting of all values this user has for the stat.
        :param user: the User to retrieve the stats for
        :param stat_type: the type of stat to return
        :param guild: the specific guild to retrieve the stats for
        :return: ``int`` sum of the values
        """
        async with self.session() as session:
            query = select(func.sum(UserStats.value)).where(
                and_(
                    UserStats.user_id == user.id, UserStats.stat_type == stat_type.value, UserStats.guild_id == guild.id
                )
            )
            result = (await session.execute(query)).scalar_one_or_none()
            return result or 0

    async def delete_user_stats(
        self, user: discord.User | discord.Member | None, stat_type: StatTypeEnum, guild: discord.Guild | None
    ) -> None:
        """
        Deletes all stats of a user for a specific stat type and guild.
        :param user: the User to delete the stats for
        :param stat_type: the type of stat to delete
        :param guild: the specific guild to delete the stats for
        :return: ``None``
        """
        async with self.session() as session:
            if user and guild:
                query = select(UserStats).where(
                    and_(
                        UserStats.user_id == user.id,
                        UserStats.stat_type == stat_type.value,
                        UserStats.guild_id == guild.id,
                    )
                )
            elif user and not guild:
                query = select(UserStats).where(
                    and_(
                        UserStats.user_id == user.id,
                        UserStats.stat_type == stat_type.value,
                    )
                )
            elif not user and guild:
                query = select(UserStats).where(
                    and_(UserStats.stat_type == stat_type.value, UserStats.guild_id == guild.id)
                )
            else:
                return
            result = (await session.execute(query)).scalars().all()
            for stat in result:
                await session.delete(stat)

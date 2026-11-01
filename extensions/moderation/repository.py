from collections.abc import Sequence
from datetime import datetime

import discord
from sqlalchemy import select

from utils.enums import InfractionsEnum
from utils.orm_database.repository import BaseRepository

from .models import Infractions, Modmail

__all__ = ["InfractionsRepository", "ModmailRepository"]


class InfractionsRepository(BaseRepository):
    """Repository for moderation infraction operations."""

    async def create_infraction(
        self, user: discord.User | discord.Member, infraction: InfractionsEnum, reason: str, guild: discord.Guild
    ) -> int:
        """
        Creates a new infraction record in the database.

        Args:
            user (discord.User | discord.Member): The user who received the infraction.
            infraction (InfractionsEnum): The type of infraction.
            reason (str): The reason for the infraction.
            guild (discord.Guild): The guild where the infraction occurred.

        Returns:
            int: The case ID of the created infraction.
        """
        async with self.session() as session:
            record = Infractions(
                user_id=user.id, infraction=infraction.value, reason=reason, date=datetime.now(), guild=guild.id
            )
            session.add(record)
            await session.flush()
            return record.case_id

    async def get_infraction(
        self, case_id: int | None, user: discord.Member | discord.User | None, guild: discord.Guild | None = None
    ) -> None | Infractions | Sequence[Infractions]:
        """
        Retrieves infraction(s) from the database based on case ID or user.

        Args:
            case_id (int | None): The case ID of the infraction to retrieve. If None, retrieves by user.
            user (discord.Member | discord.User | None): The user whose infractions to retrieve. Used if case_id is None.
            guild (discord.Guild | None): The guild associated with the infraction. Filters infractions to this guild when provided.

        Returns:
            None | Infractions | Sequence[Infractions]: Returns None if no infractions are found,
            a single Infractions object if one is found, or a sequence of Infractions if multiple are found.

        Raises:
            LookupError: If both case_id and user are None.
        """
        async with self.session() as session:
            if case_id:
                query = select(Infractions).where(Infractions.case_id == case_id)
            elif user:
                query = select(Infractions).where(Infractions.user_id == user.id)
            else:
                raise LookupError("Both arguments are 'None'. At least one must have a value!")
            if guild is not None:
                query = query.where(Infractions.guild == guild.id)
            infractions = (await session.execute(query)).scalars().all()
        if len(infractions) == 0:
            return None
        if len(infractions) == 1:
            return infractions[0]
        return infractions


class ModmailRepository(BaseRepository):
    """Repository for modmail operations."""

    async def create_modmail(
        self, user: discord.User | discord.Member, guild: discord.Guild, uuid: str, anonymous: bool
    ) -> None:
        async with self.session() as session:
            session.add(
                Modmail(
                    user_id=user.id,
                    guild_id=guild.id,
                    uuid=uuid,
                    anon=anonymous,
                )
            )

    async def get_modmail(self, user: discord.User | discord.Member | None, uuid: str | None) -> None | Modmail:
        async with self.session() as session:
            if user:
                query = select(Modmail).where(Modmail.user_id == user.id)
            elif uuid:
                query = select(Modmail).where(Modmail.uuid == uuid)
            else:
                raise LookupError("Both arguments are 'None'. At least one must have a value!")
            modmail = (await session.execute(query)).scalar_one_or_none()
        return modmail

    async def delete_modmail(self, user: discord.User | discord.Member) -> None:
        async with self.session() as session:
            query = select(Modmail).where(Modmail.user_id == user.id)
            result = (await session.execute(query)).scalar()
            if result is None:
                return
            await session.delete(result)

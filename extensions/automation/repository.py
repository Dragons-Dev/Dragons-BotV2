import discord
from sqlalchemy import select

from utils.orm_database.repository import BaseRepository

from .models import Join2Create

__all__ = ["Join2CreateRepository"]


class Join2CreateRepository(BaseRepository):
    """Repository for Join2Create temporary voice channel operations."""

    async def create(
        self, channel: discord.VoiceChannel, owner: discord.Member, derived_channel: discord.VoiceChannel
    ) -> Join2Create | None:
        async with self.session() as session:
            new_entry = Join2Create(channel=channel.id, owner_id=owner.id, derived_channel=derived_channel.id)
            session.add(new_entry)
            await session.flush()
            return new_entry

    async def update(self, channel: discord.VoiceChannel, owner: discord.Member) -> None:
        async with self.session() as session:
            query = select(Join2Create).where(Join2Create.channel == channel.id)
            _channel = (await session.execute(query)).scalar_one_or_none()
            if _channel is not None:
                _channel.owner_id = owner.id

    async def get(self, channel: discord.VoiceChannel) -> Join2Create | None:
        async with self.session() as session:
            query = select(Join2Create).where(Join2Create.channel == channel.id)
            temp_channel = (await session.execute(query)).scalar_one_or_none()
        return temp_channel

    async def delete(self, channel: discord.VoiceChannel) -> None:
        async with self.session() as session:
            query = select(Join2Create).where(Join2Create.channel == channel.id)
            temp_channel = (await session.execute(query)).scalar_one_or_none()
            if temp_channel is not None:
                await session.delete(temp_channel)

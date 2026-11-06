from collections.abc import Sequence
from datetime import datetime

import discord
from sqlalchemy import delete, select

from utils.enums import InfractionsEnum
from utils.orm_database.repository import BaseRepository

from .models import ArchivedTranscript, CachedAttachment, Infractions, Modmail

__all__ = ["ChannelExporterRepository", "InfractionsRepository", "ModmailRepository"]


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


class ChannelExporterRepository(BaseRepository):
    """Repository for channel exporter cached attachments and archived transcripts."""

    async def save_attachment(
        self,
        channel_id: int,
        message_id: int,
        attachment_id: int,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> CachedAttachment:
        """
        Saves a cached attachment in the database.

        Args:
            channel_id (int): The ID of the channel where the attachment was sent.
            message_id (int): The ID of the message containing the attachment.
            attachment_id (int): The Discord attachment ID.
            filename (str): The filename of the attachment.
            content_type (str): The MIME content type.
            data (bytes): The raw binary content of the attachment.

        Returns:
            CachedAttachment: The saved cached attachment model instance.
        """
        async with self.session() as session:
            record = CachedAttachment(
                channel_id=channel_id,
                message_id=message_id,
                attachment_id=attachment_id,
                filename=filename,
                content_type=content_type,
                data=data,
            )
            session.add(record)
            await session.flush()
            return record

    async def get_channel_attachments(self, channel_id: int) -> Sequence[CachedAttachment]:
        """
        Retrieves all cached attachments for a specific channel.

        Args:
            channel_id (int): The channel ID.

        Returns:
            Sequence[CachedAttachment]: All cached attachments belonging to the channel.
        """
        async with self.session() as session:
            query = select(CachedAttachment).where(CachedAttachment.channel_id == channel_id)
            return (await session.execute(query)).scalars().all()

    async def delete_channel_attachments(self, channel_id: int) -> None:
        """
        Deletes all cached attachments for a specific channel.

        Args:
            channel_id (int): The channel ID.
        """
        async with self.session() as session:
            query = delete(CachedAttachment).where(CachedAttachment.channel_id == channel_id)
            await session.execute(query)

    async def save_transcript(
        self,
        guild_id: int,
        channel_id: int,
        channel_name: str,
        exported_by: int,
        html_content: str,
    ) -> int:
        """
        Saves an exported HTML transcript to the database.

        Args:
            guild_id (int): The guild ID.
            channel_id (int): The channel ID that was exported.
            channel_name (str): The name of the channel.
            exported_by (int): The user ID who exported the transcript.
            html_content (str): The exported HTML content.

        Returns:
            int: The ID of the archived transcript.
        """
        async with self.session() as session:
            transcript = ArchivedTranscript(
                guild_id=guild_id,
                channel_id=channel_id,
                channel_name=channel_name,
                exported_by=exported_by,
                html_content=html_content,
                created_at=datetime.now(),
            )
            session.add(transcript)
            await session.flush()
            return transcript.id

    async def get_transcript(self, transcript_id: int, guild_id: int | None = None) -> ArchivedTranscript | None:
        """
        Retrieves an archived transcript by its ID, optionally scoped to a guild.

        Args:
            transcript_id (int): The transcript ID.
            guild_id (int | None): The guild ID to filter by, if provided.

        Returns:
            ArchivedTranscript | None: The transcript if found, else None.
        """
        async with self.session() as session:
            query = select(ArchivedTranscript).where(ArchivedTranscript.id == transcript_id)
            if guild_id is not None:
                query = query.where(ArchivedTranscript.guild_id == guild_id)
            return (await session.execute(query)).scalar_one_or_none()

    async def list_transcripts(self, guild_id: int, limit: int = 10) -> Sequence[ArchivedTranscript]:
        """
        Lists recent archived transcripts for a specific guild.

        Args:
            guild_id (int): The guild ID.
            limit (int): Maximum number of transcripts to return (defaults to 10).

        Returns:
            Sequence[ArchivedTranscript]: The archived transcripts.
        """
        async with self.session() as session:
            query = (
                select(ArchivedTranscript)
                .where(ArchivedTranscript.guild_id == guild_id)
                .order_by(ArchivedTranscript.created_at.desc(), ArchivedTranscript.id.desc())
                .limit(limit)
            )
            return (await session.execute(query)).scalars().all()

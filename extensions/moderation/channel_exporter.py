import base64
from collections.abc import Sequence
from datetime import datetime
import io

import chat_exporter
import discord
import pycord.multicog as pycog
from discord.ext import commands

from utils import Bot, CustomLogger, is_team
from utils.enums import SettingsEnum

from .models import CachedAttachment
from .repository import ChannelExporterRepository

__all__ = ["ChannelExporter", "DatabaseAttachmentHandler", "export_and_archive_channel", "setup"]

MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB


class DatabaseAttachmentHandler(chat_exporter.AttachmentHandler):
    """Replaces Discord attachment URLs with base64 data URIs from cached attachments in the database."""

    def __init__(
        self,
        cached_attachments: Sequence[CachedAttachment] | dict[int, CachedAttachment],
    ) -> None:
        if isinstance(cached_attachments, dict):
            attachments_list = list(cached_attachments.values())
            self.cached_by_id: dict[int, CachedAttachment] = cached_attachments
        else:
            attachments_list = list(cached_attachments)
            self.cached_by_id = {att.attachment_id: att for att in cached_attachments}

        filename_counts: dict[str, int] = {}
        filename_map: dict[str, CachedAttachment] = {}
        for att in attachments_list:
            filename_counts[att.filename] = filename_counts.get(att.filename, 0) + 1
            filename_map[att.filename] = att
        self.cached_by_name: dict[str, CachedAttachment] = {
            name: att for name, att in filename_map.items() if filename_counts[name] == 1
        }

    async def process_asset(self, attachment: discord.Attachment) -> discord.Attachment:
        cached = self.cached_by_id.get(attachment.id) or self.cached_by_name.get(attachment.filename)
        if cached is not None:
            b64_str = base64.b64encode(cached.data).decode("ascii")
            data_uri = f"data:{cached.content_type};base64,{b64_str}"
            attachment.url = data_uri
            attachment.proxy_url = data_uri
        return attachment


async def export_and_archive_channel(
    bot: Bot,
    channel: discord.TextChannel | discord.Thread,
    guild: discord.Guild,
    exported_by_id: int,
    exporter_repo: ChannelExporterRepository | None = None,
) -> tuple[str | None, int | None]:
    """
    Exports a channel to HTML transcript, embeds cached attachments as base64 data URIs,
    archives the HTML transcript in the database, and deletes cached attachments.

    Returns:
        tuple[str | None, int | None]: (transcript_html, archive_id) or (None, None) if transcript is empty.
    """
    if exporter_repo is None:
        exporter_repo = ChannelExporterRepository(bot.db.session_maker)

    cached_attachments = await exporter_repo.get_channel_attachments(channel.id)
    cached_map = {att.attachment_id: att for att in cached_attachments}
    handler = DatabaseAttachmentHandler(cached_map)

    transcript_html = await chat_exporter.export(
        channel=channel,
        guild=guild,
        military_time=True,
        fancy_times=True,
        bot=bot,
        support_dev=False,
        attachment_handler=handler,
    )

    if not transcript_html or transcript_html.lstrip().startswith("Whoops! Something went wrong"):
        return None, None

    channel_name = getattr(channel, "name", f"channel-{channel.id}")
    archive_id = await exporter_repo.save_transcript(
        guild_id=guild.id,
        channel_id=channel.id,
        channel_name=channel_name,
        exported_by=exported_by_id,
        html_content=transcript_html,
    )
    await exporter_repo.delete_channel_attachments(channel.id)
    return transcript_html, archive_id


class ChannelExporter(commands.Cog):
    def __init__(self, client: Bot, exporter_repo: ChannelExporterRepository | None = None) -> None:
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.exporter_repo = exporter_repo or ChannelExporterRepository(self.client.db.session_maker)

    async def export_and_archive_channel(
        self,
        channel: discord.TextChannel | discord.Thread,
        guild: discord.Guild,
        exported_by_id: int,
    ) -> tuple[str | None, int | None]:
        return await export_and_archive_channel(
            bot=self.client,
            channel=channel,
            guild=guild,
            exported_by_id=exported_by_id,
            exporter_repo=self.exporter_repo,
        )

    async def _is_exportable_modmail_thread(self, msg: discord.Message) -> bool:
        if not msg.guild or not hasattr(self.client, "db") or not self.client.db:
            return False

        channel = msg.channel
        is_thread = (
            isinstance(channel, discord.Thread)
            or getattr(channel, "type", None)
            in (
                discord.ChannelType.public_thread,
                discord.ChannelType.private_thread,
                discord.ChannelType.news_thread,
            )
            or getattr(channel, "parent_id", None) is not None
        )
        if not is_thread:
            return False

        setting = await self.client.db.get_setting(SettingsEnum.ModmailChannel, msg.guild)
        if setting is None:
            return False

        modmail_channel_id = int(setting.value)
        parent_id = getattr(channel, "parent_id", None)
        if parent_id is None and getattr(channel, "parent", None) is not None:
            parent_id = channel.parent.id

        if parent_id == modmail_channel_id:
            return True

        if getattr(channel, "name", "").startswith("Thread for") and (
            parent_id is None or parent_id == modmail_channel_id
        ):
            return True

        return False

    async def _cache_single_attachment(self, msg: discord.Message, attachment: discord.Attachment) -> None:
        if attachment.size is not None and attachment.size >= MAX_ATTACHMENT_SIZE:
            return

        try:
            data = await attachment.read()
        except Exception as exc:
            self.logger.warning(f"Failed to read attachment {attachment.id}: {exc}")
            return

        content_type = getattr(attachment, "content_type", None) or "application/octet-stream"
        await self.exporter_repo.save_attachment(
            channel_id=msg.channel.id,
            message_id=msg.id,
            attachment_id=attachment.id,
            filename=attachment.filename,
            content_type=content_type,
            data=data,
        )

    @commands.Cog.listener("on_message")
    async def on_message(self, msg: discord.Message) -> None:
        if not getattr(msg, "attachments", None):
            return
        if not await self._is_exportable_modmail_thread(msg):
            return

        for attachment in msg.attachments:
            await self._cache_single_attachment(msg, attachment)

    @pycog.subcommand("mod")
    @is_team()
    @discord.guild_only()
    @commands.slash_command(name="export", description="Exports a channel to a single html file to archive it.")
    async def export(self, ctx: discord.ApplicationContext) -> None:
        if ctx.guild is None:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)
            return

        await ctx.response.defer(ephemeral=True, invisible=False)
        transcript_html, _ = await self.export_and_archive_channel(
            channel=ctx.channel,
            guild=ctx.guild,
            exported_by_id=ctx.author.id,
        )

        if transcript_html is None:
            await ctx.followup.send("Could not export channel. The channel may be empty.", ephemeral=True)
            return

        channel_name = getattr(ctx.channel, "name", f"channel-{ctx.channel.id}")
        author_name = getattr(ctx.author, "name", "unknown")
        filename = f"{datetime.now().strftime('%Y-%m-%d')}-{channel_name}-{author_name}.html"
        temp = io.StringIO(transcript_html)
        file = discord.File(fp=temp, filename=filename)
        await ctx.followup.send(f"{channel_name} export", file=file)


def setup(client: Bot) -> None:
    client.add_cog(ChannelExporter(client))

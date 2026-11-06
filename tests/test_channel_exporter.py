import base64
from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import chat_exporter
import discord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from extensions.moderation.channel_exporter import (
    ChannelExporter,
    DatabaseAttachmentHandler,
    export_and_archive_channel,
    setup,
)
from extensions.moderation.models import CachedAttachment
from extensions.moderation.repository import ChannelExporterRepository
from utils.orm_database import Base, ORMDataBase


class TestChannelExporterRepository(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(self.engine, expire_on_commit=False)
        ORMDataBase._discover_models(SimpleNamespace(logger=None))  # type: ignore[arg-type]
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.repo = ChannelExporterRepository(self.session_maker)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_save_and_get_attachments(self):
        saved = await self.repo.save_attachment(
            channel_id=100,
            message_id=200,
            attachment_id=300,
            filename="image.png",
            content_type="image/png",
            data=b"test-bytes",
        )
        self.assertIsNotNone(saved.id)
        self.assertEqual(saved.channel_id, 100)
        self.assertEqual(saved.message_id, 200)
        self.assertEqual(saved.attachment_id, 300)
        self.assertEqual(saved.filename, "image.png")
        self.assertEqual(saved.content_type, "image/png")
        self.assertEqual(saved.data, b"test-bytes")

        # Save for another channel
        await self.repo.save_attachment(
            channel_id=101,
            message_id=201,
            attachment_id=301,
            filename="other.jpg",
            content_type="image/jpeg",
            data=b"other-bytes",
        )

        attachments = await self.repo.get_channel_attachments(100)
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].attachment_id, 300)

    async def test_delete_channel_attachments(self):
        await self.repo.save_attachment(
            channel_id=100,
            message_id=200,
            attachment_id=300,
            filename="image.png",
            content_type="image/png",
            data=b"test-bytes",
        )
        await self.repo.save_attachment(
            channel_id=101,
            message_id=201,
            attachment_id=301,
            filename="other.jpg",
            content_type="image/jpeg",
            data=b"other-bytes",
        )

        await self.repo.delete_channel_attachments(100)
        self.assertEqual(len(await self.repo.get_channel_attachments(100)), 0)
        self.assertEqual(len(await self.repo.get_channel_attachments(101)), 1)

    async def test_transcript_lifecycle(self):
        archive_id = await self.repo.save_transcript(
            guild_id=500,
            channel_id=100,
            channel_name="modmail-user",
            exported_by=900,
            html_content="<html>Transcript</html>",
        )
        self.assertIsInstance(archive_id, int)

        # Retrieve by id
        transcript = await self.repo.get_transcript(archive_id)
        self.assertIsNotNone(transcript)
        assert transcript is not None
        self.assertEqual(transcript.channel_name, "modmail-user")
        self.assertEqual(transcript.exported_by, 900)
        self.assertEqual(transcript.html_content, "<html>Transcript</html>")

        # Filter by matching guild_id
        self.assertIsNotNone(await self.repo.get_transcript(archive_id, guild_id=500))
        # Filter by non-matching guild_id
        self.assertIsNone(await self.repo.get_transcript(archive_id, guild_id=999))
        # Unknown id
        self.assertIsNone(await self.repo.get_transcript(99999))

        # Test listing transcripts
        await self.repo.save_transcript(
            guild_id=500,
            channel_id=101,
            channel_name="modmail-user-2",
            exported_by=901,
            html_content="<html>Transcript 2</html>",
        )
        await self.repo.save_transcript(
            guild_id=501,
            channel_id=102,
            channel_name="different-guild",
            exported_by=902,
            html_content="<html>Transcript 3</html>",
        )

        listed = await self.repo.list_transcripts(500, limit=10)
        self.assertEqual(len(listed), 2)
        self.assertEqual(listed[0].channel_name, "modmail-user-2")
        self.assertEqual(listed[1].channel_name, "modmail-user")

        limited = await self.repo.list_transcripts(500, limit=1)
        self.assertEqual(len(limited), 1)
        self.assertEqual(limited[0].channel_name, "modmail-user-2")


class TestDatabaseAttachmentHandler(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sample_bytes = b"sample_png_bytes"
        self.b64_expected = base64.b64encode(self.sample_bytes).decode("ascii")
        self.cached_item = CachedAttachment(
            id=1,
            channel_id=100,
            message_id=200,
            attachment_id=3001,
            filename="photo.png",
            content_type="image/png",
            data=self.sample_bytes,
        )

    async def test_process_asset_by_id(self):
        handler = DatabaseAttachmentHandler([self.cached_item])
        self.assertIsInstance(handler, chat_exporter.AttachmentHandler)

        mock_attachment = MagicMock(spec=discord.Attachment)
        mock_attachment.id = 3001
        mock_attachment.filename = "different_name.png"
        mock_attachment.url = "https://cdn.discordapp.com/old_url.png"
        mock_attachment.proxy_url = "https://media.discordapp.net/old_proxy.png"

        result = await handler.process_asset(mock_attachment)
        expected_data_uri = f"data:image/png;base64,{self.b64_expected}"
        self.assertEqual(result.url, expected_data_uri)
        self.assertEqual(result.proxy_url, expected_data_uri)

    async def test_process_asset_by_filename_fallback(self):
        handler = DatabaseAttachmentHandler({self.cached_item.attachment_id: self.cached_item})

        mock_attachment = MagicMock(spec=discord.Attachment)
        mock_attachment.id = 9999  # Different ID
        mock_attachment.filename = "photo.png"  # Matching filename
        mock_attachment.url = "https://cdn.discordapp.com/old_url.png"
        mock_attachment.proxy_url = "https://media.discordapp.net/old_proxy.png"

        result = await handler.process_asset(mock_attachment)
        expected_data_uri = f"data:image/png;base64,{self.b64_expected}"
        self.assertEqual(result.url, expected_data_uri)
        self.assertEqual(result.proxy_url, expected_data_uri)

    async def test_process_asset_ambiguous_filename_not_used(self):
        item2 = CachedAttachment(
            id=2,
            channel_id=100,
            message_id=201,
            attachment_id=3002,
            filename="photo.png",
            content_type="image/png",
            data=b"other_bytes",
        )
        handler = DatabaseAttachmentHandler([self.cached_item, item2])

        mock_attachment = MagicMock(spec=discord.Attachment)
        mock_attachment.id = 9999
        mock_attachment.filename = "photo.png"
        mock_attachment.url = "https://cdn.discordapp.com/old_url.png"
        mock_attachment.proxy_url = "https://media.discordapp.net/old_proxy.png"

        result = await handler.process_asset(mock_attachment)
        self.assertEqual(result.url, "https://cdn.discordapp.com/old_url.png")

    async def test_process_asset_not_found(self):
        handler = DatabaseAttachmentHandler([self.cached_item])

        mock_attachment = MagicMock(spec=discord.Attachment)
        mock_attachment.id = 9999
        mock_attachment.filename = "unrelated.txt"
        mock_attachment.url = "https://cdn.discordapp.com/unrelated.txt"
        mock_attachment.proxy_url = "https://media.discordapp.net/unrelated.txt"

        result = await handler.process_asset(mock_attachment)
        self.assertEqual(result.url, "https://cdn.discordapp.com/unrelated.txt")
        self.assertEqual(result.proxy_url, "https://media.discordapp.net/unrelated.txt")


class TestOnMessageAutoSaveAttachments(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.boot_time = datetime.now()
        self.bot.db = AsyncMock()
        self.repo = AsyncMock(spec=ChannelExporterRepository)
        self.cog = ChannelExporter(self.bot, exporter_repo=self.repo)

    async def test_on_message_no_attachments(self):
        msg = MagicMock(spec=discord.Message)
        msg.attachments = []
        await self.cog.on_message(msg)
        self.repo.save_attachment.assert_not_called()

    async def test_on_message_no_guild(self):
        msg = MagicMock(spec=discord.Message)
        msg.guild = None
        att = MagicMock(spec=discord.Attachment)
        msg.attachments = [att]
        await self.cog.on_message(msg)
        self.repo.save_attachment.assert_not_called()

    async def test_on_message_regular_channel_ignored(self):
        msg = MagicMock(spec=discord.Message)
        msg.guild = MagicMock(spec=discord.Guild, id=500)
        # Regular text channel, not a thread
        channel = MagicMock(spec=discord.TextChannel)
        channel.type = discord.ChannelType.text
        channel.parent_id = None
        msg.channel = channel
        att = MagicMock(spec=discord.Attachment)
        msg.attachments = [att]

        await self.cog.on_message(msg)
        self.repo.save_attachment.assert_not_called()

    async def test_on_message_modmail_setting_missing(self):
        msg = MagicMock(spec=discord.Message)
        msg.guild = MagicMock(spec=discord.Guild, id=500)
        thread = MagicMock(spec=discord.Thread)
        thread.type = discord.ChannelType.public_thread
        thread.parent_id = 1234
        msg.channel = thread
        msg.attachments = [MagicMock(spec=discord.Attachment)]

        self.bot.db.get_setting.return_value = None
        await self.cog.on_message(msg)
        self.repo.save_attachment.assert_not_called()

    async def test_on_message_different_thread_parent_ignored(self):
        msg = MagicMock(spec=discord.Message)
        msg.guild = MagicMock(spec=discord.Guild, id=500)
        thread = MagicMock(spec=discord.Thread)
        thread.type = discord.ChannelType.public_thread
        thread.parent_id = 9999
        thread.name = "Random Discussion"
        msg.channel = thread
        msg.attachments = [MagicMock(spec=discord.Attachment)]

        self.bot.db.get_setting.return_value = SimpleNamespace(value="1234")
        await self.cog.on_message(msg)
        self.repo.save_attachment.assert_not_called()

    async def test_on_message_saves_valid_attachments_in_modmail_thread(self):
        msg = MagicMock(spec=discord.Message)
        msg.id = 2001
        msg.guild = MagicMock(spec=discord.Guild, id=500)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 1001
        thread.type = discord.ChannelType.public_thread
        thread.parent_id = 1234
        thread.name = "Thread for User"
        msg.channel = thread

        self.bot.db.get_setting.return_value = SimpleNamespace(value=1234)

        att1 = MagicMock(spec=discord.Attachment)
        att1.id = 3001
        att1.filename = "evidence.png"
        att1.size = 1024 * 50  # 50 KB
        att1.content_type = "image/png"
        att1.read = AsyncMock(return_value=b"png-data")

        att2 = MagicMock(spec=discord.Attachment)
        att2.id = 3002
        att2.filename = "log.txt"
        att2.size = 512
        att2.content_type = None  # Should fallback to octet-stream
        att2.read = AsyncMock(return_value=b"txt-data")

        msg.attachments = [att1, att2]
        await self.cog.on_message(msg)

        self.assertEqual(self.repo.save_attachment.call_count, 2)
        self.repo.save_attachment.assert_any_await(
            channel_id=1001,
            message_id=2001,
            attachment_id=3001,
            filename="evidence.png",
            content_type="image/png",
            data=b"png-data",
        )
        self.repo.save_attachment.assert_any_await(
            channel_id=1001,
            message_id=2001,
            attachment_id=3002,
            filename="log.txt",
            content_type="application/octet-stream",
            data=b"txt-data",
        )

    async def test_on_message_skips_large_attachments(self):
        msg = MagicMock(spec=discord.Message)
        msg.guild = MagicMock(spec=discord.Guild, id=500)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 1001
        thread.parent_id = 1234
        msg.channel = thread

        self.bot.db.get_setting.return_value = SimpleNamespace(value="1234")

        large_att = MagicMock(spec=discord.Attachment)
        large_att.size = 10 * 1024 * 1024 + 1  # Over 10 MB
        large_att.read = AsyncMock()
        msg.attachments = [large_att]

        await self.cog.on_message(msg)
        large_att.read.assert_not_called()
        self.repo.save_attachment.assert_not_called()

    async def test_on_message_handles_read_exception_gracefully(self):
        msg = MagicMock(spec=discord.Message)
        msg.guild = MagicMock(spec=discord.Guild, id=500)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 1001
        thread.parent_id = 1234
        msg.channel = thread

        self.bot.db.get_setting.return_value = SimpleNamespace(value=1234)

        failing_att = MagicMock(spec=discord.Attachment)
        failing_att.id = 4001
        failing_att.size = 1024
        failing_att.read = AsyncMock(side_effect=Exception("Network error"))
        msg.attachments = [failing_att]

        await self.cog.on_message(msg)
        self.repo.save_attachment.assert_not_called()


class TestExportAndArchiveFlow(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.boot_time = datetime.now()
        self.bot.db = MagicMock()
        self.repo = AsyncMock(spec=ChannelExporterRepository)
        self.cog = ChannelExporter(self.bot, exporter_repo=self.repo)

    @patch("chat_exporter.export", new_callable=AsyncMock)
    async def test_export_and_archive_channel_success(self, mock_export):
        mock_export.return_value = "<html><body>Exported Transcript</body></html>"
        self.repo.get_channel_attachments.return_value = [
            CachedAttachment(
                id=1,
                channel_id=701,
                message_id=801,
                attachment_id=901,
                filename="pic.png",
                content_type="image/png",
                data=b"imagebytes",
            )
        ]
        self.repo.save_transcript.return_value = 42

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 701
        channel.name = "modmail-thread-1"
        guild = MagicMock(spec=discord.Guild)
        guild.id = 501

        html, archive_id = await export_and_archive_channel(
            bot=self.bot,
            channel=channel,
            guild=guild,
            exported_by_id=12345,
            exporter_repo=self.repo,
        )

        self.assertEqual(html, "<html><body>Exported Transcript</body></html>")
        self.assertEqual(archive_id, 42)

        # Verify chat_exporter.export was called with DatabaseAttachmentHandler
        mock_export.assert_awaited_once()
        kwargs = mock_export.call_args.kwargs
        self.assertIsInstance(kwargs["attachment_handler"], DatabaseAttachmentHandler)
        self.assertEqual(kwargs["channel"], channel)
        self.assertEqual(kwargs["guild"], guild)
        self.assertEqual(kwargs["military_time"], True)
        self.assertEqual(kwargs["fancy_times"], True)
        self.assertEqual(kwargs["support_dev"], False)

        # Verify transcript saved and attachments deleted
        self.repo.save_transcript.assert_awaited_once_with(
            guild_id=501,
            channel_id=701,
            channel_name="modmail-thread-1",
            exported_by=12345,
            html_content="<html><body>Exported Transcript</body></html>",
        )
        self.repo.delete_channel_attachments.assert_awaited_once_with(701)

    @patch("chat_exporter.export", new_callable=AsyncMock)
    async def test_export_and_archive_channel_empty(self, mock_export):
        mock_export.return_value = None
        self.repo.get_channel_attachments.return_value = []

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 701
        guild = MagicMock(spec=discord.Guild)
        guild.id = 501

        html, archive_id = await export_and_archive_channel(
            bot=self.bot,
            channel=channel,
            guild=guild,
            exported_by_id=12345,
            exporter_repo=self.repo,
        )

        self.assertIsNone(html)
        self.assertIsNone(archive_id)
        self.repo.save_transcript.assert_not_called()
        self.repo.delete_channel_attachments.assert_not_called()

    @patch("chat_exporter.export", new_callable=AsyncMock)
    async def test_export_and_archive_channel_whoops_error(self, mock_export):
        mock_export.return_value = "Whoops! Something went wrong while exporting."
        self.repo.get_channel_attachments.return_value = []

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 701
        guild = MagicMock(spec=discord.Guild)
        guild.id = 501

        html, archive_id = await export_and_archive_channel(
            bot=self.bot,
            channel=channel,
            guild=guild,
            exported_by_id=12345,
            exporter_repo=self.repo,
        )

        self.assertIsNone(html)
        self.assertIsNone(archive_id)
        self.repo.save_transcript.assert_not_called()
        self.repo.delete_channel_attachments.assert_not_called()

    async def test_slash_command_export_dm_guard(self):
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.guild = None
        ctx.respond = AsyncMock()

        await self.cog.export.callback(self.cog, ctx)
        ctx.respond.assert_awaited_once_with("This command can only be used in a server.", ephemeral=True)

    @patch("extensions.moderation.channel_exporter.export_and_archive_channel", new_callable=AsyncMock)
    async def test_slash_command_export_success(self, mock_export_helper):
        mock_export_helper.return_value = ("<html><body>Exported</body></html>", 42)

        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.channel = MagicMock(spec=discord.TextChannel)
        ctx.channel.id = 701
        ctx.channel.name = "modmail-thread"
        ctx.guild = MagicMock(spec=discord.Guild, id=501)
        ctx.author = MagicMock(spec=discord.Member, id=999)
        ctx.author.name = "Moderator"
        ctx.response = MagicMock()
        ctx.response.defer = AsyncMock()
        ctx.followup = MagicMock()
        ctx.followup.send = AsyncMock()

        await self.cog.export.callback(self.cog, ctx)

        ctx.response.defer.assert_awaited_once_with(ephemeral=True, invisible=False)
        mock_export_helper.assert_awaited_once_with(
            bot=self.bot,
            channel=ctx.channel,
            guild=ctx.guild,
            exported_by_id=999,
            exporter_repo=self.repo,
        )
        ctx.followup.send.assert_awaited_once()
        call_args, call_kwargs = ctx.followup.send.call_args
        self.assertIn("modmail-thread export", call_args[0])
        self.assertIsInstance(call_kwargs["file"], discord.File)
        self.assertTrue(call_kwargs["file"].filename.endswith(".html"))

    @patch("extensions.moderation.channel_exporter.export_and_archive_channel", new_callable=AsyncMock)
    async def test_slash_command_export_empty_channel(self, mock_export_helper):
        mock_export_helper.return_value = (None, None)

        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.channel = MagicMock(spec=discord.TextChannel)
        ctx.channel.id = 701
        ctx.channel.name = "empty-channel"
        ctx.guild = MagicMock(spec=discord.Guild, id=501)
        ctx.author = MagicMock(spec=discord.Member, id=999)
        ctx.response = MagicMock()
        ctx.response.defer = AsyncMock()
        ctx.followup = MagicMock()
        ctx.followup.send = AsyncMock()

        await self.cog.export.callback(self.cog, ctx)

        ctx.response.defer.assert_awaited_once_with(ephemeral=True, invisible=False)
        ctx.followup.send.assert_awaited_once()
        self.assertIn("empty", ctx.followup.send.call_args[0][0])
        self.assertTrue(ctx.followup.send.call_args[1].get("ephemeral"))

    @patch("chat_exporter.export", new_callable=AsyncMock)
    async def test_cog_helper_method_delegation(self, mock_export):
        mock_export.return_value = "<html>Helper</html>"
        self.repo.get_channel_attachments.return_value = []
        self.repo.save_transcript.return_value = 88

        channel = MagicMock(spec=discord.TextChannel, id=701, name="ch")
        guild = MagicMock(spec=discord.Guild, id=501)

        html, archive_id = await self.cog.export_and_archive_channel(channel, guild, exported_by_id=123)
        self.assertEqual(html, "<html>Helper</html>")
        self.assertEqual(archive_id, 88)

    def test_setup_registers_cog(self):
        mock_bot = MagicMock()
        mock_bot.boot_time = datetime.now()
        mock_bot.db = MagicMock()
        setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
        self.assertIsInstance(mock_bot.add_cog.call_args[0][0], ChannelExporter)


if __name__ == "__main__":
    unittest.main()

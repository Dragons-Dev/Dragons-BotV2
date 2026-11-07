from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from extensions.moderation.modmail import (
    CloseModmailThreadView,
    EndModmailView,
    ModMail,
    _closure_message,
    _first_int,
    _to_embed,
    close_and_archive_modmail,
)
from extensions.moderation.models import Modmail
from extensions.moderation.repository import ModmailRepository
from utils.orm_database import Base, ORMDataBase


def mock_entity(entity_id: int, **kwargs) -> SimpleNamespace:
    return SimpleNamespace(id=entity_id, **kwargs)


class TestModmailRepositoryCRUD(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(self.engine, expire_on_commit=False)
        ORMDataBase._discover_models(SimpleNamespace(logger=None))  # type: ignore[arg-type]
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.repo = ModmailRepository(self.session_maker)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_crud_with_thread_id(self):
        user = mock_entity(101)
        guild = mock_entity(201)
        uuid_str = "test-uuid-12345"

        # LookupError when all args are None
        with self.assertRaises(LookupError):
            await self.repo.get_modmail(None, None, None)
        with self.assertRaises(LookupError):
            await self.repo.delete_modmail(None, None, None)

        # Create modmail with thread_id=None initially
        mail = await self.repo.create_modmail(user, guild, uuid_str, anonymous=True, thread_id=None)  # type: ignore[arg-type]
        self.assertIsInstance(mail, Modmail)
        self.assertEqual(mail.uuid, uuid_str)
        self.assertEqual(mail.user_id, 101)
        self.assertEqual(mail.guild_id, 201)
        self.assertTrue(mail.anon)
        self.assertIsNone(mail.thread_id)

        # Query by user
        by_user = await self.repo.get_modmail(user=user)  # type: ignore[arg-type]
        self.assertIsNotNone(by_user)
        assert by_user is not None
        self.assertEqual(by_user.uuid, uuid_str)

        # Query by uuid
        by_uuid = await self.repo.get_modmail(uuid=uuid_str)
        self.assertIsNotNone(by_uuid)
        assert by_uuid is not None
        self.assertEqual(by_uuid.user_id, 101)

        # Query by thread_id before setting
        self.assertIsNone(await self.repo.get_modmail(thread_id=5555))

        # Update thread_id
        await self.repo.update_thread_id(uuid_str, 5555)

        # Query by thread_id after setting
        by_thread = await self.repo.get_modmail(thread_id=5555)
        self.assertIsNotNone(by_thread)
        assert by_thread is not None
        self.assertEqual(by_thread.uuid, uuid_str)
        self.assertEqual(by_thread.thread_id, 5555)

        # Delete by thread_id
        await self.repo.delete_modmail(thread_id=5555)
        self.assertIsNone(await self.repo.get_modmail(uuid=uuid_str))

        # Safe no-op delete
        await self.repo.delete_modmail(thread_id=5555)


class TestToEmbedAndAnonymity(unittest.TestCase):
    def test_first_int(self):
        self.assertEqual(_first_int("1234"), 1)
        self.assertEqual(_first_int("89"), 4)  # 8 > 5 -> 8 // 2 = 4
        self.assertEqual(_first_int("abc"), 0)

    def test_to_embed_anonymous(self):
        msg = MagicMock(spec=discord.Message)
        msg.author = MagicMock(spec=discord.User)
        msg.author.name = "SecretUser"
        msg.author.display_avatar.url = "https://cdn.discordapp.com/avatars/123/avatar.png"
        msg.author.id = 999888777
        msg.content = "Anonymous hello"
        msg.created_at = datetime.now()

        uuid = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
        embed = _to_embed(msg, uuid, anonymous=True)

        self.assertEqual(embed.author.name, f"Anon#{uuid[:7]}")
        self.assertIn("https://cdn.discordapp.com/embed/avatars/", embed.author.icon_url)
        self.assertIsNone(embed.author.url)
        self.assertEqual(embed.footer.text, f"UUID: {uuid}")
        self.assertEqual(embed.description, "Anonymous hello")

        # Ensure no user ID or real username anywhere in embed data
        embed_dict = embed.to_dict()
        dict_str = str(embed_dict)
        self.assertNotIn("SecretUser", dict_str)
        self.assertNotIn("999888777", dict_str)

    def test_to_embed_non_anonymous(self):
        msg = MagicMock(spec=discord.Message)
        msg.author = MagicMock(spec=discord.User)
        msg.author.name = "PublicUser"
        msg.author.display_avatar.url = "https://cdn.discordapp.com/avatars/123/avatar.png"
        msg.author.id = 11223344
        msg.content = "Public hello"
        msg.created_at = datetime.now()

        uuid = "11111111-2222-3333-4444-555555555555"
        embed = _to_embed(msg, uuid, anonymous=False)

        self.assertEqual(embed.author.name, "PublicUser")
        self.assertEqual(embed.author.url, "https://discord.id/?prefill=11223344")
        self.assertEqual(embed.author.icon_url, "https://cdn.discordapp.com/avatars/123/avatar.png")
        self.assertEqual(embed.footer.text, "Member ID: 11223344")

    def test_closure_message_anonymity(self):
        anon_mail = Modmail(uuid="abcdef123456", user_id=1, guild_id=2, anon=True)
        user = MagicMock(spec=discord.User)
        user.name = "RealUser"

        # User closes anon mail -> Anon label used
        msg = _closure_message(anon_mail, user, closed_by_staff=False)
        self.assertEqual(msg, f"Anon#{anon_mail.uuid[:7]} has closed the conversation!")
        self.assertNotIn("RealUser", msg)

        # Staff closes anon mail -> Staff name displayed
        staff = MagicMock(spec=discord.User)
        staff.name = "StaffMod"
        msg_staff = _closure_message(anon_mail, staff, closed_by_staff=True)
        self.assertEqual(msg_staff, "StaffMod has closed the conversation!")

        # User closes non-anon mail -> User name used
        non_anon_mail = Modmail(uuid="abcdef123456", user_id=1, guild_id=2, anon=False)
        msg_non_anon = _closure_message(non_anon_mail, user, closed_by_staff=False)
        self.assertEqual(msg_non_anon, "RealUser has closed the conversation!")


class TestUserDMModmailFlow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.boot_time = datetime.now()
        self.bot.db = AsyncMock()
        self.repo = AsyncMock(spec=ModmailRepository)
        self.cog = ModMail(self.bot, modmail_repo=self.repo)

    async def test_user_dm_creates_thread_saves_thread_id_and_sends_view(self):
        msg = MagicMock(spec=discord.Message)
        msg.guild = None
        msg.author = MagicMock(spec=discord.User)
        msg.author.bot = False
        msg.author.id = 1001
        msg.author.name = "TestAuthor"
        msg.content = "Help please"
        msg.created_at = datetime.now()
        msg.attachments = []

        mail = Modmail(
            uuid="12345678-abcd-ef01-2345-6789abcdef01",
            user_id=1001,
            guild_id=2001,
            anon=True,
            thread_id=None,
        )
        self.repo.get_modmail.return_value = mail

        guild = MagicMock(spec=discord.Guild)
        guild.id = 2001
        guild.get_thread.return_value = None

        modmail_channel = MagicMock(spec=discord.TextChannel)
        modmail_channel.id = 3001
        modmail_channel.threads = []

        start_msg = MagicMock(spec=discord.Message)
        new_thread = MagicMock(spec=discord.Thread)
        new_thread.id = 77777
        new_thread.send = AsyncMock()
        start_msg.create_thread = AsyncMock(return_value=new_thread)
        modmail_channel.send = AsyncMock(return_value=start_msg)

        self.bot.db.get_setting.return_value = SimpleNamespace(value=3001)

        async def fake_get_or_fetch(obj, attr, entity_id, default=None):
            if attr == "guild" and entity_id == 2001:
                return guild
            if attr == "channel" and entity_id == 3001:
                return modmail_channel
            if attr in ("channel", "thread") and entity_id == 77777:
                return new_thread
            return default

        with patch("extensions.moderation.modmail.get_or_fetch", side_effect=fake_get_or_fetch):
            await self.cog.on_modmail(msg)

        # Thread created
        modmail_channel.send.assert_awaited_once()
        start_msg.create_thread.assert_awaited_once_with(name="Thread for Anon#1234567", auto_archive_duration=4320)

        # thread_id saved in DB
        self.repo.update_thread_id.assert_awaited_once_with(mail.uuid, 77777)

        # Forwarded message to thread with CloseModmailThreadView
        new_thread.send.assert_awaited_once()
        _, kwargs = new_thread.send.call_args
        self.assertIn("embed", kwargs)
        self.assertIn("view", kwargs)
        self.assertIsInstance(kwargs["view"], CloseModmailThreadView)

    async def test_user_dm_reuses_existing_thread_by_thread_id(self):
        msg = MagicMock(spec=discord.Message)
        msg.guild = None
        msg.author = MagicMock(spec=discord.User, bot=False, id=1001, name="TestAuthor")
        msg.content = "Followup message"
        msg.created_at = datetime.now()
        msg.attachments = []

        existing_thread = MagicMock(spec=discord.Thread)
        existing_thread.id = 77777
        existing_thread.archived = False
        existing_thread.locked = False
        existing_thread.send = AsyncMock()

        mail = Modmail(
            uuid="12345678-abcd-ef01-2345-6789abcdef01",
            user_id=1001,
            guild_id=2001,
            anon=True,
            thread_id=77777,
        )
        self.repo.get_modmail.return_value = mail

        guild = MagicMock(spec=discord.Guild)
        guild.id = 2001
        guild.get_thread.return_value = existing_thread

        modmail_channel = MagicMock(spec=discord.TextChannel, id=3001, threads=[existing_thread])
        modmail_channel.send = AsyncMock()

        self.bot.db.get_setting.return_value = SimpleNamespace(value=3001)

        async def fake_get_or_fetch(obj, attr, entity_id, default=None):
            if attr == "guild":
                return guild
            if attr == "channel":
                return modmail_channel
            return default

        with patch("extensions.moderation.modmail.get_or_fetch", side_effect=fake_get_or_fetch):
            await self.cog.on_modmail(msg)

        # No new thread created
        modmail_channel.send.assert_not_called()
        # Message sent directly to existing thread
        existing_thread.send.assert_awaited_once()
        _, kwargs = existing_thread.send.call_args
        # Follow-up message does not append redundant view
        self.assertNotIn("view", kwargs)

    async def test_user_dm_large_attachment_rejected(self):
        msg = MagicMock(spec=discord.Message)
        msg.guild = None
        msg.author = MagicMock(spec=discord.User, bot=False, id=1001)
        msg.channel = MagicMock()
        msg.channel.send = AsyncMock()

        att = MagicMock(spec=discord.Attachment)
        att.size = 15 * 1024 * 1024  # 15 MB
        att.filename = "huge.zip"
        msg.attachments = [att]

        mail = Modmail(uuid="abc", user_id=1001, guild_id=2001, anon=False)
        self.repo.get_modmail.return_value = mail

        with patch("extensions.moderation.modmail.get_or_fetch", return_value=MagicMock()):
            await self.cog.on_modmail(msg)

        msg.channel.send.assert_awaited_once()
        args, _ = msg.channel.send.call_args
        self.assertIn("to large to be send", args[0])


class TestStaffMessageModmailFlow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.boot_time = datetime.now()
        self.bot.db = AsyncMock()
        self.repo = AsyncMock(spec=ModmailRepository)
        self.cog = ModMail(self.bot, modmail_repo=self.repo)

    async def test_staff_message_in_thread_looks_up_by_thread_id_without_scraping(self):
        staff_author = MagicMock(spec=discord.Member)
        staff_author.bot = False
        staff_author.name = "StaffModerator"
        staff_author.id = 8888
        staff_author.display_avatar.url = "https://cdn.discordapp.com/avatars/8888/avatar.png"

        thread = MagicMock(spec=discord.Thread)
        thread.id = 77777
        thread.parent_id = 3001
        thread.history = MagicMock()  # Must NOT be called

        msg = MagicMock(spec=discord.Message)
        msg.guild = MagicMock(spec=discord.Guild, id=2001)
        msg.author = staff_author
        msg.channel = thread
        msg.content = "Here is the response from staff."
        msg.created_at = datetime.now()
        msg.attachments = []

        self.bot.db.get_setting.return_value = SimpleNamespace(value=3001)

        mail = Modmail(uuid="test-uuid", user_id=1001, guild_id=2001, anon=True, thread_id=77777)
        self.repo.get_modmail.return_value = mail

        target_user = MagicMock(spec=discord.User)
        target_user.send = AsyncMock()

        async def fake_get_or_fetch(obj, attr, entity_id, default=None):
            if attr == "user" and entity_id == 1001:
                return target_user
            return default

        with patch("extensions.moderation.modmail.get_or_fetch", side_effect=fake_get_or_fetch):
            await self.cog.on_modmail(msg)

        # Lookup by thread_id verified
        self.repo.get_modmail.assert_awaited_once_with(thread_id=77777)
        # History scraping eliminated!
        thread.history.assert_not_called()
        # Message delivered to user in DM
        target_user.send.assert_awaited_once()
        _, kwargs = target_user.send.call_args
        embed = kwargs["embed"]
        self.assertEqual(embed.author.name, "StaffModerator")
        self.assertEqual(embed.description, "Here is the response from staff.")

    async def test_staff_message_fallback_when_thread_id_not_set(self):
        staff_author = MagicMock(spec=discord.Member, bot=False, name="StaffMod", id=8888)
        staff_author.display_avatar.url = "https://cdn.discordapp.com/avatars/8888/avatar.png"

        thread = MagicMock(spec=discord.Thread)
        thread.id = 77777
        thread.parent_id = 3001

        history_msg = MagicMock(spec=discord.Message)
        embed_mock = MagicMock()
        embed_mock.footer.text = "UUID: fallback-uuid-123"
        history_msg.embeds = [embed_mock]

        async def fake_history(limit=50):
            yield history_msg

        thread.history = fake_history

        msg = MagicMock(spec=discord.Message)
        msg.guild = MagicMock(spec=discord.Guild, id=2001)
        msg.author = staff_author
        msg.channel = thread
        msg.content = "Fallback test response"
        msg.created_at = datetime.now()
        msg.attachments = []

        self.bot.db.get_setting.return_value = SimpleNamespace(value=3001)

        # First call by thread_id returns None; second call by uuid returns mail
        mail = Modmail(uuid="fallback-uuid-123", user_id=1001, guild_id=2001, anon=True, thread_id=None)

        async def fake_get_modmail(**kwargs):
            if kwargs.get("thread_id") == 77777:
                return None
            if kwargs.get("uuid") == "fallback-uuid-123":
                return mail
            return None

        self.repo.get_modmail.side_effect = fake_get_modmail

        target_user = MagicMock(spec=discord.User)
        target_user.send = AsyncMock()

        async def fake_get_or_fetch(obj, attr, entity_id, default=None):
            if attr == "user" and entity_id == 1001:
                return target_user
            return default

        with patch("extensions.moderation.modmail.get_or_fetch", side_effect=fake_get_or_fetch):
            await self.cog.on_modmail(msg)

        # Verified fallback updated thread_id in DB
        self.repo.update_thread_id.assert_awaited_once_with("fallback-uuid-123", 77777)
        target_user.send.assert_awaited_once()


class TestCloseAndArchiveModmail(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.boot_time = datetime.now()
        self.bot.db = AsyncMock()
        self.repo = AsyncMock(spec=ModmailRepository)

    async def test_close_and_archive_modmail_staff_initiated(self):
        mail = Modmail(
            uuid="12345678-90ab-cdef-1234-567890abcdef",
            user_id=1001,
            guild_id=2001,
            anon=True,
            thread_id=77777,
        )
        closer = MagicMock(spec=discord.Member)
        closer.id = 8888
        closer.name = "StaffCloser"

        guild = MagicMock(spec=discord.Guild, id=2001)
        guild.name = "Test Guild"
        thread = MagicMock(spec=discord.Thread, id=77777)
        thread.name = "Thread for Anon#1234567"
        thread.send = AsyncMock()
        thread.edit = AsyncMock()
        guild.get_thread.return_value = thread
        self.bot.get_guild.return_value = guild

        modmail_channel = MagicMock(spec=discord.TextChannel, id=3001)
        modmail_channel.send = AsyncMock()

        self.bot.db.get_setting.return_value = SimpleNamespace(value=3001)

        user = MagicMock(spec=discord.User)
        user.name = "TestUser"
        user.send = AsyncMock()

        async def fake_get_or_fetch(obj, attr, entity_id, default=None):
            if attr == "channel" and entity_id == 3001:
                return modmail_channel
            if attr == "user" and entity_id == 1001:
                return user
            return default

        with (
            patch("extensions.moderation.modmail.get_or_fetch", side_effect=fake_get_or_fetch),
            patch(
                "extensions.moderation.modmail.export_and_archive_channel",
                new_callable=AsyncMock,
                return_value=("<html>Transcript</html>", 42),
            ) as mock_export,
        ):
            await close_and_archive_modmail(
                bot=self.bot,
                mail=mail,
                closer=closer,
                modmail_repo=self.repo,
                closed_by_staff=True,
            )

        # 1. Deleted from repo
        self.repo.delete_modmail.assert_awaited_once_with(uuid=mail.uuid)

        # 2. Sent closure message in thread
        thread.send.assert_awaited_once_with("StaffCloser has closed the conversation!")

        # 3. Called export_and_archive_channel
        mock_export.assert_awaited_once_with(
            bot=self.bot,
            channel=thread,
            guild=guild,
            exported_by_id=closer.id,
        )

        # 4. Transcript HTML file posted to modmail_channel
        modmail_channel.send.assert_awaited_once()
        _, kwargs = modmail_channel.send.call_args
        self.assertIn("file", kwargs)
        self.assertIsInstance(kwargs["file"], discord.File)
        self.assertEqual(kwargs["file"].filename, "Thread for Anon#1234567.html")

        # 5. Thread locked and archived
        thread.edit.assert_awaited_once_with(locked=True, archived=True)

        # 6. User informed in DM since closed by staff
        user.send.assert_awaited_once()

    async def test_close_and_archive_modmail_user_initiated_preserves_anonymity(self):
        mail = Modmail(
            uuid="12345678-90ab-cdef-1234-567890abcdef",
            user_id=1001,
            guild_id=2001,
            anon=True,
            thread_id=77777,
        )
        closer = MagicMock(spec=discord.User)
        closer.id = 1001
        closer.name = "RealSecretUser"

        guild = MagicMock(spec=discord.Guild, id=2001)
        guild.name = "Test Guild"
        thread = MagicMock(spec=discord.Thread, id=77777)
        thread.name = "Thread for Anon#1234567"
        thread.send = AsyncMock()
        thread.edit = AsyncMock()
        guild.get_thread.return_value = thread
        self.bot.get_guild.return_value = guild

        modmail_channel = MagicMock(spec=discord.TextChannel, id=3001)
        modmail_channel.send = AsyncMock()
        self.bot.db.get_setting.return_value = SimpleNamespace(value=3001)

        async def fake_get_or_fetch(obj, attr, entity_id, default=None):
            if attr == "channel" and entity_id == 3001:
                return modmail_channel
            return default

        with (
            patch("extensions.moderation.modmail.get_or_fetch", side_effect=fake_get_or_fetch),
            patch(
                "extensions.moderation.modmail.export_and_archive_channel",
                new_callable=AsyncMock,
                return_value=("<html>Transcript</html>", 42),
            ),
        ):
            await close_and_archive_modmail(
                bot=self.bot,
                mail=mail,
                closer=closer,
                modmail_repo=self.repo,
                closed_by_staff=False,
            )

        # Closure message must preserve anonymity!
        thread.send.assert_awaited_once_with(f"Anon#{mail.uuid[:7]} has closed the conversation!")
        self.assertNotIn("RealSecretUser", str(thread.send.call_args))

    async def test_close_modmail_thread_view_button_interaction(self):
        view = CloseModmailThreadView(self.bot, self.repo)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel_id = 77777
        interaction.user = MagicMock(spec=discord.Member, id=9999, name="StaffButtonCloser")
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        mail = Modmail(uuid="btn-uuid", user_id=1001, guild_id=2001, anon=False, thread_id=77777)
        self.repo.get_modmail.return_value = mail

        with patch("extensions.moderation.modmail.close_and_archive_modmail", new_callable=AsyncMock) as mock_close:
            await view.close_thread_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        mock_close.assert_awaited_once_with(
            bot=self.bot,
            mail=mail,
            closer=interaction.user,
            modmail_repo=self.repo,
            closed_by_staff=True,
        )

    async def test_close_modmail_thread_view_button_already_closed(self):
        view = CloseModmailThreadView(self.bot, self.repo)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel_id = 77777
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        self.repo.get_modmail.return_value = None

        with patch("extensions.moderation.modmail.close_and_archive_modmail", new_callable=AsyncMock) as mock_close:
            await view.close_thread_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        args, kwargs = interaction.response.send_message.call_args
        self.assertIn("already closed", args[0])
        self.assertTrue(kwargs.get("ephemeral"))
        mock_close.assert_not_called()

    async def test_end_modmail_view_button(self):
        author = MagicMock(spec=discord.User, id=1001)
        author.name = "EndUser"
        view = EndModmailView(author, self.bot, self.repo)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.edit = AsyncMock()

        mail = Modmail(uuid="end-uuid", user_id=1001, guild_id=2001, anon=False)
        self.repo.get_modmail.return_value = mail

        guild = MagicMock(spec=discord.Guild)
        guild.name = "EndGuild"
        self.bot.get_guild.return_value = guild

        with patch("extensions.moderation.modmail.close_and_archive_modmail", new_callable=AsyncMock) as mock_close:
            await view.end_modmail.callback(interaction)

        interaction.edit.assert_awaited_once()
        mock_close.assert_awaited_once_with(
            bot=self.bot,
            mail=mail,
            closer=author,
            modmail_repo=self.repo,
            closed_by_staff=False,
        )

    async def test_slash_command_close_in_thread_by_staff(self):
        cog = ModMail(self.bot, modmail_repo=self.repo)
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.guild = MagicMock(spec=discord.Guild, id=2001)
        ctx.channel = MagicMock(spec=discord.Thread, id=77777)
        ctx.author = MagicMock(spec=discord.Member, id=9999)
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()

        mail = Modmail(uuid="close-uuid", user_id=1001, guild_id=2001, anon=True, thread_id=77777)
        self.repo.get_modmail.return_value = mail

        with patch("extensions.moderation.modmail.close_and_archive_modmail", new_callable=AsyncMock) as mock_close:
            await cog.close_modmail.callback(cog, ctx)

        mock_close.assert_awaited_once_with(
            bot=self.bot,
            mail=mail,
            closer=ctx.author,
            modmail_repo=self.repo,
            closed_by_staff=True,
        )

    async def test_slash_command_close_in_dm_by_user(self):
        cog = ModMail(self.bot, modmail_repo=self.repo)
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.guild = None
        ctx.author = MagicMock(spec=discord.User, id=1001)
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()

        mail = Modmail(uuid="close-uuid-dm", user_id=1001, guild_id=2001, anon=True, thread_id=77777)
        self.repo.get_modmail.return_value = mail

        with patch("extensions.moderation.modmail.close_and_archive_modmail", new_callable=AsyncMock) as mock_close:
            await cog.close_modmail.callback(cog, ctx)

        mock_close.assert_awaited_once_with(
            bot=self.bot,
            mail=mail,
            closer=ctx.author,
            modmail_repo=self.repo,
            closed_by_staff=False,
        )

    async def test_slash_command_end_modmail_confirmed(self):
        cog = ModMail(self.bot, modmail_repo=self.repo)
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.author = MagicMock(spec=discord.User, id=1001)
        ctx.author.name = "EndUser"
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()
        ctx.followup = MagicMock()
        ctx.followup.send = AsyncMock()

        mail = Modmail(uuid="end-cmd-uuid", user_id=1001, guild_id=2001, anon=False)
        self.repo.get_modmail.return_value = mail

        guild = MagicMock(spec=discord.Guild)
        guild.name = "EndGuild"

        with (
            patch("extensions.moderation.modmail.get_or_fetch", return_value=guild),
            patch("extensions.moderation.modmail.ButtonConfirm") as mock_confirm_cls,
            patch("extensions.moderation.modmail.close_and_archive_modmail", new_callable=AsyncMock) as mock_close,
        ):
            mock_confirm_instance = MagicMock()
            mock_confirm_instance.value = True
            mock_confirm_instance.wait = AsyncMock()
            mock_confirm_cls.return_value = mock_confirm_instance

            await cog.end_modmail.callback(cog, ctx)

        mock_close.assert_awaited_once_with(
            bot=self.bot,
            mail=mail,
            closer=ctx.author,
            modmail_repo=self.repo,
            closed_by_staff=False,
        )
        ctx.followup.send.assert_awaited_once()

    async def test_slash_command_create_modmail_in_guild(self):
        cog = ModMail(self.bot, modmail_repo=self.repo)
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.guild = MagicMock(spec=discord.Guild, id=2001)
        ctx.author = MagicMock(spec=discord.Member, id=1001)
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()

        # No active modmail yet
        self.repo.get_modmail.return_value = None

        await cog.create_modmail.callback(cog, ctx, anonymous=True)

        self.repo.create_modmail.assert_awaited_once()
        args, kwargs = self.repo.create_modmail.call_args
        self.assertEqual(args[0], ctx.author)
        self.assertEqual(args[1], ctx.guild)
        self.assertTrue(args[3])  # anonymous
        ctx.response.send_message.assert_awaited_once()

    async def test_close_modmail_thread_view_button_unauthorized(self):
        view = CloseModmailThreadView(self.bot, self.repo)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel_id = 77777
        user = MagicMock(spec=discord.Member, id=9999, name="RandomUser")
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = False
        user.roles = []
        interaction.user = user
        interaction.guild = MagicMock(spec=discord.Guild, id=2001)
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        self.bot.db = AsyncMock()
        self.bot.db.get_setting.return_value = None

        mail = Modmail(uuid="btn-uuid", user_id=1001, guild_id=2001, anon=False, thread_id=77777)
        self.repo.get_modmail.return_value = mail

        with patch("extensions.moderation.modmail.close_and_archive_modmail", new_callable=AsyncMock) as mock_close:
            await view.close_thread_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        self.assertIn("permission", interaction.response.send_message.call_args.args[0])
        mock_close.assert_not_called()

    async def test_slash_command_close_in_thread_unauthorized(self):
        cog = ModMail(self.bot, modmail_repo=self.repo)
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.guild = MagicMock(spec=discord.Guild, id=2001)
        ctx.channel = MagicMock(spec=discord.Thread, id=77777)
        user = MagicMock(spec=discord.Member, id=9999)
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = False
        user.roles = []
        ctx.author = user
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()

        self.bot.db = AsyncMock()
        self.bot.db.get_setting.return_value = None

        mail = Modmail(uuid="close-uuid", user_id=1001, guild_id=2001, anon=True, thread_id=77777)
        self.repo.get_modmail.return_value = mail

        with patch("extensions.moderation.modmail.close_and_archive_modmail", new_callable=AsyncMock) as mock_close:
            await cog.close_modmail.callback(cog, ctx)

        interaction_call = ctx.response.send_message.call_args
        self.assertIn("permission", interaction_call.args[0])
        mock_close.assert_not_called()

    async def test_slash_command_close_in_guild_non_thread_does_not_fall_back_to_user_dm(self):
        cog = ModMail(self.bot, modmail_repo=self.repo)
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.guild = MagicMock(spec=discord.Guild, id=2001)
        ctx.channel = MagicMock(spec=discord.TextChannel, id=88888)  # Not a thread
        ctx.author = MagicMock(spec=discord.Member, id=1001)
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()

        # Thread query returns None; user query returns active ticket
        async def fake_get_modmail(*args, **kwargs):
            if kwargs.get("thread_id") == 88888:
                return None
            if kwargs.get("user") == ctx.author:
                return Modmail(uuid="user-dm-mail", user_id=1001, guild_id=2001, anon=False)
            return None

        self.repo.get_modmail.side_effect = fake_get_modmail

        with patch("extensions.moderation.modmail.close_and_archive_modmail", new_callable=AsyncMock) as mock_close:
            await cog.close_modmail.callback(cog, ctx)

        interaction_call = ctx.response.send_message.call_args
        self.assertIn("No active modmail session or thread found", interaction_call.args[0])
        mock_close.assert_not_called()

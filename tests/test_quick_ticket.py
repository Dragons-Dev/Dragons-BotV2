from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock

import discord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from extensions.moderation.moderation_events import ModerationEvents
from extensions.moderation.modmail import (
    CloseModmailThreadView,
    EndModmailView,
    ModMail,
    ModerationQuickTicketView,
)
from extensions.moderation.repository import InfractionsRepository, ModmailRepository
from utils import InfractionsEnum
from utils.orm_database import Base, ORMDataBase


def create_mock_user(user_id: int = 12345, name: str = "TestUser") -> MagicMock:
    user = MagicMock(spec=discord.User)
    user.id = user_id
    user.name = name
    user.mention = f"<@{user_id}>"
    user.bot = False
    user.send = AsyncMock()
    user.display_avatar = MagicMock()
    user.display_avatar.url = "https://example.com/avatar.png"
    return user


def create_mock_guild(guild_id: int = 99999, name: str = "Test Guild") -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    guild.name = name
    guild.get_or_fetch = AsyncMock()
    guild.get_channel = MagicMock()
    return guild


def create_mock_interaction(user: MagicMock, message: MagicMock | None = None) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = user
    interaction.message = message
    interaction.response = MagicMock()
    interaction.response.is_done = MagicMock(return_value=False)

    async def fake_defer(*args, **kwargs):
        interaction.response.is_done.return_value = True

    interaction.response.defer = AsyncMock(side_effect=fake_defer)
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def get_button(view: discord.ui.View, index: int) -> discord.ui.Button:
    btn = view.children[index]
    assert isinstance(btn, discord.ui.Button)
    return btn


class TestModerationQuickTicket(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(self.engine, expire_on_commit=False)
        ORMDataBase._discover_models(SimpleNamespace(logger=None))  # type: ignore[arg-type]
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.infractions_repo = InfractionsRepository(self.session_maker)
        self.modmail_repo = ModmailRepository(self.session_maker)

        self.mock_client = MagicMock()
        self.mock_client.boot_time = datetime.now()
        self.mock_client.add_view = MagicMock()
        self.mock_client.db = MagicMock()
        self.mock_client.db.session_maker = self.session_maker
        self.mock_client.db.get_setting = AsyncMock(return_value=None)
        self.mock_client.get_or_fetch = AsyncMock()
        self.mock_client.get_guild = MagicMock(return_value=None)

        self.guild = create_mock_guild(guild_id=99999, name="Dragons Server")
        self.user = create_mock_user(user_id=12345, name="BannedUser")
        self.moderator = create_mock_user(user_id=67890, name="ModUser")

        self.modmail_channel = MagicMock(spec=discord.TextChannel)
        self.modmail_channel.id = 55555

        self.thread = MagicMock(spec=discord.Thread)
        self.thread.id = 77777
        self.thread.send = AsyncMock()

        self.modmail_channel.create_thread = AsyncMock(return_value=self.thread)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_send_dm_attaches_quick_ticket_view(self):
        cog = ModerationEvents(self.mock_client, infractions_repo=self.infractions_repo)
        embed = discord.Embed(title="Ban", description="You have been banned")
        embed.set_footer(text="Case ID: 101")

        await cog._send_dm(self.user, embed, dm_info_text="Custom info text")

        self.user.send.assert_awaited_once()
        call_kwargs = self.user.send.call_args.kwargs
        self.assertIn("view", call_kwargs)
        view = call_kwargs["view"]
        self.assertIsInstance(view, ModerationQuickTicketView)
        self.assertEqual(view.info_text, "Custom info text")

        self.assertEqual(len(view.children), 2)
        # Button 1: Info
        info_btn = get_button(view, 0)
        self.assertEqual(info_btn.custom_id, "mod_quick_ticket__info_button")
        self.assertIsNotNone(info_btn.emoji)
        assert info_btn.emoji is not None
        self.assertEqual(info_btn.emoji.name, "ℹ️")
        self.assertEqual(info_btn.label, "")
        self.assertEqual(info_btn.style, discord.ButtonStyle.grey)

        # Button 2: Quick Ticket
        ticket_btn = get_button(view, 1)
        self.assertEqual(ticket_btn.custom_id, "mod_quick_ticket__open_button")
        self.assertIsNotNone(ticket_btn.emoji)
        assert ticket_btn.emoji is not None
        self.assertEqual(ticket_btn.emoji.name, "🎫")
        self.assertEqual(ticket_btn.label, "Open Modmail Ticket")
        self.assertEqual(ticket_btn.style, discord.ButtonStyle.primary)

    async def test_info_button_callback(self):
        view = ModerationQuickTicketView(
            info_text="Important infraction info",
            bot=self.mock_client,
            infractions_repo=self.infractions_repo,
            modmail_repo=self.modmail_repo,
        )
        interaction = create_mock_interaction(user=self.user)

        await get_button(view, 0).callback(interaction)
        interaction.response.send_message.assert_awaited_once_with("Important infraction info", ephemeral=True)

    async def test_info_button_fallback_safebrowsing_context(self):
        # View initialized without custom info text (simulating persistent view after bot restart)
        view = ModerationQuickTicketView(
            bot=self.mock_client,
            infractions_repo=self.infractions_repo,
            modmail_repo=self.modmail_repo,
        )
        sb_embed = discord.Embed(title="Message context", description="Malicious link detected")
        msg = MagicMock(spec=discord.Message)
        msg.embeds = [discord.Embed(title="Warn"), sb_embed]

        interaction = create_mock_interaction(user=self.user, message=msg)

        await get_button(view, 0).callback(interaction)
        interaction.response.send_message.assert_awaited_once_with(
            "You were warned due to the message above.", ephemeral=True
        )

    async def test_open_modmail_ticket_standard_ban_user_not_in_guild(self):
        case_id = await self.infractions_repo.create_infraction(
            user=self.user,
            infraction=InfractionsEnum.Ban,
            reason="Violating community rules",
            guild=self.guild,
        )

        setting_mock = SimpleNamespace(value=self.modmail_channel.id)
        self.mock_client.db.get_setting.return_value = setting_mock
        self.mock_client.get_or_fetch.return_value = self.guild
        self.guild.get_or_fetch.return_value = self.modmail_channel

        view = ModerationQuickTicketView(
            bot=self.mock_client,
            infractions_repo=self.infractions_repo,
            modmail_repo=self.modmail_repo,
        )

        dm_embed = discord.Embed(title="Ban", description="You have been banned")
        dm_embed.set_footer(text=f"Case ID: {case_id}")

        msg = MagicMock(spec=discord.Message)
        msg.embeds = [dm_embed]
        msg.edit = AsyncMock()

        interaction = create_mock_interaction(user=self.user, message=msg)

        await get_button(view, 1).callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)

        # 1. Modmail session created in DB
        mail = await self.modmail_repo.get_modmail(user=self.user)
        self.assertIsNotNone(mail)
        assert mail is not None
        self.assertEqual(mail.guild_id, self.guild.id)
        self.assertEqual(mail.user_id, self.user.id)
        self.assertFalse(mail.anon)
        self.assertEqual(mail.thread_id, self.thread.id)

        # 2. Thread created in ModmailChannel
        self.modmail_channel.create_thread.assert_awaited_once_with(
            name=f"Thread for {self.user.name}", auto_archive_duration=4320
        )

        # 3. Initial context message sent to thread
        self.thread.send.assert_awaited_once()
        send_kwargs = self.thread.send.call_args.kwargs
        self.assertIn("embeds", send_kwargs)
        self.assertIn("view", send_kwargs)
        self.assertIsInstance(send_kwargs["view"], CloseModmailThreadView)

        context_embed = send_kwargs["embeds"][0]
        self.assertEqual(context_embed.title, f"Moderation Ticket — Case #{case_id} (Ban)")
        self.assertEqual(context_embed.footer.text, f"Member ID: {self.user.id}")
        field_dict = {f.name: f.value for f in context_embed.fields}
        self.assertIn("User", field_dict)
        self.assertIn(self.user.mention, field_dict["User"])
        self.assertIn(self.user.name, field_dict["User"])
        self.assertIn("Reason", field_dict)
        self.assertEqual(field_dict["Reason"], "Violating community rules")

        # 4. Button disabled and label updated
        ticket_btn_after = get_button(view, 1)
        self.assertTrue(ticket_btn_after.disabled)
        self.assertEqual(ticket_btn_after.label, "Ticket Opened")
        msg.edit.assert_awaited_once_with(view=view)

        # 5. User confirmation sent ephemerally via followup
        interaction.followup.send.assert_awaited_once()
        confirm_text = interaction.followup.send.call_args.args[0]
        self.assertIn(self.guild.name, confirm_text)
        self.assertTrue(interaction.followup.send.call_args.kwargs.get("ephemeral"))

    async def test_open_modmail_ticket_safebrowsing_forwards_extra_embeds(self):
        case_id = await self.infractions_repo.create_infraction(
            user=self.user,
            infraction=InfractionsEnum.Warn,
            reason="Malicious link detected",
            guild=self.guild,
        )

        setting_mock = SimpleNamespace(value=self.modmail_channel.id)
        self.mock_client.db.get_setting.return_value = setting_mock
        self.mock_client.get_or_fetch.return_value = self.guild
        self.guild.get_or_fetch.return_value = self.modmail_channel

        view = ModerationQuickTicketView(
            bot=self.mock_client,
            infractions_repo=self.infractions_repo,
            modmail_repo=self.modmail_repo,
        )

        mod_embed = discord.Embed(title="Warn", description="You have been warned")
        mod_embed.set_footer(text=f"Case ID: {case_id}")

        safebrowsing_embed = discord.Embed(
            title="Message context",
            description="Message: Visit http://phishing-site.example.com",
        )

        msg = MagicMock(spec=discord.Message)
        msg.embeds = [mod_embed, safebrowsing_embed]
        msg.edit = AsyncMock()

        interaction = create_mock_interaction(user=self.user, message=msg)

        await get_button(view, 1).callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        self.thread.send.assert_awaited_once()
        send_kwargs = self.thread.send.call_args.kwargs
        embeds = send_kwargs["embeds"]
        self.assertEqual(len(embeds), 2)
        # First embed: moderation ticket context
        self.assertEqual(embeds[0].title, f"Moderation Ticket — Case #{case_id} (Warn)")
        # Second embed: forwarded Safebrowsing context
        self.assertEqual(embeds[1].title, "Message context")
        self.assertEqual(embeds[1].description, "Message: Visit http://phishing-site.example.com")

    async def test_open_modmail_ticket_user_already_has_active_modmail(self):
        other_guild = create_mock_guild(guild_id=88888, name="Other Guild")
        await self.modmail_repo.create_modmail(
            user=self.user,
            guild=other_guild,
            uuid="existing-uuid-1234",
            anonymous=False,
        )

        view = ModerationQuickTicketView(
            bot=self.mock_client,
            infractions_repo=self.infractions_repo,
            modmail_repo=self.modmail_repo,
        )

        mod_embed = discord.Embed(title="Ban")
        mod_embed.set_footer(text="Case ID: 404")

        msg = MagicMock(spec=discord.Message)
        msg.embeds = [mod_embed]

        interaction = create_mock_interaction(user=self.user, message=msg)

        # Infraction exists
        case_id = await self.infractions_repo.create_infraction(
            user=self.user,
            infraction=InfractionsEnum.Ban,
            reason="Spam",
            guild=self.guild,
        )
        mod_embed.set_footer(text=f"Case ID: {case_id}")

        self.mock_client.get_or_fetch.side_effect = lambda obj_type, obj_id, default=None: (
            self.guild if obj_id == self.guild.id else other_guild
        )

        await get_button(view, 1).callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        # Thread should NOT be created
        self.modmail_channel.create_thread.assert_not_called()

        # Ephemeral response informing user of existing session
        interaction.followup.send.assert_awaited_once()
        call_args = interaction.followup.send.call_args
        self.assertIn("already have an open modmail session", call_args.args[0])
        self.assertIn(other_guild.name, call_args.args[0])
        self.assertIsInstance(call_args.kwargs.get("view"), EndModmailView)

    async def test_open_modmail_ticket_missing_case_in_db(self):
        view = ModerationQuickTicketView(
            bot=self.mock_client,
            infractions_repo=self.infractions_repo,
            modmail_repo=self.modmail_repo,
        )

        mod_embed = discord.Embed(title="Ban")
        mod_embed.set_footer(text="Case ID: 999999")

        msg = MagicMock(spec=discord.Message)
        msg.embeds = [mod_embed]

        interaction = create_mock_interaction(user=self.user, message=msg)

        await get_button(view, 1).callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once_with(
            "Could not find the moderation case in the database.", ephemeral=True
        )

    async def test_open_modmail_ticket_missing_case_id_in_footer(self):
        view = ModerationQuickTicketView(
            bot=self.mock_client,
            infractions_repo=self.infractions_repo,
            modmail_repo=self.modmail_repo,
        )

        mod_embed = discord.Embed(title="Ban")
        mod_embed.set_footer(text="No ID here")

        msg = MagicMock(spec=discord.Message)
        msg.embeds = [mod_embed]

        interaction = create_mock_interaction(user=self.user, message=msg)

        await get_button(view, 1).callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once_with(
            "Could not find the moderation case in the database.", ephemeral=True
        )

    async def test_open_modmail_ticket_unconfigured_modmail_channel(self):
        case_id = await self.infractions_repo.create_infraction(
            user=self.user,
            infraction=InfractionsEnum.Ban,
            reason="Rule violation",
            guild=self.guild,
        )

        self.mock_client.db.get_setting.return_value = None
        self.mock_client.get_or_fetch.return_value = self.guild

        view = ModerationQuickTicketView(
            bot=self.mock_client,
            infractions_repo=self.infractions_repo,
            modmail_repo=self.modmail_repo,
        )

        mod_embed = discord.Embed(title="Ban")
        mod_embed.set_footer(text=f"Case ID: {case_id}")

        msg = MagicMock(spec=discord.Message)
        msg.embeds = [mod_embed]

        interaction = create_mock_interaction(user=self.user, message=msg)

        await get_button(view, 1).callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        self.modmail_channel.create_thread.assert_not_called()
        interaction.followup.send.assert_awaited_once()
        self.assertIn("Modmail is not configured", interaction.followup.send.call_args.args[0])

    async def test_open_modmail_ticket_guild_not_found(self):
        case_id = await self.infractions_repo.create_infraction(
            user=self.user,
            infraction=InfractionsEnum.Ban,
            reason="Rule violation",
            guild=self.guild,
        )

        self.mock_client.get_or_fetch.return_value = None
        self.mock_client.get_guild.return_value = None

        view = ModerationQuickTicketView(
            bot=self.mock_client,
            infractions_repo=self.infractions_repo,
            modmail_repo=self.modmail_repo,
        )

        mod_embed = discord.Embed(title="Ban")
        mod_embed.set_footer(text=f"Case ID: {case_id}")

        msg = MagicMock(spec=discord.Message)
        msg.embeds = [mod_embed]

        interaction = create_mock_interaction(user=self.user, message=msg)

        await get_button(view, 1).callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once_with(
            "Could not find the server associated with this moderation case.", ephemeral=True
        )

    async def test_open_modmail_ticket_thread_creation_failure_leaves_no_modmail_record(self):
        case_id = await self.infractions_repo.create_infraction(
            user=self.user,
            infraction=InfractionsEnum.Ban,
            reason="Violating community rules",
            guild=self.guild,
        )

        setting_mock = SimpleNamespace(value=self.modmail_channel.id)
        self.mock_client.db.get_setting.return_value = setting_mock
        self.mock_client.get_or_fetch.return_value = self.guild
        self.guild.get_or_fetch.return_value = self.modmail_channel

        # Simulate create_thread failure
        self.modmail_channel.create_thread.side_effect = discord.HTTPException(
            MagicMock(status=500), "Discord thread error"
        )
        self.modmail_channel.send = AsyncMock(return_value=None)

        view = ModerationQuickTicketView(
            bot=self.mock_client,
            infractions_repo=self.infractions_repo,
            modmail_repo=self.modmail_repo,
        )

        dm_embed = discord.Embed(title="Ban", description="You have been banned")
        dm_embed.set_footer(text=f"Case ID: {case_id}")

        msg = MagicMock(spec=discord.Message)
        msg.embeds = [dm_embed]

        interaction = create_mock_interaction(user=self.user, message=msg)

        await get_button(view, 1).callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)

        # Ensure no Modmail record was created in DB
        mail = await self.modmail_repo.get_modmail(user=self.user)
        self.assertIsNone(mail)

        # Ephemeral error sent to user via followup
        interaction.followup.send.assert_awaited_once_with(
            "Failed to create a ticket thread. Please try again later.", ephemeral=True
        )

    async def test_on_ready_registers_persistent_view_on_both_cogs(self):
        mod_events = ModerationEvents(self.mock_client, infractions_repo=self.infractions_repo)
        await mod_events.on_ready()

        self.mock_client.add_view.assert_called()
        last_view = self.mock_client.add_view.call_args.args[0]
        self.assertIsInstance(last_view, ModerationQuickTicketView)

        self.mock_client.add_view.reset_mock()
        modmail_cog = ModMail(self.mock_client, modmail_repo=self.modmail_repo)
        await modmail_cog.on_ready()

        registered_views = [call.args[0] for call in self.mock_client.add_view.call_args_list]
        self.assertTrue(any(isinstance(v, ModerationQuickTicketView) for v in registered_views))
        self.assertTrue(any(isinstance(v, CloseModmailThreadView) for v in registered_views))
